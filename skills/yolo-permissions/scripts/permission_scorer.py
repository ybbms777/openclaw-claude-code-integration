#!/usr/bin/env python3
"""
permission_scorer.py — 工具调用权限评分系统

功能：
  1. 对命令进行多维度评分：操作(40%) + 路径(30%) + 上下文(20%) + 模式(10%)
  2. 返回 0-100 的风险分数
  3. 提供 risk_level() 方法将分数映射到风险等级
  4. 集成到 yolo_classifier.py 作为补充判断

用法：
  python3 permission_scorer.py <tool_name> '<json_params>'
  python3 permission_scorer.py --test
"""

import json
import sys
import re
import os
from typing import Dict, Optional, Tuple


# ─── 评分规则数据库 ────────────────────────────────────────────────────────

# 危险操作及其风险分数（0-100）
DANGEROUS_OPERATIONS = {
    # 最危险：文件系统/系统操作
    "rm": 95,
    "delete": 95,
    "trash": 90,
    "dd": 98,
    "mkfs": 100,
    "format": 98,
    "chmod": 85,
    "chown": 88,

    # 系统控制
    "shutdown": 100,
    "reboot": 100,
    "poweroff": 100,
    "kill": 90,
    "pkill": 88,
    "killall": 88,

    # 网络风险
    "curl": 70,
    "wget": 70,
    "ssh": 75,
    "scp": 75,
    "rsync": 70,
    "git push": 65,
    "git force": 90,

    # 代码执行
    "eval": 98,
    "exec": 96,
    "source": 80,

    # 数据库/存储
    "drop": 95,
    "truncate": 95,
    "delete from": 85,

    # 低风险操作
    "echo": 5,
    "ls": 5,
    "cat": 10,
    "grep": 8,
    "find": 15,
}

# 危险路径前缀及其风险分数
DANGEROUS_PATHS = {
    "/.ssh": 95,
    "/.aws": 95,
    "/etc/": 98,
    "/usr/bin": 85,
    "/usr/local/bin": 80,
    "/bin/": 85,
    "/sbin/": 90,
    "/System/": 95,
    "/Library/": 90,
    "/Applications/": 85,
    "/.openclaw": 80,
    "/.bashrc": 75,
    "/.bash_profile": 75,
    "/.zshrc": 75,
    "/root": 85,
}

# 敏感文件模式
SENSITIVE_FILES = {
    "credentials": 95,
    "secrets": 95,
    "password": 90,
    "token": 85,
    ".env": 85,
    "api_key": 90,
    "private_key": 98,
    "id_rsa": 98,
}

# 上下文风险指示符（标志性词汇）
CONTEXT_RISK_INDICATORS = {
    "production": 30,
    "prod": 35,
    "live": 30,
    "main": 20,
    "critical": 25,
    "important": 15,
    "force": 25,
    "dangerous": 40,
    "backup": -15,  # 降低风险
    "test": -20,
    "demo": -20,
    "dry.?run": -25,
    "dry-run": -25,
}

# 高风险命令模式
RISKY_PATTERNS = {
    r"rm.*-rf": 95,
    r"chmod.*777": 85,
    r">\s*/dev/sd": 100,
    r">\s*/dev/null": 10,
    r"dd.*if=": 95,
    r"\.pipe\(": 70,
    r"subprocess\.call\(": 50,
    r"subprocess\.Popen\(": 50,
    r"os\.system\(": 75,
    r"__import__": 85,
    r"exec\(": 98,
    r"eval\(": 98,
}


# ─── 权限评分器类 ──────────────────────────────────────────────────────────

