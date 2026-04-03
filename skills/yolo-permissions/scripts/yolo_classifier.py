#!/usr/bin/env python3
"""
yolo_classifier.py — 工具调用安全分类器

用法：
  python3 yolo_classifier.py <tool_name> '<json_params>'
  python3 yolo_classifier.py --interactive

示例：
  python3 yolo_classifier.py bash '{"command": "rm -rf /tmp/test"}'
  python3 yolo_classifier.py write '{"path": "/Users/ybbms/test.txt"}'
"""

import json
import sys
import urllib.request
import urllib.error

# ─── 配置 ─────────────────────────────────────────────────────────────────
MINIMAX_API_KEY = "sk-cp-DtqXh99hmgbdLdYAyGJBi22-15cNDkRT08C8ZRhwSWz6P7wprqHfPIAsc5VgR2OlZqn-Jw8aYI-cZpnoWnScq2jS99nc-MfFASRsDHoJP5QTJ38Mxc1Nylw"
MINIMAX_URL = "https://api.minimaxi.com/v1/chat/completions"

# ─── 风险等级定义 ──────────────────────────────────────────────────────────

# 完全安全，自动放行
LOW_RISK_TOOLS = {
    "read", "search", "list_directory", "memory_recall", "web_search",
    "glob", "grep", "stat", "tree", "echo", "pwd", "cd", "head", "tail",
    "which", "file", "dirname", "basename", "readlink", "locale", "uptime",
    "hostname", "whoami", "id", "uname",
}

# 已知高风险工具
HIGH_RISK_TOOLS = {
    "delete", "trash", "drop", "shutdown", "reboot",
    "kill", "pkill", "killall",
}

# 沙箱自动放行命令（bash工具）
SAFE_BASH_PATTERNS = [
    "ls", "pwd", "cd ", "cat ", "head ", "tail ", "find ", "grep ",
    "which", "file ", "stat", "tree ", "dirname", "basename", "readlink",
    "ps aux", "top -l", "df -h", "du -h", "free -m",
    "hostname", "uptime", "uname", "whoami", "id",
    "env", "printenv", "locale",
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote -v", "git tag", "git stash list",
    "git fetch", "git ls-files", "git rev-parse",
    "npm --version", "node --version", "python3 --version",
    "echo ", "printf ", "true", "false", "yes", "date",
]

# 高风险bash命令模式
RISKY_BASH_PATTERNS = [
    "rm -rf", "rm -r /", "rm -f /", "dd if=", "mkfs",
    "chmod 777", "chmod -R 777",
    "> /dev/sd", "2> /dev/sd",
    "curl | bash", "wget | bash",
    "eval ", "exec ", "source ~/.bashrc",
    "git push", "git force-push",
    "ssh ", "scp ", "rsync",
    "--format=raw", "--no-check-certificate",
]


# ─── 快速规则判断（不用API） ────────────────────────────────────────────────

def quick_rule_check(tool_name: str, params: dict) -> dict | None:
    """快速规则判断，无需调用API"""

    # LOW risk 工具直接放行
    if tool_name in LOW_RISK_TOOLS:
        return {
            "risk": "LOW",
            "reason": f"{tool_name} 是只读/查询工具，无写入风险",
            "action": "allow",
            "source": "rule"
        }

    # HIGH risk 工具直接阻止
    if tool_name in HIGH_RISK_TOOLS:
        return {
            "risk": "HIGH",
            "reason": f"{tool_name} 是已知高风险操作，需要明确确认",
            "action": "confirm",
            "source": "rule"
        }

    # Bash 工具：检查命令模式
    if tool_name == "bash":
        command = params.get("command", "")

        # 完全安全的命令
        for safe in SAFE_BASH_PATTERNS:
            if command.strip().startswith(safe.strip()) or command == safe:
                return {
                    "risk": "LOW",
                    "reason": f"命令 '{command[:50]}' 属于只读操作",
                    "action": "allow",
                    "source": "rule"
                }

        # 高风险命令
        for risky in RISKY_BASH_PATTERNS:
            if risky in command:
                return {
                    "risk": "HIGH",
                    "reason": f"命令包含高风险模式 '{risky}'",
                    "action": "block",
                    "source": "rule"
                }

    # Write/Edit 工具：检查路径
    if tool_name in ("write", "edit"):
        path = params.get("path", "")

        # 高危路径
        danger_paths = [
            "/.ssh/", "/.openclaw/", "/~/",
            "credentials", "secrets", ".env",
            "/etc/", "/usr/bin/", "/bin/", "/sbin/",
            "/System/", "/Library/", "/Applications/",
        ]
        for dp in danger_paths:
            if dp in path:
                return {
                    "risk": "HIGH",
                    "reason": f"目标路径 '{path}' 属于系统关键目录",
                    "action": "block",
                    "source": "rule"
                }

        # 写操作本身是 MEDIUM 风险
        return {
            "risk": "MEDIUM",
            "reason": f"写入操作，目标：{path}",
            "action": "confirm",
            "source": "rule"
        }

    # 外部发送工具
    if tool_name in ("email", "webhook", "http_request", "send_message"):
        return {
            "risk": "HIGH",
            "reason": f"{tool_name} 涉及外部通信，需要确认",
            "action": "confirm",
            "source": "rule"
        }

    return None  # 无法快速判断，需要API


