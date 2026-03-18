# Cluster API Reference

This document describes the Kubernetes/OpenShift cluster-aware endpoints and core quantum execution endpoints.

## 📌 Complete API Reference

For the **comprehensive and authoritative API documentation**, see: [`quantum-kc-demo-API.md`](./quantum-kc-demo-API.md)

This file focuses on cluster coordination, job queue, and Prometheus metrics integration. The main API reference covers all endpoints including execution, configuration, QASM management, and discovery.

## 🔍 API Discovery

### GET /api/endpoints
Get a comprehensive map of all available API endpoints organized by category.

**Response (200 OK):**
```json
{
  "base_url": "http://localhost:5000",
  "endpoints": {
    "core": [...],
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
curl http://localhost:5000/api/endpoints | jq
```

This endpoint provides **dynamic API discovery** — use it to programmatically discover all available endpoints instead of relying on static documentation.

---

## Health & Readiness Probes

These endpoints are used by Kubernetes liveness and readiness probes to monitor pod health.

### GET /health
**Liveness probe** — Verify the app is alive and responsive (no deadlock).

Returns lightweight information without heavy I/O.

**Response 200 (OK):**
```json
{
  "status": "ok",
  "uptime_seconds": 42.5,
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

**Response 503 (Service Unavailable):**
```json
{
  "status": "error",
  "reason": "lock_timeout",
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

### GET /ready
**Readiness probe** — Verify the app is ready to serve traffic (Qiskit initialized).

Returns 503 until Qiskit library is successfully initialized.

**Response 200 (OK):**
```json
{
  "status": "ready",
  "qiskit_available": true,
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

**Response 503 (Service Unavailable):**
```json
{
  "status": "not_ready",
  "reason": "qiskit_not_initialized",
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

---

## Qubit Measurement Read

### GET /api/qubits
Get the latest quantum circuit measurement result as both a plain string pattern and a structured array.

**Response 200 (OK):**
```json
{
  "pattern": "10110",
  "qubits": [
    {"index": 0, "value": 1},
    {"index": 1, "value": 0},
    {"index": 2, "value": 1},
    {"index": 3, "value": 1},
    {"index": 4, "value": 0}
  ],
  "num_qubits": 5,
  "timestamp": "2025-03-17T10:30:45.123456",
  "backend": "local",
  "shots": 10
}
```

**Response 404 (Not Found):**
```json
{
  "error": "No measurement available yet"
}
```

---

## Cluster Node Coordination

Nodes register themselves in the cluster and periodically send heartbeats to indicate they are active.

### POST /api/cluster/register
Register a node in the cluster. Nodes can auto-generate a UUID or provide their own.

**Request:**
```json
{
  "name": "quantum-node-1",
  "host": "10.128.0.5",
  "port": 5000,
  "capabilities": ["aer", "loop", "ibm_runtime"],
  "node_id": "optional-uuid-here"
}
```

**Response 200 (OK):**
```json
{
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "registered",
  "message": "Node registered successfully"
}
```

### POST /api/cluster/heartbeat
Update the `last_seen` timestamp for an active node.

**Request:**
```json
{
  "node_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response 200 (OK):**
```json
{
  "status": "ok",
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

**Response 404 (Not Found):**
```json
{
  "error": "Node not found"
}
```

*Note: A 404 means the node must re-register.*

### GET /api/cluster/nodes
List all registered nodes, including their last-seen time and status.

**Response 200 (OK):**
```json
{
  "nodes": [
    {
      "node_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "quantum-node-1",
      "host": "10.128.0.5",
      "port": 5000,
      "capabilities": ["aer", "loop"],
      "registered_at": "2025-03-17T10:00:00.000000",
      "last_seen_seconds_ago": 2.5,
      "status": "active"
    }
  ],
  "total": 1,
  "active": 1,
  "inactive": 0
}
```

### DELETE /api/cluster/nodes/{node_id}
Deregister a node from the cluster.

**Response 200 (OK):**
```json
{
  "status": "deregistered",
  "node_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response 404 (Not Found):**
```json
{
  "error": "Node not found"
}
```

### GET /api/cluster/status
Get a summary of cluster status.

**Response 200 (OK):**
```json
{
  "total_nodes": 3,
  "active_nodes": 2,
  "inactive_nodes": 1,
  "this_node": {
    "host": "10.128.0.5",
    "port": 5000
  },
  "timestamp": "2025-03-17T10:30:45.123456"
}
```

**Automatic Node Staling:** Nodes that do not send a heartbeat for >30 seconds are automatically marked as `"status": "inactive"` by a background thread.

---

## Job Queue Management

Submit, track, and manage quantum circuit execution jobs in a queue.

### POST /api/jobs
Submit a new quantum circuit job to the queue.

**Request:**
```json
{
  "qasm_file": "expt.qasm",
  "backend": "local",
  "shots": 10,
  "priority": 5
}
```

- `qasm_file`: Must be one of the available QASM files in the app directory (e.g., `expt.qasm`, `expt12.qasm`, `expt16.qasm`)
- `backend`: "local" or a real IBM Quantum backend name
- `shots`: Number of measurement repetitions
- `priority`: Priority level (stored for future use; current implementation is FIFO)

**Response 202 (Accepted):**
```json
{
  "job_id": "12345678-1234-5678-1234-567812345678",
  "status": "queued",
  "submitted_at": "2025-03-17T10:30:45.123456",
  "queue_depth": 3
}
```

### GET /api/jobs
List all jobs with filtering and pagination.

**Query Parameters:**
- `?status=queued` — Filter by status (queued|running|completed|failed|cancelled)
- `?limit=50&offset=0` — Pagination

**Response 200 (OK):**
```json
{
  "jobs": [
    {
      "job_id": "12345678-1234-5678-1234-567812345678",
      "submitted_at": "2025-03-17T10:30:45.123456",
      "started_at": "2025-03-17T10:30:46.000000",
      "completed_at": "2025-03-17T10:30:48.500000",
      "status": "completed",
      "parameters": {
        "qasm_file": "expt.qasm",
        "backend": "local",
        "shots": 10,
        "priority": 5
      },
      "result": {
        "counts": {"00000": 3, "00001": 7},
        "backend": "QasmSimulator",
        "timestamp": "2025-03-17T10:30:48.500000",
        "shots": 10,
        "num_qubits": 5
      },
      "error": null
    }
  ],
  "total": 42,
  "queued": 0,
  "running": 1,
  "completed": 40,
  "failed": 1,
  "cancelled": 0
}
```

### GET /api/jobs/{job_id}
Get detailed information about a specific job.

**Response 200 (OK):**
```json
{
  "job_id": "12345678-1234-5678-1234-567812345678",
  "submitted_at": "2025-03-17T10:30:45.123456",
  "started_at": "2025-03-17T10:30:46.000000",
  "completed_at": "2025-03-17T10:30:48.500000",
  "status": "completed",
  "parameters": {
    "qasm_file": "expt.qasm",
    "backend": "local",
    "shots": 10,
    "priority": 5
  },
  "result": {
    "counts": {"00000": 3, "00001": 7},
    ...
  },
  "error": null
}
```

**Response 404 (Not Found):**
```json
{
  "error": "Job not found"
}
```

### DELETE /api/jobs/{job_id}
Cancel a queued job. Running jobs cannot be cancelled.

**Response 200 (OK):**
```json
{
  "status": "cancelled",
  "job_id": "12345678-1234-5678-1234-567812345678"
}
```

**Response 409 (Conflict):**
```json
{
  "error": "Cannot cancel a running job"
}
```

**Response 404 (Not Found):**
```json
{
  "error": "Job not found"
}
```

---

## Prometheus Metrics

### GET /metrics
Prometheus-format metrics endpoint for monitoring cluster and quantum execution health.

**Response 200 (OK):**
Returns text in Prometheus exposition format (`text/plain; version=0.0.4`).

**Metrics Exposed:**

- **quantum_jobs_total{status="completed|failed|cancelled"}** — Counter of completed jobs by outcome
- **quantum_jobs_running** — Gauge of currently running jobs
- **quantum_jobs_queued** — Gauge of jobs waiting in queue
- **quantum_circuit_execution_seconds** — Summary of circuit execution duration (quantiles: 0.5, 0.9, 0.99, _sum, _count)
- **quantum_cluster_nodes_total{state="active|inactive"}** — Gauge of cluster nodes by status
- **quantum_loop_mode_active** — Gauge (0 or 1) indicating whether loop mode is running
- **http_requests_total{endpoint="...",method="..."}** — Counter of HTTP requests by endpoint and method (excludes /health, /ready, /metrics)

**Example:**
```
# HELP quantum_jobs_total Total quantum jobs by status
# TYPE quantum_jobs_total counter
quantum_jobs_total{status="completed"} 42
quantum_jobs_total{status="failed"} 1
quantum_jobs_total{status="cancelled"} 0

# HELP quantum_jobs_running Currently running quantum jobs
# TYPE quantum_jobs_running gauge
quantum_jobs_running 1

# HELP quantum_circuit_execution_seconds Quantum circuit execution duration
# TYPE quantum_circuit_execution_seconds summary
quantum_circuit_execution_seconds{quantile="0.5"} 2.15
quantum_circuit_execution_seconds{quantile="0.9"} 3.80
quantum_circuit_execution_seconds{quantile="0.99"} 5.20
quantum_circuit_execution_seconds_sum 98.5
quantum_circuit_execution_seconds_count 42

# HELP quantum_cluster_nodes_total Registered cluster nodes by status
# TYPE quantum_cluster_nodes_total gauge
quantum_cluster_nodes_total{state="active"} 2
quantum_cluster_nodes_total{state="inactive"} 0

# HELP quantum_loop_mode_active Whether loop mode is currently active
# TYPE quantum_loop_mode_active gauge
quantum_loop_mode_active 0

# HELP http_requests_total Total HTTP requests by endpoint and method
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/status",method="GET"} 127
http_requests_total{endpoint="/api/jobs",method="POST"} 14
```

---

## Backward Compatibility

The existing endpoints remain unchanged and fully functional:

- **GET /api/status** — Still returns `quantum_state`
- **POST /api/execute** — Now returns `job_id` in addition to `status` (fully backward-compatible)
- **GET /api/result** — Still returns the last execution result
- **GET /api/svg** — Still returns auto-refreshing SVG visualization
- **POST/GET /api/config** — Still manages configuration
- **POST/GET /api/auth/** — Still manages IBM Quantum authentication
- **POST /api/loop/start** — Still starts loop mode
- **POST /api/loop/stop** — Still stops loop mode

---

## Kubernetes Deployment

Three manifest files are provided in `k8s/`:

- **deployment.yaml** — Pod deployment with liveness/readiness probes, resource limits, and downward API integration
- **service.yaml** — ClusterIP Service for pod discovery
- **servicemonitor.yaml** — Prometheus Operator integration (optional)

Apply all three:
```bash
kubectl apply -f k8s/
```

---

## Design Notes

### Job Queue

- Single background worker thread processes jobs FIFO
- Concurrent `/api/jobs` submissions are accepted and queued instead of rejected
- Jobs track full lifecycle: queued → running → completed/failed/cancelled
- Cancelled jobs are skipped when dequeued (lazy cancellation)
- Execution metrics (duration, success/failure) are accumulated in Prometheus counters

### Cluster Coordination

- Nodes auto-generate UUIDs if not provided on registration
- A background reaper thread marks nodes inactive after 30 seconds of no heartbeat
- Stale nodes remain in the registry until explicitly deregistered
- Environment variable `POD_IP` (set by Kubernetes downward API) is used for node identity; falls back to hostname

### Metrics

- HTTP request counting via Flask `@before_request` hook
- Execution duration list capped at 1000 entries (FIFO eviction)
- Percentiles computed at scrape time (no pre-aggregation)
- Prometheus-compatible text format (no external library required)

---

## Example: Multi-Node Cluster

### Node A (10.128.0.5:5000)
```bash
curl -X POST http://10.128.0.5:5000/api/cluster/register -H "Content-Type: application/json" -d '{
  "name": "node-a",
  "host": "10.128.0.5",
  "port": 5000,
  "capabilities": ["aer"]
}'
```

### Node B (10.128.0.6:5000)
```bash
curl -X POST http://10.128.0.6:5000/api/cluster/register -H "Content-Type: application/json" -d '{
  "name": "node-b",
  "host": "10.128.0.6",
  "port": 5000,
  "capabilities": ["ibm_runtime"]
}'
```

### Node A: View cluster
```bash
curl http://10.128.0.5:5000/api/cluster/nodes
```

Response:
```json
{
  "nodes": [
    {"node_id": "...", "name": "node-a", "host": "10.128.0.5", "status": "active", ...},
    {"node_id": "...", "name": "node-b", "host": "10.128.0.6", "status": "active", ...}
  ],
  "total": 2,
  "active": 2,
  "inactive": 0
}
```

### Node A: Submit and track job
```bash
# Submit a job
JOB_ID=$(curl -X POST http://10.128.0.5:5000/api/jobs -H "Content-Type: application/json" -d '{
  "qasm_file": "expt.qasm",
  "backend": "local",
  "shots": 10
}' | jq -r '.job_id')

# Poll status
curl http://10.128.0.5:5000/api/jobs/$JOB_ID

# When complete, get result
curl http://10.128.0.5:5000/api/jobs/$JOB_ID | jq '.result'
```
