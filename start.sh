#!/bin/bash
# Agent Pulse — Quick launcher
# Opens the live dashboard in a new terminal window (macOS)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# Create venv if missing
if [ ! -d "$VENV" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv "$VENV"
fi

# Install deps if textual is missing
if ! "$VENV/bin/python" -c "import textual" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    "$VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
fi

# If already running inside a spawned terminal, just run directly
if [ "$AGENT_PULSE_SPAWNED" = "1" ]; then
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "$@"
fi

# Open dashboard in a new terminal window
CMD="export AGENT_PULSE_SPAWNED=1; cd '$SCRIPT_DIR' && '$VENV/bin/python' '$SCRIPT_DIR/agent_pulse.py' $*"

if command -v osascript &>/dev/null; then
    # macOS — open a new Terminal.app window
    osascript -e "tell application \"Terminal\"
        activate
        do script \"$CMD\"
    end tell" &>/dev/null
    echo "⚡ Agent Pulse launched in a new Terminal window."
elif command -v gnome-terminal &>/dev/null; then
    gnome-terminal -- bash -c "$CMD; exec bash" &>/dev/null &
    echo "⚡ Agent Pulse launched in a new terminal window."
elif command -v xterm &>/dev/null; then
    xterm -e bash -c "$CMD" &>/dev/null &
    echo "⚡ Agent Pulse launched in xterm."
else
    # Fallback — run in current terminal
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "$@"
fi
