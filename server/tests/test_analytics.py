"""
Tests for analytics router — event allowlist, provider validation, and rate limiting.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

import json
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from app.auth.deps import get_current_user_id
from app.analytics.router import router as analytics_router, VALID_EVENTS, VALID_PROVIDERS
from app.ratelimit import limiter
from app.main import _rate_limit_exceeded_handler

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/analytics")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return app


def _client_with(conn: FakeConn) -> TestClient:
    app = _make_app()
    with patch("app.analytics.router.get_conn", make_get_conn(conn)):
        return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def reset_limiter():
    """Clear in-memory rate-limit counters before each test."""
    limiter._storage.reset()
    yield


# ── Event allowlist ──────────────────────────────────────────────────────────

class TestEventAllowlist:
    def test_valid_event_returns_204(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post("/api/analytics/event", json={"event": "journal_session_started"})
        assert r.status_code == 204
        assert len(conn.execute_calls) == 1

    def test_invalid_event_returns_400(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post("/api/analytics/event", json={"event": "drop_table_users"})
        assert r.status_code == 400
        assert "Unknown event" in r.json()["detail"]
        assert len(conn.execute_calls) == 0

    def test_empty_event_string_returns_400(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post("/api/analytics/event", json={"event": ""})
        assert r.status_code == 400

    def test_all_valid_events_accepted(self):
        """Every event in VALID_EVENTS returns 204 — no valid event is broken."""
        for event in VALID_EVENTS:
            conn = FakeConn()
            with patch("app.analytics.router.get_conn", make_get_conn(conn)):
                client = TestClient(_make_app())
                r = client.post("/api/analytics/event", json={"event": event})
            assert r.status_code == 204, f"Expected 204 for event={event!r}, got {r.status_code}"

    def test_valid_event_with_metadata_accepted(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/event",
                json={"event": "connected_any", "metadata": {"provider": "spotify"}},
            )
        assert r.status_code == 204
        _, args = conn.execute_calls[0]
        stored_meta = json.loads(args[2])
        assert stored_meta["provider"] == "spotify"

    def test_practice_completed_counts_toward_streak_and_funnel(self):
        """Spiral/audio/trance completions must feed the streak + completed_session funnel."""
        from app.analytics.router import SELF_EXPRESSION_COMPLETED, SELF_EXPRESSION_EVENTS
        assert "practice_completed" in VALID_EVENTS
        assert "practice_completed" in SELF_EXPRESSION_COMPLETED
        assert "practice_completed" in SELF_EXPRESSION_EVENTS


# ── Provider allowlist ───────────────────────────────────────────────────────

class TestProviderAllowlist:
    def test_original_providers_still_valid(self):
        for provider in ("spotify", "twitter", "google", "strava", "steam", "letterboxd", "costar"):
            assert provider in VALID_PROVIDERS, f"{provider} missing from VALID_PROVIDERS"

    def test_new_providers_now_valid(self):
        for provider in ("github", "reddit", "youtube"):
            assert provider in VALID_PROVIDERS, f"{provider} missing from VALID_PROVIDERS — stale allowlist"

    def test_invalid_provider_returns_400(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/feedback/connector",
                json={"provider": "linkedin", "rating": 4},
            )
        assert r.status_code == 400
        assert "Unknown provider" in r.json()["detail"]

    def test_github_provider_feedback_accepted(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/feedback/connector",
                json={"provider": "github", "rating": 5, "tags": ["insightful"]},
            )
        assert r.status_code == 204

    def test_reddit_provider_feedback_accepted(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/feedback/connector",
                json={"provider": "reddit", "rating": 3},
            )
        assert r.status_code == 204

    def test_youtube_provider_feedback_accepted(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/feedback/connector",
                json={"provider": "youtube", "rating": 4},
            )
        assert r.status_code == 204

    def test_rating_out_of_range_returns_400(self):
        conn = FakeConn()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            r = client.post(
                "/api/analytics/feedback/connector",
                json={"provider": "spotify", "rating": 6},
            )
        assert r.status_code == 400


# ── Event rate limiting ──────────────────────────────────────────────────────

class TestEventRateLimit:
    def test_first_event_not_rate_limited(self):
        conn = FakeConn()
        app = _make_app()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(app, raise_server_exceptions=False)
            r = client.post("/api/analytics/event", json={"event": "journal_session_started"})
        assert r.status_code == 204

    def test_61st_event_returns_429(self):
        conn = FakeConn()
        app = _make_app()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(60):
                client.post("/api/analytics/event", json={"event": "journal_session_started"})
            r = client.post("/api/analytics/event", json={"event": "journal_session_started"})
        assert r.status_code == 429

    def test_429_has_retry_after_header(self):
        conn = FakeConn()
        app = _make_app()
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            client = TestClient(app, raise_server_exceptions=False)
            for _ in range(60):
                client.post("/api/analytics/event", json={"event": "journal_session_started"})
            r = client.post("/api/analytics/event", json={"event": "journal_session_started"})
        assert r.status_code == 429
        assert "retry-after" in r.headers or "Retry-After" in r.headers
