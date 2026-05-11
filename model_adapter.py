"""
model_adapter.py — Multi-model prompt formatting for Miser.

Detects model family from the model name and returns the correct
raw prompt format + response post-processor for each family.

Supported families:
  qwen3 / qwen3.5   — chatml + forced <think></think> skip
  qwen2.5 / qwen2   — standard chatml, no thinking
  llama3.x          — chatml (llama3 uses same format)
  llama2            — [INST]...[/INST] format
  mistral / mixtral — [INST]...[/INST] format
  phi3 / phi4       — <|user|>...<|assistant|> format
  gemma / gemma3    — <start_of_turn> format
  deepseek-coder    — chatml (deepseek uses chatml)
  deepseek-r1       — chatml + thinking (like qwen3)
  default           — chat API, no raw format
"""

import re
import requests as _req
from typing import Callable

# ──────────────────────────────────────────────────────────────────────────────
#  Family detection
# ──────────────────────────────────────────────────────────────────────────────

def _ollama_family(model_name: str) -> str:
    """Ask Ollama for the actual model family (works for aliases like miser-qwen)."""
    try:
        r = _req.post("http://localhost:11434/api/show",
                      json={"name": model_name}, timeout=5)
        det = r.json().get("details", {})
        fam = (det.get("family") or "").lower()
        if fam:
            if "qwen35" in fam or "qwen3.5" in fam:
                return "qwen3"
            if "qwen3" in fam:
                return "qwen3"
            if "qwen2" in fam:
                return "qwen2"
            if "llama3" in fam or "llama-3" in fam:
                return "llama3"
            if "llama" in fam:
                return "llama2"
            if "mistral" in fam or "mixtral" in fam:
                return "mistral"
            if "phi" in fam:
                return "phi3"
            if "gemma" in fam:
                return "gemma"
            if "deepseek" in fam:
                return "deepseek-r1" if "r1" in fam else "deepseek"
    except Exception:
        pass
    return ""


def detect_family(model_name: str) -> str:
    # First try name-based detection (fast, no network)
    n = model_name.lower()
    if re.search(r'qwen3\.5|qwen3', n):
        return "qwen3"
    if re.search(r'qwen2\.5|qwen2', n):
        return "qwen2"
    if re.search(r'llama3|llama-3', n):
        return "llama3"
    if re.search(r'llama2|llama-2', n):
        return "llama2"
    if re.search(r'mistral|mixtral', n):
        return "mistral"
    if re.search(r'phi4', n):
        return "phi4"
    if re.search(r'phi3|phi-3', n):
        return "phi3"
    if re.search(r'gemma3|gemma', n):
        return "gemma"
    if re.search(r'deepseek-r1|deepseek_r1', n):
        return "deepseek-r1"
    if re.search(r'deepseek', n):
        return "deepseek"
    if re.search(r'codellama', n):
        return "llama3"
    # Name didn't match — ask Ollama (handles aliases like miser-qwen)
    ollama_fam = _ollama_family(model_name)
    return ollama_fam if ollama_fam else "default"


def has_thinking(family: str) -> bool:
    """True if this model family does chain-of-thought in a <think> block."""
    return family in ("qwen3", "deepseek-r1")


def use_raw_generate(family: str) -> bool:
    """True if we must use /api/generate (raw prompt) rather than /api/chat."""
    return family in ("qwen3", "qwen2", "llama2", "mistral", "phi3", "phi4", "gemma", "deepseek-r1", "deepseek")


# ──────────────────────────────────────────────────────────────────────────────
#  Prompt builders  (return raw prompt string for /api/generate)
# ──────────────────────────────────────────────────────────────────────────────

