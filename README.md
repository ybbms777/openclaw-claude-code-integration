# OpenClaw × Claude Code 精华整合指南

> 把 Claude Code 源码泄露里最有价值的工程思路，移植到 OpenClaw 个人助手体系中。
> 
> 本仓库包含：完整的配置文件示例、可直接复制的 skill 指令、以及背后的设计思路说明。

---

## 背景

2026 年 3 月 31 日，Claude Code 的完整 TypeScript 源码通过 npm sourcemap 意外泄露。源码揭示了几个此前不为人知的内部系统：

- **autoDream**：后台自动整合记忆的子 agent
- **KAIROS**：始终在线的主动感知循环
- **静态/动态提示词分离**：通过 `DYNAMIC_BOUNDARY` 节省 prompt cache 费用
- **压缩失败熔断**：防止 auto-compact 无限循环消耗 API

这些机制本质上是生产级 AI Agent 的工程经验。本仓库把其中对 OpenClaw 用户真正有价值的部分提炼出来，整理成可直接使用的配置。

---

## 适用对象

- **OpenClaw 用户**：文件可直接复制使用，按说明调整个人信息即可
- **泛 AI Agent 开发者**：设计思路和提示词架构可移植到其他框架

---

## 整合内容总览

| 模块 | 来源 | 解决的问题 |
|---|---|---|
| 压缩失败熔断（compact-guardian） | Claude Code 源码 | auto-compact 失败导致记忆碎片堆积 |
| 静态/动态提示词分离 | Claude Code 架构 | 每次对话重复计算静态 token，浪费费用 |
| 工具调用失败协议 | Claude Code 系统提示词 | agent 在工具失败时无限重试或静默绕过 |
| 上报触发规则 | Claude Code 系统提示词 | agent 自作主张执行不可逆操作 |
| 文件优先级声明 | Claude Code 提示词架构 | 规则冲突时 agent 行为不可预测 |
| memory-compaction cron | Claude Code autoDream 思路 | LanceDB 记忆只进不出，碎片堆积 |
| /evolve 命令 | ECC Continuous Learning v2 | 高频记忆无法升华为永久行为规则 |

---

## 目录结构

```
.
├── README.md                          # 本文件
├── SOUL.md                            # 完整示例：人格与表达规范
├── AGENTS.md                          # 完整示例：行为规则与协议
├── skills/
│   ├── compact-guardian/SKILL.md      # 压缩失败熔断
│   ├── memory-compaction/SKILL.md     # LanceDB 定期整理
│   └── evolve/SKILL.md                # /evolve 命令
└── docs/
    ├── 01-architecture.md             # 设计思路详解
    ├── 02-prompt-engineering.md       # 提示词工程对比分析
    ├── 03-memory-system.md           # 记忆系统架构说明
    └── 04-session-hooks.md           # 钩子注册说明（self_eval / cache_monitor / evolve）
```

---

## 快速开始

### 1. 配置文件

把 `SOUL.md` 和 `AGENTS.md` 复制到你的 OpenClaw workspace：

```bash
cp SOUL.md ~/.openclaw/workspace/SOUL.md
cp AGENTS.md ~/.openclaw/workspace/AGENTS.md
```

按你的实际情况修改 `SOUL.md` 第二章的中文表达规范（或替换成你自己的语气偏好），以及 `AGENTS.md` 里的 BDX 相关规则。

### 2. Skills 安装

```bash
# 压缩失败熔断
cp -r skills/compact-guardian ~/.openclaw/workspace/skills/

# 记忆整理 cron
cp -r skills/memory-compaction ~/.openclaw/workspace/skills/

# /evolve 命令
cp -r skills/evolve ~/.openclaw/workspace/skills/
```

然后让你的 OpenClaw 注册这些 skill：

```
帮我注册以下三个 skill 并确认生效：compact-guardian、memory-compaction、evolve
```

### 3. 静态/动态提示词分离

把以下指令发给你的 OpenClaw：

