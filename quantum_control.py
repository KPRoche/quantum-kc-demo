"""
Quantum Control Module
Handles inter-process communication between Flask web dashboard and quantum execution engine.
Implements a file-based command queue for requesting quantum circuit runs with specified parameters.
"""

import os
import json
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

# Control file location
CONTROL_DIR = Path("/app/files/control")
CONTROL_FILE = CONTROL_DIR / "command.json"
CONTROL_LOCK_FILE = CONTROL_DIR / ".lock"

# Ensure control directory exists
CONTROL_DIR.mkdir(exist_ok=True, mode=0o777)


def initialize_control():
    """Initialize the control system and create default command file."""
    try:
        CONTROL_DIR.chmod(0o777)
        if not CONTROL_FILE.exists():
            default_cmd = {
                "status": "waiting",
                "command": "wait",
                "parameters": [],
                "timestamp": time.time(),
            }
            write_command(default_cmd)
    except Exception as e:
        print(f"Warning: Could not initialize control directory: {e}")


def write_command(cmd_dict: Dict[str, Any]) -> bool:
    """
    Atomically write a command to the control file.

    Args:
        cmd_dict: Command dictionary with keys: status, command, parameters, timestamp

    Returns:
        True if successful, False otherwise
    """
    try:
        # Use atomic write pattern: write to temp file, then rename
        temp_file = CONTROL_FILE.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(cmd_dict, f, indent=2)
        temp_file.replace(CONTROL_FILE)
        # Ensure readable by quantum process
        CONTROL_FILE.chmod(0o666)
        return True
    except Exception as e:
        print(f"Error writing command file: {e}")
        return False


def read_command() -> Optional[Dict[str, Any]]:
    """
    Read the current command from the control file.

    Returns:
        Command dictionary or None if error
    """
    try:
        if not CONTROL_FILE.exists():
            return None
        with open(CONTROL_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading command file: {e}")
        return None


def wait_for_command(timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Block until a new command is available (not 'wait' status).

    This is what the quantum process calls to pause and wait for the next run.

    Args:
        timeout: Maximum time to wait in seconds (None = infinite)

    Returns:
        Command dictionary when a command is received, or None on timeout
    """
    start_time = time.time()
    last_timestamp = read_command()
    if last_timestamp:
        last_timestamp = last_timestamp.get("timestamp", 0)

    while True:
        cmd = read_command()
        if cmd and cmd.get("status") != "waiting":
            # Got a new command
            return cmd

        # Check timeout
        if timeout is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return None

        # Brief sleep to avoid busy-waiting
        time.sleep(0.1)


def request_run(parameters: List[str], description: str = "") -> bool:
    """
    Request a quantum circuit run with specified parameters.
    Called by Flask to trigger the quantum process.

    Args:
        parameters: List of command-line style parameters (e.g., ["-b:aer", "-hex"])
        description: Human-readable description of the request

    Returns:
        True if command was queued successfully
    """
    cmd = {
        "status": "queued",
        "command": "run",
        "parameters": parameters,
        "description": description,
        "timestamp": time.time(),
    }
    return write_command(cmd)


def acknowledge_command() -> bool:
    """
    Acknowledge that a command was received and is being processed.
    Called by quantum process to mark the command as in-progress.

    Returns:
        True if successful
    """
    cmd = read_command()
    if cmd:
        cmd["status"] = "running"
        return write_command(cmd)
    return False


def command_complete() -> bool:
    """
    Mark the current command as complete and return to waiting state.
    Called by quantum process after execution finishes.

    Returns:
        True if successful
    """
    cmd = {
        "status": "waiting",
        "command": "wait",
        "parameters": [],
        "timestamp": time.time(),
    }
    return write_command(cmd)


def shutdown() -> bool:
    """
    Request that the quantum process shut down gracefully.

    Returns:
        True if command was queued successfully
    """
    cmd = {
        "status": "queued",
        "command": "shutdown",
        "parameters": [],
        "timestamp": time.time(),
    }
    return write_command(cmd)


def get_status() -> Dict[str, Any]:
    """
    Get the current status of the quantum control system.

    Returns:
        Dictionary with status information
    """
    cmd = read_command()
    if cmd:
        return {
            "status": cmd.get("status", "unknown"),
            "command": cmd.get("command", "unknown"),
            "description": cmd.get("description", ""),
            "timestamp": cmd.get("timestamp", 0),
        }
    return {"status": "error", "command": "unknown"}


if __name__ == "__main__":
    # Test the control system
    print("Initializing control system...")
    initialize_control()

    print("Current status:", get_status())
    print("Requesting run...")
    request_run(["-b:aer", "-hex"], "Test run")
    print("Status after request:", get_status())

    print("Acknowledging command...")
    acknowledge_command()
    print("Status after acknowledge:", get_status())

    print("Completing command...")
    command_complete()
    print("Status after complete:", get_status())


# Control system is available when this module can be imported
CONTROL_ENABLED = True
