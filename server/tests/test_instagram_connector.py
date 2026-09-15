"""
Tests for /api/instagram — profile retrieval, psychoanalysis endpoint,
connect 503, and the _distill_profile pure function.

Covers:
- GET /instagram/profile: happy path (JSON string + dict), no row, null data
- GET /instagram/analyze: happy path, prompt content, no data → 404, null data → 404
- GET /instagram/connect: 503 when not configured
- _distill_profile: media aggregation, hashtag extraction, posting frequency, empty input

Run:  cd server && python -m pytest tests/test_instagram_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.instagram.router import _distill_profile, router as instagram_router

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


class TestInstagramAnalyze:
    """GET /instagram/analyze"""

    def test_returns_narrative_for_connected_user(self):
        conn = FakeConn(fetchrow_results=[{"instagram_data": json.dumps(_SAMPLE_PROFILE)}])
        mock_narrative = "Your grid is a stage you built for yourself."
        with patch("app.instagram.router.get_conn", make_get_conn(conn)), \
             patch("app.instagram.router.get_settings", return_value=MagicMock()), \
             patch("app.instagram.router.chat_completion", new=AsyncMock(return_value=mock_narrative)):
            resp = TestClient(_make_app()).get("/api/instagram/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == mock_narrative

    def test_chat_completion_called_with_aesthetic_prompt(self):
        """The LLM prompt must reference key Instagram metrics."""
        conn = FakeConn(fetchrow_results=[{"instagram_data": json.dumps(_SAMPLE_PROFILE)}])
        captured: list[str] = []

        async def _capture(prompt: str) -> str:
            captured.append(prompt)
            return "ok"

        with patch("app.instagram.router.get_conn", make_get_conn(conn)), \
             patch("app.instagram.router.get_settings", return_value=MagicMock()), \
             patch("app.instagram.router.chat_completion", side_effect=_capture):
            TestClient(_make_app()).get("/api/instagram/analyze")

        assert captured, "chat_completion was not called"
        prompt = captured[0]
        assert "aestheticuser" in prompt
        assert "210" in prompt  # avg_likes

    def test_404_when_no_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)), \
             patch("app.instagram.router.get_settings", return_value=MagicMock()), \
             patch("app.instagram.router.chat_completion", new=AsyncMock(return_value="x")):
            resp = TestClient(_make_app()).get("/api/instagram/analyze")
        assert resp.status_code == 404

    def test_404_when_row_has_null_data(self):
        conn = FakeConn(fetchrow_results=[{"instagram_data": None}])
        with patch("app.instagram.router.get_conn", make_get_conn(conn)), \
             patch("app.instagram.router.get_settings", return_value=MagicMock()), \
             patch("app.instagram.router.chat_completion", new=AsyncMock(return_value="x")):
            resp = TestClient(_make_app()).get("/api/instagram/analyze")
        assert resp.status_code == 404


class TestInstagramConnect:
    """GET /instagram/connect"""

    def test_503_when_not_configured(self):
        settings = MagicMock()
        settings.instagram_client_id = None
        with patch("app.instagram.router.get_settings", return_value=settings):
            resp = TestClient(_make_app()).get("/api/instagram/connect")
        assert resp.status_code == 503


class TestDistillInstagramProfile:
    """_distill_profile — pure function, no mocking required."""

    def _make_media(
        self,
        media_type: str = "IMAGE",
        caption: str = "",
        like_count: int = 100,
        comments_count: int = 5,
        timestamp: str = "2024-06-01T12:00:00Z",
    ) -> dict:
        return {
            "media_type": media_type,
            "caption": caption,
            "like_count": like_count,
            "comments_count": comments_count,
            "timestamp": timestamp,
        }

    def test_aggregates_media_types(self):
        profile_data = {"username": "testuser", "account_type": "personal", "media_count": 50}
        media = [
            self._make_media("IMAGE"),
            self._make_media("IMAGE"),
            self._make_media("VIDEO"),
            self._make_media("CAROUSEL_ALBUM"),
        ]
        result = _distill_profile(profile_data, media)
        assert result["username"] == "testuser"
        assert result["media_types"]["IMAGE"] == 2
        assert result["media_types"]["VIDEO"] == 1
        assert result["media_types"]["CAROUSEL_ALBUM"] == 1
        assert result["recent_count"] == 4
        assert result["media_count"] == 50

    def test_extracts_hashtags_from_captions(self):
        media = [
            self._make_media(caption="golden hour #photography #travel"),
            self._make_media(caption="morning vibes #coffee #photography"),
        ]
        result = _distill_profile({}, media)
        assert "photography" in result["top_hashtags"]
        assert "travel" in result["top_hashtags"]
        assert "coffee" in result["top_hashtags"]

    def test_avg_likes_and_comments(self):
        media = [
            self._make_media(like_count=200, comments_count=10),
            self._make_media(like_count=100, comments_count=20),
        ]
        result = _distill_profile({}, media)
        assert result["avg_likes"] == pytest.approx(150.0)
        assert result["avg_comments"] == pytest.approx(15.0)
        assert result["total_likes"] == 300
        assert result["total_comments"] == 30

    def test_avg_caption_length_computed(self):
        media = [
            self._make_media(caption="a" * 50),
            self._make_media(caption="b" * 100),
        ]
        result = _distill_profile({}, media)
        assert result["avg_caption_length"] == pytest.approx(75.0)

    def test_posts_per_week_from_timestamps(self):
        """Two posts 7 days apart = 2.0 posts/week."""
        media = [
            self._make_media(timestamp="2024-06-01T12:00:00Z"),
            self._make_media(timestamp="2024-06-08T12:00:00Z"),
        ]
        result = _distill_profile({}, media)
        assert result["posts_per_week"] is not None
        assert result["posts_per_week"] == pytest.approx(2.0)

    def test_empty_media_returns_zero_defaults(self):
        result = _distill_profile({"username": "empty", "media_count": 0}, [])
        assert result["username"] == "empty"
        assert result["recent_count"] == 0
        assert result["total_likes"] == 0
        assert result["avg_likes"] == 0.0
        assert result["top_hashtags"] == []
        assert result["posts_per_week"] is None
