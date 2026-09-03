"""
SmartCSV – Security Middleware & HTTP Hardening.

Applies Content-Security-Policy, security headers, and other protections.
"""

from __future__ import annotations

from flask import Flask, Response


def apply_security_headers(app: Flask) -> None:
    """Register an ``after_request`` hook that sets security headers.

    Headers applied:
    - Content-Security-Policy (CSP)
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    - Strict-Transport-Security (HSTS)
    """

    @app.after_request
    def _set_headers(response: Response) -> Response:
        # Content Security Policy — allow CDN for Chart.js and Axios,
        # Google Fonts for typography, and inline styles for dynamic UI.
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Prevent MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent framing (clickjacking)
        response.headers["X-Frame-Options"] = "DENY"

        # XSS filter (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # HSTS (only effective over HTTPS)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        return response
