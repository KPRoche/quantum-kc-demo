"""
Web Dashboard for Quantum Raspberry Tie
Provides a browser-based interface for running quantum circuits and viewing results
"""

import os
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import numpy as np

# Import quantum execution logic
import sys
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)

# Configuration
SVG_DIR = Path(__file__).parent / "svg"
SVG_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR = Path(__file__).parent / "credentials"
CREDENTIALS_DIR.mkdir(exist_ok=True)

# Global state
quantum_state = {
    "running": False,
    "last_result": None,
    "last_result_time": None,
    "status": "ready",
    "message": "",
    "circuit_info": None,
    "backend_info": None,
    "loop_mode": False,
    "loop_process": None
}

state_lock = threading.Lock()

# Loop mode process management
import subprocess
loop_process = None


class QuantumExecutor:
    """Manages quantum circuit execution"""

    def __init__(self):
        self.backend = None
        self.qiskit_available = False
        self.circuit = None

    def initialize(self):
        """Initialize Qiskit components"""
        try:
            from qiskit import QuantumCircuit, transpile
            from qiskit_aer import Aer
            from qiskit_ibm_runtime.fake_provider import FakeManilaV2
            self.qiskit_available = True
            self.QuantumCircuit = QuantumCircuit
            self.transpile = transpile
            self.Aer = Aer
            self.FakeManilaV2 = FakeManilaV2
            return True
        except ImportError as e:
            print(f"Failed to initialize Qiskit: {e}")
            return False

    def load_qasm(self, qasm_content):
        """Load and parse QASM content"""
        if not self.qiskit_available:
            return False
        try:
            self.circuit = self.QuantumCircuit.from_qasm_str(qasm_content)
            return True
        except Exception as e:
            print(f"Failed to load QASM: {e}")
            return False

    def execute(self, backend_name="local", shots=10):
        """Execute circuit on specified backend"""
        if not self.circuit or not self.qiskit_available:
            return None

        try:
            if backend_name == "local":
                backend = self.Aer.get_backend('qasm_simulator')
            else:
                # Try to use fake backend for testing
                backend = self.FakeManilaV2()

            # Transpile circuit for backend
            transpiled = self.transpile(self.circuit, backend)

            # Execute
            job = backend.run(transpiled, shots=shots)
            result = job.result()

            counts = result.get_counts()
            return {
                "counts": counts,
                "backend": str(backend),
                "timestamp": datetime.now().isoformat(),
                "shots": shots,
                "num_qubits": self.circuit.num_qubits
            }
        except Exception as e:
            print(f"Execution error: {e}")
            return None


executor = QuantumExecutor()


@app.route("/")
def index():
    """Serve the main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/status")
def get_status():
    """Get current quantum state"""
    with state_lock:
        return jsonify(quantum_state)


@app.route("/api/execute", methods=["POST"])
def execute_circuit():
    """Execute a quantum circuit"""
    global quantum_state

    if quantum_state["running"]:
        return jsonify({"error": "Already running"}), 409

    data = request.json or {}
    qasm_file = data.get("qasm_file", "expt.qasm")
    backend = data.get("backend", "local")
    shots = data.get("shots", 10)
    qubits = data.get("qubits", 5)

    def run_execution():
        global quantum_state
        with state_lock:
            quantum_state["running"] = True
            quantum_state["status"] = "loading_circuit"

        try:
            # Load QASM file
            qasm_path = Path(__file__).parent / qasm_file
            if not qasm_path.exists():
                with state_lock:
                    quantum_state["status"] = "error"
                    quantum_state["message"] = f"QASM file not found: {qasm_file}"
                return

            with open(qasm_path, 'r') as f:
                qasm_content = f.read()

            if not executor.load_qasm(qasm_content):
                with state_lock:
                    quantum_state["status"] = "error"
                    quantum_state["message"] = "Failed to parse QASM"
                return

            with state_lock:
                quantum_state["status"] = "executing"
                quantum_state["circuit_info"] = {
                    "qubits": executor.circuit.num_qubits,
                    "gates": executor.circuit.size()
                }

            # Execute circuit
            result = executor.execute(backend, shots)

            if result:
                with state_lock:
                    quantum_state["last_result"] = result
                    quantum_state["last_result_time"] = datetime.now().isoformat()
                    quantum_state["status"] = "success"
                    quantum_state["message"] = "Circuit executed successfully"
                    quantum_state["backend_info"] = {"name": backend, "shots": shots}

                # Generate SVG
                generate_result_svg(result)
            else:
                with state_lock:
                    quantum_state["status"] = "error"
                    quantum_state["message"] = "Execution failed"

        except Exception as e:
            print(f"Error in run_execution: {e}")
            with state_lock:
                quantum_state["status"] = "error"
                quantum_state["message"] = str(e)

        finally:
            with state_lock:
                quantum_state["running"] = False

    # Run in background thread
    thread = threading.Thread(target=run_execution, daemon=True)
    thread.start()

    return jsonify({"status": "submitted"})


@app.route("/api/svg")
def get_svg():
    """Get the current SVG result with auto-refresh"""
    svg_path = SVG_DIR / "pixels.html"
    if svg_path.exists():
        # Create an auto-refreshing wrapper page
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { margin: 0; padding: 10px; background: #f0f0f0; font-family: Arial, sans-serif; }
                .container { max-width: 1000px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                #svg-content { margin: 20px 0; }
                .status { color: #666; font-size: 12px; }
                .refresh-info { background: #e3f2fd; padding: 10px; border-radius: 3px; margin-bottom: 10px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🔄 Live Quantum Visualization (Auto-refreshing every 1s)</h2>
                <div class="refresh-info">
                    <span class="status">Last updated: <span id="update-time">loading...</span></span>
                </div>
                <div id="svg-content"></div>
            </div>

            <script>
                function loadSVG() {
                    fetch('/api/svg/raw')
                        .then(response => response.text())
                        .then(html => {
                            document.getElementById('svg-content').innerHTML = html;
                            document.getElementById('update-time').textContent = new Date().toLocaleTimeString();
                        })
                        .catch(err => {
                            console.error('Error loading SVG:', err);
                            document.getElementById('svg-content').innerHTML = '<p style="color: red;">Error loading visualization...</p>';
                        });
                }

                // Load immediately
                loadSVG();

                // Refresh every 1 second
                setInterval(loadSVG, 1000);
            </script>
        </body>
        </html>
        """
        return html_content, 200, {'Content-Type': 'text/html'}
    return jsonify({"error": "No result available"}), 404


