# Wingman

**Local LLM co-processor for AI coding assistants.**

Runs a small Ollama model locally so Claude Code, Codex, Aider, or Cursor can delegate token-heavy subtasks without hitting the cloud API. Every file read, code explanation, grep, or unit-test generation that Wingman handles is one less billable Claude/GPT call.

```
Your AI coding assistant (Claude Code, Codex, Aider, Cursor)
              │  HTTP POST → localhost:7860
              ▼
         Wingman (Flask + Ollama)
              │
    ┌─────────┴────────────┐
    │ Zero-LLM (<50ms)     │  Local-LLM (no cloud)
    │ /grep /outline /tree │  /explain /fix /test
    │ /exists /write /patch│  /review /codegen
    │ /run /read           │  /summarize /git_summary
    └──────────────────────┘
```

## Why

| Task | Without Wingman | With Wingman | Saving |
|------|----------------|--------------|--------|
| Read 600-line file | ~8 000 tokens | — | — |
| `/outline` (function map) | — | ~400 tokens returned | **~7 600 tokens** |
| `/grep` (find one function) | — | ~130 tokens returned | **~7 870 tokens** |
| `/explain` a module | — | local LLM, 0 API tokens | **100%** |
| `/fix` an error | — | local LLM, 0 API tokens | **100%** |
| `/test` generate tests | — | local LLM, 0 API tokens | **100%** |

Zero-LLM endpoints respond in **<50ms**. Local-LLM endpoints use Ollama on your machine — no internet, no API key, no cost.

## Quick start

### 1. Install Ollama + pull a model

```bash
# https://ollama.com
ollama pull qwen3.5:4b        # 3.4 GB — recommended (latest, Apple Silicon)
# or
ollama pull qwen2.5:4b        # also supported

ollama create wingman-qwen -f Modelfile.qwen3.5-4b

# Semantic memory (optional)
ollama pull nomic-embed-text
```

### 2. Start Wingman

```bash
pip install flask requests numpy rich
python main.py
# Server at http://localhost:7860
```

### 3. Use from Claude Code (or any script)

```python
import sys; sys.path.insert(0, '/path/to/wingman')
from client import W   # W for Wingman  (J also works for backward compat)

# ── Zero-LLM (instant) ────────────────────────────────────────────────────
W.outline("~/project/app.py")              # function/class map
W.grep("~/project/app.py", "def process") # search with context
W.tree("~/project", depth=2)              # directory tree
W.exists("~/project/.env")                # existence check
W.write("~/project/config.py", "KEY=1")   # write file
W.patch("~/project/config.py", "1", "2")  # find-and-replace
W.run("pytest --tb=short -q")             # shell command

# ── Local-LLM (no API cost) ───────────────────────────────────────────────
W.explain("~/project/utils.py")            # plain-English explanation
W.fix("TypeError: NoneType", code="...")   # error → fix suggestion
W.test("~/project/utils.py", function="parse_csv")  # generate tests
W.review("~/project/utils.py")            # bugs + improvements
W.git_summary("~/project", n=10)          # recent commits in plain English
W.summarize("~/project/big_file.py", focus="error handling")
W.codegen("write a function to debounce async calls")

# ── Batch (one HTTP round-trip) ───────────────────────────────────────────
W.batch([
    ("outline", "~/project/app.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

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
| `GET  /status` | — | `{model, tokens_saved_est, ...}` |

## Supported models

| Modelfile | Base | Size | Notes |
|-----------|------|------|-------|
| `Modelfile.qwen3.5-4b` | qwen3.5:4b | 3.4 GB | **Default** — latest Qwen, Apple Silicon |
| `Modelfile.qwen2.5-4b` | qwen2.5:4b | 2.5 GB | Lighter alternative |
| `Modelfile.qwen3-8b` | qwen3:8b | 5.2 GB | Higher quality, 2× slower |
| `Modelfile.gemma3-4b` | gemma3:4b | 3.3 GB | Fallback |

```bash
# Switch model:
ollama create wingman-qwen -f Modelfile.qwen2.5-4b
# restart main.py — MODEL = "wingman-qwen" stays the same
```

## Benchmark (Apple M-series, qwen3.5:4b)

```
Zero-LLM ops:   8 endpoints   avg latency  <50ms   ✓ all pass
Local-LLM ops:  9 endpoints   avg latency  15–40s  ✓ all pass

Token saving per /outline call:     ~7 600 tokens
Token saving per /grep call:        ~7 870 tokens
Estimated savings per session:      20 000–50 000 tokens
```

Local-LLM endpoints are slower (15–40s on 4b models) due to chain-of-thought reasoning. Use them for background tasks, not interactive queries.

## Integration examples

**Claude Code hook** — add to your CLAUDE.md:
```
When reading large files, prefer W.outline() or W.grep() via Wingman
instead of Read tool to save context tokens.
```

**Aider / Cursor** — add to your system prompt or wrapper script:
```python
from client import W
W.explain("path/to/confusing_module.py")  # before asking Aider to modify it
```

## Memory

Wingman stores conversation history with semantic embeddings (`nomic-embed-text`). Relevant past context is injected into `/ask` and `/summarize` calls automatically.

```python
W.note("project_lang", "Python 3.11, FastAPI")   # persist facts
W.clear()                                          # reset history
```

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) running locally
- `pip install flask requests numpy rich`

## License

MIT
