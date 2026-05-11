"""
Miser v1.0 — Claude Code's local co-processor.
Two execution paths:
  1. Zero-LLM (<50ms): shell, file read/write/grep/tree/exists/outline/patch
  2. Local LLM (no API cost): summarize, codegen, explain, fix, test, review, git_summary
"""

import os, json, threading, time, re, subprocess, math, fnmatch
from datetime import datetime
from pathlib import Path

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

import requests as req
from flask import Flask, request, jsonify
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from model_adapter import ModelAdapter

console = Console()
app = Flask(__name__)

MEMORY_FILE = Path(__file__).parent / "memory.json"
EMBED_FILE  = Path(__file__).parent / "embeddings.json"
EMBED_URL   = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
MODEL       = os.environ.get("MISER_MODEL", "miser-qwen")

adapter = ModelAdapter(MODEL)

_tokens_saved = 0
def _count_saved(chars: int):
    global _tokens_saved
    _tokens_saved += int(chars / 4)   # ~4 chars per token for code/English

# ── memory ─────────────────────────────────────────────────────────────────────

class Memory:
    def __init__(self):
        self.notes: dict = {}
        self.history: list = []
        self.embeddings: list = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                d = json.loads(MEMORY_FILE.read_text())
                self.notes   = d.get("notes", {})
                self.history = d.get("history", [])
            except Exception:
                pass
        if EMBED_FILE.exists():
            try:
                self.embeddings = json.loads(EMBED_FILE.read_text())
            except Exception:
                pass

    def _save(self):
        MEMORY_FILE.write_text(json.dumps(
            {"notes": self.notes, "history": self.history[-40:]},
            ensure_ascii=False, indent=2
        ))

    def _save_embeddings(self):
        EMBED_FILE.write_text(json.dumps(self.embeddings[-40:], ensure_ascii=False))

    def _embed(self, text: str) -> list:
        try:
            r = req.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=10)
            return r.json().get("embedding", [])
        except Exception:
            return []

    def _cosine(self, a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    def clear(self):
        with self._lock:
            self.history = []
            self.embeddings = []
            self._save()
            if EMBED_FILE.exists():
                EMBED_FILE.unlink()

    def save(self, key: str, val: str):
        with self._lock:
            self._load()
            self.notes[key] = val
            self._save()

    def record(self, tid: int, task: str, result: str):
        with self._lock:
            self._load()
            self.history.append({
                "id": tid,
                "time": datetime.now().strftime("%m-%d %H:%M"),
                "task": task[:100],
                "result": result[:200],
            })
            self._save()
        def _do_embed():
            emb = self._embed(task)
            if emb:
                with self._lock:
                    self.embeddings.append({
                        "id": tid, "task": task[:100],
                        "result": result[:200], "emb": emb
                    })
                    self._save_embeddings()
        threading.Thread(target=_do_embed, daemon=True).start()

    def ctx(self, current_task: str = "") -> str:
        out = []
        if self.notes:
            out.append("Notes: " + " | ".join(f"{k}={v}" for k, v in list(self.notes.items())[-6:]))
        if not self.history:
            return "\n".join(out)
        if current_task and self.embeddings:
            q_emb = self._embed(current_task)
            if q_emb:
                scored = sorted(
                    self.embeddings, key=lambda e: self._cosine(q_emb, e["emb"]), reverse=True
                )[:3]
                out.append("Relevant: " + " | ".join(
                    f"#{e['id']} \"{e['task'][:50]}\"→{e['result'][:60]}" for e in scored
                ))
                return "\n".join(out)
        out.append("Recent: " + " | ".join(
            f"#{h['id']} \"{h['task'][:50]}\"→{h['result'][:60]}"
            for h in self.history[-3:]
        ))
        return "\n".join(out)

mem = Memory()

# ── state ───────────────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.status = "IDLE"
        self.task   = "—"
        self.result = ""
        self.count  = 0
        self._lock  = threading.Lock()
    def set(self, status, task=None):
        with self._lock:
            self.status = status
            if task is not None: self.task = task

st = State()

# ── deterministic tools (zero LLM cost) ────────────────────────────────────────

def _shell(cmd: str, timeout: int = 30) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return (r.stdout + r.stderr).strip() or "(no output)"

def _read(path: str, limit: int = 8000) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    return text[:limit] + (f"\n...[truncated, total {len(text)} chars]" if len(text) > limit else "")

def _ls(path: str, pattern: str = "*") -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"Path not found: {path}"
    items = sorted(p.glob(pattern))
    return "\n".join(
        f"{'[dir]' if i.is_dir() else '[file]'} {i.name}  ({i.stat().st_size//1024}KB)"
        for i in items
    ) or "(empty)"

def _grep_file(path: str, pattern: str, context: int = 2, ignore_case: bool = True) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    lines = p.read_text(errors="replace").splitlines()
    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return f"Invalid pattern: {e}"
    matches = []
    seen = set()
    for i, line in enumerate(lines):
        if rx.search(line):
            start = max(0, i - context)
            end   = min(len(lines), i + context + 1)
            for j in range(start, end):
                if j not in seen:
                    seen.add(j)
                    matches.append(f"{j+1:4d}  {lines[j]}")
            matches.append("---")
    return "\n".join(matches).rstrip("---").strip() or f"No matches for: {pattern}"

def _tree(path: str, depth: int = 2, exclude: str = "__pycache__,.git,node_modules,.DS_Store") -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"Path not found: {path}"
    excl = set(exclude.split(","))
    lines = [str(p)]
    def _walk(d: Path, prefix: str, level: int):
        if level > depth:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in excl]
        for i, e in enumerate(entries):
            is_last = i == len(entries) - 1
            conn = "└── " if is_last else "├── "
            size = f" ({e.stat().st_size//1024}KB)" if e.is_file() else ""
            lines.append(f"{prefix}{conn}{e.name}{size}")
            if e.is_dir() and level < depth:
                ext = "    " if is_last else "│   "
                _walk(e, prefix + ext, level + 1)
    _walk(p, "", 1)
    return "\n".join(lines)

