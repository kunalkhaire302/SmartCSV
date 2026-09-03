"""
SmartCSV – Flask REST API.

Endpoints:
    GET  /              – Serve the single-page dashboard.
    GET  /landing       – Marketing landing page.
    GET  /health        – Health check.
    GET  /config/limits – Plan limits for frontend.
    POST /upload        – Upload CSV, return metadata.
    POST /process       – Run ETL pipeline, return summary.
    GET  /insights      – Return stats, charts, NLG insights.
    GET  /download      – Download processed CSV.
    GET  /uploads       – List user's upload history.
    POST /chat          – Chat with a processed CSV using AI.
    POST /share         – Create a shareable report link.
    GET  /share/<token> – View a shared report (public).
    DELETE /share/<token> – Revoke a shared report link.
    GET  /shares        – List user's shared reports.
    POST /api-keys      – Generate a new API key.
    GET  /api-keys      – List user's API keys.
    DELETE /api-keys/<id> – Revoke an API key.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
)
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from auth.decorators import require_auth
from auth.routes import auth_bp
from billing.routes import billing_bp
from db import uploads as db_uploads
from db import reports as db_reports
from etl import ETLPipeline
from insights import generate_insights
from utils.file_handler import load_csv, save_upload
from utils.logger import get_logger
from utils.quotas import check_upload_quota, check_file_size_quota, check_ai_quota, has_feature
from utils.storage import get_storage
from utils.validators import get_upload_metadata, validate_csv, validate_file_type, compute_data_quality_score

logger = get_logger(__name__)

# ── Sentry (best-effort) ─────────────────────────────────────────────
try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    if config.SENTRY_DSN:
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.2,
            profiles_sample_rate=0.1,
            environment=config.FLASK_ENV,
            send_default_pii=False,
        )
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]

# ── App factory ─────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = config.SECRET_KEY

# ── CORS — restrict origins in production ─────────────────────────────
if config.CORS_ALLOWED_ORIGINS:
    CORS(app, origins=config.CORS_ALLOWED_ORIGINS, supports_credentials=True)
else:
    CORS(app)  # Allow all in development

# ── Rate Limiter ─────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri=config.RATELIMIT_STORAGE_URI,
)

# ── Register blueprints ────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(billing_bp)

# ── Security middleware ────────────────────────────────────────────────
from utils.security import apply_security_headers
apply_security_headers(app)


# ═══════════════════════════════════════════════════════════════════════
#  Request ID Middleware
# ═══════════════════════════════════════════════════════════════════════

@app.before_request
def _inject_request_id():
    """Assign a unique ID to every request for tracing."""
    g.request_id = str(uuid.uuid4())[:8]


# ═══════════════════════════════════════════════════════════════════════
#  Error Handlers — never expose internal exceptions
# ═══════════════════════════════════════════════════════════════════════

@app.errorhandler(413)
def file_too_large(error):  # noqa: ANN001, ANN201
    max_mb = config.MAX_CONTENT_LENGTH / (1024 * 1024)
    return jsonify({"error": f"File exceeds maximum size ({max_mb:.0f} MB)."}), 413


@app.errorhandler(400)
def bad_request(error):  # noqa: ANN001, ANN201
    return jsonify({"error": str(error.description)}), 400


@app.errorhandler(404)
def not_found(error):  # noqa: ANN001, ANN201
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(429)
def rate_limited(error):  # noqa: ANN001, ANN201
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429


@app.errorhandler(500)
def internal_error(error):  # noqa: ANN001, ANN201
    rid = getattr(g, "request_id", "unknown")
    logger.exception("Internal server error (request_id=%s)", rid)
    return jsonify({
        "error": "An internal error occurred.",
        "request_id": rid,
    }), 500


# ═══════════════════════════════════════════════════════════════════════
#  Helper — get user plan safely
# ═══════════════════════════════════════════════════════════════════════

def _get_user_plan() -> str:
    """Get the authenticated user's plan (defaults to 'free')."""
    try:
        from db.users import get_user_plan
        return get_user_plan(g.user_id)
    except Exception:
        return "free"


# ═══════════════════════════════════════════════════════════════════════
#  Public Routes
# ═══════════════════════════════════════════════════════════════════════

@app.route("/")
def index():  # noqa: ANN201
    """Serve the single-page dashboard."""
    return render_template("index.html")


@app.route("/landing")
def landing():  # noqa: ANN201
    """Serve the marketing landing page."""
    return render_template("landing.html")


@app.route("/login")
def login_page():  # noqa: ANN201
    """Serve the login page."""
    return render_template("login.html")


@app.route("/register")
def register_page():  # noqa: ANN201
    """Serve the register page."""
    return render_template("register.html")


