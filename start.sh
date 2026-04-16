#!/bin/bash
# Agent Pulse — Quick launcher
# By default opens the dashboard in a new terminal window.
# Use --here to run in the current terminal instead.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# --- Parse launcher flags (consumed here, not passed to agent_pulse.py) ---
RUN_HERE=0
PASSTHROUGH_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --here) RUN_HERE=1 ;;
        *)      PASSTHROUGH_ARGS+=("$arg") ;;
    esac
done

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

# If --here is passed, or already inside a spawned terminal, run directly
if [ "$RUN_HERE" = "1" ] || [ "$AGENT_PULSE_SPAWNED" = "1" ]; then
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${PASSTHROUGH_ARGS[@]}"
fi

# Open dashboard in a new terminal window
CMD="export AGENT_PULSE_SPAWNED=1; cd '$SCRIPT_DIR' && '$VENV/bin/python' '$SCRIPT_DIR/agent_pulse.py' ${PASSTHROUGH_ARGS[*]}"

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
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${PASSTHROUGH_ARGS[@]}"
fi
