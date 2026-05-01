OPENQASM 2.0;
include "qelib1.inc";

// Bell State (maximally entangled state)
// This circuit demonstrates the creation of a Bell state,
// which is fundamental to testing Bell's inequality and quantum entanglement.
//
// The circuit:
// 1. Applies a Hadamard gate to qubit 0, creating superposition: (|0⟩ + |1⟩)/√2
// 2. Applies a CNOT gate with q[0] as control and q[1] as target
// 3. This creates the entangled Bell state: (|00⟩ + |11⟩)/√2
// 4. Measures both qubits to collapse the state

qreg q[2];
creg c[2];

// Create superposition on first qubit
h q[0];

// Entangle the two qubits (CNOT with q[0] as control)
cx q[0], q[1];

// Measure both qubits
measure q -> c;
