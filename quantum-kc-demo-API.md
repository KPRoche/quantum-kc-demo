# Quantum KC Demo API Reference

## Base URL
```
http://localhost:5000
```

---

## Health & Readiness Probes (Kubernetes)

### GET /health
Liveness probe to verify app is alive and not deadlocked.

**Response (200 OK):**
```json
{
  "status": "ok",
  "uptime_seconds": 123.45,
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "error",
  "reason": "lock_timeout",
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

---

### GET /ready
Readiness probe. Returns 200 only if Qiskit is initialized and ready.

**Response (200 OK):**
```json
{
  "status": "ready",
  "qiskit_available": true,
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "not_ready",
  "reason": "qiskit_not_initialized",
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

---

## Dashboard & Visualization

### GET /
Serves the main dashboard HTML page.

**Response (200 OK):** Returns `dashboard.html`

---

### GET /api/qubits
Get the latest qubit measurement as a string and structured data.

**Response (200 OK):**
```json
{
  "pattern": "01101",
  "qubits": [
    {"index": 0, "value": 1},
    {"index": 1, "value": 0},
    {"index": 2, "value": 1},
    {"index": 3, "value": 1},
    {"index": 4, "value": 0}
  ],
  "num_qubits": 5,
  "timestamp": "2026-03-18T10:30:00.000000",
  "backend": "aer_simulator",
  "shots": 10
}
```

**Response (404 Not Found):**
```json
{
  "error": "No measurement available yet"
}
```

---

### GET /api/svg
Get current SVG result visualization with auto-refresh wrapper (HTML page).

**Response (200 OK):** Returns HTML page with embedded SVG and auto-refresh every 1 second

**Response (404 Not Found):**
```json
{
  "error": "No result available"
}
```

---

### GET /api/svg/raw
Get raw SVG content without HTML wrapper.

**Response (200 OK):** Returns raw SVG HTML

**Response (404 Not Found):**
```
<p>No visualization available yet. Start the quantum program first.</p>
```

---

## API Discovery

### GET /api/endpoints
Get a comprehensive map of all available API endpoints organized by category.

**Response (200 OK):**
```json
{
  "base_url": "http://localhost:5000",
  "endpoints": {
    "core": [
      {"path": "/", "method": "GET", "description": "Serve main dashboard page"},
      {"path": "/api/status", "method": "GET", "description": "Get current quantum state"},
      {"path": "/api/result", "method": "GET", "description": "Get last execution result"},
      {"path": "/api/endpoints", "method": "GET", "description": "Get all available endpoints (this endpoint)"}
    ],
    "execution": [...],
    "qasm_management": [...],
    "qubit_measurement": [...],
    "configuration": [...],
    "loop_mode": [...],
    "cluster_coordination": [...],
    "health_and_monitoring": [...]
  },
  "timestamp": "2026-03-18T10:30:00.000000",
  "total_endpoints": 34
}
```

**Usage:**
```bash
curl http://localhost:5000/api/endpoints
```

---

## Circuit Execution

### GET /api/status
Get current quantum state.

**Response (200 OK):**
```json
{
  "running": false,
  "last_result": null,
  "last_result_time": null,
  "status": "ready",
  "message": "",
  "circuit_info": null,
  "backend_info": null,
  "loop_mode": false,
  "qasm_file": "expt.qasm"
}
```

---

### POST /api/execute
Execute a quantum circuit (queues it for execution).

**Request Body:**
```json
{
  "qasm_file": "expt.qasm",
  "backend": "local",
  "shots": 10
}
```

**Parameters:**
- `qasm_file` (string, default: "expt.qasm") — QASM file to execute
- `backend` (string, default: "local") — Backend to use ("local" or hardware name)
- `shots` (integer, default: 10) — Number of times to execute circuit

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Note:** The endpoint returns immediately with a `job_id`. Poll `/api/jobs/<job_id>` to check execution status.

---

### GET /api/result
Get the last execution result.

**Response (200 OK):**
```json
{
  "counts": {
    "00000": 3,
    "11111": 7
  },
  "backend": "aer_simulator",
  "timestamp": "2026-03-18T10:30:00.000000",
  "shots": 10,
  "num_qubits": 5
}
```

**Response (404 Not Found):**
```json
{
  "error": "No result available"
}
```

---

## Job Queue Management

### POST /api/jobs
Submit a job to the execution queue.

**Request Body:**
```json
{
  "qasm_file": "expt.qasm",
  "backend": "local",
  "shots": 10
}
```

**Parameters:**
- `qasm_file` (string, required) — QASM file to execute
- `backend` (string, default: "local") — Backend to use
- `shots` (integer, default: 10) — Number of shots

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "qasm_file is required"
}
```

---

### GET /api/jobs
List all jobs with optional status filtering.

**Query Parameters:**
- `status` (optional) — Filter by status: "queued", "running", "completed", "failed", "cancelled"

**Examples:**
```
GET /api/jobs
GET /api/jobs?status=queued
GET /api/jobs?status=completed
```

**Response (200 OK):**
```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "completed",
      "parameters": {
        "qasm_file": "expt.qasm",
        "backend": "local",
        "shots": 10
      },
      "submitted_at": "2026-03-18T10:30:00.000000",
      "started_at": "2026-03-18T10:30:02.000000",
      "completed_at": "2026-03-18T10:30:15.000000",
      "result": {
        "counts": {"00000": 3, "11111": 7},
        "backend": "aer_simulator",
        "timestamp": "2026-03-18T10:30:15.000000",
        "shots": 10,
        "num_qubits": 5
      },
      "error": null
    }
  ],
  "total": 1,
  "timestamp": "2026-03-18T10:30:20.000000"
}
```

---

### GET /api/jobs/<job_id>
Get a specific job's status and result.

**Path Parameters:**
- `job_id` (string, required) — Job identifier (UUID)

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "parameters": {
    "qasm_file": "expt.qasm",
    "backend": "local",
    "shots": 10
  },
  "submitted_at": "2026-03-18T10:30:00.000000",
  "started_at": "2026-03-18T10:30:02.000000",
  "completed_at": "2026-03-18T10:30:15.000000",
  "result": {
    "counts": {"00000": 3, "11111": 7},
    "backend": "aer_simulator",
    "timestamp": "2026-03-18T10:30:15.000000",
    "shots": 10,
    "num_qubits": 5
  },
  "error": null
}
```

