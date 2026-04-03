#!/usr/bin/env python3
"""
self_eval.py — 自我评估脚本

在 session_end 时自动运行：
1. 读取当前 session 历史
2. 检查三种情况：用户纠正 / 工具重试失败 / 上报规则触发
3. 有任一情况 → memory_store 写入 reflection 记忆
4. 无情况 → 静默退出
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path.home() / ".openclaw" / "workspace"
MEMORY_STORE_SCRIPT = WORKSPACE / "skills" / "memory-lancedb-pro" / "scripts" / "memory_store.py"
LANCE_DB_PATH = Path.home() / ".openclaw" / "memory" / "lancedb-pro"
STATE_FILE = WORKSPACE / ".self_eval.json"

# ─── 读取 session 历史 ─────────────────────────────────────────────────────

def get_latest_transcript_path() -> Path | None:
    transcripts = sorted(
        Path.home().glob(".openclaw/agents/main/sessions/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return transcripts[0] if transcripts else None


def load_session_messages(limit: int = 200) -> list[dict]:
    """读取当前 session 最新 N 条消息"""
    transcript_path = get_latest_transcript_path()
    if not transcript_path:
        return []

    messages = []
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "message":
                    inner = obj.get("message", {})
                    if isinstance(inner, dict) and inner.get("role") in ("user", "assistant"):
                        messages.append(inner)
                elif isinstance(obj, dict) and obj.get("role") in ("user", "assistant"):
                    messages.append(obj)
            except Exception:
                pass
    return messages[-limit:]


# ─── 检测条件 ─────────────────────────────────────────────────────────────

CORRECTION_PATTERNS = [
    r"不对", r"不是", r"重来", r"重新做", r"错了", r"不对的",
    r"不是这个", r"纠正", r"我想要的是", r"其实我想要",
    r"no,?", r"not right", r"wrong", r"mistake",
    r"不是要这个", r"我说的是", r"你应该", r"不对啊",
]

# 排除模式：单独出现但不是在纠正AI
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
    r"bdx.*失败",
    r"BDX.*失败",
    r"bdx.*error",
    r"BDX.*error",
    r"BDX.*告警",
    r"bdx.*alert",
    r"qmt.*失败",
    r"akshare.*失败",
    r"回测.*失败",
    r"策略.*失败",
    r"量化.*失败",
]

PAUSE_CONFIRM_PATTERNS = [
    r"需要我确认",
    r"先告诉我",
    r"暂停.*等",
    r"must.*confirm",
    r"等我.*指示",
]


def detect_corrections(messages: list[dict]) -> list[dict]:
    """检测用户纠正语句（只在 role==user 的消息里匹配，排除无关语境）"""
    findings = []
    user_messages = [m for m in messages if m.get("role") == "user"]
    for msg in user_messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    t = b.get("text", "")
                    if not t.strip().startswith("{"):
                        parts.append(t)
            text = " ".join(parts)
        else:
            text = str(content)
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
                    findings.append({
                        "type": "user_correction",
                        "pattern": pattern,
                        "excerpt": text[:200],
                        "timestamp": msg.get("timestamp"),
                    })
                    break
    return findings


def detect_tool_failures(messages: list[dict]) -> list[dict]:
    """检测工具重试失败（去重：同一工具只记录一次）"""
    findings = []
    seen_tools = set()
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = str(content)
        for pattern in TOOL_FAILURE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # 提取工具名（从内容中找 "tool XXX failed" 之类）
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
    """检测 BDX 相关工具失败"""
    findings = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = str(content)
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
    """检测上报规则触发（跳过含JSON元数据的消息，只看真实文本）"""
    findings = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    t = b.get("text", "")
                    # 跳过纯JSON元数据行
                    if not t.strip().startswith("{"):
                        parts.append(t)
            text = " ".join(parts)
        else:
            text = str(content)
        # 跳过包含元数据块的消息
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


# ─── 写入 LanceDB ─────────────────────────────────────────────────────────

def store_reflection(category: str, content: str, importance: float = 0.9) -> bool:
    """通过 lance_db 直接写入 reflection 记忆"""
    try:
        import lancedb
    except ImportError:
        print("[ERROR] lancedb not installed", file=sys.stderr)
        return False

    now_ms = int(datetime.now(timezone(timedelta(hours=8))).timestamp() * 1000)
    import hashlib, time as _time
    record_id = hashlib.sha256(f"reflection_{now_ms}".encode()).hexdigest()[:16]

    meta = {
        "l0_abstract": content[:100],
        "category": category,
        "source": "self_eval",
        "created_at": now_ms,
    }


    # ─── MiniMax embedding ──────────────────────────────────────────────
    import urllib.request, urllib.error

    MINIMAX_API_KEY = "sk-cp-DtqXh99hmgbdLdYAyGJBi22-15cNDkRT08C8ZRhwSWz6P7wprqHfPIAsc5VgR2OlZqn-Jw8aYI-cZpnoWnScq2jS99nc-MfFASRsDHoJP5QTJ38Mxc1Nylw"
    MINIMAX_EMBED_URL = "https://api.minimaxi.com/v1/embeddings"

    def get_embedding(text: str) -> tuple[list[float], bool]:
        """
        调用 MiniMax bge-m3 (embo1) 获取文本 embedding（1024维）。
        API format: POST /v1/embeddings, body: {"model":"embo1","type":"db_compute","texts":[...]}
        返回 (vector, is_fallback)。is_fallback=True 表示使用了 hash 伪向量。
        """
        payload = json.dumps({
            "model": "embo1",
            "type": "db_compute",
            "texts": [text[:2000]],  # 截断避免超限，MiniMax 要求 texts 数组
        }).encode("utf-8")
        req = urllib.request.Request(
            MINIMAX_EMBED_URL,
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
                vectors = result.get("vectors")
                if vectors and vectors[0]:
                    return vectors[0], False
                # vectors 为 null 说明账户余额不足
                raise ValueError(f"MiniMax returned null vectors: {result.get('base_resp')}")
        except Exception as e:
            err_str = str(e)
            if "null vectors" in err_str:
                print(f"[self_eval] MiniMax embedding returned null (insufficient balance) — FALLBACK: hash pseudo vector", file=sys.stderr)
            else:
                print(f"[self_eval] MiniMax embedding API failed: {e} — FALLBACK: hash pseudo vector", file=sys.stderr)
            # FALLBACK: 基于文本内容的确定性伪向量（相同文本产生相同向量，但语义质量差，仅作保底）
            import hashlib
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [0.0] * 1024
            for i in range(min(len(h), 1024)):
                vec[i] = (h[i] / 255.0) * 2 - 1  # [-1, 1] 范围
            return vec, True

    vector, is_fallback = get_embedding(content)

    if is_fallback:
        print(f"[self_eval] WARNING: using FALLBACK hash vector for reflection {record_id}", file=sys.stderr)

    db = lancedb.connect(str(LANCE_DB_PATH))
    tbl = db.open_table("memories")

    tbl.add([
        {
            "id": record_id,
            "text": content,
            "vector": vector,
            "category": category,
            "scope": "agent",
            "importance": importance,
            "timestamp": float(now_ms) / 1000,
            "metadata": json.dumps(meta, ensure_ascii=False),
        }
    ])
    print(f"[self_eval] stored reflection: {record_id} (fallback={is_fallback})")
    return True


def build_reflection_text(finding: dict, context: str = "") -> str:
    """构建反思记忆文本"""
    t = finding["type"]
    excerpt = finding.get("excerpt", "")[:150]

    if t == "user_correction":
        return (
            f"自我评估：在用户纠正场景下判断失误/处理不当。"
            f"正确做法：收到「不对/重来/错了」时立即停止当前思路，重新理解需求再行动。"
            f"触发原因：用户纠正 | 内容：{excerpt}"
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

def run_self_eval() -> dict:
    ts = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] self_eval 开始")

    messages = load_session_messages(limit=200)
    print(f"  读取 {len(messages)} 条消息")

    if not messages:
        print("  无消息，静默退出")
        return {"status": "silent", "corrections": 0, "failures": 0, "pauses": 0}

    corrections = detect_corrections(messages)
    failures = detect_tool_failures(messages)
    pauses = detect_pause_rules(messages)
    bdx_failures = detect_bdx_failures(messages)

    total = len(corrections) + len(failures) + len(pauses) + len(bdx_failures)
    print(f"  纠正: {len(corrections)} | 工具失败: {len(failures)} | BDX失败: {len(bdx_failures)} | 上报: {len(pauses)}")

    if total == 0:
        print("  无异常，静默退出")
        return {"status": "silent", "corrections": 0, "failures": 0, "bdx_failures": 0, "pauses": 0}

    stored = 0
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

    print(f"  已写入 {stored} 条 reflection 记忆")
    return {
        "status": "stored",
        "corrections": len(corrections),
        "failures": len(failures),
        "pauses": len(pauses),
        "stored": stored,
    }


if __name__ == "__main__":
    result = run_self_eval()
    sys.exit(0)
