---
name: self-eval
description: 自我评估钩子。每次 session 结束时自动检查三种异常情况（用户纠正/工具重试失败/上报规则触发），有任一情况则写入 reflection 记忆到 LanceDB。无异常则静默退出。
---

# Self-Eval — 自我评估钩子

## 功能

每次 session 结束时自动运行，检查三种异常情况：

| 检测类型 | 关键词/模式 |
|---------|-----------|
| **用户纠正** | 不对、重来、不是这个意思、错了、我想要的是... |
| **工具重试失败** | 重试2次仍失败、工具调用失败、失败后停止 |
| **上报规则触发** | 需要我确认、先告诉我、暂停等待 |

## 触发条件

有任一情况 → `memory_store` 写入 reflection 记忆：
- category: reflection
- importance: 0.9
- 格式：`自我评估：[场景]。正确做法：[应该怎么做]。触发原因：[类型]`

无任何异常 → 静默退出，不输出任何内容。

## 核心文件

| 文件 | 作用 |
|------|------|
| `scripts/self_eval.py` | 主脚本（检测 + 写入 LanceDB） |

## 注册方式

通过 OpenClaw `command:stop` 钩子自动触发。

> ⚠️ OpenClaw 当前没有 `session:end` 内置钩子（列为 planned 事件）。
> 本 skill 使用 `command:stop` 作为近似替代——仅在用户显式执行 `/stop` 时触发。
> 如果 session 因超时或断连而结束，本 hook 不会运行。

已注册钩子：`~/.openclaw/hooks/self-eval-hook/`

## 依赖

- LanceDB（memory-lancedb-pro 已安装）
- 读取 `~/.openclaw/agents/main/sessions/*.jsonl`
