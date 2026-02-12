# ── Build stage ──────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Production stage ─────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p uploads processed logs

# Environment
ENV PORT=5000 \
    FLASK_DEBUG=false \
    UPLOAD_FOLDER=/app/uploads \
    PROCESSED_FOLDER=/app/processed \
    LOG_FOLDER=/app/logs

EXPOSE 5000

# Run with Gunicorn in production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
