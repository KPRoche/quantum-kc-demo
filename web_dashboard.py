"""
Web Dashboard for Quantum KC Demo
Provides a browser-based interface for running quantum circuits and viewing results
"""

import os
import sys
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


def get_version_info():
    """Get version information from git or environment"""
    version = os.environ.get("APP_VERSION", "unknown")
    commit = "unknown"

    # Try to get git commit hash
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(__file__),
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return {
        "version": version,
        "commit": commit,
        "timestamp": datetime.now().isoformat()
    }


@app.before_request
def track_http_request():
    """Track HTTP requests for Prometheus metrics (exclude probes)"""
    # Exclude health/metrics endpoints from tracking
    if request.path not in ["/health", "/ready", "/metrics"]:
        with metrics_lock:
            key = (request.path, request.method)
            metrics["http_requests"][key] = metrics["http_requests"].get(key, 0) + 1

# Configuration
FILES_DIR = Path(__file__).parent / "files"
FILES_DIR.mkdir(exist_ok=True)
SVG_DIR = FILES_DIR / "svg"
SVG_DIR.mkdir(exist_ok=True)
QASM_DIR = FILES_DIR / "qasm"
QASM_DIR.mkdir(exist_ok=True)
CONTROL_DIR = FILES_DIR / "control"
CONTROL_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR = Path(__file__).parent / "credentials"
CREDENTIALS_DIR.mkdir(exist_ok=True)

# Preset QASM files in project root
PRESET_QASM_FILES = ["expt.qasm", "expt12.qasm", "expt16.qasm", "expt32.qasm"]

# Loop mode result file (IPC from subprocess)
LOOP_RESULT_FILE = FILES_DIR / "control" / "result.json"

# Backend status file (IPC from subprocess during initialization)
BACKEND_STATUS_FILE = FILES_DIR / "control" / "backend_status.json"

