#!/usr/bin/env python3
"""
evolve.py — 从 reflection 记忆和 .learnings/LEARNINGS.md 提炼候选规则

功能：
  1. 从 LanceDB 读取最近 30 条 category="reflection" 的记忆
  2. 读取 ~/.openclaw/workspace/.learnings/LEARNINGS.md 的所有纠正记录
  3. 按触发原因分类统计（用户纠正 / 工具失败 / 上报触发）
  4. 识别高频模式，生成 NEVER/MUST 格式的规则
  5. 输出到 stdout，格式：[[WRITE]] rule text 或 [[SKIP]] reason
  6. 不自动写入文件，只输出候选规则供人工确认

用法：
  python3 evolve.py
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from skills.shared.config import (
    LANCE_DB_PATH,
    LEARNINGS_FILE,
    PENDING_FILE,
    MAX_MEMORIES,
    CATEGORY,
)
from skills.shared.logger import get_logger

logger = get_logger(__name__)

# Week 3 Integration: Learnings Extractor
try:
    from skills.evolve.scripts.learnings_extractor import extract_learnings_from_reflections
    LEARNINGS_EXTRACTOR_AVAILABLE = True
except ImportError:
    LEARNINGS_EXTRACTOR_AVAILABLE = False

# ─── 类型别名 ─────────────────────────────────────────────────────────────
MemoryEntry = Dict[str, str]
LearningEntry = Dict[str, Any]
RuleTuple = Tuple[str, str]  # (keyword, rule_text)
CandidateDict = Dict[str, Any]
ByCategory = Dict[str, List[Tuple[str, str, str]]]

# ─── LanceDB 读取 ──────────────────────────────────────────────────────────

def get_reflection_memories() -> List[MemoryEntry]:
    """读取最近 MAX_MEMORIES 条 reflection 类别的记忆"""
    try:
        import lancedb
        db = lancedb.connect(str(LANCE_DB_PATH))
        table = db.open_table("memories")
        try:
            all_rows = list(table.scan())
            reflections = [
                r for r in all_rows
                if r.get("category", "").lower() == CATEGORY
                or "reflection" in r.get("text", "").lower()
            ]
            reflections.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return [{"text": r["text"], "metadata": r.get("metadata", "{}"), "source": "LanceDB"} for r in reflections[:MAX_MEMORIES]]
        except Exception:
            results = list(table.search().limit(MAX_MEMORIES).to_list())
            return [{"text": r.get("text", ""), "metadata": "{}", "source": "LanceDB"} for r in results]
    except Exception as e:
        logger.error(f"无法连接 LanceDB: {e}")
        return []


def get_memory_texts() -> List[MemoryEntry]:
    """读取 memory jsonl 文件作为备用"""
    from skills.shared.config import MEMORY_DIR
    memories: List[MemoryEntry] = []
    memory_file = MEMORY_DIR / "reflections.jsonl"
    if memory_file.exists():
        with open(memory_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "reflection" in obj.get("category", "").lower():
                        memories.append({**obj, "source": "LanceDB"})
                except json.JSONDecodeError:
                    continue
    return memories[:MAX_MEMORIES]


# ─── .learnings/LEARNINGS.md 读取 ─────────────────────────────────────────

def get_learnings_entries() -> List[LearningEntry]:
    """
    读取 ~/.openclaw/workspace/.learnings/LEARNINGS.md
    解析每条记录的 title/summary/details，转换为候选条目
    """
    if not LEARNINGS_FILE.exists():
        return []

    with open(LEARNINGS_FILE, encoding="utf-8") as f:
        content = f.read()

    entries: List[LearningEntry] = []
    # 按 ## 标题 分隔条目
    blocks = re.split(r"\n## ", "\n" + content)
    for block in blocks[1:]:  # 跳过空开头
        lines = block.strip().split("\n")
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        # 提取 details（--- 之间）
        details_match = re.search(r"---\n(.*?)\n---", body, re.DOTALL)
        details = details_match.group(1).strip() if details_match else body

        # 提取 summary（最后一行的 - 列表）
        summary_lines = [l.strip() for l in lines if l.strip().startswith("- ")]
        summary = " ".join(summary_lines[:3])

        if summary or details:
            entries.append({
                "text": f"{title}。{summary}。{details[:200]}",
                "metadata": json.dumps({"from": "learnings_file", "title": title}),
                "source": "learnings_file"
            })

    logger.info(f"从 .learnings/ 读取 {len(entries)} 条记录")
    return entries


# ─── 规则提炼 ───────────────────────────────────────────────────────────────

REFLECTION_PATTERNS: Dict[str, List[str]] = {
    "用户纠正": [
        r"不是让你记吗", r"你记哪去了", r"不对", r"重来", r"不是这个意思",
        r"错了", r"我想要的是", r"其实", r"不是这样", r"等等", r"停",
        r"不是要", r"等等", r"等等再", r"不是这样",
        r"你怎么还没", r"我说了", r"我说的是",
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


def classify_reflection(text: str, metadata_json: str = "") -> str:
    """根据文本内容和metadata分类触发原因"""
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for category, patterns in REFLECTION_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_lower))
        scores[category] = score

    try:
        meta = json.loads(metadata_json) if metadata_json else {}
        if meta.get("bad_recall_count", 0) >= 3:
            scores["用户纠正"] = scores.get("用户纠正", 0) + 2
        if meta.get("suppressed_until_turn", 0) > 0:
            scores["用户纠正"] = scores.get("用户纠正", 0) + 1
    except (json.JSONDecodeError, ValueError):
        pass

    if max(scores.values()) == 0:
        return "其他"
    return max(scores, key=scores.get)


def extract_rule_candidates(all_memories: List[MemoryEntry]) -> ByCategory:
    """
    从所有记忆（含 LanceDB + learnings 文件）中提取规则候选
    by_category 按 (触发类型, 来源) 组织
    """
    by_category: ByCategory = {
        "用户纠正": [], "工具失败": [], "上报触发": [], "其他": []
    }

    for mem in all_memories:
        text = mem.get("text", "")
        if not text:
            continue
        metadata_str = mem.get("metadata", "{}")
        source = mem.get("source", "LanceDB")
        cat = classify_reflection(text, metadata_str)
        by_category[cat].append((text, metadata_str, source))

    return by_category


def generate_rules(by_category: ByCategory) -> List[RuleTuple]:
    """生成 NEVER/MUST 格式规则，标注来源"""
    rules: List[RuleTuple] = []

    # 用户纠正 → 行为规则
    corrections = by_category.get("用户纠正", [])
    if corrections:
        lance_count = sum(1 for c in corrections if len(c) > 2 and c[2] == "LanceDB")
        learnings_count = sum(1 for c in corrections if len(c) > 2 and c[2] == "learnings_file")
        _deduplicate_patterns([c[0] for c in corrections])
        source_note = _format_source_note(lance_count, learnings_count)
        rules.append((
            "MUST",
            f"【用户纠正检测】当用户说「不对」「重来」「其实不是」「我说的是」时，立即停止当前行动，明确询问正确方向，不重复犯错。{source_note}（触发次数：{len(corrections)}）"
        ))

    # 工具失败 → 协议规则
    failures = by_category.get("工具失败", [])
    if failures:
        lance_count = sum(1 for f in failures if len(f) > 2 and f[2] == "LanceDB")
        learnings_count = sum(1 for f in failures if len(f) > 2 and f[2] == "learnings_file")
        source_note = _format_source_note(lance_count, learnings_count)
        rules.append((
            "NEVER",
            f"【工具失败协议】任何工具调用失败后，最多重试 2 次，每次必须改变策略。2 次后仍失败 → 停止并报告原因，不可自动切换工具绕过。{source_note}（触发 {len(failures)} 次）"
        ))

    # 上报触发 → 确认规则
    escalations = by_category.get("上报触发", [])
    if escalations:
        lance_count = sum(1 for e in escalations if len(e) > 2 and e[2] == "LanceDB")
        learnings_count = sum(1 for e in escalations if len(e) > 2 and e[2] == "learnings_file")
        source_note = _format_source_note(lance_count, learnings_count)
        rules.append((
            "MUST",
            f"【上报触发规则】以下情况必须暂停并明确告知用户，等待确认：涉及资金/仓位/删除操作/外部发送。不可擅自决定。{source_note}（触发 {len(escalations)} 次）"
        ))

    return rules


def _format_source_note(lance_count: int, learnings_count: int) -> str:
    parts: List[str] = []
    if lance_count > 0:
        parts.append(f"LanceDB {lance_count}条")
    if learnings_count > 0:
        parts.append(f".learnings/ {learnings_count}条")
    return "来源：" + "，".join(parts)


def _deduplicate_patterns(texts: List[str]) -> List[str]:
    """去除重复模式，保留核心关键词"""
    seen: set = set()
    unique: List[str] = []
    for t in texts:
        words = t.split("。")[0][:50]
        key = words.lower()
        if key not in seen:
            seen.add(key)
            unique.append(words)
    return unique


# ─── 暂存机制 ───────────────────────────────────────────────────────────────

def save_pending_candidates(candidates: List[CandidateDict]) -> None:
    """生成候选后保存到暂存文件"""
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "candidates": candidates
    }
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"候选已暂存到 {PENDING_FILE}")


def load_pending_candidates() -> List[CandidateDict]:
    """读取暂存文件，返回所有 pending 状态的候选"""
    if not PENDING_FILE.exists():
        return []
    try:
        with open(PENDING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        pending = [c for c in data.get("candidates", []) if c.get("status") == "pending"]
        return pending
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def update_pending_status(rule_id: int, new_status: str) -> None:
    """更新指定候选的状态为 written / skipped"""
    if not PENDING_FILE.exists():
        return
    with open(PENDING_FILE, encoding="utf-8") as f:
        data = json.load(f)
    updated = False
    for c in data.get("candidates", []):
        if c.get("id") == rule_id:
            c["status"] = new_status
            updated = True
    if updated:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"候选 #{rule_id} → {new_status}")


# ─── 主逻辑 ─────────────────────────────────────────────────────────────────

def main():
    # 启动时检查是否有未处理的暂存候选
    pending = load_pending_candidates()
    if pending:
        logger.warning(f"还有 {len(pending)} 条上次的候选未处理")
        for c in pending:
            logger.warning(f"  #{c['id']} [{c.get('status')}] {c.get('rule','')[:60]}...")
        logger.warning("回复「写入 N」或「跳过 N」处理后再生成新候选")
        sys.exit(0)

    all_memories = []

    # 1. 从 LanceDB 读取 reflection 记忆
    memories = get_reflection_memories()
    if not memories:
        memories = get_memory_texts()
    all_memories.extend(memories)

    # 2. 从 .learnings/LEARNINGS.md 读取纠正记录
    learnings = get_learnings_entries()
    all_memories.extend(learnings)

    # Week 3 Integration: Extract learnings from reflections
    if LEARNINGS_EXTRACTOR_AVAILABLE:
        try:
            extracted_learnings = extract_learnings_from_reflections(limit=10)
            if extracted_learnings:
                logger.info(f"从 learnings_extractor 提取 {len(extracted_learnings)} 条候选")
                for learning in extracted_learnings:
                    all_memories.append({
                        "text": learning.get("action", learning.get("rule", "")),
                        "metadata": json.dumps({"from": "learnings_extractor", "type": learning.get("type")}),
                        "source": "learnings_extractor"
                    })
        except Exception as le:
            logger.error(f"learnings_extractor 提取失败: {le}")

    if not all_memories:
        print("[[SKIP]] 没有找到 reflection 记忆和纠正记录，无需提炼规则。")
        sys.exit(0)

    lance_total = sum(1 for m in all_memories if m.get("source") == "LanceDB")
    learnings_total = sum(1 for m in all_memories if m.get("source") == "learnings_file")
    extractor_total = sum(1 for m in all_memories if m.get("source") == "learnings_extractor")
    logger.info(f"共 {len(all_memories)} 条（LanceDB {lance_total} + .learnings/ {learnings_total} + extractor {extractor_total}）")

    by_category = extract_rule_candidates(all_memories)

    for cat, items in by_category.items():
        if items:
            lance_n = sum(1 for i in items if i[2] == "LanceDB")
            learnings_n = sum(1 for i in items if i[2] == "learnings_file")
            logger.info(f"{cat}: {len(items)} 条（LanceDB {lance_n} / .learnings/ {learnings_n}）")

    rules = generate_rules(by_category)

    if not rules:
        print("[[SKIP]] 未识别到足够的高频模式，跳过规则生成。")
        sys.exit(0)

    # 构建候选列表（含来源标注）
    candidates = []
    for i, (keyword, rule) in enumerate(rules, 1):
        # 从 source_note 中提取来源字符串
        source_match = re.search(r"来源：[^\s]+", rule)
        source = source_match.group() if source_match else ""
        candidates.append({
            "id": i,
            "rule": rule,
            "keyword": keyword,
            "source": source,
            "target": f"## {keyword} — 来自 evolve",
            "status": "pending"
        })

    # 保存暂存
    save_pending_candidates(candidates)

    print("\n" + "=" * 60)
    print("候选规则（复制以下内容到 AGENTS.md 确认写入）：")
    print("=" * 60 + "\n")

    for c in candidates:
        print(f"{c['id']}. [[WRITE]] {c['target']}")
        print(f"   {c['rule']}  ← 暂存候选 #{c['id']}\n")

    print("=" * 60)
    print(f"共生成 {len(candidates)} 条候选规则（已暂存）。")
    print("回复「写入 N」写入 AGENTS.md，或「跳过 N」放弃。")


if __name__ == "__main__":
    main()
