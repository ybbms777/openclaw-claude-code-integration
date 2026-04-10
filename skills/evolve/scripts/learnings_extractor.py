#!/usr/bin/env python3
"""
learnings_extractor.py — 从反思记忆中提取学习规则

功能：
  1. 从 LanceDB 查询 category='reflection' 的记忆（近期、高 importance）
  2. 应用分类规则（NEVER/MUST/ALWAYS）提取关键模式
  3. 去重 + 相似度分组（>= 0.85）
  4. 生成 Markdown 候选列表供用户审核
  5. 支持批准单条规则

用法：
  python3 learnings_extractor.py                    # 显示候选规则
  python3 learnings_extractor.py --limit 100       # 指定查询数量
  python3 learnings_extractor.py --approve <id>   # 批准规则并追加到 LEARNINGS.md
"""

import json
import os
import sys
import re
import hashlib
import urllib.request
import urllib.error
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# ─── 配置 ──────────────────────────────────────────────────────────────────

WORKSPACE = Path.home() / ".openclaw" / "workspace"
LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb-pro"
LEARNINGS_FILE = WORKSPACE / ".learnings" / "LEARNINGS.md"

SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_EMBED_URL = "https://api.minimaxi.com/v1/embeddings"

# 分类规则模式
CLASSIFICATION_PATTERNS = {
    "MUST": r"\bMUST\b",
    "NEVER": r"\bNEVER\b",
    "ALWAYS": r"\bALWAYS\b",
    "DO_NOT": r"\b(DO\s+)?NOT\b",
    "SHOULD": r"\bSHOULD\b",
}

# 重要性和时间阈值
IMPORTANCE_MIN = 0.75
MAX_AGE_DAYS = 30
SIMILARITY_THRESHOLD = 0.85


# ─── Embedding 函数 ────────────────────────────────────────────────────────

