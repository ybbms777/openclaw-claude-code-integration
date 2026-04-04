# OpenClaw 手动操作清单

本文件记录需要人工介入的操作，其余流程全部自动运行。
用 Obsidian 打开 ~/.openclaw/workspace/ 即可查看本文件。

---

## 需要定期手动执行的操作

### /evolve — 规则提炼
频率： 每 2-4 周一次
时机： memory-compaction 跑完之后效果最好
步骤：
1. 在 Telegram 发送 /evolve
2. 逐条回复「写入」或「跳过」
3. 完成后会收到「写入 N 条，跳过 M 条」汇总

注意： NEVER 让 agent 自动写入，必须人工确认每一条。

---

### /smart-compact — 智能压缩
频率： 上下文接近满时
步骤：
1. 发送 /smart-compact
2. agent 会告诉你检测到什么类型的 session、使用哪种策略
3. 回复「确认」后执行

---

### MEMORY.md 整理
频率： 文件超过 15,000 字符时
触发信号： openclaw doctor 提示 MEMORY.md 接近上限
步骤：
1. 发送：「帮我整理 MEMORY.md，删除过期内容，合并同主题碎片，保留策略参数、账号配置、长期偏好」
2. 确认整理报告（删了多少行、合并了多少条）

---

### GitHub 同步
频率： 每次重大配置变更后
步骤：
1. 发送：「帮我把最新的 AGENTS.md、SOUL.md 和新增 skill 推送到 GitHub YOUR_GITHUB_USERNAME/openclaw-claude-code-integration」
2. 确认 commit 内容后推送

---

## 自动运行的操作（无需介入）

| 操作 | 频率 | 触发方式 |
|---|---|---|
| memory-compaction | 每周日 03:00 | cron 自动 |
| cache-monitor | 每次 session 启动 | 钩子自动 |
| compact-guardian | 每次 compact 失败 | 钩子自动 |
| self-eval | 每次 session 结束 | 钩子自动 |
| 失败模式标记 | 工具失败时 | 钩子自动 |
| autoCapture | 每次对话 | 钩子自动 |
| Heartbeat 检查 | 每 30 分钟 | 心跳自动 |

---

## Obsidian 使用方式

打开 Obsidian → 选择「打开本地仓库」→ 路径选择 ~/.openclaw/workspace/

可以在 Obsidian 里直接查看和编辑：
- SOUL.md — 人格设定
- AGENTS.md — 行为规则
- MEMORY.md — 当前上下文
- MANUAL.md — 本文件
- skills/ — 所有 skill 定义
