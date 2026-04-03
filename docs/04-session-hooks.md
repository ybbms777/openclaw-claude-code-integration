# Session Hooks 注册说明

## 概述

本项目的 session_end / session_start 相关脚本已注册为 OpenClaw 钩子，路径：`~/.openclaw/hooks/`。

> ⚠️ **重要限制**：OpenClaw 当前版本的 `session:end` 和 `PreAgentStart` 钩子尚未实现（列为 planned 事件）。
> 本项目使用现有内置钩子作为近似替代，存在以下限制：
> - `self_eval.py` 仅在用户显式执行 `/stop` 时触发，session 超时/断连时不触发
> - `cache_monitor.py` 在 agent 初始化阶段触发，早于 session 正式启动

## 已注册的钩子

| 钩子名称 | 触发事件 | 对应脚本 | 功能 |
|---------|---------|---------|------|
| `self-eval-hook` | `command:stop` | `skills/self-eval/scripts/self_eval.py` | 检测异常写入 reflection 记忆 |
| `cache-monitor-hook` | `agent:bootstrap` | `skills/cache-monitor/scripts/cache_monitor.py` | 检测静态层文件 hash 变更 |
| `evolve-hook` | `gateway:startup` | — | 输出 /evolve 手动触发提醒 |

## 手动验证方法

```bash
# 1. 查看钩子是否被发现
openclaw hooks list | grep -E "self-eval|cache-monitor|evolve"

# 2. 查看钩子详情
openclaw hooks info self-eval-hook
openclaw hooks info cache-monitor-hook
openclaw hooks info evolve-hook

# 3. 测试 self_eval（模拟 /stop 后的 session）
python3 skills/self-eval/scripts/self_eval.py

# 4. 测试 cache_monitor --check
python3 skills/cache-monitor/scripts/cache_monitor.py --check

# 5. 查看 gateway 日志中的钩子输出
tail -f ~/.openclaw/gateway.log | grep -E "self-eval-hook|cache-monitor-hook|evolve-hook"

# 6. 重启 gateway 使新钩子生效
openclaw gateway restart
```

## 触发场景说明

### self-eval-hook（command:stop）

```
用户发送 /stop
    ↓
command:stop 事件触发
    ↓
self_eval.py 读取 session transcript
    ↓
检测用户纠正 / 工具失败 / 上报触发
    ↓
有异常 → 写入 reflection 记忆到 LanceDB
无异常 → 静默退出
```

### cache-monitor-hook（agent:bootstrap）

```
新 session 启动（用户发送任意消息）
    ↓
agent:bootstrap 事件触发
    ↓
cache_monitor.py --check 计算静态层 hash
    ↓
与上次记录对比
    ↓
有变更 → 输出 Cache 失效警告
无变更 → 静默通过
```

### evolve-hook（gateway:startup）

```
Gateway 启动时
    ↓
gateway:startup 事件触发
    ↓
输出 /evolve 手动触发提醒（不发消息，仅日志）
    ↓
实际 /evolve 仍需手动触发
```

## 限制与已知问题

1. **session:end 不存在**：`self_eval.py` 无法在 session 自然结束时自动运行。只能依赖用户主动 `/stop`。
2. **PreAgentStart 不存在**：`cache_monitor.py` 触发时机比预期略早，但功能不受影响。
3. **subagent session 跳过**：所有钩子均跳过 subagent session，避免触发噪音。

## 配置持久化

钩子启用状态保存在 `~/.openclaw/openclaw.json` 的 `hooks.internal.entries` 中。
如需在新机器上重建：

```bash
openclaw hooks enable self-eval-hook
openclaw hooks enable cache-monitor-hook
openclaw hooks enable evolve-hook
```
