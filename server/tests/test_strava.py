"""
Tests for /api/strava — retired 2026-10-30 (app/providers.py).

Covers:
- GET /strava/profile: the user's own stored snapshot (JSON string + dict), no row, null data
- connect / callback / sync / analyze: 410 {code: retired}
- Strava data never reaches an LLM: connector availability, correlations,
  portrait, Oracle trigger and prompt

Run:  cd server && python -m pytest tests/test_strava.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.strava.router import router as strava_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000002")

_SAMPLE_PROFILE = {
    "athlete_name": "Test Runner",
    "activity_types": {"Run": 20, "Ride": 5},
    "recent_count": 25,
    "total_elevation_m": 1500.0,
    "total_distance_km": 300.0,
    "total_moving_hours": 24.0,
    "avg_heartrate": 142.0,
    "max_heartrate": 178.0,
    "all_time_runs": 200,
    "all_time_run_distance_km": 1200.0,
    "all_time_rides": 30,
    "all_time_ride_distance_km": 600.0,
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(strava_router, prefix="/api/strava")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


class TestStravaProfile:
    """GET /strava/profile"""

    def test_returns_profile_when_data_is_json_string(self):
        conn = FakeConn(fetchrow_results=[{"strava_data": json.dumps(_SAMPLE_PROFILE)}])
        with patch("app.strava.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/strava/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["athlete_name"] == "Test Runner"
        assert data["activity_types"]["Run"] == 20

    def test_returns_profile_when_data_is_dict(self):
        """strava_data may arrive as a dict (asyncpg JSONB auto-decodes)."""
        conn = FakeConn(fetchrow_results=[{"strava_data": _SAMPLE_PROFILE}])
        with patch("app.strava.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/strava/profile")
        assert resp.status_code == 200
        assert resp.json()["athlete_name"] == "Test Runner"

    def test_returns_null_when_no_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.strava.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/strava/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_row_has_null_data(self):
        conn = FakeConn(fetchrow_results=[{"strava_data": None}])
        with patch("app.strava.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/strava/profile")
        assert resp.status_code == 200
        assert resp.json() is None


class TestRetired:
    """Every path that connects, fetches or narrates answers 410 retired."""

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/strava/connect"),
        ("get", "/api/strava/callback?code=c&state=s"),
        ("post", "/api/strava/sync"),
        ("get", "/api/strava/analyze"),
    ])
    def test_answers_410_retired(self, method, path):
        resp = getattr(TestClient(_make_app()), method)(path)
        assert resp.status_code == 410
        assert resp.json()["detail"]["code"] == "retired"
        assert "AI use" in resp.json()["detail"]["message"]


class TestNeverReachesAnLLM:
    """API Policy §5.3: no Strava data in any model's context."""

    def test_marked_unavailable(self):
        from app.connectors.router import get_available_connectors
        import asyncio
        out = asyncio.run(get_available_connectors())
        assert out["providers"]["strava"] is False

    def test_correlations_never_read_it(self):
        from app.connectors.router import _DATA_COLUMNS
        assert "strava_data" not in _DATA_COLUMNS
        assert "spotify_data" in _DATA_COLUMNS

    def test_portrait_never_reads_it(self):
        from app.portrait.stitcher import connected_providers
        row = {"strava_data": json.dumps(_SAMPLE_PROFILE), "spotify_data": json.dumps({"top_genres": ["x"]})}
        assert set(connected_providers(row)) == {"spotify"}

    def test_oracle_prompt_has_no_strava(self):
        import inspect
        from app.oracle import service, trigger
        assert "data.strava" not in inspect.getsource(service)
        assert '_parse(row["strava_data"])' not in inspect.getsource(trigger)
