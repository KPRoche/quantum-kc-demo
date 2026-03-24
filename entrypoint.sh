#!/bin/bash
set -e

# In container deployment, run both services in a coordinated way
# The quantum program uses the control system to wait for commands from Flask

echo "Starting Quantum KC Demo Services..."
echo ""

# Start Flask in the background so quantum process can communicate with it
echo "Starting Flask web dashboard (background)..."
python web_dashboard.py &
FLASK_PID=$!

# Give Flask a moment to start and initialize
sleep 2

echo "Starting quantum program (control-enabled, waits for commands)..."
# Run quantum program in foreground - it will wait for commands from Flask
python qapp.py -b:aer -hex

# If quantum program exits, clean up Flask
echo "Quantum program ended. Cleaning up..."
kill $FLASK_PID 2>/dev/null || true

exit 0
