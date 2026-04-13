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

# Install Python deps
echo "  🐍 Installing dependencies..."
pip install --quiet -r requirements.txt 2>/dev/null || pip3 install --quiet -r requirements.txt

echo ""
echo "  ✅ Installed to $DEST"
echo ""
echo "  Run it:"
echo "    python3 $DEST/agent_pulse.py --live"
echo ""
echo "  Or use the launcher:"
echo "    $DEST/start.sh"
echo ""
