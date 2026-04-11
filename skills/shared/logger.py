#!/usr/bin/env python3
"""
logger.py — 统一日志工具

提供标准化的日志配置，所有技能共享使用。
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional


# 默认日志格式
DEFAULT_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# 日志级别环境变量
LOG_LEVEL: str = os.environ.get("OPENCLAW_LOG_LEVEL", "INFO").upper()


def get_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    format_str: str = DEFAULT_FORMAT,
) -> logging.Logger:
    """
    获取配置好的 logger 实例

    Args:
        name: logger 名称，通常用 __name__
        level: 日志级别，默认从 OPENCLAW_LOG_LEVEL 环境变量读取
        log_file: 可选的文件输出路径
        format_str: 日志格式字符串

    Returns:
        配置好的 Logger 实例

    Example:
        from skills.shared.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Hello, world!")
    """
    logger = logging.getLogger(name)

    # 避免重复配置
    if logger.handlers:
        return logger

    log_level = getattr(logging, level or LOG_LEVEL, logging.INFO)
    logger.setLevel(log_level)

    # 控制台处理器（stderr）
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(format_str, datefmt=DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（可选）
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(format_str, datefmt=DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


# 便捷的默认 logger 工厂
def create_logger(name: str) -> logging.Logger:
    """创建默认配置的 logger（仅输出到 stderr）"""
    return get_logger(name)


# 全局日志级别设置
def set_log_level(level: str) -> None:
    """设置所有 logger 的全局级别"""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)
