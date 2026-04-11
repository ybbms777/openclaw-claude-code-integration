#!/usr/bin/env python3
"""
telegram.py — Telegram 通知工具

提供统一的 Telegram 消息发送功能，所有技能共享使用。
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from skills.shared.logger import get_logger

logger = get_logger(__name__)


def send_telegram(
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    timeout: int = 10
) -> bool:
    """
    发送 Telegram 消息

    Args:
        text: 消息内容
        bot_token: Bot Token，默认从 TG_BOT_TOKEN 环境变量读取
        chat_id: Chat ID，默认从 TG_CHAT_ID 环境变量读取
        parse_mode: 解析模式，HTML 或 Markdown
        timeout: 超时秒数

    Returns:
        是否发送成功
    """
    token = bot_token or os.environ.get("TG_BOT_TOKEN", "")
    cid = chat_id or os.environ.get("TG_CHAT_ID", "")

    if not token or not cid:
        logger.error("TG_BOT_TOKEN or TG_CHAT_ID not set")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            return result.get("ok", False)
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error {e.code}: {e.read().decode()}")
        return False
    except urllib.error.URLError as e:
        logger.error(f"URL error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Failed to send: {e}")
        return False


def send_telegram_safe(text: str, **kwargs) -> None:
    """安全的发送版本，忽略所有错误"""
    try:
        send_telegram(text, **kwargs)
    except Exception:
        pass
