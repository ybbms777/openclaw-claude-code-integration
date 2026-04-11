#!/usr/bin/env python3
"""
notify_telegram.py — 通过 Telegram Bot 发送通知

用法：python3 notify_telegram.py <消息内容>

使用环境变量或硬编码凭证发送 Telegram 消息。
"""

import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import json

from skills.shared.logger import get_logger

logger = get_logger(__name__)

# 配置 — 从环境变量读取（需在 ~/.openclaw/.env 中配置）
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT_ID", "")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_telegram_message(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("TG_BOT_TOKEN and TG_CHAT_ID environment variables not set")
        return False
    data = urllib.parse.urlencode(
        {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = resp.read().decode("utf-8")
            parsed = json.loads(result)
            return parsed.get("ok", False)
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def main() -> None:
    if len(sys.argv) < 2:
        logger.error("Usage: notify_telegram.py <message>")
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    ok = send_telegram_message(message)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
