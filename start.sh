#!/bin/bash
# Agent Pulse — Quick launcher
# Launches the real-time agent tracking dashboard

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check for Rich
if ! python3 -c "import rich" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# Launch the dashboard
exec python3 "$SCRIPT_DIR/agent_pulse.py" --live "$@"
