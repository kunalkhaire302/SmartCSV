"""
SmartCSV – Statistical Insights & Chart Engine.

Generates descriptive statistics, correlations with real p-values,
frequency tables, and auto-selected chart configurations for Chart.js.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  P-Value Calculation (no scipy dependency)
# ═══════════════════════════════════════════════════════════════════════

def _t_cdf(t_val: float, df: int) -> float:
    """Approximate the CDF of Student's t-distribution.

    Uses the regularized incomplete beta function approximation.
    Accurate for df >= 1. For large df (>100), uses normal approximation.

    Args:
        t_val: t-statistic value.
        df: degrees of freedom.

    Returns:
        CDF value (probability that T <= t_val).
    """
    if df <= 0:
        return 0.5

    # For large df, use normal approximation
    if df > 100:
        return _normal_cdf(t_val)

    x = df / (df + t_val * t_val)
    # Use the relationship: P(T <= t) = 1 - 0.5 * I_x(df/2, 0.5) for t > 0
    beta_val = _regularized_beta(x, df / 2.0, 0.5)

    if t_val >= 0:
        return 1.0 - 0.5 * beta_val
    else:
        return 0.5 * beta_val


def _normal_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _regularized_beta(x: float, a: float, b: float, max_iter: int = 200) -> float:
    """Regularized incomplete beta function I_x(a, b).

    Uses the continued fraction representation.
    """
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    # Use the continued fraction for better convergence
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta) / a

    # Lentz's algorithm for continued fraction
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d

    for m in range(1, max_iter + 1):
        # Even step
        numerator = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= d * c

        # Odd step
        numerator = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        delta = d * c
        f *= delta

        if abs(delta - 1.0) < 1e-10:
            break

    return front * f


def pearson_p_value(r: float, n: int) -> float:
    """Calculate a two-tailed p-value for a Pearson correlation.

    Uses the t-distribution with n-2 degrees of freedom.

    Args:
        r: Pearson correlation coefficient.
        n: Number of observations.

    Returns:
        Two-tailed p-value, or 1.0 if computation fails.
    """
    if n <= 2:
        return 1.0

    if abs(r) >= 1.0:
        return 0.0 if abs(r) == 1.0 and n > 2 else 1.0

    try:
        df = n - 2
        t_stat = r * math.sqrt(df / (1.0 - r * r))
        # Two-tailed p-value
        cdf_val = _t_cdf(abs(t_stat), df)
        p_val = 2.0 * (1.0 - cdf_val)
        return max(0.0, min(1.0, p_val))
    except (ValueError, ZeroDivisionError, OverflowError):
        return 1.0


# ═══════════════════════════════════════════════════════════════════════
#  Gradient palette for charts
# ═══════════════════════════════════════════════════════════════════════

CHART_PALETTE = [
    "rgba(99, 102, 241, 0.7)",    # indigo
    "rgba(236, 72, 153, 0.7)",     # pink
    "rgba(34, 197, 94, 0.7)",      # green
    "rgba(245, 158, 11, 0.7)",     # amber
    "rgba(6, 182, 212, 0.7)",      # cyan
    "rgba(139, 92, 246, 0.7)",     # violet
    "rgba(239, 68, 68, 0.7)",      # red
    "rgba(20, 184, 166, 0.7)",     # teal
    "rgba(251, 146, 60, 0.7)",     # orange
    "rgba(168, 85, 247, 0.7)",     # purple
]

CHART_PALETTE_SOLID = [c.replace("0.7", "1") for c in CHART_PALETTE]


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def generate_insights(df: pd.DataFrame) -> dict[str, Any]:
    """Generate comprehensive statistical insights for a DataFrame.

    Returns:
        Dict with ``descriptive_stats``, ``correlations``, ``frequency_tables``,
        ``insights`` (NLG summaries), and ``charts`` (Chart.js configs).
    """
    stats = _descriptive_stats(df)
    correlations = _correlation_analysis(df)
    freq_tables = _frequency_tables(df)
    insights = _generate_nlg_insights(stats, correlations, freq_tables, df)
    charts = _generate_charts(df, stats, correlations, freq_tables)

    return {
        "descriptive_stats": stats,
        "correlations": correlations,
        "frequency_tables": freq_tables,
        "insights": insights,
        "charts": charts,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Descriptive Statistics
# ═══════════════════════════════════════════════════════════════════════

def _descriptive_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute descriptive statistics for numeric columns."""
    numeric_df = df.select_dtypes(include=["number"])
    if numeric_df.empty:
        return []

    result: list[dict[str, Any]] = []
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        if len(series) == 0:
            continue

        total = len(df[col])
        missing = int(df[col].isnull().sum())

        stat = {
            "column": col,
            "count": len(series),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "std": round(float(series.std()), 4) if len(series) > 1 else 0.0,
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
            "q1": round(float(series.quantile(0.25)), 4),
            "q3": round(float(series.quantile(0.75)), 4),
            "skewness": round(float(series.skew()), 4) if len(series) > 2 else 0.0,
            "kurtosis": round(float(series.kurtosis()), 4) if len(series) > 3 else 0.0,
            "missing_pct": round(missing / total * 100, 1) if total > 0 else 0.0,
        }
        result.append(stat)

    return result


