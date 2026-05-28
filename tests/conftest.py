"""Shared pytest fixtures for quantum-kc-demo tests.

The Flask app in ``web_dashboard.py`` does substantial work at import time
(Prometheus metrics registration, directory creation, ``quantum_control``
import). The ``quantum_control`` module hardcodes ``/app/files/control``
which doesn't exist outside the container, so we register a stub for it
in ``sys.modules`` *before* ``web_dashboard`` is imported. Individual tests
then patch auth-related paths/imports via the ``isolated_creds`` fixture.
"""
import sys
import tempfile
import types
from pathlib import Path

import pytest

# Make the repo root importable so ``import web_dashboard`` works regardless
# of the cwd pytest is invoked from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Build a ``quantum_control`` stub with the symbols ``web_dashboard`` imports.
# Tests for /api/auth/status do not exercise quantum-control IPC, so empty
# implementations are fine.
def _install_quantum_control_stub():
    if "quantum_control" in sys.modules:
        return
    qc = types.ModuleType("quantum_control")
    tmp = Path(tempfile.mkdtemp(prefix="qkcd-test-control-"))
    qc.CONTROL_DIR = tmp
    qc.CONTROL_FILE = tmp / "command.json"
    qc.CONTROL_LOCK_FILE = tmp / ".lock"
    qc.CONTROL_ENABLED = False

    def _noop(*a, **kw):
        return None

    qc.request_run = _noop
    qc.get_status = lambda: {"status": "waiting"}
    qc.initialize_control = _noop
    qc.write_command = _noop
    qc.read_command = lambda: None
    qc.acknowledge_command = _noop
    qc.command_complete = _noop
    qc.wait_for_command = lambda *a, **kw: None
    sys.modules["quantum_control"] = qc


_install_quantum_control_stub()


@pytest.fixture(scope="session")
def web_dashboard_module():
    """Import the Flask module exactly once per test session."""
    import web_dashboard
    return web_dashboard


@pytest.fixture
def client(web_dashboard_module):
    """A Flask test client for issuing requests to the app."""
    web_dashboard_module.app.config.update(TESTING=True)
    with web_dashboard_module.app.test_client() as c:
        yield c


@pytest.fixture
def isolated_creds(tmp_path, monkeypatch, web_dashboard_module):
    """Point both credential paths at a clean tmp directory.

    Yields a dict with the patched paths so tests can write/delete files
    to simulate stored / cleared / corrupted states.
    """
    creds_dir = tmp_path / "credentials"
    creds_dir.mkdir()
    qiskit_dir = tmp_path / "qiskit"
    qiskit_dir.mkdir()
    qiskit_account = qiskit_dir / "qiskit-ibm.json"

    monkeypatch.setattr(web_dashboard_module, "CREDENTIALS_DIR", creds_dir)
    monkeypatch.setattr(web_dashboard_module, "QISKIT_ACCOUNT_FILE", qiskit_account)

    return {
        "creds_dir": creds_dir,
        "auth_json": creds_dir / "auth.json",
        "qiskit_account": qiskit_account,
    }
