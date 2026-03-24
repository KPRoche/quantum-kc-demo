"""
Web Dashboard for Quantum KC Demo
Provides a browser-based interface for running quantum circuits and viewing results
"""

import os
import json
import threading
import time
import queue as queue_module
import uuid
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import numpy as np

# Import quantum execution logic
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Try to import quantum control system
try:
    from quantum_control import request_run, get_status as get_control_status, CONTROL_ENABLED
except ImportError:
    CONTROL_ENABLED = False
    def request_run(*args, **kwargs):
        """Stub if control system unavailable"""
        return False
    def get_control_status():
        return {"status": "unavailable"}

app = Flask(__name__)
CORS(app)


@app.before_request
def track_http_request():
    """Track HTTP requests for Prometheus metrics (exclude probes)"""
    # Exclude health/metrics endpoints from tracking
    if request.path not in ["/health", "/ready", "/metrics"]:
        with metrics_lock:
            key = (request.path, request.method)
            metrics["http_requests"][key] = metrics["http_requests"].get(key, 0) + 1

# Configuration
SVG_DIR = Path(__file__).parent / "svg"
SVG_DIR.mkdir(exist_ok=True)
QASM_DIR = Path(__file__).parent / "qasm"
QASM_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR = Path(__file__).parent / "credentials"
CREDENTIALS_DIR.mkdir(exist_ok=True)

# Preset QASM files in project root
PRESET_QASM_FILES = ["expt.qasm", "expt12.qasm", "expt16.qasm"]

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
    "qasm_file": "expt.qasm"
}

state_lock = threading.Lock()
loop_lock = threading.Lock()

# Startup timestamp for liveness probe
APP_START_TIME = time.time()

# Cluster node registry
cluster_registry = {}
cluster_lock = threading.Lock()

# Job queue management
job_queue = queue_module.Queue()
job_store = {}
job_lock = threading.Lock()

# Prometheus-style metrics
metrics_lock = threading.Lock()
metrics = {
    "jobs_completed": 0,
    "jobs_failed": 0,
    "jobs_cancelled": 0,
    "execution_durations": [],
    "http_requests": {}
}

# Loop mode process management
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


# ============================================================================
# HEALTH & READINESS PROBES (Kubernetes)
# ============================================================================

@app.route("/health")
def health():
    """Liveness probe: verify app is alive and not deadlocked"""
    try:
        # Try to acquire lock with timeout to detect deadlock
        acquired = state_lock.acquire(timeout=1.0)
        if not acquired:
            return jsonify({"status": "error", "reason": "lock_timeout", "timestamp": datetime.now().isoformat()}), 503
        state_lock.release()

        uptime = time.time() - APP_START_TIME
        return jsonify({
            "status": "ok",
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e), "timestamp": datetime.now().isoformat()}), 503


@app.route("/ready")
def ready():
    """Readiness probe: returns 200 only if Qiskit is initialized and ready"""
    if executor.qiskit_available:
        return jsonify({
            "status": "ready",
            "qiskit_available": True,
            "timestamp": datetime.now().isoformat()
        }), 200
    else:
        return jsonify({
            "status": "not_ready",
            "reason": "qiskit_not_initialized",
            "timestamp": datetime.now().isoformat()
        }), 503


# ============================================================================
# QUBIT MEASUREMENT READ
# ============================================================================

@app.route("/api/qubits")
def get_qubits():
    """Get the latest qubit measurement as a string and structured data"""
    with state_lock:
        if not quantum_state["last_result"]:
            return jsonify({"error": "No measurement available yet"}), 404

        result = quantum_state["last_result"]
        counts = result.get("counts", {})

    if not counts:
        return jsonify({"error": "No measurement data available"}), 404

    # Get most common pattern (same logic as SVG generation)
    pattern = max(counts, key=counts.get)
    num_qubits = len(pattern)

    # Convert pattern string to structured qubits array
    qubits = [{"index": i, "value": int(bit)} for i, bit in enumerate(reversed(pattern))]

    return jsonify({
        "pattern": pattern,
        "qubits": qubits,
        "num_qubits": num_qubits,
        "timestamp": quantum_state.get("last_result_time"),
        "backend": result.get("backend"),
        "shots": result.get("shots")
    }), 200


