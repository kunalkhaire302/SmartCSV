"""
SmartCSV – Central Configuration Module.

All application settings with environment variable overrides.
"""

import os
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
FLASK_PORT: int = int(os.environ.get("PORT", 5000))
FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
SECRET_KEY: str = os.getenv("SECRET_KEY", "smartcsv-secret-key-change-in-prod")

# ── Supabase Auth ──────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ── AI / LLM ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ── Stripe Billing ─────────────────────────────────────────────────────
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO: str = os.getenv("STRIPE_PRICE_PRO", "")      # Stripe Price ID for Pro plan
STRIPE_PRICE_TEAM: str = os.getenv("STRIPE_PRICE_TEAM", "")    # Stripe Price ID for Team plan

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
CORRELATION_SIGNIFICANCE: float = 0.05

# ── Ensure directories exist ───────────────────────────────────────────
for _dir in (UPLOAD_FOLDER, PROCESSED_FOLDER, LOG_FOLDER):
    _dir.mkdir(parents=True, exist_ok=True)
