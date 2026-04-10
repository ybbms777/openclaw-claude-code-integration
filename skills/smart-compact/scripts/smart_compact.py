#!/usr/bin/env python3
"""
smart_compact.py — 智能压缩决策 + 执行脚本

功能：
  分析当前 session 上下文类型，选择压缩策略
  --dry-run: 只分析不压缩，报告策略和 token 估算
  --compress: 生成 LLM 摘要，压缩 session 文件
  自动触发: token 使用率超过 80% 时触发压缩

用法：
  python3 smart_compact.py --dry-run
  python3 smart_compact.py --compress
  python3 smart_compact.py --compress --force   # 强制压缩（无视阈值）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Telegram ───────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT_ID", "")


def send_telegram(text: str) -> bool:
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except Exception as e:
        print(f"[TG ERROR] {e}", file=sys.stderr)
        return False


# ─── 策略指纹 ─────────────────────────────────────────────────────────────

STRATEGY_PATTERNS = {
    "BDX量化": {
        "strategy": "A",
        "keywords": [
            "bdx", "回测", "选股", "因子", "策略", "rsrs", "涨停",
            "沪深300", "a股", "kdj", "macd", "rsi", "boll",
            "资金流向", "北向资金", "融资融券", "筹码", "主力",
            "sklearn", "pyqlib", "akshare", "baostock", "qmt",
            "量化", "因子分析", "组合优化", "择时", "趋势"
        ],
        "code_markers": ["def ", "import ", "akshare", "baostock", "pandas", "numpy"],
        "keep_tokens_kb": 12,
        "drop": ["中间计算", "重复数据行", "调试输出"],
    },
    "代码开发": {
        "strategy": "B",
        "keywords": [
            "def ", "class ", "import ", "git commit", "git push",
            "git add", "git merge", "branch", "pull request",
            "python3", "node_modules", "package.json",
            "typescript", "rust", "cargo", "npm install",
            "makefile", "cmake", "dockerfile", "yaml", "json",
            "openclaw", "plugin", "skill", "cron", "session"
        ],
        "code_markers": ["```python", "```typescript", "```bash", "```sh", "```js"],
        "keep_tokens_kb": 10,
        "drop": ["完整代码块", "成功执行的中间命令", "调试日志"],
    },
    "日常对话": {
        "strategy": "C",
        "keywords": [
            "你好", "谢谢", "帮我查", "请问", "问一下",
            "这个", "那个", "怎么", "为什么", "是什么"
        ],
        "code_markers": [],
        "keep_tokens_kb": 6,
        "drop": ["寒暄", "重复确认", "过程性讨论"],
    }
}


# ─── 上下文分析 ──────────────────────────────────────────────────────────

def get_current_session_messages(limit: int = 50) -> list[dict]:
    """通过 openclaw sessions list 获取当前 session 并读取消息"""
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "history", "main", "--limit", str(limit), "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                if isinstance(data, dict) and "messages" in data:
                    return data["messages"]
                elif isinstance(data, list):
                    return data
            except Exception:
                pass
    except Exception as e:
        print(f"[SESSION WARN] {e}", file=sys.stderr)

    # fallback：读取 transcript 文件
    transcripts = sorted(
        Path.home().glob(".openclaw/agents/main/sessions/*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    messages = []
    if transcripts:
        latest = transcripts[0]
        print(f"[TRANSCRIPT] reading {latest.name} ({latest.stat().st_size} bytes)", file=sys.stderr)
        with open(latest) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("role") in ("user", "assistant"):
                        messages.append(obj)
                    elif isinstance(obj, dict) and obj.get("type") == "message":
                        inner = obj.get("message", {})
                        if isinstance(inner, dict) and inner.get("role") in ("user", "assistant"):
                            messages.append(inner)
                except Exception:
                    pass
    print(f"[TRANSCRIPT] loaded {len(messages)} messages", file=sys.stderr)
    return messages[-limit:] if messages else []


def estimate_tokens(text: str) -> int:
    """粗估 token 数（按中文1.5、英文1.0chars/token）"""
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    english = len(re.findall(r'[a-zA-Z0-9]', text))
    other = len(text) - chinese - english
    return int(chinese * 1.5 + english * 0.25 + other * 0.5)


def analyze_context(messages: list[dict]) -> dict:
    """分析上下文，返回策略类型和详情"""
    all_text = ""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            all_text += content + "\n"
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    all_text += block.get("text", "") + "\n"

    all_lower = all_text.lower()
    scores = {"A": 0, "B": 0, "C": 0}
    matched_keywords = {"A": [], "B": [], "C": []}
    code_block_count = len(re.findall(r"```[\s\S]*?```", all_text))

    for name, spec in STRATEGY_PATTERNS.items():
        strategy = spec["strategy"]
        for kw in spec["keywords"]:
            if kw.lower() in all_lower:
                scores[strategy] += 1
                matched_keywords[strategy].append(kw)
        if strategy == "B" and code_block_count >= 3:
            scores["B"] += code_block_count

    total_tokens = estimate_tokens(all_text)
    max_score = max(scores.values())
    if max_score == 0:
        detected = "C"
    elif scores["A"] == max_score and scores["B"] == max_score:
        detected = "D"
    else:
        detected = max(scores, key=scores.get)

    strategy_info = {
        "A": ("BDX量化", STRATEGY_PATTERNS["BDX量化"]),
        "B": ("代码开发", STRATEGY_PATTERNS["代码开发"]),
        "C": ("日常对话", STRATEGY_PATTERNS["日常对话"]),
        "D": ("混合session", None),
    }
    name, spec = strategy_info[detected]
    keep_kb = spec["keep_tokens_kb"] if spec else 8
    keep_tokens = keep_kb * 1000
    retention_rate = min(100, int(keep_tokens / max(total_tokens, 1) * 100))

    return {
        "strategy": detected,
        "strategy_name": name,
        "scores": scores,
        "matched_keywords": matched_keywords[detected],
        "total_tokens": total_tokens,
        "total_tokens_kb": round(total_tokens / 1000, 1),
        "keep_tokens_kb": keep_kb,
        "retention_rate": retention_rate,
        "code_block_count": code_block_count,
        "message_count": len(messages),
    }


def format_dry_run(analysis: dict) -> str:
    s = analysis
    lines = [
        f"🧠 <b>Smart Compact — 策略分析</b>",
        f"{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}",
        "",
        f"检测到：<b>{s['strategy_name']}</b> session（策略 {s['strategy']}）",
        f"消息数：{s['message_count']} 条",
        f"总 token：约 {s['total_tokens_kb']}k",
        "",
        f"<b>策略 {s['strategy']} 详情：</b>",
    ]
    spec_map = {
        "A": ("BDX量化", STRATEGY_PATTERNS["BDX量化"]),
        "B": ("代码开发", STRATEGY_PATTERNS["代码开发"]),
        "C": ("日常对话", STRATEGY_PATTERNS["日常对话"]),
        "D": ("混合session", None),
    }
    name, spec = spec_map[s["strategy"]]
    if spec:
        lines.append(f"保留 token：约 {s['keep_tokens_kb']}k")
        lines.append(f"预计保留率：{s['retention_rate']}%")
        lines.append(f"丢弃内容：{'、'.join(spec['drop'])}")
    if s["matched_keywords"]:
        lines.append(f"匹配关键词：{' '.join(s['matched_keywords'][:8])}")
    if s["strategy"] == "D":
        lines.extend([
            "",
            "<b>策略 D 混合 session：</b>",
            f"BDX关键词命中：{s['scores']['A']} 个",
            f"代码关键词命中：{s['scores']['B']} 个",
            "将按比例分配 token 预算，优先保留最近 30% 内容",
        ])
    lines.extend([
        "",
        "⚠️ 这是 dry-run，未执行任何压缩",
        "",
        "回复 <code>确认</code> 执行实际压缩",
    ])
    return "\n".join(lines)


# ─── MiniMax API ─────────────────────────────────────────────────────────

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_URL = "https://api.minimaxi.com/v1/chat/completions"
CONTEXT_WINDOW = 200000
COMPACT_THRESHOLD = 0.80


def call_minimax(prompt: str, max_tokens: int = 512) -> str:
    if not MINIMAX_API_KEY:
        print("[ERROR] MINIMAX_API_KEY environment variable not set", file=sys.stderr)
        return None
    import urllib.request, urllib.error
    payload = json.dumps({
        "model": "MiniMax-M2",
        "messages": [
            {"role": "system", "content": "你是对话摘要专家。把长对话压缩成简短、有价值的摘要，保留所有关键决策、结论和待办事项。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        MINIMAX_URL, data=payload,
        headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            raw = result["choices"][0]["message"]["content"]
            import re as re2
            raw = re2.sub(r'<thinking>[\s\S]*?</thinking>', '', raw)
            return raw.strip()
    except Exception as e:
        print(f"[MiniMax API ERROR] {e}", file=sys.stderr)
        return None


def generate_summary(messages: list[dict], strategy: str) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            lines.append(f"[{role.upper()}] {content[:500]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")[:500]
                    if text.strip():
                        lines.append(f"[{role.upper()}] {text}")

    session_text = "\n".join(lines[-30:])
    COMPRESS_PROMPT = """你是一个专业的对话压缩助手。请对以下对话内容进行压缩摘要。