@app.route("/api/endpoints")
def list_endpoints():
    """Get a map of all available API endpoints"""
    endpoints = {
        "core": [
            {"path": "/", "method": "GET", "description": "Serve main dashboard page"},
            {"path": "/api/status", "method": "GET", "description": "Get current quantum state"},
            {"path": "/api/result", "method": "GET", "description": "Get last execution result"},
            {"path": "/api/endpoints", "method": "GET", "description": "Get all available endpoints (this endpoint)"}
        ],
        "execution": [
            {"path": "/api/execute", "method": "POST", "description": "Execute a quantum circuit (returns job_id)"},
            {"path": "/api/svg", "method": "GET", "description": "Get SVG result with auto-refresh wrapper"},
            {"path": "/api/svg/raw", "method": "GET", "description": "Get raw SVG/HTML content without wrapper"}
        ],
        "job_queue": [
            {"path": "/api/jobs", "method": "POST", "description": "Submit a job to the queue"},
            {"path": "/api/jobs", "method": "GET", "description": "List all jobs (optional ?status= filter)"},
            {"path": "/api/jobs/<job_id>", "method": "GET", "description": "Get a specific job's status and result"},
            {"path": "/api/jobs/<job_id>/cancel", "method": "POST", "description": "Cancel a queued job or interrupt running job"}
        ],
        "qasm_management": [
            {"path": "/api/qasm/file", "method": "GET/POST", "description": "Get or save QASM files"},
            {"path": "/api/qasm/active", "method": "GET/POST", "description": "Get or load active QASM in executor"},
            {"path": "/api/qasm/circuit", "method": "GET", "description": "Get circuit diagram as HTML with matplotlib image"},
            {"path": "/api/qasm/circuit/raw", "method": "GET", "description": "Get circuit diagram as ASCII art text (returns 'circuit not rendered yet' if no circuit)"},
            {"path": "/api/qasm/circuit/ascii", "method": "GET", "description": "Get circuit diagram as ASCII art text drawing (same as /circuit/raw)"}
        ],
        "qubit_measurement": [
            {"path": "/api/qubits", "method": "GET", "description": "Get the latest qubit measurement as string and structured data"}
        ],
        "configuration": [
            {"path": "/api/config", "method": "GET/POST", "description": "Get or set configuration"},
            {"path": "/api/auth/save", "method": "POST", "description": "Save IBM Quantum credentials"},
            {"path": "/api/auth/status", "method": "GET", "description": "Check authentication status"}
        ],
        "loop_mode": [
            {"path": "/api/loop/status", "method": "GET", "description": "Get loop mode status"},
            {"path": "/api/loop/start", "method": "POST", "description": "Start continuous loop execution"},
            {"path": "/api/loop/stop", "method": "POST", "description": "Stop continuous loop execution"}
        ],
        "cluster_coordination": [
            {"path": "/api/cluster/register", "method": "POST", "description": "Register a node in the cluster"},
            {"path": "/api/cluster/heartbeat", "method": "POST", "description": "Update last_seen for a node"},
            {"path": "/api/cluster/nodes", "method": "GET", "description": "List all registered nodes"},
            {"path": "/api/cluster/nodes/<node_id>", "method": "DELETE", "description": "Deregister a node"},
            {"path": "/api/cluster/status", "method": "GET", "description": "Get cluster status summary"}
        ],
        "health_and_monitoring": [
            {"path": "/health", "method": "GET", "description": "Liveness probe (Kubernetes)"},
            {"path": "/ready", "method": "GET", "description": "Readiness probe (Kubernetes)"},
            {"path": "/metrics", "method": "GET", "description": "Prometheus text exposition format metrics"}
        ]
    }

    return jsonify({
        "base_url": "http://localhost:5000",
        "endpoints": endpoints,
        "timestamp": datetime.now().isoformat(),
        "total_endpoints": sum(len(v) for v in endpoints.values())
    }), 200


