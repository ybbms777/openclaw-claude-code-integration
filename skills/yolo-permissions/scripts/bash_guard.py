#!/usr/bin/env python3
"""
bash_guard.py — Bash 命令安全验证层

基于 Claude Code 的 Stage 1 (AST解析) 设计思路，
用纯 Python 实现，用于 macOS/Linux 的命令安全检测。

检测目标：
1. 命令替换 $() / `` — 动态执行
2. 变量扩展 ${var} / $var — 内容不确定
3. 子shell () — 独立进程
4. 反斜杠转义混淆 — 解析器差异攻击
5. 引号未闭合 — 解析器差异攻击
6. 命令链 ; && || | — 多命令组合
7. 文件名通配符 * ? [ — 可能有意外匹配

用法：
  python3 bash_guard.py '<command>'
  echo $?  # 0=SAFE, 1=PARSE_FAILED, 2=UNSAFE
"""

import re
import sys
import shlex
import os


# ─── 危险模式定义 ──────────────────────────────────────────────────────────

class Threat:
    """威胁等级"""
    SAFE = 0
    PARSE_FAILED = 1  # 解析不了，可能是注入攻击
    UNSAFE = 2        # 已知危险模式


class BashGuardResult:
    def __init__(self, threat: int, level: str, reason: str, detail: str = ""):
        self.threat = threat
        self.level = level
        self.reason = reason
        self.detail = detail

    def __str__(self):
        icon = {0: "✅", 1: "⚠️", 2: "🚫"}
        return f"{icon.get(self.threat,'❓')} [{self.level}] {self.reason}"


