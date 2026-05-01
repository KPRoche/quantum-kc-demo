OPENQASM 2.0;
include "qelib1.inc";

// Quantum Half-Adder
// A simple quantum circuit implementing a 1-bit half-adder.
//
// The circuit:
// - Takes 2 input qubits (q[0], q[1]) initialized to computational basis states
// - Computes sum (q[2]) and carry (q[3])
// - Uses CNOT gates for XOR logic and Toffoli for AND logic
//
// For default inputs (both q[0] and q[1] set to 1 via X gates):
// sum = 0 (1 XOR 1), carry = 1 (1 AND 1)

qreg q[4];
creg c[2];

// Initialize inputs (set both to 1 for this example)
// Comment out either X gate to test different input combinations
x q[0];  // Input A = 1
x q[1];  // Input B = 1

barrier q[0], q[1], q[2], q[3];

// Half-adder logic
// Sum: q[2] = q[0] XOR q[1]
cx q[0], q[2];
cx q[1], q[2];

// Carry: q[3] = q[0] AND q[1]
ccx q[0], q[1], q[3];

barrier q[0], q[1], q[2], q[3];

// Measure outputs
measure q[2] -> c[0];  // Sum bit
measure q[3] -> c[1];  // Carry bit
