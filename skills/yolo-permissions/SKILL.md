---
name: yolo-permissions
description: YOLO权限分类器 — 工具调用前的AI辅助安全判断，参考Claude Code的auto mode设计
---

# YOLO Permissions — 工具调用安全分类器

## 背景

Claude Code 在 auto 模式下，每次工具调用前会经过一个 YOLO 分类器判断风险等级：
- **LOW**：直接放行
- **MEDIUM**：快速一阶段XML判断
- **HIGH**：两阶段thinking判断，阻止则抛异常

本 skill 用 MiniMax-M2 实现类似能力，作为 OpenClaw 的安全辅助层。

## 核心机制

### 风险等级判断

当工具调用进入决策点时，调用 `yolo_classifier.py`：

```python
python3 yolo_classifier.py "bash" '{"command": "rm -rf /tmp/test"}'
# 输出：{"risk": "HIGH", "reason": "rm -rf递归删除，且路径为/tmp/test有风险"}
```

### 三级分类标准

**LOW（直接放行）：**
- 只读命令（ls/cat/grep/git status）
- 路径在当前项目目录下的小文件操作
- 工具本身声明无安全相关性的

**MEDIUM（一阶段XML快速判断）：**
- 写入操作（edit/write/mkdir）
- 跨目录文件操作
- 网络请求（curl/fetch）

**HIGH（两阶段判断）：**
- 破坏性操作（rm/rmdir/drop）
- 外部发送（email/webhook/post）
- 认证凭据操作
- 涉及生产配置

### 与 AGENTS.md 的关系

AGENTS.md 定义了静态规则（NEVER/MUST），本 skill 在规则之外加一层AI辅助判断：
- 静态规则优先于AI判断（规则已明确的，按规则走）
- 静态规则未覆盖的 → 调用YOLO分类器
- AI判断为HIGH → 阻止+理由展示
- AI判断为LOW → 自动放行

## 工具调用集成

在工具执行前，Agent应调用：

```
当执行任何写入/删除/外部发送操作前，
先问自己：这个操作的直接后果是什么？是否不可逆？
如果是不可逆操作，调用 /yolo-check <工具名> <参数>
```

## 使用命令

```bash
# 检查单次工具调用风险
python3 scripts/yolo_classifier.py <tool_name> '<json_params>'

# 交互模式：持续检查
python3 scripts/yolo_classifier.py --interactive
```

## 输出格式

```json
{
  "tool": "bash",
  "params": {"command": "rm -rf /tmp/test"},
  "risk": "HIGH",
  "reason": "rm -rf递归删除，且路径为/tmp/test有风险",
  "action": "block",
  "suggestion": "用 trash 命令替代 rm，或先确认路径"
}
```
