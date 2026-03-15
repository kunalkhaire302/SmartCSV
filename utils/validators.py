"""
CSV and data quality validators.
"""

from __future__ import annotations

import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


def validate_csv(df: pd.DataFrame) -> list[str]:
    """Run data-quality checks on a loaded DataFrame.

    Args:
        df: DataFrame to validate.

    Returns:
        List of warning/info messages (empty if clean).

    Raises:
        ValueError: If the data is empty or fatally malformed.
    """
    warnings: list[str] = []

    if df.empty:
        raise ValueError("CSV file is empty – zero rows loaded.")

    if len(df.columns) == 0:
        raise ValueError("CSV file has no columns.")

    # Check for entirely null columns
    null_cols = [c for c in df.columns if df[c].isna().all()]
    if null_cols:
        warnings.append(f"Entirely null columns detected: {null_cols}")

    # Check for single-column CSVs (possible delimiter issue)
    if len(df.columns) == 1:
        warnings.append(
            "Only one column detected – the file may use a non-standard "
            "delimiter."
        )

    # Check for excessive duplicates
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        pct = dup_count / len(df) * 100
        warnings.append(f"{dup_count} duplicate rows ({pct:.1f}%) found.")

    for w in warnings:
        logger.warning("Validation: %s", w)

    return warnings


def get_upload_metadata(
    df: pd.DataFrame, storage_key: str, size_bytes: int,
) -> dict:
    """Build metadata dict for an uploaded file.

    Args:
        df: Loaded DataFrame.
        storage_key: Storage key (e.g. ``uploads/data.csv``).
        size_bytes: Size of the raw file in bytes.

    Returns:
        Metadata dictionary.
    """
    filename = storage_key.split("/")[-1]
    return {
        "filename": filename,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_values": {col: int(df[col].isna().sum()) for col in df.columns},
        "duplicate_rows": int(df.duplicated().sum()),
        "size_kb": round(size_bytes / 1024, 1),
    }
