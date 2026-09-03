"""
SmartCSV – Input Validators.

Validates uploaded CSV files for structure, size, and data quality.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


def validate_csv(df: pd.DataFrame) -> list[str]:
    """Validate a DataFrame and return warnings.

    Raises:
        ValueError: If the DataFrame is empty or exceeds hard limits.

    Returns:
        List of warning strings (non-fatal issues).
    """
    warnings_list: list[str] = []

    # ── Empty check ──────────────────────────────────────────────────
    if df.empty or len(df) == 0:
        raise ValueError("CSV is empty — no data rows found.")

    if len(df.columns) == 0:
        raise ValueError("CSV has no columns.")

    # ── Hard limits ─────────────────────────────────────────────────
    if len(df) > config.MAX_ROWS:
        raise ValueError(
            f"CSV exceeds maximum of {config.MAX_ROWS:,} rows "
            f"(found {len(df):,})."
        )

    if len(df.columns) > config.MAX_COLUMNS:
        raise ValueError(
            f"CSV exceeds maximum of {config.MAX_COLUMNS} columns "
            f"(found {len(df.columns)})."
        )

    # ── Cell length check (sample-based for performance) ────────────
    for col in df.select_dtypes(include=["object"]).columns[:20]:
        max_len = df[col].dropna().astype(str).str.len().max()
        if max_len and max_len > config.MAX_CELL_LENGTH:
            raise ValueError(
                f"Column '{col}' contains values exceeding "
                f"{config.MAX_CELL_LENGTH:,} characters."
            )

    # ── Duplicate column names ──────────────────────────────────────
    dup_cols = df.columns[df.columns.duplicated()].tolist()
    if dup_cols:
        warnings_list.append(
            f"Duplicate column names found: {', '.join(str(c) for c in dup_cols[:5])}"
        )

    # ── Duplicate rows ──────────────────────────────────────────────
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        pct = round(dup_count / len(df) * 100, 1)
        warnings_list.append(
            f"{dup_count:,} duplicate rows detected ({pct}%)."
        )

    # ── Missing values ──────────────────────────────────────────────
    missing = df.isnull().sum()
    cols_with_missing = missing[missing > 0]
    if len(cols_with_missing) > 0:
        total_missing = cols_with_missing.sum()
        total_cells = len(df) * len(df.columns)
        pct = round(total_missing / total_cells * 100, 1)
        warnings_list.append(
            f"{total_missing:,} missing values across "
            f"{len(cols_with_missing)} columns ({pct}% of all cells)."
        )

    # ── Constant columns ────────────────────────────────────────────
    constant_cols = [col for col in df.columns if df[col].nunique(dropna=True) <= 1]
    if constant_cols:
        warnings_list.append(
            f"Constant/empty columns: {', '.join(str(c) for c in constant_cols[:5])}"
        )

    return warnings_list


def validate_file_type(filename: str) -> bool:
    """Validate that the filename has an allowed extension.

    Args:
        filename: Original filename.

    Returns:
        True if the extension is allowed.
    """
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in config.ALLOWED_EXTENSIONS


def get_upload_metadata(
    df: pd.DataFrame, storage_key: str, size_bytes: int,
) -> dict[str, Any]:
    """Compute metadata for a freshly uploaded CSV.

    Args:
        df: Parsed DataFrame.
        storage_key: The storage key.
        size_bytes: File size in bytes.

    Returns:
        Dict with file metadata.
    """
    # Data type summary
    data_types = {col: str(dtype) for col, dtype in df.dtypes.items()}

    # Missing values per column
    missing = df.isnull().sum()
    missing_dict = {col: int(val) for col, val in missing.items() if val > 0}

    # Filename from key
    filename = storage_key.split("/")[-1] if "/" in storage_key else storage_key

    return {
        "filename": filename,
        "storage_key": storage_key,
        "row_count": len(df),
        "column_count": len(df.columns),
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024, 2),
        "data_types": data_types,
        "missing_values": missing_dict,
        "duplicate_rows": int(df.duplicated().sum()),
        "columns": df.columns.tolist(),
    }


def compute_data_quality_score(df: pd.DataFrame) -> dict[str, Any]:
    """Compute a data quality score (0-100) for a DataFrame.

    Scores are based on:
    - Completeness (missing values)
    - Uniqueness (duplicate rows)
    - Consistency (constant columns)

    Returns:
        Dict with ``score``, ``completeness``, ``uniqueness``, ``consistency``.
    """
    total_cells = len(df) * len(df.columns)

    # Completeness: % of non-null cells
    missing_count = int(df.isnull().sum().sum())
    completeness = round((1 - missing_count / max(total_cells, 1)) * 100, 1)

    # Uniqueness: % of non-duplicate rows
    dup_count = int(df.duplicated().sum())
    uniqueness = round((1 - dup_count / max(len(df), 1)) * 100, 1)

    # Consistency: % of non-constant columns
    constant_cols = sum(1 for col in df.columns if df[col].nunique(dropna=True) <= 1)
    consistency = round((1 - constant_cols / max(len(df.columns), 1)) * 100, 1)

    # Weighted average
    score = round(completeness * 0.4 + uniqueness * 0.35 + consistency * 0.25, 1)

    return {
        "score": score,
        "completeness": completeness,
        "uniqueness": uniqueness,
        "consistency": consistency,
        "missing_cells": missing_count,
        "duplicate_rows": dup_count,
        "constant_columns": constant_cols,
        "total_cells": total_cells,
    }
