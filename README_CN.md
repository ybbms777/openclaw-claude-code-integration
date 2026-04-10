<div align="center">

# 🦞 OpenClaw × Claude Code · 精华整合

**[OpenClaw](https://github.com/openclaw/openclaw) AI 智能体的 Claude Code 工程实践移植**

*把 Claude Code 源码里最有价值的工程实践，移植到你的个人 AI 助手。*

[![OpenClaw](https://img.shields.io/badge/OpenClaw-Ready-blue)](https://github.com/openclaw/openclaw)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-源码泄露-green)](https://github.com/Fried-Chicken/Claude-Code)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/YOUR_GITHUB_USERNAME/openclaw-claude-code-integration)](https://github.com/YOUR_GITHUB_USERNAME/openclaw-claude-code-integration/stargazers)

[English](README.md) | [简体中文](README_CN.md)

</div>

---

## 为什么做这个？

**2026 年 3 月 31 日**，Claude Code 完整 TypeScript 源码意外泄露。源码揭示了一套生产级 AI Agent 核心工程系统——从未出现在官方文档里：

| 系统 | 作用 |
|------|------|
| **autoDream** | 24h+5sessions 自动整合记忆 |
| **YOLO 分类器** | Bash 命令四级风险评估，fail-closed |
| **压缩熔断机制** | 防止 auto-compact 死循环 |
| **四层 Bash 安全** | AST 解析 → 正则验证 → 权限规则 → OS 沙箱 |

这套系统背后是 **$2.5B ARR 商业产品**在真实生产环境踩过的坑。**本仓库**把对 OpenClaw 用户真正有价值的部分提炼出来，整理成可直接安装的 skill 和配置。

---

## ✨ 你得到了什么

### 🔧 8 个可安装的 Skills

| Skill | 功能 | 触发方式 |
|-------|------|---------|
| **self-eval** | 每次 session 结束检测异常，写入 reflection 记忆 | `command:stop` hook |
| **evolve** | 从 reflection 记忆提炼 NEVER/MUST 规则 | 手动或 `gateway:startup` |
| **memory-compaction** | 每周自动整理 LanceDB，删除低价值记忆 + 合并相似碎片 | cron（每周日凌晨3点） |
| **compact-guardian** | 压缩连续3次失败后熔断，停用自动压缩 + Telegram 告警 | 自动监控 |
| **cache-monitor** | agent:bootstrap 时检测 prompt cache 是否失效 | `agent:bootstrap` hook |
| **smart-compact** | LLM 摘要压缩 session 文件（双阶段输出） | 手动 |
| **yolo-permissions** | 三级权限分类（LOW/MEDIUM/HIGH），fail-closed | 自动集成到 exec |
| **safe-command-execution** | Bash AST 解析 + 正则验证，检测危险命令 | 自动集成到 exec |

### 🧪 测试套件

**94 个 pytest 测试**，覆盖 bash_guard / self_eval / evolve / yolo_classifier

### 📜 配置示例

- `SOUL.md` — 人格与表达规范（含 Akino 规则）
- `AGENTS.md` — 完整行为协议（含 11 条用户纠正检测规则）
- `docs/` — 4 篇设计文档，解释背后的工程思路

---

## 系统架构

```
用户对话
    │
    ├── command:stop ──→ self_eval.py ──→ LanceDB (reflection)
    │
    ├── agent:bootstrap ──→ cache_monitor.py ──→ 静态层变更检测
    │
    └── gateway:startup ──→ evolve 提醒 ──→ 手动触发规则提炼

─────────────────────────────────────────────────

LanceDB memories 表
    │
    ├── 实时：autoCapture（memory-lancedb-pro 插件）
    │
    ├── 每周 cron ──→ memory_compaction.py ──→ 备份 + 删除 + 合并
    │
    └── 手动 evolve ──→ 规则写入 AGENTS.md
```

---

## 快速安装

```bash
# 克隆仓库
git clone https://github.com/YOUR_GITHUB_USERNAME/openclaw-claude-code-integration.git
cd openclaw-claude-code-integration

# 安装所有 skills
cp -r skills/* ~/.openclaw/workspace/skills/

# 复制配置文件（按需修改）
cp SOUL.md ~/.openclaw/workspace/SOUL.md
cp AGENTS.md ~/.openclaw/workspace/AGENTS.md

# 重启 Gateway
openclaw gateway restart
```

确认生效：
```bash
openclaw skills list | grep -E "self-eval|evolve|compact|cache|yolo|safe"
```

---

## 核心设计思路

### 提示词即协议（Prompt-as-Protocol）

> 不要写模糊指令，只写明确协议。

```markdown
# ❌ 模糊指令（无效）
尽量小心处理涉及资金的操作

# ✅ 明确协议（可执行）
NEVER 直接修改涉及资金/仓位/外部发送的操作，必须先生成变更计划等用户确认
```

### 静态/动态分层（Prompt Cache 优化）

```
┌─────────────────────────────────────────┐
│  静态层（每次对话不变化，命中 cache）   │
│  SOUL.md / AGENTS.md / TOOLS.md          │
│  USER.md / IDENTITY.md                  │
│  HEARTBEAT.md                           │
├────────── <!-- DYNAMIC_BOUNDARY --> ─────┤
│  动态层（每次刷新，按需注入）            │
│  MEMORY.md                              │
│  LanceDB 检索结果                       │
└─────────────────────────────────────────┘
```

在 HEARTBEAT.md 和 MEMORY.md 之间插入 `<!-- DYNAMIC_BOUNDARY -->` 分隔符，边界前内容稳定命中 prompt cache，每次节省约 6,000-8,000 tokens。

### 支持 Prompt Cache 的模型

| 模型 | 缓存机制 | 配置方式 |
|------|---------|---------|
| **Claude**（Anthropic API） | 原生自动缓存 | 无需配置 |
| **GPT-4o**（OpenAI API） | 自动缓存 | 无需配置（>1024 tokens 自动生效） |
| **Gemini 1.5 Pro** | 显式 Context Caching | 需手动创建缓存 |
| **DeepSeek V3/R1**（SiliconFlow） | 支持 | SiliconFlow 上已配置 |

> **当前 OpenClaw（MiniMax）：** 不支持 prompt cache 自动复用。静态/动态分层架构已就绪，模型支持后自动生效。

---

## 目录结构

```
openclaw-claude-code-integration/
├── README.md / README_CN.md           # 本文件（双语）
├── SOUL.md                            # 人格与表达规范
├── AGENTS.md                          # 完整行为协议（11条规则）
├── MANUAL.md                          # 使用手册
├── SKILL.md                           # Skill 开发规范
├── skills/
│   ├── self-eval/                   # 自我评估脚本
│   ├── evolve/                       # 规则提炼（含 learnings 整合）
│   ├── memory-compaction/            # LanceDB 定期整理（access_count 权重）
│   ├── compact-guardian/              # 压缩熔断
│   ├── cache-monitor/               # Prompt cache 监控
│   ├── smart-compact/               # LLM 摘要压缩（双阶段输出）
│   ├── yolo-permissions/            # 三级权限分类
│   └── safe-command-execution/       # Bash AST 安全层
├── tests/                            # pytest 测试套件（94测试）
└── docs/
    ├── 01-architecture.md           # 设计思路详解
    ├── 02-prompt-engineering.md     # 提示词工程对比分析
    ├── 03-memory-system.md           # 记忆系统架构
    └── 04-session-hooks.md          # 钩子注册说明
```

---

## 与 Claude Code 原文的对比

| 维度 | Claude Code 源码 | 本整合方案 | 状态 |
|------|----------------|-----------|------|
| autoDream | ✅ 24h+5sessions 自动整合 | ❌ 需 OpenClaw 支持 `session:end` 钩子 | [已向官方提 issue](https://github.com/openclaw/openclaw/issues/60514) |
| YOLO Bash 分类 | ✅ 四级风险，fail-closed | ✅ 已实现 | ✅ |
| 四层 Bash 安全 | ✅ AST+正则+权限+沙箱 | ✅ AST+正则已实现 | ⚠️ 部分 |
| 工具失败协议 | ✅ 明确处理路径 | ✅ 写入 AGENTS.md | ✅ |
| 压缩熔断 | ✅ auto-compact 死循环保护 | ✅ 已实现 | ✅ |
| evolve 规则提炼 | ❌ 无 | ✅ 手动触发 | ✅ |
| Fork cache 复用 | ✅ 子 agent 复用父 prompt cache | ❌ MiniMax 不支持 | ❌ |

---

## ⚠️ 已知限制

1. **`session:end` 钩子**：OpenClaw 当前版本不支持，已向[官方提 issue](https://github.com/openclaw/openclaw/issues/60514)。
2. **Fork cache 复用**：Claude Code 支持，MiniMax 不支持。
3. **OS 沙箱层**：Bash AST 安全层只实现了 AST 解析+正则验证，bwrap 沙箱需系统级支持。

---

## ⚠️ 免责声明

本仓库**不包含任何 Claude Code 原始源码**，只提取了工程思路和设计模式。Claude Code 源码版权属于 Anthropic PBC。

---

## 致谢

- Claude Code 源码泄露发现：[Chaofan Shou](https://twitter.com/Fried_rice)
- OpenClaw 项目：[Peter Steinberger](https://twitter.com/steipete)
- Compound Engineering 插件：[EveryInc](https://github.com/EveryInc)
- memory-lancedb-pro：[CortexReach](https://github.com/CortexReach)

---

## License

MIT — 配置文件和 skill 模板可自由使用和修改。
