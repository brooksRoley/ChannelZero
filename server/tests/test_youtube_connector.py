"""
Tests for the YouTube connector: _distill_profile (pure function),
/youtube/profile endpoint, /youtube/analyze endpoint (mocked LLM),
and /youtube/connect 503 guard.

Uses FakeConn from conftest — no real DB or external HTTP calls.

Run:  cd server && python -m pytest tests/test_youtube_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.youtube.router import _distill_profile, router as youtube_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000004")

SAMPLE_CHANNEL = {
    "snippet": {
        "title": "brooks",
        "description": "just here to watch and learn",
        "publishedAt": "2016-05-20T00:00:00Z",
    },
    "statistics": {
        "subscriberCount": "12",
        "videoCount": "3",
        "viewCount": "1450",
    },
}

SAMPLE_SUBSCRIPTIONS = [
    {"snippet": {"title": "Lo-Fi Girl", "description": "chill music beats to relax and study"}},
    {"snippet": {"title": "Two Minute Papers", "description": "science and technology research explained"}},
    {"snippet": {"title": "GDC", "description": "gaming and game development talks"}},
    {"snippet": {"title": "Bon Appetit", "description": "cooking and food recipes"}},
    {"snippet": {"title": "No Description Channel", "description": ""}},
    {"snippet": {"title": ""}},  # empty title — should be skipped from top_subs
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(youtube_router, prefix="/api/youtube")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _distill_profile (pure function) ─────────────────────────────────────────


class TestDistillProfile:
    def test_empty_inputs_return_defaults(self):
        result = _distill_profile({}, [], 0)
        assert result["channel_name"] == ""
        assert result["channel_description"] == ""
        assert result["subscriber_count"] == 0
        assert result["video_count"] == 0
        assert result["view_count"] == 0
        assert result["top_subscriptions"] == []
        assert result["subscription_categories"] == {}
        assert result["total_subscriptions"] == 0
        assert result["liked_videos_count"] == 0
        assert result["subscription_diversity"] == 0

    def test_channel_basics_extracted_from_snippet_and_statistics(self):
        result = _distill_profile(SAMPLE_CHANNEL, [], 0)
        assert result["channel_name"] == "brooks"
        assert result["channel_description"] == "just here to watch and learn"
        assert result["account_created"] == "2016-05-20T00:00:00Z"

    def test_statistics_coerced_to_int(self):
        result = _distill_profile(SAMPLE_CHANNEL, [], 0)
        assert result["subscriber_count"] == 12
        assert isinstance(result["subscriber_count"], int)
        assert result["video_count"] == 3
        assert result["view_count"] == 1450

    def test_top_subscriptions_collects_titles(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 0)
        assert "Lo-Fi Girl" in result["top_subscriptions"]
        assert "Two Minute Papers" in result["top_subscriptions"]

    def test_empty_titles_excluded_from_top_subscriptions(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 0)
        assert "" not in result["top_subscriptions"]
        # 6 subs but one has an empty title → 5 named channels
        assert len(result["top_subscriptions"]) == 5

    def test_subscription_categories_from_description_keywords(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 0)
        cats = result["subscription_categories"]
        assert cats.get("music") == 1
        assert cats.get("science") == 1
        assert cats.get("technology") == 1
        assert cats.get("gaming") == 1
        assert cats.get("cooking") == 1

    def test_total_subscriptions_counts_all_including_empty_title(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 0)
        # total counts the raw list length, not just named channels
        assert result["total_subscriptions"] == 6

    def test_subscription_diversity_equals_named_channel_count(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 0)
        assert result["subscription_diversity"] == len(result["top_subscriptions"])
        assert result["subscription_diversity"] == 5

    def test_liked_count_passed_through(self):
        result = _distill_profile(SAMPLE_CHANNEL, SAMPLE_SUBSCRIPTIONS, 37)
        assert result["liked_videos_count"] == 37

    def test_top_subscriptions_capped_at_twenty(self):
        many = [
            {"snippet": {"title": f"Channel{i}", "description": ""}} for i in range(30)
        ]
        result = _distill_profile(SAMPLE_CHANNEL, many, 0)
        assert len(result["top_subscriptions"]) == 20
        # total still reflects the full list
        assert result["total_subscriptions"] == 30

    def test_long_description_truncated_to_500_chars(self):
        channel = {"snippet": {"title": "x", "description": "a" * 800}, "statistics": {}}
        result = _distill_profile(channel, [], 0)
        assert len(result["channel_description"]) == 500

    def test_missing_snippet_and_statistics_are_safe(self):
        result = _distill_profile({"snippet": {}, "statistics": {}}, [], 0)
        assert result["channel_name"] == ""
        assert result["subscriber_count"] == 0


# ── /youtube/profile endpoint ─────────────────────────────────────────────────


class TestYoutubeProfileEndpoint:
    def test_returns_null_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_youtube_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"youtube_data": None}])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_parsed_dict_when_data_is_json_string(self):
        stored = json.dumps({"channel_name": "brooks", "total_subscriptions": 6})
        conn = FakeConn(fetchrow_results=[{"youtube_data": stored}])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["channel_name"] == "brooks"
        assert body["total_subscriptions"] == 6

    def test_returns_dict_passthrough_when_already_dict(self):
        stored = {"channel_name": "brooks", "liked_videos_count": 37}
        conn = FakeConn(fetchrow_results=[{"youtube_data": stored}])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/profile")
        assert resp.status_code == 200
        assert resp.json()["liked_videos_count"] == 37


# ── /youtube/analyze endpoint ─────────────────────────────────────────────────


class TestYoutubeAnalyzeEndpoint:
    def test_404_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/analyze")
        assert resp.status_code == 404

    def test_404_when_youtube_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"youtube_data": None}])
        app = _make_app()
        with patch("app.youtube.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/youtube/analyze")
        assert resp.status_code == 404

    def test_200_with_narrative_when_data_is_json_string(self):
        stored = json.dumps({
            "channel_name": "brooks",
            "channel_description": "just here to watch",
            "subscriber_count": 12,
            "video_count": 3,
            "view_count": 1450,
            "top_subscriptions": ["Lo-Fi Girl", "Two Minute Papers"],
            "subscription_categories": {"music": 1, "science": 1},
            "total_subscriptions": 6,
            "liked_videos_count": 37,
            "subscription_diversity": 5,
        })
        conn = FakeConn(fetchrow_results=[{"youtube_data": stored}])
        app = _make_app()
        with (
            patch("app.youtube.router.get_conn", make_get_conn(conn)),
            patch(
                "app.youtube.router.chat_completion",
                new=AsyncMock(return_value="You watch to become who you are not yet."),
            ),
        ):
            resp = TestClient(app).get("/api/youtube/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "You watch to become who you are not yet."

    def test_200_with_narrative_when_data_already_dict(self):
        stored = {
            "channel_name": "brooks",
            "top_subscriptions": ["GDC"],
            "subscription_categories": {"gaming": 1},
        }
        conn = FakeConn(fetchrow_results=[{"youtube_data": stored}])
        app = _make_app()
        with (
            patch("app.youtube.router.get_conn", make_get_conn(conn)),
            patch(
                "app.youtube.router.chat_completion",
                new=AsyncMock(return_value="Your attention orbits the makers."),
            ),
        ):
            resp = TestClient(app).get("/api/youtube/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "Your attention orbits the makers."

    def test_analyze_passes_profile_signal_into_llm_prompt(self):
        stored = {"channel_name": "brooks", "top_subscriptions": ["Lo-Fi Girl"]}
        conn = FakeConn(fetchrow_results=[{"youtube_data": stored}])
        app = _make_app()
        llm = AsyncMock(return_value="ok")
        with (
            patch("app.youtube.router.get_conn", make_get_conn(conn)),
            patch("app.youtube.router.chat_completion", new=llm),
        ):
            resp = TestClient(app).get("/api/youtube/analyze")
        assert resp.status_code == 200
        prompt = llm.call_args.args[0]
        assert "Lo-Fi Girl" in prompt
        assert "brooks" in prompt


# ── /youtube/connect 503 guard ────────────────────────────────────────────────


class TestYoutubeConnectEndpoint:
    def test_503_when_google_client_id_not_configured(self):
        """Missing GOOGLE_CLIENT_ID → 503 before any token exchange or DB call."""
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            mock_settings.return_value.google_client_id = None
            resp = TestClient(app).get("/api/youtube/connect")
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "not_configured"

    def test_connect_returns_auth_url_when_configured(self):
        """Configured client id → returns a Google auth URL for the frontend."""
        app = _make_app()
        with (
            patch("app.oauth_base.get_settings") as mock_settings,
            patch("app.oauth_base.make_oauth_state", return_value="state-token"),
        ):
            s = mock_settings.return_value
            s.google_client_id = "client-123"
            s.youtube_redirect_uri = "https://channelzero.onrender.com/api/youtube/callback"
            resp = TestClient(app).get("/api/youtube/connect")
        assert resp.status_code == 200
        auth_url = resp.json()["auth_url"]
        assert auth_url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=client-123" in auth_url
        assert "state=state-token" in auth_url
