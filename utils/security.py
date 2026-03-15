"""
Security middleware and hardening utilities.
"""

from __future__ import annotations

from flask import Flask


def apply_security_headers(app: Flask) -> None:
    """Add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security (when not debug)
    - Content-Security-Policy (basic)
    - Referrer-Policy: strict-origin-when-cross-origin
    """

    @app.after_request
    def set_security_headers(response):  # noqa: ANN001, ANN201
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Basic CSP — allow self + Google Fonts + inline styles (for templates)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )

        return response


def apply_request_validation(app: Flask) -> None:
    """Add request validation middleware.

    - Rejects excessively large headers
    - Logs suspicious requests
    """
    from utils.logger import get_logger
    logger = get_logger("security")

    @app.before_request
    def validate_request():  # noqa: ANN201
        from flask import request

        # Check for oversized headers (potential header injection)
        total_header_size = sum(
            len(k) + len(v) for k, v in request.headers
        )
        if total_header_size > 16384:  # 16 KB
            logger.warning(
                "Oversized headers from %s (%d bytes)",
                request.remote_addr,
                total_header_size,
            )
            from flask import jsonify
            return jsonify({"error": "Request headers too large."}), 431