```
帮我在 Gateway 的 system prompt 组装逻辑里，在静态内容（SOUL.md、AGENTS.md、TOOLS.md、USER.md、HEARTBEAT.md）和动态内容（MEMORY.md、LanceDB 检索结果）之间加入分隔标记 <!-- DYNAMIC_BOUNDARY -->。改完后告诉我改动了哪个文件的哪几行。
```

---

## 核心设计说明

### 提示词分层架构

Claude Code 最值得借鉴的工程实践之一是**静态/动态分离**。

```
┌─────────────────────────────────┐
│         静态层（不随对话变化）        │
│  SOUL.md / AGENTS.md / TOOLS.md  │
│  USER.md / IDENTITY.md           │
│  HEARTBEAT.md                    │
├────── <!-- DYNAMIC_BOUNDARY --> ──┤
│         动态层（每次刷新）           │
│  MEMORY.md                       │
│  LanceDB 检索结果                  │
│  当前对话上下文                     │
└─────────────────────────────────┘
```

静态层内容稳定，命中 prompt cache，不重复计费。动态层每次对话按需注入。

### 提示词即协议（Prompt-as-Protocol）

Claude Code 的系统提示词不写模糊指令，只写明确协议：

```markdown
# 错误写法（模糊）
尽量小心处理 BDX 生产参数

# 正确写法（协议）
NEVER 直接修改 BDX 生产参数，必须先生成变更计划等用户确认
```

`AGENTS.md` 里的所有规则应遵循这个原则：禁止行为用 NEVER，必须执行用 MUST，每次都要用 ALWAYS。

### 工具调用失败协议

Claude Code 对每一种失败场景都有明确的处理路径，不依赖 agent 自行判断：

```markdown
任何工具调用失败时：
1. 先用记忆系统搜索相关关键词
2. 最多重试 2 次，每次改变策略
3. 2 次后仍失败：停止，报告原因，等待指示
4. NEVER 自动切换其他工具绕过问题
5. 关键业务工具失败：立即告警，不重试
```

没有这个协议，agent 在工具卡住时会一直重试直到 token 耗尽。

### 记忆系统三层架构

```
对话记录
    ↓ autoCapture（每轮最多3条）
LanceDB 原子记忆
    ↓ memory-compaction（每周整理）
高质量记忆条目
    ↓ /evolve（每2-4周手动触发）
AGENTS.md 永久规则
```

这三层对应三个不同的时间尺度：实时、周级、月级。缺少任何一层都会导致记忆系统退化。

---

## 与 Claude Code / ECC 的差距分析

| 维度 | 本方案 | Claude Code | ECC |
|---|---|---|---|
| 个性/语气定义 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 记忆系统 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 工具调用协议 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 上报/熔断机制 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| 提示词分层结构 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| 主动感知（Heartbeat） | ⭐⭐⭐⭐ | ⭐⭐（未发布）| ⭐⭐ |
| 规则进化（/evolve） | ⭐⭐⭐⭐ | ❌ | ⭐⭐⭐⭐⭐ |

---

## 注意事项

**关于泄露源码的使用：** 本仓库不包含任何 Claude Code 的原始源码，只提取了其中的工程思路和设计模式。Claude Code 源码的版权属于 Anthropic PBC。

**关于 /evolve 的使用频率：** 建议每 2-4 周手动触发一次，不要设成自动。候选规则需要人工确认，频率太高会产生噪音。

**关于 TOOLS.md：** 本仓库提供的 `AGENTS.md` 示例中不包含真实账号、密码、API Key。请在你自己的 `TOOLS.md` 里配置这些信息，不要提交到公开仓库。

---

## 致谢

- Claude Code 源码发现者：Chaofan Shou（@Fried_rice）
- OpenClaw 项目：Peter Steinberger（@steipete）
- Everything Claude Code：affaan-m

---

## License

MIT — 配置文件和 skill 模板可自由使用和修改。
