#!/usr/bin/env bash
# Miser uninstaller — removes service, CLAUDE.md patch, and pid/log files.
# Ollama models are kept (remove manually with: ollama rm miser-qwen)
set -euo pipefail

MISER_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }

echo "=== Miser Uninstaller ==="

# Stop server
bash "$MISER_DIR/start.sh" --stop 2>/dev/null || true

# macOS LaunchAgent
PLIST="$HOME/Library/LaunchAgents/com.miser.plist"
if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    green "✓ Removed macOS LaunchAgent"
fi

# Linux systemd
SERVICE="$HOME/.config/systemd/user/miser.service"
if [[ -f "$SERVICE" ]]; then
    systemctl --user stop miser 2>/dev/null || true
    systemctl --user disable miser 2>/dev/null || true
    rm -f "$SERVICE"
    systemctl --user daemon-reload 2>/dev/null || true
    green "✓ Removed systemd service"
fi

# CLAUDE.md patch
if [[ -f "$CLAUDE_MD" ]] && grep -q "miser-block" "$CLAUDE_MD"; then
    python3 - "$CLAUDE_MD" << 'PYEOF'
import sys, re
path = sys.argv[1]
text = open(path).read()
cleaned = re.sub(r'\n<!-- miser-block -->.*?<!-- end-miser-block -->', '', text, flags=re.DOTALL)
open(path, 'w').write(cleaned.rstrip('\n') + '\n')
PYEOF
    green "✓ Removed Miser block from ~/.claude/CLAUDE.md"
fi

rm -f /tmp/miser.log /tmp/miser.pid
green "✓ Miser removed."
yellow "  Ollama models kept — to remove: ollama rm miser-qwen"
