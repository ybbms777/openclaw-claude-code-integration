# evolve

## 用途

把 LanceDB 里反复出现的高频记忆，提炼成 AGENTS.md 的永久行为规则。

来源：Everything Claude Code (ECC) 的 Continuous Learning v2 思路，
针对 OpenClaw 的记忆系统重新实现。

---

## 安装方式

复制到 `~/.openclaw/workspace/skills/evolve/SKILL.md`，
然后发给你的 OpenClaw：

```
帮我创建 /evolve 命令的执行脚本，注册为 slash command。
```

## Hook 注册

已注册 `gateway:startup` 钩子：`~/.openclaw/hooks/evolve-hook/`

钩子在 gateway 启动时输出提醒（evolve.py 本身仍需手动 `/evolve` 触发）。

---

## 使用方式

```
/evolve
```

手动触发，**不建议设成自动**。建议每 2-4 周触发一次。

---

## 执行流程

```
查询高频记忆
（过去30天，被检索≥3次，importance≥0.7）
    ↓
语义聚类
（相似度≥0.75 归为一簇，使用 bge-m3）
    ↓
生成候选规则列表
（NEVER/MUST/ALWAYS 格式）
    ↓
发给用户确认
（每次最多10条）
    ↓
用户逐条回复「写入」或「跳过」
    ↓
写入 AGENTS.md 对应段落
打标签 evolved: true，避免重复提交
    ↓
汇总：写入 N 条，跳过 M 条
```

---

## 候选规则格式

```
#1 [MUST] ## 工具调用协议
   来源：
     1. 工具失败后直接换工具导致问题被掩盖（3次）
     2. 重试未改变策略仍然失败（2次）
   候选规则：MUST 在工具失败后改变策略再重试，最多2次

回复：写入 或 跳过
```

---

## 过滤规则（自动排除以下内容）

1. **今日新建记忆** — 当天的操作指令不纳入提炼
2. **对话碎片** — 包含疑问/抱怨语气的条目（「为什么」「你玩我呢」等）
3. **AGENTS.md 已有规则** — 与现有规则相似度 ≥ 85% 的跳过
4. **已提炼过的记忆** — 标有 `evolved: true` 的跳过

---

## 注意事项

**必须人工确认，NEVER 自动写入。**

候选规则的质量取决于记忆质量。建议在 memory-compaction 跑完（碎片清理后）再触发 /evolve，提炼质量更高。

记忆积累越多，/evolve 的价值越大。刚开始使用时候选规则较少是正常的。
