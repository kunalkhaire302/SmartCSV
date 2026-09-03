"""
SmartCSV – ETL Pipeline.

Automated data cleaning, type inference, and transformation pipeline.
Each transformation is logged with structured metadata for explainability.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


class ETLPipeline:
    """Automated ETL pipeline for CSV data cleaning.

    Each transformation step records structured metadata:
    ``{"operation": ..., "column": ..., "method": ..., "affected_rows": ..., "reason": ...}``

    Supports custom cleaning configurations:
    ``{"outlier_handling": "flag" | "cap" | "remove" | "keep", ...}``

    Usage::

        pipeline = ETLPipeline(df, cleaning_config={"outlier_handling": "cap"})
        cleaned = pipeline.run()
        summary = pipeline.get_summary()
    """

    def __init__(
        self,
        df: pd.DataFrame,
        cleaning_config: dict[str, Any] | None = None,
    ) -> None:
        self._original_df = df.copy()
        self.df = df.copy()
        self._transformations: list[dict[str, Any]] = []
        self._outliers: dict[str, int] = {}
        self._quality_before: dict[str, Any] = {}
        self._quality_after: dict[str, Any] = {}
        self._config = cleaning_config or {}

        # Record initial quality metrics
        self._quality_before = self._compute_quality()

    # ═══════════════════════════════════════════════════════════════════
    #  Public Interface
    # ═══════════════════════════════════════════════════════════════════

    def run(self) -> pd.DataFrame:
        """Execute the full cleaning pipeline.

        Returns:
            The cleaned DataFrame.
        """
        steps = [
            ("normalize_columns", self._normalize_columns),
            ("trim_strings", self._trim_strings),
            ("detect_types", self._detect_and_convert_types),
            ("convert_dates", self._convert_dates),
            ("handle_missing", self._handle_missing),
            ("remove_duplicates", self._remove_duplicates),
            ("detect_outliers", self._detect_outliers),
            ("optimize_dtypes", self._optimize_dtypes),
        ]

        for step_name, step_fn in steps:
            try:
                step_fn()
            except Exception as exc:
                logger.warning("ETL step '%s' failed: %s", step_name, exc)
                self._log_transformation(
                    operation=step_name,
                    reason=f"Step skipped due to error: {exc}",
                    critical=False,
                )

        # Record final quality metrics
        self._quality_after = self._compute_quality()

        logger.info(
            "ETL complete: %d rows -> %d rows, %d transformations",
            len(self._original_df),
            len(self.df),
            len(self._transformations),
        )
        return self.df

    def get_summary(self) -> dict[str, Any]:
        """Return a structured summary of the ETL pipeline execution.

        Returns:
            Dict with transformation metadata, before/after quality, etc.
        """
        return {
            "rows_before": len(self._original_df),
            "rows_after": len(self.df),
            "columns_before": len(self._original_df.columns),
            "columns_after": len(self.df.columns),
            "transformations_applied": [t["description"] for t in self._transformations],
            "transformations_detail": self._transformations,
            "outliers_detected": self._outliers,
            "quality_before": self._quality_before,
            "quality_after": self._quality_after,
            "memory_reduction_mb": round(
                (self._original_df.memory_usage(deep=True).sum()
                 - self.df.memory_usage(deep=True).sum())
                / (1024 * 1024),
                2,
            ),
        }

    # ═══════════════════════════════════════════════════════════════════
    #  Pipeline Steps
    # ═══════════════════════════════════════════════════════════════════

    def _normalize_columns(self) -> None:
        """Clean column names: strip whitespace, lowercase, replace spaces."""
        original_cols = self.df.columns.tolist()
        new_cols = []
        for col in original_cols:
            cleaned = str(col).strip().lower()
            cleaned = re.sub(r"[^a-z0-9_]", "_", cleaned)
            cleaned = re.sub(r"_+", "_", cleaned).strip("_")
            if not cleaned:
                cleaned = f"column_{len(new_cols)}"
            new_cols.append(cleaned)

        # Handle duplicates
        seen: dict[str, int] = {}
        final_cols: list[str] = []
        for col in new_cols:
            if col in seen:
                seen[col] += 1
                final_cols.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                final_cols.append(col)

        renamed_count = sum(
            1 for a, b in zip(original_cols, final_cols) if a != b
        )

        if renamed_count > 0:
            self.df.columns = final_cols
            self._log_transformation(
                operation="normalize_columns",
                affected_rows=0,
                method="strip + lowercase + regex cleanup",
                reason=f"Standardized {renamed_count} column names",
                description=f"Normalized {renamed_count} column names",
            )

    def _trim_strings(self) -> None:
        """Strip leading/trailing whitespace from string columns."""
        str_cols = self.df.select_dtypes(include=["object"]).columns
        trimmed_total = 0

        for col in str_cols:
            before = self.df[col].copy()
            self.df[col] = self.df[col].astype(str).str.strip()
            self.df[col] = self.df[col].replace({"nan": np.nan, "": np.nan, "None": np.nan})
            changed = (before != self.df[col]).sum()
            trimmed_total += int(changed)

        if trimmed_total > 0:
            self._log_transformation(
                operation="trim_strings",
                affected_rows=trimmed_total,
                method="str.strip()",
                reason="Remove leading/trailing whitespace and normalize empty strings",
                description=f"Trimmed whitespace in {len(str_cols)} string columns",
            )

    def _detect_and_convert_types(self) -> None:
        """Attempt to infer and convert column types (string → numeric)."""
        converted = 0
        for col in self.df.select_dtypes(include=["object"]).columns:
            try:
                numeric = pd.to_numeric(self.df[col], errors="coerce")
                non_null_original = self.df[col].notna().sum()
                non_null_converted = numeric.notna().sum()

                # Only convert if at least 80% of non-null values parsed
                if non_null_original > 0 and non_null_converted / non_null_original >= 0.8:
                    self.df[col] = numeric
                    converted += 1
                    self._log_transformation(
                        operation="type_conversion",
                        column=col,
                        affected_rows=int(non_null_converted),
                        method="pd.to_numeric",
                        reason=f"Column '{col}' contains mostly numeric values ({non_null_converted}/{non_null_original} parsed)",
                        description=f"Converted '{col}' from string to numeric",
                    )
            except Exception:
                continue

    def _convert_dates(self) -> None:
        """Detect and convert date-like string columns."""
        date_patterns = [
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}",  # YYYY-MM-DD
            r"\d{1,2}[-/]\d{1,2}[-/]\d{4}",  # DD-MM-YYYY or MM-DD-YYYY
        ]

        for col in self.df.select_dtypes(include=["object"]).columns:
            sample = self.df[col].dropna().head(20).astype(str)
            if len(sample) == 0:
                continue

            # Check if sample matches date patterns
            matches = sum(
                1 for val in sample
                if any(re.match(p, str(val).strip()) for p in date_patterns)
            )

            if matches / len(sample) >= 0.8:
                try:
                    converted = pd.to_datetime(self.df[col], errors="coerce", infer_datetime_format=True)
                    success_rate = converted.notna().sum() / max(self.df[col].notna().sum(), 1)

                    if success_rate >= 0.8:
                        self.df[col] = converted
                        self._log_transformation(
                            operation="date_conversion",
                            column=col,
                            affected_rows=int(converted.notna().sum()),
                            method="pd.to_datetime (inferred)",
                            reason=f"Column '{col}' contains date-like values",
                            description=f"Converted '{col}' to datetime",
                        )
                except Exception:
                    continue

    def _handle_missing(self) -> None:
        """Fill missing values using appropriate strategies per column type."""
        missing_before = int(self.df.isnull().sum().sum())
        if missing_before == 0:
            return

        for col in self.df.columns:
            null_count = int(self.df[col].isnull().sum())
            if null_count == 0:
                continue

            null_pct = null_count / len(self.df) * 100

            # Skip columns with too many missing values (> 90%)
            if null_pct > 90:
                self._log_transformation(
                    operation="missing_values",
                    column=col,
                    affected_rows=null_count,
                    method="skipped (>90% missing)",
                    reason=f"Column '{col}' has {null_pct:.1f}% missing — too sparse to fill",
                    description=f"Skipped '{col}' — {null_pct:.1f}% missing",
                )
                continue

            if pd.api.types.is_numeric_dtype(self.df[col]):
                # Use median for skewed data, mean for symmetric
                skewness = self.df[col].skew()
                if abs(skewness) > config.SKEWNESS_THRESHOLD:
                    fill_val = self.df[col].median()
                    method = f"median ({fill_val:.2f}), skew={skewness:.2f}"
                else:
                    fill_val = self.df[col].mean()
                    method = f"mean ({fill_val:.2f}), skew={skewness:.2f}"
                self.df[col] = self.df[col].fillna(fill_val)
            elif pd.api.types.is_datetime64_any_dtype(self.df[col]):
                if null_pct < config.DATETIME_MISSING_DROP_PCT:
                    self.df = self.df.dropna(subset=[col])
                    method = f"dropped rows (only {null_pct:.1f}% missing)"
                else:
                    method = "skipped (datetime)"
                    continue
            else:
                # Categorical/string: fill with mode
                mode_vals = self.df[col].mode()
                if len(mode_vals) > 0:
                    fill_val = mode_vals.iloc[0]
                    self.df[col] = self.df[col].fillna(fill_val)
                    method = f"mode ('{fill_val}')"
                else:
                    method = "skipped (no mode)"
                    continue

            self._log_transformation(
                operation="fill_missing",
                column=col,
                affected_rows=null_count,
                method=method,
                reason=f"Filled {null_count} missing values in '{col}' ({null_pct:.1f}%)",
                description=f"Filled {null_count} missing in '{col}' using {method.split(',')[0]}",
            )

    def _remove_duplicates(self) -> None:
        """Remove exact duplicate rows."""
        before = len(self.df)
        self.df = self.df.drop_duplicates()
        removed = before - len(self.df)

        if removed > 0:
            self._log_transformation(
                operation="remove_duplicates",
                affected_rows=removed,
                method="DataFrame.drop_duplicates()",
                reason=f"Removed {removed} exact duplicate rows ({removed/before*100:.1f}%)",
                description=f"Removed {removed:,} duplicate rows",
            )

    def _detect_outliers(self) -> None:
        """Detect outliers using IQR method and handle per config.

        Supports: ``keep`` (just flag), ``cap`` (winsorize), ``remove``, ``flag``.
        """
        handling = self._config.get("outlier_handling", "flag")
        numeric_cols = self.df.select_dtypes(include=["number"]).columns

        for col in numeric_cols:
            series = self.df[col].dropna()
            if len(series) < 10:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                continue

            lower = q1 - config.IQR_MULTIPLIER * iqr
            upper = q3 + config.IQR_MULTIPLIER * iqr

            outlier_mask = (self.df[col] < lower) | (self.df[col] > upper)
            outlier_count = int(outlier_mask.sum())

            if outlier_count == 0:
                continue

            self._outliers[col] = outlier_count

            if handling == "cap":
                self.df[col] = self.df[col].clip(lower=lower, upper=upper)
                method = f"capped to [{lower:.2f}, {upper:.2f}]"
            elif handling == "remove":
                self.df = self.df[~outlier_mask]
                method = "removed outlier rows"
            elif handling == "flag":
                flag_col = f"{col}_outlier"
                self.df[flag_col] = outlier_mask.astype(int)
                method = f"flagged in '{flag_col}' column"
            else:  # "keep"
                method = "detected only (kept)"

            self._log_transformation(
                operation="outlier_detection",
                column=col,
                affected_rows=outlier_count,
                method=f"IQR ({config.IQR_MULTIPLIER}x), {method}",
                reason=f"{outlier_count} outliers in '{col}' (IQR: [{lower:.2f}, {upper:.2f}])",
                description=f"Found {outlier_count} outliers in '{col}' — {method}",
            )

    def _optimize_dtypes(self) -> None:
        """Downcast numeric types to save memory."""
        memory_before = self.df.memory_usage(deep=True).sum()

        for col in self.df.select_dtypes(include=["int64"]).columns:
            self.df[col] = pd.to_numeric(self.df[col], downcast="integer")

        for col in self.df.select_dtypes(include=["float64"]).columns:
            self.df[col] = pd.to_numeric(self.df[col], downcast="float")

        memory_after = self.df.memory_usage(deep=True).sum()
        saved = memory_before - memory_after

        if saved > 1024:  # Only log if savings > 1 KB
            self._log_transformation(
                operation="optimize_dtypes",
                affected_rows=0,
                method="pd.to_numeric(downcast=...)",
                reason=f"Reduced memory by {saved / 1024:.1f} KB",
                description=f"Optimized dtypes — saved {saved / 1024:.1f} KB",
            )

    # ═══════════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════════

    def _log_transformation(
        self,
        operation: str,
        reason: str,
        affected_rows: int = 0,
        column: str | None = None,
        method: str = "",
        description: str = "",
        critical: bool = False,
    ) -> None:
        """Record a structured transformation log entry."""
        entry = {
            "operation": operation,
            "column": column,
            "method": method,
            "affected_rows": affected_rows,
            "reason": reason,
            "description": description or reason,
            "critical": critical,
        }
        self._transformations.append(entry)
        logger.debug("ETL: %s", description or reason)

    def _compute_quality(self) -> dict[str, Any]:
        """Compute quality metrics for the current state of the DataFrame."""
        total_cells = len(self.df) * len(self.df.columns)
        missing = int(self.df.isnull().sum().sum())
        duplicates = int(self.df.duplicated().sum())

        completeness = round((1 - missing / max(total_cells, 1)) * 100, 1)
        uniqueness = round((1 - duplicates / max(len(self.df), 1)) * 100, 1)

        return {
            "rows": len(self.df),
            "columns": len(self.df.columns),
            "completeness": completeness,
            "uniqueness": uniqueness,
            "missing_cells": missing,
            "duplicate_rows": duplicates,
            "total_cells": total_cells,
        }