@app.route("/api/svg/raw")
def get_svg_raw():
    """Get the raw SVG content (without wrapper)"""
    svg_path = SVG_DIR / "pixels.html"
    if svg_path.exists():
        with open(svg_path, 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    return "<p>No visualization available yet. Start the quantum program first.</p>", 404, {'Content-Type': 'text/html'}


@app.route("/api/result")
def get_result():
    """Get the last execution result"""
    with state_lock:
        if quantum_state["last_result"]:
            return jsonify(quantum_state["last_result"])
    return jsonify({"error": "No result available"}), 404


@app.route("/api/config", methods=["GET", "POST"])
def config():
    """Get or set configuration"""
    if request.method == "POST":
        data = request.json or {}
        # Store configuration
        config_path = CREDENTIALS_DIR / "config.json"
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"status": "saved"})
    else:
        config_path = CREDENTIALS_DIR / "config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                return jsonify(json.load(f))
        return jsonify({})


@app.route("/api/auth/save", methods=["POST"])
def save_authentication():
    """Save IBM Quantum authentication credentials"""
    data = request.json or {}
    api_key = data.get("api_key", "").strip()
    crn = data.get("crn", "").strip()

    if not api_key or not crn:
        return jsonify({"error": "Both API Key and CRN are required"}), 400

    try:
        # Import Qiskit Runtime Service
        from qiskit_ibm_runtime import QiskitRuntimeService

        # Save the account credentials
        QiskitRuntimeService.save_account(
            token=api_key,
            instance=crn,
            overwrite=True,
            set_as_default=True
        )

        # Also store in our config for reference
        config_path = CREDENTIALS_DIR / "auth.json"
        auth_data = {
            "authenticated": True,
            "timestamp": datetime.now().isoformat(),
            "crn_masked": crn[:20] + "..." if len(crn) > 20 else crn
        }
        with open(config_path, 'w') as f:
            json.dump(auth_data, f, indent=2)

        return jsonify({
            "status": "saved",
            "message": "IBM Quantum credentials saved successfully",
            "authenticated": True
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "message": "Failed to save credentials"
        }), 500


@app.route("/api/auth/status", methods=["GET"])
def get_auth_status():
    """Check if IBM Quantum authentication is configured"""
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService
        from qiskit_ibm_runtime.accounts.exceptions import AccountNotFoundError

        try:
            service = QiskitRuntimeService()
            # If we get here, authentication is available
            config_path = CREDENTIALS_DIR / "auth.json"
            crn_display = "Configured"

            if config_path.exists():
                with open(config_path, 'r') as f:
                    auth_data = json.load(f)
                    crn_display = auth_data.get("crn_masked", "Configured")

            return jsonify({
                "authenticated": True,
                "message": "IBM Quantum credentials are configured",
                "crn": crn_display
            })

        except AccountNotFoundError:
            return jsonify({
                "authenticated": False,
                "message": "No IBM Quantum credentials found. Please configure authentication."
            })

    except Exception as e:
        return jsonify({
            "authenticated": False,
            "message": f"Error checking authentication: {str(e)}"
        }), 500


