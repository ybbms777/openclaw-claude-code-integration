#!/usr/bin/env python3
"""
self_eval.py — 自我评估脚本

在 session_end 时自动运行：
1. 读取当前 session 历史
2. 检查三种情况：用户纠正 / 工具重试失败 / 上报规则触发
3. 有任一情况 → memory_store 写入 reflection 记忆 + LEARNINGS.md（仅纠正）
4. 无情况 → 静默退出
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.session import SessionResolver
from oeck.runtime_core.workspace import WorkspaceResolver
from skills.shared.config import (
    WORKSPACE,
    LANCE_DB_PATH,
    LEARNINGS_FILE,
)
from skills.shared.logger import get_logger

logger = get_logger(__name__)

STATE_FILE = WORKSPACE / ".self_eval.json"
SESSION_RESOLVER = SessionResolver(WorkspaceResolver.from_workspace(WORKSPACE))


# ─── 读取 session 历史 ─────────────────────────────────────────────────────

def get_latest_transcript_path() -> Path | None:
    return SESSION_RESOLVER.latest_transcript_path()


def load_session_messages(limit: int = 200) -> list[dict]:
    """读取当前 session 最新 N 条消息"""
    return SESSION_RESOLVER.load_messages(limit=limit)


def extract_text(content) -> str:
    """从消息 content 字段中提取纯文本"""
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                t = b.get("text", "")
                if not t.strip().startswith("{"):
                    parts.append(t)
        return " ".join(parts)
    return str(content)


# ─── 检测条件 ─────────────────────────────────────────────────────────────

CORRECTION_PATTERNS_EXPLICIT = [
    r"\b不对\b", r"\b不是\b", r"\b重来\b", r"\b重新做\b", r"\b错了\b",
    r"\b纠正\b", r"我想要的是", r"其实我想要",
    r"\bno\b", r"not right", r"\bwrong\b", r"\bmistake\b",
    r"不是要这个", r"\b我说的是\b", r"\b你应该\b", r"\b不对啊\b",
    r"不是这个", r"不对的",
]

# 隐式纠正模式：语气强烈暗示 agent 行为有误，但未直接说"不对"
CORRECTION_PATTERNS_IMPLICIT = [
    r"又这样了", r"又卡了", r"又不回复", r"为什么(没有|不|又)",
    r"怎么(又|还|老是)", r"这不是.*麻烦", r"\b太慢了\b",
    r"还是没有", r"没有任何", r"\b不对[啊吧]?\b",
    r"停下来", r"你搞错了", r"不是这个意思",
    r"我说的不是", r"不用.*了", r"\b算了\b",
]

CORRECTION_PATTERNS = CORRECTION_PATTERNS_EXPLICIT + CORRECTION_PATTERNS_IMPLICIT

# 排除模式：陈述客观事实而非纠正 AI
CORRECTION_EXCLUDE = [
    r"市场不对", r"数据不对", r"价格不对", r"数字不对",
    r"名字不对", r"地址不对", r"时间不对", r"日期不对",
    r"顺序不对", r"格式不对", r"配置不对",
]

TOOL_FAILURE_PATTERNS = [
    r"重试.*次.*仍失败",
    r"失败.*次.*已停止",
    r"工具调用失败",
    r"tool.*failed.*retry",
    r"rejected.*tool.*call",
]

BDX_FAILURE_PATTERNS = [
    r"bdx.*失败", r"BDX.*失败", r"\bbdx.*error", r"\bBDX.*error",
    r"\bBDX.*告警", r"\bbdx.*alert", r"\bqmt.*失败", r"\bakshare.*失败",
    r"回测.*失败", r"策略.*失败", r"量化.*失败",
]

PAUSE_CONFIRM_PATTERNS = [
    r"需要我确认", r"先告诉我", r"暂停.*等",
    r"must.*confirm", r"等我.*指示",
]


def detect_corrections(messages: list[dict]) -> list[dict]:
    """检测用户纠正语句（含显式+隐式），返回每个纠正及其前一跳 assistant 消息"""
    findings = []
    user_messages = [m for m in messages if m.get("role") == "user"]
    msg_idx_map = {id(m): i for i, m in enumerate(messages)}

    for msg in user_messages:
        idx = msg_idx_map.get(id(msg), -1)
        text = extract_text(msg.get("content", ""))

        # 跳过含元数据块的消息
        if not text.strip() or re.search(
            r"(relevant-memories|Conversation info|Sender \(untrusted|UNTRUSTED DATA|message_id|sender_id|metadata)",
            text, re.IGNORECASE
        ):
            continue

        # 排除无关语境
        for exc in CORRECTION_EXCLUDE:
            if re.search(exc, text, re.IGNORECASE):
                break
        else:
            for pattern in CORRECTION_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    # 取前一条 assistant 消息作为上下文
                    prev_assistant = ""
                    if idx > 0:
                        for prev in reversed(messages[:idx]):
                            if prev.get("role") == "assistant":
                                prev_assistant = extract_text(prev.get("content", ""))[:200]
                                break

                    findings.append({
                        "type": "user_correction",
                        "pattern": pattern,
                        "pattern_type": "implicit" if pattern in CORRECTION_PATTERNS_IMPLICIT else "explicit",
                        "excerpt": text[:200],
                        "prev_assistant": prev_assistant,
                        "timestamp": msg.get("timestamp"),
                    })
                    break
    return findings


def detect_tool_failures(messages: list[dict]) -> list[dict]:
    """检测工具重试失败（去重：同一工具只记录一次）"""
    findings = []
    seen_tools = set()
    for msg in messages:
        text = extract_text(msg.get("content", ""))
        for pattern in TOOL_FAILURE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                tool_match = re.search(r"tool[:\s]+(\w+)", text, re.IGNORECASE)
                tool_name = tool_match.group(1).lower() if tool_match else pattern
                if tool_name in seen_tools:
                    continue
                seen_tools.add(tool_name)
                findings.append({
                    "type": "tool_failure",
                    "pattern": pattern,
                    "tool": tool_name,
                    "excerpt": text[:200],
                })
                break
    return findings


def detect_bdx_failures(messages: list[dict]) -> list[dict]:
    """检测 BDX 相关工具失败（只在非 assistant 消息中匹配，避免误报）"""
    findings = []
    for msg in messages:
        if msg.get("role") == "assistant":
            continue
        text = extract_text(msg.get("content", ""))
        for pattern in BDX_FAILURE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                findings.append({
                    "type": "bdx_failure",
                    "pattern": pattern,
                    "excerpt": text[:200],
                })
                break
    return findings


def detect_pause_rules(messages: list[dict]) -> list[dict]:
    """检测上报规则触发"""
    findings = []
    for msg in messages:
        text = extract_text(msg.get("content", ""))
        if not text.strip() or re.search(
            r"(relevant-memories|Conversation info|Sender \(untrusted|UNTRUSTED DATA|message_id|sender_id|metadata)",
            text, re.IGNORECASE
        ):
            continue
        for pattern in PAUSE_CONFIRM_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                findings.append({
                    "type": "pause_confirm",
                    "pattern": pattern,
                    "excerpt": text[:200],
                })
                break
    return findings


# ─── 写入 LEARNINGS.md ────────────────────────────────────────────────────

def store_learnings_md(findings: list[dict]) -> int:
    """将纠正写入 LEARNINGS.md，返回写入条数"""
    if not findings:
        return 0

    LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有内容，避免重复追加
    existing = ""
    if LEARNINGS_FILE.exists():
        existing = LEARNINGS_FILE.read_text()

    entries = []
    now = datetime.now(timezone(timedelta(hours=8)))
    ts = now.strftime("%Y-%m-%d %H:%M")

    for f in findings:
        prev = f.get("prev_assistant", "")[:50].replace("\n", " ").strip()
        user_text = f.get("excerpt", "")[:50].replace("\n", " ").strip()
        entry = f"""## [{ts}] 用户纠正
