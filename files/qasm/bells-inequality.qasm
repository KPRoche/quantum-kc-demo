OPENQASM 2.0;
include "qelib1.inc";

// Bell's Inequality Test Circuit
// This circuit tests Bell's inequality by preparing a Bell state
// and measuring correlations between entangled qubits.
//
// Bell's inequality (CHSH inequality) states that for local hidden
// variable theories:
//   |E(a,b) - E(a,b') + E(a',b) + E(a',b')| ≤ 2
//
// Quantum mechanics can violate this bound, achieving up to 2√2 ≈ 2.828
//
// This circuit:
// 1. Prepares a Bell state (|Φ+⟩ = (|00⟩ + |11⟩)/√2)
// 2. Applies measurement basis rotations simulating different angle choices
// 3. Measures both qubits to compute correlations
//
// For a complete Bell test, this should be run multiple times with
// different angle settings (a, a', b, b') to collect statistics.

qreg q[2];
creg c[2];

// Prepare Bell state |Φ+⟩ = (|00⟩ + |11⟩)/√2
h q[0];
cx q[0], q[1];

// Apply measurement basis rotation on q[0]
// For CHSH test: rotate by angle a (here: 0°)
// Alternative angles: 22.5° or 45° for other measurement settings
// ry(0.0) q[0];  // 0° rotation (computational basis)

// Apply measurement basis rotation on q[1]
// For CHSH test: rotate by angle b (here: 22.5°)
// Alternative angles: 0° or 45° for other measurement settings
// ry(0.3926991) q[1];  // 22.5° rotation

// Measure both qubits
measure q[0] -> c[0];
measure q[1] -> c[1];

// Expected results for Bell state correlation:
// - When both qubits measured in same basis: strong anti-correlation
//   (results tend to be opposite)
// - When measured in different bases: weaker correlation
// - Statistical analysis reveals violation of classical bounds
