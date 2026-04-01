# Quantum Flask Server API Endpoints

**Server:** `web_dashboard.py` (runs on port 5000)
**Base URL:** `http://localhost:5000`

## Core Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/` | GET | Serve main dashboard page | HTML dashboard |
| `/api/status` | GET | Get current quantum state | JSON state object |
| `/api/result` | GET | Get last execution result | JSON result data |

## Qubit Measurement Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/qubits` | GET | Get full qubit measurement data | `{pattern, qubits, num_qubits, backend, shots, timestamp}` |
| `/api/qubits/simple` | GET | Get simplified qubit measurement | `{pattern, num_qubits, shots, timestamp}` |

## Execution Endpoints

| Endpoint | Method | Purpose | Payload |
|----------|--------|---------|---------|
| `/api/execute` | POST | Execute a quantum circuit | `{qasm_file, backend, shots, qubits}` |
| `/api/svg` | GET | Get SVG result with auto-refresh wrapper | HTML with auto-refresh |
| `/api/svg/raw` | GET | Get raw SVG/HTML content (no wrapper) | HTML content |

## Configuration Endpoints

| Endpoint | Method | Purpose | Payload |
|----------|--------|---------|---------|
| `/api/config` | GET/POST | Get/set configuration | JSON config data |
| `/api/auth/save` | POST | Save IBM Quantum credentials | `{api_key, crn}` |
| `/api/auth/status` | GET | Check authentication status | JSON status |

## Loop Mode Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/loop/status` | GET | Get loop mode status | `{loop_mode, status, message}` |
| `/api/loop/start` | POST | Start continuous loop execution | `{status, message}` |
| `/api/loop/stop` | POST | Stop continuous loop execution | `{status, message}` |

## Key State Object

```javascript
{
  "running": boolean,
  "last_result": { /* result object */ },
  "last_result_time": "ISO timestamp",
  "status": string,  // "ready", "loading_circuit", "executing", "success", "error", "loop_running"
  "message": string,
  "circuit_info": { "qubits": number, "gates": number },
  "backend_info": { "name": string, "shots": number },
  "loop_mode": boolean
}
```

## Example Usage

### Check Status
```bash
curl http://localhost:5000/api/status
```

### Start Loop Mode
```bash
curl -X POST http://localhost:5000/api/loop/start
```

### Stop Loop Mode
```bash
curl -X POST http://localhost:5000/api/loop/stop
```

### Save Credentials
```bash
curl -X POST http://localhost:5000/api/auth/save \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-key", "crn": "your-crn"}'
```

### Get SVG Result
```bash
curl http://localhost:5000/api/svg/raw
```
