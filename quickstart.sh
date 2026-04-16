#!/usr/bin/env bash
# ⚡ Agent Pulse — One-command installer
# https://github.com/DUBSOpenHub/copilot-cli-agent-pulse
set -euo pipefail

DEST="$HOME/copilot-cli-agent-pulse"

echo ""
echo "  ⚡ Agent Pulse — Quick Installer"
echo "  ─────────────────────────────────"
echo ""

# Clone or update
if [ -d "$DEST" ]; then
  echo "  📂 Updating existing install..."
  cd "$DEST" && git pull --quiet
else
  echo "  📦 Cloning repository..."
  git clone --quiet https://github.com/DUBSOpenHub/copilot-cli-agent-pulse.git "$DEST"
  cd "$DEST"
fi

# Create/reuse virtual environment and install deps
VENV="$DEST/.venv"
if [ ! -d "$VENV" ]; then
  echo "  🐍 Creating virtual environment..."
  python3 -m venv "$VENV"
fi

echo "  📦 Installing dependencies..."
"$VENV/bin/pip" install --quiet -r requirements.txt

echo ""
echo "  ✅ Installed to $DEST"
echo ""

# Auto-add shell aliases if not already present
FISH_CONFIG="$HOME/.config/fish/config.fish"
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
  SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
  SHELL_RC="$HOME/.bashrc"
fi

ALIASES_ADDED=0

# bash/zsh aliases
if [ -n "$SHELL_RC" ] && ! grep -q 'alias agentpulse=' "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# Agent Pulse — auto-opens live dashboard in a new terminal window" >> "$SHELL_RC"
  echo "alias agentpulse='~/copilot-cli-agent-pulse/start.sh'" >> "$SHELL_RC"
  echo "alias agentdashboard='~/copilot-cli-agent-pulse/start.sh'" >> "$SHELL_RC"
  echo "  🔗 Added 'agentpulse' and 'agentdashboard' aliases to $(basename "$SHELL_RC")"
  ALIASES_ADDED=1
fi

# fish aliases
if [ -f "$FISH_CONFIG" ] || echo "$SHELL" | grep -q fish; then
  mkdir -p "$(dirname "$FISH_CONFIG")"
  if ! grep -q 'alias agentpulse' "$FISH_CONFIG" 2>/dev/null; then
    echo "" >> "$FISH_CONFIG"
    echo "# Agent Pulse — auto-opens live dashboard in a new terminal window" >> "$FISH_CONFIG"
    echo "alias agentpulse '~/copilot-cli-agent-pulse/start.sh'" >> "$FISH_CONFIG"
    echo "alias agentdashboard '~/copilot-cli-agent-pulse/start.sh'" >> "$FISH_CONFIG"
    echo "  🔗 Added 'agentpulse' and 'agentdashboard' aliases to config.fish"
    ALIASES_ADDED=1
  fi
fi

if [ "$ALIASES_ADDED" -eq 0 ]; then
  echo "  🔗 Aliases already configured."
fi

echo ""
echo "  Launch it (opens in a new terminal window):"
echo "    agentpulse"
echo "    agentdashboard"
echo ""
echo "  Or run directly:"
echo "    $DEST/start.sh"
echo ""
