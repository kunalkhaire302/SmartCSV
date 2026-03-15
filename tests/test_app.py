"""
SmartCSV – Comprehensive Test Suite.

Tests cover:
- Storage abstraction (LocalStorage)
- File handler (save/load)
- ETL pipeline
- Auth decorators
- API endpoints (upload, process, insights, download)
- Quotas
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Set test env before importing app
os.environ["STORAGE_BACKEND"] = "local"
os.environ["FLASK_DEBUG"] = "false"


@pytest.fixture
def app():
    """Create test Flask application."""
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_csv() -> bytes:
    """Generate a sample CSV as bytes."""
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "age": [25, 30, 35, 40, 45],
        "salary": [50000, 60000, 70000, 80000, 90000],
        "department": ["Engineering", "Marketing", "Engineering", "Sales", "Marketing"],
    })
    return df.to_csv(index=False).encode("utf-8")


# ═══════════════════════════════════════════════════════════════════════
#  Storage Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLocalStorage:
    """Test LocalStorage backend."""

    def test_save_and_load(self, tmp_path):
        """Save and load bytes through LocalStorage."""
        import config
        original_root = config.ROOT_STORAGE
        config.ROOT_STORAGE = tmp_path

        # Re-import to reset singleton
        from utils.storage import LocalStorage
        storage = LocalStorage()

        data = b"hello,world\n1,2\n3,4"
        key = "test/data.csv"
        storage.save(key, data)

        assert storage.exists(key)
        loaded = storage.load(key)
        assert loaded == data

        config.ROOT_STORAGE = original_root

    def test_delete(self, tmp_path):
        """Delete a key."""
        import config
        original_root = config.ROOT_STORAGE
        config.ROOT_STORAGE = tmp_path

        from utils.storage import LocalStorage
        storage = LocalStorage()

        storage.save("test/delete_me.csv", b"data")
        assert storage.exists("test/delete_me.csv")

        storage.delete("test/delete_me.csv")
        assert not storage.exists("test/delete_me.csv")

        config.ROOT_STORAGE = original_root

    def test_load_nonexistent_raises(self, tmp_path):
        """Loading a nonexistent key raises FileNotFoundError."""
        import config
        original_root = config.ROOT_STORAGE
        config.ROOT_STORAGE = tmp_path

        from utils.storage import LocalStorage
        storage = LocalStorage()

        with pytest.raises(FileNotFoundError):
            storage.load("nonexistent/file.csv")

        config.ROOT_STORAGE = original_root


# ═══════════════════════════════════════════════════════════════════════
#  File Handler Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFileHandler:
    """Test file handler utilities."""

    def test_sanitize_filename(self):
        """Filenames are sanitized."""
        from utils.file_handler import _sanitize_filename
        assert _sanitize_filename("my file (1).csv") == "my_file__1_.csv"
        assert _sanitize_filename("data.csv") == "data.csv"

    def test_generate_unique_filename(self):
        """Generated filenames are unique and contain timestamp."""
        from utils.file_handler import generate_unique_filename
        name1 = generate_unique_filename("test.csv")
        name2 = generate_unique_filename("test.csv")
        assert name1 != name2
        assert name1.endswith("_test.csv")

    def test_detect_encoding(self):
        """Encoding detection works for UTF-8."""
        from utils.file_handler import detect_encoding
        data = "name,age\nAlice,25\n".encode("utf-8")
        enc = detect_encoding(data)
        assert enc.lower() in ("utf-8", "ascii")


# ═══════════════════════════════════════════════════════════════════════
#  ETL Tests
# ═══════════════════════════════════════════════════════════════════════

class TestETLPipeline:
    """Test ETL pipeline."""

    def test_pipeline_removes_duplicates(self):
        """ETL pipeline removes duplicate rows."""
        from etl import ETLPipeline
        df = pd.DataFrame({"a": [1, 1, 2, 3], "b": ["x", "x", "y", "z"]})
        pipeline = ETLPipeline(df)
        cleaned = pipeline.run()
        assert len(cleaned) == 3

    def test_pipeline_summary(self):
        """ETL pipeline returns a summary."""
        from etl import ETLPipeline
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        pipeline = ETLPipeline(df)
        pipeline.run()
        summary = pipeline.get_summary()
        assert "transformations_applied" in summary
        assert "rows_after" in summary


# ═══════════════════════════════════════════════════════════════════════
#  API Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPublicEndpoints:
    """Test public (unauthenticated) endpoints."""

    def test_index_returns_200(self, client):
        """GET / returns 200."""
        r = client.get("/")
        assert r.status_code == 200

    def test_landing_returns_200(self, client):
        """GET /landing returns 200."""
        r = client.get("/landing")
        assert r.status_code == 200

    def test_auth_login_without_config(self, client):
        """POST /auth/login returns 503 without Supabase config."""
        r = client.post("/auth/login", json={"email": "test@test.com", "password": "123"})
        assert r.status_code == 503


class TestProtectedEndpoints:
    """Test protected endpoints return 401 without auth."""

    def test_upload_requires_auth(self, client):
        r = client.post("/upload")
        assert r.status_code == 401

    def test_process_requires_auth(self, client):
        r = client.post("/process")
        assert r.status_code == 401

    def test_insights_requires_auth(self, client):
        r = client.get("/insights")
        assert r.status_code == 401

    def test_download_requires_auth(self, client):
        r = client.get("/download")
        assert r.status_code == 401

    def test_chat_requires_auth(self, client):
        r = client.post("/chat")
        assert r.status_code == 401

    def test_uploads_requires_auth(self, client):
        r = client.get("/uploads")
        assert r.status_code == 401

    def test_share_requires_auth(self, client):
        r = client.post("/share")
        assert r.status_code == 401

    def test_shares_requires_auth(self, client):
        r = client.get("/shares")
        assert r.status_code == 401

    def test_api_keys_requires_auth(self, client):
        r = client.post("/api-keys")
        assert r.status_code == 401

    def test_billing_requires_auth(self, client):
        r = client.post("/billing/checkout")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
#  Validator Tests
# ═══════════════════════════════════════════════════════════════════════

class TestValidators:
    """Test CSV validators."""

    def test_validate_csv_empty(self):
        """Empty DataFrame raises ValueError."""
        from utils.validators import validate_csv
        with pytest.raises(ValueError, match="empty"):
            validate_csv(pd.DataFrame())

    def test_validate_csv_with_duplicates(self):
        """Validator detects duplicates."""
        from utils.validators import validate_csv
        df = pd.DataFrame({"a": [1, 1, 2], "b": [3, 3, 4]})
        warnings = validate_csv(df)
        assert any("duplicate" in w.lower() for w in warnings)

    def test_get_upload_metadata(self):
        """Metadata is computed correctly."""
        from utils.validators import get_upload_metadata
        df = pd.DataFrame({"x": [1, 2], "y": ["a", "b"]})
        meta = get_upload_metadata(df, "uploads/test.csv", 100)
        assert meta["filename"] == "test.csv"
        assert meta["row_count"] == 2
        assert meta["column_count"] == 2
        assert meta["size_kb"] == pytest.approx(0.1, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════
#  Quota Tests
# ═══════════════════════════════════════════════════════════════════════

class TestQuotas:
    """Test quota system."""

    def test_plan_limits(self):
        """Plan limits are defined correctly."""
        from utils.quotas import get_limits
        free = get_limits("free")
        assert free["uploads_per_month"] == 10
        pro = get_limits("pro")
        assert pro["uploads_per_month"] == 100
        team = get_limits("team")
        assert team["uploads_per_month"] == 500

    def test_unknown_plan_defaults_to_free(self):
        """Unknown plans default to free limits."""
        from utils.quotas import get_limits
        limits = get_limits("unknown_plan")
        assert limits["uploads_per_month"] == 10
