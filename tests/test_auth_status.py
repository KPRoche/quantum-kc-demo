"""Tests for ``GET /api/auth/status`` (v0.4.0 response shape).

Covers the normal-path 200 cases (no token, token stored + validates,
token stored + drift, token stored + transient IBM blip, token stored +
fatal non-transient error) and the narrow 500 paths (corrupt auth.json,
qiskit not importable).

Tests stub Qiskit at ``web_dashboard.QiskitRuntimeService`` import time so
they never reach a real IBM endpoint.
"""
import json
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_qiskit_stub(behavior, monkeypatch):
    """Install a fake ``qiskit_ibm_runtime`` module before the handler runs.

    ``behavior`` controls what ``QiskitRuntimeService()`` does when called:
      - ``"ok"``         — instantiates successfully (authenticated path)
      - ``"not_found"``  — raises ``AccountNotFoundError``
      - ``"transient"``  — raises a generic Exception with a retryable msg
      - ``"fatal"``      — raises a generic Exception with a non-retryable msg
      - ``"missing"``    — pretend qiskit_ibm_runtime is not importable
    """
    if behavior == "missing":
        # Force the inner ``import qiskit_ibm_runtime`` to fail.
        monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime", None)
        return

    fake_runtime = types.ModuleType("qiskit_ibm_runtime")
    fake_accounts = types.ModuleType("qiskit_ibm_runtime.accounts")
    fake_exceptions = types.ModuleType("qiskit_ibm_runtime.accounts.exceptions")

    class _AccountNotFoundError(Exception):
        pass

    fake_exceptions.AccountNotFoundError = _AccountNotFoundError
    fake_accounts.exceptions = fake_exceptions

    if behavior == "ok":
        class _Service:
            def __init__(self, *a, **kw):
                pass
        fake_runtime.QiskitRuntimeService = _Service
    elif behavior == "not_found":
        class _Service:
            def __init__(self, *a, **kw):
                raise _AccountNotFoundError("no account named 'default'")
        fake_runtime.QiskitRuntimeService = _Service
    elif behavior == "transient":
        class _Service:
            def __init__(self, *a, **kw):
                raise Exception("max retries attempted; service unavailable")
        fake_runtime.QiskitRuntimeService = _Service
    elif behavior == "fatal":
        class _Service:
            def __init__(self, *a, **kw):
                raise Exception("invalid api key")
        fake_runtime.QiskitRuntimeService = _Service
    else:
        raise ValueError(f"unknown behavior: {behavior}")

    monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime", fake_runtime)
    monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime.accounts", fake_accounts)
    monkeypatch.setitem(
        sys.modules, "qiskit_ibm_runtime.accounts.exceptions", fake_exceptions
    )


def _write_auth_json(path, crn_masked="crn:v1:bluemix:..."):
    path.write_text(json.dumps({
        "authenticated": True,
        "timestamp": "2026-05-28T12:00:00",
        "crn_masked": crn_masked,
    }))


# ---------------------------------------------------------------------------
# Normal path: 200 responses
# ---------------------------------------------------------------------------


