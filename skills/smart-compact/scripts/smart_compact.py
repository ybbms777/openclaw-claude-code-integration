#!/usr/bin/env python3
"""
smart_compact.py — 智能压缩决策脚本

功能：
  分析当前 session 上下文类型，选择对应压缩策略
  dry-run：只分析不压缩，报告策略和 token 估算
  实际执行：按策略执行压缩后报告结果

用法：
  python3 smart_compact.py --dry-run
  python3 smart_compact.py --execute
  python3 smart_compact.py --analyze-only
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

BOT_TOKEN = "8466224710:AAHjJS9vzZKBWxGymgJMs7tTPT83AzEfl20"
CHAT_ID = "8356965403"


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
        # 获取 main session 最近消息
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

    # fallback：读取 transcript 文件（支持两种格式）
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
                    # 格式1：{role, content}
                    if isinstance(obj, dict) and obj.get("role") in ("user", "assistant"):
                        messages.append(obj)
                    # 格式2：{type:"message", message:{role,content,...}}
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

    # 评分
    scores = {"A": 0, "B": 0, "C": 0}
    matched_keywords = {"A": [], "B": [], "C": []}
    code_block_count = len(re.findall(r"```[\s\S]*?```", all_text))

    for name, spec in STRATEGY_PATTERNS.items():
        strategy = spec["strategy"]
        for kw in spec["keywords"]:
            if kw.lower() in all_lower:
                scores[strategy] += 1
                matched_keywords[strategy].append(kw)
        # 代码块加权
        if strategy == "B" and code_block_count >= 3:
            scores["B"] += code_block_count

    total_tokens = estimate_tokens(all_text)

    # 判断策略
    max_score = max(scores.values())
    if max_score == 0:
        detected = "C"
    elif scores["A"] == max_score and scores["B"] == max_score:
        detected = "D"  # 混合
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Compact")
    parser.add_argument("--dry-run", action="store_true", help="只分析不压缩")
    parser.add_argument("--analyze-only", action="store_true", help="等同于 dry-run")
    args = parser.parse_args()

    if args.dry_run or args.analyze_only:
        run_dry_run()
    else:
        print("用法：smart_compact.py --dry-run")
        print("实际压缩由 /compact 命令触发，这里只做策略分析和 Telegram 报告")


if __name__ == "__main__":
    main()
