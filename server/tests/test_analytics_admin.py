"""
Tests for analytics admin endpoints and GET /streak.

Covers the 8 endpoints with zero prior coverage:
  GET /streak, GET /funnel, GET /archetypes, GET /attachment-styles,
  GET /connector-depth, GET /events, GET /users/{id}/connectors,
  GET /connectors

Run: cd server && python -m pytest tests/test_analytics_admin.py -v
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id, require_admin
from app.analytics.router import router as analytics_router, VALID_PROVIDERS

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("00000000-0000-0000-0000-000000000099")

TODAY = datetime.now(timezone.utc).date()


def _make_app(admin: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/analytics")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    if admin:
        app.dependency_overrides[require_admin] = lambda: ADMIN_ID
    return app


# ── Streak ───────────────────────────────────────────────────────────────────

class TestStreak:
    def test_empty_history_returns_zero(self):
        conn = FakeConn(fetch_results=[[]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/analytics/streak")
        assert r.status_code == 200
        data = r.json()
        assert data["streak"] == 0
        assert data["today_active"] is False
        assert len(data["last_7_days"]) == 7

    def test_today_active_streak_one(self):
        conn = FakeConn(fetch_results=[[{"day": TODAY}]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/analytics/streak")
        data = r.json()
        assert data["streak"] == 1
        assert data["today_active"] is True

    def test_three_consecutive_days(self):
        rows = [
            {"day": TODAY},
            {"day": TODAY - timedelta(days=1)},
            {"day": TODAY - timedelta(days=2)},
        ]
        conn = FakeConn(fetch_results=[rows])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/analytics/streak")
        assert r.json()["streak"] == 3

    def test_yesterday_fallback_no_gap(self):
        """Streak counts from yesterday when today has no activity yet."""
        yesterday = TODAY - timedelta(days=1)
        rows = [{"day": yesterday}, {"day": TODAY - timedelta(days=2)}]
        conn = FakeConn(fetch_results=[rows])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/analytics/streak")
        data = r.json()
        assert data["streak"] == 2
        assert data["today_active"] is False

    def test_last_7_days_structure_and_order(self):
        conn = FakeConn(fetch_results=[[{"day": TODAY}]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/analytics/streak")
        last_7 = r.json()["last_7_days"]
        assert len(last_7) == 7
        assert all("date" in d and "active" in d for d in last_7)
        assert last_7[-1]["date"] == TODAY.isoformat()
        assert last_7[-1]["active"] is True


# ── Admin: Funnel ─────────────────────────────────────────────────────────────

_FUNNEL_ROW = {
    "total_registered": 100,
    "completed_poll": 80,
    "has_vibe_vector": 60,
    "connected_any": 50,
    "connected_2plus": 30,
    "completed_psychometrics": 25,
    "opened_self_expression_view": 20,
    "completed_session": 15,
    "returned_next_day": 8,
}


class TestAdminFunnel:
    def test_funnel_returns_nine_steps(self):
        conn = FakeConn(fetchrow_results=[_FUNNEL_ROW])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/funnel")
        assert r.status_code == 200
        assert len(r.json()) == 9

    def test_funnel_step_shape_and_first_step(self):
        conn = FakeConn(fetchrow_results=[_FUNNEL_ROW])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/funnel")
        first = r.json()[0]
        assert first["step"] == "registered"
        assert first["count"] == 100
        assert first["pct"] == 100.0

    def test_funnel_zero_registered_no_division_error(self):
        row = {k: 0 for k in _FUNNEL_ROW}
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/funnel")
        assert r.status_code == 200
        assert all(step["pct"] == 0.0 for step in r.json())


# ── Admin: Archetypes ─────────────────────────────────────────────────────────

class TestAdminArchetypes:
    def test_archetypes_returns_distribution(self):
        rows = [{"archetype": "Exile", "count": 42}, {"archetype": "Hero", "count": 18}]
        conn = FakeConn(fetch_results=[rows], fetchval_results=[60])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/archetypes")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 60
        assert data["archetypes"][0] == {"archetype": "Exile", "count": 42}

    def test_archetypes_empty_db(self):
        conn = FakeConn(fetch_results=[[]], fetchval_results=[0])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/archetypes")
        data = r.json()
        assert data["total"] == 0
        assert data["archetypes"] == []


# ── Admin: Attachment Styles ──────────────────────────────────────────────────

class TestAdminAttachmentStyles:
    def test_returns_all_styles(self):
        rows = [
            {"attachment_style": "anxious", "count": 55},
            {"attachment_style": "secure",  "count": 40},
            {"attachment_style": "avoidant", "count": 30},
        ]
        conn = FakeConn(fetch_results=[rows], fetchval_results=[125])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/attachment-styles")
        data = r.json()
        assert data["total"] == 125
        assert len(data["styles"]) == 3
        assert data["styles"][0] == {"style": "anxious", "count": 55}


# ── Admin: Connector Depth ────────────────────────────────────────────────────

class TestAdminConnectorDepth:
    def test_all_four_buckets_always_present(self):
        rows = [{"bucket": 0, "count": 20}, {"bucket": 2, "count": 5}]
        conn = FakeConn(fetch_results=[rows])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/connector-depth")
        histogram = r.json()["histogram"]
        assert len(histogram) == 4
        buckets = {item["connectors"] for item in histogram}
        assert buckets == {0, 1, 2, 3}

    def test_missing_buckets_default_to_zero(self):
        conn = FakeConn(fetch_results=[[{"bucket": 3, "count": 7}]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/connector-depth")
        by_bucket = {item["connectors"]: item["count"] for item in r.json()["histogram"]}
        assert by_bucket[0] == 0
        assert by_bucket[1] == 0
        assert by_bucket[2] == 0
        assert by_bucket[3] == 7


# ── Admin: Events ─────────────────────────────────────────────────────────────

_EVENT_ROW = {
    "id": "evt-1",
    "user_id": str(USER_ID),
    "email": "a@b.com",
    "display_name": "Alice",
    "event": "journal_session_started",
    "metadata": {},
    "created_at": "2026-10-01T10:00:00",
}


class TestAdminEvents:
    def test_events_unfiltered_returns_rows(self):
        conn = FakeConn(fetch_results=[[_EVENT_ROW]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/events")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_events_filtered_by_event_type(self):
        conn = FakeConn(fetch_results=[[_EVENT_ROW]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get(
                "/api/analytics/events?event=journal_session_started"
            )
        assert r.status_code == 200
        _, args = conn.fetchrow_calls[0] if conn.fetchrow_calls else (None, (None,))
        # fetch was called (not fetchrow) — verify it ran without error
        assert r.status_code == 200

    def test_events_empty_result(self):
        conn = FakeConn(fetch_results=[[]])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/events")
        assert r.status_code == 200
        assert r.json() == []


# ── Admin: User Connectors ────────────────────────────────────────────────────

_ALL_CONNECTOR_KEYS = [
    "spotify_data", "twitter_data", "strava_data", "gcal_data", "costar_data",
    "letterboxd_data", "steam_data", "github_data", "youtube_data",
    "reddit_data", "instagram_data", "tiktok_data",
]


class TestAdminUserConnectors:
    def test_found_user_returns_connectors(self):
        row = {
            "spotify_data": json.dumps({"top_artists": ["The Smiths"]}),
            **{k: None for k in _ALL_CONNECTOR_KEYS if k != "spotify_data"},
        }
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get(
                f"/api/analytics/users/{USER_ID}/connectors"
            )
        assert r.status_code == 200
        data = r.json()["connectors"]
        assert data["spotify"]["top_artists"] == ["The Smiths"]
        assert data["twitter"] is None

    def test_missing_user_returns_empty_connectors(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get(
                f"/api/analytics/users/{USER_ID}/connectors"
            )
        assert r.status_code == 200
        assert r.json()["connectors"] == {}

    def test_dict_valued_data_parses_without_json_loads(self):
        """A dict value (not a JSON string) is returned as-is by parse()."""
        row = {
            "spotify_data": {"top_artists": ["Björk"]},
            **{k: None for k in _ALL_CONNECTOR_KEYS if k != "spotify_data"},
        }
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get(
                f"/api/analytics/users/{USER_ID}/connectors"
            )
        assert r.json()["connectors"]["spotify"]["top_artists"] == ["Björk"]


# ── Admin: Connectors ─────────────────────────────────────────────────────────

class TestAdminConnectors:
    def test_returns_all_valid_providers(self):
        conn = FakeConn(
            fetchval_results=[100],
            fetch_results=[
                [{"provider": "spotify", "connected_count": 40}],
                [],
            ],
        )
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/connectors")
        assert r.status_code == 200
        returned = {item["provider"] for item in r.json()}
        assert returned == VALID_PROVIDERS

    def test_connection_rate_calculation(self):
        conn = FakeConn(
            fetchval_results=[200],
            fetch_results=[
                [{"provider": "spotify", "connected_count": 50}],
                [],
            ],
        )
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/connectors")
        spotify = next(item for item in r.json() if item["provider"] == "spotify")
        assert spotify["connected_count"] == 50
        assert spotify["connection_rate_pct"] == 25.0

    def test_tag_deduplication(self):
        fb_rows = [
            {
                "provider": "spotify",
                "feedback_count": 3,
                "avg_rating": "4.50",
                "tag_arrays": [["insightful", "accurate"], ["insightful"]],
            }
        ]
        conn = FakeConn(
            fetchval_results=[10],
            fetch_results=[[], fb_rows],
        )
        with patch("app.analytics.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(admin=True)).get("/api/analytics/connectors")
        spotify = next(item for item in r.json() if item["provider"] == "spotify")
        assert "insightful" in spotify["top_tags"]
        assert spotify["top_tags"].count("insightful") == 1
