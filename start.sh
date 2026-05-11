#!/bin/bash
# Wingman startup script — run this once before / alongside Claude Code.
# Starts Ollama (if not running) and the Wingman Flask server.
#
# Usage:
#   bash ~/Desktop/wingman/start.sh           # default model (wingman-qwen)
#   WINGMAN_MODEL=mistral:7b bash start.sh    # override model
#   bash start.sh --stop                      # kill server

set -euo pipefail

WINGMAN_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=7860
MODEL="${WINGMAN_MODEL:-wingman-qwen}"
LOGFILE="/tmp/wingman.log"
PIDFILE="/tmp/wingman.pid"

# ── helpers ───────────────────────────────────────────────────────────────────
green() { echo -e "\033[32m$*\033[0m"; }
yellow(){ echo -e "\033[33m$*\033[0m"; }
red()   { echo -e "\033[31m$*\033[0m"; }

# ── stop mode ─────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    if [[ -f "$PIDFILE" ]]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null && green "Wingman stopped." || yellow "Already stopped."
        rm -f "$PIDFILE"
    else
        pkill -f wingman.py 2>/dev/null && green "Wingman stopped." || yellow "Not running."
    fi
    exit 0
fi

# ── check already running ────────────────────────────────────────────────────
if curl -sf "http://localhost:$PORT/status" >/dev/null 2>&1; then
    green "Wingman already running on port $PORT."
    curl -s "http://localhost:$PORT/status" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'  model={d[\"model\"]}  family={d.get(\"model_family\",\"?\")}  tasks={d[\"count\"]}  tokens_saved={d[\"tokens_saved_est\"]}')
"
    exit 0
fi

# ── ensure Ollama is running ──────────────────────────────────────────────────
if ! pgrep -x ollama >/dev/null 2>&1; then
    yellow "Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 2
fi

# ── ensure wingman-qwen model exists ─────────────────────────────────────────
if [[ "$MODEL" == "wingman-qwen" ]]; then
    if ! ollama list 2>/dev/null | grep -q "wingman-qwen"; then
        yellow "Creating wingman-qwen model..."
        # prefer newest Modelfile
        MF="$WINGMAN_DIR/Modelfile.qwen3.5-4b"
        [[ ! -f "$MF" ]] && MF="$WINGMAN_DIR/Modelfile.qwen3-4b"
        [[ ! -f "$MF" ]] && MF="$WINGMAN_DIR/Modelfile.qwen2.5-4b"
        if [[ -f "$MF" ]]; then
            ollama create wingman-qwen -f "$MF"
        else
            red "No Modelfile found in $WINGMAN_DIR — run: ollama pull qwen3.5:4b && ollama create wingman-qwen -f Modelfile.qwen3.5-4b"
            exit 1
        fi
    fi
fi

# ── activate conda env if available ──────────────────────────────────────────
START_CMD="python3 $WINGMAN_DIR/wingman.py"

if command -v conda &>/dev/null; then
    if conda env list 2>/dev/null | grep -q "^wingman\|^jarves"; then
        ENV=$(conda env list 2>/dev/null | grep -E "^wingman|^jarves" | awk '{print $1}' | head -1)
        START_CMD="conda run -n $ENV python3 $WINGMAN_DIR/wingman.py"
    fi
fi

# ── launch ────────────────────────────────────────────────────────────────────
yellow "Starting Wingman (model=$MODEL)..."
WINGMAN_MODEL="$MODEL" $START_CMD > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

# wait for ready
for i in $(seq 1 15); do
    sleep 1
    if curl -sf "http://localhost:$PORT/status" >/dev/null 2>&1; then
        green "Wingman ready on http://localhost:$PORT"
        green "  Log: $LOGFILE"
        green "  PID: $(cat $PIDFILE)"
        exit 0
    fi
done

red "Wingman failed to start — check $LOGFILE"
exit 1