def _outline(path: str) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    lines = text.splitlines()
    results = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(def |class |async def )(\w+)", line)
        if m:
            indent = len(m.group(1)) // 4
            kind   = m.group(2).strip()
            name   = m.group(3)
            doc = ""
            if i + 1 < len(lines):
                dl = lines[i + 1].strip()
                if dl.startswith('"""') or dl.startswith("'''"):
                    doc = " — " + dl.strip('"\' ')[:60]
            results.append(f"{'  ' * indent}{kind} {name}{doc}  [L{i+1}]")
    return "\n".join(results) or "(no functions/classes found)"

def _write_file(path: str, content: str) -> str:
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written {len(content)} chars to {path}"

def _patch_file(path: str, old: str, new: str) -> str:
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(errors="replace")
    count = text.count(old)
    if count == 0:
        return f"Pattern not found in {path}"
    updated = text.replace(old, new, 1)
    p.write_text(updated)
    return f"Patched {path}: replaced 1/{count} occurrence(s), {len(old)}→{len(new)} chars"

# ── LLM call ────────────────────────────────────────────────────────────────────

def llm(task: str, system: str = "", max_tokens: int = 600, mode: str = "text") -> str:
    is_code    = mode == "code"    or re.search(r'\b(write|def|function|code|implement|class)\b', task, re.I)
    is_bullets = mode == "bullets" or re.search(r'\b(summarize|bullet|list|summary|points)\b', task, re.I)
    detected_mode = "code" if is_code and not is_bullets else ("bullets" if is_bullets else "text")

    sys_prompt = "You are Miser, Claude Code's local assistant.\nOutput ONLY the final answer, no preamble.\n"
    if detected_mode == "text":
        ctx_text = mem.ctx(task)
        if ctx_text:
            sys_prompt += f"Context: {ctx_text}\n"
    if system:
        sys_prompt += system

    payload = adapter.generate_payload(sys_prompt, task, max_tokens=max_tokens)

    for attempt in range(3):
        try:
            resp = req.post(adapter.url, json=payload, timeout=240)
            raw  = adapter.extract_text(resp.json())
            if raw:
                answer = adapter.clean(raw, mode=detected_mode)
                if answer:
                    return answer
            console.print(f"[dim yellow]empty response, retry {attempt+1}/3[/dim yellow]")
        except Exception as e:
            if attempt == 2:
                return f"ERROR: {e}"
    return "(no response)"