@app.route("/")
def index():
    """Serve the main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/status")
def get_status():
    """Get current quantum state and control system status"""
    with state_lock:
        status_response = dict(quantum_state)
        # Add control system status if available
        if CONTROL_ENABLED:
            status_response["control_system"] = get_control_status()
            status_response["execution_mode"] = "control-based"
        else:
            status_response["execution_mode"] = "queue-based"
        return jsonify(status_response)


@app.route("/api/execute", methods=["POST"])
def execute_circuit():
    """Execute a quantum circuit (via control system or job queue)"""
    data = request.json or {}
    qasm_file = data.get("qasm_file", "expt.qasm")
    backend = data.get("backend", "local")
    shots = data.get("shots", 10)

    # Build parameters list for quantum app
    parameters = []

    # Map backend to quantum app parameters
    if backend and backend != "local":
        if "aer" in backend.lower():
            parameters.append("-b:aer")
        elif "least" in backend.lower():
            parameters.append("-b:least")
        else:
            parameters.append(f"-b:{backend}")

    # Add file parameter if specified
    if qasm_file and qasm_file != "expt.qasm":
        parameters.append(f"-f:{qasm_file}")

    job_id = str(uuid.uuid4())
    description = f"Execute {qasm_file} on {backend} backend"

    # If control system is enabled, send command to quantum process
    if CONTROL_ENABLED:
        success = request_run(parameters, description)
        if success:
            with job_lock:
                job_store[job_id] = {
                    "job_id": job_id,
                    "status": "submitted_to_quantum",
                    "parameters": {
                        "qasm_file": qasm_file,
                        "backend": backend,
                        "shots": shots,
                        "quantum_parameters": parameters
                    },
                    "submitted_at": datetime.now().isoformat(),
                    "started_at": None,
                    "completed_at": None,
                    "result": None,
                    "error": None
                }
            return jsonify({
                "status": "submitted_to_quantum",
                "job_id": job_id,
                "description": description
            }), 202
        else:
            return jsonify({
                "status": "error",
                "error": "Failed to submit command to quantum process"
            }), 500

    # Fallback to job queue if control system unavailable
    with job_lock:
        job_store[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "parameters": {
                "qasm_file": qasm_file,
                "backend": backend,
                "shots": shots
            },
            "submitted_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None
        }

    # Enqueue the job
    job_queue.put(job_id)

    return jsonify({
        "status": "queued",
        "job_id": job_id
    }), 202


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


# ============================================================================
# QASM MANAGEMENT
# ============================================================================

@app.route("/api/qasm/file", methods=["GET", "POST"])
def qasm_file():
    """Get or save QASM files"""
    if request.method == "GET":
        # Get QASM file content
        filename = request.args.get("name")

        if not filename:
            # Return currently active QASM file and content
            with state_lock:
                filename = quantum_state.get("qasm_file", "expt.qasm")

        # Determine file location
        if filename in PRESET_QASM_FILES:
            qasm_path = Path(__file__).parent / filename
            source = "preset"
        else:
            qasm_path = QASM_DIR / filename
            source = "user"

        # Check if file exists
        if not qasm_path.exists():
            return jsonify({"error": f"QASM file not found: {filename}"}), 404

        # Read and return file
        try:
            with open(qasm_path, 'r') as f:
                content = f.read()
            return jsonify({
                "name": filename,
                "content": content,
                "source": source
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == "POST":
        # Save QASM file
        data = request.json or {}
        filename = data.get("name", "").strip()
        content = data.get("content", "").strip()

        if not filename or not content:
            return jsonify({"error": "Both 'name' and 'content' are required"}), 400

        # Determine file location
        if filename in PRESET_QASM_FILES:
            qasm_path = Path(__file__).parent / filename
            source = "preset"
        else:
            qasm_path = QASM_DIR / filename
            source = "user"

        # Write file
        try:
            with open(qasm_path, 'w') as f:
                f.write(content)
            return jsonify({
                "status": "saved",
                "name": filename,
                "source": source
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/qasm/active", methods=["GET", "POST"])
def qasm_active():
    """Get or load active QASM in executor"""
    if request.method == "GET":
        # Return QASM content currently loaded in executor
        # Check circuit under lock, release lock before calling qasm()
        with state_lock:
            if not executor.circuit:
                return jsonify({"error": "No circuit loaded"}), 404
            circuit = executor.circuit

        try:
            content = circuit.qasm()
            num_qubits = circuit.num_qubits
            num_gates = circuit.size()

            return jsonify({
                "content": content,
                "num_qubits": num_qubits,
                "num_gates": num_gates
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == "POST":
        # Load QASM content into executor
        data = request.json or {}
        content = data.get("content", "").strip()

        if not content:
            return jsonify({"error": "Content is required"}), 400

        try:
            if not executor.load_qasm(content):
                return jsonify({"error": "Failed to parse QASM"}), 400

            with state_lock:
                quantum_state["circuit_info"] = {
                    "qubits": executor.circuit.num_qubits,
                    "gates": executor.circuit.size()
                }

            return jsonify({
                "status": "loaded",
                "num_qubits": executor.circuit.num_qubits,
                "num_gates": executor.circuit.size()
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400


@app.route("/api/qasm/circuit", methods=["GET"])
def get_circuit_diagram():
    """Get circuit diagram as HTML with matplotlib rendering"""
    if not executor.qiskit_available:
        return jsonify({"error": "Qiskit not available"}), 503

    with state_lock:
        if not executor.circuit:
            return jsonify({"error": "No circuit loaded"}), 404

    try:
        # Generate circuit diagram using matplotlib
        from io import BytesIO
        import base64

        fig = executor.circuit.draw(output='mpl')

        # Convert matplotlib figure to PNG base64
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()

        # Create HTML wrapper with embedded image
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ margin: 0; padding: 10px; background: #f0f0f0; font-family: Arial, sans-serif; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                #circuit-content {{ margin: 20px 0; overflow-x: auto; text-align: center; }}
                img {{ max-width: 100%; height: auto; }}
                .info {{ color: #666; font-size: 12px; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Quantum Circuit Diagram</h2>
                <div id="circuit-content">
                    <img src="data:image/png;base64,{image_base64}" alt="Quantum Circuit Diagram">
                </div>
                <div class="info">
                    <p>Circuit auto-refreshes every 5 seconds</p>
                </div>
            </div>
            <script>
                setTimeout(() => {{ location.reload(); }}, 5000);
            </script>
        </body>
        </html>
        """
        return html_content, 200, {'Content-Type': 'text/html'}

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/qasm/circuit/raw", methods=["GET"])
def get_circuit_raw():
    """Get circuit diagram as ASCII art text"""
    if not executor.qiskit_available:
        return jsonify({"error": "Qiskit not available"}), 503

    with state_lock:
        if not executor.circuit:
            return "circuit not rendered yet", 200, {'Content-Type': 'text/plain'}

    try:
        # Generate circuit diagram as ASCII/text art
        circuit_ascii = str(executor.circuit.draw(output='text'))
        return circuit_ascii, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"Error generating circuit: {str(e)}", 500, {'Content-Type': 'text/plain'}