class PermissionScorer:
    """权限评分系统"""

    def __init__(self):
        """初始化评分器"""
        self.weights = {
            "operation": 0.4,
            "path": 0.3,
            "context": 0.2,
            "pattern": 0.1,
        }

    def _score_operation(self, tool_name: str, command: str = "") -> float:
        """
        评分操作类型（权重 40%）

        返回: 0-100 分
        """
        # 直接匹配工具名
        if tool_name.lower() in DANGEROUS_OPERATIONS:
            return float(DANGEROUS_OPERATIONS[tool_name.lower()])

        # 对于 bash，检查命令开头
        if tool_name.lower() == "bash":
            cmd_lower = command.lower().strip()
            for op, score in DANGEROUS_OPERATIONS.items():
                if cmd_lower.startswith(op):
                    return float(score)

        # 检查命令中的危险操作关键字
        if command:
            cmd_lower = command.lower()
            for op, score in DANGEROUS_OPERATIONS.items():
                if op in cmd_lower:
                    return float(score)

        # 默认得分（中等风险的写操作）
        if tool_name in ("write", "edit"):
            return 35.0
        if tool_name in ("bash", "shell"):
            return 25.0
        if tool_name in ("read", "grep", "search"):
            return 5.0

        return 15.0  # 默认低风险

    def _score_path(self, path: str = "") -> float:
        """
        评分目标路径风险（权重 30%）

        返回: 0-100 分
        """
        if not path:
            return 0.0

        path_lower = path.lower()

        if path_lower.startswith("/tmp/") or path_lower == "/tmp":
            return 10.0

        # 检查危险路径前缀
        for danger_path, score in DANGEROUS_PATHS.items():
            if path_lower.startswith(danger_path.lower()):
                return float(score)

        # 检查敏感文件名
        for sensitive, score in SENSITIVE_FILES.items():
            if sensitive in path_lower:
                return float(score)

        # 用户目录是相对安全的（但仍有风险）
        if "~" in path or "/home/" in path_lower or "/users/" in path_lower:
            return 25.0

        # 未知路径（中等风险）
        return 35.0

    def _score_context(self, context: Dict = None) -> float:
        """
        评分执行上下文（权重 20%）

        Args:
            context: 上下文字典，可包含 environment, description, 等字段

        返回: -25 到 +40 的加分（相对）
        """
        if not context:
            return 0.0

        score = 0.0

        # 检查环境变量
        env = context.get("environment", "").lower()
        desc = context.get("description", "").lower()

        all_text = f"{env} {desc}".lower()

        for indicator, value in CONTEXT_RISK_INDICATORS.items():
            if re.search(indicator, all_text, re.IGNORECASE):
                score += value

        # 限制范围
        return max(-25.0, min(40.0, score))

    def _score_pattern(self, command: str = "") -> float:
        """
        评分命令模式（权重 10%）

        返回: 0-100 分
        """
        if not command:
            return 0.0

        cmd_lower = command.lower()
        max_score = 0.0

        # 检查所有高风险模式，返回最高分
        for pattern, score in RISKY_PATTERNS.items():
            if re.search(pattern, cmd_lower):
                max_score = max(max_score, float(score))

        if max_score > 0:
            return max_score

        # 检查管道链（可能增加风险）
        if "|" in command and len(command.split("|")) > 3:
            return 40.0

        # 检查重定向（>）
        if re.search(r">\s*[^\s]", command):  # 重定向到文件
            if "/dev/" not in command:
                return 35.0

        return 0.0

    def score_command(self, tool_name: str, params: Dict = None, context: Dict = None) -> float:
        """
        对命令进行综合评分

        Args:
            tool_name: 工具名称
            params: 工具参数
            context: 执行上下文

        返回: 0-100 的风险分数
        """
        if not params:
            params = {}
        if not context:
            context = {}

        # 提取关键参数
        command = params.get("command", "")
        path = params.get("path", "")

        # 各维度评分
        op_score = self._score_operation(tool_name, command)
        path_score = self._score_path(path)
        context_score = self._score_context(context)
        pattern_score = self._score_pattern(command)

        # 加权组合（需要归一化上下文分数）
        context_normalized = (context_score + 25.0) / 65.0 * 100.0  # 将 [-25, 40] 映射到 [0, 100]
        context_normalized = max(0.0, min(100.0, context_normalized))

        total_score = (
            op_score * self.weights["operation"] +
            path_score * self.weights["path"] +
            context_normalized * self.weights["context"] +
            pattern_score * self.weights["pattern"]
        )

        # 极危险命令模式必须返回 HIGH (>=70)
        critical_patterns = [
            r"rm\s+-rf", r"chmod\s+777", r"git\s+push",
            r"scp\s+", r"dd\s+", r"git\s+push\s+--force",
        ]
        for pattern in critical_patterns:
            import re
            if re.search(pattern, command, re.IGNORECASE):
                total_score = max(total_score, 70.0)
                break

        return min(100.0, max(0.0, total_score))

    def risk_level(self, score: float) -> Tuple[str, str]:
        """
        将分数映射到风险等级

        Args:
            score: 0-100 的分数

        Returns:
            (risk_level, description)
            - LOW: 0-30，只读操作
            - MEDIUM: 30-70，需要确认
            - HIGH: 70-100，阻止或需要多次确认
        """
        if score < 30:
            return "LOW", "低风险，只读操作"
        elif score < 70:
            return "MEDIUM", "中等风险，需要确认"
        else:
            return "HIGH", "高风险，需要多次确认或阻止"

    def get_score_breakdown(self, tool_name: str, params: Dict = None, context: Dict = None) -> Dict:
        """获取详细的评分分解"""
        if not params:
            params = {}
        if not context:
            context = {}

        command = params.get("command", "")
        path = params.get("path", "")

        op_score = self._score_operation(tool_name, command)
        path_score = self._score_path(path)
        context_score = self._score_context(context)
        pattern_score = self._score_pattern(command)

        total_score = self.score_command(tool_name, params, context)
        risk_level, description = self.risk_level(total_score)

        return {
            "total_score": round(total_score, 1),
            "risk_level": risk_level,
            "description": description,
            "breakdown": {
                "operation": round(op_score * self.weights["operation"], 1),
                "path": round(path_score * self.weights["path"], 1),
                "context": round(self._score_context(context) * self.weights["context"], 1),
                "pattern": round(pattern_score * self.weights["pattern"], 1),
            },
            "weights": self.weights,
        }


