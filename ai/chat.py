"""
Chat with your CSV – RAG-style question answering.

Sends a slice of the DataFrame context + user question to Claude,
which answers based on the actual data.  No vector DB required —
uses a "context-stuffing" approach that works well for CSVs under
~50k rows.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-5-20250514"
MAX_TOKENS = 1024


def _build_data_context(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Build a compact text representation of the DataFrame for the LLM.

    Includes:
    - Column names + dtypes
    - Summary stats
    - First N rows as CSV
    """
    parts = []

    # Schema
    schema = {col: str(dtype) for col, dtype in df.dtypes.items()}
    parts.append(f"Schema ({len(df)} rows × {len(df.columns)} cols):")
    parts.append(json.dumps(schema, indent=2))

    # Summary stats for numeric columns
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        desc = df[numeric_cols].describe().round(2).to_dict()
        parts.append("\nNumeric summary:")
        parts.append(json.dumps(desc, indent=2, default=str))

    # Sample rows
    sample = df.head(max_rows)
    parts.append(f"\nFirst {len(sample)} rows (CSV):")
    parts.append(sample.to_csv(index=False))

    return "\n".join(parts)


def chat_with_csv(
    df: pd.DataFrame,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Answer a question about a DataFrame using Claude.

    Args:
        df: The CSV data as a DataFrame.
        question: User's natural-language question.
        history: Optional conversation history (list of {role, content}).

    Returns:
        Dict with ``answer`` (str), ``tokens_used`` (int).

    Raises:
        ImportError: If anthropic SDK is not installed.
        ValueError: If API key is not configured.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic SDK required. Install: pip install anthropic")

    if not config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    data_context = _build_data_context(df)

    system_prompt = f"""You are a data analyst assistant. The user has uploaded a CSV dataset. Answer their questions based ONLY on the data provided below. Be specific with numbers and cite actual values from the data.

If the user asks something not answerable from the data, say so clearly.

Keep answers concise (2-5 sentences unless a detailed breakdown is requested).

DATASET:
{data_context}"""

    messages = []
    if history:
        for msg in history[-6:]:  # Keep last 6 messages for context
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=messages,
    )

    answer = response.content[0].text.strip()
    tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

    logger.info("Chat response: %d chars, %d tokens", len(answer), tokens_used)

    return {
        "answer": answer,
        "tokens_used": tokens_used,
    }
