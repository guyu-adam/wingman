# Miser

**Local LLM token-saver for Claude Code.**

One command installs everything. After that, every Claude Code session automatically offloads file ops and code tasks to a local Ollama model — zero cloud API tokens spent on things that don't need them.

## Install

```bash
git clone https://github.com/guyu-adam/miser
bash miser/install.sh
```

`install.sh` will:
1. Install Python dependencies (`flask requests numpy rich`)
2. Pull `qwen3.5:4b` if not present (~3.4 GB, one-time)
3. Register a background service — auto-starts on login, auto-restarts on crash
4. Patch `~/.claude/CLAUDE.md` so Claude Code uses Miser automatically in every project

> **Requirements:** Python 3.9+, [Ollama](https://ollama.com), ~4 GB free RAM, macOS or Linux

---

## What it saves

| Task | Without Miser | With Miser | Saving |
|------|--------------|------------|--------|
| Map a 600-line file | ~8 000 tokens | `W.outline()` → ~100 tokens | **~7 900** |
| Find one function | ~8 000 tokens | `W.grep()` → ~50 tokens | **~7 950** |
| Explain a module | ~8 000 tokens | `W.explain()` → 0 API tokens | **100%** |
| Generate unit tests | ~500 tokens | `W.test()` → 0 API tokens | **100%** |
| Fix an error | ~300 tokens | `W.fix()` → 0 API tokens | **100%** |

Zero-LLM endpoints respond in **<50ms**. Local-LLM endpoints use Ollama — no internet, no API key, no billing.

---

## How it works

```
Claude Code (or any AI coding tool)
        │  HTTP POST → localhost:7860
        ▼
     Miser  (Flask + Ollama)
        │
┌───────┴──────────────────────┐
│ Zero-LLM  (<50ms)            │  Local-LLM  (0 API tokens)
│ /grep  /outline  /tree       │  /explain  /fix  /test  /review
│ /exists  /write  /patch      │  /codegen  /summarize  /ask
│ /run  /read                  │  /git_summary  /batch
└──────────────────────────────┘
```

After `install.sh` runs, Claude Code reads the decision rules injected into `~/.claude/CLAUDE.md` and routes tasks automatically.

---

## Usage (once installed)

```python
import sys; sys.path.insert(0, '/path/to/miser')
from client import W

# Zero-LLM — instant
W.outline("~/project/app.py")                    # function/class map
W.grep("~/project/app.py", "def process", ctx=3) # search with context
W.tree("~/project", depth=2)                     # directory tree
W.exists("~/project/.env")                       # existence check
W.run("pytest --tb=short -q")                    # shell command

# Local-LLM — 0 API tokens
W.explain("~/project/utils.py")                  # plain-English explanation
W.fix("TypeError: NoneType", code="...")         # error → fix suggestion
W.test("~/project/utils.py", function="parse")   # generate pytest tests
W.review("~/project/utils.py")                   # bugs + improvements
W.git_summary("~/project", n=10)                 # recent commits summary
W.codegen("write a debounce function in python") # code generation

# Batch — one round-trip
W.batch([
    ("outline", "~/project/app.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

---

## Supported models

| Modelfile | Base | Size | Notes |
|-----------|------|------|-------|
| `Modelfile.qwen3.5-4b` | qwen3.5:4b | 3.4 GB | **Default** — Apple Silicon optimised |
| `Modelfile.qwen2.5-4b` | qwen2.5:4b | 2.5 GB | Lighter, no thinking mode |
| `Modelfile.qwen3-8b`   | qwen3:8b   | 5.2 GB | Higher quality, 2× slower |
| `Modelfile.gemma3-4b`  | gemma3:4b  | 3.3 GB | Good for English prose |

Switch model at any time:

```bash
MISER_MODEL=mistral:7b bash start.sh
```

`model_adapter.py` auto-detects prompt format and thinking-mode suppression for: qwen3/3.5, qwen2.5, llama3.x, mistral, phi3/4, gemma3, deepseek-coder, deepseek-r1.

---

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

---

## Uninstall

```bash
bash /path/to/miser/uninstall.sh
```

Removes the background service and the `~/.claude/CLAUDE.md` patch. Ollama models are kept.

---

## Memory

Miser stores conversation history with semantic embeddings (`nomic-embed-text`). Relevant past context is injected into `/ask` calls automatically.

```python
W.note("project_lang", "Python 3.11, FastAPI")
W.clear()   # reset history
```

---

## Requirements

- Python 3.9+
- [Ollama](https://ollama.com) running locally
- `pip install flask requests numpy rich`
- macOS or Linux (Windows: manual start only)

## License

MIT