def build_prompt(family: str, system: str, user: str) -> str:
    """Build a raw prompt string appropriate for the model family."""

    if family in ("qwen3", "qwen2"):
        # ChatML format; qwen3 gets injected empty <think> to suppress verbose thinking
        think_block = "<think>\n\n</think>\n\n" if family == "qwen3" else ""
        return (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n{think_block}"
        )

    if family == "llama3":
        return (
            f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
            f"{system}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n"
            f"{user}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n"
        )

    if family == "llama2":
        sys_block = f"<<SYS>>\n{system}\n<</SYS>>\n\n" if system else ""
        return f"[INST] {sys_block}{user} [/INST]"

    if family == "mistral":
        # Mistral v3 uses chatml; older uses [INST]
        sys_block = f"[SYSTEM_PROMPT]{system}[/SYSTEM_PROMPT]\n" if system else ""
        return f"{sys_block}[INST] {user} [/INST]"

    if family in ("phi3", "phi4"):
        return (
            f"<|system|>\n{system}<|end|>\n"
            f"<|user|>\n{user}<|end|>\n"
            f"<|assistant|>\n"
        )

    if family == "gemma":
        sys_part = f"<start_of_turn>system\n{system}<end_of_turn>\n" if system else ""
        return (
            f"{sys_part}"
            f"<start_of_turn>user\n{user}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )

    if family in ("deepseek-r1", "deepseek"):
        return (
            f"<|begin▁of▁sentence|>{system}\n"
            f"<|User|>{user}\n"
            f"<|Assistant|>"
        )

    # default / unknown: just system + user in plaintext, let Ollama handle it
    return f"{system}\n\nUser: {user}\nAssistant:"


# ──────────────────────────────────────────────────────────────────────────────
#  Response post-processor
# ──────────────────────────────────────────────────────────────────────────────

def clean_response(raw: str, family: str, mode: str = "text") -> str:
    """Strip thinking tokens and clean up the raw model response."""
    if not raw:
        return ""

    # Remove thinking blocks (qwen3, deepseek-r1)
    if has_thinking(family):
        # Strip <think>...</think> blocks
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        # If thinking leaked without closing tag, take everything after </think>
        if '</think>' in raw:
            raw = raw.split('</think>', 1)[-1].strip()

    # Strip code fences
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw.strip())
    raw = re.sub(r'\n?```$', '', raw).strip()

    # Strip EOS tokens
    for tok in ['<|im_end|>', '<|end|>', '<|eot_id|>', '<end_of_turn>',
                '<|endoftext|>', '</s>', '[/INST]', '<|Assistant|>']:
        raw = raw.replace(tok, '').strip()

    if mode == "code":
        m = re.search(r'^(def |class )[a-zA-Z_]', raw, re.MULTILINE)
        if m:
            block = raw[m.start():]
            lines = block.splitlines()
            result = [lines[0]]
            for ln in lines[1:]:
                if ln and not ln.startswith((' ', '\t')) and not ln.startswith(('def ', 'class ')):
                    break
                result.append(ln)
            return "\n".join(result).strip()

    if mode == "bullets":
        bullets = re.findall(r'^[ \t]*[-•*\d\.]\s+.+', raw, re.MULTILINE)
        if len(bullets) >= 2:
            seen, deduped = set(), []
            for b in bullets:
                key = b.strip().lower()[:60]
                if key not in seen:
                    seen.add(key)
                    deduped.append(b.strip())
            return "\n".join(deduped[:8])

    # Long response: find the last clean block (avoid leaked meta-commentary)
    if len(raw) > 600:
        paras = [p.strip() for p in re.split(r'\n{2,}', raw) if p.strip()]
        meta = re.compile(r'^(we|let\'s|the problem|note:|however|but|so|now|wait|actually)', re.I)
        clean = [p for p in paras if not meta.match(p)]
        if clean:
            return clean[-1]
        return paras[-1] if paras else raw[-400:]

    return raw


# ──────────────────────────────────────────────────────────────────────────────
#  Unified LLM call spec
# ──────────────────────────────────────────────────────────────────────────────

class ModelAdapter:
    """
    Encapsulates model-family-specific behaviour.
    Usage:
        adapter = ModelAdapter("qwen3.5:4b")
        payload = adapter.generate_payload(system, user, max_tokens=600)
        raw = requests.post(adapter.url, json=payload).json().get("response","")
        answer = adapter.clean(raw, mode="code")
    """

    GENERATE_URL = "http://localhost:11434/api/generate"
    CHAT_URL     = "http://localhost:11434/api/chat"

    def __init__(self, model_name: str):
        self.model  = model_name
        self.family = detect_family(model_name)
        self._raw   = use_raw_generate(self.family)
        self._think = has_thinking(self.family)

    @property
    def url(self) -> str:
        return self.GENERATE_URL if self._raw else self.CHAT_URL

    def generate_payload(self, system: str, user: str, max_tokens: int = 600,
                         temperature: float = 0.2) -> dict:
        think_budget = 2400 if self._think else 0
        opts = {"num_predict": max_tokens + think_budget, "temperature": temperature}

        if self._raw:
            return {
                "model":    self.model,
                "prompt":   build_prompt(self.family, system, user),
                "options":  opts,
                "stream":   False,
                "raw":      True,
                "keep_alive": -1,
            }
        else:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": user})
            return {
                "model":      self.model,
                "messages":   messages,
                "options":    opts,
                "stream":     False,
                "keep_alive": -1,
            }

    def extract_text(self, response_json: dict) -> str:
        """Pull text out of the Ollama API response dict."""
        if self._raw:
            return response_json.get("response", "").strip()
        msg = response_json.get("message", {})
        return (msg.get("content") or msg.get("thinking") or "").strip()

    def clean(self, raw: str, mode: str = "text") -> str:
        return clean_response(raw, self.family, mode)

    def info(self) -> dict:
        return {"model": self.model, "family": self.family,
                "thinking": self._think, "raw_api": self._raw}


# ──────────────────────────────────────────────────────────────────────────────
#  Model suggestions  (for README / help output)
# ──────────────────────────────────────────────────────────────────────────────

RECOMMENDED_MODELS = {
    "4b_apple_silicon": "qwen3.5:4b",
    "4b_lightweight":   "qwen2.5:4b",
    "7b_quality":       "mistral:7b",
    "8b_llama":         "llama3.1:8b",
    "code_focused":     "deepseek-coder:6.7b",
    "phi_windows":      "phi4:latest",
    "gemma_google":     "gemma3:4b",
}
