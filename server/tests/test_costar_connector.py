"""
Tests for the Co-Star connector.

Run:  cd server && python -m pytest tests/test_costar_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.costar.router import router as costar_router

from .conftest import FakeConn, make_get_conn

USER_ID = "22222222-2222-2222-2222-222222222222"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(costar_router, prefix="/api/costar")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── POST /costar/manual ───────────────────────────────────────────────────────

class TestCoStarManualEndpoint:
    def test_stores_and_returns_full_chart(self):
        conn = FakeConn()
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).post(
                "/api/costar/manual",
                json={
                    "sun_sign": "Aries",
                    "moon_sign": "Taurus",
                    "rising_sign": "Gemini",
                    "venus_sign": "Cancer",
                    "mars_sign": "Leo",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "connected"
        assert body["chart"]["source"] == "manual_entry"
        assert body["chart"]["sun"] == "Aries"
        assert body["chart"]["moon"] == "Taurus"
        assert body["chart"]["rising"] == "Gemini"
        assert body["chart"]["venus"] == "Cancer"
        assert body["chart"]["mars"] == "Leo"
        assert len(conn.execute_calls) == 1
        # Upsert, not UPDATE — users without a vibe_vectors row must not lose the chart
        sql = conn.execute_calls[0][0]
        assert "INSERT INTO vibe_vectors" in sql and "ON CONFLICT (user_id)" in sql

    def test_optional_venus_mars_stored_as_none(self):
        conn = FakeConn()
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).post(
                "/api/costar/manual",
                json={
                    "sun_sign": "Virgo",
                    "moon_sign": "Libra",
                    "rising_sign": "Scorpio",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["chart"]["venus"] is None
        assert body["chart"]["mars"] is None

    def test_rejects_unknown_sign(self):
        r = TestClient(_make_app()).post(
            "/api/costar/manual",
            json={"sun_sign": "Ophiuchus", "moon_sign": "Libra", "rising_sign": "Leo"},
        )
        assert r.status_code == 422

    def test_ingest_password_endpoint_is_gone(self):
        r = TestClient(_make_app()).post(
            "/api/costar/ingest",
            json={"costar_username": "u", "costar_password": "p"},
        )
        assert r.status_code in (404, 405)


# ── GET /costar/analyze ───────────────────────────────────────────────────────

class TestCoStarAnalyzeEndpoint:
    def test_404_when_no_row(self):
        conn = FakeConn()
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/costar/analyze")
        assert r.status_code == 404

    def test_404_when_data_null(self):
        conn = FakeConn(fetchrow_results=[{"costar_data": None}])
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/costar/analyze")
        assert r.status_code == 404

    def test_200_with_mocked_narrative(self):
        profile = {
            "source": "costar_api",
            "sun": "Scorpio", "moon": "Pisces", "rising": "Aquarius",
            "venus": "Libra", "mars": "Aries",
            "mercury": "Sagittarius", "jupiter": "Capricorn", "saturn": "Taurus",
        }
        conn = FakeConn(fetchrow_results=[{"costar_data": json.dumps(profile)}])
        with patch("app.costar.router.get_conn", make_get_conn(conn)), \
             patch(
                 "app.costar.router.chat_completion",
                 new=AsyncMock(return_value="Your water-dominant chart reveals deep intuition."),
             ):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/costar/analyze")
        assert r.status_code == 200
        assert r.json()["narrative"] == "Your water-dominant chart reveals deep intuition."


# ── GET /costar/profile ───────────────────────────────────────────────────────

class TestCoStarProfileEndpoint:
    def test_returns_null_when_no_row(self):
        conn = FakeConn()
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/costar/profile")
        assert r.status_code == 200
        assert r.json() is None

    def test_returns_parsed_json_string(self):
        payload = {
            "source": "manual_entry",
            "sun": "Aries", "moon": "Taurus", "rising": "Gemini",
            "venus": "Cancer", "mars": None,
        }
        conn = FakeConn(fetchrow_results=[{"costar_data": json.dumps(payload)}])
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/costar/profile")
        assert r.status_code == 200
        assert r.json() == payload

    def test_returns_dict_passthrough(self):
        payload = {
            "source": "costar_api",
            "sun": "Capricorn", "moon": "Virgo", "rising": "Scorpio",
            "venus": "", "mars": "",
        }
        conn = FakeConn(fetchrow_results=[{"costar_data": payload}])
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).get("/api/costar/profile")
        assert r.status_code == 200
        assert r.json() == payload