@app.route("/health")
def health():  # noqa: ANN201
    """Health check endpoint for load balancers and monitoring."""
    return jsonify({"status": "healthy", "version": "2.0.0"}), 200


@app.route("/config/limits")
def get_plan_limits():  # noqa: ANN201
    """Return plan limits for the frontend to display."""
    return jsonify(config.PLAN_LIMITS), 200


# ═══════════════════════════════════════════════════════════════════════
#  Upload
# ═══════════════════════════════════════════════════════════════════════

@app.route("/upload", methods=["POST"])
@require_auth
def upload_file():  # noqa: ANN201
    """Upload a CSV file and return metadata.

    Enforces:
    - File type validation
    - Plan-based file size limits
    - Upload quota
    - CSV structure validation
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No file selected."}), 400

    filename = file.filename
    if not validate_file_type(filename):
        return jsonify({"error": "Invalid file type. Only CSV files are accepted."}), 400

    try:
        plan = _get_user_plan()

        # Check file size quota
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset

        size_check = check_file_size_quota(file_size, plan)
        if not size_check["allowed"]:
            return jsonify({
                "error": f"File size ({size_check['size_mb']} MB) exceeds "
                         f"your plan limit ({size_check['limit_mb']} MB).",
            }), 413

        # Check upload quota
        quota = check_upload_quota(g.user_id, plan)
        if not quota["allowed"]:
            return jsonify({
                "error": f"Upload quota exceeded. "
                         f"Used {quota['used']}/{quota['limit']} this month.",
                "quota": quota,
            }), 429

        storage_key = save_upload(file, filename)
        storage = get_storage()
        raw = storage.load(storage_key)
        size_bytes = len(raw)

        df = load_csv(storage_key)
        warnings = validate_csv(df)
        metadata = get_upload_metadata(df, storage_key, size_bytes)
        metadata["warnings"] = warnings
        metadata["quality"] = compute_data_quality_score(df)

        # Record in database (best-effort)
        upload_record = None
        try:
            upload_record = db_uploads.create_upload(
                user_id=g.user_id,
                original_name=filename,
                storage_key=storage_key,
                row_count=metadata["row_count"],
                column_count=metadata["column_count"],
                size_bytes=size_bytes,
            )
            metadata["dataset_id"] = upload_record.get("id")
        except Exception as db_exc:
            logger.warning("Failed to record upload in DB: %s", db_exc)

        logger.info("Upload successful: %s", storage_key)
        return jsonify(metadata), 200
    except ValueError as exc:
        logger.warning("Upload validation failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Upload failed (request_id=%s)", getattr(g, "request_id", ""))
        return jsonify({"error": "Upload failed. Please try again."}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Process (ETL)
# ═══════════════════════════════════════════════════════════════════════

@app.route("/process", methods=["POST"])
@require_auth
def process_file():  # noqa: ANN201
    """Run ETL pipeline on an uploaded file.

    Expects JSON body: ``{"filename": "...", "cleaning_config": {...}}``

    Enforces dataset ownership via storage key lookup.
    """
    data = request.get_json(silent=True)
    if not data or "filename" not in data:
        return jsonify({"error": "Missing 'filename' in request body."}), 400

    filename = data["filename"]
    upload_key = f"uploads/{filename}"
    cleaning_config = data.get("cleaning_config", {})

    # ── Ownership verification ────────────────────────────────────
    try:
        record = db_uploads.get_user_upload_by_key(g.user_id, upload_key)
        if not record:
            return jsonify({"error": "Dataset not found."}), 404
    except Exception:
        # If DB is down, check storage exists as fallback
        storage = get_storage()
        if not storage.exists(upload_key):
            return jsonify({"error": "Dataset not found."}), 404

    try:
        df = load_csv(upload_key)
        pipeline = ETLPipeline(df, cleaning_config=cleaning_config)
        cleaned = pipeline.run()
        summary = pipeline.get_summary()

        # Save processed file
        output_filename = f"cleaned_{filename}"
        output_key = f"processed/{output_filename}"
        storage = get_storage()
        storage.save(output_key, cleaned.to_csv(index=False).encode("utf-8"))

        summary["processed_file"] = output_filename

        # Update upload status in DB (best-effort)
        try:
            if record:
                db_uploads.update_upload_status(
                    record["id"], "completed", processed_key=output_key,
                )
        except Exception as db_exc:
            logger.warning("Failed to update upload status: %s", db_exc)

        logger.info("ETL complete: %s -> %s", upload_key, output_key)
        return jsonify(summary), 200
    except ValueError as exc:
        logger.warning("ETL failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("ETL processing failed (request_id=%s)", getattr(g, "request_id", ""))
        return jsonify({"error": "Processing failed. Please try again."}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Insights
# ═══════════════════════════════════════════════════════════════════════

@app.route("/insights", methods=["GET"])
@require_auth
def get_insights():  # noqa: ANN201
    """Return full insights for a processed CSV.

    Query param: ``?file=cleaned_...``

    Enforces ownership via processed_key lookup.
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    processed_key = f"processed/{filename}"

    # ── Ownership verification ────────────────────────────────────
    try:
        record = db_uploads.get_user_upload_by_processed_key(g.user_id, processed_key)
        if not record:
            # Fallback: check storage exists
            storage = get_storage()
            if not storage.exists(processed_key):
                return jsonify({"error": "Dataset not found."}), 404
    except Exception:
        storage = get_storage()
        if not storage.exists(processed_key):
            return jsonify({"error": "Dataset not found."}), 404

    try:
        df = load_csv(processed_key)
        result = generate_insights(df)
        logger.info("Insights generated for %s", filename)
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Insight generation failed (request_id=%s)", getattr(g, "request_id", ""))
        return jsonify({"error": "Insight generation failed. Please try again."}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Download
# ═══════════════════════════════════════════════════════════════════════

@app.route("/download", methods=["GET"])
@require_auth
def download_file():  # noqa: ANN201
    """Download a processed CSV file.

    Query param: ``?file=cleaned_...``

    Enforces ownership.
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    processed_key = f"processed/{filename}"

    # ── Ownership verification ────────────────────────────────────
    try:
        record = db_uploads.get_user_upload_by_processed_key(g.user_id, processed_key)
        if not record:
            storage = get_storage()
            if not storage.exists(processed_key):
                return jsonify({"error": "File not found."}), 404
    except Exception:
        storage = get_storage()
        if not storage.exists(processed_key):
            return jsonify({"error": "File not found."}), 404

    storage = get_storage()
    download_ref = storage.get_download_path(processed_key)

    if isinstance(download_ref, Path):
        return send_file(str(download_ref), as_attachment=True, download_name=filename)
    else:
        return redirect(download_ref)


# ═══════════════════════════════════════════════════════════════════════
#  Upload History
# ═══════════════════════════════════════════════════════════════════════

@app.route("/uploads", methods=["GET"])
@require_auth
def list_uploads():  # noqa: ANN201
    """Return the authenticated user's upload history."""
    try:
        uploads = db_uploads.get_user_uploads(g.user_id)
        return jsonify(uploads), 200
    except Exception as exc:
        logger.warning("Failed to fetch uploads: %s", exc)
        return jsonify([]), 200


# ═══════════════════════════════════════════════════════════════════════
#  Chat
# ═══════════════════════════════════════════════════════════════════════

@app.route("/chat", methods=["POST"])
@require_auth
def chat():  # noqa: ANN201
    """Chat with a processed CSV using AI.

    Enforces:
    - Feature gating (pro/team only)
    - AI quota
    - Dataset ownership
    """
    data = request.get_json(silent=True)
    if not data or not data.get("file") or not data.get("question"):
        return jsonify({"error": "Missing 'file' and 'question' in request body."}), 400

    plan = _get_user_plan()
    if not has_feature(plan, "chat"):
        return jsonify({
            "error": "Chat feature requires Pro or Team plan.",
            "upgrade_required": True,
        }), 403

    filename = data["file"]
    processed_key = f"processed/{filename}"

    # ── Ownership verification ────────────────────────────────────
    try:
        record = db_uploads.get_user_upload_by_processed_key(g.user_id, processed_key)
        if not record:
            storage = get_storage()
            if not storage.exists(processed_key):
                return jsonify({"error": "Dataset not found."}), 404
    except Exception:
        storage = get_storage()
        if not storage.exists(processed_key):
            return jsonify({"error": "Dataset not found."}), 404

    try:
        from ai.chat import chat_with_csv
        df = load_csv(processed_key)
        result = chat_with_csv(
            df,
            question=data["question"],
            history=data.get("history"),
            user_id=g.user_id,
        )
        return jsonify(result), 200
    except ImportError:
        return jsonify({"error": "AI chat is not available (SDK missing)."}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Chat failed (request_id=%s)", getattr(g, "request_id", ""))
        return jsonify({"error": "Chat failed. Please try again."}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Sharing
# ═══════════════════════════════════════════════════════════════════════

@app.route("/share", methods=["POST"])
@require_auth
def create_share():  # noqa: ANN201
    """Create a shareable link for a processed report.

    Enforces feature gating and dataset ownership.

    Request JSON: ``{"file": "cleaned_...", "title": "...", "expires_hours": 72}``
    """
    plan = _get_user_plan()
    if not has_feature(plan, "share"):
        return jsonify({
            "error": "Sharing feature requires Pro or Team plan.",
            "upgrade_required": True,
        }), 403

    data = request.get_json(silent=True)
    if not data or not data.get("file"):
        return jsonify({"error": "Missing 'file' in request body."}), 400

    filename = data["file"]
    processed_key = f"processed/{filename}"

    # ── Ownership verification ────────────────────────────────────
    try:
        record = db_uploads.get_user_upload_by_processed_key(g.user_id, processed_key)
        if not record:
            storage = get_storage()
            if not storage.exists(processed_key):
                return jsonify({"error": "Dataset not found."}), 404
    except Exception:
        storage = get_storage()
        if not storage.exists(processed_key):
            return jsonify({"error": "Dataset not found."}), 404

    try:
        expires_at = None
        if data.get("expires_hours"):
            from datetime import datetime, timedelta, timezone
            hours = min(int(data["expires_hours"]), 720)  # Max 30 days
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

        share = db_reports.create_share(
            user_id=g.user_id,
            processed_key=processed_key,
            title=data.get("title"),
            expires_at=expires_at,
        )
        share["share_url"] = f"{config.APP_BASE_URL}/share/{share['share_token']}"
        return jsonify(share), 201
    except Exception as exc:
        logger.exception("Share creation failed (request_id=%s)", getattr(g, "request_id", ""))
        return jsonify({"error": "Failed to create share. Please try again."}), 500


@app.route("/share/<token>", methods=["GET"])
def view_shared_report(token: str):  # noqa: ANN201
    """View a shared report (public, no auth required)."""
    try:
        report = db_reports.get_share_by_token(token)
        if not report:
            return jsonify({"error": "Report not found or expired."}), 404

        # Check expiry
        if report.get("expires_at"):
            from datetime import datetime, timezone
            expiry = datetime.fromisoformat(report["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry:
                return jsonify({"error": "This report link has expired."}), 410

        # Increment views (best-effort)
        db_reports.increment_views(token)

        # Load and return insights
        df = load_csv(report["processed_key"])
        result = generate_insights(df)
        result["share_info"] = {
            "title": report.get("title"),
            "view_count": report.get("view_count", 0) + 1,
        }
        return jsonify(result), 200
    except FileNotFoundError:
        return jsonify({"error": "Shared data file not found."}), 404
    except Exception as exc:
        logger.exception("Shared report view failed")
        return jsonify({"error": "Failed to load shared report."}), 500


@app.route("/shares", methods=["GET"])
@require_auth
def list_shares():  # noqa: ANN201
    """List the authenticated user's shared reports."""
    try:
        shares = db_reports.get_user_shares(g.user_id)
        return jsonify(shares), 200
    except Exception as exc:
        logger.warning("Failed to fetch shares: %s", exc)
        return jsonify([]), 200


@app.route("/share/<token>", methods=["DELETE"])
@require_auth
def revoke_share(token: str):  # noqa: ANN201
    """Delete a shared report link (owner only)."""
    deleted = db_reports.delete_share(token, g.user_id)
    if deleted:
        return jsonify({"message": "Share revoked."}), 200
    return jsonify({"error": "Share not found or unauthorized."}), 404


# ═══════════════════════════════════════════════════════════════════════
#  API Keys
# ═══════════════════════════════════════════════════════════════════════

@app.route("/api-keys", methods=["POST"])
@require_auth
def create_api_key():  # noqa: ANN201
    """Generate a new API key for the authenticated user."""
    plan = _get_user_plan()
    if not has_feature(plan, "api"):
        return jsonify({
            "error": "API key feature requires Pro or Team plan.",
            "upgrade_required": True,
        }), 403

    from auth.api_keys import generate_key
    data = request.get_json(silent=True) or {}
    try:
        result = generate_key(g.user_id, name=data.get("name", "Default"))
        return jsonify(result), 201
    except Exception as exc:
        logger.exception("API key creation failed")
        return jsonify({"error": "Failed to create API key."}), 500


@app.route("/api-keys", methods=["GET"])
@require_auth
def list_api_keys():  # noqa: ANN201
    """List the authenticated user's API keys (prefix only)."""
    from auth.api_keys import list_keys
    try:
        keys = list_keys(g.user_id)
        return jsonify(keys), 200
    except Exception as exc:
        logger.warning("Failed to list API keys: %s", exc)
        return jsonify([]), 200


@app.route("/api-keys/<key_id>", methods=["DELETE"])
@require_auth
def revoke_api_key(key_id: str):  # noqa: ANN201
    """Revoke an API key."""
    from auth.api_keys import revoke_key
    if revoke_key(key_id, g.user_id):
        return jsonify({"message": "API key revoked."}), 200
    return jsonify({"error": "Key not found or unauthorized."}), 404


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
