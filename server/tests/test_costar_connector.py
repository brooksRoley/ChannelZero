"""
Tests for the Co-Star connector.

Run:  cd server && python -m pytest tests/test_costar_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.costar.router import router as costar_router, _distill_chart

from .conftest import FakeConn, make_get_conn

USER_ID = "22222222-2222-2222-2222-222222222222"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(costar_router, prefix="/api/costar")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _mock_httpx_client(
    login_status: int = 200,
    login_json: dict | None = None,
    chart_status: int = 200,
    chart_json: dict | None = None,
    raise_error: bool = False,
) -> MagicMock:
    """Return a mock for httpx.AsyncClient usable as an async context manager."""
    mock_client = AsyncMock()

    if raise_error:
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
    else:
        login_resp = MagicMock()
        login_resp.status_code = login_status
        login_resp.json.return_value = login_json or {"token": "fake_token_abc"}
        mock_client.post = AsyncMock(return_value=login_resp)

        chart_resp = MagicMock()
        chart_resp.status_code = chart_status
        chart_resp.json.return_value = chart_json or {
            "placements": [{"planet": "sun", "sign": "Scorpio"}]
        }
        mock_client.get = AsyncMock(return_value=chart_resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ── _distill_chart ────────────────────────────────────────────────────────────

class TestDistillChart:
    def test_source_always_costar_api(self):
        result = _distill_chart({"placements": {}})
        assert result["source"] == "costar_api"

    def test_list_placements_with_planet_key(self):
        raw = {
            "placements": [
                {"planet": "sun", "sign": "Aries"},
                {"planet": "moon", "sign": "Taurus"},
            ]
        }
        result = _distill_chart(raw)
        assert result["sun"] == "Aries"
        assert result["moon"] == "Taurus"

    def test_list_placements_with_name_key_fallback(self):
        raw = {"placements": [{"name": "venus", "sign": "Libra"}]}
        result = _distill_chart(raw)
        assert result["venus"] == "Libra"

    def test_dict_placements_passthrough(self):
        raw = {"placements": {"sun": "Gemini", "moon": "Scorpio"}}
        result = _distill_chart(raw)
        assert result["sun"] == "Gemini"
        assert result["moon"] == "Scorpio"

    def test_chart_key_used_when_no_placements(self):
        raw = {"chart": {"sun": "Capricorn", "moon": "Aquarius"}}
        result = _distill_chart(raw)
        assert result["sun"] == "Capricorn"
        assert result["moon"] == "Aquarius"

    def test_ascendant_key_maps_to_rising(self):
        raw = {"placements": {"ascendant": "Virgo"}}
        result = _distill_chart(raw)
        assert result["rising"] == "Virgo"

    def test_rising_key_maps_to_rising_fallback(self):
        raw = {"placements": {"rising": "Pisces"}}
        result = _distill_chart(raw)
        assert result["rising"] == "Pisces"

    def test_empty_list_placements_all_empty_strings(self):
        result = _distill_chart({"placements": []})
        assert result["sun"] == ""
        assert result["moon"] == ""
        assert result["rising"] == ""

    def test_planet_with_empty_sign_skipped(self):
        raw = {
            "placements": [
                {"planet": "sun", "sign": ""},
                {"planet": "moon", "sign": "Cancer"},
            ]
        }
        result = _distill_chart(raw)
        assert result["sun"] == ""  # skipped — defaults to empty
        assert result["moon"] == "Cancer"

    def test_non_dict_non_list_placements_falls_back_to_raw(self):
        raw = {"placements": "unexpected_string", "sun": "Sagittarius"}
        result = _distill_chart(raw)
        assert result["sun"] == "Sagittarius"


# ── POST /costar/manual ───────────────────────────────────────────────────────

class TestCoStarManualEndpoint:
    def test_stores_and_returns_full_chart(self):
        conn = FakeConn()
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
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

    def test_optional_venus_mars_stored_as_none(self):
        conn = FakeConn()
        with patch("app.costar.router.get_conn", make_get_conn(conn)):
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


# ── POST /costar/ingest ───────────────────────────────────────────────────────

class TestCoStarIngestEndpoint:
    def test_400_on_login_failure(self):
        mock_cm = _mock_httpx_client(login_status=401)
        with patch("app.costar.router.httpx.AsyncClient", return_value=mock_cm):
            r = TestClient(_make_app(), raise_server_exceptions=False).post(
                "/api/costar/ingest",
                json={"costar_username": "user@test.com", "costar_password": "wrong"},
            )
        assert r.status_code == 400

    def test_502_on_httpx_network_error(self):
        mock_cm = _mock_httpx_client(raise_error=True)
        with patch("app.costar.router.httpx.AsyncClient", return_value=mock_cm):
            r = TestClient(_make_app(), raise_server_exceptions=False).post(
                "/api/costar/ingest",
                json={"costar_username": "user@test.com", "costar_password": "pass"},
            )
        assert r.status_code == 502

    def test_502_when_chart_fetch_fails(self):
        mock_cm = _mock_httpx_client(login_status=200, chart_status=403)
        conn = FakeConn()
        with patch("app.costar.router.httpx.AsyncClient", return_value=mock_cm), \
             patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app(), raise_server_exceptions=False).post(
                "/api/costar/ingest",
                json={"costar_username": "user@test.com", "costar_password": "pass"},
            )
        assert r.status_code == 502

    def test_happy_path_returns_distilled_profile(self):
        chart_json = {
            "placements": [
                {"planet": "sun", "sign": "Scorpio"},
                {"planet": "moon", "sign": "Pisces"},
                {"planet": "rising", "sign": "Aquarius"},
            ]
        }
        mock_cm = _mock_httpx_client(chart_json=chart_json)
        conn = FakeConn()
        with patch("app.costar.router.httpx.AsyncClient", return_value=mock_cm), \
             patch("app.costar.router.get_conn", make_get_conn(conn)):
            r = TestClient(_make_app()).post(
                "/api/costar/ingest",
                json={"costar_username": "user@test.com", "costar_password": "pass"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "connected"
        assert body["chart"]["sun"] == "Scorpio"
        assert body["chart"]["moon"] == "Pisces"
        assert body["chart"]["source"] == "costar_api"
        assert len(conn.execute_calls) == 1


# ── GET /costar/analyze ───────────────────────────────────────────────────────
# NOTE: costar_analyze calls get_settings() but never uses the result — dead code
# that requires env vars in any environment. Patch it so tests don't need real secrets.

class TestCoStarAnalyzeEndpoint:
    def test_404_when_no_row(self):
        conn = FakeConn()
        with patch("app.costar.router.get_conn", make_get_conn(conn)), \
             patch("app.costar.router.get_settings", return_value=MagicMock()):
            r = TestClient(_make_app(), raise_server_exceptions=False).get("/api/costar/analyze")
        assert r.status_code == 404

    def test_404_when_data_null(self):
        conn = FakeConn(fetchrow_results=[{"costar_data": None}])
        with patch("app.costar.router.get_conn", make_get_conn(conn)), \
             patch("app.costar.router.get_settings", return_value=MagicMock()):
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
             patch("app.costar.router.get_settings", return_value=MagicMock()), \
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
