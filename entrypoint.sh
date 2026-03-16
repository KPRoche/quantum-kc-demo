#!/bin/bash
set -e

# Start the quantum program in background (writes SVG updates with 8x8 grid)
echo "Starting quantum program..."
python app.py -b:aer -hex &
QUANTUM_PID=$!

# Give it a moment to start
sleep 2

# Start the Flask web dashboard in foreground
echo "Starting Flask web dashboard..."
python web_dashboard.py

# Clean up on exit
trap "kill $QUANTUM_PID 2>/dev/null || true" EXIT
