#!/usr/local/bin/python3.12
"""
safe_ast_check.py — BashAST 与 safe-exec 集成层

将 BashAST 解析器整合到 safe-exec 工作流中，
作为四层安全的第 1 层（AST 解析层）。

用法：
  python3 safe_ast_check.py '<command>'
  echo $?  # 0=SAFE, 1=PARSE_FAILED, 2=UNSAFE

被 safe-exec shell wrapper 调用（如果已安装）。
"""

import sys
import os

# 添加 bash_ast 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
BASH_AST_PATH = os.path.join(SKILL_DIR, "skills", "bash_ast", "scripts", "bash_ast.py")

# 尝试导入 bash_ast
try:
    sys.path.insert(0, os.path.dirname(BASH_AST_PATH))
    from bash_ast import analyze, Threat
except ImportError:
    # fallback: 直接复制核心逻辑
    import re
    Threat = type('Threat', (), {'SAFE': 0, 'PARSE_FAILED': 1, 'UNSAFE': 2})()

    DANGEROUS_COMMANDS = {
        "rm", "dd", "chmod", "curl", "wget", "nc", "netcat",
        "bash", "sh", "zmod", "eval", "exec", "source", "mkfs",
    }

    def analyze(command: str):
        if not command or not command.strip():
            return {"threat": Threat.SAFE, "level": "CLEAR", "reason": "空命令", "detail": "", "ast": None}

        # 零宽字符
        if re.search(r'[\u200b\u200c\u200d\ufeff]', command):
            return {"threat": Threat.UNSAFE, "level": "ZERO_WIDTH_CHAR",
                    "reason": "零宽字符注入", "detail": "", "ast": None}

        # rm -rf
        if re.search(r'rm\s+.*-[rfF]', command):
            return {"threat": Threat.UNSAFE, "level": "HIGH_RISK",
                    "reason": "rm 递归删除", "detail": command[:80], "ast": None}

        # chmod 777
        if re.search(r'chmod\s+777', command):
            return {"threat": Threat.UNSAFE, "level": "HIGH_RISK",
                    "reason": "chmod 777 全权限", "detail": command[:80], "ast": None}

        # curl|wget pipe to shell
        if re.search(r'(curl|wget)\s+[^\|]+\s*\|.*(bash|sh|zsh)', command, re.IGNORECASE):
            return {"threat": Threat.UNSAFE, "level": "HIGH_RISK",
                    "reason": "curl/wget pipe 到 shell", "detail": command[:80], "ast": None}

        # 敏感路径
        sensitive = re.search(r'/\.ssh/|/etc/|/etc/shadow|/etc/passwd|/dev/sd|/proc/', command)
        if sensitive:
            return {"threat": Threat.UNSAFE, "level": "HIGH_RISK",
                    "reason": f"敏感路径: {sensitive.group()}", "detail": sensitive.group(), "ast": None}

        # 路径遍历
        if re.search(r'(?:\.\./){2,}', command):
            return {"threat": Threat.UNSAFE, "level": "MEDIUM_RISK",
                    "reason": "路径遍历过多", "detail": command[:80], "ast": None}

        return {"threat": Threat.SAFE, "level": "CLEAR", "reason": "命令安全", "detail": "", "ast": None}


def main():
    if len(sys.argv) < 2:
        print("用法: python3 safe_ast_check.py '<command>'")
        sys.exit(0)

    command = " ".join(sys.argv[1:])
    result = analyze(command)

    icon = {0: "✅", 1: "⚠️", 2: "🚫"}
    print(f"{icon.get(result['threat'], '❓')} [{result['level']}] {result['reason']}")
    if result.get('detail'):
        print(f"   详情: {result['detail']}")

    sys.exit(result["threat"])


if __name__ == "__main__":
    main()