@app.route("/api/qasm/circuit/ascii", methods=["GET"])
def get_circuit_ascii():
    """Get circuit diagram as ASCII art text drawing"""
    if not executor.qiskit_available:
        return jsonify({"error": "Qiskit not available"}), 503

    with state_lock:
        if not executor.circuit:
            return "circuit not rendered yet", 200, {'Content-Type': 'text/plain'}

    try:
        # Generate circuit diagram as ASCII/text art
        circuit_ascii = str(executor.circuit.draw(output='text'))
        return circuit_ascii, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"Error generating circuit: {str(e)}", 500, {'Content-Type': 'text/plain'}


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


# ============================================================================
# JOB QUEUE MANAGEMENT
# ============================================================================

@app.route("/api/jobs", methods=["POST"])
def submit_job():
    """Submit a job to the queue"""
    data = request.json or {}
    qasm_file = data.get("qasm_file", "expt.qasm")
    backend = data.get("backend", "local")
    shots = data.get("shots", 10)

    if not qasm_file:
        return jsonify({"error": "qasm_file is required"}), 400

    job_id = str(uuid.uuid4())

    with job_lock:
        job_store[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "parameters": {
                "qasm_file": qasm_file,
                "backend": backend,
                "shots": shots
            },
            "submitted_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None
        }

    # Enqueue the job
    job_queue.put(job_id)

    return jsonify({
        "job_id": job_id,
        "status": "queued"
    }), 202


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    """List jobs from the job store"""
    status_filter = request.args.get("status")

    with job_lock:
        jobs = list(job_store.values())

    if status_filter:
        jobs = [j for j in jobs if j["status"] == status_filter]

    return jsonify({
        "jobs": jobs,
        "total": len(jobs),
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Get a specific job's status and result"""
    with job_lock:
        job = job_store.get(job_id)

    if not job:
        return jsonify({"error": f"Job not found: {job_id}"}), 404

    return jsonify(job), 200


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Cancel a job if queued, or attempt to interrupt if running"""
    with job_lock:
        job = job_store.get(job_id)

    if not job:
        return jsonify({"error": f"Job not found: {job_id}"}), 404

    if job["status"] == "queued":
        # Mark as cancelled (will be skipped when dequeued)
        with job_lock:
            job["status"] = "cancelled"
            job["completed_at"] = datetime.now().isoformat()
        with metrics_lock:
            metrics["jobs_cancelled"] += 1
        return jsonify({"status": "cancelled", "job_id": job_id}), 200

    elif job["status"] == "running":
        # Best-effort attempt to interrupt (would need to track running thread)
        # For now, just mark as cancelled and let it complete
        with job_lock:
            job["status"] = "cancelled"
        return jsonify({"status": "cancel_requested", "job_id": job_id, "message": "Running job will be cancelled at next checkpoint"}), 200

    else:
        return jsonify({"error": f"Cannot cancel job in {job['status']} state"}), 409


@app.route("/api/loop/status", methods=["GET"])
def get_loop_status():
    """Get the current loop mode status"""
    with state_lock:
        return jsonify({
            "loop_mode": quantum_state["loop_mode"],
            "status": quantum_state["status"],
            "message": quantum_state.get("message", "")
        })


def build_quantum_args():
    """Build command-line arguments for QuantumKCDemo from saved configuration"""
    args = []

    # Load configuration
    config_path = CREDENTIALS_DIR / "config.json"
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception:
            pass

    # Backend option (default: -b:aer)
    backend = config.get("backend", "aer").lower()
    if backend == "aer":
        args.append("-b:aer")
    elif backend == "aer_noise" or backend == "aer_model":
        args.append("-b:aer_noise")
    elif backend.startswith("b:"):
        args.append(f"-{backend}")
    elif backend != "aer":
        # Custom backend name
        args.append(f"-b:{backend}")
    else:
        args.append("-b:aer")

    # Noise model (if specified separately from backend)
    if config.get("noise_model") and "noise" not in backend.lower():
        args.append("-b:aer_noise")

    # Display mode (default: -hex for 12-qubit hex display)
    display_mode = config.get("display_mode", "hex").lower()
    if display_mode == "hex":
        args.append("-hex")
    elif display_mode == "tee":
        args.append("-tee")
    elif display_mode == "d16" or display_mode == "16":
        args.append("-d16")
    elif display_mode == "bowtie" or display_mode == "5":
        pass  # bowtie is default, no flag needed

    # QASM file (if specified)
    qasm_file = config.get("qasm_file")
    if qasm_file:
        args.append(f"-f:{qasm_file}")

    # Additional boolean flags
    if config.get("no_logo"):
        args.append("-noq")
    if config.get("emulator"):
        args.append("-e")
    if config.get("dual_display"):
        args.append("-d")
    if config.get("neopixel_continuous"):
        args.append("-notile")

    return args


@app.route("/api/loop/start", methods=["POST"])
def start_loop_mode():
    """Start continuous loop mode"""
    global loop_process

    # Check loop_mode under state_lock first
    with state_lock:
        if quantum_state["loop_mode"]:
            return jsonify({"error": "Loop mode already running"}), 409
        quantum_state["status"] = "starting_loop"
        quantum_state["message"] = "Starting loop mode..."

    # Acquire loop_lock before spawning subprocess
    with loop_lock:
        try:
            # Start the quantum program with loop mode
            # Try qapp.py first (standard name in container), then QuantumKCDemo.v0_2.py (development)
            app_path = Path(__file__).parent / "qapp.py"
            if not app_path.exists():
                app_path = Path(__file__).parent / "QuantumKCDemo.v0_2.py"

            # Build arguments from saved configuration
            cmd_args = ["python3", str(app_path)]
            cmd_args.extend(build_quantum_args())

            # Set up environment to ensure SVG output goes to the Flask svg directory
            env = os.environ.copy()
            env["SVG_OUTPUT_DIR"] = str(SVG_DIR)

            loop_process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )

            # Set loop_mode = True only after Popen succeeds
            with state_lock:
                quantum_state["loop_mode"] = True
                quantum_state["status"] = "loop_running"
                quantum_state["message"] = "Loop mode active - continuously executing quantum circuits"

            return jsonify({"status": "loop_started", "message": "Quantum program running in loop mode"})

        except Exception as e:
            with state_lock:
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

    # Acquire loop_lock around process terminate/kill sequence
    with loop_lock:
        try:
            if loop_process:
                # Check if process is still running
                if loop_process.poll() is None:
                    # Process is still running, terminate it
                    loop_process.terminate()
                    try:
                        loop_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        loop_process.kill()
                        loop_process.wait()
                # If process already exited (poll() is not None), just clean up state

            # Clean up state
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


# ============================================================================
# CLUSTER COORDINATION
# ============================================================================

@app.route("/api/cluster/register", methods=["POST"])
def cluster_register():
    """Register a node in the cluster"""
    data = request.json or {}
    node_id = data.get("node_id") or str(uuid.uuid4())
    name = data.get("name", "unknown")
    host = data.get("host", "unknown")
    port = data.get("port", 5000)
    capabilities = data.get("capabilities", [])

    with cluster_lock:
        cluster_registry[node_id] = {
            "node_id": node_id,
            "name": name,
            "host": host,
            "port": port,
            "capabilities": capabilities,
            "registered_at": datetime.now().isoformat(),
            "last_seen": time.monotonic(),
            "status": "active"
        }

    return jsonify({
        "node_id": node_id,
        "status": "registered",
        "message": "Node registered successfully"
    }), 200


@app.route("/api/cluster/heartbeat", methods=["POST"])
def cluster_heartbeat():
    """Update last_seen for a node"""
    data = request.json or {}
    node_id = data.get("node_id")

    if not node_id:
        return jsonify({"error": "node_id is required"}), 400

    with cluster_lock:
        if node_id not in cluster_registry:
            return jsonify({"error": "Node not found"}), 404

        cluster_registry[node_id]["last_seen"] = time.monotonic()
        cluster_registry[node_id]["status"] = "active"

    return jsonify({
        "status": "ok",
        "node_id": node_id,
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route("/api/cluster/nodes", methods=["GET"])
def cluster_nodes():
    """List all registered nodes"""
    now = time.monotonic()

    with cluster_lock:
        nodes = []
        active = 0
        inactive = 0

        for node in cluster_registry.values():
            seconds_ago = now - node["last_seen"]
            node_copy = node.copy()
            node_copy["last_seen_seconds_ago"] = seconds_ago
            nodes.append(node_copy)

            if node["status"] == "active":
                active += 1
            else:
                inactive += 1

    return jsonify({
        "nodes": nodes,
        "total": len(nodes),
        "active": active,
        "inactive": inactive
    }), 200


@app.route("/api/cluster/nodes/<node_id>", methods=["DELETE"])
def cluster_deregister(node_id):
    """Deregister a node"""
    with cluster_lock:
        if node_id not in cluster_registry:
            return jsonify({"error": "Node not found"}), 404

        del cluster_registry[node_id]

    return jsonify({
        "status": "deregistered",
        "node_id": node_id
    }), 200


@app.route("/api/cluster/status", methods=["GET"])
def cluster_status():
    """Get cluster status summary"""
    pod_ip = os.environ.get("POD_IP", socket.gethostname())
    port = os.environ.get("PORT", 5000)

    with cluster_lock:
        total = len(cluster_registry)
        active = sum(1 for n in cluster_registry.values() if n["status"] == "active")
        inactive = total - active

    return jsonify({
        "total_nodes": total,
        "active_nodes": active,
        "inactive_nodes": inactive,
        "this_node": {
            "host": pod_ip,
            "port": port
        },
        "timestamp": datetime.now().isoformat()
    }), 200


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

@app.route("/metrics")
def metrics_endpoint():
    """Prometheus text exposition format metrics"""
    with metrics_lock:
        jobs_completed = metrics["jobs_completed"]
        jobs_failed = metrics["jobs_failed"]
        jobs_cancelled = metrics["jobs_cancelled"]
        execution_durations = metrics["execution_durations"][:]  # copy list
        http_reqs = metrics["http_requests"].copy()

    # Count running and queued jobs
    with job_lock:
        jobs_running = sum(1 for j in job_store.values() if j["status"] == "running")
        jobs_queued = sum(1 for j in job_store.values() if j["status"] == "queued")

    # Count cluster nodes
    with cluster_lock:
        active_nodes = sum(1 for n in cluster_registry.values() if n["status"] == "active")
        inactive_nodes = sum(1 for n in cluster_registry.values() if n["status"] == "inactive")

    # Loop mode status
    with state_lock:
        loop_active = 1 if quantum_state["loop_mode"] else 0

    # Compute execution duration percentiles
    exec_count = len(execution_durations)
    exec_sum = sum(execution_durations)
    if execution_durations:
        sorted_durations = sorted(execution_durations)
        p50 = sorted_durations[int(len(sorted_durations) * 0.5)]
        p90 = sorted_durations[int(len(sorted_durations) * 0.9)]
        p99 = sorted_durations[int(len(sorted_durations) * 0.99)]
    else:
        p50 = p90 = p99 = 0.0

    # Build Prometheus text format
    lines = []
    lines.append("# HELP quantum_jobs_total Total quantum jobs by status")
    lines.append("# TYPE quantum_jobs_total counter")
    lines.append(f"quantum_jobs_total{{status=\"completed\"}} {jobs_completed}")
    lines.append(f"quantum_jobs_total{{status=\"failed\"}} {jobs_failed}")
    lines.append(f"quantum_jobs_total{{status=\"cancelled\"}} {jobs_cancelled}")

    lines.append("# HELP quantum_jobs_running Currently running quantum jobs")
    lines.append("# TYPE quantum_jobs_running gauge")
    lines.append(f"quantum_jobs_running {jobs_running}")

    lines.append("# HELP quantum_jobs_queued Jobs waiting in queue")
    lines.append("# TYPE quantum_jobs_queued gauge")
    lines.append(f"quantum_jobs_queued {jobs_queued}")

    lines.append("# HELP quantum_circuit_execution_seconds Quantum circuit execution duration")
    lines.append("# TYPE quantum_circuit_execution_seconds summary")
    lines.append(f"quantum_circuit_execution_seconds{{quantile=\"0.5\"}} {p50}")
    lines.append(f"quantum_circuit_execution_seconds{{quantile=\"0.9\"}} {p90}")
    lines.append(f"quantum_circuit_execution_seconds{{quantile=\"0.99\"}} {p99}")
    lines.append(f"quantum_circuit_execution_seconds_sum {exec_sum}")
    lines.append(f"quantum_circuit_execution_seconds_count {exec_count}")

    lines.append("# HELP quantum_cluster_nodes_total Registered cluster nodes by status")
    lines.append("# TYPE quantum_cluster_nodes_total gauge")
    lines.append(f"quantum_cluster_nodes_total{{state=\"active\"}} {active_nodes}")
    lines.append(f"quantum_cluster_nodes_total{{state=\"inactive\"}} {inactive_nodes}")

    lines.append("# HELP quantum_loop_mode_active Whether loop mode is currently active")
    lines.append("# TYPE quantum_loop_mode_active gauge")
    lines.append(f"quantum_loop_mode_active {loop_active}")

    lines.append("# HELP http_requests_total Total HTTP requests by endpoint and method")
    lines.append("# TYPE http_requests_total counter")
    for (endpoint, method), count in sorted(http_reqs.items()):
        lines.append(f"http_requests_total{{endpoint=\"{endpoint}\",method=\"{method}\"}} {count}")

    response_text = "\n".join(lines) + "\n"
    return response_text, 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Server error"}), 500


# ============================================================================
# BACKGROUND THREADS
# ============================================================================

def stale_node_reaper():
    """Marks nodes inactive if last_seen > 30s ago"""
    STALE_THRESHOLD = 30
    CHECK_INTERVAL = 10

    while True:
        try:
            now = time.monotonic()
            with cluster_lock:
                for node in cluster_registry.values():
                    if now - node["last_seen"] > STALE_THRESHOLD:
                        node["status"] = "inactive"
                    else:
                        node["status"] = "active"
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Error in stale_node_reaper: {e}")
            time.sleep(CHECK_INTERVAL)


def loop_process_monitor():
    """Monitor loop process and reset state if it exits unexpectedly"""
    CHECK_INTERVAL = 2

    while True:
        try:
            with loop_lock:
                if loop_process and loop_process.poll() is not None:
                    # Process has exited
                    with state_lock:
                        if quantum_state["loop_mode"]:
                            quantum_state["loop_mode"] = False
                            quantum_state["status"] = "error"
                            quantum_state["message"] = "Loop process exited unexpectedly"
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Error in loop_process_monitor: {e}")
            time.sleep(CHECK_INTERVAL)


def job_queue_worker():
    """Dequeues and executes jobs one at a time"""
    while True:
        try:
            job_id = job_queue.get()  # blocks until a job is available

            with job_lock:
                job = job_store.get(job_id)

            # Skip if cancelled or not found
            if job is None or job["status"] == "cancelled":
                job_queue.task_done()
                continue

            # Execute the job
            _execute_queued_job(job_id)
            job_queue.task_done()

        except Exception as e:
            print(f"Error in job_queue_worker: {e}")
            job_queue.task_done()


def _execute_queued_job(job_id):
    """Execute a job from the queue"""
    global quantum_state

    t0 = time.monotonic()

    try:
        with job_lock:
            job = job_store.get(job_id)

        if not job:
            return

        # Update job status to running
        with job_lock:
            job["status"] = "running"
            job["started_at"] = datetime.now().isoformat()

        # Update global quantum state for backward compatibility
        with state_lock:
            quantum_state["running"] = True
            quantum_state["status"] = "executing"
            quantum_state["message"] = "Running..."

        parameters = job.get("parameters", {})
        qasm_file = parameters.get("qasm_file", "expt.qasm")
        backend = parameters.get("backend", "local")
        shots = parameters.get("shots", 10)

        # Track qasm_file
        with state_lock:
            quantum_state["qasm_file"] = qasm_file

        # Load QASM file
        qasm_path = Path(__file__).parent / qasm_file
        if not qasm_path.exists():
            raise FileNotFoundError(f"QASM file not found: {qasm_file}")

        with open(qasm_path, 'r') as f:
            qasm_content = f.read()

        # Load circuit
        if not executor.load_qasm(qasm_content):
            raise RuntimeError("Failed to parse QASM")

        # Execute circuit
        result = executor.execute(backend, shots)

        if result:
            # Success
            with job_lock:
                job["status"] = "completed"
                job["completed_at"] = datetime.now().isoformat()
                job["result"] = result

            with state_lock:
                quantum_state["last_result"] = result
                quantum_state["last_result_time"] = datetime.now().isoformat()
                quantum_state["status"] = "success"
                quantum_state["message"] = "Circuit executed successfully"
                quantum_state["backend_info"] = {"name": backend, "shots": shots}

            # Record metrics
            duration = time.monotonic() - t0
            with metrics_lock:
                metrics["execution_durations"].append(duration)
                if len(metrics["execution_durations"]) > 1000:
                    metrics["execution_durations"].pop(0)
                metrics["jobs_completed"] += 1

            # Generate SVG
            generate_result_svg(result)

        else:
            raise RuntimeError("Execution returned no result")

    except Exception as e:
        print(f"Error executing job {job_id}: {e}")
        with job_lock:
            job["status"] = "failed"
            job["completed_at"] = datetime.now().isoformat()
            job["error"] = str(e)

        with state_lock:
            quantum_state["status"] = "error"
            quantum_state["message"] = str(e)

        with metrics_lock:
            metrics["jobs_failed"] += 1

    finally:
        with state_lock:
            quantum_state["running"] = False


def main():
    """Start the web dashboard"""
    print("Initializing Quantum Executor...")
    if not executor.initialize():
        print("Warning: Qiskit not available, dashboard will be in demo mode")

    # Start background threads
    print("Starting background threads...")
    reaper_thread = threading.Thread(target=stale_node_reaper, daemon=True)
    reaper_thread.start()
    print("  - Stale node reaper started")

    worker_thread = threading.Thread(target=job_queue_worker, daemon=True)
    worker_thread.start()
    print("  - Job queue worker started")

    monitor_thread = threading.Thread(target=loop_process_monitor, daemon=True)
    monitor_thread.start()
    print("  - Loop process monitor started")

    print("Starting web dashboard on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