- 触发词：{f['pattern']}（{'隐式' if f.get('pattern_type') == 'implicit' else '显式'}）
- 上下文：{user_text}
- agent 行为：{prev}
- 状态：pending
"""
        entries.append(entry)

    # 追加到文件
    with open(LEARNINGS_FILE, "a", encoding="utf-8") as fw:
        fw.write("\n".join(entries) + "\n")

    logger.info(f"写入 {len(entries)} 条到 LEARNINGS.md")
    return len(entries)


# ─── 写入 LanceDB ─────────────────────────────────────────────────────────

def store_reflection(category: str, content: str, importance: float = 0.9) -> bool:
    """写入 reflection 记忆到 LanceDB"""
    try:
        import lancedb
    except ImportError:
        logger.error("lancedb not installed")
        return False

    now_ms = int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)
    import hashlib
    record_id = hashlib.sha256(f"reflection_{now_ms}".encode()).hexdigest()[:16]

    meta = {
        "l0_abstract": content[:100],
        "category": category,
        "source": "self_eval",
        "created_at": now_ms,
    }

    import urllib.request, urllib.error

    SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
    SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"

    def get_embedding(text: str) -> list[float]:
        if not SILICONFLOW_API_KEY:
            # Fallback to MiniMax if SiliconFlow key not set
            return _get_embedding_minimax(text)
        payload = json.dumps({
            "model": "BAAI/bge-m3",
            "input": text[:2000],
            "encoding_format": "float"
        }).encode("utf-8")
        req = urllib.request.Request(
            SILICONFLOW_EMBED_URL,
            data=payload,
            headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}", "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())["data"][0]["embedding"]
        except Exception:
            return _get_embedding_minimax(text)

    def _get_embedding_minimax(text: str) -> list[float]:
        MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
        if not MINIMAX_API_KEY:
            logger.warning("no embedding API key available, using hash fallback")
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [0.0] * 1024
            for i in range(min(len(h), 1024)):
                vec[i] = (h[i] / 255.0) * 2 - 1
            return vec
        MINIMAX_EMBED_URL = "https://api.minimaxi.com/v1/embeddings"
        payload2 = json.dumps({"model": "minimax-embedding", "input": text[:2000]}).encode("utf-8")
        req2 = urllib.request.Request(
            MINIMAX_EMBED_URL, data=payload2,
            headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                return json.loads(resp2.read())["data"][0]["embedding"]
        except Exception as e2:
            logger.warning(f"embedding failed: {e2}, using hash fallback")
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [0.0] * 1024
            for i in range(min(len(h), 1024)):
                vec[i] = (h[i] / 255.0) * 2 - 1
            return vec

    vector = get_embedding(content)
    db = lancedb.connect(str(LANCE_DB_PATH))
    tbl = db.open_table("memories")
    tbl.add([{
        "id": record_id,
        "text": content,
        "vector": vector,
        "category": category,
        "scope": "agent",
        "importance": importance,
        "timestamp": float(now_ms) / 1000,
        "metadata": json.dumps(meta, ensure_ascii=False),
        "uri": "",
        "access_count": 0,
    }])
    logger.debug(f"stored reflection: {record_id}")
    return True


def build_reflection_text(finding: dict, context: str = "") -> str:
    """构建反思记忆文本"""
    t = finding["type"]
    excerpt = finding.get("excerpt", "")[:150]

    if t == "user_correction":
        pattern_type = finding.get("pattern_type", "explicit")
        prefix = "隐式" if pattern_type == "implicit" else "显式"
        return (
            f"自我评估：在用户纠正场景下判断失误/处理不当（{prefix}纠正）。"
            f"正确做法：收到「不对/重来/错了/又」时立即停止当前思路，重新理解需求再行动。"
            f"触发原因：{prefix}纠正 | 触发词：{finding['pattern']} | 内容：{excerpt}"
        )
    elif t == "tool_failure":
        return (
            f"失败模式：工具调用在执行过程中失败。"
            f"正确做法：2次重试失败后立即停止，报告原因并等待指示，不尝试绕过。"
            f"错误信息：{excerpt[:100]}"
        )
    elif t == "bdx_failure":
        return (
            f"失败模式：BDX相关工具/操作失败。"
            f"正确做法：立即停止，回退状态，发Telegram告警，不重试。"
            f"错误信息：{excerpt[:100]}"
        )
    elif t == "pause_confirm":
        return (
            f"自我评估：应上报确认的场景未主动暂停。"
            f"正确做法：涉及BDX实盘/生产参数/外部发送/不可逆操作时，必须先确认再执行。"
            f"触发原因：上报规则触发 | 内容：{excerpt}"
        )
    return ""


# ─── 主流程 ──────────────────────────────────────────────────────────────

def run_self_eval(dry_run: bool = False) -> dict:
    """
    执行自我评估。dry_run=True 时只检测不写入，用于测试。
    """
    ts = datetime.now(timezone(timedelta(hours=8)))
    logger.info(f"self_eval {'(dry-run)' if dry_run else ''} 开始")

    messages = load_session_messages(limit=200)
    logger.debug(f"读取 {len(messages)} 条消息")

    if not messages:
        logger.debug("无消息，静默退出")
        return {"status": "silent", "corrections": 0, "failures": 0, "pauses": 0}

    corrections = detect_corrections(messages)
    failures = detect_tool_failures(messages)
    pauses = detect_pause_rules(messages)
    bdx_failures = detect_bdx_failures(messages)

    explicit_corr = [c for c in corrections if c.get("pattern_type") == "explicit"]
    implicit_corr = [c for c in corrections if c.get("pattern_type") == "implicit"]

    logger.info(f"显式纠正: {len(explicit_corr)} | 隐式纠正: {len(implicit_corr)} | 工具失败: {len(failures)} | BDX失败: {len(bdx_failures)} | 上报: {len(pauses)}")

    if dry_run:
        # 只打印检测结果，不写入
        for i, c in enumerate(corrections, 1):
            print(f"\n  [{i}] 触发词: {c['pattern']}（{c.get('pattern_type')}）")
            print(f"      用户: {c['excerpt'][:80]}")
            print(f"      Agent: {c.get('prev_assistant','')[:80]}")
        if not corrections:
            print("  无纠正检测到")
        return {
            "status": "dry_run",
            "corrections": len(corrections),
            "explicit": len(explicit_corr),
            "implicit": len(implicit_corr),
            "failures": len(failures),
            "pauses": len(pauses),
        }

    total = len(corrections) + len(failures) + len(pauses) + len(bdx_failures)
    if total == 0:
        logger.debug("无异常，静默退出")
        return {"status": "silent", "corrections": 0, "failures": 0, "bdx_failures": 0, "pauses": 0}

    stored = 0

    # 纠正 → 写 LEARNINGS.md + LanceDB
    if corrections:
        store_learnings_md(corrections)
        for finding in corrections:
            text = build_reflection_text(finding)
            if text and store_reflection("reflection", text, importance=0.9):
                stored += 1

    for finding in failures:
        text = build_reflection_text(finding)
        if text and store_reflection("reflection", text, importance=0.92):
            stored += 1

    for finding in bdx_failures:
        text = build_reflection_text(finding)
        if text and store_reflection("reflection", text, importance=0.92):
            stored += 1

    for finding in pauses:
        text = build_reflection_text(finding)
        if text and store_reflection("reflection", text, importance=0.92):
            stored += 1

    logger.info(f"已写入 {stored} 条 reflection 记忆")
    return {
        "status": "stored",
        "corrections": len(corrections),
        "explicit": len(explicit_corr),
        "implicit": len(implicit_corr),
        "failures": len(failures),
        "pauses": len(pauses),
        "stored": stored,
    }


if __name__ == "__main__":
    # 默认 dry_run=True 用于手动测试；cron 调用时传 dry_run=False
    dry = "--dry" in sys.argv or "--dry-run" in sys.argv
    result = run_self_eval(dry_run=dry)
    sys.exit(0)
