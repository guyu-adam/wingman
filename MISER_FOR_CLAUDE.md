# Miser — Claude Code Usage Guide

Miser is a local co-processor running at `http://localhost:7860`.
Two classes of work — Claude Code spends fewer API tokens on both:

- **Zero-LLM ops** (<50ms): file ops, shell, grep, outline, tree — no model
- **Local-LLM ops** (15-40s): codegen, explain, fix, review, test, summarize — runs on your machine, 0 API tokens

## Quick health check

```python
import sys; sys.path.insert(0, '/path/to/miser')
from client import W
print(W.status())   # should show model=miser-qwen, status=IDLE
```

If the server is not running:
```bash
bash /path/to/miser/start.sh
```

---

## Decision rules

### Always use Miser instead of Read tool when:
- You need only the **function/class map** of a file → `W.outline(path)`
- You need to **find one function** in a large file → `W.grep(path, "def func_name")`
- You need a **directory overview** → `W.tree(path, depth=2)`
- You need to **check if a file exists** → `W.exists(path)`
- You need to **run a shell command** → `W.run("cmd")`

### Always use Miser instead of generating code yourself when:
- Writing **boilerplate** (tests, getters, parsers) → `W.codegen("task")`
- Explaining a **module you haven't read** → `W.explain(path)`
- Diagnosing an **error message** → `W.fix("error text", code="...")`
- Doing a **quick review** before suggesting changes → `W.review(path)`
- **Summarizing recent git work** → `W.git_summary(path, n=10)`

### Use batch for multiple lookups in one round-trip:
```python
results = W.batch([
    ("outline", "~/project/app.py"),
    ("outline", "~/project/models.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

---

## Token saving cheatsheet

| Instead of this (expensive) | Use this (cheap) |
|-----------------------------|-----------------|
| `Read("~/project/large.py")` → 8 000 tokens | `W.outline("~/project/large.py")` → ~100 tokens |
| Read file to find one function | `W.grep(path, "def target_fn")` → ~50 tokens |
| Read file to understand it | `W.explain(path)` → 0 API tokens |
| Write tests yourself | `W.test(path, function="fn")` → 0 API tokens |
| Analyze error + write fix | `W.fix(error, code=snippet)` → 0 API tokens |
| Read 10 files to map project | `W.tree(root, depth=3)` → ~200 tokens |

---

## Full API reference

```python
from client import W

# ── Zero-LLM (instant) ────────────────────────────────────────────────────────
W.outline("~/project/app.py")                    # function/class map
W.grep("~/project/app.py", "def process", ctx=3) # search with context
W.tree("~/project", depth=2)                     # directory tree
W.exists("~/project/.env")                       # existence + size
W.run("pytest --tb=short -q")                    # shell command
W.read("~/project/config.py")                    # read file (use sparingly)
W.write("~/project/out.py", "content")           # write file
W.patch("~/project/conf.py", "old", "new")       # find-and-replace

# ── Local-LLM (0 API tokens) ──────────────────────────────────────────────────
W.explain("~/project/utils.py")                  # plain-English explanation
W.fix("TypeError: None", code="...")             # error → fix
W.test("~/project/utils.py", function="parse")   # generate pytest tests
W.review("~/project/utils.py")                   # bugs + improvements
W.git_summary("~/project", n=10)                 # recent commits summary
W.summarize("~/project/big.py", focus="errors")  # compress to bullets
W.codegen("write RSI indicator in python")       # code generation
W.ask("any freeform task")                       # general purpose

# ── Batch (one HTTP round-trip) ───────────────────────────────────────────────
W.batch([
    ("outline", "~/project/app.py"),
    ("run",     "git diff --stat"),
    ("exists",  "~/project/.env"),
    ("ask",     "summarize the diff"),
])

# ── Memory ────────────────────────────────────────────────────────────────────
W.note("stack", "Python 3.11, FastAPI, PostgreSQL")
W.clear()   # reset conversation history
```

---

## Changing the model

```bash
ollama pull mistral:7b
MISER_MODEL=mistral:7b bash /path/to/miser/start.sh
```

Supported families: qwen3/3.5, qwen2.5, llama3.x, mistral, phi3/4, gemma3, deepseek-coder, deepseek-r1.
