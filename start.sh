#!/bin/bash
# Agent Pulse — Quick launcher
# Runs the dashboard in the current terminal by default.
# Use --new-window to open in a new window of your current terminal emulator.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# Parse --new-window flag (pass everything else through to agent_pulse.py)
NEW_WINDOW=0
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--new-window" ]; then
        NEW_WINDOW=1
    else
        ARGS+=("$arg")
    fi
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

# Default: run in current terminal
if [ "$NEW_WINDOW" -eq 0 ] || [ "$AGENT_PULSE_SPAWNED" = "1" ]; then
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${ARGS[@]}"
fi

# --new-window: open in a new window/pane
CMD="export AGENT_PULSE_SPAWNED=1; cd '$SCRIPT_DIR' && '$VENV/bin/python' '$SCRIPT_DIR/agent_pulse.py' ${ARGS[*]}"

# tmux — new window in the current session
if [ -n "$TMUX" ]; then
    tmux new-window -n "AgentPulse" "bash -c '$CMD'"
    echo "⚡ Agent Pulse launched in a new tmux window."
    exit 0
fi

# Detect the running terminal emulator (macOS)
TERM_APP=""
if [ "$(uname)" = "Darwin" ]; then
    TERM_BUNDLE=$(__CFBundleIdentifier="" && osascript -e 'tell application "System Events" to get bundle identifier of (first process whose frontmost is true)' 2>/dev/null)
    case "$TERM_BUNDLE" in
        com.mitchellh.ghostty)          TERM_APP="ghostty" ;;
        com.googlecode.iterm2)          TERM_APP="iterm" ;;
        io.alacritty)                   TERM_APP="alacritty" ;;
        net.kovidgoyal.kitty)           TERM_APP="kitty" ;;
        com.github.wez.wezterm)         TERM_APP="wezterm" ;;
        dev.warp.Warp-Stable|dev.warp*) TERM_APP="warp" ;;
        com.apple.Terminal)             TERM_APP="terminal" ;;
    esac
fi

case "$TERM_APP" in
    ghostty)
        # Ghostty — open a new window via its CLI
        if command -v ghostty &>/dev/null; then
            ghostty -e bash -c "$CMD" &
        else
            osascript -e "tell application \"Ghostty\" to activate" \
                      -e "tell application \"System Events\" to keystroke \"n\" using command down" &>/dev/null
            sleep 0.5
            osascript -e "tell application \"System Events\" to tell process \"Ghostty\" to keystroke \"$CMD
\"" &>/dev/null
        fi
        echo "⚡ Agent Pulse launched in a new Ghostty window."
        ;;
    iterm)
        osascript -e "
            tell application \"iTerm\"
                activate
                create window with default profile command \"bash -c '$CMD'\"
            end tell" &>/dev/null
        echo "⚡ Agent Pulse launched in a new iTerm window."
        ;;
    kitty)
        kitty @ launch --type=os-window bash -c "$CMD" 2>/dev/null \
            || kitty --single-instance bash -c "$CMD" &
        echo "⚡ Agent Pulse launched in a new Kitty window."
        ;;
    wezterm)
        wezterm cli spawn --new-window -- bash -c "$CMD" 2>/dev/null \
            || wezterm start -- bash -c "$CMD" &
        echo "⚡ Agent Pulse launched in a new WezTerm window."
        ;;
    alacritty)
        alacritty -e bash -c "$CMD" &
        echo "⚡ Agent Pulse launched in a new Alacritty window."
        ;;
    warp)
        osascript -e "
            tell application \"Warp\"
                activate
            end tell
            tell application \"System Events\" to keystroke \"n\" using command down" &>/dev/null
        sleep 0.5
        osascript -e "tell application \"System Events\" to keystroke \"$CMD
\"" &>/dev/null
        echo "⚡ Agent Pulse launched in a new Warp window."
        ;;
    terminal)
        osascript -e "
            tell application \"Terminal\"
                activate
                do script \"$CMD\"
            end tell" &>/dev/null
        echo "⚡ Agent Pulse launched in a new Terminal window."
        ;;
    *)
        # Linux / fallback detection
        if command -v ghostty &>/dev/null; then
            ghostty -e bash -c "$CMD" &
            echo "⚡ Agent Pulse launched in a new Ghostty window."
        elif command -v kitty &>/dev/null; then
            kitty bash -c "$CMD" &
            echo "⚡ Agent Pulse launched in a new Kitty window."
        elif command -v wezterm &>/dev/null; then
            wezterm start -- bash -c "$CMD" &
            echo "⚡ Agent Pulse launched in a new WezTerm window."
        elif command -v alacritty &>/dev/null; then
            alacritty -e bash -c "$CMD" &
            echo "⚡ Agent Pulse launched in a new Alacritty window."
        elif command -v gnome-terminal &>/dev/null; then
            gnome-terminal -- bash -c "$CMD; exec bash" &
            echo "⚡ Agent Pulse launched in a new terminal window."
        elif command -v xterm &>/dev/null; then
            xterm -e bash -c "$CMD" &
            echo "⚡ Agent Pulse launched in xterm."
        else
            echo "⚠️  Could not detect terminal emulator — running in current terminal."
            exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${ARGS[@]}"
        fi
        ;;
esac
