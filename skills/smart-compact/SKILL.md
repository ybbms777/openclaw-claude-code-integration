---
name: smart-compact
description: 智能压缩决策 skill。根据当前 session 上下文类型自动选择压缩策略（BDX量化/代码开发/日常对话/混合），分析后报告预计保留率，等 Boss 确认后再执行。注册为 /smart-compact 命令。
allowed-tools: sessions_history, read_file, write_file
model: minimax-portal/MiniMax-M2.7
effort: medium
---

# Smart Compact — 智能压缩策略选择

## 功能

分析当前 session 上下文，自动选择压缩策略，避免一刀切压缩。

## 四种策略

| 策略 | 适用场景 | 保留 token |
|------|----------|-----------|
| A — BDX量化 | 回测数据、选股结果、因子分析、策略参数 | ~12k |
| B — 代码开发 | 大量代码块、git 操作、文件路径 | ~10k |
| C — 日常对话 | 普通对话、寒暄、过程性讨论 | ~6k |
| D — 混合session | 同时包含多种类型 | 按比例分配 |

## 执行流程

1. **分析**：读取当前 session 历史，判断策略类型
2. **报告**：发 Telegram 报告策略和预计保留率
3. **确认**：Boss 回复 `确认` 后执行压缩
4. **完成**：报告「压缩前 Xk → 压缩后 Yk，保留率 Z%」

## 核心文件

| 文件 | 作用 |
|------|------|
| `scripts/smart_compact.py` | 分析脚本（dry-run + 策略判断） |

## 命令注册

注册为 `/smart-compact` 命令，触发 `smart_compact.py --dry-run`。

## Dry-run 用法

```bash
python3 ~/.openclaw/workspace/skills/smart-compact/scripts/smart_compact.py --dry-run
```

## 策略详情

### 策略 A — BDX量化
**保留**：策略结论、参数配置、回测结果摘要、未完成任务  
**丢弃**：中间计算过程、重复数据行、调试输出

### 策略 B — 代码开发
**保留**：当前任务目标、已完成的改动摘要、待完成事项、关键报错  
**丢弃**：完整代码块（只保留函数签名）、成功执行的中间命令

### 策略 C — 日常对话
**保留**：用户的核心问题、结论性回答、待跟进事项  
**丢弃**：寒暄、重复确认、过程性讨论

### 策略 D — 混合session
**保留**：按各类型比例分配预算，优先保留最近 30% 内容
