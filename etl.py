"""
ETL Pipeline – Extract, Transform, Load for CSV data.

Performs ordered transformation steps: column standardisation, deduplication,
missing-value imputation, date conversion, outlier detection (IQR), dtype
optimisation, feature engineering, and final validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


class ETLPipeline:
    """Stateful ETL pipeline that records every transformation applied.

    Attributes:
        df: Working DataFrame.
        original_memory: Memory usage of the input DataFrame in bytes.
        transformations: List of transformation descriptions applied.
        outlier_counts: Per-column count of detected outliers.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df: pd.DataFrame = df.copy()
        self.original_memory: float = df.memory_usage(deep=True).sum()
        self.transformations: list[str] = []
        self.outlier_counts: dict[str, int] = {}

    # ──────────────────── Step 1: Column name standardisation ──────────
    def standardize_columns(self) -> None:
        """Lowercase, replace spaces/special chars with underscores."""
        rename_map: dict[str, str] = {}
        for col in self.df.columns:
            new = col.strip().lower()
            new = re.sub(r"[^a-z0-9_]", "_", new)
            new = re.sub(r"_+", "_", new).strip("_")
            if new != col:
                rename_map[col] = new
        if rename_map:
            self.df.rename(columns=rename_map, inplace=True)
            self.transformations.append(
                f"standardized_column_names ({len(rename_map)} renamed)"
            )
            logger.info("Renamed columns: %s", rename_map)

    # ──────────────────── Step 2: Trim string fields ──────────────────
    def trim_strings(self) -> None:
        """Strip leading/trailing whitespace from object columns."""
        obj_cols = self.df.select_dtypes(include=["object"]).columns.tolist()
        for col in obj_cols:
            self.df[col] = self.df[col].astype(str).str.strip()
            # Restore NaN where it was 'nan' string
            self.df[col] = self.df[col].replace({"nan": np.nan, "None": np.nan, "": np.nan})
        if obj_cols:
            self.transformations.append(
                f"trimmed_string_fields ({len(obj_cols)} columns)"
            )

    # ──────────────────── Step 3: Remove duplicates ───────────────────
    def remove_duplicates(self) -> None:
        """Drop duplicate rows, keep first occurrence."""
        before = len(self.df)
        self.df.drop_duplicates(inplace=True)
        self.df.reset_index(drop=True, inplace=True)
        removed = before - len(self.df)
        if removed > 0:
            self.transformations.append(f"removed_duplicates ({removed} rows)")
            logger.info("Removed %d duplicate rows", removed)

    # ──────────────────── Step 4: Handle missing values ───────────────
    def handle_missing_values(self) -> None:
        """Impute missing values based on column dtype and skewness."""
        for col in self.df.columns:
            missing = int(self.df[col].isna().sum())
            if missing == 0:
                continue

            dtype = self.df[col].dtype

            if pd.api.types.is_numeric_dtype(dtype):
                skew_val = self.df[col].skew()
                if abs(skew_val) > config.SKEWNESS_THRESHOLD:
                    fill = self.df[col].median()
                    strategy = "median (skewed)"
                else:
                    fill = self.df[col].mean()
                    strategy = "mean"
                self.df[col].fillna(fill, inplace=True)
                self.transformations.append(
                    f"filled_missing_{col}_with_{strategy} ({missing} values)"
                )

            elif pd.api.types.is_datetime64_any_dtype(dtype):
                pct_missing = missing / len(self.df) * 100
                if pct_missing < config.DATETIME_MISSING_DROP_PCT:
                    self.df.dropna(subset=[col], inplace=True)
                    self.df.reset_index(drop=True, inplace=True)
                    self.transformations.append(
                        f"dropped_missing_datetime_{col} ({missing} rows, {pct_missing:.1f}%)"
                    )
                else:
                    self.df[col].ffill(inplace=True)
                    self.transformations.append(
                        f"forward_filled_datetime_{col} ({missing} values)"
                    )

            else:  # categorical / object / bool
                mode_val = self.df[col].mode()
                if not mode_val.empty:
                    self.df[col].fillna(mode_val.iloc[0], inplace=True)
                    self.transformations.append(
                        f"filled_missing_{col}_with_mode ({missing} values)"
                    )

    # ──────────────────── Step 5: Convert date-like columns ───────────
    def convert_dates(self) -> None:
        """Attempt to convert object columns that look like dates."""
        obj_cols = self.df.select_dtypes(include=["object"]).columns.tolist()
        converted: list[str] = []
        for col in obj_cols:
            sample = self.df[col].dropna().head(50)
            if sample.empty:
                continue
            try:
                parsed = pd.to_datetime(sample, errors="coerce", infer_datetime_format=True)
                ratio = parsed.notna().sum() / len(sample)
                if ratio > 0.6:
                    self.df[col] = pd.to_datetime(self.df[col], errors="coerce", infer_datetime_format=True)
                    converted.append(col)
            except Exception:
                continue
        if converted:
            self.transformations.append(
                f"converted_to_datetime ({', '.join(converted)})"
            )
            logger.info("Date columns converted: %s", converted)

    # ──────────────────── Step 6: Outlier detection (IQR) ─────────────
    def detect_outliers(self) -> None:
        """Flag outliers using Inter-Quartile Range method."""
        num_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()
        for col in num_cols:
            q1 = self.df[col].quantile(0.25)
            q3 = self.df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - config.IQR_MULTIPLIER * iqr
            upper = q3 + config.IQR_MULTIPLIER * iqr
            outlier_mask = (self.df[col] < lower) | (self.df[col] > upper)
            count = int(outlier_mask.sum())
            if count > 0:
                self.df[f"is_outlier_{col}"] = outlier_mask.astype(int)
                self.outlier_counts[col] = count
        if self.outlier_counts:
            self.transformations.append(
                f"detected_outliers ({sum(self.outlier_counts.values())} total across {len(self.outlier_counts)} columns)"
            )

    # ──────────────────── Step 7: Dtype optimisation ──────────────────
    def optimize_dtypes(self) -> None:
        """Downcast numeric columns to reduce memory."""
        for col in self.df.select_dtypes(include=["int64", "int32"]).columns:
            self.df[col] = pd.to_numeric(self.df[col], downcast="integer")
        for col in self.df.select_dtypes(include=["float64"]).columns:
            if not col.startswith("is_outlier_"):
                self.df[col] = pd.to_numeric(self.df[col], downcast="float")
        self.transformations.append("optimized_dtypes")

    # ──────────────────── Step 8: Feature engineering ─────────────────
    def feature_engineering(self) -> None:
        """Extract date parts and create computed columns where logical."""
        dt_cols = self.df.select_dtypes(include=["datetime64"]).columns.tolist()
        for col in dt_cols:
            self.df[f"{col}_year"] = self.df[col].dt.year
            self.df[f"{col}_month"] = self.df[col].dt.month
            self.df[f"{col}_day"] = self.df[col].dt.day
            self.transformations.append(f"extracted_date_parts_from_{col}")

        cols_lower = {c.lower(): c for c in self.df.columns}
        price_col = cols_lower.get("price") or cols_lower.get("total_price")
        qty_col = cols_lower.get("quantity") or cols_lower.get("qty")
        if price_col and qty_col:
            if pd.api.types.is_numeric_dtype(self.df[price_col]) and pd.api.types.is_numeric_dtype(self.df[qty_col]):
                mask = self.df[qty_col] != 0
                self.df.loc[mask, "price_per_unit"] = (
                    self.df.loc[mask, price_col] / self.df.loc[mask, qty_col]
                )
                self.transformations.append("created_price_per_unit")

    # ──────────────────── Step 9: Final validation ────────────────────
    def validate_output(self) -> None:
        """Ensure no all-null columns or infinite values remain."""
        # Replace infinities
        inf_count = int(np.isinf(self.df.select_dtypes(include=[np.number])).sum().sum())
        if inf_count > 0:
            self.df.replace([np.inf, -np.inf], np.nan, inplace=True)
            self.transformations.append(f"replaced_infinities ({inf_count})")

        # Drop columns that became entirely null
        null_cols = [c for c in self.df.columns if self.df[c].isna().all()]
        if null_cols:
            self.df.drop(columns=null_cols, inplace=True)
            self.transformations.append(f"dropped_all_null_columns ({', '.join(null_cols)})")

    # ──────────────────── Run full pipeline ────────────────────────────
    def run(self) -> pd.DataFrame:
        """Execute all ETL steps in order and return the cleaned DataFrame.

        Returns:
            Cleaned DataFrame.
        """
        logger.info("Starting ETL pipeline (%d rows × %d cols)", len(self.df), len(self.df.columns))
        self.standardize_columns()
        self.trim_strings()
        self.remove_duplicates()
        self.handle_missing_values()
        self.convert_dates()
        self.detect_outliers()
        self.optimize_dtypes()
        self.feature_engineering()
        self.validate_output()
        logger.info("ETL complete – %d transformations applied", len(self.transformations))
        return self.df

    def get_summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the pipeline run.

        Returns:
            Summary dictionary.
        """
        final_memory = self.df.memory_usage(deep=True).sum()
        return {
            "transformations_applied": self.transformations,
            "outliers_detected": self.outlier_counts,
            "rows_after": len(self.df),
            "columns_after": len(self.df.columns),
            "memory_reduction_mb": round(
                (self.original_memory - final_memory) / (1024 * 1024), 2
            ),
        }


def run_etl(input_path: Path) -> tuple[pd.DataFrame, dict[str, Any], Path]:
    """High-level function: load CSV, run ETL, save result.

    Args:
        input_path: Path to the original uploaded CSV.

    Returns:
        Tuple of (cleaned DataFrame, summary dict, output file path).
    """
    from utils.file_handler import load_csv

    df = load_csv(input_path)
    pipeline = ETLPipeline(df)
    cleaned = pipeline.run()

    output_name = f"cleaned_{input_path.name}"
    output_path = config.PROCESSED_FOLDER / output_name
    cleaned.to_csv(str(output_path), index=False)
    logger.info("Saved cleaned CSV to %s", output_path)

    summary = pipeline.get_summary()
    summary["processed_file"] = output_name
    return cleaned, summary, output_path
