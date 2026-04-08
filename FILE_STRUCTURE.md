# Container File Structure - /app/files

## Current Pod Details
- **Deployment**: quantum-kc-demo v0.2.25
- **Pod User**: quantum (UID 1000)
- **Container Runtime**: Docker (Kubernetes)
- **Snapshot Date**: 2026-04-08

## Directory Tree with Permissions

```
/app/files
├── (d) drwxr-xr-x  quantum:quantum  4096  /app/files
│
├── control/
│   ├── (d) drwxrwxrwx  quantum:quantum  4096
│   ├── command.json          -rw-rw-rw-  quantum:quantum  181 bytes
│   └── config.json           -rw-r--r--  quantum:quantum   28 bytes
│
├── qasm/
│   └── (d) drwxr-xr-x  quantum:quantum  4096
│       └── (empty)
│
└── svg/
    └── (d) drwxrwxrwx  root:root  4096
        └── (empty)
```

## Detailed Permissions Analysis

### /app/files
- **Type**: Directory
- **Permissions**: `drwxr-xr-x` (755)
- **Owner**: quantum:quantum
- **Access**:
  - Owner (quantum): read, write, execute
  - Group (quantum): read, execute
  - Others: read, execute

### /app/files/control
- **Type**: Directory
- **Permissions**: `drwxrwxrwx` (777)
- **Owner**: quantum:quantum
- **Access**:
  - Owner (quantum): read, write, execute
  - Group (quantum): read, write, execute
  - Others: read, write, execute
- **Purpose**: Command input/output directory for control system

#### Files in control/
- **command.json**
  - Permissions: `-rw-rw-rw-` (666)
  - Owner: quantum:quantum
  - Size: 181 bytes
  - Purpose: Run commands from Flask API

- **config.json**
  - Permissions: `-rw-r--r--` (644)
  - Owner: quantum:quantum
  - Size: 28 bytes
  - Purpose: Configuration storage

### /app/files/qasm
- **Type**: Directory
- **Permissions**: `drwxr-xr-x` (755)
- **Owner**: quantum:quantum
- **Access**:
  - Owner (quantum): read, write, execute
  - Group (quantum): read, execute
  - Others: read, execute
- **Contents**: Empty
- **Purpose**: Intended for QASM circuit files (not currently used)

#### Current QASM File Locations
QASM files are currently stored in `/app/` directly:
- `/app/expt.qasm` - Default 5-qubit circuit
- `/app/expt12.qasm` - 12-qubit circuit
- `/app/expt16.qasm` - 16-qubit circuit  
- `/app/expt32.qasm` - 32-qubit circuit

**⚠️ Note**: These built-in QASM files are hardcoded in the Dockerfile and the code looks for them in `/app/` (scriptfolder). The `/app/files/qasm/` directory is currently unused.

### /app/files/svg
- **Type**: Directory
- **Permissions**: `drwxrwxrwx` (777)
- **Owner**: root:root ⚠️
- **Access**:
  - Owner (root): read, write, execute
  - Group (root): read, write, execute
  - Others: read, write, execute
- **Contents**: Empty
- **Purpose**: SVG visualization output

## Permission Issues Identified

### ⚠️ svg/ Folder Ownership Issue
- **Problem**: `/app/files/svg` is owned by `root:root` instead of `quantum:quantum`
- **Impact**: While permissions allow quantum user to write (777), the ownership mismatch could cause issues with:
  - File deletion/cleanup
  - Permission maintenance
  - Kubernetes volume handling
- **Recommendation**: Ensure svg/ is owned by quantum user and group

### ✅ control/ Directory Permissions
- **Status**: Correct
- **Configuration**: 777 permissions with quantum ownership
- **Purpose**: Allows Flask API (quantum user) to read/write commands and configs

## Expected Files (Not Currently Present)

### Missing Expected Files
- `/app/files/control/result.json` - **MISSING**
  - Should contain quantum execution results
  - Should be written by the quantum execution block
  - Should be polled by Flask API monitor
  - ⚠️ **This is the core issue**: Results are not being persisted to file

### Expected Content Structure When Working
```
/app/files
├── control/
│   ├── command.json          (run commands from API)
│   ├── config.json           (execution configuration)
│   ├── result.json           (execution results) ← MISSING
│   └── command.tmp           (temporary during write)
├── qasm/
│   ├── custom_circuit.qasm   (uploaded QASM files)
│   └── ...
└── svg/
    └── circuit_visualization.html (SVG output)
```

## File Access Patterns

### Flask API (web_dashboard.py)
- Reads: `command.json`, `config.json`
- Writes: `command.json`, `config.json`
- Monitors: `result.json` (for modifications)
- Watches: `svg/` directory

### Quantum Execution Block (QuantumKCDemo.v0_2.py)
- Reads: `command.json`, `config.json`, QASM files
- Writes: `result.json` (should be writing but isn't)
- Output: `svg/circuit_visualization.html`

## Permission Model Summary

| Component | Folder | Permissions | Owner | Purpose |
|-----------|--------|-------------|-------|---------|
| control | 777 | quantum:quantum | Command/config/result IPC |
| qasm | 755 | quantum:quantum | QASM file storage |
| svg | 777 | root:root ⚠️ | SVG visualization output |

## Recommendations

### Priority 1: Critical Issues

1. **Fix svg/ Ownership**
   ```bash
   kubectl exec -n quantum deployment/quantum-kc-demo -- \
     chown -R quantum:quantum /app/files/svg
   ```

2. **Verify Result File Creation**
   - Monitor `/app/files/control/` for `result.json` appearance
   - Check permissions when file appears
   - Currently not being created - this is the core blocker

### Priority 2: Design Improvements

3. **Consolidate QASM Files Under /app/files/qasm/**
   - Move built-in QASM files from `/app/` to `/app/files/qasm/`
   - Update code to look in `/app/files/qasm/` instead of scriptfolder
   - Would allow easier volume mounting for custom QASM files
   - Better separation of concerns (data vs. runtime)

   Proposed structure:
   ```
   /app/files/qasm/
   ├── expt.qasm       (5-qubit default)
   ├── expt12.qasm     (12-qubit)
   ├── expt16.qasm     (16-qubit)
   ├── expt32.qasm     (32-qubit)
   └── custom_*.qasm   (user-uploaded circuits)
   ```

4. **Add result.json to Expected Artifacts**
   - Should be created after each execution
   - Should be readable by Flask API
   - Should be accessible to monitor thread
   - Path: `/app/files/control/result.json`
