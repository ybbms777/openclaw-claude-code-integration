#!/usr/bin/env python3
"""
compact_guardian.py — 压缩熔断守护脚本

功能：
  guardian <session_id>   检查当前 session 是否被熔断（返回 JSON）
  fail    <session_id>    记录一次压缩失败
  success <session_id>    记录一次压缩成功（重置计数器）

状态存储：~/.openclaw/workspace/skills/compact-guardian/circuit_state.json

熔断规则：
  - 连续失败次数 >= 3 → 触发熔断
  - 熔断后该 session 停止触发自动压缩
  - 每次 success 调用重置计数器
  - session 结束由调用方负责重置（调用 success）
"""

import json
import os
import sys
import time
from pathlib import Path

GUARDIAN_DIR = Path.home() / ".openclaw" / "workspace" / "skills" / "compact-guardian"
STATE_FILE = GUARDIAN_DIR / "circuit_state.json"
MAX_FAILURES = 3


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"sessions": {}, "tripped": {}}


def save_state(state: dict) -> None:
    GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_guardian(session_id: str) -> None:
    """检查 session 是否已熔断"""
    state = load_state()
    sessions = state.get("sessions", {})
    session_data = sessions.get(session_id, {})
    failures = session_data.get("failures", 0)
    tripped = failures >= MAX_FAILURES

    print(
        json.dumps(
            {
                "allow": tripped is False,
                "failures": failures,
                "tripped": tripped,
                "reason": (
                    f"consecutive failures ({failures}) >= {MAX_FAILURES}"
                    if tripped
                    else None
                ),
            },
            ensure_ascii=False,
        )
    )


def cmd_fail(session_id: str, reason: str) -> None:
    """记录一次压缩失败"""
    state = load_state()
    sessions = state.setdefault("sessions", {})
    session_data = sessions.setdefault(session_id, {})

    failures = session_data.get("failures", 0)
    session_data["failures"] = failures + 1
    session_data["last_failure"] = reason
    session_data["last_failure_at"] = int(time.time())

    save_state(state)

    current = session_data["failures"]
    if current >= MAX_FAILURES:
        print(
            json.dumps(
                {
                    "status": "tripped",
                    "failures": current,
                    "max_failures": MAX_FAILURES,
                    "message": f"熔断触发！连续失败 {current} 次，停止自动压缩。请手动 /compact 处理。",
                },
                ensure_ascii=False,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "status": "recorded",
                    "failures": current,
                    "max_failures": MAX_FAILURES,
                },
                ensure_ascii=False,
            )
        )


def cmd_success(session_id: str) -> None:
    """记录一次压缩成功，重置计数器"""
    state = load_state()
    sessions = state.get("sessions", {})
    session_data = sessions.get(session_id, {})

    was_tripped = session_data.get("failures", 0) >= MAX_FAILURES
    session_data["failures"] = 0
    session_data["last_success_at"] = int(time.time())
    sessions[session_id] = session_data
    save_state(state)

    print(
        json.dumps(
            {
                "status": "reset",
                "failures": 0,
                "was_tripped": was_tripped,
            },
            ensure_ascii=False,
        )
    )


def cmd_reset(session_id: str) -> None:
    """重置 session 计数器（session 结束时调用）"""
    state = load_state()
    sessions = state.get("sessions", {})
    if session_id in sessions:
        del sessions[session_id]
        save_state(state)
    print(
        json.dumps(
            {
                "status": "reset",
                "session_id": session_id,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    if len(sys.argv) < 3:
        print(
            json.dumps(
                {"error": "Usage: compact_guardian.py <guardian|fail|success|reset> <session_id> [--reason ...]"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = sys.argv[1].lower()
    session_id = sys.argv[2]

    if cmd == "guardian":
        cmd_guardian(session_id)
    elif cmd == "fail":
        reason = ""
        if len(sys.argv) >= 5 and sys.argv[3] == "--reason":
            reason = sys.argv[4]
        cmd_fail(session_id, reason)
    elif cmd == "success":
        cmd_success(session_id)
    elif cmd == "reset":
        cmd_reset(session_id)
    else:
        print(
            json.dumps({"error": f"Unknown command: {cmd}"}),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
