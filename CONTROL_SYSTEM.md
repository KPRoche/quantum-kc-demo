# Quantum Control System

## Overview

The Quantum KC Demo now includes a **control system** that enables coordinated execution between the Flask web dashboard and the quantum execution engine. This replaces the old architecture where the quantum app would continuously loop regardless of configuration.

## Architecture

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Container Startup                                           │
└─────────────────────────────────────────────────────────────┘
         │
         ├─→ Flask App (Background)
         │   ├─ Initializes quantum_control
         │   └─ Creates /tmp/quantum-control/
         │
         └─→ Quantum App (Foreground)
             ├─ Initializes quantum_control
             ├─ Enters outer waiting loop
             └─ Calls wait_for_command()
                   │
                   ├─ [WAITING FOR COMMAND]
                   │
                   ↓ Flask receives POST /api/execute
                   │
                   ├─ Flask calls request_run(["-b:aer", "-hex"], description)
                   ├─ Control file: /tmp/quantum-control/command.json updated
                   │
                   ↓ Quantum app detects command
                   │
                   ├─ acknowledge_command()
                   ├─ apply_parameters(cmd.parameters)
                   ├─ Execute one circuit (Looping = False)
                   ├─ command_complete()
                   │
                   └─ Return to waiting loop
```

## Components

### 1. Control Module (`quantum_control.py`)

Provides inter-process communication via a JSON file at `/tmp/quantum-control/command.json`.

**Key Functions:**

```python
# Flask calls this to request execution
request_run(parameters: List[str], description: str) -> bool

# Quantum app calls this to wait for a command
wait_for_command(timeout: Optional[float]) -> Dict[str, Any]

# Quantum app calls these to signal progress
acknowledge_command() -> bool
command_complete() -> bool

# Get current system status
get_status() -> Dict[str, Any]
```

**Command File Format:**

```json
{
  "status": "waiting|queued|running",
  "command": "wait|run|shutdown",
  "parameters": ["-b:aer", "-hex"],
  "description": "Execute 5-qubit demo on Aer backend",
  "timestamp": 1674330128.1234567
}
```

### 2. Quantum App Integration (`QuantumKCDemo.v0_2.py`)

**New Features:**

- **Graceful Degradation:** If `quantum_control` module unavailable, runs in CLI mode with original behavior
- **Parameter Processing Function:** `apply_parameters(param_list)` - resets globals and applies parameters
- **Outer Control Loop:**
  ```python
  if outer_control_loop:
      while outer_control_loop:
          cmd = wait_for_command()
          if cmd.command == "run":
              apply_parameters(cmd.parameters)
              # Execute one circuit
              command_complete()
          elif cmd.command == "shutdown":
              break
  ```

**Execution Modes:**

| Mode | Configuration | Behavior |
|------|---------------|----------|
| **CLI (CLI args)** | `-int` or command line | Auto-loops on simulators (original) |
| **CLI (no args)** | None | Default parameters, single shot |
| **Container** | Flask + control system enabled | Waits for commands from Flask |

### 3. Flask Integration (`web_dashboard.py`)

**Execute Endpoint Enhancement:**

```python
@app.route("/api/execute", methods=["POST"])
def execute_circuit():
    """
    Request a quantum circuit execution.

    If control system enabled:
        - Builds parameter list from request
        - Calls quantum_control.request_run()
        - Quantum app receives command and executes
        - Returns immediately with status "submitted_to_quantum"

    If control system unavailable:
        - Falls back to job queue mechanism
    """
```

**Status Endpoint Enhancement:**

```python
@app.route("/api/status")
def get_status():
    # Returns:
    # {
    #     "quantum_state": {...},
    #     "control_system": {"status": "waiting", ...},
    #     "execution_mode": "control-based"
    # }
```

### 4. Entrypoint Updates (`entrypoint.sh`)

**Before:**
```bash
python qapp.py -b:aer -hex &    # Background (auto-looping)
python web_dashboard.py         # Foreground
```

**After:**
```bash
python web_dashboard.py &       # Background
python qapp.py -b:aer -hex      # Foreground (waits for commands)
```

## Usage

### Local CLI Usage (Backward Compatible)

```bash
# Interactive mode
python qapp.py -int

# With parameters (auto-loops on simulators)
python qapp.py -b:aer -hex

# Single execution
python qapp.py -b:aer
```

### Container Usage

1. **Start container:**
   ```bash
   docker run -p 5000:5000 ghcr.io/kproche/quantum-kc-demo:latest
   ```

2. **Access dashboard:**
   ```
   http://localhost:5000
   ```

3. **Execute via API:**
   ```bash
   curl -X POST http://localhost:5000/api/execute \
     -H "Content-Type: application/json" \
     -d '{
       "qasm_file": "expt.qasm",
       "backend": "aer",
       "shots": 10
     }'
   ```

4. **Check status:**
   ```bash
   curl http://localhost:5000/api/status | jq '.control_system'
   ```

## Advantages

✅ **Separation of Concerns:** Flask controls execution, quantum app executes
✅ **No Background Processes:** Simpler process management, easier debugging
✅ **Single-Shot Capability:** Can run one circuit without auto-looping
✅ **Backward Compatible:** Old CLI usage still works
✅ **Human-Readable State:** JSON control file is easy to inspect
✅ **No Signal Handling:** File-based IPC is simpler than POSIX signals
✅ **Extensible:** Can easily add new commands (pause, resume, etc.)

## Control File Location

- **Path:** `/tmp/quantum-control/command.json`
- **Permissions:** `0o666` (readable/writable by all)
- **Atomic Operations:** Writes use temp file + rename for consistency

## Debugging

### Check Control System Status

```bash
cat /tmp/quantum-control/command.json | jq .
```

### Monitor in Real-Time

```bash
watch -n 0.1 'cat /tmp/quantum-control/command.json | jq .'
```

### Check Execution Logs

```bash
# Flask logs
docker logs <container> 2>&1 | grep -i control

# Quantum logs (if running locally)
python qapp.py -b:aer -hex 2>&1 | grep -i control
```

## Implementation Details

### Why Not Use Signals?

- Signals can be lost or overloaded
- No way to pass parameters with signals
- More complex error handling

### Why Not Use a Database?

- Extra dependency
- Overkill for simple state
- /tmp is designed for temporary state

### Why Not Use a Socket?

- Requires connection management
- More complex than file-based state
- File-based is more testable

### Why Not Use Environment Variables?

- Can't be changed at runtime
- Not suitable for dynamic commands
- Limited size constraints

## Migration Guide

If you have code using the old execution model:

### Old Way (Auto-looping in container)
```python
# Quantum app would loop forever
while Looping:
    # execute circuit
    Looping = UseLocal or Q.simulator
```

### New Way (Control-based)
```python
# Check command from Flask
cmd = wait_for_command()
if cmd.command == "run":
    apply_parameters(cmd.parameters)
    # execute one circuit
    command_complete()
```

## Future Enhancements

- [ ] Pause/resume commands
- [ ] Parameter validation at queue time
- [ ] Metrics collection (execution time, success rate)
- [ ] Circuit result caching
- [ ] Multi-backend orchestration
- [ ] Priority queue support

## See Also

- [Memory: control_loop_architecture](../memory/control_loop_architecture.md)
- [Deployment Documentation](k8s/README.md)
- [API Endpoints](web_dashboard.py)
