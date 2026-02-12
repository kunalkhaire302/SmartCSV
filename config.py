"""
SmartCSV – Central Configuration Module.

All application settings with environment variable overrides.
"""

import os
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent
UPLOAD_FOLDER: Path = Path(os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads")))
PROCESSED_FOLDER: Path = Path(os.getenv("PROCESSED_FOLDER", str(BASE_DIR / "processed")))
LOG_FOLDER: Path = Path(os.getenv("LOG_FOLDER", str(BASE_DIR / "logs")))

# ── File Upload ─────────────────────────────────────────────────────────
MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024)))  # 10 MB
ALLOWED_EXTENSIONS: set[str] = {"csv"}
ALLOWED_MIME_TYPES: set[str] = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
}

# ── Flask ───────────────────────────────────────────────────────────────
FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT: int = int(os.getenv("PORT", "5000"))
FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
SECRET_KEY: str = os.getenv("SECRET_KEY", "smartcsv-secret-key-change-in-prod")

# ── Logging ─────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB per log file
LOG_BACKUP_COUNT: int = 3

# ── ETL Settings ────────────────────────────────────────────────────────
SKEWNESS_THRESHOLD: float = 1.0  # use median if abs(skew) > threshold
IQR_MULTIPLIER: float = 1.5
DATETIME_MISSING_DROP_PCT: float = 5.0  # drop datetime rows if missing < 5 %
TOP_N_CATEGORIES: int = 10

# ── Insight / Chart Settings ───────────────────────────────────────────
MAX_PIE_CATEGORIES: int = 7
CORRELATION_SIGNIFICANCE: float = 0.05

# ── Ensure directories exist ───────────────────────────────────────────
for _dir in (UPLOAD_FOLDER, PROCESSED_FOLDER, LOG_FOLDER):
    _dir.mkdir(parents=True, exist_ok=True)