# ─── 命令行接口 ────────────────────────────────────────────────────────────

def main():
    """命令行接口"""
    import argparse

    parser = argparse.ArgumentParser(description="Permission Scorer")
    parser.add_argument("tool_name", nargs="?", help="工具名称")
    parser.add_argument("params", nargs="?", help="参数 JSON")
    parser.add_argument("--context", help="上下文 JSON")
    parser.add_argument("--test", action="store_true", help="运行测试")
    parser.add_argument("--breakdown", action="store_true", help="显示详细分解")
    args = parser.parse_args()

    scorer = PermissionScorer()

    if args.test:
        # 测试用例
        test_cases = [
            ("bash", {"command": "ls -la"}, None),
            ("bash", {"command": "rm -rf /"}, None),
            ("write", {"path": "/tmp/test.txt"}, None),
            ("write", {"path": "/.ssh/id_rsa"}, None),
            ("bash", {"command": "git push origin main"}, {"environment": "production"}),
            ("bash", {"command": "grep password credentials.txt"}, None),
        ]

        print("权限评分系统测试\n")
        print("-" * 80)

        for tool_name, params, context in test_cases:
            score = scorer.score_command(tool_name, params, context)
            risk, desc = scorer.risk_level(score)

            print(f"\n工具: {tool_name}")
            print(f"参数: {json.dumps(params, ensure_ascii=False)}")
            if context:
                print(f"上下文: {json.dumps(context, ensure_ascii=False)}")
            print(f"分数: {score:.1f}/100")
            print(f"风险等级: {risk} - {desc}")

            if args.breakdown:
                breakdown = scorer.get_score_breakdown(tool_name, params, context)
                print(f"分解: {json.dumps(breakdown, ensure_ascii=False, indent=2)}")

        print("\n" + "-" * 80)
        return

    if not args.tool_name or not args.params:
        print("用法:")
        print("  python3 permission_scorer.py <tool_name> '<json_params>'")
        print("  python3 permission_scorer.py bash '{\"command\": \"ls -la\"}'")
        print("  python3 permission_scorer.py --test")
        sys.exit(1)

    try:
        params = json.loads(args.params)
        context = json.loads(args.context) if args.context else None
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
        sys.exit(1)

    score = scorer.score_command(args.tool_name, params, context)
    risk, desc = scorer.risk_level(score)

    output = {
        "score": round(score, 1),
        "risk_level": risk,
        "description": desc,
    }

    if args.breakdown:
        output.update(scorer.get_score_breakdown(args.tool_name, params, context))

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
