# 新手快速开始指南

欢迎使用 OpenClaw × Claude Code 集成方案！本指南帮助你在 5 分钟内快速上手。

## 📝 前置条件

- OpenClaw 已安装 (`openclaw --version` 能显示版本号)
- Python 3.10+
- 基础命令行知识
- （可选但推荐）Telegram Bot 账户

## ⚡ 5 分钟快速安装

### 1️⃣ 克隆仓库（1 分钟）

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/openclaw-claude-code-integration.git
cd openclaw-claude-code-integration
```

### 2️⃣ 配置 API 凭证（2 分钟）

```bash
# 复制配置模板
cp .env.template ~/.openclaw/.env

# 编辑配置（最少需要 SILICONFLOW_API_KEY）
nano ~/.openclaw/.env  # 或用你喜欢的编辑器

# 设置文件权限
chmod 600 ~/.openclaw/.env
```

详见 [SETUP_ENV.md](SETUP_ENV.md) 了解如何获取各个 API Key。

### 3️⃣ 安装技能（2 分钟）

```bash
# 复制所有 skills 到 OpenClaw
cp -r skills/* ~/.openclaw/workspace/skills/

# 重启 Gateway 载入新 skills
openclaw gateway restart

# 验证安装
openclaw skills list | grep -E "self-eval|evolve|compact|yolo|safe"
```

完成！🎉

## 🎯 接下来做什么

### 第一次运行（重要）

1. 复制配置文件到 workspace：
```bash
cp SOUL.md ~/.openclaw/workspace/SOUL.md
cp AGENTS.md ~/.openclaw/workspace/AGENTS.md
```

2. **编辑 AGENTS.md**：
   - 第 11-140 行是核心行为规则，建议先看一遍
   - 第 220-312 行有 11 条"用户纠正检测规则"，这是项目的学习能力
   - 其他部分保持原样即可

3. **编辑 SOUL.md**：
   - 如果你不使用中文，删除"第二章：中文表达规范"
   - 根据你的工作风格修改"工作流程"和"技术工具偏好"

### 日常使用

**自动运行的**（无需操作）：
- ✅ Session 结束时自动评估异常 (`self_eval`)
- ✅ 每周日 3 AM 自动整理记忆 (`memory-compaction`)
- ✅ Bash 命令自动安全检查 (`safe-command-execution`)

**手动触发的**（按需操作）：
- 📋 每 2-4 周运行一次 `/evolve` 提炼高频规则
- 📊 当上下文接近满时运行 `/smart-compact` 智能压缩
- 🔍 每月运行一次 `rule_conflict_detector.py` 检查规则冲突

## 🐛 常见问题

### Q: 安装后 Telegram 通知收不到？

**A:** 检查以下步骤：
1. `~/.openclaw/.env` 中 `TG_BOT_TOKEN` 和 `TG_CHAT_ID` 是否填写
2. 运行测试：`python3 skills/compact-guardian/scripts/notify_telegram.py "test message"`
3. 检查日志：`openclaw logs -f`

### Q: Embedding 模型错误（SILICONFLOW_API_KEY no set）？

**A:**
1. 在 https://cloud.siliconflow.cn 申请免费 API Key
2. 填入 `~/.openclaw/.env` 的 `SILICONFLOW_API_KEY`
3. 或使用 `MINIMAX_API_KEY` 作为备选（需付费）

### Q: memory-compaction 说 LanceDB 不存在？

**A:** LanceDB 会在第一次自动创建。如果报错，手动创建目录：
```bash
mkdir -p ~/.openclaw/memory/lancedb-pro
```

### Q: 我想要定制 AGENTS.md 规则？

**A:** 编辑 `~/.openclaw/workspace/AGENTS.md` 即可。修改格式：
```markdown
### 规则名称

NEVER 做某事，因为...
MUST 先做A再做B
ALWAYS 检查...

来源：evolve/用户要求/手工定义
```

### Q: 如何验证配置是否正确？

**A:** 运行诊断工具：
```bash
# 检查 MEMORY.md 容量
python3 skills/memory-compaction/scripts/memory_capacity_monitor.py

# 检查 AGENTS.md 规则冲突
python3 skills/smart-compact/scripts/rule_conflict_detector.py

# 检查 Telegram 连接
python3 skills/compact-guardian/scripts/notify_telegram.py "Diagnostic test"
```

## 📚 深入学习

### 理解核心概念

1. **SOUL.md**（进阶）
   - 定义你的个性和工作风格
   - 不只是表达规范，更是行为准则

2. **AGENTS.md**（关键）
   - 11 条用户纠正检测规则是机器学习（evolve）的基础
   - 优先级定义确保规则冲突时的决策透明

3. **记忆三层架构**（高阶）：
   - 实时层：autoCapture 记录原子事实
   - 周级层：memory-compaction 清理低价值、合并碎片
   - 永久层：/evolve 提炼高频模式成规则

### 阅读设计文档

- `docs/01-architecture.md` — 系统架构和决策背景
- `docs/02-prompt-engineering.md` — 如何写出好的规则
- `docs/03-memory-system.md` — 记忆系统深入解析
- `docs/04-session-hooks.md` — 如何扩展 hooks

### 参考实现

所有 skills 的源代码都在 `skills/*/scripts/` 里，可以作为参考学习如何集成新的自动化流程。

## 🆘 获取帮助

### 遇到问题？

1. **检查日志**：`openclaw logs -f` 实时查看错误
2. **查看诊断**：运行上面的诊断工具
3. **检查配置**：`cat ~/.openclaw/.env | grep -v "^#"` 看有没有填写
4. **官方 Issue**：https://github.com/openclaw/openclaw/issues

### 想要贡献改进？

1. Fork 这个仓库
2. 创建 feature branch：`git checkout -b feature/your-improvement`
3. 推送  PR（不包含个人信息！）
4. 等待 review

## 📡 重要：数据隐私

⚠️ **TOOLS.md 从不提交到 git**：
- TOOLS.md 包含你的 API Keys、账号配置、私密设置
- .gitignore 已配置排除，但再次确认：永不提交

⚠️ **定期检查敏感信息**：
```bash
# 扫描是否不小心提交了密钥
git log -p | grep -i "api.*key\|token\|password"
```

## 🎓 学习路径建议

**Week 1**: 装好系统，跑通基本流程  
**Week 2-3**: 编辑 SOUL.md 和 AGENTS.md，定制适合自己的规则  
**Week 4+**: 使用 `/evolve` 命令从实际工作中学习新规则，持续改进  

---

**还有问题？** 建议阅读 [MANUAL.md](MANUAL.md) 查看完整操作流程。

**祝你使用愉快！** 🚀
