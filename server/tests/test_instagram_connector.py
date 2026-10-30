"""
Instagram is retired (app/providers.py): connect, callback and analyze answer
410; a stored snapshot can still be read by its owner; nothing reaches an LLM.

Run:  cd server && python -m pytest tests/test_instagram_connector.py -v
"""

from __future__ import annotations

import inspect
import json
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.instagram.router import router as instagram_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000009")

_SAMPLE_PROFILE = {
    "username": "aestheticuser",
    "account_type": "personal",
    "media_count": 120,
    "media_types": {"IMAGE": 80, "VIDEO": 30, "CAROUSEL_ALBUM": 10},
    "recent_count": 25,
    "avg_caption_length": 95.0,
    "posts_per_week": 2.5,
    "top_hashtags": ["art", "photography", "travel"],
    "avg_likes": 210.5,
    "avg_comments": 12.3,
    "total_likes": 5262,
    "total_comments": 307,
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(instagram_router, prefix="/api/instagram")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


class TestInstagramProfile:
    """GET /instagram/profile"""

    def test_returns_profile_when_data_is_json_string(self):
        conn = FakeConn(fetchrow_results=[{"instagram_data": json.dumps(_SAMPLE_PROFILE)}])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/instagram/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "aestheticuser"
        assert data["media_types"]["IMAGE"] == 80

    def test_returns_profile_when_data_is_dict(self):
        """instagram_data may arrive as a dict (asyncpg JSONB auto-decodes)."""
        conn = FakeConn(fetchrow_results=[{"instagram_data": _SAMPLE_PROFILE}])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/instagram/profile")
        assert resp.status_code == 200
        assert resp.json()["username"] == "aestheticuser"

    def test_returns_null_when_no_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/instagram/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_row_has_null_data(self):
        conn = FakeConn(fetchrow_results=[{"instagram_data": None}])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/instagram/profile")
        assert resp.status_code == 200
        assert resp.json() is None


class TestRetired:
    @pytest.mark.parametrize("path", ["/api/instagram/connect", "/api/instagram/callback", "/api/instagram/analyze"])
    def test_answers_410_retired(self, path):
        resp = TestClient(_make_app()).get(path)
        assert resp.status_code == 410
        assert resp.json()["detail"]["code"] == "retired"
        assert "Business and Creator" in resp.json()["detail"]["message"]

    def test_never_reaches_an_llm(self):
        from app.connectors import router as connectors
        from app.oracle import service, trigger
        from app.portrait import stitcher

        assert "instagram_data" not in connectors._DATA_COLUMNS
        assert "instagram" not in trigger._PROVIDER_COLUMNS
        assert "instagram" not in stitcher.ai_columns(stitcher.PROVIDER_COLUMNS)
        assert 'name="instagram"' not in inspect.getsource(service)
