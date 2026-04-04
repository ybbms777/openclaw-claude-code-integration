#!/usr/bin/env python3
"""
memory_compaction.py — LanceDB 记忆压缩脚本（增强版）

功能：
  1. 备份：操作前备份 LanceDB 到 backups/YYYY-MM-DD/，保留最近 4 份
  2. 删除：importance < 0.3 且 14 天未检索的记忆
  3. 合并：同 scope 下向量相似度 >= 0.85 的碎片，保留最高 importance 的 L0 摘要
  4. 报告：发送到 Telegram

用法：
  python3 memory_compaction.py               # 完整执行
  python3 memory_compaction.py --dry-run      # 只报告会删除/合并哪些，不实际执行
  python3 memory_compaction.py --cron        # cron 调用，错误也发 Telegram
"""

import argparse
import glob
import json
import math
import os
import shutil
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────────────────────────

LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb-pro"
BACKUP_DIR = LANCE_DB_PATH / "backups"
SILICONFLOW_API_KEY = "sk-upwbwgadvnjyeyqspqrnmoimwmodutrocqxxguhtxswywups"
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"

TELEGRAM_BOT_TOKEN = "8466224710:AAHjJS9vzZKBWxGymgJMs7tTPT83AzEfl20"
TELEGRAM_CHAT_ID = "8356965403"

IMPORTANCE_THRESHOLD = 0.3
AGE_DAYS_THRESHOLD = 14
SIMILARITY_THRESHOLD = 0.85
BATCH_SIZE = 8
MAX_BACKUPS = 4

# ─── Telegram ───────────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_BOT_TOKEN,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except Exception as e:
        print("[TG ERROR]", e, file=sys.stderr)
        return False


def send_telegram_safe(text: str) -> None:
    try:
        send_telegram(text)
    except Exception:
        pass


class CompactionError(Exception):
    """任何步骤出错时抛出，触发告警并停止"""
    pass


# ─── 备份 ───────────────────────────────────────────────────────────────────

