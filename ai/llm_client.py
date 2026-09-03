"""
LLM client – Gemini API integration for AI-powered data summaries.

Uses the Google GenAI SDK with gemini-2.5-flash. Falls back to template-based
summaries when the API key is missing or the user exceeds their quota.
Includes quota checking and usage recording.
"""

from __future__ import annotations

import json
from typing import Any

import config
from utils.logger import get_logger

logger = get_logger(__name__)

MODEL = "gemini-2.5-flash"


def _get_client():
    """Lazy-import and return Gemini client."""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai SDK is required for AI summaries. "
            "Install: pip install google-genai"
        )
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generate_ai_summary(
    stats_data: list[dict],
    corr_data: dict,
    freq_data: list[dict],
    summary_info: dict,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Generate an AI-powered data summary using Gemini.

    Args:
        stats_data: Descriptive statistics.
        corr_data: Correlation analysis results.
        freq_data: Frequency table data.
        summary_info: Dataset summary (rows, cols, types).
        user_id: Optional user ID for quota checking and usage recording.

    Returns:
        Dict with ``insights`` (list[str]), ``ai_generated`` (bool),
        ``tokens_used`` (int).

    Raises:
        ValueError: If quota exceeded.
        Exception: On API failure.
    """
    # ── Quota check ───────────────────────────────────────────────
    if user_id:
        from utils.quotas import check_ai_quota
        from db.users import get_user_plan

        plan = get_user_plan(user_id)
        quota = check_ai_quota(user_id, plan)
        if not quota["allowed"]:
            raise ValueError(
                f"AI request quota exceeded. "
                f"Used {quota['used']}/{quota['limit']} this month."
            )

    # Build a concise data context for the LLM
    context = {
        "dataset": summary_info,
        "statistics": stats_data[:8],  # top 8 columns to save tokens
        "top_correlations": corr_data.get("significant_pairs", [])[:5],
        "categories": [
            {
                "column": f["column"],
                "top_value": f["values"][0] if f["values"] else None,
                "unique_count": f["unique_count"],
            }
            for f in freq_data[:5]
        ],
    }

    prompt = f"""You are a data analyst. Analyze this CSV dataset and provide exactly 5-8 concise, actionable insights.

Dataset context (JSON):
{json.dumps(context, indent=2, default=str)}

Rules:
1. Each insight should be 1-2 sentences max
2. Focus on: trends, outliers, correlations, distributions, business implications
3. Be specific with numbers — cite actual values
4. Avoid generic statements like "the data is interesting"
5. Return ONLY a JSON array of strings, no other text

Example output:
["Revenue shows strong positive correlation with quantity (r=0.85), suggesting volume-driven pricing.", "The median salary ($52,000) is 15% below the mean ($61,000), indicating right-skewed distribution with high earners pulling the average up."]"""

    client = _get_client()
    from google.genai import types
    
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=config.MAX_AI_OUTPUT_TOKENS,
        )
    )

    # Extract text and parse JSON
    raw_text = response.text.strip()
    
    tokens_used = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens_used = (getattr(response.usage_metadata, "prompt_token_count", 0) or 0) + \
                      (getattr(response.usage_metadata, "candidates_token_count", 0) or 0)

    # Parse the JSON array from the response
    try:
        # Handle cases where Claude wraps in markdown code blocks
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        insights = json.loads(raw_text)
        if not isinstance(insights, list):
            insights = [str(insights)]
    except json.JSONDecodeError:
        # Fallback: split by newlines
        insights = [line.strip("- •").strip() for line in raw_text.split("\n") if line.strip()]

    # ── Record usage ──────────────────────────────────────────────
    if user_id:
        try:
            from db.llm_usage import record_usage
            record_usage(user_id, tokens_used, purpose="summary")
        except Exception as exc:
            logger.warning("Failed to record LLM usage: %s", exc)

    logger.info("AI summary generated: %d insights, %d tokens", len(insights), tokens_used)

    return {
        "insights": insights,
        "ai_generated": True,
        "tokens_used": tokens_used,
    }


def is_available() -> bool:
    """Check if the AI summary service is configured."""
    return bool(config.GEMINI_API_KEY)
