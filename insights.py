"""
Insight Engine – Statistical analysis, chart decision logic, and NLG summaries.

Generates descriptive statistics, correlation matrices, distribution analysis,
frequency tables, auto-selects chart types, and produces natural language
insights from cleaned data.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

import config
from utils.logger import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Column classification
# ═══════════════════════════════════════════════════════════════════════

def classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Classify columns into numeric, categorical, and datetime groups.

    Args:
        df: Input DataFrame.

    Returns:
        Dict with keys ``numeric``, ``categorical``, ``datetime``.
    """
    result: dict[str, list[str]] = {"numeric": [], "categorical": [], "datetime": []}
    for col in df.columns:
        if col.startswith("is_outlier_"):
            continue
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            result["datetime"].append(col)
        elif pd.api.types.is_numeric_dtype(df[col]):
            result["numeric"].append(col)
        else:
            result["categorical"].append(col)
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Descriptive statistics
# ═══════════════════════════════════════════════════════════════════════

def descriptive_stats(df: pd.DataFrame, numeric_cols: list[str]) -> list[dict[str, Any]]:
    """Compute descriptive statistics for numeric columns.

    Args:
        df: Input DataFrame.
        numeric_cols: List of numeric column names.

    Returns:
        List of stat dictionaries, one per column.
    """
    results: list[dict[str, Any]] = []
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        results.append({
            "column": col,
            "count": int(series.count()),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "std": round(float(series.std()), 4),
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
            "skewness": round(float(series.skew()), 4),
            "kurtosis": round(float(series.kurtosis()), 4),
            "missing_pct": round(float(df[col].isna().sum() / len(df) * 100), 2),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Correlation matrix
# ═══════════════════════════════════════════════════════════════════════

def correlation_matrix(df: pd.DataFrame, numeric_cols: list[str]) -> dict[str, Any]:
    """Compute Pearson correlation with p-values for numeric columns.

    Args:
        df: Input DataFrame.
        numeric_cols: List of numeric column names.

    Returns:
        Dict with ``matrix`` (nested dict) and ``significant_pairs`` list.
    """
    if len(numeric_cols) < 2:
        return {"matrix": {}, "significant_pairs": []}

    subset = df[numeric_cols].dropna()
    corr = subset.corr().round(4)
    matrix = corr.to_dict()

    significant: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, c1 in enumerate(numeric_cols):
        for c2 in numeric_cols[i + 1:]:
            if (c1, c2) in seen:
                continue
            seen.add((c1, c2))
            try:
                r, p = scipy_stats.pearsonr(subset[c1], subset[c2])
                if p < config.CORRELATION_SIGNIFICANCE:
                    significant.append({
                        "col1": c1,
                        "col2": c2,
                        "correlation": round(float(r), 4),
                        "p_value": round(float(p), 6),
                    })
            except Exception:
                continue

    significant.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return {"matrix": matrix, "significant_pairs": significant}


# ═══════════════════════════════════════════════════════════════════════
#  Distribution analysis (Freedman-Diaconis binning)
# ═══════════════════════════════════════════════════════════════════════

def distribution_analysis(
    df: pd.DataFrame, numeric_cols: list[str],
) -> list[dict[str, Any]]:
    """Compute histogram bins using Freedman-Diaconis rule.

    Args:
        df: Input DataFrame.
        numeric_cols: Numeric column names.

    Returns:
        List of dicts with ``column``, ``bins``, ``counts``.
    """
    results: list[dict[str, Any]] = []
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty or len(series) < 2:
            continue
        try:
            iqr = float(series.quantile(0.75) - series.quantile(0.25))
            n = len(series)
            if iqr > 0:
                bin_width = 2 * iqr * (n ** (-1 / 3))
                n_bins = max(1, int(math.ceil((series.max() - series.min()) / bin_width)))
            else:
                n_bins = max(1, int(math.sqrt(n)))
            n_bins = min(n_bins, 50)  # cap for UI
            counts, edges = np.histogram(series, bins=n_bins)
            labels = [f"{edges[i]:.2f}-{edges[i+1]:.2f}" for i in range(len(counts))]
            results.append({
                "column": col,
                "bins": labels,
                "counts": counts.tolist(),
                "n_bins": n_bins,
            })
        except Exception as exc:
            logger.warning("Distribution analysis failed for %s: %s", col, exc)
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Frequency tables
# ═══════════════════════════════════════════════════════════════════════

def frequency_tables(
    df: pd.DataFrame, categorical_cols: list[str],
) -> list[dict[str, Any]]:
    """Top-N value counts for categorical columns.

    Args:
        df: Input DataFrame.
        categorical_cols: Categorical column names.

    Returns:
        List of dicts with ``column``, ``values``, ``counts``, ``percentages``.
    """
    results: list[dict[str, Any]] = []
    for col in categorical_cols:
        vc = df[col].value_counts().head(config.TOP_N_CATEGORIES)
        total = int(df[col].notna().sum())
        results.append({
            "column": col,
            "values": vc.index.tolist(),
            "counts": vc.values.tolist(),
            "percentages": [round(c / total * 100, 1) if total else 0 for c in vc.values],
            "unique_count": int(df[col].nunique()),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
#  Chart decision engine
# ═══════════════════════════════════════════════════════════════════════

def _build_chart_config(
    chart_type: str,
    title: str,
    labels: list,
    datasets: list[dict],
    extra: dict | None = None,
) -> dict[str, Any]:
    """Build a Chart.js-compatible configuration dict."""
    cfg: dict[str, Any] = {
        "chart_type": chart_type,
        "title": title,
        "data": {"labels": labels, "datasets": datasets},
    }
    if extra:
        cfg.update(extra)
    return cfg


def auto_select_charts(
    df: pd.DataFrame,
    col_types: dict[str, list[str]],
    corr_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate chart configurations based on column types and data patterns.

    Args:
        df: Cleaned DataFrame.
        col_types: Output of :func:`classify_columns`.
        corr_data: Output of :func:`correlation_matrix`.

    Returns:
        List of Chart.js-compatible config dicts.
    """
    charts: list[dict[str, Any]] = []
    numeric = col_types["numeric"]
    categorical = col_types["categorical"]
    datetime_cols = col_types["datetime"]

    palette = [
        "rgba(99, 102, 241, 0.8)",
        "rgba(236, 72, 153, 0.8)",
        "rgba(34, 197, 94, 0.8)",
        "rgba(245, 158, 11, 0.8)",
        "rgba(14, 165, 233, 0.8)",
        "rgba(168, 85, 247, 0.8)",
        "rgba(239, 68, 68, 0.8)",
        "rgba(20, 184, 166, 0.8)",
    ]

    # ── Time series: datetime + numeric → line chart
    for dt_col in datetime_cols:
        for num_col in numeric[:3]:
            sorted_df = df[[dt_col, num_col]].dropna().sort_values(dt_col)
            if len(sorted_df) < 2:
                continue
            labels = sorted_df[dt_col].dt.strftime("%Y-%m-%d").tolist()
            # Subsample if too many points
            if len(labels) > 200:
                step = len(labels) // 200
                labels = labels[::step]
                values = sorted_df[num_col].tolist()[::step]
            else:
                values = sorted_df[num_col].tolist()
            # Convert numpy types to native Python
            values = [float(v) if not (isinstance(v, float) and math.isnan(v)) else 0 for v in values]
            charts.append(_build_chart_config(
                "line",
                f"{num_col} over time",
                labels,
                [{"label": num_col, "data": values, "borderColor": palette[0],
                  "backgroundColor": palette[0].replace("0.8", "0.1"),
                  "fill": True, "tension": 0.3}],
            ))

    # ── Categorical + numeric → bar chart
    for cat_col in categorical[:3]:
        for num_col in numeric[:2]:
            grouped = df.groupby(cat_col)[num_col].mean().nlargest(config.TOP_N_CATEGORIES)
            if grouped.empty:
                continue
            charts.append(_build_chart_config(
                "bar",
                f"Average {num_col} by {cat_col}",
                [str(v) for v in grouped.index.tolist()],
                [{"label": f"Avg {num_col}", "data": [round(float(v), 2) for v in grouped.values],
                  "backgroundColor": palette[:len(grouped)]}],
            ))

    # ── Single categorical → pie / donut
    for cat_col in categorical[:3]:
        vc = df[cat_col].value_counts().head(config.MAX_PIE_CATEGORIES)
        if vc.empty:
            continue
        chart_type = "pie" if len(vc) <= config.MAX_PIE_CATEGORIES else "bar"
        charts.append(_build_chart_config(
            chart_type if chart_type == "pie" else "bar",
            f"Distribution of {cat_col}",
            [str(v) for v in vc.index.tolist()],
            [{"label": cat_col, "data": vc.values.tolist(),
              "backgroundColor": palette[:len(vc)]}],
        ))

    # ── Single numeric → histogram (use distribution data)
    for num_col in numeric[:4]:
        series = df[num_col].dropna()
        if len(series) < 2:
            continue
        counts, edges = np.histogram(series, bins=min(30, max(5, int(math.sqrt(len(series))))))
        labels = [f"{edges[i]:.1f}" for i in range(len(counts))]
        charts.append(_build_chart_config(
            "bar",
            f"Distribution of {num_col}",
            labels,
            [{"label": num_col, "data": counts.tolist(),
              "backgroundColor": palette[1]}],
        ))

    # ── Scatter: numeric vs numeric (top correlated pairs)
    if corr_data.get("significant_pairs"):
        for pair in corr_data["significant_pairs"][:3]:
            c1, c2 = pair["col1"], pair["col2"]
            subset = df[[c1, c2]].dropna()
            if len(subset) > 500:
                subset = subset.sample(500, random_state=42)
            scatter_data = [{"x": round(float(r[c1]), 4), "y": round(float(r[c2]), 4)} for _, r in subset.iterrows()]
            charts.append({
                "chart_type": "scatter",
                "title": f"{c1} vs {c2} (r={pair['correlation']:.2f})",
                "data": {
                    "datasets": [{
                        "label": f"{c1} vs {c2}",
                        "data": scatter_data,
                        "backgroundColor": palette[4],
                    }],
                },
            })

    # ── Correlation heatmap data (rendered as table in frontend)
    if len(numeric) >= 2 and corr_data.get("matrix"):
        charts.append({
            "chart_type": "heatmap",
            "title": "Correlation Matrix",
            "columns": numeric,
            "matrix": corr_data["matrix"],
        })

    return charts


# ═══════════════════════════════════════════════════════════════════════
#  NLG Summary Engine – template-based natural language insights
# ═══════════════════════════════════════════════════════════════════════

def generate_nlg_insights(
    df: pd.DataFrame,
    col_types: dict[str, list[str]],
    stats_data: list[dict[str, Any]],
    corr_data: dict[str, Any],
    freq_data: list[dict[str, Any]],
) -> list[str]:
    """Generate natural language insight sentences from data analysis.

    Args:
        df: Cleaned DataFrame.
        col_types: Column classification dict.
        stats_data: Descriptive statistics list.
        corr_data: Correlation data dict.
        freq_data: Frequency table data list.

    Returns:
        List of insight sentences.
    """
    insights: list[str] = []

    # ── Dataset overview
    n_rows, n_cols = df.shape
    insights.append(
        f"The dataset contains {n_rows:,} records across {n_cols} columns "
        f"({len(col_types['numeric'])} numeric, {len(col_types['categorical'])} categorical, "
        f"{len(col_types['datetime'])} datetime)."
    )

    # ── Numeric column extremes
    for s in stats_data:
        col = s["column"]
        insights.append(
            f"'{col}' ranges from {s['min']:,.2f} to {s['max']:,.2f} "
            f"(mean: {s['mean']:,.2f}, median: {s['median']:,.2f})."
        )
        if abs(s["skewness"]) > 1:
            direction = "right" if s["skewness"] > 0 else "left"
            insights.append(
                f"  → '{col}' is significantly skewed to the {direction} "
                f"(skewness: {s['skewness']:.2f})."
            )

    # ── Max and min across all numeric
    if stats_data:
        max_col = max(stats_data, key=lambda x: x["max"])
        insights.append(
            f"The highest value in the dataset is {max_col['max']:,.2f} "
            f"in the '{max_col['column']}' column."
        )

    # ── Strongest correlations
    sig_pairs = corr_data.get("significant_pairs", [])
    if sig_pairs:
        top = sig_pairs[0]
        strength = "strong" if abs(top["correlation"]) > 0.7 else "moderate"
        direction = "positive" if top["correlation"] > 0 else "negative"
        insights.append(
            f"The strongest correlation is a {strength} {direction} relationship "
            f"between '{top['col1']}' and '{top['col2']}' (r = {top['correlation']:.2f}, "
            f"p = {top['p_value']:.4f})."
        )

    # ── Top categories
    for freq in freq_data:
        if freq["values"] and freq["percentages"]:
            top_val = freq["values"][0]
            top_pct = freq["percentages"][0]
            insights.append(
                f"In '{freq['column']}', the most frequent value is '{top_val}' "
                f"({top_pct:.1f}% of records). There are {freq['unique_count']} unique values."
            )

    # ── Time-series trend (simple linear regression)
    for dt_col in col_types["datetime"]:
        for num_col in col_types["numeric"][:2]:
            sub = df[[dt_col, num_col]].dropna().sort_values(dt_col)
            if len(sub) < 10:
                continue
            try:
                x = np.arange(len(sub), dtype=float)
                y = sub[num_col].values.astype(float)
                slope, intercept, r_value, _, _ = scipy_stats.linregress(x, y)
                r_sq = r_value ** 2
                trend = "upward" if slope > 0 else "downward"
                insights.append(
                    f"'{num_col}' shows a {trend} trend over time "
                    f"(R² = {r_sq:.2f})."
                )
            except Exception:
                continue

    return insights


# ═══════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════

def generate_full_insights(df: pd.DataFrame) -> dict[str, Any]:
    """Run all insight analyses on a cleaned DataFrame.

    Args:
        df: Cleaned DataFrame (output of ETL pipeline).

    Returns:
        Comprehensive insights dictionary.
    """
    logger.info("Generating insights for %d rows × %d cols", len(df), len(df.columns))

    col_types = classify_columns(df)
    stats = descriptive_stats(df, col_types["numeric"])
    corr = correlation_matrix(df, col_types["numeric"])
    dist = distribution_analysis(df, col_types["numeric"])
    freq = frequency_tables(df, col_types["categorical"])
    charts = auto_select_charts(df, col_types, corr)
    nlg = generate_nlg_insights(df, col_types, stats, corr, freq)

    return {
        "column_types": col_types,
        "descriptive_stats": stats,
        "correlation": corr,
        "distributions": dist,
        "frequency_tables": freq,
        "charts": charts,
        "insights": nlg,
        "summary": {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "numeric_columns": len(col_types["numeric"]),
            "categorical_columns": len(col_types["categorical"]),
            "datetime_columns": len(col_types["datetime"]),
        },
    }