# ═══════════════════════════════════════════════════════════════════════
#  Correlation Analysis
# ═══════════════════════════════════════════════════════════════════════

def _correlation_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """Compute correlation matrix with real p-values.

    Only includes pairs with at least 5 observations and non-constant columns.
    """
    numeric_df = df.select_dtypes(include=["number"])

    # Filter out constant columns
    varying_cols = [
        col for col in numeric_df.columns
        if numeric_df[col].nunique(dropna=True) > 1
    ]

    if len(varying_cols) < 2:
        return {"matrix": {}, "significant_pairs": [], "columns": []}

    numeric_df = numeric_df[varying_cols]

    # Compute correlation matrix
    corr_matrix = numeric_df.corr()

    # Replace NaN/inf with 0
    corr_matrix = corr_matrix.fillna(0).replace([np.inf, -np.inf], 0)

    matrix_dict = {
        col: {
            row: round(float(corr_matrix.loc[row, col]), 4)
            for row in corr_matrix.index
        }
        for col in corr_matrix.columns
    }

    # Find significant pairs with real p-values
    significant: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, col_a in enumerate(varying_cols):
        for col_b in varying_cols[i + 1:]:
            pair_key = (min(col_a, col_b), max(col_a, col_b))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Count common non-null observations
            mask = numeric_df[[col_a, col_b]].dropna()
            n = len(mask)
            if n < 5:
                continue

            r = float(corr_matrix.loc[col_a, col_b])
            if not math.isfinite(r):
                continue

            p = pearson_p_value(r, n)

            if p < config.CORRELATION_P_VALUE_THRESHOLD and abs(r) > 0.1:
                significant.append({
                    "column_a": col_a,
                    "column_b": col_b,
                    "correlation": round(r, 4),
                    "p_value": round(p, 6),
                    "n_observations": n,
                    "strength": _correlation_strength(r),
                })

    # Sort by absolute correlation
    significant.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    return {
        "matrix": matrix_dict,
        "significant_pairs": significant[:20],
        "columns": varying_cols,
    }


def _correlation_strength(r: float) -> str:
    """Classify correlation strength."""
    abs_r = abs(r)
    if abs_r >= 0.8:
        return "very strong"
    elif abs_r >= 0.6:
        return "strong"
    elif abs_r >= 0.4:
        return "moderate"
    elif abs_r >= 0.2:
        return "weak"
    return "negligible"


# ═══════════════════════════════════════════════════════════════════════
#  Frequency Tables
# ═══════════════════════════════════════════════════════════════════════