**Response (404 Not Found):**
```json
{
  "error": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /api/jobs/<job_id>/cancel
Cancel a queued job or interrupt a running job (best-effort).

**Path Parameters:**
- `job_id` (string, required) — Job identifier (UUID)

**Response (200 OK, if queued):**
```json
{
  "status": "cancelled",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (200 OK, if running):**
```json
{
  "status": "cancel_requested",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Running job will be cancelled at next checkpoint"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (409 Conflict, if already completed):**
```json
{
  "error": "Cannot cancel job in completed state"
}
```

---

## QASM Management

### GET /api/qasm/file
Get QASM file content.

**Query Parameters:**
- `name` (optional) — Filename to retrieve. If omitted, returns currently active QASM file.

**Examples:**
```
GET /api/qasm/file
GET /api/qasm/file?name=expt.qasm
GET /api/qasm/file?name=expt12.qasm
GET /api/qasm/file?name=myfile.qasm
```

**Response (200 OK):**
```json
{
  "name": "expt.qasm",
  "content": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\n...",
  "source": "preset"
}
```

**Response (404 Not Found):**
```json
{
  "error": "QASM file not found: filename.qasm"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

### POST /api/qasm/file
Save QASM file content.

**Request Body:**
```json
{
  "name": "myfile.qasm",
  "content": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[5];\nmeasure q -> c[5];"
}
```

**Parameters:**
- `name` (string, required) — Filename to save
  - Preset names (`expt.qasm`, `expt12.qasm`, `expt16.qasm`) → saved to project root
  - Other names → saved to `qasm/` subfolder
- `content` (string, required) — QASM circuit code

**Response (200 OK):**
```json
{
  "status": "saved",
  "name": "myfile.qasm",
  "source": "user"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Both 'name' and 'content' are required"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

### GET /api/qasm/active
Get QASM content currently loaded in executor.

**Response (200 OK):**
```json
{
  "content": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\n...",
  "num_qubits": 5,
  "num_gates": 8
}
```

**Response (404 Not Found):**
```json
{
  "error": "No circuit loaded"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

### POST /api/qasm/active
Load QASM content into executor (in-memory, not written to disk).

**Request Body:**
```json
{
  "content": "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[5];\nmeasure q -> c[5];"
}
```

**Parameters:**
- `content` (string, required) — QASM circuit code

**Response (200 OK):**
```json
{
  "status": "loaded",
  "num_qubits": 5,
  "num_gates": 8
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Content is required"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Failed to parse QASM"
}
```

---

### GET /api/qasm/circuit
Get circuit diagram as HTML page with embedded SVG (auto-refreshes every 5 seconds).

**Response (200 OK):** Returns HTML page with circuit diagram SVG

**Response (404 Not Found):**
```json
{
  "error": "No circuit loaded"
}
```

**Response (503 Service Unavailable):**
```json
{
  "error": "Qiskit not available"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

### GET /api/qasm/circuit/raw
Get circuit diagram as raw SVG image.

**Response (200 OK):** Returns raw SVG with `Content-Type: image/svg+xml`

**Response (404 Not Found):**
```json
{
  "error": "No circuit loaded"
}
```

**Response (503 Service Unavailable):**
```json
{
  "error": "Qiskit not available"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

## Configuration & Authentication

### GET /api/config
Get configuration settings.

**Response (200 OK):**
```json
{
  "setting_key": "setting_value"
}
```

**Response (200 OK, empty):**
```json
{}
```

---

### POST /api/config
Save configuration settings.

**Request Body:**
```json
{
  "setting_key": "setting_value"
}
```

**Response (200 OK):**
```json
{
  "status": "saved"
}
```

---

### POST /api/auth/save
Save IBM Quantum authentication credentials.

**Request Body:**
```json
{
  "api_key": "your-api-key",
  "crn": "your-crn-string"
}
```

**Parameters:**
- `api_key` (string, required) — IBM Quantum API key
- `crn` (string, required) — Cloud Resource Name

**Response (200 OK):**
```json
{
  "status": "saved",
  "message": "IBM Quantum credentials saved successfully",
  "authenticated": true
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Both API Key and CRN are required"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message",
  "message": "Failed to save credentials"
}
```

---

### GET /api/auth/status
Check IBM Quantum authentication status.

**Response (200 OK, authenticated):**
```json
{
  "authenticated": true,
  "message": "IBM Quantum credentials are configured",
  "crn": "Configured"
}
```

**Response (200 OK, not authenticated):**
```json
{
  "authenticated": false,
  "message": "No IBM Quantum credentials found. Please configure authentication."
}
```

**Response (500 Server Error):**
```json
{
  "authenticated": false,
  "message": "Error checking authentication: error message"
}
```

---

## Loop Mode

### GET /api/loop/status
Get current loop mode status.

**Response (200 OK):**
```json
{
  "loop_mode": false,
  "status": "ready",
  "message": ""
}
```

---

### POST /api/loop/start
Start continuous loop mode.

**Response (200 OK):**
```json
{
  "status": "loop_started",
  "message": "Quantum program running in loop mode"
}
```

**Response (409 Conflict):**
```json
{
  "error": "Loop mode already running"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

### POST /api/loop/stop
Stop continuous loop mode.

**Response (200 OK):**
```json
{
  "status": "loop_stopped",
  "message": "Quantum program stopped"
}
```

**Response (409 Conflict):**
```json
{
  "error": "Loop mode not running"
}
```

**Response (500 Server Error):**
```json
{
  "error": "error message"
}
```

---

## Cluster Coordination

### POST /api/cluster/register
Register a node in the cluster.

**Request Body:**
```json
{
  "node_id": "node-123",
  "name": "Node 1",
  "host": "192.168.1.10",
  "port": 5000,
  "capabilities": ["quantum_execution"]
}
```

**Parameters:**
- `node_id` (string, optional) — Node identifier (auto-generated if omitted)
- `name` (string, default: "unknown") — Human-readable node name
- `host` (string, default: "unknown") — Node hostname or IP
- `port` (integer, default: 5000) — Node port
- `capabilities` (array, default: []) — List of node capabilities

**Response (200 OK):**
```json
{
  "node_id": "node-123",
  "status": "registered",
  "message": "Node registered successfully"
}
```

---

### POST /api/cluster/heartbeat
Update last_seen timestamp for a node.

**Request Body:**
```json
{
  "node_id": "node-123"
}
```

**Parameters:**
- `node_id` (string, required) — Node identifier

**Response (200 OK):**
```json
{
  "status": "ok",
  "node_id": "node-123",
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "node_id is required"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Node not found"
}
```

---

### GET /api/cluster/nodes
List all registered nodes.

**Response (200 OK):**
```json
{
  "nodes": [
    {
      "node_id": "node-123",
      "name": "Node 1",
      "host": "192.168.1.10",
      "port": 5000,
      "capabilities": ["quantum_execution"],
      "registered_at": "2026-03-18T10:25:00.000000",
      "last_seen": 1000.5,
      "last_seen_seconds_ago": 5.3,
      "status": "active"
    }
  ],
  "total": 1,
  "active": 1,
  "inactive": 0
}
```

---

### DELETE /api/cluster/nodes/<node_id>
Deregister a node.

**Path Parameters:**
- `node_id` (string, required) — Node identifier

**Response (200 OK):**
```json
{
  "status": "deregistered",
  "node_id": "node-123"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Node not found"
}
```

---

### GET /api/cluster/status
Get cluster status summary.

**Response (200 OK):**
```json
{
  "total_nodes": 3,
  "active_nodes": 2,
  "inactive_nodes": 1,
  "this_node": {
    "host": "pod-hostname",
    "port": "5000"
  },
  "timestamp": "2026-03-18T10:30:00.000000"
}
```

---

## Prometheus Metrics

### GET /metrics
Get Prometheus-format metrics.

**Response (200 OK):**
```
# HELP quantum_jobs_total Total quantum jobs by status
# TYPE quantum_jobs_total counter
quantum_jobs_total{status="completed"} 42
quantum_jobs_total{status="failed"} 2
quantum_jobs_total{status="cancelled"} 1

# HELP quantum_jobs_running Currently running quantum jobs
# TYPE quantum_jobs_running gauge
quantum_jobs_running 0

# HELP quantum_jobs_queued Jobs waiting in queue
# TYPE quantum_jobs_queued gauge
quantum_jobs_queued 5

# HELP quantum_circuit_execution_seconds Quantum circuit execution duration
# TYPE quantum_circuit_execution_seconds summary
quantum_circuit_execution_seconds{quantile="0.5"} 0.123
quantum_circuit_execution_seconds{quantile="0.9"} 0.456
quantum_circuit_execution_seconds{quantile="0.99"} 0.789
quantum_circuit_execution_seconds_sum 50.123
quantum_circuit_execution_seconds_count 200

# HELP quantum_cluster_nodes_total Registered cluster nodes by status
# TYPE quantum_cluster_nodes_total gauge
quantum_cluster_nodes_total{state="active"} 2
quantum_cluster_nodes_total{state="inactive"} 1

# HELP quantum_loop_mode_active Whether loop mode is currently active
# TYPE quantum_loop_mode_active gauge
quantum_loop_mode_active 0

# HELP http_requests_total Total HTTP requests by endpoint and method
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/status",method="GET"} 150
http_requests_total{endpoint="/api/execute",method="POST"} 42
```

---

## Error Responses

### 404 Not Found
```json
{
  "error": "Not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Server error"
}
```

---

## Notes

- All timestamps are in ISO 8601 format
- Thread-safe operations use locks for concurrent access
- Preset QASM files: `expt.qasm`, `expt12.qasm`, `expt16.qasm` (in project root)
- User QASM files are stored in `qasm/` subfolder
- Circuit diagrams use Qiskit's SVG output format
- Metrics are in Prometheus text exposition format (version 0.0.4)
