"""
SmartCSV – Central Configuration Module.

All application settings with environment variable overrides.
Single source of truth for plan limits, file validation, AI limits,
and deployment configuration.
"""

import os
import warnings
from pathlib import Path

# ── Base Paths ──────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent

# Support Vercel (read-only filesystem) by using /tmp if running there
IS_VERCEL = os.getenv("VERCEL") == "1"
ROOT_STORAGE = Path("/tmp") if IS_VERCEL else BASE_DIR

UPLOAD_FOLDER: Path = Path(os.getenv("UPLOAD_FOLDER", str(ROOT_STORAGE / "uploads")))
PROCESSED_FOLDER: Path = Path(os.getenv("PROCESSED_FOLDER", str(ROOT_STORAGE / "processed")))
LOG_FOLDER: Path = Path(os.getenv("LOG_FOLDER", str(ROOT_STORAGE / "logs")))

# ── Storage Backend ────────────────────────────────────────────────────
STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # "local" | "s3"
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "")
AWS_S3_REGION: str = os.getenv("AWS_S3_REGION", "auto")
AWS_S3_ENDPOINT_URL: str = os.getenv("AWS_S3_ENDPOINT_URL", "")  # For R2/MinIO

# ── File Upload & Validation ──────────────────────────────────────────
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "500"))
MAX_CONTENT_LENGTH: int = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS: set[str] = {"csv"}
ALLOWED_MIME_TYPES: set[str] = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
}
MAX_ROWS: int = int(os.getenv("MAX_ROWS", "500000"))
MAX_COLUMNS: int = int(os.getenv("MAX_COLUMNS", "200"))
MAX_CELL_LENGTH: int = int(os.getenv("MAX_CELL_LENGTH", "32768"))

# ── Flask ───────────────────────────────────────────────────────────────
FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT: int = int(os.environ.get("PORT", 5000))
FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_ENV: str = os.getenv("FLASK_ENV", "production")

_DEFAULT_SECRET = "smartcsv-secret-key-change-in-prod"
SECRET_KEY: str = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
if SECRET_KEY == _DEFAULT_SECRET and FLASK_ENV == "production":
    warnings.warn(
        "SECRET_KEY is set to the insecure default. "
        "Set a strong SECRET_KEY environment variable for production.",
        stacklevel=1,
    )

# ── Application URL ───────────────────────────────────────────────────
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")

# ── CORS ──────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins. Empty = restrict in production.
_cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if _cors_raw
    else []
)

# ── Rate Limiting ─────────────────────────────────────────────────────
RATELIMIT_STORAGE_URI: str = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

# ── Supabase Auth ──────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_JWKS_URL: str = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ── AI / LLM ───────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MAX_QUESTION_LENGTH: int = int(os.getenv("MAX_QUESTION_LENGTH", "2000"))
MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
MAX_AI_OUTPUT_TOKENS: int = int(os.getenv("MAX_AI_OUTPUT_TOKENS", "1024"))
MAX_DATA_CONTEXT_ROWS: int = int(os.getenv("MAX_DATA_CONTEXT_ROWS", "100"))

# ── Stripe Billing ─────────────────────────────────────────────────────
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO: str = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_TEAM: str = os.getenv("STRIPE_PRICE_TEAM", "")

# ── Logging ─────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
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
MAX_CHARTS: int = int(os.getenv("MAX_CHARTS", "10"))
# P-value threshold for correlation significance (NOT a correlation threshold)
CORRELATION_P_VALUE_THRESHOLD: float = 0.05

# ── Plan Limits (Single Source of Truth) ───────────────────────────────
PLAN_LIMITS: dict[str, dict] = {
    "free": {
        "uploads_per_month": 10,
        "max_file_size_mb": 50,
        "ai_requests_per_month": 3,
        "max_rows": 50000,
        "retention_days": 7,
        "features": ["etl", "insights", "export"],
    },
    "pro": {
        "uploads_per_month": 100,
        "max_file_size_mb": 150,
        "ai_requests_per_month": 50,
        "max_rows": 200000,
        "retention_days": 30,
        "features": ["etl", "insights", "export", "chat", "share", "api"],
    },
    "team": {
        "uploads_per_month": 500,
        "max_file_size_mb": 500,
        "ai_requests_per_month": -1,  # unlimited
        "max_rows": 500000,
        "retention_days": 90,
        "features": ["etl", "insights", "export", "chat", "share", "api", "priority"],
    },
}

# ── Retention / Cleanup ───────────────────────────────────────────────
FREE_RETENTION_DAYS: int = int(os.getenv("FREE_RETENTION_DAYS", "7"))
PRO_RETENTION_DAYS: int = int(os.getenv("PRO_RETENTION_DAYS", "30"))
TEAM_RETENTION_DAYS: int = int(os.getenv("TEAM_RETENTION_DAYS", "90"))

# ── Ensure directories exist ───────────────────────────────────────────
for _dir in (UPLOAD_FOLDER, PROCESSED_FOLDER, LOG_FOLDER):
    _dir.mkdir(parents=True, exist_ok=True)
