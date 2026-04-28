# Quantum Shots Parameter Bug - Complete Analysis

**Status:** Two bugs identified and root causes documented
**Date:** 2026-04-21
**Severity:** High - Shots parameter not being correctly reported in results

---

## Problem Summary

When users set the number of shots (e.g., 75) in the Quantum Control Panel and execute a circuit, the results still report the default value of 50 shots, not the value the user specified.

---

## Bug #1: Backend Forwarding (FIXED)

### Location
`/app/web_dashboard.py` - Line 423

### Root Cause
The shots parameter was only being forwarded conditionally:
```python
if shots and shots != 10:
    parameters.append(f"-shots:{shots}")
```

This condition prevented the shots parameter from always being sent to the quantum app.

### Fix Applied
Change line 423 to always append the shots parameter:
```python
parameters.append(f"-shots:{shots}")
```

**Status:** ✅ ALREADY FIXED in workload code

---

## Bug #2: Result Shots Value (NEEDS FIX)

### Location
`/app/qapp.py` - In the `execute()` method where `result_data` is built

### Root Cause
The shots field in the result is being calculated from the counts instead of using the actual `num_shots` parameter:

**Current (WRONG):**
```python
result_data = {
    "shots": sum(counts.values()),  # ← WRONG: calculates from counts
    ...
}
```

This reports the wrong shots value because it's deriving it from the execution results instead of preserving the parameter that was passed in.

### Fix Required
Change to use the actual `num_shots` parameter:
```python
result_data = {
    "shots": num_shots,  # ← CORRECT: use the actual parameter
    ...
}
```

**Status:** ❌ NEEDS FIX - This is why results still show 50 shots instead of the user-specified value

---

## Data Flow

### Frontend → Backend
1. ✅ QuantumControlPanel.tsx sends `shots: 75` in POST to `/api/execute`
2. ✅ web_dashboard.py receives it via `data.get("shots", 10)`
3. ✅ (After Bug #1 fix) web_dashboard.py forwards it to quantum app as `-shots:75`

### Backend Processing
4. ✅ qapp.py parses `-shots:75` and sets `num_shots = 75`
5. ✅ executor.execute() receives `num_shots = 75`
6. ❌ (Bug #2) result_data reports `shots: sum(counts.values())` instead of `num_shots`

### Frontend Display
7. ❌ `/api/quantum/status` returns `shots: 50` (the wrong value from step 6)
8. ❌ Any card showing shots displays 50 instead of 75

---

## How to Find and Fix Bug #2

### Search Pattern
```bash
grep -n "shots.*sum(counts" app/qapp.py
```

### Expected Output
Should find the line where `result_data` dictionary is built with `"shots": sum(counts.values())`

### Fix Steps
1. Locate the line: `"shots": sum(counts.values())`
2. Change to: `"shots": num_shots`
3. Verify that `num_shots` is in scope at that location
4. Rebuild and redeploy the backend

---

## Verification Steps

After fixing Bug #2:

1. **Set shots to 75 in Control Panel**
2. **Execute a circuit**
3. **Check `/api/quantum/status` response:**
   ```bash
   curl http://localhost:5000/api/quantum/status | jq '.shots'
   ```
   Should return: `75` (not `50`)

4. **Check that counts sum matches:**
   ```bash
   curl http://localhost:5000/api/quantum/status | jq '.counts | values | add'
   ```
   Should equal: `75`

---

## Key Code Locations

- **Frontend sends shots:** `web/components/cards/QuantumControlPanel.tsx:193` (POST body)
- **Backend receives shots:** `app/web_dashboard.py:404` (data.get())
- **Backend forwards shots:** `app/web_dashboard.py:424` (parameters.append) - ✅ FIXED
- **Quantum app parses shots:** `app/qapp.py:1301-1308` (parameter parsing)
- **Result shots value:** `app/qapp.py` (result_data dict) - ❌ NEEDS FIX

---

## Notes for Claude CLI

When using Claude CLI to examine the quantum-kc-demo repo:

1. Start with `grep -n "shots.*sum(counts" app/qapp.py` to locate Bug #2
2. Check the full context of where `result_data` is built
3. Verify `num_shots` variable is available at that location
4. Make the one-line change: `sum(counts.values())` → `num_shots`
5. Rebuild the container and redeploy to test

The fix is simple but critical - it ensures that the shots parameter requested by the user is preserved and reported in the results, not recalculated from the execution data.
