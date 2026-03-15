"""
SmartCSV – Flask REST API.

Endpoints:
    POST /upload    – Upload CSV, return metadata.
    POST /process   – Run ETL pipeline, return summary.
    GET  /insights  – Return stats, charts, NLG insights.
    GET  /download  – Download processed CSV.
"""

from __future__ import annotations

import os
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
from etl import run_etl
from insights import generate_full_insights
from utils.file_handler import load_csv, save_upload
from utils.logger import get_logger
from utils.quotas import check_upload_quota
from utils.storage import get_storage
from utils.validators import get_upload_metadata, validate_csv

logger = get_logger(__name__)

# ── App factory ─────────────────────────────────────────────────────────
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    integrations=[FlaskIntegration()],
    traces_sample_rate=0.2,
    profiles_sample_rate=0.1,
    environment=os.environ.get("FLASK_ENV", "production"),
    send_default_pii=False,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = config.SECRET_KEY
CORS(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

# ── Register blueprints ────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(billing_bp)

# ── Security middleware ────────────────────────────────────────────────
from utils.security import apply_security_headers, apply_request_validation
apply_security_headers(app)
apply_request_validation(app)


# ═══════════════════════════════════════════════════════════════════════
#  Error handlers
# ═══════════════════════════════════════════════════════════════════════

@app.errorhandler(413)
def file_too_large(error):  # noqa: ANN001, ANN201
    """Handle file-size-exceeded errors."""
    max_mb = config.MAX_CONTENT_LENGTH / (1024 * 1024)
    return jsonify({"error": f"File exceeds maximum size ({max_mb:.0f} MB)."}), 413


@app.errorhandler(400)
def bad_request(error):  # noqa: ANN001, ANN201
    """Handle bad request errors."""
    return jsonify({"error": str(error.description)}), 400


@app.errorhandler(404)
def not_found(error):  # noqa: ANN001, ANN201
    """Handle not-found errors."""
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(500)
def internal_error(error):  # noqa: ANN001, ANN201
    """Handle internal server errors."""
    logger.exception("Internal server error")
    return jsonify({"error": "An internal error occurred."}), 500


# ═══════════════════════════════════════════════════════════════════════
#  Routes
# ═══════════════════════════════════════════════════════════════════════

@app.route("/")
def index():  # noqa: ANN201
    """Serve the single-page dashboard."""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
@require_auth
def upload_file():  # noqa: ANN201
    """Upload a CSV file and return metadata.

    Returns:
        JSON with file metadata or error message.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No file selected."}), 400

    filename = file.filename
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in config.ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Invalid file type '.{ext}'. Only CSV files are accepted."}), 400

    try:
        # Check upload quota before saving
        quota_err = check_upload_quota()
        if quota_err:
            return quota_err

        storage_key = save_upload(file, filename)
        storage = get_storage()
        raw = storage.load(storage_key)
        size_bytes = len(raw)

        df = load_csv(storage_key)
        warnings = validate_csv(df)
        metadata = get_upload_metadata(df, storage_key, size_bytes)
        metadata["warnings"] = warnings

        # Record in database (best-effort — don't block upload if DB is down)
        try:
            db_uploads.create_upload(
                user_id=g.user_id,
                original_name=filename,
                storage_key=storage_key,
                row_count=metadata["row_count"],
                column_count=metadata["column_count"],
                size_bytes=size_bytes,
            )
            # Increment monthly upload counter
            from db import users as db_users
            db_users.increment_upload_count(g.user_id)
        except Exception as db_exc:
            logger.warning("Failed to record upload in DB: %s", db_exc)

        logger.info("Upload successful: %s", storage_key)
        return jsonify(metadata), 200
    except ValueError as exc:
        logger.warning("Upload validation failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Upload failed")
        return jsonify({"error": f"Upload failed: {exc}"}), 500


@app.route("/process", methods=["POST"])
@require_auth
def process_file():  # noqa: ANN201
    """Run ETL pipeline on an uploaded file.

    Expects JSON body: ``{"filename": "..."}``

    Returns:
        JSON with ETL summary or error message.
    """
    data = request.get_json(silent=True)
    if not data or "filename" not in data:
        return jsonify({"error": "Missing 'filename' in request body."}), 400

    filename = data["filename"]
    upload_key = f"uploads/{filename}"

    storage = get_storage()
    if not storage.exists(upload_key):
        return jsonify({"error": f"File '{filename}' not found."}), 404

    try:
        _, summary, output_key = run_etl(upload_key)

        # Update upload status in DB (best-effort)
        try:
            record = db_uploads.get_upload_by_key(upload_key)
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
        logger.exception("ETL processing failed")
        return jsonify({"error": f"Processing failed: {exc}"}), 500


@app.route("/insights", methods=["GET"])
@require_auth
def get_insights():  # noqa: ANN201
    """Return full insights for a processed CSV.

    Query param: ``?file=cleaned_...``

    Returns:
        JSON with stats, charts, NLG insights.
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    processed_key = f"processed/{filename}"
    storage = get_storage()
    if not storage.exists(processed_key):
        return jsonify({"error": f"Processed file '{filename}' not found."}), 404

    try:
        with sentry_sdk.start_span(op="insights.compute", description="Full insights pipeline"):
            df = load_csv(processed_key)
            result = generate_full_insights(df)
        logger.info("Insights generated for %s", filename)
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Insight generation failed")
        return jsonify({"error": f"Insight generation failed: {exc}"}), 500


@app.route("/download", methods=["GET"])
@require_auth
def download_file():  # noqa: ANN201
    """Download a processed CSV file.

    Query param: ``?file=cleaned_...``

    For local storage: serves the file directly.
    For S3 storage: redirects to a presigned URL.
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    processed_key = f"processed/{filename}"
    storage = get_storage()
    if not storage.exists(processed_key):
        return jsonify({"error": f"File '{filename}' not found."}), 404

    download_ref = storage.get_download_path(processed_key)

    # LocalStorage returns a Path, S3Storage returns a presigned URL string
    if isinstance(download_ref, Path):
        return send_file(str(download_ref), as_attachment=True, download_name=filename)
    else:
        return redirect(download_ref)


@app.route("/uploads", methods=["GET"])
@require_auth
def list_uploads():  # noqa: ANN201
    """Return the authenticated user's upload history.

    Returns:
        JSON list of upload records, newest first.
    """
    try:
        uploads = db_uploads.get_user_uploads(g.user_id)
        return jsonify(uploads), 200
    except Exception as exc:
        logger.warning("Failed to fetch uploads: %s", exc)
        return jsonify([]), 200  # graceful degradation


@app.route("/chat", methods=["POST"])
@require_auth
def chat():  # noqa: ANN201
    """Chat with a processed CSV using AI.

    Request JSON::

        {
            "file": "cleaned_...",
            "question": "What is the average revenue?",
            "history": [{"role": "user", "content": "..."}, ...]  // optional
        }

    Returns:
        JSON with ``answer`` and ``tokens_used``.
    """
    data = request.get_json(silent=True)
    if not data or not data.get("file") or not data.get("question"):
        return jsonify({"error": "Missing 'file' and 'question' in request body."}), 400

    filename = data["file"]
    processed_key = f"processed/{filename}"

    storage = get_storage()
    if not storage.exists(processed_key):
        return jsonify({"error": f"File '{filename}' not found."}), 404

    try:
        from ai.chat import chat_with_csv
        df = load_csv(processed_key)
        result = chat_with_csv(
            df,
            question=data["question"],
            history=data.get("history"),
        )
        return jsonify(result), 200
    except (ImportError, ValueError) as exc:
        return jsonify({"error": f"AI chat not available: {exc}"}), 503
    except Exception as exc:
        logger.exception("Chat failed")
        return jsonify({"error": f"Chat failed: {exc}"}), 500


@app.route("/share", methods=["POST"])
@require_auth
def create_share():  # noqa: ANN201
    """Create a shareable link for a processed report.

    Request JSON: ``{"file": "cleaned_...", "title": "...", "expires_hours": 72}``
    """
    data = request.get_json(silent=True)
    if not data or not data.get("file"):
        return jsonify({"error": "Missing 'file' in request body."}), 400

    filename = data["file"]
    processed_key = f"processed/{filename}"

    storage = get_storage()
    if not storage.exists(processed_key):
        return jsonify({"error": f"File '{filename}' not found."}), 404

    try:
        share = db_reports.create_share(
            user_id=g.user_id,
            processed_key=processed_key,
            title=data.get("title"),
            expires_hours=data.get("expires_hours"),
        )
        share["share_url"] = f"/share/{share['share_token']}"
        return jsonify(share), 201
    except Exception as exc:
        logger.exception("Share creation failed")
        return jsonify({"error": f"Failed to create share: {exc}"}), 500


@app.route("/share/<token>", methods=["GET"])
def view_shared_report(token: str):  # noqa: ANN201
    """View a shared report (public, no auth required)."""
    try:
        report = db_reports.get_by_token(token)
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
        from insights import generate_full_insights
        result = generate_full_insights(df)
        result["share_info"] = {
            "title": report.get("title"),
            "view_count": report.get("view_count", 0) + 1,
        }
        return jsonify(result), 200
    except FileNotFoundError:
        return jsonify({"error": "Shared data file not found."}), 404
    except Exception as exc:
        logger.exception("Shared report view failed")
        return jsonify({"error": str(exc)}), 500


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


@app.route("/api-keys", methods=["POST"])
@require_auth
def create_api_key():  # noqa: ANN201
    """Generate a new API key for the authenticated user.

    Request JSON: ``{"name": "My Integration"}`` (optional)
    """
    from auth.api_keys import generate_key
    data = request.get_json(silent=True) or {}
    try:
        result = generate_key(g.user_id, name=data.get("name", "Default"))
        return jsonify(result), 201
    except Exception as exc:
        logger.exception("API key creation failed")
        return jsonify({"error": str(exc)}), 500


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


@app.route("/landing")
def landing():  # noqa: ANN201
    """Serve the marketing landing page."""
    return render_template("landing.html")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
