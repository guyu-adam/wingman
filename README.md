# Miser

**本地 LLM 协处理器，专为 Claude Code / Codex / Aider 设计。把耗 token 的任务卸载到本地 Ollama，零云端成本。**

**Local LLM co-processor for Claude Code, Codex, and Aider. Offload token-heavy tasks to a local Ollama model — zero cloud API cost.**

---

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![Tests: 62/62](https://img.shields.io/badge/tests-62%2F62%20passing-brightgreen.svg)](TEST_REPORT.md)
[![Model: qwen3.5:4b](https://img.shields.io/badge/model-qwen3.5%3A4b-orange.svg)](https://ollama.com/library/qwen3.5)

---

## 一键安装 / One-Command Install

```bash
git clone https://github.com/guyu-adam/miser.git
bash miser/install.sh
```

安装后重启 Claude Code，它会**自动**使用 Miser，无需任何额外配置。

After restart, Claude Code **automatically** uses Miser for every session — no extra config.

---

## 它能做什么 / What It Does

Claude Code 每次对话都烧大量 token 读文件、分析代码。Miser 在本地运行一个 Flask 服务（端口 7860），拦截这些任务交给本地 LLM（Ollama）处理：

Claude Code burns tokens reading files and analyzing code. Miser runs a local Flask server (port 7860) and intercepts those tasks for a local Ollama model:

| 任务 / Task | 没有 Miser | 用了 Miser | 节省 / Saved |
|---|---|---|---|
| 分析大文件结构 / Map file structure | `Read` → ~7 500 tokens | `W.outline(path)` | **~7 500 tokens** |
| 查找单个函数 / Find one function | `Read` → ~7 800 tokens | `W.grep(path, "fn")` | **~7 800 tokens** |
| 项目概览 / Project overview | 多次 `ls` | `W.tree(path)` | **~3 000 tokens** |
| 理解模块 / Explain module | Read + GPT 推理 | `W.explain(path)` | **0 API tokens** |
| 诊断报错 / Diagnose error | GPT 推理 | `W.fix(error)` | **0 API tokens** |
| 生成测试 / Write tests | GPT 生成 | `W.test(path)` | **0 API tokens** |

---

## 实测性能 / Benchmark Results

> 完整报告见 [TEST_REPORT.md](TEST_REPORT.md) · Full report: [TEST_REPORT.md](TEST_REPORT.md)

```
Tests passed  :  62 / 62  ✓
Zero-LLM avg  :  14 ms     (grep, outline, tree, exists, read, write, patch, run, batch)
Local-LLM avg :   6.8 s    (ask, explain, fix, codegen, test, review, summarize)
Model families:  17 detected correctly (qwen3/qwen2/llama3/llama2/mistral/phi3/phi4/gemma/deepseek…)
LLM always-on :  keep_alive=-1, startup warmup thread → first response < 1s after warmup
```

---

## API 速查 / API Reference

```python
from client import W   # W = Miser client

# ── 零 LLM（本地文件操作，<50ms） / Zero-LLM (local file ops, <50ms) ──
W.outline(path)                    # 返回函数/类列表 / list functions & classes
W.grep(path, pattern, ctx=2)       # 搜索代码 / search code
W.tree(path, depth=2)              # 目录树 / directory tree
W.exists(path)                     # 检查文件 / check file exists
W.read(path)                       # 读文件 / read file
W.write(path, content)             # 写文件 / write file
W.batch([path1, path2, ...])       # 批量读取 / batch read
W.run(cmd)                         # 执行命令 / run shell command

# ── 本地 LLM（0 API token） / Local LLM (0 API tokens) ──
W.ask(question)                    # 通用问答 / general Q&A
W.explain(path)                    # 解释代码 / explain code
W.fix(error, code=ctx)             # 修复报错 / diagnose & fix error
W.codegen(task)                    # 生成代码 / generate code
W.test(path)                       # 生成测试 / generate tests
W.review(path)                     # 代码审查 / code review
W.summarize(text)                  # 摘要 / summarize
W.git_summary()                    # git diff 摘要 / git diff summary
```

---

## 支持的模型 / Supported Models

Miser 自动检测模型系列，适配正确的提示格式：

| 系列 / Family | 代表模型 / Examples |
|---|---|
| qwen3 / qwen3.5 | `qwen3.5:4b`（默认）, `qwen3:8b` |
| qwen2 / qwen2.5 | `qwen2.5:4b`, `qwen2.5:7b` |
| llama3 | `llama3.1:8b`, `codellama:7b` |
| mistral | `mistral:7b`, `mixtral:8x7b` |
| phi3 / phi4 | `phi4:latest`, `phi3:mini` |
| gemma / gemma3 | `gemma3:4b`, `gemma3:12b` |
| deepseek | `deepseek-coder:6.7b`, `deepseek-r1:8b` |

切换模型 / Switch model:
```bash
MISER_MODEL=mistral:7b bash start.sh
```

---

## 系统要求 / Requirements

- Python 3.9+
- [Ollama](https://ollama.com) (自动安装 / auto-installed by `install.sh`)
- macOS / Linux / Windows (WSL)
- 推荐 8GB+ RAM（运行 4b 模型）/ 8GB+ RAM recommended for 4b models

---

## 卸载 / Uninstall

```bash
bash miser/uninstall.sh
```

---

## License

MIT
