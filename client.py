"""
Miser v1.0 client for Claude Code.

Usage:
    import sys; sys.path.insert(0, '/path/to/miser')
    from client import W

    W.outline("~/project/app.py")           # function/class map
    W.grep("~/project/app.py", "def fn")    # search with context
    W.tree("~/project", depth=2)            # directory tree
    W.exists("~/project/.env")              # existence check
    W.run("pytest --tb=short -q")           # shell command
    W.explain("~/project/utils.py")         # plain-English explanation
    W.fix("TypeError: None", code="...")    # error → fix
    W.test("~/project/utils.py")            # generate pytest tests
    W.review("~/project/utils.py")          # code review
    W.codegen("write a debounce in python") # code generation
    W.ask("any freeform task")              # general purpose
    W.batch([("outline","~/f.py"),("run","git status")])
    W.status()
    W.clear()
"""
import requests

BASE = "http://localhost:7860"

def _post(path, data):
    r = requests.post(f"{BASE}{path}", json=data, timeout=120)
    return r.json()

class _W:
    def ask(self, task, max_tokens=600):
        d = _post("/ask", {"task": task, "from": "claude", "max_tokens": max_tokens})
        return d.get("result") or d.get("error")

    def run(self, cmd, timeout=30):
        d = _post("/run", {"cmd": cmd, "timeout": timeout})
        return d.get("output") or d.get("error")

    def read(self, path, limit=8000):
        d = _post("/read", {"path": path, "limit": limit})
        return d.get("content") or d.get("error")

    def grep(self, path, pattern, ctx=2, ignore_case=True):
        d = _post("/grep", {"path": path, "pattern": pattern,
                            "context": ctx, "ignore_case": ignore_case})
        return d.get("matches") or d.get("error")

    def outline(self, path):
        d = _post("/outline", {"path": path})
        return d.get("outline") or d.get("error")

    def tree(self, path="~/Desktop", depth=2):
        d = _post("/tree", {"path": path, "depth": depth})
        return d.get("tree") or d.get("error")

    def exists(self, path):
        return _post("/exists", {"path": path})

    def write(self, path, content):
        d = _post("/write", {"path": path, "content": content})
        return d.get("result") or d.get("error")

    def patch(self, path, old, new):
        d = _post("/patch", {"path": path, "old": old, "new": new})
        return d.get("result") or d.get("error")

    def summarize(self, path_or_text, focus="key logic and structure"):
        key = "path" if ("/" in path_or_text or "~" in path_or_text) else "text"
        d = _post("/summarize", {key: path_or_text, "focus": focus})
        return d.get("summary") or d.get("error")

    def codegen(self, task, lang="python"):
        d = _post("/codegen", {"task": task, "lang": lang})
        return d.get("code") or d.get("error")

    def explain(self, path_or_code):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        d = _post("/explain", {key: path_or_code})
        return d.get("explanation") or d.get("error")

    def fix(self, error_msg, code=""):
        d = _post("/fix", {"error": error_msg, "code": code})
        return d.get("fix") or d.get("error")

    def test(self, path_or_code, function=""):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        payload = {key: path_or_code}
        if function:
            payload["function"] = function
        d = _post("/test", payload)
        return d.get("tests") or d.get("error")

    def review(self, path_or_code):
        key = "path" if ("/" in path_or_code or "~" in path_or_code) else "code"
        d = _post("/review", {key: path_or_code})
        return d.get("review") or d.get("error")

    def git_summary(self, path=".", n=10):
        d = _post("/git_summary", {"path": path, "n": n})
        return d.get("summary") or d.get("error")

    def batch(self, tasks):
        """tasks: list of tuples — ("run","cmd"), ("outline","~/f.py"),
        ("grep","~/f.py","pattern"), ("tree","~/dir",depth),
        ("exists","~/f"), ("write","~/f","content"), ("ask","task")
        """
        items = []
        for t in tasks:
            typ = t[0]
            if   typ == "run":     items.append({"type":"run",     "cmd":t[1]})
            elif typ == "read":    items.append({"type":"read",    "path":t[1]})
            elif typ == "grep":    items.append({"type":"grep",    "path":t[1], "pattern":t[2],
                                                 "context": t[3] if len(t)>3 else 2})
            elif typ == "outline": items.append({"type":"outline", "path":t[1]})
            elif typ == "tree":    items.append({"type":"tree",    "path":t[1],
                                                 "depth": t[2] if len(t)>2 else 2})
            elif typ == "exists":  items.append({"type":"exists",  "path":t[1]})
            elif typ == "write":   items.append({"type":"write",   "path":t[1], "content":t[2]})
            else:                  items.append({"type":"ask",     "task":t[1]})
        d = _post("/batch", {"tasks": items})
        return [r.get("result") or r.get("error") for r in d.get("results", [])]

    def note(self, key, value):
        d = _post("/note", {"key": key, "value": value})
        return d.get("saved") or d.get("error")

    def clear(self):
        return requests.post(f"{BASE}/memory/clear", timeout=10).json().get("cleared")

    def status(self):
        return requests.get(f"{BASE}/status", timeout=5).json()

W = _W()   # W for Miser
J = W      # backward-compat alias
