#!/bin/bash
# Agent Pulse — Quick launcher
#
# Default: opens the live dashboard in a new window of your current terminal
#          emulator (auto-detects Ghostty, iTerm, Kitty, WezTerm, Alacritty,
#          Warp, Terminal.app, tmux, gnome-terminal, xterm).
#
# Use --here to run in the current terminal instead (useful over SSH,
# inside tmux panes, or when you don't want a new window).

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

# Install deps if needed
if ! "$VENV/bin/python" -c "import textual" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    "$VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
fi

# If --here, or already inside a spawned child terminal, run directly.
if [ "$RUN_HERE" = "1" ] || [ "$AGENT_PULSE_SPAWNED" = "1" ]; then
    exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${PASSTHROUGH_ARGS[@]}"
fi

# --- Otherwise, spawn in a new window/pane of the user's terminal emulator ---
CMD="export AGENT_PULSE_SPAWNED=1; cd '$SCRIPT_DIR' && '$VENV/bin/python' '$SCRIPT_DIR/agent_pulse.py' ${PASSTHROUGH_ARGS[*]}"

# tmux — open a new window in the current session
if [ -n "$TMUX" ]; then
    tmux new-window -n "AgentPulse" "bash -c '$CMD'"
    echo "⚡ Agent Pulse launched in a new tmux window."
    exit 0
fi

# Detect the frontmost terminal emulator on macOS
TERM_APP=""
if [ "$(uname)" = "Darwin" ]; then
    TERM_BUNDLE=$(osascript -e 'tell application "System Events" to get bundle identifier of (first process whose frontmost is true)' 2>/dev/null)
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
        # Linux / unknown — fall back through common emulators by availability
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
        elif command -v osascript &>/dev/null; then
            # macOS last-resort: use Terminal.app
            osascript -e "
                tell application \"Terminal\"
                    activate
                    do script \"$CMD\"
                end tell" &>/dev/null
            echo "⚡ Agent Pulse launched in a new Terminal window."
        else
            echo "⚠️  Could not detect a terminal emulator — running in the current terminal."
            echo "    (Tip: pass --here to always run in place.)"
            exec "$VENV/bin/python" "$SCRIPT_DIR/agent_pulse.py" "${PASSTHROUGH_ARGS[@]}"
        fi
        ;;
esac
