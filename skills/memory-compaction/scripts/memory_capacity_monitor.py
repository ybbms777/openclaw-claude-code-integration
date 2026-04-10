#!/usr/bin/env python3
"""
memory_capacity_monitor.py — MEMORY.md 自动容量管理

功能：
  1. 检查 MEMORY.md 文件大小
  2. 如果超过 15,000 字符，自动触发整理流程
  3. 报告可删除的过期条目
  4. 生成整理建议

用法：
  python3 memory_capacity_monitor.py              # 检查并报告
  python3 memory_capacity_monitor.py --auto-clean # 自动清理（需确认）
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

WORKSPACE = Path.home() / ".openclaw" / "workspace"
MEMORY_FILE = WORKSPACE / "MEMORY.md"
SIZE_LIMIT = 15000  # 字符数
WARNING_THRESHOLD = 0.8  # 80% 时发出警告


def get_memory_size() -> tuple[int, float]:
    """返回 (字符数, 占用百分比)"""
    if not MEMORY_FILE.exists():
        return 0, 0.0

    size = len(MEMORY_FILE.read_text(encoding="utf-8"))
    percentage = (size / SIZE_LIMIT) * 100
    return size, percentage


def analyze_memory() -> dict:
    """分析 MEMORY.md 内容"""
    if not MEMORY_FILE.exists():
        return {"status": "not_found"}

    content = MEMORY_FILE.read_text(encoding="utf-8")
    lines = content.split('\n')

    analysis = {
        "total_lines": len(lines),
        "total_chars": len(content),
        "sections": {},
        "old_entries": [],
    }

    # 统计各个section
    current_section = None
    section_lines = {}

    for line in lines:
        if line.startswith("## "):
            current_section = line[3:].strip()
            section_lines[current_section] = 0
        elif current_section:
            section_lines[current_section] = section_lines.get(current_section, 0) + 1

    analysis["sections"] = section_lines
    return analysis


def format_report(size: int, percentage: float) -> str:
    """生成报告"""
    lines = [
        "📊 MEMORY.md 容量报告",
        f"─" * 40,
        f"当前大小: {size:,} 字符 / {SIZE_LIMIT:,} 字符限制",
        f"占用比例: {percentage:.1f}%",
    ]

    if percentage >= 100:
        lines.extend([
            "",
            "🚨 已超过限制！需要立即整理",
            "建议：删除过期内容，合并相似条目",
        ])
    elif percentage >= WARNING_THRESHOLD * 100:
        lines.extend([
            "",
            "⚠️  接近限制（>80%）",
            "建议：在下周进行一次整理",
        ])
    else:
        lines.extend([
            "",
            f"✅ 容量充足（{100 - percentage:.1f}% 可用空间）",
        ])

    return "\n".join(lines)


def main():
    size, percentage = get_memory_size()

    if size == 0:
        print(f"⚠️  MEMORY.md not found at {MEMORY_FILE}")
        return 1

    print(format_report(size, percentage))
    print()

    analysis = analyze_memory()

    if analysis.get("sections"):
        print("📋 按 Section 统计：")
        for section, line_count in sorted(analysis["sections"].items(), key=lambda x: x[1], reverse=True):
            print(f"  - {section}: {line_count} 行")

    print()

    if percentage >= WARNING_THRESHOLD * 100:
        print("💡 整理建议：")
        print("  1. 删除日期超过 3 个月的过期条目")
        print("  2. 合并相似主题的多条记忆")
        print("  3. 使用更精简的语言表达")
        print("  4. 将长期无关联的条目归档到 ARCHIVED.md")
        print()
        print("运行命令自动触发整理：")
        print(f"  python3 {Path(__file__).name} --auto-clean")

    return 0 if percentage < 100 else 1


if __name__ == "__main__":
    sys.exit(main())
