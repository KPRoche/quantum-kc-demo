# QASM Circuit Files

This directory contains OpenQASM circuit definitions for quantum execution.

## Default Circuits (provided by container)

- `expt.qasm` - Default 5-qubit random number generator (QASM 2)
- `expt12.qasm` - 12-qubit Hadamard circuit (QASM 2)
- `expt16.qasm` - 16-qubit pattern circuit (QASM 2)
- `expt20.qasm` - 20-qubit superposition-and-measure template (QASM 2, v0.5.0+)
- `expt32.qasm` - 32-qubit extended circuit (QASM 2)
- `urs.qasm` - 3-qubit Universal Resource State preparation (QASM 3, v0.5.3+)

These ship inside the image, so they're always present after a pod
restart or rollout. `urs.qasm` is the canonical OpenQASM 3.x example —
use it to exercise the QASM 3 parsing path (`qiskit_qasm3_import`) and
the circuit-viewer endpoints introduced in v0.5.0/v0.5.2.

## Custom Circuits

You can add custom QASM files to this directory. They will be available for execution via the API or CLI with the `-f:filename.qasm` parameter.

### Persistence

Custom uploads are **session-local by design** — `/app/files/qasm/` is
backed by an `emptyDir` volume, not a `PersistentVolume`. Uploaded
files survive the lifetime of a single pod but are wiped when the pod
is deleted, restarted, or replaced (e.g. by a `kubectl rollout`,
`Deployment` image bump, or node eviction). After any of those events,
re-upload via `POST /api/qasm/file` or re-reference your circuit from
the client.

This is intentional: the workload is meant to be ephemeral and easy to
roll forward. If you need durable user-circuit storage, supply your
own `PersistentVolumeClaim` mounted at `/app/files/qasm/` in
`k8s/deployment.yaml` (the `qiskit-config` PV used for IBM credentials
is a working example). The default presets above are baked into the
image, not user uploads, so they always come back.

### QASM File Format

```qasm
OPENQASM 2.0;
include "qelib1.inc";

qreg q[5];
creg c[5];

h q[0];
h q[1];
h q[2];
h q[3];
h q[4];

measure q -> c;
```

## API Usage

Upload or reference QASM files via the `/api/qasm/file` endpoint.