# Global state
quantum_state = {
    "running": False,
    "last_result": None,
    "last_result_time": None,
    "status": "ready",
    "message": "",
    "circuit_info": None,
    "backend_info": {"name": "aer", "shots": 10, "type": "simulator"},
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

# Keep only the 100 most recent jobs in memory to prevent memory growth
MAX_JOBS_IN_MEMORY = 100

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


def _cleanup_old_jobs():
	"""Remove oldest jobs if store exceeds MAX_JOBS_IN_MEMORY."""
	with job_lock:
		if len(job_store) > MAX_JOBS_IN_MEMORY:
			completed_jobs = sorted(
				(job_id for job_id, job in job_store.items() if job.get("status") == "completed"),
				key=lambda jid: job_store[jid].get("completed_at", ""),
			)
			for job_id in completed_jobs[:len(job_store) - MAX_JOBS_IN_MEMORY]:
				del job_store[job_id]


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
            # Backend selection: "aer" and "local" both use qasm_simulator
            if backend_name in ("local", "aer"):
                backend = self.Aer.get_backend('qasm_simulator')
            else:
                # For other backends, try fake backend (limited to 5 qubits)
                if self.circuit.num_qubits > 5:
                    raise RuntimeError(f"Circuit has {self.circuit.num_qubits} qubits but fake backend only supports 5 qubits. Use 'aer' or 'local' backend instead.")
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
            import traceback
            print(f"Execution error: {e}")
            print(traceback.format_exc())
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

@app.route("/api/qubits/simple")
def get_qubits_simple():
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

    return jsonify({
        "pattern": pattern,
        "num_qubits": num_qubits,
        "timestamp": quantum_state.get("last_result_time"),
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
            {"path": "/api/version", "method": "GET", "description": "Get version and commit information"},
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
            {"path": "/api/qubits", "method": "GET", "description": "Get the latest qubit measurement as string and structured data"},
            {"path": "/api/qubits/simple", "method": "GET", "description": "Get the latest qubit measurement (lightweight: pattern, num_qubits, timestamp, shots)"}
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


@app.route("/api/version")
def get_version():
    """Get version information"""
    return jsonify(get_version_info()), 200


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
        # Add version information
        status_response["version_info"] = get_version_info()
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
        backend_lower = backend.lower()
        if backend_lower in ("aer_noise", "aer_model", "model"):
            parameters.append("-b:aer_noise")
        elif backend_lower == "aer":
            parameters.append("-b:aer")
        elif "least" in backend_lower:
            parameters.append("-b:least")
        elif "aer" in backend_lower:
            parameters.append("-b:aer")
        else:
            parameters.append(f"-b:{backend}")

    # Add file parameter if specified
    if qasm_file and qasm_file != "expt.qasm":
        parameters.append(f"-f:{qasm_file}")

    # Add shots parameter if specified
    if shots is not None:
        parameters.append(f"-shots:{shots}")

    job_id = str(uuid.uuid4())
    description = f"Execute {qasm_file} on {backend} backend"

    # If control system is enabled, send command to quantum process
    if CONTROL_ENABLED:
        # Write config.json with qasm_file, shots, backend, and loop_mode so subprocess can read it
        config_path = FILES_DIR / "control" / "config.json"
        try:
            with open(config_path, 'w') as f:
                json.dump({"qasm_file": qasm_file, "shots": shots, "backend": backend, "loop_mode": False}, f)
        except Exception as e:
            print(f"Warning: Could not write config.json: {e}")

        success = request_run(parameters, description)
        if success:
            with state_lock:
                quantum_state["qasm_file"] = qasm_file
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


# Alias for console compatibility
@app.route("/api/quantum/execute", methods=["POST"])
def execute_quantum():
    """Alias for /api/execute for console API compatibility"""
    return execute_circuit()


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
    return jsonify({"warning": "No result available"}), 200


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

            filename = data.get("name", "").strip() or quantum_state.get("qasm_file", "expt.qasm")
            with state_lock:
                quantum_state["circuit_info"] = {
                    "filename": filename,
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

    # Ensure circuit is loaded from current QASM file (single and loop modes)
    _ensure_circuit_loaded()

    with state_lock:
        if not executor.circuit:
            # Return warning (not error) - normal until execution happens
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { margin: 0; padding: 10px; background: #f0f0f0; font-family: Arial, sans-serif; }
                    .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    #circuit-content { margin: 20px 0; padding: 20px; text-align: center; background: #fff8e1; border-left: 4px solid #ffc107; }
                    .warning { color: #856404; font-size: 14px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Quantum Circuit Diagram</h2>
                    <div id="circuit-content">
                        <div class="warning">⚠ No circuit loaded yet. Run an execution or load a QASM file to display circuit.</div>
                    </div>
                </div>
                <script>
                    setTimeout(() => { location.reload(); }, 5000);
                </script>
            </body>
            </html>
            """
            return html_content, 200, {'Content-Type': 'text/html'}

    try:
        # Generate circuit diagram using matplotlib
        from io import BytesIO
        import base64

        num_qubits = executor.circuit.num_qubits
        # Scale width based on qubit count (0.3 inches per qubit, minimum 12)
        width = max(12, num_qubits * 0.3)
        height = max(8, num_qubits * 0.15 + 3)

        # fold=-1 disables wrapping, draw entire circuit horizontally
        fig = executor.circuit.draw(output='mpl', scale=0.7, fold=-1)
        fig.set_size_inches(width, height)

        # Convert matplotlib figure to PNG base64
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
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

    # Ensure circuit is loaded from current QASM file (single and loop modes)
    _ensure_circuit_loaded()

    with state_lock:
        if not executor.circuit:
            return "⚠ No circuit loaded yet. Run an execution or load a QASM file to display circuit.", 200, {'Content-Type': 'text/plain'}

    try:
        # Generate circuit diagram as ASCII/text art
        circuit_ascii = str(executor.circuit.draw(output='text'))
        return circuit_ascii, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"Error generating circuit: {str(e)}", 500, {'Content-Type': 'text/plain'}


@app.route("/api/qasm/circuit/png", methods=["GET"])
def get_circuit_png():
    """Get circuit diagram as PNG binary image"""
    if not executor.qiskit_available:
        return jsonify({"error": "Qiskit not available"}), 503

    # Ensure circuit is loaded from current QASM file (single and loop modes)
    _ensure_circuit_loaded()

    with state_lock:
        if not executor.circuit:
            return jsonify({"error": "No circuit loaded yet"}), 400

    try:
        from io import BytesIO
        import sys
        import traceback
        num_qubits = executor.circuit.num_qubits
        # Scale width based on qubit count (0.3 inches per qubit, minimum 12)
        width = max(12, num_qubits * 0.3)
        height = max(8, num_qubits * 0.15 + 3)

        # In Qiskit 2.4.1, circuit rendering with matplotlib can hit recursion limits
        # Use a reasonable fold value and reduce DPI to minimize layout complexity
        try:
            fig = executor.circuit.draw(output='mpl', scale=0.5, fold=100)
        except RecursionError:
            # If drawing still fails, try with even more conservative settings
            fig = executor.circuit.draw(output='mpl', scale=0.3, fold=4)

        fig.set_size_inches(width, height)
        buffer = BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', dpi=80)
        buffer.seek(0)
        return send_file(buffer, mimetype='image/png', as_attachment=False)
    except RecursionError:
        return jsonify({"error": "Circuit too complex for PNG rendering. Use ASCII format instead."}), 400
    except Exception as e:
        import traceback as tb
        tb.print_exc(file=sys.stderr, limit=5)
        return jsonify({"error": str(e)[:200]}), 500


@app.route("/api/qasm/circuit/ascii", methods=["GET"])
def get_circuit_ascii():
    """Get circuit diagram as ASCII art text drawing"""
    if not executor.qiskit_available:
        return jsonify({"error": "Qiskit not available"}), 503

    # Ensure circuit is loaded from current QASM file (single and loop modes)
    _ensure_circuit_loaded()

    with state_lock:
        if not executor.circuit:
            return "⚠ No circuit loaded yet. Run an execution or load a QASM file to display circuit.", 200, {'Content-Type': 'text/plain'}

    try:
        # Generate circuit diagram as ASCII/text art
        circuit_ascii = str(executor.circuit.draw(output='text'))
        return circuit_ascii, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"Error generating circuit: {str(e)}", 500, {'Content-Type': 'text/plain'}


@app.route("/api/config", methods=["GET", "POST"])
def config():
    """Get or set configuration"""
    try:
        if request.method == "POST":
            data = request.json or {}
            # Store configuration in writable files dir
            config_path = FILES_DIR / "control" / "config.json"
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=2)
            return jsonify({"status": "saved"})
        else:
            config_path = FILES_DIR / "control" / "config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return jsonify(json.load(f))
            return jsonify({})
    except Exception as e:
        import traceback
        print(f"Config error: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e)}), 500


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
        _cleanup_old_jobs()
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


def _ensure_circuit_loaded():
    """Helper: Ensure circuit is loaded from current QASM file (works in both modes)"""
    try:
        # Determine current QASM file: check config first, fallback to state
        qasm_file = None

        # Try to read from config (updated by control system or execute endpoint)
        config_path = FILES_DIR / "control" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    qasm_file = config.get("qasm_file")
            except Exception:
                pass

        # Fallback to state
        if not qasm_file:
            with state_lock:
                qasm_file = quantum_state.get("qasm_file", "expt.qasm")

        # Find and read the QASM file - check files/qasm/ first, then project root
        qasm_path = QASM_DIR / qasm_file
        if not qasm_path.exists() and qasm_file in PRESET_QASM_FILES:
            qasm_path = Path(__file__).parent / qasm_file

        if not qasm_path.exists():
            return False  # File not found

        # Read and load the circuit
        with open(qasm_path, 'r') as f:
            qasm_content = f.read()

        # Load into executor (this updates executor.circuit)
        executor.load_qasm(qasm_content)

        with state_lock:
            quantum_state["qasm_file"] = qasm_file
            if executor.circuit:
                quantum_state["circuit_info"] = {
                    "filename": qasm_file,
                    "qubits": executor.circuit.num_qubits,
                    "gates": executor.circuit.size()
                }

        return True

    except Exception as e:
        return False


def build_quantum_args():
    """Build command-line arguments for QuantumKCDemo from saved configuration"""
    args = []

    # Load configuration
    config_path = FILES_DIR / "control" / "config.json"
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

    # Shots parameter (if specified)
    shots = config.get("shots")
    if shots is not None:
        try:
            shots_val = int(shots)
            if 0 < shots_val < 1025:
                args.append(f"-shots:{shots_val}")
        except (ValueError, TypeError):
            pass

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
    """Start continuous loop mode via control system"""

    # Log entry
    try:
        with open(FILES_DIR / "debug.log", "a") as f:
            f.write(f"[{datetime.now().isoformat()}] start_loop_mode() called\n")
    except:
        pass

    # Check loop_mode under state_lock first
    with state_lock:
        if quantum_state["loop_mode"]:
            try:
                with open(FILES_DIR / "debug.log", "a") as f:
                    f.write(f"  - Loop already running, returning 409\n")
            except:
                pass
            return jsonify({"error": "Loop mode already running"}), 409
        quantum_state["status"] = "starting_loop"
        quantum_state["message"] = "Starting loop mode..."

    try:
        # Ensure /app/files/control directory exists for IPC
        control_dir = FILES_DIR / "control"
        control_dir.mkdir(exist_ok=True, mode=0o777)

        # Write loop configuration to config.json so the running quantum app can read it
        config_path = control_dir / "config.json"
        config = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
            except:
                pass

        # Get loop iterations from request or default to infinite (0 means keep looping)
        request_data = request.get_json(force=True, silent=True) or {}
        loop_iterations = request_data.get("loop_iterations", 0)
        if loop_iterations <= 0:
            loop_iterations = 999999  # Effectively infinite

        # Update config with loop parameters
        config["loop_mode"] = True
        config["loop_iterations"] = loop_iterations

        with open(config_path, 'w') as f:
            json.dump(config, f)

        debug_log = FILES_DIR / "debug.log"
        with open(debug_log, "a") as f:
            f.write(f"Wrote loop config: loop_mode=True, loop_iterations={loop_iterations}\n")

        # If control system is enabled, send a run command to start the loop
        if CONTROL_ENABLED:
            try:
                from quantum_control import request_run, get_status

                # Build parameters from saved configuration
                custom_args = build_quantum_args()
                description = f"Start loop mode: {loop_iterations} iterations"

                request_run(custom_args, description)

                with open(debug_log, "a") as f:
                    f.write(f"Sent loop mode command to control system\n")
            except Exception as e:
                with open(debug_log, "a") as f:
                    f.write(f"Error sending control command: {e}\n")
                raise

        # Set loop_mode = True in our state
        with state_lock:
            quantum_state["loop_mode"] = True
            quantum_state["status"] = "loop_running"
            quantum_state["message"] = "Loop mode active - continuously executing quantum circuits"

        return jsonify({"status": "loop_started", "message": "Quantum program running in loop mode"})

    except Exception as e:
        import traceback
        import sys
        error_msg = f"Failed to start loop mode: {str(e)}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr, flush=True)
        try:
            with open(FILES_DIR / "debug.log", "a") as f:
                f.write(f"EXCEPTION: {error_msg}\n")
        except:
            pass
        with state_lock:
            quantum_state["status"] = "error"
            quantum_state["message"] = error_msg
        return jsonify({"error": str(e)}), 500


@app.route("/api/loop/stop", methods=["POST"])
def stop_loop_mode():
    """Stop continuous loop mode"""

    with state_lock:
        if not quantum_state["loop_mode"]:
            return jsonify({"error": "Loop mode not running"}), 409

    try:
        # Write loop_mode: false to config so the running quantum app stops after current iteration
        config_path = FILES_DIR / "control" / "config.json"
        config = {}
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
            except:
                pass

        config["loop_mode"] = False
        config["loop_iterations"] = 1

        with open(config_path, 'w') as f:
            json.dump(config, f)

        # Clean up state
        with state_lock:
            quantum_state["loop_mode"] = False
            quantum_state["status"] = "stopped"
            quantum_state["message"] = "Loop mode stopped"

        return jsonify({"status": "loop_stopped", "message": "Loop mode stopped - quantum app will finish current iteration"})

    except Exception as e:
        with state_lock:
            quantum_state["status"] = "error"
            quantum_state["message"] = f"Error stopping loop: {str(e)}"
        return jsonify({"error": str(e)}), 500


def generate_result_svg(result):
    """Generate SVG visualization of results"""
    if not result or "counts" not in result:
        return

    try:
        counts = result["counts"]
        num_qubits = result.get("num_qubits", 5)

        # Find the most common result
        most_common = max(counts, key=counts.get)

        # Calculate SVG dimensions based on number of qubits
        square_size = 25
        padding = 10
        squares_per_row = min(20, num_qubits)  # Max 20 squares per row
        num_rows = (num_qubits + squares_per_row - 1) // squares_per_row
        svg_width = squares_per_row * (square_size + 5) + 40
        svg_height = num_rows * (square_size + 5) + 40

        # Create simple HTML with SVG visualization
        svg_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="2">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            svg {{ border: 1px solid #ccc; margin: 20px 0; background: white; }}
            .stats {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
            .info {{ color: #666; font-size: 12px; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Quantum Circuit Results ({num_qubits} qubits)</h2>
            <svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}">
                <!-- Display qubit results as colored squares -->
    """

        # Generate colored squares for each qubit
        x = padding
        y = padding
        qubit_idx = 0
        for i, bit in enumerate(reversed(most_common)):
            color = "#FF6B6B" if bit == "0" else "#4ECDC4"
            svg_content += f'            <rect x="{x}" y="{y}" width="{square_size}" height="{square_size}" fill="{color}" stroke="black" stroke-width="1"/>\n'
            svg_content += f'            <text x="{x + square_size//2}" y="{y + square_size//2 + 4}" font-size="11" text-anchor="middle" fill="white" font-weight="bold">{qubit_idx}</text>\n'
            x += square_size + 5
            qubit_idx += 1
            if qubit_idx % squares_per_row == 0:
                x = padding
                y += square_size + 5

        svg_content += """
            </svg>
            <div class="stats">
                <h3>Most Common Result: """ + most_common + """</h3>
                <p>Probability: """ + f"{counts[most_common] / sum(counts.values()) * 100:.1f}%" + """</p>
                <div class="info">
    """

        # Show all results distribution
        for result_str, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            prob = count / sum(counts.values()) * 100
            svg_content += f"                <div>{result_str}: {count} shots ({prob:.1f}%)</div>\n"

        svg_content += """
                </div>
                <div class="info">
                    Timestamp: """ + result.get("timestamp", "") + """<br>
                    Backend: """ + result.get("backend", "") + """<br>
                    Total Shots: """ + str(result.get("shots", 10)) + """<br>
                    Qubits: """ + str(num_qubits) + """
                </div>
            </div>
        </div>
    </body>
    </html>
    """

        # Write to file
        output_path = SVG_DIR / "pixels.html"
        with open(output_path, 'w') as f:
            bytes_written = f.write(svg_content)
            f.flush()
        print(f"SVG written: {output_path}, bytes: {bytes_written}")
    except Exception as e:
        import traceback
        error_msg = f"Error generating SVG: {e}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        # Also try to write error to a log file
        try:
            with open(SVG_DIR / "error.log", 'a') as f:
                f.write(error_msg + "\n")
        except:
            pass


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

    # Count running, building, and queued jobs
    with job_lock:
        jobs_running = sum(1 for j in job_store.values() if j["status"] == "running")
        jobs_building = sum(1 for j in job_store.values() if j["status"] == "building")
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

    lines.append("# HELP quantum_jobs_building Jobs initializing backend")
    lines.append("# TYPE quantum_jobs_building gauge")
    lines.append(f"quantum_jobs_building {jobs_building}")

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
    """Monitor loop process and reset state if it exits unexpectedly. Also poll for result updates."""
    CHECK_INTERVAL = 2
    last_result_sequence = -1

    while True:
        try:
            with loop_lock:
                if loop_process and loop_process.poll() is not None:
                    # Process has exited
                    exit_code = loop_process.returncode
                    import sys
                    print(f"Loop process exited with code: {exit_code}", file=sys.stderr, flush=True)

                    with state_lock:
                        if quantum_state["loop_mode"]:
                            quantum_state["loop_mode"] = False
                            quantum_state["status"] = "error"
                            quantum_state["message"] = f"Loop process exited with code {exit_code}"

            # Poll result file for new data from loop subprocess
            if LOOP_RESULT_FILE.exists():
                try:
                    with open(LOOP_RESULT_FILE) as f:
                        result_data = json.load(f)

                    # Check if this is a new execution (sequence number changed)
                    current_sequence = result_data.get("execution_sequence", -1)

                    if current_sequence > last_result_sequence:
                        with state_lock:
                            quantum_state["last_result"] = result_data
                            quantum_state["last_result_time"] = result_data.get("timestamp")
                            # Update backend_info with shots and type from loop result
                            if "shots" in result_data:
                                quantum_state["backend_info"] = {
                                    "name": result_data.get("backend", "aer"),
                                    "shots": result_data["shots"],
                                    "type": result_data.get("backend_type", "simulator")
                                }

                        last_result_sequence = current_sequence
                        print(f"[LOOP] Result updated: execution #{current_sequence}")
                except json.JSONDecodeError:
                    print(f"[LOOP] Error decoding result file (partial write?)", file=sys.stderr)
                except Exception as e:
                    print(f"[LOOP] Error reading result file: {e}", file=sys.stderr)

            # Check backend status file for job initialization state
            if BACKEND_STATUS_FILE.exists():
                try:
                    with open(BACKEND_STATUS_FILE) as f:
                        status_data = json.load(f)
                    backend_status = status_data.get("status")

                    # Update any job that is in "submitted_to_quantum" state to "building"
                    with job_lock:
                        for job in job_store.values():
                            if job["status"] == "submitted_to_quantum" and backend_status == "building":
                                job["status"] = "building"
                                print(f"[BACKEND] Job status updated to building")
                except Exception as e:
                    print(f"[BACKEND] Error reading backend status file: {e}", file=sys.stderr)

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

        # Load QASM file - check files/qasm/ first, then project root
        qasm_path = QASM_DIR / qasm_file
        if not qasm_path.exists() and qasm_file in PRESET_QASM_FILES:
            qasm_path = Path(__file__).parent / qasm_file
        if not qasm_path.exists():
            raise FileNotFoundError(f"QASM file not found: {qasm_file}")

        with open(qasm_path, 'r') as f:
            qasm_content = f.read()

        # Load circuit
        if not executor.load_qasm(qasm_content):
            raise RuntimeError("Failed to parse QASM")

        with state_lock:
            if executor.circuit:
                quantum_state["circuit_info"] = {
                    "filename": qasm_file,
                    "qubits": executor.circuit.num_qubits,
                    "gates": executor.circuit.size()
                }

        # Execute circuit
        result = executor.execute(backend, shots)
        num_qubits = executor.QuantumCircuit.num_qubits

        if result:
            # Success
            with job_lock:
                job["status"] = "completed"
                job["completed_at"] = datetime.now().isoformat()
                job["result"] = result
            _cleanup_old_jobs()

            with state_lock:
                quantum_state["last_result"] = result
                quantum_state["last_result_time"] = datetime.now().isoformat()
                quantum_state["status"] = "success"
                quantum_state["message"] = "Circuit executed successfully"
                # Determine backend type
                backend_type = "simulator"
                if "least" in backend:
                    backend_type = "real"
                elif "aer_noise" in backend:
                    backend_type = "noise_model"
                elif backend not in ("aer", "sim"):
                    backend_type = "real"
                quantum_state["backend_info"] = {"name": backend, "shots": shots, "type": backend_type}

            # Record metrics
            duration = time.monotonic() - t0
            with metrics_lock:
                metrics["execution_durations"].append(duration)
                if len(metrics["execution_durations"]) > 1000:
                    metrics["execution_durations"].pop(0)
                metrics["jobs_completed"] += 1

            # Generate SVG
            print(f"DEBUG: About to call generate_result_svg with {num_qubits} qubits")
            sys.stdout.flush()
            generate_result_svg(result)
            print(f"DEBUG: generate_result_svg completed")
            sys.stdout.flush()

        else:
            raise RuntimeError("Execution returned no result")

    except Exception as e:
        import traceback
        error_msg = str(e)
        tb_msg = traceback.format_exc()
        print(f"Error executing job {job_id}: {error_msg}")
        print(tb_msg)
        with job_lock:
            job["status"] = "failed"
            job["completed_at"] = datetime.now().isoformat()
            job["error"] = error_msg
        _cleanup_old_jobs()

        with state_lock:
            quantum_state["status"] = "error"
            quantum_state["message"] = error_msg

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
