# API 凭证配置指南

本项目使用多个第三方服务的 API。本指南说明如何安全地配置这些凭证。

## 🚀 快速开始

### 1. 创建环境变量文件

```bash
# 复制模板
cp .env.template ~/.openclaw/.env

# 编辑文件（添加你的凭证）
nano ~/.openclaw/.env
```

### 2. 获取各服务的 API Keys

#### Telegram 配置（可选但推荐）

用于接收 OpenClaw 的异常告警和压缩失败通知。

**获取步骤：**
1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令
3. 按提示给你的 bot 命名
4. 复制生成的 **token** → 填入 `TG_BOT_TOKEN`
5. 在 Telegram 中搜索 `@userinfobot`，它会告诉你你的 Chat ID → 填入 `TG_CHAT_ID`

```env
TG_BOT_TOKEN="your_token_here"
TG_CHAT_ID="your_chat_id_here"
```

#### SiliconFlow API（推荐，免费）

用于 embedding 生成（记忆向量化）。**免费额度充足，推荐优先使用。**

**获取步骤：**
1. 访问 https://cloud.siliconflow.cn
2. 注册账户
3. 进入控制台 → API Keys
4. 创建新 Key → 复制 → 填入 `SILICONFLOW_API_KEY`

```env
SILICONFLOW_API_KEY="sk_your_key_here"
```

**模型：** BAAI/bge-m3（推荐，速度快，效果好）

#### MiniMax API（可选，作为 Fallback）

当 SiliconFlow 不可用时的备选 embedding 和摘要生成服务。

**获取步骤：**
1. 访问 https://api.minimaxi.com
2. 注册账户
3. 获取 API Key
4. 填入 `MINIMAX_API_KEY`

```env
MINIMAX_API_KEY="sk-your_key_here"
```

## 🔐 安全最佳实践

### ✅ 推荐做法

```bash
# 1. 环境变量文件权限设置为仅自己可读
chmod 600 ~/.openclaw/.env

# 2. 永远不要提交 .env 文件到 git
# （.gitignore 已配置，但再次确认）

# 3. 定期轮换 API Keys
# - SiliconFlow / MiniMax 控制台里可以禁用旧 Key

# 4. 使用 least-privilege 原则
# - 每个 Key 只启用需要的权限
```

### ❌ 禁止做法

```bash
# ❌ 永远不要在代码中硬编码 API Key
# ❌ 永远不要把 .env 文件提交到 git（即使是内部仓库）
# ❌ 永远不要把 API Key 分享给他人
# ❌ 永远不要在公开的 GitHub Issue / 讨论中粘贴 Key
```

## 🔄 环境变量加载流程

OpenClaw skills 在启动时会按以下顺序加载凭证：

```
1. ~/.openclaw/.env          (推荐：首选位置)
2. /etc/openclaw/.env        (系统级配置)
3. 环境变量（命令行 export） (临时变量)
4. 硬编码默认值（空字符串）   (如果上面都没有)
```

## 📋 检查清单

- [ ] 复制了 `.env.template` 为 `~/.openclaw/.env`
- [ ] 填入了 `TG_BOT_TOKEN` 和 `TG_CHAT_ID`（Telegram）
- [ ] 填入了 `SILICONFLOW_API_KEY`（embedding，优先级最高）
- [ ] 填入了 `MINIMAX_API_KEY`（fallback 服务，可选）
- [ ] 设置了权限：`chmod 600 ~/.openclaw/.env`
- [ ] 验证了配置：使用 `source ~/.openclaw/.env` 然后 `echo $TG_BOT_TOKEN`

## 🧪 测试配置

验证 API 凭证是否正确加载：

```bash
# 测试 Telegram
python3 skills/compact-guardian/scripts/notify_telegram.py "Test message from OpenClaw"

# 测试 SiliconFlow embedding
python3 -c "
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / '.openclaw' / 'workspace' / 'skills'))
# 测试代码会在这里运行
"
```

## 🆘 常见问题

### Q: 我没有 Telegram，是否必须配置？

**A:** 不必须。Telegram 只用于异常告警。如果不配置，系统仍能正常运行，只是错误时不会收到通知。

### Q: SiliconFlow 和 MiniMax 都不配置行吗？

**A:** 不行。embedding 生成对 memory-lancedb-pro 插件是必须的。必须至少配置其中一个。推荐优先使用 SiliconFlow（免费额度更充足）。

### Q: 如何知道 API Key 是否生效？

**A:** 检查 OpenClaw 的日志：

```bash
openclaw logs -f  # 实时查看日志
# 或查看保存的日志文件
tail -f ~/.openclaw/logs/gateway.log
```

如果看到 `[API ERROR]` 或 `401 Unauthorized` 等错误，说明 Key 不生效。

### Q: 能否使用环境变量而不是 .env 文件？

**A:** 可以。但不推荐，因为：
- `.env` 文件方便集中管理
- 环境变量容易被记录到 shell history
- `.gitignore` 已配置排除 `.env` 文件

## 📞 获取帮助

如果遇到配置问题，请：

1. 检查 ~/.openclaw/.env 文件是否存在且有正确的格式
2. 查看 OpenClaw 日志寻找错误信息
3. 确认 API Key 有效（在各服务的控制台里验证）
4. 尝试手动触发脚本来测试 API 连接

---

**记住：秘钥安全无小事。良好的习惯今天，就是避免明天的宿醉。** 🔒
