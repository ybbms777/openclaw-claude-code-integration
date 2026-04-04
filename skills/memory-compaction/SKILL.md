---
name: memory-compaction
description: LanceDB 记忆压缩 cron skill。每周日凌晨 3:00 自动执行记忆整理：(1) 备份当前 LanceDB 到 backups/YYYY-MM-DD/（保留最近4份）；(2) 删除 importance &lt; 0.3 且 14 天未访问的记忆；(3) 用 SiliconFlow bge-m3 向量相似度 ≥ 0.85 的碎片合并成一条，保留最高 importance 的 L0 摘要；(4) 任何步骤出错立即停止并发 Telegram 告警；(5) 报告发送到 Telegram 主会话。激活条件：需要创建/维护/验证每周记忆压缩 cron job，或手动触发压缩时使用。
allowed-tools: memory_recall, memory_store, bash
model: minimax-portal/MiniMax-M2.7
effort: low
---

# Memory Compaction — 记忆压缩 Cron

## 功能

每周日 03:00 AM 自动执行记忆整理：

**Step 0 — 备份**
- 路径：`~/.openclaw/memory/lancedb-pro/backups/YYYY-MM-DD/`
- 保留最近 4 份，更早的自动删除
- 失败 → 立即停止，发 Telegram 告警

**Step 1 — 删除**
- 条件：`importance < 0.3` 且 `last_accessed_at < 14 天`
- 失败 → 立即停止，发 Telegram 告警

**Step 2 — 合并**
- 范围：同 scope 内，向量相似度 ≥ 0.85
- 方式：SiliconFlow `BAAI/bge-m3` + 贪心聚类
- 合并后保留最高 importance 的 L0 abstract
- 失败 → 立即停止，发 Telegram 告警

**Step 3 — 报告**
- 删除条数、合并簇数、最终记忆总数
- 备份路径发送到 Telegram

## 阈值

| 参数 | 值 |
|------|---|
| `importance_threshold` | 0.3 |
| `age_days_threshold` | 14 天 |
| `similarity_threshold` | 0.85 |
| `embedding_model` | `BAAI/bge-m3`（SiliconFlow） |
| `batch_size` | 8 |
| `max_backups` | 4 |

## 核心文件

| 文件 | 作用 |
|------|------|
| `scripts/memory_compaction.py` | 主脚本（备份 + 删除 + 合并 + 告警） |

## Cron Job

- **ID**: `memory-compaction-weekly`
- **时间**: 每周日 03:00 AM Asia/Shanghai
- **命令**: `python3 ~/.openclaw/workspace/skills/memory-compaction/scripts/memory_compaction.py --cron`

## 手动触发

```bash
# 完整执行（先备份，再压缩）
python3 ~/.openclaw/workspace/skills/memory-compaction/scripts/memory_compaction.py

# Dry-run（只分析，不执行写操作）
python3 ~/.openclaw/workspace/skills/memory-compaction/scripts/memory_compaction.py --dry-run

# Cron 模式（错误也发 Telegram）
python3 ~/.openclaw/workspace/skills/memory-compaction/scripts/memory_compaction.py --cron
```

## 熔断机制

任何步骤（备份 / 删除 / 合并 / 写入）出错，立即：
1. 停止后续所有步骤
2. Telegram 发送告警
3. 进程退出码 1

## 最近运行结果

- **2026-04-03（首次 dry-run）**: 见 Telegram 报告