def get_embedding(text: str) -> Optional[List[float]]:
    """获取文本的 embedding（优先使用 SiliconFlow，备用 MiniMax）"""
    text = text[:2000]  # 限制长度

    if SILICONFLOW_API_KEY:
        try:
            payload = json.dumps({
                "model": "BAAI/bge-m3",
                "input": text,
                "encoding_format": "float"
            }).encode("utf-8")
            req = urllib.request.Request(
                SILICONFLOW_EMBED_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                return result["data"][0]["embedding"]
        except Exception as e:
            print(f"[EMBED] SiliconFlow 失败: {e}, 尝试 MiniMax", file=sys.stderr)

    if MINIMAX_API_KEY:
        try:
            payload = json.dumps({
                "model": "minimax-embedding",
                "input": text
            }).encode("utf-8")
            req = urllib.request.Request(
                MINIMAX_EMBED_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                return result["data"][0]["embedding"]
        except Exception as e:
            print(f"[EMBED] MiniMax 失败: {e}", file=sys.stderr)

    # 备用方案：哈希向量
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [0.0] * 1024
    for i in range(min(len(h), 1024)):
        vec[i] = (h[i] / 255.0) * 2 - 1
    return vec


def cosine_sim(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── LanceDB 查询 ──────────────────────────────────────────────────────────

def load_reflections(limit: int = 50) -> List[Dict]:
    """从 LanceDB 加载 reflection 记忆"""
    try:
        import lancedb
    except ImportError:
        print("[ERROR] lancedb 未安装", file=sys.stderr)
        return []

    try:
        db = lancedb.connect(str(LANCE_DB_PATH))
        tbl = db.open_table("memories")

        # 查询 category='reflection' 且 importance >= IMPORTANCE_MIN 的记忆
        now_ms = datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000
        age_cutoff_ms = now_ms - MAX_AGE_DAYS * 24 * 60 * 60 * 1000

        df = tbl.search(
            query_text="MUST NEVER ALWAYS",
            where=f"category = 'reflection' AND importance >= {IMPORTANCE_MIN} AND timestamp * 1000 >= {age_cutoff_ms}"
        ).limit(limit).to_pandas()

        records = []
        for _, row in df.iterrows():
            try:
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
            except Exception:
                meta = {}

            records.append({
                "id": row["id"],
                "text": row["text"],
                "category": row["category"],
                "importance": float(row["importance"]),
                "timestamp": float(row["timestamp"]),
                "vector": list(row["vector"]) if hasattr(row["vector"], "__iter__") else [],
                "metadata": meta,
            })

        print(f"[EXTRACT] 加载 {len(records)} 条 reflection 记忆")
        return records

    except Exception as e:
        print(f"[ERROR] 加载记忆失败: {e}", file=sys.stderr)
        return []


# ─── 规则提取 ──────────────────────────────────────────────────────────────

def extract_learning_rules(text: str) -> List[Tuple[str, str]]:
    """
    从文本中提取学习规则

    返回: [(rule_type, rule_text), ...]
    """
    rules = []

    for rule_type, pattern in CLASSIFICATION_PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            # 提取该模式周围的上下文（前后各 100 字符）
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end].strip()

            # 标准化：移除多余空格
            context = re.sub(r"\s+", " ", context)

            rules.append((rule_type, context))

    return rules


def deduplicate_rules(rules: List[Tuple[str, str]]) -> List[Dict]:
    """
    去重规则（精确匹配）

    返回: [{rule_type, text, count, ids}, ...]
    """
    dedup = {}
    for rule_type, text in rules:
        key = (rule_type, text)
        if key not in dedup:
            dedup[key] = {
                "rule_type": rule_type,
                "text": text,
                "count": 0,
                "ids": []
            }
        dedup[key]["count"] += 1

    return list(dedup.values())


def group_similar_rules(rules: List[Dict]) -> List[List[Dict]]:
    """
    根据相似度分组规则（相似度 >= SIMILARITY_THRESHOLD）

    返回: [[rule1, rule2, ...], ...]  # 相似的规则聚在一起
    """
    if not rules:
        return []

    # 为每条规则计算 embedding
    for rule in rules:
        vec = get_embedding(rule["text"])
        rule["_embedding"] = vec if vec else []

    # 分组
    groups = []
    assigned = set()

    for i, rule in enumerate(rules):
        if i in assigned:
            continue

        group = [rule]
        assigned.add(i)

        if rule["_embedding"]:
            for j, other in enumerate(rules[i + 1:], start=i + 1):
                if j in assigned:
                    continue
                if other["_embedding"] and cosine_sim(rule["_embedding"], other["_embedding"]) >= SIMILARITY_THRESHOLD:
                    group.append(other)
                    assigned.add(j)

        groups.append(group)

    return groups


# ─── 候选列表生成 ────────────────────────────────────────────────────────────

def generate_markdown_candidate_list(limit: int = 50) -> Tuple[str, List[Dict]]:
    """
    生成候选规则的 Markdown 表格

    返回: (markdown_text, candidate_rules_list)
    """
    reflections = load_reflections(limit=limit)
    if not reflections:
        return "# 无可用的 Reflection 记忆\n", []

    # 提取规则
    all_rules = []
    for reflection in reflections:
        rules = extract_learning_rules(reflection["text"])
        for rule_type, rule_text in rules:
            all_rules.append({
                "rule_type": rule_type,
                "text": rule_text,
                "source_id": reflection["id"],
                "importance": reflection["importance"],
                "timestamp": reflection["timestamp"],
            })

    if not all_rules:
        return "# 未找到匹配规则（MUST/NEVER/ALWAYS）\n", []

    # 去重
    dedup_rules = deduplicate_rules([(r["rule_type"], r["text"]) for r in all_rules])
    print(f"[EXTRACT] 去重后 {len(dedup_rules)} 条规则")

    # 分组相似规则
    grouped = group_similar_rules(dedup_rules)
    print(f"[EXTRACT] 分组后 {len(grouped)} 个规则簇")

    # 生成 Markdown
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    md_lines = [
        f"# 学习规则候选列表",
        f"\n_生成时间: {now}_",
        f"\n**总计: {len(grouped)} 个规则簇，{len(all_rules)} 条原始规则**",
        "",
        "| 规则类型 | 规则内容 | 出现次数 | 重要度 | 操作 |",
        "|--------|--------|--------|------|------|",
    ]

    candidates = []
    for group_id, group in enumerate(grouped, 1):
        primary = max(group, key=lambda x: x["count"])  # 选择出现最多的作为主规则
        rule_type = primary["rule_type"]
        rule_text = primary["text"][:100].replace("|", "\\|")
        total_count = sum(r["count"] for r in group)
        avg_importance = sum(r["importance"] for r in group) / len(group) if group else 0

        candidate_id = hashlib.md5(rule_text.encode()).hexdigest()[:8]

        md_lines.append(
            f"| {rule_type} | {rule_text}... | {total_count} | {avg_importance:.2f} | "
            f"[approve-{candidate_id}](#approve) |"
        )

        candidates.append({
            "id": candidate_id,
            "rule_type": rule_type,
            "text": rule_text,
            "full_text": primary["text"],
            "count": total_count,
            "importance": avg_importance,
            "group_size": len(group),
        })

    md_lines.append("\n---\n")
    md_lines.append("## 使用说明\n")
    md_lines.append("1. 查看候选规则列表\n")
    md_lines.append("2. 点击 `[approve-<id>]` 批准规则\n")
    md_lines.append("3. 批准后的规则将追加到 LEARNINGS.md\n")
    md_lines.append("4. 批准规则会被标记为 `verified`\n")

    return "\n".join(md_lines), candidates


def approve_candidate(candidate_id: str) -> bool:
    """
    批准一条规则候选，追加到 LEARNINGS.md

    Args:
        candidate_id: 规则 ID

    Returns:
        是否批准成功
    """
    # 生成候选列表以获取对应的规则
    _, candidates = generate_markdown_candidate_list(limit=50)

    target = None
    for c in candidates:
        if c["id"] == candidate_id:
            target = c
            break

    if not target:
        print(f"[ERROR] 未找到规则 ID: {candidate_id}", file=sys.stderr)
        return False

    # 追加到 LEARNINGS.md
    try:
        LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n## [{now}] 已批准规则\n"
            f"- 类型: {target['rule_type']}\n"
            f"- 规则: {target['full_text'][:150]}\n"
            f"- 出现次数: {target['count']}\n"
            f"- 重要度: {target['importance']:.2f}\n"
            f"- 状态: verified\n"
        )

        with open(LEARNINGS_FILE, "a", encoding="utf-8") as f:
            f.write(entry)

        print(f"[APPROVE] 已批准规则 {candidate_id} 并追加到 {LEARNINGS_FILE}")
        return True

    except Exception as e:
        print(f"[ERROR] 批准规则失败: {e}", file=sys.stderr)
        return False


# ─── 主函数 ────────────────────────────────────────────────────────────────

def main() -> None:
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Learnings Extractor")
    parser.add_argument("--limit", type=int, default=50, help="查询记忆数量上限")
    parser.add_argument("--approve", metavar="ID", help="批准指定 ID 的规则")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    if args.approve:
        if approve_candidate(args.approve):
            sys.exit(0)
        else:
            sys.exit(1)

    # 生成候选列表
    md, candidates = generate_markdown_candidate_list(limit=args.limit)

    if args.json:
        output = {
            "candidates_count": len(candidates),
            "candidates": candidates,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(md)
        print(f"\n## 候选规则数据 (JSON)\n")
        print(json.dumps(candidates, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
