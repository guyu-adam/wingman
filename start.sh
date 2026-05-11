#!/bin/bash
# Miser startup script.
# Usage:
#   bash start.sh                       # default model (miser-qwen)
#   MISER_MODEL=mistral:7b bash start.sh
#   bash start.sh --stop

set -euo pipefail

MISER_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=7860
MODEL="${MISER_MODEL:-miser-qwen}"
LOGFILE="/tmp/miser.log"
PIDFILE="/tmp/miser.pid"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }

# ── stop ──────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    if [[ -f "$PIDFILE" ]]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null && green "Miser stopped." || yellow "Already stopped."
        rm -f "$PIDFILE"
    else
        pkill -f "miser\.py" 2>/dev/null && green "Miser stopped." || yellow "Not running."
    fi
    exit 0
fi

# ── already running ───────────────────────────────────────────────────────────
if curl -sf "http://localhost:$PORT/status" >/dev/null 2>&1; then
    green "Miser already running on port $PORT."
    curl -s "http://localhost:$PORT/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  model={d[\"model\"]}  family={d.get(\"model_family\",\"?\")}  tasks={d[\"count\"]}  tokens_saved={d[\"tokens_saved_est\"]}')
"
    exit 0
fi

# ── ensure Ollama is running ──────────────────────────────────────────────────
if ! pgrep -x ollama >/dev/null 2>&1; then
    yellow "Starting Ollama..."
    OLLAMA_KEEP_ALIVE=-1 ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

# ── ensure miser-qwen model exists ───────────────────────────────────────────
if [[ "$MODEL" == "miser-qwen" ]]; then
    if ! ollama list 2>/dev/null | grep -q "miser-qwen"; then
        yellow "Creating miser-qwen model..."
        MF="$MISER_DIR/Modelfile.qwen3.5-4b"
        [[ ! -f "$MF" ]] && MF="$MISER_DIR/Modelfile.qwen3-4b"
        [[ ! -f "$MF" ]] && MF="$MISER_DIR/Modelfile.qwen2.5-4b"
        if [[ -f "$MF" ]]; then
            ollama create miser-qwen -f "$MF"
        else
            red "No Modelfile found — run: ollama pull qwen3.5:4b && ollama create miser-qwen -f Modelfile.qwen3.5-4b"
            exit 1
        fi
    fi
fi

# ── conda env (optional) ──────────────────────────────────────────────────────
START_CMD="python3 $MISER_DIR/miser.py"
if command -v conda &>/dev/null; then
    if conda env list 2>/dev/null | grep -qE "^miser\b"; then
        START_CMD="conda run -n miser python3 $MISER_DIR/miser.py"
    fi
fi

# ── launch ────────────────────────────────────────────────────────────────────
yellow "Starting Miser (model=$MODEL)..."
MISER_MODEL="$MODEL" $START_CMD > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

for i in $(seq 1 15); do
    sleep 1
    if curl -sf "http://localhost:$PORT/status" >/dev/null 2>&1; then
        green "Miser ready on http://localhost:$PORT"
        green "  Log: $LOGFILE  |  PID: $(cat $PIDFILE)"
        # Trigger LLM warmup in background (miser.py also does this, belt+suspenders)
        python3 -c "
import sys; sys.path.insert(0, '$MISER_DIR')
from client import W
try: W.ask('ok', max_tokens=1)
except: pass
" > /dev/null 2>&1 &
        exit 0
    fi
done

red "Miser failed to start — check $LOGFILE"
exit 1
