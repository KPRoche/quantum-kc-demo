# QASM Circuit Files

This directory contains OpenQASM circuit definitions for quantum execution.

## Default Circuits (provided by container)

- `expt.qasm` - Default 5-qubit random number generator
- `expt12.qasm` - 12-qubit Hadamard circuit
- `expt16.qasm` - 16-qubit pattern circuit
- `expt32.qasm` - 32-qubit extended circuit

## Custom Circuits

You can add custom QASM files to this directory. They will be available for execution via the API or CLI with the `-f:filename.qasm` parameter.

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
