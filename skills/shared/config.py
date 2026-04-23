#!/usr/bin/env python3
"""Compatibility config layer backed by OECK runtime resolvers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oeck.runtime_core.config import load_kit_config
from oeck.runtime_core.workspace import WorkspaceResolver


def _build_runtime() -> tuple:
    config = load_kit_config(os.environ.get("OECK_WORKSPACE") or os.environ.get("OPENCLAW_WORKSPACE"))
    resolver = WorkspaceResolver(config)
    resolver.ensure_runtime_dirs()
    return config, resolver


KIT_CONFIG, RESOLVER = _build_runtime()

# 基础路径
OPENCLAW_HOME = RESOLVER.layout.host_home
WORKSPACE = RESOLVER.layout.workspace_root
MEMORY_DIR = RESOLVER.lancedb_dir().parent
LANCE_DB_PATH = RESOLVER.lancedb_dir()
LEARNINGS_DIR = RESOLVER.learnings_file().parent
LEARNINGS_FILE = RESOLVER.learnings_file()
PENDING_FILE = RESOLVER.pending_file()
SESSIONS_DIR = KIT_CONFIG.session_dir or RESOLVER.layout.legacy_sessions_dir
RECOVERY_DIR = RESOLVER.recovery_state_dir()
BACKUP_DIR = LANCE_DB_PATH / "backups"
SKILLS_DIR = RESOLVER.layout.skills_dir

# LanceDB 配置
LANCE_DB_TABLE = "memories"

# 记忆压缩配置
IMPORTANCE_MIN = 0.3
MAX_AGE_DAYS = 14
SIMILARITY_THRESHOLD = 0.85
IMPORTANCE_THRESHOLD = 0.3
MAX_BACKUPS = 4
BACKUP_PREFIX = "backups"
COMPACT_THRESHOLD = 0.80
CONTEXT_WINDOW = 200000

# 熔断配置
MAX_FAILURES = 3
CIRCUIT_TRIP_DURATION = 3600
CIRCUIT_STATE_FILE = "circuit_state.json"
RETRY_DELAYS = [0, 300, 1800]

# 反射/学习配置
MAX_MEMORIES = 30
CATEGORY = "reflection"
REFLECTION_IMPORTANCE = 0.9
TOOL_FAILURE_IMPORTANCE = 0.92
RULE_IMPORTANCE_MIN = 0.75
RULE_MAX_AGE_DAYS = 30
RULE_SIMILARITY_THRESHOLD = 0.85

# 行为分析配置
HEALTH_WARNING_THRESHOLD = 80
HEALTH_CRITICAL_THRESHOLD = 50
HEALTH_EMERGENCY_THRESHOLD = 20

# 权限评分配置
PERMISSION_WEIGHTS = {
    "operation": 0.40,
    "path": 0.30,
    "context": 0.20,
    "pattern": 0.10,
}
RISK_LEVEL_THRESHOLDS = {"low": 30, "medium": 70}

# API / 外部服务配置
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
SILICONFLOW_EMBED_MODEL = "BAAI/bge-m3"
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_EMBED_URL = "https://api.minimaxi.com/v1/embeddings"
MINIMAX_EMBED_MODEL = "minimax-embedding"
MINIMAX_CHAT_URL = "https://api.minimaxi.com/v1/chat/completions"
MINIMAX_CHAT_MODEL = "MiniMax-M2"
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# 日志配置
LOG_LEVEL = os.environ.get("OPENCLAW_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_config() -> Dict[str, Any]:
    return CONFIG.copy()


def reload_config() -> None:
    global KIT_CONFIG, RESOLVER
    global OPENCLAW_HOME, WORKSPACE, MEMORY_DIR, LANCE_DB_PATH, LEARNINGS_DIR
    global LEARNINGS_FILE, PENDING_FILE, SESSIONS_DIR, RECOVERY_DIR, BACKUP_DIR, SKILLS_DIR
    global SILICONFLOW_API_KEY, MINIMAX_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID, LOG_LEVEL, CONFIG

    KIT_CONFIG, RESOLVER = _build_runtime()
    OPENCLAW_HOME = RESOLVER.layout.host_home
    WORKSPACE = RESOLVER.layout.workspace_root
    MEMORY_DIR = RESOLVER.lancedb_dir().parent
    LANCE_DB_PATH = RESOLVER.lancedb_dir()
    LEARNINGS_DIR = RESOLVER.learnings_file().parent
    LEARNINGS_FILE = RESOLVER.learnings_file()
    PENDING_FILE = RESOLVER.pending_file()
    SESSIONS_DIR = KIT_CONFIG.session_dir or RESOLVER.layout.legacy_sessions_dir
    RECOVERY_DIR = RESOLVER.recovery_state_dir()
    BACKUP_DIR = LANCE_DB_PATH / "backups"
    SKILLS_DIR = RESOLVER.layout.skills_dir

    SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
    MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
    TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
    TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
    LOG_LEVEL = os.environ.get("OPENCLAW_LOG_LEVEL", "INFO").upper()
    CONFIG = _build_config()


def _build_config() -> Dict[str, Any]:
    return {
        "openclaw_home": str(OPENCLAW_HOME),
        "workspace": str(WORKSPACE),
        "memory_dir": str(MEMORY_DIR),
        "lance_db_path": str(LANCE_DB_PATH),
        "learnings_dir": str(LEARNINGS_DIR),
        "learnings_file": str(LEARNINGS_FILE),
        "sessions_dir": str(SESSIONS_DIR),
        "recovery_dir": str(RECOVERY_DIR),
        "backup_dir": str(BACKUP_DIR),
        "state_dir": str(RESOLVER.layout.state_dir),
        "checks_dir": str(RESOLVER.layout.checks_dir),
        "distribution_dir": str(RESOLVER.layout.distribution_dir),
        "importance_min": IMPORTANCE_MIN,
        "importance_threshold": IMPORTANCE_THRESHOLD,
        "max_age_days": MAX_AGE_DAYS,
        "max_memories": MAX_MEMORIES,
        "max_backups": MAX_BACKUPS,
        "compact_threshold": COMPACT_THRESHOLD,
        "context_window": CONTEXT_WINDOW,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "rule_similarity_threshold": RULE_SIMILARITY_THRESHOLD,
        "siliconflow_api_available": bool(SILICONFLOW_API_KEY),
        "minimax_api_available": bool(MINIMAX_API_KEY),
        "telegram_configured": bool(TG_BOT_TOKEN and TG_CHAT_ID),
        "feature_flags": KIT_CONFIG.feature_flags,
        "adapter_flags": KIT_CONFIG.adapter_flags,
    }


CONFIG = _build_config()