def detect_threats(command: str) -> BashGuardResult:
    """
    主检测函数。检测顺序按照 Claude Code 的安全优先级。
    """
    if not command or not command.strip():
        return BashGuardResult(Threat.SAFE, "CLEAR", "空命令")

    original = command
    command = command.strip()

    # ── Stage 1: 命令替换检测 ──────────────────────────────────────────
    # $() 和 `` 都是动态执行，最危险
    if re.search(r'\$\([^)]+\)', command):  # $()
        return BashGuardResult(
            Threat.UNSAFE, "COMMAND_SUBSTITUTION",
            "命令替换 $() — 动态执行，内容不确定",
            re.search(r'\$\([^)]+\)', command).group()
        )

    if re.search(r'`[^`]+`', command):  # 反引号
        return BashGuardResult(
            Threat.UNSAFE, "BACKTICK_SUBSTITUTION",
            "反引号命令替换 — 动态执行",
            re.search(r'`[^`]+`', command).group()
        )

    # ── Stage 2: 变量扩展检测 ──────────────────────────────────────────
    # ${var} 有读写两种，$var 只读但内容不确定
    # 未定义的变量在某些 shell 下会变成空字符串，也可能被利用

    # 允许的安全变量（只读查询）
    SAFE_VARS = {
        "HOME", "USER", "PWD", "OLDPWD", "SHELL", "TERM", "PATH",
        "LANG", "LC_ALL", "EDITOR", "VISUAL", "SSH_TTY",
        "TERM_PROGRAM", "TERM_SESSION_ID",
        "PATH", "HOME", "USER", "LOGNAME",
    }

    # 检测未追踪的变量扩展（变量名不在白名单）
    # ${!} 是间接扩展，${#var} 是长度，${var:=default} 是赋值
    unsafe_var_pattern = re.compile(r'\$\{[^}]+\}')
    for match in unsafe_var_pattern.findall(command):
        var_name = match[2:-1]
        # 允许: 纯数字索引 $1 $2, 安全变量名, 长度 ${#var}, 属性 ${!var}
        if not re.match(r'^\d+$', var_name) and \
           var_name not in SAFE_VARS and \
           not var_name.startswith('!') and \
           not var_name.startswith('#') and \
           not var_name.startswith('?'):
            return BashGuardResult(
                Threat.UNSAFE, "UNTRACKED_VARIABLE",
                f"未追踪变量 {match} — 内容不确定",
                match
            )

    # 检测裸露的 $变量（简化判断）
    bare_var = re.search(r'(?<!\\)\$([a-zA-Z_][a-zA-Z0-9_]*)', command)
    if bare_var:
        var_name = bare_var.group(1)
        if var_name not in SAFE_VARS:
            return BashGuardResult(
                Threat.UNSAFE, "BARE_VARIABLE",
                f"未追踪裸变量 ${var_name} — 内容不确定",
                f"${var_name}"
            )

    # ── Stage 3: 子shell检测 ──────────────────────────────────────────
    # ( command ) 在子shell中执行，内容不确定
    if re.search(r'\(\s*[^)]+\)', command):
        # 排除 heredoc 中的子shell (常见无害)
        # heredoc 格式: (cat <<'EOF' ... EOF)
        if not re.search(r'<<[\'"]?\w+[\'"]?', command):
            return BashGuardResult(
                Threat.UNSAFE, "SUBSHELL",
                "子shell () — 独立进程执行",
                re.search(r'\(\s*[^)]+\)', command).group()
            )

    # ── Stage 4: 危险路径扩展 ──────────────────────────────────────────
    # 包含 ~ 但不在合法上下文中（~ 后面不是 / 或空格）
    # ~ 在某些上下文会扩展为 HOME，影响命令行为
    if re.search(r'~\S', command) and not re.search(r'~\s|~\s|$', command):
        return BashGuardResult(
            Threat.UNSAFE, "TILDE_EXPANSION",
            "波浪号路径扩展 — 目标路径不确定",
            re.search(r'~\S+', command).group()
        )

    # ── Stage 5: curl|wget pipe to shell 检测 ─────────────────────────────
    # curl/wget | bash 是典型攻击模式，单独拎出来优先检测
    if re.search(r'(curl|wget|nc|netcat)\s+[^\|]+\s*\|\s*(bash|sh|zsh|perl|python|ruby)', command, re.IGNORECASE):
        return BashGuardResult(
            Threat.UNSAFE, "PIPE_TO_SHELL",
            "curl/wget | bash — 下载并执行，是典型攻击模式",
            command[:80]
        )

    # ── Stage 6: 命令链检测 ─────────────────────────────────────────────
    # ; && || | 都是多命令执行，可能是注入
    chain_operators = re.findall(r'\|\||&&|\band\b|\bor\b|[;]', command)
    if chain_operators:
        # 检查第一个命令是否是已知危险命令
        first_cmd = command.split()[0] if command.split() else ""
        dangerous_first = {
            'curl', 'wget', 'nc', 'netcat', 'bash', 'sh', 'zsh',
            'python', 'ruby', 'perl', 'node', 'npm', 'eval', 'exec',
            'source', '.', 'mkdir', 'chmod', 'chown', 'dd',
        }
        if first_cmd in dangerous_first:
            return BashGuardResult(
                Threat.UNSAFE, "COMMAND_CHAIN",
                f"危险命令 {first_cmd} 后的命令链 — 可能是注入攻击",
                f"{first_cmd} ..."
            )

    # ── Stage 6: 反斜杠歧义检测 ────────────────────────────────────────
    # Claude Code 检测：\; 在不同解析器间有不同含义
    if re.search(r'\\[^sStTdpnrfbe]', command):  # 非标准转义
        # 常见无害转义 \n \t \r \f \b \e 除外
        return BashGuardResult(
            Threat.PARSE_FAILED, "AMBIGUOUS_BACKSLASH",
            "反斜杠歧义 — 不同解析器可能有不同理解",
            re.search(r'\\[^sStTdpnrfbe]', command).group()
        )

    # ── Stage 7: 引号未闭合 ────────────────────────────────────────────
    try:
        tokens = shlex.split(command, comments=False)
    except ValueError as e:
        return BashGuardResult(
            Threat.PARSE_FAILED, "UNCLOSED_QUOTE",
            f"引号未闭合 — 解析失败: {e}",
            str(e)
        )

    # ── Stage 8: glob/wildcard 检测 ──────────────────────────────────
    # * ? [...] 在文件名扩展中可能是危险的（rm *.log 如果没有匹配会变成字面量）
    # 但 find -name 和 grep 里的 glob 是正常的
    first_cmd = tokens[0] if tokens else ""
    if first_cmd in ('rm', 'del', 'unlink'):
        if '*' in command or '?' in command or '[' in command:
            return BashGuardResult(
                Threat.UNSAFE, "WILDCARD_IN_DELETE",
                "删除命令中的通配符 — 可能有意外匹配或无匹配",
                "rm * 或 rm *.ext"
            )

    # ── Stage 9: 零宽字符检测 ──────────────────────────────────────────
    zero_width = re.search(r'[\u200b\u200c\u200d\ufeff]', command)
    if zero_width:
        return BashGuardResult(
            Threat.UNSAFE, "ZERO_WIDTH_CHAR",
            "零宽字符注入 — 可能在终端隐藏命令内容",
            repr(zero_width.group())
        )

    # ── Stage 10: 高危命令检测（规则黑名单） ─────────────────────────
    high_risk_patterns = [
        (r'^\s*rm\s+.*-[rfF]', "rm -rf 递归删除"),
        (r'^\s*rm\s+.*\s+-r\b', "rm -r 递归删除"),
        (r'^\s*dd\s+', "dd 原始磁盘操作"),
        (r'^\s*mkfs\b', "mkfs 格式化"),
        (r'^\s*chmod\s+777', "chmod 777 全权限"),
        (r'^\s*chmod\s+-[R]?\s+777', "chmod -R 777 递归全权限"),
        (r'^\s*:()\s*:\s*{', "bash 僵尸进程创建"),
        (r'>\s*/dev/sd[a-z]', "直接写磁盘设备"),
        (r'eval\s+', "eval 动态执行"),
        (r'exec\s+', "exec 进程替换"),
    ]

    for pattern, desc in high_risk_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return BashGuardResult(
                Threat.UNSAFE, "HIGH_RISK_COMMAND",
                f"高危命令: {desc}",
                re.search(pattern, command).group()
            )

    # ── 最终: 安全 ─────────────────────────────────────────────────────
    return BashGuardResult(Threat.SAFE, "CLEAR", f"命令安全（{first_cmd}）")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 bash_guard.py '<command>'")
        print("返回码: 0=SAFE, 1=PARSE_FAILED, 2=UNSAFE")
        sys.exit(0)

    command = " ".join(sys.argv[1:])
    result = detect_threats(command)

    print(result)
    sys.exit(result.threat)


if __name__ == "__main__":
    main()
