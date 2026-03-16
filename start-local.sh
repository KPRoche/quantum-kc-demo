#!/bin/bash

# Start Quantum Raspberry Tie locally without Docker
# Useful for development and testing

set -e

echo "🚀 Quantum Raspberry Tie - Local Startup"
echo "=========================================="

# Check Python version
PYTHON_CMD=$(which python3 || which python)
if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Python 3 not found. Please install Python 3.9 or later."
    exit 1
fi

VERSION=$($PYTHON_CMD --version)
echo "✓ Found $VERSION"

# Create/activate virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

echo "🔌 Activating virtual environment..."
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate 2>/dev/null

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements-docker.txt

# Create necessary directories
mkdir -p svg credentials

# Show startup info
echo ""
echo "=========================================="
echo "✨ Setup complete!"
echo ""
echo "🌐 Web Dashboard will be available at:"
echo "   http://localhost:5000"
echo ""
echo "📝 Press Ctrl+C to stop the server"
echo "=========================================="
echo ""

# Start the dashboard
python web_dashboard.py