class TestAuthStatusNormalPath:
    def test_no_token_returns_token_stored_false(self, client, isolated_creds, monkeypatch):
        _install_qiskit_stub("ok", monkeypatch)  # never reached

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is False
        assert body["authenticated"] is False
        assert body["lastIbmError"] is None
        assert "No IBM Quantum credentials found" in body["message"]
        assert "crn" not in body

    def test_auth_json_present_and_validates(self, client, isolated_creds, monkeypatch):
        _write_auth_json(isolated_creds["auth_json"], crn_masked="crn:masked")
        _install_qiskit_stub("ok", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is True
        assert body["crn"] == "crn:masked"
        assert body["lastIbmError"] is None

    def test_qiskit_account_present_no_auth_json_simulates_pod_restart(
        self, client, isolated_creds, monkeypatch
    ):
        # Pod restart scenario: auth.json gone (emptyDir), Qiskit file
        # survives on the PV. tokenStored must still be True.
        isolated_creds["qiskit_account"].write_text("{}")
        _install_qiskit_stub("ok", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is True
        # No masked CRN available — that's fine; UI falls back gracefully.
        assert "crn" not in body

    def test_account_not_found_drift_state(self, client, isolated_creds, monkeypatch):
        _write_auth_json(isolated_creds["auth_json"])
        _install_qiskit_stub("not_found", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is False
        assert body["lastIbmError"] is not None
        assert body["lastIbmError"]["code"] == "account_not_found"
        assert body["lastIbmError"]["retryable"] is False

    def test_transient_ibm_error_classified_retryable(
        self, client, isolated_creds, monkeypatch
    ):
        # The motivating bug: IBM upstream blips like "max retries attempted"
        # must NOT 500, must classify as retryable so the Console can render
        # the soft yellow banner instead of the scary red one.
        _write_auth_json(isolated_creds["auth_json"])
        _install_qiskit_stub("transient", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is False
        assert body["lastIbmError"]["code"] == "service_unavailable"
        assert body["lastIbmError"]["retryable"] is True
        assert "max retries" in body["lastIbmError"]["message"]

    def test_fatal_ibm_error_not_retryable(self, client, isolated_creds, monkeypatch):
        _write_auth_json(isolated_creds["auth_json"])
        _install_qiskit_stub("fatal", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is False
        assert body["lastIbmError"]["code"] == "unknown"
        assert body["lastIbmError"]["retryable"] is False

    @pytest.mark.parametrize("msg,expected_code", [
        ("Rate limit exceeded for IBM API", "rate_limited"),
        ("HTTP 429 Too Many Requests", "rate_limited"),
        ("Service Unavailable", "service_unavailable"),
        ("HTTP 503 Bad Gateway", "service_unavailable"),
        ("max retries attempted", "service_unavailable"),
        ("Connection timed out", "timeout"),
        ("Read timeout", "timeout"),
    ])
    def test_classifier_keyword_coverage(
        self, client, isolated_creds, monkeypatch, msg, expected_code
    ):
        _write_auth_json(isolated_creds["auth_json"])

        # Build a one-off stub that raises with this specific message.
        fake_runtime = types.ModuleType("qiskit_ibm_runtime")
        fake_accounts = types.ModuleType("qiskit_ibm_runtime.accounts")
        fake_exceptions = types.ModuleType("qiskit_ibm_runtime.accounts.exceptions")

        class _AccountNotFoundError(Exception):
            pass

        fake_exceptions.AccountNotFoundError = _AccountNotFoundError
        fake_accounts.exceptions = fake_exceptions

        class _Service:
            def __init__(self, *a, **kw):
                raise Exception(msg)

        fake_runtime.QiskitRuntimeService = _Service
        monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime", fake_runtime)
        monkeypatch.setitem(sys.modules, "qiskit_ibm_runtime.accounts", fake_accounts)
        monkeypatch.setitem(
            sys.modules, "qiskit_ibm_runtime.accounts.exceptions", fake_exceptions
        )

        resp = client.get("/api/auth/status")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["lastIbmError"]["code"] == expected_code
        assert body["lastIbmError"]["retryable"] is True


# ---------------------------------------------------------------------------
# Narrow 500 paths (truly unrecoverable handler-level failures)
# ---------------------------------------------------------------------------


class TestAuthStatus500Paths:
    def test_corrupt_auth_json_returns_500(self, client, isolated_creds, monkeypatch):
        # Write garbage that will fail json.load() — this is the narrow 500
        # path: we know there's a credentials file but cannot read it.
        isolated_creds["auth_json"].write_text("{not valid json")
        _install_qiskit_stub("ok", monkeypatch)  # never reached

        resp = client.get("/api/auth/status")

        assert resp.status_code == 500
        body = resp.get_json()
        # Even on 500, the structured shape stays consistent — the Console
        # can render a generic error without parsing free-form text.
        assert "tokenStored" in body
        assert "authenticated" in body
        assert "unreadable" in body["message"].lower()

    def test_qiskit_runtime_unimportable_returns_500(
        self, client, isolated_creds, monkeypatch
    ):
        _write_auth_json(isolated_creds["auth_json"])
        _install_qiskit_stub("missing", monkeypatch)

        resp = client.get("/api/auth/status")

        assert resp.status_code == 500
        body = resp.get_json()
        assert body["tokenStored"] is True
        assert body["authenticated"] is False
        assert "qiskit" in body["message"].lower()
