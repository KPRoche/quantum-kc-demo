# quantum-kc-demo Backend Fix

## State Reset Bug in v0.2.5

**Location**: `web_dashboard.py`, in `_execute_queued_job()` function (~line 1430)

**Issue**: The backend does not reset `quantum_state["message"]` before starting a new execution. This causes error messages from failed jobs to persist in the status, even when subsequent executions succeed or fail for different reasons.

**The Fix**:
In the `_execute_queued_job()` function where it sets execution state, add:

```python
# Update global quantum state for backward compatibility
with state_lock:
    quantum_state["running"] = True
    quantum_state["status"] = "executing"
    quantum_state["message"] = "Running..."  # ← ADD THIS LINE
