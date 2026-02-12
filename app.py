"""
SmartCSV – Flask REST API.

Endpoints:
    POST /upload    – Upload CSV, return metadata.
    POST /process   – Run ETL pipeline, return summary.
    GET  /insights  – Return stats, charts, NLG insights.
    GET  /download  – Download processed CSV.
"""

from __future__ import annotations

from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_cors import CORS

import config
from etl import run_etl
from insights import generate_full_insights
from utils.file_handler import load_csv, save_upload
from utils.logger import get_logger
from utils.validators import get_upload_metadata, validate_csv, validate_file_size

logger = get_logger(__name__)

# ── App factory ─────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = config.SECRET_KEY
CORS(app)


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
        saved_path = save_upload(file, filename)
        validate_file_size(saved_path)
        df = load_csv(saved_path)
        warnings = validate_csv(df)
        metadata = get_upload_metadata(df, saved_path)
        metadata["warnings"] = warnings
        logger.info("Upload successful: %s", saved_path.name)
        return jsonify(metadata), 200
    except ValueError as exc:
        logger.warning("Upload validation failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Upload failed")
        return jsonify({"error": f"Upload failed: {exc}"}), 500


@app.route("/process", methods=["POST"])
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
    file_path = config.UPLOAD_FOLDER / filename
    if not file_path.exists():
        return jsonify({"error": f"File '{filename}' not found."}), 404

    try:
        _, summary, output_path = run_etl(file_path)
        logger.info("ETL complete: %s -> %s", filename, output_path.name)
        return jsonify(summary), 200
    except ValueError as exc:
        logger.warning("ETL failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("ETL processing failed")
        return jsonify({"error": f"Processing failed: {exc}"}), 500


@app.route("/insights", methods=["GET"])
def get_insights():  # noqa: ANN201
    """Return full insights for a processed CSV.

    Query param: ``?file=cleaned_...``

    Returns:
        JSON with stats, charts, NLG insights.
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    file_path = config.PROCESSED_FOLDER / filename
    if not file_path.exists():
        return jsonify({"error": f"Processed file '{filename}' not found."}), 404

    try:
        df = load_csv(file_path)
        result = generate_full_insights(df)
        logger.info("Insights generated for %s", filename)
        return jsonify(result), 200
    except Exception as exc:
        logger.exception("Insight generation failed")
        return jsonify({"error": f"Insight generation failed: {exc}"}), 500


@app.route("/download", methods=["GET"])
def download_file():  # noqa: ANN201
    """Download a processed CSV file.

    Query param: ``?file=cleaned_...``
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "Missing 'file' query parameter."}), 400

    file_path = config.PROCESSED_FOLDER / filename
    if not file_path.exists():
        return jsonify({"error": f"File '{filename}' not found."}), 404

    return send_file(str(file_path), as_attachment=True, download_name=filename)


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Starting SmartCSV on %s:%s", config.FLASK_HOST, config.FLASK_PORT)
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
