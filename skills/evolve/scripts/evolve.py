#!/usr/bin/env python3
"""
evolve.py — 从 reflection 记忆提炼候选规则

功能：
  1. 从 LanceDB 读取最近 30 条 category="reflection" 的记忆
  2. 按触发原因分类统计（用户纠正 / 工具失败 / 上报触发）
  3. 识别高频模式，生成 NEVER/MUST 格式的规则
  4. 输出到 stdout，格式：[[WRITE]] rule text 或 [[SKIP]] reason
  5. 不自动写入文件，只输出候选规则供人工确认

用法：
  python3 evolve.py
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 配置 ─────────────────────────────────────────────────────────────────
LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb-pro"
MAX_MEMORIES = 30
CATEGORY = "reflection"

# ─── LanceDB 读取 ──────────────────────────────────────────────────────────

def get_reflection_memories():
    """读取最近 MAX_MEMORIES 条 reflection 类别的记忆"""
    try:
        import lancedb
        db = lancedb.connect(str(LANCE_DB_PATH))
        table = db.open_table("memories")
        
        try:
            results = table.search()
            # 简单过滤：取最近 30 条
            all_rows = list(table.scan())
            reflections = [
                r for r in all_rows
                if r.get("category", "").lower() == CATEGORY
                or "reflection" in r.get("text", "").lower()
            ]
            # 按 timestamp 排序，取最近的
            reflections.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return reflections[:MAX_MEMORIES]
        except Exception:
            # fallback: 搜索所有
            results = list(table.search().limit(MAX_MEMORIES).execute())
            return results
    except Exception as e:
        print(f"[evolve] 无法连接 LanceDB: {e}", file=sys.stderr)
        return []


def get_memory_texts():
    """读取 memory jsonl 文件作为备用"""
    memories = []
    memory_file = Path.home() / ".openclaw" / "workspace" / "memory" / "reflections.jsonl"
    if memory_file.exists():
        with open(memory_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "reflection" in obj.get("category", "").lower():
                        memories.append(obj)
                except json.JSONDecodeError:
                    continue
    return memories[:MAX_MEMORIES]


# ─── 规则提炼 ───────────────────────────────────────────────────────────────

REFLECTION_PATTERNS = {
    "用户纠正": [
        r"不对", r"重来", r"不是这个意思", r"错了", r"我想要的是",
        r"其实", r"不是这样", r"不对不对", r"等等", r"停",
    ],
    "工具失败": [
        r"工具调用失败", r"重试.*仍失败", r"失败后停止",
        r"连接失败", r"超时", r"找不到", r"权限不足",
    ],
    "上报触发": [
        r"需要我确认", r"先告诉我", r"暂停等待", r"等一下",
        r"先别", r"等等再", r"确认一下",
    ],
}


def classify_reflection(text: str) -> str:
    """根据文本内容分类触发原因"""
    text_lower = text.lower()
    scores = {}
    for category, patterns in REFLECTION_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_lower))
        scores[category] = score
    if max(scores.values()) == 0:
        return "其他"
    return max(scores, key=scores.get)


def extract_rule_candidates(memories: list) -> dict:
    """从记忆列表中提取规则候选"""
    by_category = {"用户纠正": [], "工具失败": [], "上报触发": [], "其他": []}
    
    for mem in memories:
        text = mem.get("text", mem.get("content", ""))
        if not text:
            continue
        cat = classify_reflection(text)
        by_category[cat].append(text)
    
    return by_category


def generate_rules(by_category: dict) -> list:
    """生成 NEVER/MUST 格式规则"""
    rules = []
    
    # 用户纠正 → 行为规则
    corrections = by_category.get("用户纠正", [])
    if corrections:
        unique_patterns = _deduplicate_patterns(corrections)
        rules.append(("MUST", f"【用户纠正检测】当用户说「不对」「重来」「其实不是」时，立即停止当前行动，明确询问正确的方向，不重复犯错。触发次数: {len(corrections)}"))
    
    # 工具失败 → 协议规则
    failures = by_category.get("工具失败", [])
    if failures:
        rules.append(("NEVER", f"【工具失败协议】任何工具调用失败后，最多重试 2 次，每次必须改变策略。2 次后仍失败 → 停止并报告原因。不可自动切换工具绕过。触发次数: {len(failures)}"))
    
    # 上报触发 → 确认规则
    escalations = by_category.get("上报触发", [])
    if escalations:
        rules.append(("MUST", f"【上报触发规则】以下情况必须暂停并明确告知用户，等待确认：涉及 BDX 生产参数/实盘仓位/删除操作/外部发送。不可擅自决定。触发次数: {len(escalations)}"))
    
    return rules


def _deduplicate_patterns(texts: list) -> list:
    """去除重复模式，保留核心关键词"""
    # 简单去重：提取关键动作词
    seen = set()
    unique = []
    for t in texts:
        words = t.split("。")[0][:50]  # 取第一句的前50字
        key = words.lower()
        if key not in seen:
            seen.add(key)
            unique.append(words)
    return unique


# ─── 主逻辑 ─────────────────────────────────────────────────────────────────

def main():
    print(f"[evolve] 开始分析 reflection 记忆（最多 {MAX_MEMORIES} 条）...")
    
    # 优先从 LanceDB 读取
    memories = get_reflection_memories()
    if not memories:
        # fallback: 读 jsonl 文件
        memories = get_memory_texts()
    
    if not memories:
        print("[[SKIP]] 没有找到 reflection 类别的记忆，无需提炼规则。")
        sys.exit(0)
    
    print(f"[evolve] 找到 {len(memories)} 条 reflection 记忆")
    
    by_category = extract_rule_candidates(memories)
    
    for cat, items in by_category.items():
        if items:
            print(f"[evolve] {cat}: {len(items)} 条")
    
    rules = generate_rules(by_category)
    
    if not rules:
        print("[[SKIP]] 未识别到足够的高频模式，跳过规则生成。")
        sys.exit(0)
    
    print("\n" + "=" * 60)
    print("候选规则（复制以下内容到 AGENTS.md 确认写入）：")
    print("=" * 60 + "\n")
    
    for i, (keyword, rule) in enumerate(rules, 1):
        print(f"{i}. [[WRITE]] ## {keyword} — 来自 evolve")
        print(f"   {rule}\n")
    
    print("=" * 60)
    print(f"共生成 {len(rules)} 条候选规则。")
    print("回复「写入 N」确认写入 AGENTS.md，或「跳过」放弃。")


if __name__ == "__main__":
    main()
