OPENQASM 3.0;
include "stdgates.inc";

// Universal Resource State preparation — single iteration.
// The original program retries this segment until both ancilla
// measurements come back 0 (probability 5/8 per try). qiskit's
// QASM 3 importer 0.6.0 doesn't yet support `def` with quantum
// arguments or `while` loops with classical conditions, so this
// version runs the segment once and lets the user see both
// outcomes in the histogram.

qubit psi;
qubit[2] anc;
bit[2] anc_bits;
bit psi_meas;

reset psi;
reset anc;

h psi;

// --- segment body, inlined ---
h anc[0];
h anc[1];
ccx anc[0], anc[1], psi;
s psi;
ccx anc[0], anc[1], psi;
z psi;
h anc[0];
h anc[1];
anc_bits[0] = measure anc[0];
anc_bits[1] = measure anc[1];
// --- end segment ---

// Final correction: rz(pi - arccos(3/5)) becomes a numeric literal
// because the importer's expression parser is conservative.
// pi - arccos(3/5) = 3.141593 - 0.927295 = 2.214297
rz(2.214297) psi;
h psi;
psi_meas = measure psi;
