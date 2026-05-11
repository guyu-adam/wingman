# Wingman

**Local LLM co-processor for AI coding assistants.**

Runs a small Ollama model locally so Claude Code, Codex, Aider, or Cursor can delegate token-heavy subtasks without hitting the cloud API. Every file outline, code explanation, grep, or unit-test generation that Wingman handles is one less billable API call.

```
Your AI assistant (Claude Code / Codex / Aider / Cursor)
              │  HTTP POST → localhost:7860
              ▼
         Wingman v1.1 (Flask + Ollama)
              │
    ┌─────────┴────────────┐
    │ Zero-LLM (<50ms)     │  Local-LLM (0 API tokens)
    │ /grep /outline /tree │  /explain /fix /test /review
    │ /exists /write /patch│  /codegen /summarize /git_summary
    │ /run /read           │  /ask /batch
    └──────────────────────┘
```

## Why

| Task | Without Wingman | With Wingman | Saving |
|------|----------------|--------------|--------|
| Map a 600-line file | ~8 000 tokens | `W.outline()` → ~100 tokens | **~7 900 tokens** |
| Find one function | ~8 000 tokens | `W.grep()` → ~50 tokens | **~7 950 tokens** |
| Explain a module | ~8 000 tokens (read+reason) | `W.explain()` → 0 API tokens | **100%** |
| Generate unit tests | ~500 tokens (output) | `W.test()` → 0 API tokens | **100%** |
| Fix an error | ~300 tokens | `W.fix()` → 0 API tokens | **100%** |

Zero-LLM endpoints respond in **<50ms**. Local-LLM endpoints use Ollama on your machine — no internet, no API key, no billing.

## Quick start

### 1. Install Ollama + pull a model

```bash
# https://ollama.com
ollama pull qwen3.5:4b        # 3.4 GB — recommended (Apple Silicon, latest Qwen)

# Create the wingman-qwen alias (keeps server config stable across model upgrades)
ollama create wingman-qwen -f Modelfile.qwen3.5-4b

# Optional: semantic memory
ollama pull nomic-embed-text
```

### 2. Start Wingman

```bash
pip install flask requests numpy rich
bash start.sh                     # auto-detects conda env, starts Ollama if needed
# or manually:
python main.py
```

### 3. Use from Claude Code (or any script)

```python
import sys; sys.path.insert(0, '/path/to/wingman')
from client import W   # W for Wingman  (J also works for backward compat)

# ── Zero-LLM (instant) ────────────────────────────────────────────────────────
W.outline("~/project/app.py")                    # function/class map
W.grep("~/project/app.py", "def process", ctx=3) # search with context
W.tree("~/project", depth=2)                     # directory tree
W.exists("~/project/.env")                       # existence check
W.write("~/project/config.py", "KEY=1")          # write file
W.patch("~/project/config.py", "1", "2")         # find-and-replace
W.run("pytest --tb=short -q")                    # shell command

# ── Local-LLM (0 API tokens) ──────────────────────────────────────────────────
W.explain("~/project/utils.py")                  # plain-English explanation
W.fix("TypeError: NoneType", code="...")         # error → fix suggestion
W.test("~/project/utils.py", function="parse")   # generate pytest tests
W.review("~/project/utils.py")                   # bugs + improvements
W.git_summary("~/project", n=10)                 # recent commits in plain English
W.summarize("~/project/big_file.py", focus="error handling")
W.codegen("write a debounce function in python")

# ── Batch (one HTTP round-trip) ───────────────────────────────────────────────
W.batch([
    ("outline", "~/project/app.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

## Auto-start with Claude Code

Add this to your `CLAUDE.md` so Wingman starts automatically:

```python
import sys; sys.path.insert(0, '/path/to/wingman')
from client import W
try:
    W.status()
except Exception:
    import subprocess, time
    subprocess.Popen(['bash', '/path/to/wingman/start.sh'])
    time.sleep(4)
```

See `WINGMAN_FOR_CLAUDE.md` for the full decision-rule cheatsheet.

## Supported models

| Modelfile | Base | Size | Notes |
|-----------|------|------|-------|
| `Modelfile.qwen3.5-4b` | qwen3.5:4b | 3.4 GB | **Default** — latest Qwen, Apple Silicon |
| `Modelfile.qwen2.5-4b` | qwen2.5:4b | 2.5 GB | Lighter, no thinking mode |
| `Modelfile.qwen3-8b`   | qwen3:8b   | 5.2 GB | Higher quality, 2× slower |
| `Modelfile.gemma3-4b`  | gemma3:4b  | 3.3 GB | Google, good for English prose |

### Other supported model families (no custom Modelfile needed)

```bash
# Switch to any of these — model_adapter.py auto-detects format:
WINGMAN_MODEL=mistral:7b       bash start.sh   # Mistral [INST] format
WINGMAN_MODEL=llama3.1:8b      bash start.sh   # Llama3 ChatML
WINGMAN_MODEL=phi4:latest      bash start.sh   # Phi4 format
WINGMAN_MODEL=deepseek-coder:6.7b bash start.sh # DeepSeek code specialist
WINGMAN_MODEL=gemma3:4b        bash start.sh   # Gemma turns format
```

`model_adapter.py` handles prompt formatting, thinking-mode suppression, and response extraction for each family automatically.

## Endpoint reference

### Zero-LLM — instant, no model

| Endpoint | Input | Output |
|----------|-------|--------|
| `POST /run` | `{cmd, timeout}` | `{output}` |
| `POST /read` | `{path, limit}` | `{content}` |
| `POST /grep` | `{path, pattern, context}` | `{matches}` |
| `POST /outline` | `{path}` | `{outline}` |
| `POST /tree` | `{path, depth}` | `{tree}` |
| `POST /exists` | `{path}` | `{exists, is_file, size}` |
| `POST /write` | `{path, content}` | `{result}` |
| `POST /patch` | `{path, old, new}` | `{result}` |

### Local-LLM — Ollama, no cloud API

| Endpoint | Input | Output |
|----------|-------|--------|
| `POST /explain` | `{path}` or `{code}` | `{explanation}` |
| `POST /fix` | `{error, code}` | `{fix}` |
| `POST /test` | `{path, function}` or `{code}` | `{tests}` |
| `POST /review` | `{path}` or `{code}` | `{review}` |
| `POST /git_summary` | `{path, n}` | `{summary}` |
| `POST /ask` | `{task, max_tokens}` | `{result}` |
| `POST /summarize` | `{path, focus}` | `{summary}` |
| `POST /codegen` | `{task, lang}` | `{code}` |
| `POST /batch` | `{tasks:[...]}` | `{results:[...]}` |
| `GET  /status` | — | `{model, family, tokens_saved_est, ...}` |

## Benchmark (Apple M-series, qwen3.5:4b)

```
Zero-LLM ops:   8 endpoints   avg latency  <50ms    ✓
Local-LLM ops:  9 endpoints   avg latency  11-19s   ✓

Token saving per /outline call:     ~7 900 tokens
Token saving per /grep call:        ~7 950 tokens
Estimated savings per session:      20 000–50 000 tokens
```

## Memory

Wingman stores conversation history with semantic embeddings (`nomic-embed-text`). Relevant past context is injected into `/ask` calls automatically.

```python
W.note("project_lang", "Python 3.11, FastAPI")
W.clear()   # reset history
```

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) running locally
- `pip install flask requests numpy rich`

## License

MIT
