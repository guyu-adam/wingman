# Miser v1.0 — Test Report

**Date:** 2026-05-11  
**Platform:** macOS Apple Silicon (Darwin 24.6.0)  
**Python:** 3.9.13  
**Model:** miser-qwen (qwen3.5:4b, 3.4 GB)  
**Dependencies:** flask 1.1.2 · requests 2.28.2 · numpy 1.23.5 · rich 15.0.0

---

## Results at a glance

| Test suite | Passed | Total |
|------------|--------|-------|
| Performance — Zero-LLM endpoints | 9 | 9 |
| Performance — Local-LLM endpoints | 8 | 8 |
| Compatibility — Family detection | 17 | 17 |
| Compatibility — Prompt format | 11 | 11 |
| Compatibility — Response cleaning | 6 | 6 |
| Compatibility — ModelAdapter | 4 | 4 |
| Compatibility — Endpoint edge cases | 6 | 6 |
| Compatibility — Concurrency | 1 | 1 |
| **Total** | **62** | **62** |

**Pass rate: 100%**

---

## Performance — Zero-LLM endpoints

Target: <50ms per call.

| Endpoint | Latency | Notes |
|----------|---------|-------|
| `GET /status` | 9ms | ✓ |
| `POST /run` | 44ms | ✓ shell execution |
| `POST /exists` | 4ms | ✓ |
| `POST /tree` | 7ms | ✓ |
| `POST /outline` | 5ms | ✓ AST parsing |
| `POST /grep` | 4ms | ✓ regex search |
| `POST /read` | 3ms | ✓ |
| `POST /write` + `/patch` | 7ms | ✓ round-trip |
| `POST /batch` (2 tasks) | 47ms | ✓ |

**Average: 14ms** (target <50ms — ✓)

---

## Performance — Local-LLM endpoints

All run on Ollama locally; zero cloud API tokens consumed.

| Endpoint | Latency | Output sample |
|----------|---------|---------------|
| `POST /ask` | 3.3s | Correct arithmetic answer |
| `POST /codegen` | 1.2s | Valid Python function generated |
| `POST /fix` | 1.7s | Correct NameError root cause + fix |
| `POST /test` | 4.4s | pytest tests with assert statements |
| `POST /review` | 5.0s | Structured BUGS/IMPROVEMENTS/VERDICT |
| `POST /git_summary` | 6.5s | Accurate plain-English commit summary |
| `POST /summarize` | 16.0s | Bullet-point summary of 700-line file |
| `POST /explain` | 16.3s | Correct architecture explanation |

**Average: 6.8s** · Simple tasks 1–5s · Complex tasks (explain/summarize) ~16s

### Token savings per call (estimated)

| Operation | API tokens saved |
|-----------|-----------------|
| `W.outline()` on 600-line file | ~7 900 |
| `W.grep()` to find one function | ~7 950 |
| `W.explain()` instead of Read+reason | ~8 000 (100%) |
| `W.test()` instead of generating | ~500 (100%) |
| `W.fix()` instead of reasoning | ~300 (100%) |

---

## Compatibility — Model family detection

`detect_family()` tested against 17 model name patterns. Uses regex first (fast, no network), falls back to Ollama `/api/show` for aliases.

| Model name | Detected family | ✓ |
|-----------|----------------|---|
| qwen3.5:4b | qwen3 | ✓ |
| qwen3:8b | qwen3 | ✓ |
| qwen2.5:7b | qwen2 | ✓ |
| qwen2:7b | qwen2 | ✓ |
| llama3.1:8b | llama3 | ✓ |
| llama3:8b | llama3 | ✓ |
| llama2:7b | llama2 | ✓ |
| mistral:7b | mistral | ✓ |
| mixtral:8x7b | mistral | ✓ |
| phi4:latest | phi4 | ✓ |
| phi3:latest | phi3 | ✓ |
| phi-3:mini | phi3 | ✓ |
| gemma3:4b | gemma | ✓ |
| gemma:7b | gemma | ✓ |
| deepseek-r1:7b | deepseek-r1 | ✓ |
| deepseek-coder:6.7b | deepseek | ✓ |
| codellama:7b | llama3 | ✓ |

---

## Compatibility — Prompt format

`build_prompt()` verified for 10 families: system prompt and user message both present in output for all families. qwen3 correctly injects empty `<think></think>` block to suppress verbose chain-of-thought.

| Family | sys ✓ | user ✓ | think-block |
|--------|-------|--------|-------------|
| qwen3 | ✓ | ✓ | injected |
| qwen2 | ✓ | ✓ | — |
| llama3 | ✓ | ✓ | — |
| llama2 | ✓ | ✓ | — |
| mistral | ✓ | ✓ | — |
| phi3 | ✓ | ✓ | — |
| phi4 | ✓ | ✓ | — |
| gemma | ✓ | ✓ | — |
| deepseek-r1 | ✓ | ✓ | — |
| deepseek | ✓ | ✓ | — |

---

## Compatibility — Response cleaning

`clean_response()` verified for common post-processing scenarios:

| Scenario | Input | Expected output | ✓ |
|----------|-------|----------------|---|
| qwen3: strip `<think>` block | `<think>blah</think>\nFinal answer.` | `Final answer.` | ✓ |
| qwen3: leaking `</think>` | `still thinking</think>\nActual answer` | `Actual answer` | ✓ |
| Strip code fences | ` ```python\nprint('hi')\n``` ` | `print('hi')` | ✓ |
| Strip `<\|eot_id\|>` | `Good answer<\|eot_id\|>` | `Good answer` | ✓ |
| Strip `<\|im_end\|>` | `Answer<\|im_end\|>` | `Answer` | ✓ |
| Empty input | `""` | `""` | ✓ |

---

## Compatibility — Endpoint edge cases

| Scenario | Expected behaviour | ✓ |
|----------|--------------------|---|
| `exists` on missing file | Returns `{"exists": false}` | ✓ |
| `grep` with no matches | Returns "No matches for: ..." | ✓ |
| `outline` on non-Python file | Returns output without crash | ✓ |
| `read` on missing file | Returns "File not found: ..." | ✓ |
| `run` with exit code 1 | Captures stderr, doesn't crash | ✓ |
| `ask` with empty task | Returns error gracefully | ✓ |

---

## Compatibility — Concurrency

4 simultaneous `/run` requests completed in **<0.1s** with 0 errors. Flask `threaded=True` mode handles concurrent Zero-LLM requests without contention.

> Note: Local-LLM endpoints serialize through Ollama (single-GPU inference). Concurrent LLM requests will queue.

---

## Known limitations

| Limitation | Detail |
|-----------|--------|
| Windows auto-start | `install.sh` installs macOS/Linux service only; Windows requires manual `start.sh` |
| Concurrent LLM | Ollama queues requests; parallel `/ask` calls don't parallelize |
| Model not loaded at idle | First LLM call after idle loads model (~3s warm-up); subsequent calls are fast |
| Flask version | Running on 1.1.2 (older); compatible but `requirements.txt` specifies `>=2.3` |

---

## Environment

```
OS       : macOS Darwin 24.6.0 (Apple Silicon)
Python   : 3.9.13
flask    : 1.1.2
requests : 2.28.2
numpy    : 1.23.5
rich     : 15.0.0
Ollama   : local
Model    : miser-qwen → qwen3.5:4b (3.4 GB)
```
