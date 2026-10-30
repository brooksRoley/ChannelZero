"""
Tests for the Google Calendar connector.

Run:  cd server && python -m pytest tests/test_gcal_connector.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.gcal.router import router as gcal_router, _distill_profile

from .conftest import FakeConn, make_get_conn

USER_ID = "11111111-1111-1111-1111-111111111111"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(gcal_router, prefix="/api/gcal")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _timed_event(hour: int, recurring: bool = False) -> dict:
    """Build a timed calendar event on 2026-08-21 (Friday) at the given UTC hour."""
    dt = datetime(2026, 8, 21, hour, 0, 0, tzinfo=timezone.utc)
    ev: dict = {"start": {"dateTime": dt.isoformat()}}
    if recurring:
        ev["recurringEventId"] = "rec_001"
    return ev


def _all_day_event() -> dict:
    return {"start": {"date": "2026-08-22"}}


# ── _distill_profile ─────────────────────────────────────────────────────────────────────────────

class TestDistillProfile:
    def test_empty_events_and_calendars(self):
        result = _distill_profile([], [])
        assert result["total_events_60d"] == 0
        assert result["events_per_week"] == 0
        assert result["calendar_count"] == 0
        assert result["recurring_ratio"] == 0
        assert result["all_day_count"] == 0
        assert result["peak_day"] is None
        assert result["peak_hour"] is None
        assert result["evening_ratio"] == 0
        assert result["day_distribution"] == {}

    def test_calendar_count(self):
        cals = [{"id": "cal1"}, {"id": "cal2"}, {"id": "cal3"}]
        result = _distill_profile([], cals)
        assert result["calendar_count"] == 3

    def test_single_timed_event_peak_day(self):
        # 2026-08-21 is a Friday
        result = _distill_profile([_timed_event(10)], [])
        assert result["peak_day"] == "Friday"

    def test_single_timed_event_peak_hour(self):
        result = _distill_profile([_timed_event(14)], [])
        assert result["peak_hour"] == 14

    def test_all_day_event_counted_not_in_distributions(self):
        result = _distill_profile([_all_day_event()], [])
        assert result["total_events_60d"] == 1
        assert result["all_day_count"] == 1
        assert result["peak_day"] is None
        assert result["peak_hour"] is None
        assert result["day_distribution"] == {}

    def test_recurring_ratio_when_all_recurring(self):
        result = _distill_profile([_timed_event(9, recurring=True)], [])
        assert result["recurring_ratio"] == 1.0

    def test_recurring_ratio_zero_when_none_recurring(self):
        events = [_timed_event(9), _timed_event(10)]
        result = _distill_profile(events, [])
        assert result["recurring_ratio"] == 0.0

    def test_evening_ratio_one_for_late_event(self):
        result = _distill_profile([_timed_event(19)], [])
        assert result["evening_ratio"] == 1.0

    def test_evening_ratio_zero_for_morning_event(self):
        result = _distill_profile([_timed_event(9)], [])
        assert result["evening_ratio"] == 0.0

    def test_events_per_week_calculation(self):
        events = [_timed_event(10)] * 17
        result = _distill_profile(events, [])
        assert result["events_per_week"] == 2.0  # round(17 / 8.5, 1)

    def test_malformed_datetime_skipped_gracefully(self):
        events = [{"start": {"dateTime": "not-a-date"}}]
        result = _distill_profile(events, [])
        assert result["total_events_60d"] == 1
        assert result["peak_day"] is None
        assert result["peak_hour"] is None
        assert result["day_distribution"] == {}


# ── GET /gcal/profile ────────────────────────────────────────────────────────────────────────

class TestGcalProfileEndpoint:
    def test_returns_null_when_no_row(self):
        conn = FakeConn()  # empty fetchrow_results → fetchrow returns None
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/gcal/profile")
        assert r.status_code == 200
        assert r.json() is None

    def test_returns_null_when_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"gcal_data": None}])
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/gcal/profile")
        assert r.status_code == 200
        assert r.json() is None

    def test_returns_parsed_json_string(self):
        payload = {"peak_day": "Monday", "events_per_week": 3.5}
        conn = FakeConn(fetchrow_results=[{"gcal_data": json.dumps(payload)}])
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/gcal/profile")
        assert r.status_code == 200
        assert r.json() == payload

    def test_returns_dict_passthrough(self):
        payload = {"peak_day": "Wednesday", "events_per_week": 5.0}
        conn = FakeConn(fetchrow_results=[{"gcal_data": payload}])
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/gcal/profile")
        assert r.status_code == 200
        assert r.json() == payload


# ── GET /gcal/analyze ────────────────────────────────────────────────────────────────────────

class TestGcalAnalyzeEndpoint:
    def test_404_when_no_data(self):
        conn = FakeConn()
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/gcal/analyze")
        assert r.status_code == 404

    def test_404_when_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"gcal_data": None}])
        with patch("app.gcal.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/gcal/analyze")
        assert r.status_code == 404

    def test_200_with_mocked_narrative(self):
        payload = {
            "peak_day": "Monday", "events_per_week": 4.0,
            "calendar_count": 2, "recurring_ratio": 0.5,
            "all_day_count": 0, "peak_hour": 10,
            "evening_ratio": 0.1,
            "day_distribution": {"Monday": 4},
            "total_events_60d": 34,
        }
        conn = FakeConn(fetchrow_results=[{"gcal_data": json.dumps(payload)}])
        with patch("app.gcal.router.get_conn", make_get_conn(conn)), \
             patch("app.gcal.router.chat_completion",
                   new=AsyncMock(return_value="Your calendar reveals temporal anxiety.")):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/gcal/analyze")
        assert r.status_code == 200
        assert r.json()["narrative"] == "Your calendar reveals temporal anxiety."


# ── GET /gcal/connect ────────────────────────────────────────────────────────────────────────

class TestGcalConnectEndpoint:
    def test_503_when_google_client_id_unset(self):
        mock_settings = MagicMock()
        mock_settings.google_client_id = ""
        with patch("app.oauth_base.get_settings", return_value=mock_settings):
            r = TestClient(_make_app(), raise_server_exceptions=False).get(
                "/api/gcal/connect", params={"ct": "fake_token"}
            )
        assert r.status_code == 503