# ── routing ──────────────────────────────────────────────────────────────────────

DIRECT_ROUTES = [
    (re.compile(r"(ls|list|列出?|有什么|有哪些).{0,20}?(文件|folder|目录|dir|~/|/\w)", re.I),
     lambda t: _ls(_extract_path(t, "~/Desktop"))),
    (re.compile(r"^(run|exec|执行|运行)[：:\s]+(.+)", re.I | re.S),
     lambda t: _shell(re.search(r"^(?:run|exec|执行|运行)[：:\s]+(.+)", t, re.I | re.S).group(1))),
    (re.compile(r"(几点|current time|what time|现在时间)", re.I),
     lambda _: datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    (re.compile(r"^[\d\s\+\-\*\/\.\^\(\)]+$"),
     lambda t: str(eval(t.replace("^", "**")))),
    (re.compile(r"(exists?|存在|有没有).{0,30}?(file|文件|目录|dir|~/|/\w)", re.I),
     lambda t: str(Path(os.path.expanduser(_extract_path(t, ""))).exists())),
]

def _extract_path(task: str, default: str) -> str:
    m = re.search(r"(~/[^\s,;'\"\)]+|/[^\s,;'\"\)]+)", task)
    if m: return m.group(1)
    for kw, path in [("桌面","~/Desktop"),("desktop","~/Desktop"),("下载","~/Downloads")]:
        if kw.lower() in task.lower(): return path
    return default

def route(task: str) -> tuple[str, str]:
    for pattern, fn in DIRECT_ROUTES:
        if pattern.search(task):
            try:
                return "direct", fn(task)
            except Exception as e:
                return "direct", f"Error: {e}"
    return "llm", ""

# ── task runner ──────────────────────────────────────────────────────────────────

def run_task(task: str, sender: str, system: str = "", max_tokens: int = 600) -> str:
    st.count += 1
    st.set("WORKING", task)
    ts = datetime.now().strftime("%H:%M:%S")
    mode, pre = route(task)
    console.print()
    console.print(Rule(f"[cyan]#{st.count}  {ts}  [{mode}]  {sender}[/cyan]"))
    console.print(f"[yellow]▶ {task[:120]}[/yellow]\n")
    try:
        result = pre if mode == "direct" else llm(task, system, max_tokens)
        st.result = result
        mem.record(st.count, task, result)
        _count_saved(len(result))
        console.print(Panel(result[:1000], title="[green]✓[/green]", border_style="green"))
    except Exception as e:
        result = f"ERROR: {e}"
        st.result = result
        console.print(Panel(result, title="[red]✗[/red]", border_style="red"))
    finally:
        st.set("IDLE", "—")
    return result

# ── endpoints ────────────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    return jsonify({
        "status":           st.status,
        "task":             st.task,
        "count":            st.count,
        "last":             st.result,
        "tokens_saved_est": _tokens_saved,
        "model":            MODEL,
        "model_family":     adapter.family,
    })

@app.route("/memory")
def memory():
    return jsonify({"notes": mem.notes, "history": mem.history[-10:]})

@app.route("/ask", methods=["POST"])
def ask():
    d = request.json or {}
    task = d.get("task","").strip()
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
    result = run_task(task, d.get("from","?"), d.get("system",""), d.get("max_tokens",600))
    ok = not result.startswith("ERROR:")
    return jsonify({"result": result} if ok else {"error": result}), (200 if ok else 500)