def create_backup() -> Path:
    """
    创建 LanceDB 备份到 backups/YYYY-MM-DD/。
    保留最近 MAX_BACKUPS 份，更早的自动删除。
    失败则抛出 CompactionError。
    """
    ts = datetime.now(timezone(timedelta(hours=8)))
    date_str = ts.strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / date_str

    if backup_path.exists():
        print(f"[BACKUP] 今日备份已存在: {backup_path}，跳过")
        return backup_path

    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise CompactionError(f"无法创建备份目录 {BACKUP_DIR}: {e}")

    try:
        source_dir = LANCE_DB_PATH
        # 跳过 backups 子目录和运行时锁文件
        skip_names = {"backups", ".memory-write.lock", ".DS_Store"}
        items = [source_dir / i for i in os.listdir(source_dir) if i not in skip_names]
        for item in items:
            dest = backup_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, symlinks=True)
            else:
                shutil.copy2(item, dest)
        print(f"[BACKUP] 已备份到: {backup_path}")
    except Exception as e:
        raise CompactionError(f"备份失败: {e}")

    # 清理旧备份，保留最近 MAX_BACKUPS 份
    try:
        all_backups = sorted(
            [d for d in BACKUP_DIR.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True
        )
        for old in all_backups[MAX_BACKUPS:]:
            shutil.rmtree(old)
            print(f"[BACKUP] 已删除旧备份: {old}")
    except Exception as e:
        print(f"[BACKUP WARN] 清理旧备份失败: {e}", file=sys.stderr)

    return backup_path


# ─── LanceDB ───────────────────────────────────────────────────────────────

def load_memories() -> list[dict]:
    try:
        import lancedb
    except ImportError:
        raise CompactionError("lancedb 未安装，运行: pip install lancedb")

    db = lancedb.connect(str(LANCE_DB_PATH))
    tbl = db.open_table("memories")
    df = tbl.to_pandas()
    records = []
    for _, row in df.iterrows():
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception:
            meta = {}
        records.append({
            "id": row["id"],
            "text": row["text"],
            "vector": list(row["vector"]) if hasattr(row["vector"], "__iter__") else list(row["vector"]),
            "category": row["category"],
            "scope": row["scope"],
            "importance": float(row["importance"]),
            "timestamp": float(row["timestamp"]),
            "last_accessed_at": meta.get("last_accessed_at", 0),
            "access_count": meta.get("access_count", 0),
            "l0_abstract": meta.get("l0_abstract", ""),
            "metadata": meta
        })
    return records


def delete_memories(ids: list[str]) -> int:
    if not ids:
        return 0
    try:
        import lancedb
    except ImportError:
        return 0
    db = lancedb.connect(str(LANCE_DB_PATH))
    tbl = db.open_table("memories")
    for rid in ids:
        tbl.delete(f"id = '{rid}'")
    return len(ids)


def write_merged_record(record: dict) -> None:
    """写入合并后的单条记忆（排除 vector 字段，LanceDB SQL 不支持 list 类型更新）"""
    try:
        import lancedb
    except ImportError:
        return
    db = lancedb.connect(str(LANCE_DB_PATH))
    tbl = db.open_table("memories")
    record["metadata"] = json.dumps(record["metadata"], ensure_ascii=False)
    # 排除 vector（SQL 更新不支持 list 类型），保留原向量不变
    values = {k: v for k, v in record.items() if k not in ("id", "vector")}
    tbl.update(where=f"id = '{record['id']}'", values=values)


# ─── SiliconFlow Embedding ───────────────────────────────────────────────────

def embed_texts_batched(texts: list[str], batch_size: int = BATCH_SIZE) -> list[list[float]]:
    """用 SiliconFlow bge-m3 逐批计算文本向量"""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = json.dumps({
            "model": "BAAI/bge-m3",
            "input": batch,
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
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            embeddings = result["data"]
            embeddings.sort(key=lambda x: x["index"])
            all_embeddings.extend([e["embedding"] for e in embeddings])
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            raise CompactionError(f"SiliconFlow embedding 失败 (offset={i}, HTTP {e.code}): {err_body[:200]}")
        except Exception as e:
            raise CompactionError(f"SiliconFlow embedding 失败 (offset={i}): {e}")
    return all_embeddings


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── 第一步：找出待删除 ─────────────────────────────────────────────────────

def step1_preview(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    返回：(待保留的记录, 待删除的记录)

    删除规则（带 access_count 权重）：
    - access_count == 0（从未检索）：importance < 0.3 且 14 天未访问 → 删除
    - access_count == 1（检索过1次）：importance < 0.3 且 30 天未访问 → 删除
    - access_count >= 3（高频检索）：不删除
    """
    now_ms = time.time() * 1000
    age_cutoff_ms = now_ms - AGE_DAYS_THRESHOLD * 24 * 60 * 60 * 1000
    age_30_cutoff_ms = now_ms - 30 * 24 * 60 * 60 * 1000

    to_delete = []
    kept = []
    for r in records:
        access_count = r.get("access_count", 0)
        if access_count >= 3:
            # 高频检索：不删除
            kept.append(r)
        elif access_count == 1:
            # 检索过1次：延长保留到30天
            if r["importance"] < IMPORTANCE_THRESHOLD and r["last_accessed_at"] < age_30_cutoff_ms:
                to_delete.append(r)
            else:
                kept.append(r)
        else:
            # 从未检索（access_count == 0）：原始规则，14天
            if r["importance"] < IMPORTANCE_THRESHOLD and r["last_accessed_at"] < age_cutoff_ms:
                to_delete.append(r)
            else:
                kept.append(r)
    return kept, to_delete


# ─── 第二步：找出待合并 ─────────────────────────────────────────────────────

def find_merge_clusters(records: list[dict]) -> list[list[dict]]:
    """返回需要合并的簇列表（不做实际合并）"""
    by_scope: dict[str, list[dict]] = {}
    for r in records:
        by_scope.setdefault(r["scope"], []).append(r)

    all_clusters: list[list[dict]] = []

    for scope, group in by_scope.items():
        if len(group) < 2:
            continue

        texts = [r["text"][:2000] for r in group]
        try:
            embeddings = embed_texts_batched(texts, batch_size=BATCH_SIZE)
        except CompactionError:
            raise
        except Exception as e:
            raise CompactionError(f"embedding 失败 (scope={scope}): {e}")

        for r, emb in zip(group, embeddings):
            r["_emb"] = emb

        sorted_group = sorted(group, key=lambda x: x["importance"], reverse=True)
        assigned = set()

        for r in sorted_group:
            if id(r) in assigned:
                continue
            cluster = [r]
            assigned.add(id(r))
            for other in sorted_group:
                if id(other) in assigned:
                    continue
                if cosine_sim(r["_emb"], other["_emb"]) >= SIMILARITY_THRESHOLD:
                    cluster.append(other)
                    assigned.add(id(other))
            if len(cluster) >= 2:
                all_clusters.append(cluster)

    return all_clusters


# ─── Dry-run ────────────────────────────────────────────────────────────────

def run_dry_run() -> dict:
    """只分析，不执行任何写操作"""
    ts = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] Memory Compaction Dry-Run 开始")

    records = load_memories()
    print(f"  当前记忆总数: {len(records)}")

    kept, to_delete = step1_preview(records)
    clusters = find_merge_clusters(kept)

    # 统计合并涉及的记忆条数
    merged_record_ids = set()
    for c in clusters:
        for r in c:
            merged_record_ids.add(r["id"])

    # dry-run 不做实际合并，故最终数量 = 初始 - 待删除 - (合并涉及条数 - 簇数)
    # 因为合并后条数 = 簇数
    actual_deleted = len(to_delete)
    actual_merged = len(merged_record_ids) - len(clusters)  # 合并后净减少

    report_lines = [
        f"🧠 <b>Memory Compaction Dry-Run 报告</b>",
        f"{ts.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"<b>--- 预计变更（未执行）---</b>",
        "",
        f"当前总数: <b>{len(records)}</b>",
        f"待删除: <b>{actual_deleted}</b> 条（importance&lt;{IMPORTANCE_THRESHOLD} & {AGE_DAYS_THRESHOLD}天未访问）",
        f"待合并: <b>{len(clusters)}</b> 簇（影响 {len(merged_record_ids)} 条 → 合并后 <b>{len(clusters)}</b> 条）",
        "",
        f"<b>预计最终总数: {len(records) - actual_deleted - (len(merged_record_ids) - len(clusters))}</b>",
        "",
        f"<b>--- 阈值 ---</b>",
        f"importance &lt; {IMPORTANCE_THRESHOLD}",
        f"未访问 &gt; {AGE_DAYS_THRESHOLD} 天",
        f"向量相似度 ≥ {SIMILARITY_THRESHOLD}（BAAI/bge-m3）",
        "",
        "⚠️ 这是 dry-run，未执行任何实际变更"
    ]

    report = "\n".join(report_lines)
    print(report)
    send_telegram_safe(report)
    return {
        "mode": "dry-run",
        "initial": len(records),
        "to_delete": actual_deleted,
        "merge_clusters": len(clusters),
        "merge_affected": len(merged_record_ids),
        "expected_final": len(records) - actual_deleted - (len(merged_record_ids) - len(clusters)),
    }


# ─── 完整执行 ────────────────────────────────────────────────────────────────

def run_compaction(is_cron: bool = False) -> dict:
    ts_start = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{ts_start.strftime('%Y-%m-%d %H:%M:%S')}] Memory Compaction 开始")

    # Step 0: 加载
    try:
        records = load_memories()
    except CompactionError:
        raise
    except Exception as e:
        raise CompactionError(f"加载记忆失败: {e}")
    print(f"  当前记忆总数: {len(records)}")

    # Step 0.5: 备份
    try:
        create_backup()
    except CompactionError:
        raise
    except Exception as e:
        raise CompactionError(f"备份失败: {e}")

    # Step 1: 删除
    kept, to_delete = step1_preview(records)
    if to_delete:
        deleted_n = delete_memories([r["id"] for r in to_delete])
        print(f"  [Step1] 删除 {deleted_n} 条")
    else:
        print(f"  [Step1] 无需删除")

    # Step 2: 合并
    clusters = find_merge_clusters(kept)
    if clusters:
        for cluster in clusters:
            best = max(cluster, key=lambda x: x["importance"])
            # 保留 cluster 中最高的 access_count（不重置为 0）
            max_access_count = max(r.get("access_count", 0) for r in cluster)
            merged_text_lines = []
            seen = set()
            for r in cluster:
                for line in r["text"].split("\n"):
                    lo = line.strip().lower()
                    if lo and lo not in seen:
                        seen.add(lo)
                        merged_text_lines.append(line.strip())
            merged_text = "\n".join(merged_text_lines)
            best_abstract = best.get("l0_abstract", "") or best["text"][:100]
            new_meta = dict(best["metadata"])
            new_meta.update({
                "compacted": True,
                "source_count": len(cluster),
                "compacted_at": int(time.time() * 1000),
                "l0_abstract": best_abstract,
                "access_count": max_access_count  # 保留 cluster 中最高的计数值
            })
            merged_record = {
                "id": best["id"],
                "text": merged_text,
                "vector": best["vector"],
                "category": best["category"],
                "scope": best["scope"],
                "importance": best["importance"],
                "timestamp": best["timestamp"],
                "access_count": max_access_count,
                "metadata": new_meta
            }
            try:
                write_merged_record(merged_record)
            except CompactionError:
                raise
            except Exception as e:
                raise CompactionError(f"写入合并记录 {best['id']} 失败: {e}")
            # 删除同簇其他记录
            for r in cluster:
                if r["id"] != best["id"]:
                    delete_memories([r["id"]])
        print(f"  [Step2] 合并 {len(clusters)} 个簇")

    # 重新加载确认最终数量
    try:
        final_records = load_memories()
        final_count = len(final_records)
    except CompactionError:
        raise
    except Exception as e:
        raise CompactionError(f"加载最终结果失败: {e}")

    ts_end = datetime.now(timezone(timedelta(hours=8)))
    elapsed = (ts_end - ts_start).total_seconds()

    merged_record_ids = sum(len(c) for c in clusters)
    expected_final = len(records) - len(to_delete) - (merged_record_ids - len(clusters))

    result = {
        "initial": len(records),
        "deleted": len(to_delete),
        "merged_clusters": len(clusters),
        "final": final_count,
        "elapsed_s": round(elapsed, 1),
        "started_at": ts_start.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": ts_end.strftime("%Y-%m-%d %H:%M:%S")
    }

    print(f"  最终记忆数: {final_count}（删除 {len(to_delete)} 条，合并 {len(clusters)} 簇）")
    print(f"  耗时: {elapsed:.1f}s")

    # 发送报告
    report = (
        f"🧠 <b>Memory Compaction 报告</b>\n"
        f"{ts_end.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"启动: {result['started_at']}\n"
        f"耗时: {result['elapsed_s']}s\n\n"
        f"--- 结果 ---\n"
        f"记忆总数: {result['initial']} → <b>{result['final']}</b>\n"
        f"删除: <b>{result['deleted']}</b> 条\n"
        f"合并: <b>{result['merged_clusters']}</b> 簇\n\n"
        f"阈值: importance&lt;{IMPORTANCE_THRESHOLD} & {AGE_DAYS_THRESHOLD}天未访问\n"
        f"相似度: ≥{SIMILARITY_THRESHOLD}（BAAI/bge-m3）\n"
        f"备份: {BACKUP_DIR.name}/{ts_start.strftime('%Y-%m-%d')}/"
    )
    send_telegram_safe(report)
    return result


# ─── 主入口 ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LanceDB Memory Compaction")
    parser.add_argument("--cron", action="store_true", help="cron 调用模式，错误也发 Telegram")
    parser.add_argument("--dry-run", action="store_true", help="只分析，不执行写操作")
    args = parser.parse_args()

    try:
        if args.dry_run:
            run_dry_run()
        else:
            run_compaction(is_cron=args.cron)
            if args.cron:
                print(f"[DONE] compaction finished")
    except CompactionError as e:
        err_msg = f"❌ Memory Compaction 熔断：{e}，停止执行"
        print(err_msg, file=sys.stderr)
        send_telegram_safe(err_msg)
        sys.exit(1)
    except Exception as e:
        err_msg = f"❌ Memory Compaction 异常：{e}"
        print(err_msg, file=sys.stderr)
        if args.cron:
            send_telegram_safe(err_msg)
        raise


if __name__ == "__main__":
    main()
