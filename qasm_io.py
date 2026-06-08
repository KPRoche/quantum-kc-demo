"""Shared OpenQASM 2.0 / 3.x parsing and emission helpers.

Single source of truth for version sniffing and dispatch. Used by:
  - web_dashboard._validate_qasm (upload-boundary validation)
  - web_dashboard.QuantumExecutor.load_qasm (dashboard circuit cache)
  - QuantumKCDemo_v0_5.load_qasm_circuit (executor)

Keeping this in one place prevents drift like the v0.5.x circuit-viewer
gap, where the dashboard executor parsed only QASM 2 while the run path
already dispatched on version.
"""

from __future__ import annotations


def sniff_qasm_version(qasm_str: str) -> int:
    """Return 2 or 3 based on the first non-empty, non-comment line.

    Defaults to 2 if no OPENQASM directive is found or the version token
    cannot be parsed — matches the legacy behavior callers expect.
    """
    for line in qasm_str.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("OPENQASM"):
            try:
                ver_token = stripped.split()[1].rstrip(";")
                return int(float(ver_token))
            except (IndexError, ValueError):
                return 2
        return 2
    return 2


def loads_qasm(qasm_str: str):
    """Parse a QASM 2.0 or 3.x program into a QuantumCircuit.

    Returns (circuit, version) so callers that need to round-trip back
    to text know which dumper to use. Raises ValueError on parse failure
    with a clean message; callers can surface this to users without
    exposing internal traceback noise.
    """
    version = sniff_qasm_version(qasm_str)
    if version >= 3:
        from qiskit import qasm3
        try:
            return qasm3.loads(qasm_str), 3
        except Exception as e:
            raise ValueError(f"QASM 3 parse error: {type(e).__name__}: {e}") from e
    from qiskit import QuantumCircuit
    try:
        return QuantumCircuit.from_qasm_str(qasm_str), 2
    except Exception as e:
        raise ValueError(f"QASM 2 parse error: {type(e).__name__}: {e}") from e


def dumps_qasm(circuit, version: int = 2) -> str:
    """Serialize a QuantumCircuit back to QASM source.

    version=3 uses qiskit.qasm3.dumps; version=2 uses qasm2.dumps with a
    fallback to the deprecated circuit.qasm() for older Qiskit installs.
    On QASM 3 dump failure, falls back to QASM 2 so the viewer can still
    show something — circuits parsed from QASM 3 are usually expressible
    in QASM 2 unless they use 3-only constructs.
    """
    if version >= 3:
        try:
            from qiskit import qasm3
            return qasm3.dumps(circuit)
        except Exception:
            pass
    try:
        from qiskit import qasm2
        return qasm2.dumps(circuit)
    except Exception:
        return circuit.qasm()


def validate_qasm(qasm_str: str) -> tuple[bool, str]:
    """Pre-validate a QASM program. Returns (ok, message)."""
    try:
        loads_qasm(qasm_str)
    except ValueError as e:
        return False, str(e)
    return True, "ok"