要求：
1. 先在 <analysis> 标签里分析：哪些内容重要、哪些可以丢弃、关键决策和结论是什么
2. 再在 <summary> 标签里写最终摘要

重要规则：
- <analysis> 是你的草稿纸，写你的分析思路，不会被保留
- <summary> 才是最终输出，必须包含：核心结论、未完成任务、关键决策、重要数据
- <summary> 控制在原内容的 20% 以内
- BDX 相关内容：保留策略参数、回测结论、失败原因，丢弃中间计算过程
- 代码开发相关：保留任务目标、已完成改动、待完成事项，丢弃完整代码块
- 日常对话相关：保留核心结论，丢弃寒暄和过程性讨论

输出格式：
<analysis>
[你的分析思路，这部分会被丢弃]
</analysis>

<summary>
[最终摘要，只保留这部分]
</summary>
"""
    result = call_minimax(COMPRESS_PROMPT + "\n\n对话：\n" + session_text, max_tokens=1024)
    if not result:
        return "[摘要生成失败]"
    import re as _re2
    result = _re2.sub(r'<thinking>[\s\S]*?</thinking>', '', result)
    # Extract only <summary> content, discard <analysis>
    summary_match = _re2.search(r'<summary>\s*([\s\S]*?)\s*</summary>', result)
    if summary_match:
        return summary_match.group(1).strip()
    # Fallback: return as-is if tags not found
    return result


def get_latest_session_file() -> Path | None:
    transcripts = sorted(
        Path.home().glob(".openclaw/agents/main/sessions/*.jsonl"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    return transcripts[0] if transcripts else None


def compact_session(force: bool = False) -> dict:
    session_file = get_latest_session_file()
    if not session_file:
        return {"success": False, "reason": "找不到 session 文件"}

    all_messages = []
    with open(session_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                all_messages.append(obj)
            except Exception:
                pass

    total_text = ""
    for msg in all_messages:
        content = msg.get("content", msg.get("message", {}).get("content", ""))
        if isinstance(content, str):
            total_text += content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_text += block.get("text", "")

    total_tokens = estimate_tokens(total_text)
    usage_ratio = total_tokens / CONTEXT_WINDOW

    print(f"[compact] 文件: {session_file.name}")
    print(f"[compact] 消息: {len(all_messages)} 条, token: ~{total_tokens}, 使用率: {usage_ratio:.1%}")

    if not force and usage_ratio < COMPACT_THRESHOLD:
        return {
            "success": True,
            "reason": f"使用率 {usage_ratio:.1%} < {COMPACT_THRESHOLD:.0%}，无需压缩",
            "token_usage": f"{usage_ratio:.1%}",
            "total_tokens": total_tokens,
        }

    analysis = analyze_context(all_messages[-50:])
    strategy = analysis["strategy"]

    print(f"[compact] 生成摘要 (策略 {strategy}: {analysis['strategy_name']})...")
    summary = generate_summary(all_messages, strategy)
    print(f"[compact] 摘要: {summary[:100]}...")

    keep_count = max(5, int(len(all_messages) * 0.3))
    recent_messages = all_messages[-keep_count:]

    tmp_file = session_file.with_suffix(".jsonl.compacting")
    with open(tmp_file, "w") as f:
        stat_msg = {
            "type": "system", "role": "system",
            "content": f"<compact_boundary pre_token_count={total_tokens} pre_msg_count={len(all_messages)} strategy={strategy}>\n压缩摘要：{summary}",
            "is_compact_boundary": True,
        }
        f.write(json.dumps(stat_msg, ensure_ascii=False) + "\n")
        for msg in recent_messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    try:
        tmp_file.rename(session_file)
    except OSError as e:
        print(f"[compact] 文件重命名失败: {e}", file=sys.stderr)
        # Fallback: copy and delete
        import shutil
        shutil.copy2(tmp_file, session_file)
        tmp_file.unlink()

    def safe_content(msg):
        c = msg.get("content") or msg.get("message", {}).get("content") or ""
        if isinstance(c, list):
            return " ".join(b.get("text","") if isinstance(b,dict) else str(b) for b in c)
        return str(c) if c else ""

    new_tokens = sum(estimate_tokens(safe_content(msg)) for msg in recent_messages)
    new_usage = new_tokens / CONTEXT_WINDOW

    return {
        "success": True,
        "summary": summary,
        "strategy": strategy,
        "strategy_name": analysis["strategy_name"],
        "pre_msg_count": len(all_messages),
        "post_msg_count": len(recent_messages) + 1,
        "pre_tokens": total_tokens,
        "post_tokens": new_tokens,
        "pre_usage": f"{usage_ratio:.1%}",
        "post_usage": f"{new_usage:.1%}",
        "saved_tokens": total_tokens - new_tokens,
    }


# ─── 主流程 ────────────────────────────────────────────────────────────────

def run_dry_run() -> None:
    ts = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] Smart Compact Dry-Run 开始")
    messages = get_current_session_messages(limit=80)
    print(f"  获取到 {len(messages)} 条消息")
    if not messages:
        send_telegram("⚠️ Smart Compact：无法获取 session 历史，请检查权限")
        return
    analysis = analyze_context(messages)
    print(f"  策略: {analysis['strategy_name']} ({analysis['strategy']})")
    print(f"  总 token: {analysis['total_tokens_kb']}k")
    print(f"  保留率: {analysis['retention_rate']}%")
    report = format_dry_run(analysis)
    send_telegram(report)
    print(f"  报告已发送")


def run_compress(force: bool = False) -> None:
    ts = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{ts.strftime('%Y-%m-%d %H:%M:%S')}] Smart Compact 执行开始")
    result = compact_session(force=force)
    if not result["success"]:
        send_telegram(f"⚠️ Smart Compact 失败：{result['reason']}")
        return
    if "无需压缩" in result.get("reason", ""):
        print(f"[compact] 跳过: {result['reason']}")
        return
    summary = result['summary']
    if len(summary) > 500:
        summary = summary[:500] + "..."

    report = f"""🗜️ <b>Smart Compact 压缩完成</b>

策略：{result['strategy_name']}（{result['strategy']}）
压缩前：{result['pre_msg_count']}条 {result['pre_usage']} → 压缩后：{result['post_msg_count']}条 {result['post_usage']}
节省：约 {result['saved_tokens']} token

【摘要】
{summary}"""
    send_telegram(report)
    print(f"[compact] 压缩完成: {result['pre_usage']} → {result['post_usage']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Compact")
    parser.add_argument("--dry-run", action="store_true", help="只分析不压缩")
    parser.add_argument("--analyze-only", action="store_true", help="等同于 dry-run")
    parser.add_argument("--compress", action="store_true", help="执行实际压缩（生成摘要）")
    parser.add_argument("--force", action="store_true", help="强制压缩（无视阈值）")
    args = parser.parse_args()

    if args.compress:
        run_compress(force=args.force)
    elif args.dry_run or args.analyze_only:
        run_dry_run()
    else:
        print("用法：smart_compact.py --dry-run | --compress [--force]")
        sys.exit(1)
