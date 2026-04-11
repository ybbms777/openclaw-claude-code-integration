#!/usr/bin/env python3
"""
embedding.py — 统一的 Embedding 获取工具

提供统一的文本 embedding 获取功能，支持多种 Provider 和 fallback。
"""

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from typing import List, Literal, Optional

from skills.shared.logger import get_logger

logger = get_logger(__name__)


# ─── 配置 ──────────────────────────────────────────────────────────────────

SILICONFLOW_API_KEY: str = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_EMBED_URL: str = "https://api.siliconflow.cn/v1/embeddings"
SILICONFLOW_MODEL: str = "BAAI/bge-m3"

MINIMAX_API_KEY: str = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_EMBED_URL: str = "https://api.minimaxi.com/v1/embeddings"
MINIMAX_MODEL: str = "minimax-embedding"

EmbeddingModel = Literal["auto", "siliconflow", "minimax", "hash"]

# ─── Embedding 函数 ────────────────────────────────────────────────────────


def get_embedding(text: str, model: EmbeddingModel = "auto") -> Optional[List[float]]:
    """
    获取文本的 embedding（优先使用 SiliconFlow，备用 MiniMax，最后 hash fallback）

    Args:
        text: 输入文本
        model: 指定模型，"siliconflow", "minimax", "hash", 或 "auto"（默认）

    Returns:
        embedding 向量列表，或 None（仅在 API 错误时）
    """
    text = text[:2000]  # 限制长度

    # 备用方案：哈希向量
    def hash_embedding(txt: str) -> List[float]:
        h = hashlib.sha256(txt.encode("utf-8")).digest()
        vec = [0.0] * 1024
        for i in range(min(len(h), 1024)):
            vec[i] = (h[i] / 255.0) * 2 - 1
        return vec

    # 指定了 hash，直接返回
    if model == "hash":
        return hash_embedding(text)

    # 尝试 SiliconFlow
    if model in ("auto", "siliconflow") and SILICONFLOW_API_KEY:
        try:
            payload = json.dumps({
                "model": SILICONFLOW_MODEL,
                "input": text,
                "encoding_format": "float"
            }).encode("utf-8")
            req = urllib.request.Request(
                SILICONFLOW_EMBED_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                return result["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"SiliconFlow 失败，尝试下一方案: {e}")

    # 尝试 MiniMax
    if model in ("auto", "minimax") and MINIMAX_API_KEY:
        try:
            payload = json.dumps({
                "model": MINIMAX_MODEL,
                "input": text
            }).encode("utf-8")
            req = urllib.request.Request(
                MINIMAX_EMBED_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                return result["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"MiniMax 失败: {e}")

    # 最后的 fallback
    logger.info("使用 hash fallback")
    return hash_embedding(text)


def cosine_sim(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
