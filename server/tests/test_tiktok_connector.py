"""
Tests for /api/tiktok — profile retrieval, psychoanalysis endpoint,
connect 503, and the _distill_profile pure function.

Covers:
- GET /tiktok/profile: happy path (JSON string + dict), no row, null data
- GET /tiktok/analyze: happy path, prompt content, no data → 404, null data → 404
- GET /tiktok/connect: 503 when not configured
- _distill_profile: video aggregation, hashtag extraction, posting hours, empty input

Run:  cd server && python -m pytest tests/test_tiktok_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.tiktok.router import _distill_profile, router as tiktok_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000010")

_SAMPLE_PROFILE = {
    "display_name": "Creator Name",
    "bio": "Making things happen",
    "is_verified": False,
    "follower_count": 5000,
    "following_count": 300,
    "likes_received": 25000,
    "video_count": 48,
    "recent_video_count": 20,
    "avg_duration_sec": 28.5,
    "avg_likes_per_video": 520.0,
    "avg_comments_per_video": 42.0,
    "avg_shares_per_video": 18.0,
    "avg_views_per_video": 4800.0,
    "top_hashtags": ["fyp", "dance", "trending"],
    "posting_hours": {"14": 5, "20": 8, "22": 4},
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(tiktok_router, prefix="/api/tiktok")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


class TestTikTokProfile:
    """GET /tiktok/profile"""

    def test_returns_profile_when_data_is_json_string(self):
        conn = FakeConn(fetchrow_results=[{"tiktok_data": json.dumps(_SAMPLE_PROFILE)}])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/tiktok/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "Creator Name"
        assert data["follower_count"] == 5000

    def test_returns_profile_when_data_is_dict(self):
        """tiktok_data may arrive as a dict (asyncpg JSONB auto-decodes)."""
        conn = FakeConn(fetchrow_results=[{"tiktok_data": _SAMPLE_PROFILE}])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/tiktok/profile")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Creator Name"

    def test_returns_null_when_no_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/tiktok/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_row_has_null_data(self):
        conn = FakeConn(fetchrow_results=[{"tiktok_data": None}])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/tiktok/profile")
        assert resp.status_code == 200
        assert resp.json() is None


class TestTikTokAnalyze:
    """GET /tiktok/analyze"""

    def test_returns_narrative_for_connected_user(self):
        conn = FakeConn(fetchrow_results=[{"tiktok_data": json.dumps(_SAMPLE_PROFILE)}])
        mock_narrative = "The algorithm shaped you before you shaped your content."
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)), \
             patch("app.tiktok.router.get_settings", return_value=MagicMock()), \
             patch("app.tiktok.router.chat_completion", new=AsyncMock(return_value=mock_narrative)):
            resp = TestClient(_make_app()).get("/api/tiktok/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == mock_narrative

    def test_chat_completion_called_with_dopamine_prompt(self):
        """The LLM prompt must reference key TikTok behavioral metrics."""
        conn = FakeConn(fetchrow_results=[{"tiktok_data": json.dumps(_SAMPLE_PROFILE)}])
        captured: list[str] = []

        async def _capture(prompt: str) -> str:
            captured.append(prompt)
            return "ok"

        with patch("app.tiktok.router.get_conn", make_get_conn(conn)), \
             patch("app.tiktok.router.get_settings", return_value=MagicMock()), \
             patch("app.tiktok.router.chat_completion", side_effect=_capture):
            TestClient(_make_app()).get("/api/tiktok/analyze")

        assert captured, "chat_completion was not called"
        prompt = captured[0]
        assert "Creator Name" in prompt
        assert "5000" in prompt  # follower_count

    def test_404_when_no_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)), \
             patch("app.tiktok.router.get_settings", return_value=MagicMock()), \
             patch("app.tiktok.router.chat_completion", new=AsyncMock(return_value="x")):
            resp = TestClient(_make_app()).get("/api/tiktok/analyze")
        assert resp.status_code == 404

    def test_404_when_row_has_null_data(self):
        conn = FakeConn(fetchrow_results=[{"tiktok_data": None}])
        with patch("app.tiktok.router.get_conn", make_get_conn(conn)), \
             patch("app.tiktok.router.get_settings", return_value=MagicMock()), \
             patch("app.tiktok.router.chat_completion", new=AsyncMock(return_value="x")):
            resp = TestClient(_make_app()).get("/api/tiktok/analyze")
        assert resp.status_code == 404


class TestTikTokConnect:
    """GET /tiktok/connect"""

    def test_503_when_not_configured(self):
        settings = MagicMock()
        settings.tiktok_client_key = None
        with patch("app.tiktok.router.get_settings", return_value=settings):
            resp = TestClient(_make_app()).get("/api/tiktok/connect")
        assert resp.status_code == 503


class TestDistillTikTokProfile:
    """_distill_profile — pure function, no mocking required."""

    def _make_video(
        self,
        duration: int = 30,
        like_count: int = 100,
        comment_count: int = 5,
        share_count: int = 10,
        view_count: int = 1000,
        description: str = "check this out #fyp",
        create_time: int = 1704067200,  # 2024-01-01 00:00:00 UTC → hour 0
    ) -> dict:
        return {
            "duration": duration,
            "like_count": like_count,
            "comment_count": comment_count,
            "share_count": share_count,
            "view_count": view_count,
            "video_description": description,
            "create_time": create_time,
        }

    def test_aggregates_video_engagement(self):
        user = {
            "display_name": "Test Creator",
            "bio_description": "bio",
            "follower_count": 1000,
            "following_count": 200,
            "likes_count": 5000,
            "video_count": 30,
            "is_verified": False,
        }
        videos = [
            self._make_video(like_count=200, comment_count=10, share_count=20, view_count=2000),
            self._make_video(like_count=100, comment_count=5, share_count=10, view_count=1000),
        ]
        result = _distill_profile(user, videos)
        assert result["display_name"] == "Test Creator"
        assert result["follower_count"] == 1000
        assert result["avg_likes_per_video"] == pytest.approx(150.0)
        assert result["avg_comments_per_video"] == pytest.approx(7.5)
        assert result["avg_shares_per_video"] == pytest.approx(15.0)
        assert result["avg_views_per_video"] == pytest.approx(1500.0)

    def test_extracts_hashtags_from_descriptions(self):
        videos = [
            self._make_video(description="dance video #fyp #dance"),
            self._make_video(description="cook at home #cooking #fyp"),
        ]
        result = _distill_profile({}, videos)
        assert "fyp" in result["top_hashtags"]
        assert "dance" in result["top_hashtags"]
        assert "cooking" in result["top_hashtags"]

    def test_avg_duration_computed(self):
        videos = [
            self._make_video(duration=20),
            self._make_video(duration=40),
        ]
        result = _distill_profile({}, videos)
        assert result["avg_duration_sec"] == pytest.approx(30.0)

    def test_posting_hours_extracted_from_create_time(self):
        # 1704067200 = 2024-01-01 00:00:00 UTC → hour 0
        # 1704110400 = 2024-01-01 12:00:00 UTC → hour 12
        videos = [
            self._make_video(create_time=1704067200),
            self._make_video(create_time=1704110400),
        ]
        result = _distill_profile({}, videos)
        assert "0" in result["posting_hours"]
        assert "12" in result["posting_hours"]

    def test_empty_videos_returns_zero_defaults(self):
        result = _distill_profile({"display_name": "Empty"}, [])
        assert result["display_name"] == "Empty"
        assert result["recent_video_count"] == 0
        assert result["avg_likes_per_video"] == 0
        assert result["top_hashtags"] == []
        assert result["posting_hours"] == {}
