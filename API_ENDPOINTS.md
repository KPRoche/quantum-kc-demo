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
| `/api/auth/status` | GET | Check authentication status | `{tokenStored, authenticated, message, crn?, lastIbmError?}` (see below) |

### `/api/auth/status` response shape (v0.4.0+)

Always returns 200 when the handler can determine an answer. Returns 500 only
when the handler itself fails — e.g., a corrupt or unreadable `auth.json`, or
`qiskit_ibm_runtime` not importable.

```json
{
  "tokenStored":   true,
  "authenticated": false,
  "message":       "Credentials saved but not validated this call.",
  "crn":           "crn:v1:bluemix:...",
  "lastIbmError":  null
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `tokenStored` | bool | A saved token exists on the backend (either `auth.json` on emptyDir or Qiskit's account file on the PV). Independent of IBM availability. |
| `authenticated` | bool | The token was validated against IBM **on this call**. `false` doesn't mean "no token" — check `tokenStored`. |
| `message` | string | Human-readable summary. |
| `crn` | string (optional) | Masked IBM CRN, when known from `auth.json`. May be absent after a pod restart even when `tokenStored: true`. |
| `lastIbmError` | object \| null | Present only when validation was attempted and failed. See below. |

`lastIbmError` shape:

```json
{
  "code":      "rate_limited",
  "message":   "max retries attempted; service unavailable",
  "retryable": true
}
```

`code` is one of: `rate_limited`, `service_unavailable`, `timeout`,
`account_not_found`, `unknown`. `retryable: true` indicates the Console
should render a soft "we'll keep retrying" banner; `retryable: false` is a
genuine credential / auth problem.

**State matrix:**

| Scenario | tokenStored | authenticated | lastIbmError |
|----------|------------|---------------|--------------|
| Fresh install, no token | `false` | `false` | `null` |
| Token saved + valid | `true` | `true` | `null` |
| Token saved + IBM rate-limit / 5xx | `true` | `false` | `{retryable: true}` |
| Token saved + Qiskit account drift | `true` | `false` | `{code: account_not_found, retryable: false}` |
| Token saved + invalid key | `true` | `false` | `{code: unknown, retryable: false}` |
| Pod restart, PV-only token | `true` | `false` (until next validation) | `null` |

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