@app.route("/chat", methods=["POST"])
def chat():
    d = request.json or {}
    task = d.get("task","").strip()
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
    threading.Thread(target=run_task, args=(task, d.get("from","?"),
                     d.get("system",""), d.get("max_tokens",600)), daemon=True).start()
    return jsonify({"accepted": True})

@app.route("/run", methods=["POST"])
def run_cmd():
    d = request.json or {}
    cmd = d.get("cmd","").strip()
    if not cmd: return jsonify({"error":"cmd required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]shell  {ts}[/green]"))
    console.print(f"[dim]$ {cmd}[/dim]")
    try:
        out = _shell(cmd, timeout=d.get("timeout", 30))
        _count_saved(len(out))
        console.print(f"[dim]{out[:300]}[/dim]")
        return jsonify({"output": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/read", methods=["POST"])
def read_file():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    content = _read(path, d.get("limit", 8000))
    _count_saved(len(content))
    console.print(Rule(f"[green]read  {path}[/green]"))
    return jsonify({"content": content, "path": path})

@app.route("/grep", methods=["POST"])
def grep():
    d = request.json or {}
    path    = d.get("path","").strip()
    pattern = d.get("pattern","").strip()
    if not path or not pattern:
        return jsonify({"error":"path and pattern required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]grep  {ts}[/green]"))
    result = _grep_file(path, pattern, d.get("context", 2), d.get("ignore_case", True))
    _count_saved(len(_read(path, 99999)) - len(result))
    return jsonify({"matches": result, "path": path, "pattern": pattern})

@app.route("/outline", methods=["POST"])
def outline():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]outline  {ts}[/green]"))
    result = _outline(path)
    _count_saved(len(_read(path, 99999)) - len(result))
    console.print(f"[dim]{result[:400]}[/dim]")
    return jsonify({"outline": result, "path": path})

@app.route("/tree", methods=["POST"])
def tree():
    d = request.json or {}
    path  = d.get("path","").strip() or "~/Desktop"
    depth = int(d.get("depth", 2))
    ts    = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]tree  {ts}[/green]"))
    result = _tree(path, depth, d.get("exclude", "__pycache__,.git,node_modules,.DS_Store"))
    _count_saved(len(result) * 3)
    return jsonify({"tree": result, "path": path})

@app.route("/exists", methods=["POST"])
def exists():
    d = request.json or {}
    path = d.get("path","").strip()
    if not path: return jsonify({"error":"path required"}), 400
    p = Path(os.path.expanduser(path))
    info = {"exists": p.exists(), "path": str(p)}
    if p.exists():
        info["is_file"] = p.is_file()
        info["is_dir"]  = p.is_dir()
        info["size"]    = p.stat().st_size if p.is_file() else None
    return jsonify(info)

