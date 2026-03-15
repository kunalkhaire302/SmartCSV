"""
LLM usage tracking and quota enforcement.
"""

from __future__ import annotations

from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "llm_usage"


def record_usage(user_id: str, tokens_used: int, model: str = "claude-sonnet-4-5") -> None:
    """Record an AI summary usage event."""
    try:
        connection.insert(TABLE, {
            "user_id": user_id,
            "model": model,
            "tokens_used": tokens_used,
            "purpose": "summary",
        })
    except Exception as exc:
        logger.warning("Failed to record LLM usage: %s", exc)


def get_monthly_count(user_id: str) -> int:
    """Return the number of AI summaries used this month."""
    try:
        rows = connection.select(
            "monthly_ai_usage",
            filters={"user_id": f"eq.{user_id}"},
            limit=1,
        )
        if rows:
            return rows[0].get("summaries_this_month", 0)
    except Exception as exc:
        logger.warning("Failed to check LLM usage: %s", exc)
    return 0