def _frequency_tables(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute frequency tables for categorical and low-cardinality columns."""
    tables: list[dict[str, Any]] = []

    for col in df.columns:
        nunique = df[col].nunique(dropna=True)
        if nunique < 2 or nunique > 50:
            continue

        # Skip numeric columns with too many unique values
        if pd.api.types.is_numeric_dtype(df[col]) and nunique > 20:
            continue

        vc = df[col].value_counts().head(config.TOP_N_CATEGORIES)
        total = len(df[col].dropna())

        values = [
            {
                "value": str(idx),
                "count": int(cnt),
                "percentage": round(cnt / total * 100, 1) if total > 0 else 0,
            }
            for idx, cnt in vc.items()
        ]

        tables.append({
            "column": col,
            "unique_count": nunique,
            "values": values,
        })

    # Sort by unique count (ascending — most likely to be meaningful categories)
    tables.sort(key=lambda x: x["unique_count"])
    return tables[:10]  # Cap at 10 tables


# ═══════════════════════════════════════════════════════════════════════
#  Natural Language Insights (Template-Based)
# ═══════════════════════════════════════════════════════════════════════

def _generate_nlg_insights(
    stats: list[dict],
    corr: dict,
    freq: list[dict],
    df: pd.DataFrame,
) -> list[str]:
    """Generate natural language insights from statistical analysis.

    Template-based for reliability; AI summaries are layered on top.
    """
    insights: list[str] = []

    # Dataset overview
    insights.append(
        f"Dataset contains {len(df):,} rows and {len(df.columns)} columns "
        f"({len(df.select_dtypes(include='number').columns)} numeric, "
        f"{len(df.select_dtypes(include='object').columns)} categorical)."
    )

    # Missing data summary
    total_missing = int(df.isnull().sum().sum())
    if total_missing > 0:
        pct = round(total_missing / (len(df) * len(df.columns)) * 100, 1)
        insights.append(
            f"Found {total_missing:,} missing values ({pct}% of all cells). "
            f"Columns with most missing: "
            + ", ".join(
                f"{col} ({val})"
                for col, val in df.isnull().sum().nlargest(3).items()
                if val > 0
            )
            + "."
        )

    # Skewness insights
    for s in stats[:5]:
        if abs(s.get("skewness", 0)) > 2:
            direction = "right" if s["skewness"] > 0 else "left"
            insights.append(
                f"'{s['column']}' is heavily {direction}-skewed "
                f"(skewness = {s['skewness']:.2f}). "
                f"Median ({s['median']:,.2f}) differs significantly from mean ({s['mean']:,.2f})."
            )

    # Correlation insights (only significant ones)
    sig_pairs = corr.get("significant_pairs", [])
    for pair in sig_pairs[:3]:
        direction = "positive" if pair["correlation"] > 0 else "negative"
        insights.append(
            f"{pair['strength'].capitalize()} {direction} correlation "
            f"between '{pair['column_a']}' and '{pair['column_b']}' "
            f"(r = {pair['correlation']:.3f}, p = {pair['p_value']:.4f}, "
            f"n = {pair['n_observations']})."
        )

    # Top category insights
    for ft in freq[:2]:
        top_val = ft["values"][0] if ft["values"] else None
        if top_val:
            insights.append(
                f"Most common value in '{ft['column']}': "
                f"'{top_val['value']}' ({top_val['percentage']}%, "
                f"{top_val['count']:,} occurrences out of {ft['unique_count']} unique values)."
            )

    # Outlier-prone columns
    for s in stats:
        iqr = s.get("q3", 0) - s.get("q1", 0)
        if iqr > 0 and s.get("max", 0) > s.get("q3", 0) + 3 * iqr:
            insights.append(
                f"'{s['column']}' has extreme outliers: "
                f"max ({s['max']:,.2f}) is far beyond the IQR range "
                f"[{s['q1']:,.2f}, {s['q3']:,.2f}]."
            )

    return insights[:10]


# ═══════════════════════════════════════════════════════════════════════
#  Chart Generation
# ═══════════════════════════════════════════════════════════════════════

def _generate_charts(
    df: pd.DataFrame,
    stats: list[dict],
    corr: dict,
    freq: list[dict],
) -> list[dict[str, Any]]:
    """Generate Chart.js chart configurations.

    Uses a scoring system to select the most informative charts,
    capped at MAX_CHARTS.
    """
    candidates: list[tuple[int, dict[str, Any]]] = []

    # ── Histograms for numeric columns ─────────────────────────────
    numeric_cols = df.select_dtypes(include=["number"]).columns
    for col in numeric_cols[:6]:
        series = df[col].dropna()
        if len(series) < 5:
            continue

        # Score: higher for skewed distributions (more informative)
        skew = abs(float(series.skew())) if len(series) > 2 else 0
        score = 60 + min(skew * 10, 30)

        bins = min(30, max(10, int(len(series) ** 0.5)))
        counts, edges = np.histogram(series, bins=bins)

        labels = [f"{edges[i]:.1f}" for i in range(len(edges) - 1)]
        chart = {
            "chart_type": "bar",
            "title": f"Distribution of {col}",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": col,
                    "data": counts.tolist(),
                    "backgroundColor": CHART_PALETTE[0],
                    "borderColor": CHART_PALETTE_SOLID[0],
                    "borderWidth": 1,
                }],
            },
        }
        candidates.append((int(score), chart))

    # ── Bar charts for categorical columns ─────────────────────────
    for ft in freq[:5]:
        if len(ft["values"]) < 2:
            continue

        score = 70 if ft["unique_count"] <= config.MAX_PIE_CATEGORIES else 50

        labels = [v["value"] for v in ft["values"]]
        data_vals = [v["count"] for v in ft["values"]]
        colors = CHART_PALETTE[: len(labels)]

        chart = {
            "chart_type": "bar",
            "title": f"Frequency: {ft['column']}",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": ft["column"],
                    "data": data_vals,
                    "backgroundColor": colors,
                    "borderWidth": 0,
                }],
            },
        }
        candidates.append((score, chart))

        # Pie chart for low-cardinality
        if ft["unique_count"] <= config.MAX_PIE_CATEGORIES:
            pie = {
                "chart_type": "doughnut",
                "title": f"Proportion: {ft['column']}",
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "data": data_vals,
                        "backgroundColor": colors,
                        "borderWidth": 2,
                        "borderColor": "rgba(0,0,0,0.1)",
                    }],
                },
            }
            candidates.append((score - 10, pie))

    # ── Scatter plots for top correlations ──────────────────────────
    sig_pairs = corr.get("significant_pairs", [])
    for pair in sig_pairs[:3]:
        col_a, col_b = pair["column_a"], pair["column_b"]
        sample = df[[col_a, col_b]].dropna()
        if len(sample) > 500:
            sample = sample.sample(500, random_state=42)

        score = 80 + int(abs(pair["correlation"]) * 20)

        scatter = {
            "chart_type": "scatter",
            "title": f"{col_a} vs {col_b} (r={pair['correlation']:.3f})",
            "data": {
                "datasets": [{
                    "label": f"{col_a} vs {col_b}",
                    "data": [
                        {"x": round(float(row[col_a]), 4), "y": round(float(row[col_b]), 4)}
                        for _, row in sample.iterrows()
                    ],
                    "backgroundColor": CHART_PALETTE[4],
                    "pointRadius": 3,
                }],
            },
        }
        candidates.append((score, scatter))

    # ── Correlation heatmap ─────────────────────────────────────────
    corr_cols = corr.get("columns", [])
    corr_matrix = corr.get("matrix", {})
    if len(corr_cols) >= 2:
        heatmap = {
            "chart_type": "heatmap",
            "title": "Correlation Matrix",
            "columns": corr_cols[:15],  # Limit for readability
            "matrix": corr_matrix,
        }
        candidates.append((90, heatmap))

    # ── Select top charts by score ──────────────────────────────────
    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = [chart for _, chart in candidates[: config.MAX_CHARTS]]

    logger.info("Generated %d charts from %d candidates", len(selected), len(candidates))
    return selected
