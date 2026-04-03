---
name: cache-monitor
description: 追踪静态层文件 hash，检测 prompt cache 失效。注册为 PreAgentStart 钩子，每次 session 启动时自动运行。有变更时输出警告，无变更静默通过。
---

# Cache Monitor — 静态层 Hash 追踪

## 功能

每次 session 启动时自动检测静态层文件是否变更，帮助追踪哪些操作导致 prompt cache 失效。

## 追踪的文件

| 文件 | 说明 |
|------|------|
| SOUL.md | 角色设定 |
| AGENTS.md | 行为规则 |
| TOOLS.md | 本地配置 |
| USER.md | Boss 信息 |
| IDENTITY.md | 身份元数据 |
| HEARTBEAT.md | 心跳任务 |
| STATIC.md | 核心规则摘要 |

## 状态文件

`~/.openclaw/workspace/.cache-monitor.json`

```json
{
  "last_updated": "2026-04-04T00:10:00",
  "hashes": {
    "SOUL.md": {"hash": "sha256...", "size": 2741, "exists": true},
    "AGENTS.md": {"hash": "sha256...", "size": 12000, "exists": true}
  },
  "change_log": [
    {"date": "2026-04-03", "file": "AGENTS.md", "reason": "追加工具权限分层规则"}
  ]
}
```

## 变更记录格式

有变更时输出：
```
⚠️ Cache 失效：[文件名] 已变更（上次变更原因：[原因]），本次对话静态层需重新计算
```

无变更：静默通过，无任何输出。

## 核心文件

| 文件 | 作用 |
|------|------|
| `scripts/cache_monitor.py` | Hash 计算 + 变更检测 |
| `~/.openclaw/workspace/.cache-monitor.json` | 状态持久化 |

## 命令

```bash
# 初始化/更新 hash 记录
python3 ~/.openclaw/workspace/skills/cache-monitor/scripts/cache_monitor.py --init

# 检查变更（默认）
python3 ~/.openclaw/workspace/skills/cache-monitor/scripts/cache_monitor.py --check
```

## 注册方式

通过 OpenClaw 的 `PreAgentStart` 钩子自动触发，无需手动运行。
