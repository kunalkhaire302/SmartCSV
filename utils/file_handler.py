"""
File I/O utilities – save uploads, load CSVs with encoding detection.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import BinaryIO

import chardet
import pandas as pd

import config
from utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename, keep extension.

    Args:
        filename: Original filename from upload.

    Returns:
        Sanitised filename string.
    """
    stem = Path(filename).stem
    ext = Path(filename).suffix
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in stem)
    return safe + ext


def generate_unique_filename(original: str) -> str:
    """Create a timestamped, unique filename.

    Args:
        original: Original uploaded filename.

    Returns:
        Unique filename like ``20260212_143000_ab12cd34_data.csv``.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    safe = _sanitize_filename(original)
    return f"{ts}_{uid}_{safe}"


def save_upload(file_storage: BinaryIO, original_filename: str) -> Path:
    """Validate and save an uploaded file to the uploads directory.

    Args:
        file_storage: File-like object from the request.
        original_filename: Original filename.

    Returns:
        Path to the saved file.

    Raises:
        ValueError: If extension or MIME type is not allowed.
    """
    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension '.{ext}' is not allowed. Accepted: {config.ALLOWED_EXTENSIONS}")

    unique_name = generate_unique_filename(original_filename)
    dest = config.UPLOAD_FOLDER / unique_name
    file_storage.save(str(dest))
    logger.info("Saved upload to %s", dest)
    return dest


def detect_encoding(file_path: Path, sample_size: int = 65536) -> str:
    """Detect file encoding using chardet.

    Args:
        file_path: Path to the file.
        sample_size: Bytes to sample for detection.

    Returns:
        Detected encoding string, defaults to ``utf-8``.
    """
    with open(file_path, "rb") as fh:
        raw = fh.read(sample_size)
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    logger.info("Detected encoding: %s (confidence: %.0f%%)", encoding, (result.get("confidence", 0) * 100))
    return encoding


def load_csv(file_path: Path) -> pd.DataFrame:
    """Load a CSV file into a DataFrame with encoding detection.

    Args:
        file_path: Path to the CSV file.

    Returns:
        Pandas DataFrame.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    encoding = detect_encoding(file_path)
    try:
        df = pd.read_csv(str(file_path), encoding=encoding, low_memory=False)
    except UnicodeDecodeError:
        logger.warning("Encoding %s failed, falling back to utf-8 with errors='replace'", encoding)
        df = pd.read_csv(str(file_path), encoding="utf-8", errors="replace", low_memory=False)
    except Exception as exc:
        logger.error("Failed to parse CSV: %s", exc)
        raise ValueError(f"Unable to read CSV file: {exc}") from exc

    logger.info("Loaded CSV with %d rows × %d columns", len(df), len(df.columns))
    return df
