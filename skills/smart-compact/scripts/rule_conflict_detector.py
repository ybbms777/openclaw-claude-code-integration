#!/usr/bin/env python3
"""
rule_conflict_detector.py — AGENTS.md 规则冲突检测工具

功能：
  1. 检测 AGENTS.md 中的规则冲突（NEVER vs MUST 的矛盾）
  2. 识别规则重复定义
  3. 验证规则优先级定义
  4. 生成冲突报告

用法：
  python3 rule_conflict_detector.py              # 运行完整检测
  python3 rule_conflict_detector.py --strict     # 严格模式（更多警告）
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict

WORKSPACE = Path.home() / ".openclaw" / "workspace"
AGENTS_FILE = WORKSPACE / "AGENTS.md"


class Rule:
    """代表一条规则"""
    def __init__(self, line_num: int, rule_type: str, content: str, context: str = ""):
        self.line_num = line_num
        self.rule_type = rule_type  # NEVER, MUST, ALWAYS
        self.content = content
        self.context = context  # 所属章节
        self.keywords = self._extract_keywords()

    def _extract_keywords(self) -> set:
        """提取规则中的关键词"""
        # 移除常见修饰词，保留实际操作对象
        words = re.findall(r'\b\w+\b', self.content.lower())
        stop_words = {'the', 'a', 'an', 'this', 'that', 'and', 'or', 'is', 'are', 'be', 'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'from', 'as', 'if', 'when', 'must', 'never', 'should', 'go', 'do'}
        return set(w for w in words if len(w) > 2 and w not in stop_words)


def parse_rules(content: str) -> List[Rule]:
    """从 AGENTS.md 中解析所有规则"""
    rules = []
    lines = content.split('\n')
    current_section = "Unknown"

    for i, line in enumerate(lines, 1):
        # 标题识别
        if line.startswith("## "):
            current_section = line[3:].strip()
        elif line.startswith("### "):
            current_section = line[4:].strip()

        # 规则识别
        for rule_type in ["NEVER", "MUST", "ALWAYS"]:
            if rule_type in line:
                # 提取整个规则（可能跨多行）
                rule_content = line
                j = i
                while j < len(lines) and not any(rt in lines[j] for rt in ["NEVER", "MUST", "ALWAYS"] if rt != rule_type):
                    j += 1
                    if j < len(lines) and lines[j].strip() and not lines[j].startswith("#"):
                        rule_content += " " + lines[j]

                rules.append(Rule(i, rule_type, rule_content, current_section))

    return rules


def detect_conflicts(rules: List[Rule]) -> List[Dict]:
    """检测规则冲突"""
    conflicts = []

    for i, rule1 in enumerate(rules):
        for rule2 in rules[i+1:]:
            # 检测 NEVER vs MUST 冲突
            if rule1.rule_type != rule2.rule_type and rule1.keywords & rule2.keywords:
                overlap = rule1.keywords & rule2.keywords
                if len(overlap) >= 2:  # 至少 2 个共同关键词
                    conflicts.append({
                        "type": "type_conflict",
                        "rule1": rule1,
                        "rule2": rule2,
                        "overlap_keywords": overlap,
                    })

            # 检测重复定义（同类型、同内容）
            if rule1.rule_type == rule2.rule_type:
                similarity = len(rule1.keywords & rule2.keywords) / max(len(rule1.keywords), len(rule2.keywords))
                if similarity > 0.7:
                    conflicts.append({
                        "type": "duplicate",
                        "rule1": rule1,
                        "rule2": rule2,
                        "similarity": similarity,
                    })

    return conflicts


def format_report(conflicts: List[Dict]) -> str:
    """生成冲突报告"""
    if not conflicts:
        return "✅ 未检测到规则冲突！\n"

    lines = [
        f"⚠️  检测到 {len(conflicts)} 个潜在冲突：",
        "",
    ]

    for idx, conflict in enumerate(conflicts, 1):
        if conflict["type"] == "type_conflict":
            r1, r2 = conflict["rule1"], conflict["rule2"]
            overlap = conflict["overlap_keywords"]
            lines.extend([
                f"冲突 #{idx}：{r1.rule_type} vs {r2.rule_type}",
                f"  位置：行 {r1.line_num} 和行 {r2.line_num}",
                f"  共同关键词：{', '.join(sorted(overlap))}",
                f"  规则1：{r1.content[:70]}...",
                f"  规则2：{r2.content[:70]}...",
                "",
            ])
        elif conflict["type"] == "duplicate":
            r1, r2 = conflict["rule1"], conflict["rule2"]
            similarity = conflict["similarity"]
            lines.extend([
                f"重复 #{idx}：两条类似的 {r1.rule_type} 规则",
                f"  位置：行 {r1.line_num} 和行 {r2.line_num}",
                f"  相似度：{similarity*100:.0f}%",
                f"  规则1：{r1.content[:70]}...",
                f"  规则2：{r2.content[:70]}...",
                "",
            ])

    return "\n".join(lines)


def main():
    if not AGENTS_FILE.exists():
        print(f"❌ 找不到 {AGENTS_FILE}")
        return 1

    print(f"📋 扫描 {AGENTS_FILE}...")
    print()

    content = AGENTS_FILE.read_text(encoding="utf-8")
    rules = parse_rules(content)

    print(f"发现 {len(rules)} 条规则：")
    type_count = {"NEVER": 0, "MUST": 0, "ALWAYS": 0}
    for rule in rules:
        type_count[rule.rule_type] += 1

    for rule_type, count in type_count.items():
        print(f"  - {rule_type}: {count} 条")

    print()

    conflicts = detect_conflicts(rules)
    print(format_report(conflicts))

    if conflicts:
        print("💡 建议：")
        print("  1. 检查冲突的规则是否表达相同的意图")
        print("  2. 考虑合并相似规则或明确优先级")
        print("  3. 更新 AGENTS.md 的规则优先级段落")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
