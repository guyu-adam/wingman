#!/usr/bin/env bash
# Miser v1.0 installer.
# Installs dependencies, pulls the model, registers a background service,
# and patches ~/.claude/CLAUDE.md so Claude Code uses Miser automatically.
#
# Usage:  bash install.sh
set -euo pipefail

MISER_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
bold()   { echo -e "\033[1m$*\033[0m"; }

bold "╔══════════════════════════════╗"
bold "║   Miser v1.0  —  Installer   ║"
bold "╚══════════════════════════════╝"
echo ""

# ── 1. Python check ───────────────────────────────────────────────────────────
PY_OK=$($PYTHON -c "import sys; print(sys.version_info >= (3,9))" 2>/dev/null || echo "False")
if [[ "$PY_OK" != "True" ]]; then
    red "✗ Python 3.9+ required (found: $($PYTHON --version 2>&1))"
    exit 1
fi
green "✓ $($PYTHON --version)"

# ── 2. Python dependencies ────────────────────────────────────────────────────
yellow "→ Installing Python dependencies..."
$PYTHON -m pip install --quiet flask requests numpy rich
green "✓ flask requests numpy rich"

# ── 3. Ollama check ───────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    red "✗ Ollama not found."
    echo "  Install from: https://ollama.com  then re-run: bash $MISER_DIR/install.sh"
    exit 1
fi
green "✓ Ollama $(ollama --version 2>/dev/null | head -1)"

# ── 4. Start Ollama if needed ─────────────────────────────────────────────────
if ! pgrep -x ollama >/dev/null 2>&1; then
    yellow "→ Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

# ── 5. Pull base model ────────────────────────────────────────────────────────
if ! ollama list 2>/dev/null | grep -q "qwen3.5:4b"; then
    yellow "→ Pulling qwen3.5:4b (~3.4 GB) — grab a coffee..."
    ollama pull qwen3.5:4b
fi
green "✓ qwen3.5:4b ready"

# ── 6. Create miser-qwen alias ────────────────────────────────────────────────
if ! ollama list 2>/dev/null | grep -q "miser-qwen"; then
    yellow "→ Creating miser-qwen model alias..."
    MF="$MISER_DIR/Modelfile.qwen3.5-4b"
    if [[ -f "$MF" ]]; then
        ollama create miser-qwen -f "$MF"
    else
        # inline minimal Modelfile
        ollama create miser-qwen -f <(printf "FROM qwen3.5:4b\nPARAMETER temperature 0.2\n")
    fi
fi
green "✓ miser-qwen alias ready"

# ── 7. System service ─────────────────────────────────────────────────────────
OS=$(uname -s)
if [[ "$OS" == "Darwin" ]]; then
    PLIST_DEST="$HOME/Library/LaunchAgents/com.miser.plist"
    sed "s|__MISER_DIR__|$MISER_DIR|g" "$MISER_DIR/com.miser.plist" > "$PLIST_DEST"
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    launchctl load "$PLIST_DEST"
    green "✓ macOS LaunchAgent installed — Miser starts automatically on login"
elif [[ "$OS" == "Linux" ]]; then
    SERVICE_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SERVICE_DIR"
    sed "s|__MISER_DIR__|$MISER_DIR|g" "$MISER_DIR/miser.service" > "$SERVICE_DIR/miser.service"
    systemctl --user daemon-reload
    systemctl --user enable miser
    systemctl --user start miser
    green "✓ systemd user service installed — Miser starts automatically on login"
else
    yellow "⚠ Windows: auto-start not yet supported. Run start.sh manually or on login."
fi

# ── 8. Patch ~/.claude/CLAUDE.md ─────────────────────────────────────────────
mkdir -p "$(dirname "$CLAUDE_MD")"
touch "$CLAUDE_MD"

if grep -q "<!-- miser-block -->" "$CLAUDE_MD" 2>/dev/null; then
    yellow "→ CLAUDE.md already patched, skipping"
else
    cat >> "$CLAUDE_MD" << MISER_EOF

<!-- miser-block -->
## Miser — Local Token-Saver (ALWAYS USE)

Miser runs at \`http://localhost:7860\`. Use it to avoid burning API tokens on
file ops and LLM tasks — it runs on your machine at zero cloud cost.

**Auto-start + LLM warmup** (paste at top of every session, or leave in CLAUDE.md):
\`\`\`python
import sys; sys.path.insert(0, '$MISER_DIR')
from client import W
try: W.status()
except:
    import subprocess, time
    subprocess.Popen(['bash', '$MISER_DIR/start.sh'],
                     stdout=open('/tmp/miser.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(5)
import threading
threading.Thread(target=lambda: W.ask('ok', max_tokens=1), daemon=True).start()
\`\`\`

**Decision rules — follow these strictly:**

| Task | Don't | Do instead |
|------|-------|------------|
| Map a file's structure | \`Read(large_file)\` | \`W.outline(path)\` — saves ~7 500 tokens |
| Find one function | \`Read(large_file)\` | \`W.grep(path, "def fn")\` — saves ~7 800 tokens |
| Project overview | Multiple \`Bash(ls)\` | \`W.tree(path, depth=2)\` |
| Check file exists | \`Bash(ls path)\` | \`W.exists(path)\` |
| Understand a module | Read + reason | \`W.explain(path)\` — 0 API tokens |
| Diagnose an error | Reason yourself | \`W.fix(error, code=ctx)\` — 0 API tokens |
| Write boilerplate / tests | Generate yourself | \`W.test(path)\` / \`W.codegen(task)\` — 0 API tokens |
| Multiple file lookups | Sequential Reads | \`W.batch([...])\` — one round-trip |

Full API: \`$MISER_DIR/MISER_FOR_CLAUDE.md\`
<!-- end-miser-block -->
MISER_EOF
    green "✓ Patched ~/.claude/CLAUDE.md with Miser decision rules"
fi

# ── 9. Start now ──────────────────────────────────────────────────────────────
yellow "→ Starting Miser..."
bash "$MISER_DIR/start.sh"

echo ""
bold "╔══════════════════════════════════════╗"
bold "║   Miser v1.0 installed successfully  ║"
bold "╚══════════════════════════════════════╝"
echo "  Server : http://localhost:7860"
echo "  Logs   : /tmp/miser.log"
echo "  Stop   : bash $MISER_DIR/start.sh --stop"
echo "  Remove : bash $MISER_DIR/uninstall.sh"
echo ""
yellow "Restart Claude Code — it will use Miser automatically from now on."
