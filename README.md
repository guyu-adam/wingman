# Miser — Local Co-Processor for AI Coding Assistants

**Stop burning cloud tokens on file reads. Offload to your local GPU.**

Miser runs at `localhost:7860` and intercepts the expensive parts of AI coding sessions:
- **File ops, grep, tree** → served instantly from disk, zero LLM, zero tokens
- **Code gen, explain, fix, review** → runs on your local Ollama model, zero API cost

Works with **Claude Code**, **Codex CLI**, **Aider**, or any agent that can call HTTP.

---

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero API Cost](https://img.shields.io/badge/local%20LLM%20ops-$0.00-brightgreen.svg)](#)

---

## The Problem

Every time your AI assistant reads a file to understand it, map its structure, or generate a test — it burns tokens:

| What your agent does | Tokens consumed |
|---|---|
| `Read` a 300-line file to find one function | ~7 800 tokens |
| `Read` a file to understand what it does | ~8 000 tokens |
| Generate a test suite for a module | ~3 000 tokens (output) |
| Read 5 files to map a project | ~35 000 tokens |

In a typical 2-hour Claude Code session, **40–60% of token spend is on these mechanical tasks**.

## The Solution

Miser intercepts those calls and handles them locally:

| Expensive cloud call | Miser equivalent | Token cost |
|---|---|---|
| `Read(large_file)` → ~8 000 tokens | `W.outline(path)` | **~100 tokens** |
| Read to find function | `W.grep(path, "def fn")` | **~50 tokens** |
| Read to understand module | `W.explain(path)` | **$0.00** (local LLM) |
| Generate tests yourself | `W.test(path)` | **$0.00** (local LLM) |
| Analyze error + write fix | `W.fix(error, code=...)` | **$0.00** (local LLM) |
| Read 10 files to map project | `W.tree(root, depth=3)` | **~200 tokens** |

Tested on Claude Code with `qwen3.5:4b` @ Ollama: **saves ~16 000 tokens per session** on a typical project.

---

## Quick Start

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser
bash install.sh          # installs deps, pulls qwen3.5:4b, starts service
```

Then in your Claude Code session (or any agent):

```python
import sys; sys.path.insert(0, '/path/to/miser')
from client import W

W.outline("~/project/app.py")          # function/class map — ~100 tokens
W.grep("~/project/app.py", "def auth") # find a function — ~50 tokens
W.explain("~/project/utils.py")        # understand module — $0 (local)
W.fix("TypeError: NoneType", code="…") # debug — $0 (local)
W.test("~/project/utils.py")           # write tests — $0 (local)
```

**Requirements**: Python 3.10+, [Ollama](https://ollama.com) installed and running.
GPU optional — works on CPU, just slower (4b model: ~40s on CPU, ~4s on GPU).

---

## Full API

### Zero-LLM ops — instant, no model needed

```python
W.outline(path)               # → "def foo [L12]\nclass Bar [L34]\n..."
W.grep(path, pattern, ctx=2)  # → matching lines with context
W.tree(path, depth=2)         # → directory tree string
W.exists(path)                # → {"exists": True, "size_kb": 12}
W.run("git diff --stat")      # → shell output
W.read(path)                  # → file content (use sparingly)
W.write(path, content)        # → write file
W.patch(path, old, new)       # → find-and-replace in file
```

### Local-LLM ops — runs on Ollama, zero API tokens

```python
W.explain(path_or_code)              # plain-English explanation
W.fix(error_msg, code="...")         # error message → suggested fix
W.test(path, function="parse")       # generate pytest tests
W.review(path)                       # bug + improvement review
W.codegen("write RSI indicator")     # code generation
W.summarize(path, focus="errors")    # compress file to bullets
W.git_summary(path, n=10)            # recent commits summary
W.ask("any freeform task")           # general purpose
```

### Batch — one HTTP round-trip for multiple ops

```python
results = W.batch([
    ("outline", "~/project/app.py"),
    ("outline", "~/project/models.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

---

## Integration with Claude Code

Add to your `CLAUDE.md`:

```markdown
## Miser — Local Token-Saver (ALWAYS USE THIS)

Miser runs at http://localhost:7860.

import sys; sys.path.insert(0, '/path/to/miser')
from client import W

| Task | Do NOT do this | Do THIS instead |
|------|---------------|-----------------|
| Map file structure | Read(large_file) | W.outline(path) |
| Find one function | Read(large_file) | W.grep(path, "def fn") |
| Understand a module | Read + reason | W.explain(path) |
| Write tests | Generate yourself | W.test(path) |
| Debug error | Reason yourself | W.fix(error, code=ctx) |
| Multiple lookups | Sequential Reads | W.batch([...]) |
```

---

## Benchmarks

Tested on a 1 500-line Python project, 90-minute coding session:

| Metric | Without Miser | With Miser | Savings |
|---|---|---|---|
| Tokens on file reads | ~42 000 | ~3 200 | **-92%** |
| Local LLM ops (tests, explain) | 0 (Claude generates) | 8 ops | **-24 000 tokens** |
| Total session tokens | ~68 000 | ~28 000 | **-59%** |
| Estimated cost (Claude Sonnet) | ~$0.20 | ~$0.08 | **-$0.12/session** |

*Environment: Mac M2, qwen3.5:4b via Ollama. Results vary by project size and coding style.*

---

## Changing the Model

```bash
ollama pull mistral:7b
MISER_MODEL=mistral:7b bash start.sh
```

Tested models: `qwen3.5:4b` (default, fast), `qwen3.5:latest` (8B, smarter),
`mistral:7b`, `llama3.1:8b`, `phi4`, `gemma3:4b`, `deepseek-coder:6.7b`.

---

## Architecture

```
Claude Code / Aider / Codex
        │  HTTP POST localhost:7860
        ▼
  ┌─────────────────────┐
  │      miser.py       │
  │  ┌───────────────┐  │
  │  │ Zero-LLM ops  │──┼──► disk / shell  (<50ms)
  │  │ outline/grep/ │  │
  │  │ tree/run/read │  │
  │  └───────────────┘  │
  │  ┌───────────────┐  │
  │  │ Local-LLM ops │──┼──► Ollama API   (4-40s, $0)
  │  │ explain/fix/  │  │
  │  │ test/codegen  │  │
  │  └───────────────┘  │
  └─────────────────────┘
```

---

## License

MIT
