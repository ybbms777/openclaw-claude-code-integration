#!/usr/bin/env python3
"""
cache_monitor.py — 静态层 hash 追踪脚本

功能：
  计算静态层文件 hash，与上次记录对比，检测 cache 失效
  用法：
    python3 cache_monitor.py [--init]      # 初始化/更新 hash 记录
    python3 cache_monitor.py [--check]     # 检查并输出变更报告
    python3 cache_monitor.py              # 等同于 --check
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path.home() / ".openclaw" / "workspace"
STATE_FILE = WORKSPACE / ".cache-monitor.json"

STATIC_FILES = [
    "SOUL.md",
    "AGENTS.md",
    "TOOLS.md",
    "USER.md",
    "IDENTITY.md",
    "HEARTBEAT.md",
    "STATIC.md",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_updated": None, "hashes": {}, "change_log": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def compute_hashes() -> dict[str, str]:
    """计算所有静态文件的 hash 和大小"""
    results = {}
    for fname in STATIC_FILES:
        fpath = WORKSPACE / fname
        if fpath.exists():
            results[fname] = {
                "hash": sha256_file(fpath),
                "size": fpath.stat().st_size,
                "exists": True,
            }
        else:
            results[fname] = {"hash": None, "size": 0, "exists": False}
    return results


def run_check() -> list[str]:
    """检查变更，返回变更信息列表"""
    state = load_state()
    new_hashes = compute_hashes()
    changes = []

    for fname, info in new_hashes.items():
        old_hash = state.get("hashes", {}).get(fname, {}).get("hash")
        new_hash = info["hash"]
        if old_hash is not None and new_hash != old_hash:
            changes.append({
                "file": fname,
                "old_hash": old_hash,
                "new_hash": new_hash,
            })

    # 更新 state
    state["last_updated"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S")
    state["hashes"] = new_hashes

    if changes:
        for ch in changes:
            fname = ch["file"]
            # 查找上次变更原因
            last_reason = ""
            for entry in reversed(state.get("change_log", [])):
                if entry.get("file") == fname:
                    last_reason = entry.get("reason", "")
                    break
            changes_info = f"⚠️ Cache 失效：{fname} 已变更"
            if last_reason:
                changes_info += f"（上次变更原因：{last_reason}）"
            changes_info += f"，本次对话静态层需重新计算"
            print(changes_info)
    else:
        print("Cache 状态：无变更，静态层 hash 未变化", flush=True)

    save_state(state)
    return changes


def run_init() -> dict:
    """初始化/更新 hash 记录，返回当前所有 hash 信息"""
    new_hashes = compute_hashes()
    state = load_state()
    state["last_updated"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S")
    state["hashes"] = new_hashes
    save_state(state)
    return new_hashes


def format_report(hashes: dict) -> list[str]:
    """格式化 hash 报告"""
    lines = ["🗂️ **Cache Monitor — 静态层 Hash 报告**"]
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    lines.append(now)
    lines.append("")
    lines.append("| 文件 | Hash (前16位) | 大小 |")
    lines.append("|------|---------------|------|")
    total_size = 0
    for fname in STATIC_FILES:
        info = hashes.get(fname, {})
        if info.get("exists"):
            h = info["hash"]
            size = info["size"]
            total_size += size
            lines.append(f"| {fname} | `{h[:16]}...` | {size:,} bytes |")
        else:
            lines.append(f"| {fname} | — | 不存在 |")
    lines.append("")
    lines.append(f"**总大小：{total_size:,} bytes（{total_size/1024:.1f} KB）**")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache Monitor")
    parser.add_argument("--init", action="store_true", help="初始化/更新 hash 记录")
    parser.add_argument("--check", action="store_true", help="检查变更")
    args = parser.parse_args()

    if args.init:
        hashes = run_init()
        for line in format_report(hashes):
            print(line)
    elif args.check:
        run_check()
    else:
        # 默认：检查变更
        changes = run_check()
        state = load_state()
        # 无论有无变更都输出当前 hash 表
        hashes = state.get("hashes", {})
        if hashes:
            for line in format_report(hashes):
                print(line)


if __name__ == "__main__":
    main()