@app.route("/write", methods=["POST"])
def write_file():
    d = request.json or {}
    path    = d.get("path","").strip()
    content = d.get("content","")
    if not path: return jsonify({"error":"path required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]write  {ts}[/green]"))
    try:
        result = _write_file(path, content)
        _count_saved(len(content))
        return jsonify({"result": result, "path": path, "chars": len(content)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/patch", methods=["POST"])
def patch():
    d = request.json or {}
    path = d.get("path","").strip()
    old  = d.get("old","")
    new  = d.get("new","")
    if not path or not old: return jsonify({"error":"path and old required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[green]patch  {ts}[/green]"))
    try:
        result = _patch_file(path, old, new)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/summarize", methods=["POST"])
def summarize():
    d = request.json or {}
    focus = d.get("focus", "key logic and structure")
    if "path" in d:
        content = _read(d["path"], limit=7000)
        label = d["path"]
    elif "text" in d:
        content = d["text"][:7000]
        label = "text"
    else:
        return jsonify({"error": "path or text required"}), 400
    if content.startswith("File not found"):
        return jsonify({"error": content}), 404
    full_len = len(content)
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[magenta]summarize  {ts}[/magenta]"))
    result = llm(f"Focus on: {focus}\n\nContent:\n{content}",
                 system="Summarize in ≤6 concise bullet points. Facts only. No preamble.\n",
                 max_tokens=400)
    _count_saved(full_len - len(result))
    console.print(Panel(result, title="[magenta]summary[/magenta]", border_style="magenta"))
    return jsonify({"summary": result, "source": label, "original_chars": full_len})

@app.route("/codegen", methods=["POST"])
def codegen():
    d = request.json or {}
    task = d.get("task","").strip()
    lang = d.get("lang","python")
    if not task: return jsonify({"error":"task required"}), 400
    if st.status == "WORKING": return jsonify({"error":"busy"}), 429
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[cyan]codegen  {ts}[/cyan]"))
    result = llm(task, system=f"Output {lang} code only. No explanation. No markdown fences.\n",
                 max_tokens=700)
    console.print(Panel(result, title="[cyan]code[/cyan]", border_style="cyan"))
    st.count += 1
    mem.record(st.count, task, result[:200])
    return jsonify({"code": result, "lang": lang})

@app.route("/explain", methods=["POST"])
def explain():
    d = request.json or {}
    if "path" in d:
        content = _read(d["path"], limit=4000)
        label = d["path"]
        if content.startswith("File not found"):
            return jsonify({"error": content}), 404
    elif "code" in d:
        content = d["code"][:4000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[blue]explain  {ts}[/blue]"))
    result = llm(f"Explain this code:\n\n{content}",
                 system="One sentence summary, then bullet points for key logic. No fences.\n",
                 max_tokens=400)
    _count_saved(len(content))
    console.print(Panel(result[:600], title="[blue]explanation[/blue]", border_style="blue"))
    return jsonify({"explanation": result, "source": label})

@app.route("/fix", methods=["POST"])
def fix():
    d = request.json or {}
    error_msg = d.get("error", "").strip()
    code_ctx  = d.get("code", "")[:3000]
    if not error_msg: return jsonify({"error": "error field required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[red]fix  {ts}[/red]"))
    prompt = f"Error:\n{error_msg}\n"
    if code_ctx:
        prompt += f"\nCode context:\n{code_ctx}\n"
    prompt += "\nWhat is the fix?"
    result = llm(prompt,
                 system="One sentence root cause, then the corrected code or line. No fences.\n",
                 max_tokens=400)
    console.print(Panel(result[:600], title="[red]fix[/red]", border_style="red"))
    return jsonify({"fix": result})

@app.route("/test", methods=["POST"])
def gen_tests():
    d = request.json or {}
    fn_name = d.get("function", "")
    if "path" in d:
        content = _read(d["path"], limit=3000)
        if fn_name:
            content = _grep_file(d["path"], rf"def {fn_name}", context=15) or content
        label = d["path"]
    elif "code" in d:
        content = d["code"][:3000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[yellow]test  {ts}[/yellow]"))
    target = f"for the function `{fn_name}`" if fn_name else "for the code"
    result = llm(f"Write pytest unit tests {target}:\n\n{content}",
                 system="Output only the test code. Use pytest. No fences.\n",
                 max_tokens=600, mode="code")
    console.print(Panel(result[:800], title="[yellow]tests[/yellow]", border_style="yellow"))
    _count_saved(len(content))
    return jsonify({"tests": result, "source": label})

@app.route("/review", methods=["POST"])
def review():
    d = request.json or {}
    if "path" in d:
        content = _read(d["path"], limit=3000)
        label = d["path"]
        if content.startswith("File not found"):
            return jsonify({"error": content}), 404
    elif "code" in d:
        content = d["code"][:3000]
        label = "snippet"
    else:
        return jsonify({"error": "path or code required"}), 400
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[magenta]review  {ts}[/magenta]"))
    result = llm(f"Review this code:\n\n{content}",
                 system="Format: BUGS: (list or 'none'), IMPROVEMENTS: (top 2-3), VERDICT: (one line). No fences.\n",
                 max_tokens=350)
    _count_saved(len(content))
    console.print(Panel(result[:600], title="[magenta]review[/magenta]", border_style="magenta"))
    return jsonify({"review": result, "source": label})

@app.route("/git_summary", methods=["POST"])
def git_summary():
    d = request.json or {}
    repo_path = os.path.expanduser(d.get("path", "."))
    n = int(d.get("n", 10))
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(Rule(f"[cyan]git_summary  {ts}[/cyan]"))
    log_raw = _shell(f"git -C {repo_path} log --oneline --stat -{n} 2>&1")
    if "not a git repository" in log_raw.lower():
        return jsonify({"error": f"Not a git repo: {repo_path}"}), 400
    result = llm(f"Summarize these recent git commits in plain English:\n\n{log_raw}",
                 system="2-4 bullet points. Focus on WHAT changed and WHY. No fences.\n",
                 max_tokens=250)
    _count_saved(len(log_raw))
    console.print(Panel(result, title="[cyan]git summary[/cyan]", border_style="cyan"))
    return jsonify({"summary": result, "commits_analyzed": n})

@app.route("/batch", methods=["POST"])
def batch():
    d = request.json or {}
    tasks = d.get("tasks", [])
    if not tasks: return jsonify({"error": "tasks required"}), 400
    results = []
    for t in tasks:
        typ = t.get("type", "ask")
        try:
            if typ == "run":
                results.append({"type": "run", "result": _shell(t.get("cmd",""))})
            elif typ == "read":
                results.append({"type": "read", "result": _read(t.get("path",""))})
            elif typ == "grep":
                results.append({"type": "grep", "result": _grep_file(
                    t.get("path",""), t.get("pattern",""), t.get("context",2))})
            elif typ == "outline":
                results.append({"type": "outline", "result": _outline(t.get("path",""))})
            elif typ == "tree":
                results.append({"type": "tree", "result": _tree(
                    t.get("path","~/Desktop"), t.get("depth",2))})
            elif typ == "exists":
                p = Path(os.path.expanduser(t.get("path","")))
                results.append({"type": "exists", "result": p.exists()})
            elif typ == "write":
                results.append({"type": "write", "result": _write_file(
                    t.get("path",""), t.get("content",""))})
            else:
                results.append({"type": "ask", "result": run_task(t.get("task",""), "batch")})
        except Exception as e:
            results.append({"type": typ, "error": str(e)})
    return jsonify({"results": results})

@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    mem.clear()
    return jsonify({"cleared": True, "notes": mem.notes})

@app.route("/note", methods=["POST"])
def note():
    d = request.json or {}
    key = d.get("key","").strip()
    val = d.get("value","").strip()
    if not key or not val: return jsonify({"error":"key and value required"}), 400
    mem.save(key, val)
    return jsonify({"saved": {key: val}})

# ── main ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=7860, threaded=True),
        daemon=True
    ).start()

    def _warmup():
        """Pre-load the LLM into memory so it's ready on first real request."""
        time.sleep(3)
        try:
            payload = adapter.generate_payload("", "ok", max_tokens=1)
            req.post(adapter.url, json=payload, timeout=60)
            console.print("[dim green]✓ LLM warmed up[/dim green]")
        except Exception:
            pass
    threading.Thread(target=_warmup, daemon=True).start()

    console.print(Panel(
        "[bold cyan]Miser v1.0[/bold cyan]  ·  Claude Code's local co-processor\n\n"
        "[bold]Zero-LLM endpoints (<50ms):[/bold]\n"
        "  [green]/run /read /grep /outline /tree /exists /write /patch[/green]\n\n"
        "[bold]Local-LLM endpoints (0 API tokens):[/bold]\n"
        "  [cyan]/ask /summarize /codegen /explain /fix /test /review /git_summary /batch[/cyan]\n\n"
        f"[bold]Model:[/bold]  {MODEL}  (family: {adapter.family})\n"
        f"[bold]Memory:[/bold] {len(mem.notes)} notes · {len(mem.history)} past tasks\n"
        "[dim]http://localhost:7860[/dim]",
        border_style="cyan", title="[bold]Ready[/bold]"
    ))
    console.print("[green]✓ Waiting...[/green]\n")

    while True:
        time.sleep(1)