@app.route("/api/loop/status", methods=["GET"])
def get_loop_status():
    """Get the current loop mode status"""
    with state_lock:
        return jsonify({
            "loop_mode": quantum_state["loop_mode"],
            "status": quantum_state["status"],
            "message": quantum_state.get("message", "")
        })


@app.route("/api/loop/start", methods=["POST"])
def start_loop_mode():
    """Start continuous loop mode"""
    global loop_process

    with state_lock:
        if quantum_state["loop_mode"]:
            return jsonify({"error": "Loop mode already running"}), 409

        quantum_state["loop_mode"] = True
        quantum_state["status"] = "starting_loop"
        quantum_state["message"] = "Starting loop mode..."

    try:
        # Start the quantum program with loop mode
        # Using app.py -b:aer -hex (or -b:aer_noise for noise model)
        app_path = Path(__file__).parent / "app.py"
        loop_process = subprocess.Popen(
            ["python", str(app_path), "-b:aer", "-hex"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        with state_lock:
            quantum_state["status"] = "loop_running"
            quantum_state["message"] = "Loop mode active - continuously executing quantum circuits"

        return jsonify({"status": "loop_started", "message": "Quantum program running in loop mode"})

    except Exception as e:
        with state_lock:
            quantum_state["loop_mode"] = False
            quantum_state["status"] = "error"
            quantum_state["message"] = f"Failed to start loop mode: {str(e)}"
        loop_process = None
        return jsonify({"error": str(e)}), 500


@app.route("/api/loop/stop", methods=["POST"])
def stop_loop_mode():
    """Stop continuous loop mode"""
    global loop_process

    with state_lock:
        if not quantum_state["loop_mode"]:
            return jsonify({"error": "Loop mode not running"}), 409

    try:
        if loop_process and loop_process.poll() is None:
            loop_process.terminate()
            try:
                loop_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                loop_process.kill()
                loop_process.wait()

        with state_lock:
            quantum_state["loop_mode"] = False
            quantum_state["status"] = "stopped"
            quantum_state["message"] = "Loop mode stopped"

        loop_process = None
        return jsonify({"status": "loop_stopped", "message": "Quantum program stopped"})

    except Exception as e:
        with state_lock:
            quantum_state["status"] = "error"
            quantum_state["message"] = f"Error stopping loop: {str(e)}"
        return jsonify({"error": str(e)}), 500


def generate_result_svg(result):
    """Generate SVG visualization of results"""
    if not result or "counts" not in result:
        return

    counts = result["counts"]
    num_qubits = result.get("num_qubits", 5)

    # Find the most common result
    most_common = max(counts, key=counts.get)

    # Create simple HTML with SVG visualization
    svg_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="2">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            svg {{ border: 1px solid #ccc; margin: 20px 0; }}
            .stats {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
            .info {{ color: #666; font-size: 12px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Quantum Circuit Results</h2>
            <svg width="400" height="60" viewBox="0 0 400 60">
                <!-- Display qubit results as colored squares -->
    """

    # Generate colored squares for each qubit
    x = 20
    for i, bit in enumerate(reversed(most_common)):
        color = "red" if bit == "0" else "blue"
        svg_content += f'            <rect x="{x}" y="10" width="30" height="30" fill="{color}" stroke="black" stroke-width="1"/>\n'
        svg_content += f'            <text x="{x + 7}" y="32" font-size="10" fill="white" font-weight="bold">{i}</text>\n'
        x += 40

    svg_content += """
            </svg>
            <div class="stats">
                <h3>Most Common Result: """ + most_common + """</h3>
                <p>Probability: """ + f"{counts[most_common] / sum(counts.values()) * 100:.1f}%" + """</p>
                <div class="info">
    """

    # Show all results distribution
    for result_str, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        prob = count / sum(counts.values()) * 100
        svg_content += f"                <div>{result_str}: {count} shots ({prob:.1f}%)</div>\n"

    svg_content += """
                </div>
                <div class="info">
                    Timestamp: """ + result.get("timestamp", "") + """<br>
                    Backend: """ + result.get("backend", "") + """<br>
                    Total Shots: """ + str(result.get("shots", 10)) + """
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Write to file
    output_path = SVG_DIR / "pixels.html"
    with open(output_path, 'w') as f:
        f.write(svg_content)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error"}), 500


def main():
    """Start the web dashboard"""
    print("Initializing Quantum Executor...")
    if not executor.initialize():
        print("Warning: Qiskit not available, dashboard will be in demo mode")

    print("Starting web dashboard on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