# ─── MiniMax API 调用 ──────────────────────────────────────────────────────

def call_minimax(prompt: str) -> str:
    """调用 MiniMax API"""
    payload = json.dumps({
        "model": "MiniMax-M2",
        "messages": [
            {"role": "system", "content": "你是一个安全分类器。输出只包含JSON，不要解释。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(
        MINIMAX_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f'{{"error": "{e}"}}'


def classify_with_ai(tool_name: str, params: dict) -> dict:
    """用 AI 做分类判断"""
    params_str = json.dumps(params, ensure_ascii=False)[:500]

    prompt = f"""判断以下工具调用的安全风险等级。

工具名: {tool_name}
参数: {params_str}

分析步骤：
1. 这个操作的直接后果是什么？
2. 是否不可逆？
3. 是否影响系统安全或数据安全？
4. 是否对外发送信息？

风险等级定义：
- LOW: 只读操作，无写入风险
- MEDIUM: 有写入/修改，但路径在用户目录内，可控
- HIGH: 破坏性操作、认证凭据操作、外部通信

输出格式（只输出JSON）：
{{"risk": "LOW|MEDIUM|HIGH", "reason": "简短原因", "action": "allow|confirm|block"}}
"""

    try:
        response = call_minimax(prompt)
        result = json.loads(response)

        # 验证字段
        if result.get("error"):
            return {
                "risk": "MEDIUM",
                "reason": f"API调用失败: {result['error']}，默认按MEDIUM处理",
                "action": "confirm",
                "source": "api"
            }

        result["source"] = "api"
        return result

    except json.JSONDecodeError:
        return {
            "risk": "MEDIUM",
            "reason": "API响应解析失败，默认按MEDIUM处理",
            "action": "confirm",
            "source": "api",
            "raw": response[:200]
        }


# ─── 主分类函数 ─────────────────────────────────────────────────────────────

def classify(tool_name: str, params: dict) -> dict:
    """主入口：规则优先，规则无法判断时调用AI"""
    rule_result = quick_rule_check(tool_name, params)
    if rule_result:
        return rule_result

    return classify_with_ai(tool_name, params)


def format_output(result: dict) -> str:
    """格式化输出"""
    risk = result.get("risk", "UNKNOWN")
    reason = result.get("reason", "无信息")
    action = result.get("action", "confirm")
    source = result.get("source", "unknown")

    emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚫", "UNKNOWN": "❓"}
    icon = emoji.get(risk, "❓")

    return f"""{icon} 风险等级: {risk} ({source})
原因: {reason}
操作: {action}
"""


# ─── 命令行接口 ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 yolo_classifier.py <tool_name> '<json_params>'")
        print("  python3 yolo_classifier.py --interactive")
        print()
        print("示例:")
        print("  python3 yolo_classifier.py bash '{{\"command\": \"ls -la\"}}'")
        print("  python3 yolo_classifier.py write '{{\"path\": \"~/test.txt\"}}'")
        sys.exit(0)

    if sys.argv[1] == "--interactive":
        print("YOLO 权限分类器 (交互模式)")
        print("输入格式: tool_name | params_json")
        print("输入 'q' 退出")
        print()
        while True:
            try:
                line = input("> ")
                if line.strip().lower() in ("q", "quit", "exit"):
                    break
                if "|" not in line:
                    print("格式错误，用 tool_name | params_json")
                    continue
                tool_name, params_str = line.split("|", 1)
                params = json.loads(params_str.strip())
                result = classify(tool_name.strip(), params)
                print(format_output(result))
            except json.JSONDecodeError:
                print("JSON格式错误")
            except Exception as e:
                print(f"错误: {e}")
        return

    if len(sys.argv) < 3:
        print("错误: 需要 tool_name 和 params")
        sys.exit(1)

    tool_name = sys.argv[1]
    params_str = sys.argv[2]

    try:
        params = json.loads(params_str)
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
        sys.exit(1)

    result = classify(tool_name, params)
    print(format_output(result))

    # 输出JSON给调用者
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
