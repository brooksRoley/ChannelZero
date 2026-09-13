"""
Tests for the Steam connector: _distill_profile (pure function),
/steam/connect endpoint, /steam/callback (mocked OpenID + HTTP),
and /steam/analyze (mocked LLM).

Uses FakeConn from conftest — no real DB, real HTTP, or real Steam API calls.

Run:  cd server && python -m pytest tests/test_steam_connector.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.steam.router import _distill_profile, router as steam_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000007")

SAMPLE_RECENT_GAMES = [
    {"name": "Hollow Knight", "playtime_2weeks": 300, "playtime_forever": 3600},
    {"name": "Celeste", "playtime_2weeks": 120, "playtime_forever": 1800},
]

SAMPLE_OWNED_GAMES = [
    {"name": "Hollow Knight", "playtime_forever": 3600},
    {"name": "Celeste", "playtime_forever": 1800},
    {"name": "Dark Souls III", "playtime_forever": 4200},
    {"name": "Hades", "playtime_forever": 2400},
    {"name": "Ori and the Blind Forest", "playtime_forever": 600},
    {"name": "Dead Cells", "playtime_forever": 900},
]

SAMPLE_PROFILE = {
    "steam_id": "76561198000000001",
    "persona_name": "SpectralGhost",
    "game_count": 6,
    "recent_2week_hours": 7.0,
    "recent_titles": ["Hollow Knight", "Celeste"],
    "total_lifetime_hours": 217.5,
    "top_games": [
        {"name": "Dark Souls III", "hours": 70.0},
        {"name": "Hollow Knight", "hours": 60.0},
    ],
    "heavy_session_hours": 213.3,
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(steam_router, prefix="/api/steam")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _distill_profile (pure function) ─────────────────────────────────────────


class TestDistillProfile:
    def test_empty_inputs_return_safe_defaults(self):
        result = _distill_profile("", "", [], [], 0)
        assert result["steam_id"] == ""
        assert result["persona_name"] == ""
        assert result["game_count"] == 0
        assert result["total_lifetime_hours"] == 0
        assert result["recent_2week_hours"] == 0
        assert result["recent_titles"] == []
        assert result["top_games"] == []
        assert result["heavy_session_hours"] == 0

    def test_recent_hours_converted_from_minutes(self):
        result = _distill_profile("123", "Ghost", SAMPLE_RECENT_GAMES, [], 2)
        # 300 + 120 = 420 minutes → 7.0 hours
        assert result["recent_2week_hours"] == 7.0

    def test_recent_titles_capped_at_ten(self):
        many_games = [{"name": f"Game{i}", "playtime_2weeks": 10, "playtime_forever": 60} for i in range(15)]
        result = _distill_profile("123", "Ghost", many_games, [], 15)
        assert len(result["recent_titles"]) == 10

    def test_total_lifetime_hours_converted_from_minutes(self):
        result = _distill_profile("123", "Ghost", [], SAMPLE_OWNED_GAMES, 6)
        expected_total = round(sum(g["playtime_forever"] for g in SAMPLE_OWNED_GAMES) / 60, 1)
        assert result["total_lifetime_hours"] == expected_total

    def test_top_games_sorted_by_playtime_descending(self):
        result = _distill_profile("123", "Ghost", [], SAMPLE_OWNED_GAMES, 6)
        hours = [g["hours"] for g in result["top_games"]]
        assert hours == sorted(hours, reverse=True)

    def test_top_games_capped_at_ten(self):
        many_games = [{"name": f"Game{i}", "playtime_forever": (20 - i) * 60} for i in range(15)]
        result = _distill_profile("123", "Ghost", [], many_games, 15)
        assert len(result["top_games"]) <= 10

    def test_heavy_session_hours_uses_top_five(self):
        result = _distill_profile("123", "Ghost", [], SAMPLE_OWNED_GAMES, 6)
        sorted_games = sorted(SAMPLE_OWNED_GAMES, key=lambda g: g["playtime_forever"], reverse=True)
        expected = round(sum(g["playtime_forever"] for g in sorted_games[:5]) / 60, 1)
        assert result["heavy_session_hours"] == expected

    def test_persona_name_stored(self):
        result = _distill_profile("123", "SpectralGhost", [], [], 0)
        assert result["persona_name"] == "SpectralGhost"

    def test_game_count_from_parameter(self):
        result = _distill_profile("123", "Ghost", [], [], 42)
        assert result["game_count"] == 42


# ── /steam/connect ────────────────────────────────────────────────────────────


class TestSteamConnect:
    def test_returns_auth_url_with_openid_params(self):
        app = _make_app()
        client = TestClient(app)

        with patch("app.steam.router.get_settings") as mock_settings:
            settings = MagicMock()
            settings.steam_api_key = "test_api_key"
            settings.steam_redirect_uri = "http://localhost:5173/api/steam/callback"
            settings.cors_origin_list = ["http://localhost:5173"]
            settings.jwt_secret = "test_jwt_secret"
            mock_settings.return_value = settings

            with patch("app.steam.router._make_state", return_value="fake_state"):
                resp = client.get("/api/steam/connect")

        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "steamcommunity.com/openid/login" in data["auth_url"]
        assert "openid.mode=checkid_setup" in data["auth_url"]

    def test_503_when_no_steam_api_key(self):
        app = _make_app()
        client = TestClient(app)

        with patch("app.steam.router.get_settings") as mock_settings:
            settings = MagicMock()
            settings.steam_api_key = None
            mock_settings.return_value = settings

            resp = client.get("/api/steam/connect")

        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()

    def test_auth_url_includes_correct_openid_identity(self):
        app = _make_app()
        client = TestClient(app)

        with patch("app.steam.router.get_settings") as mock_settings:
            settings = MagicMock()
            settings.steam_api_key = "key"
            settings.steam_redirect_uri = "http://localhost:5173/callback"
            settings.cors_origin_list = ["http://localhost:5173"]
            settings.jwt_secret = "secret"
            mock_settings.return_value = settings

            with patch("app.steam.router._make_state", return_value="state123"):
                resp = client.get("/api/steam/connect")

        url = resp.json()["auth_url"]
        assert "identifier_select" in url


# ── /steam/callback ───────────────────────────────────────────────────────────


class TestSteamCallback:
    def _make_mock_httpx(self, openid_valid: bool = True) -> MagicMock:
        mock_client = AsyncMock()

        verify_resp = MagicMock()
        verify_resp.text = "is_valid:true" if openid_valid else "is_valid:false"

        recent_resp = MagicMock()
        recent_resp.status_code = 200
        recent_resp.json.return_value = {"response": {"games": SAMPLE_RECENT_GAMES}}

        owned_resp = MagicMock()
        owned_resp.status_code = 200
        owned_resp.json.return_value = {
            "response": {"games": SAMPLE_OWNED_GAMES, "game_count": len(SAMPLE_OWNED_GAMES)}
        }

        summary_resp = MagicMock()
        summary_resp.status_code = 200
        summary_resp.json.return_value = {
            "response": {"players": [{"personaname": "SpectralGhost"}]}
        }

        # post() = verify; get() returns responses in order
        mock_client.post = AsyncMock(return_value=verify_resp)
        mock_client.get = AsyncMock(side_effect=[recent_resp, owned_resp, summary_resp])

        context_manager = MagicMock()
        context_manager.__aenter__ = AsyncMock(return_value=mock_client)
        context_manager.__aexit__ = AsyncMock(return_value=False)
        return context_manager

    def test_missing_state_returns_400(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/steam/callback")
        assert resp.status_code == 400
        assert "state" in resp.json()["detail"].lower()

    def test_invalid_openid_verification_returns_400(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)

        conn = FakeConn()
        conn.execute_calls = []  # nonce insert will run

        mock_http = self._make_mock_httpx(openid_valid=False)
        claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"

        with (
            patch("app.steam.router._verify_state", AsyncMock(return_value=str(USER_ID))),
            patch("app.steam.router.httpx.AsyncClient", return_value=mock_http),
        ):
            resp = client.get(
                "/api/steam/callback",
                params={"state": "validstate", "openid.claimed_id": claimed_id},
            )

        assert resp.status_code == 400
        assert "verification failed" in resp.json()["detail"].lower()

    def test_missing_claimed_id_returns_400(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)

        mock_http = self._make_mock_httpx(openid_valid=True)
        # Remove steam ID from claimed_id to force extraction failure
        mock_http_no_id = self._make_mock_httpx(openid_valid=True)

        with (
            patch("app.steam.router._verify_state", AsyncMock(return_value=str(USER_ID))),
            patch("app.steam.router.httpx.AsyncClient", return_value=mock_http),
        ):
            resp = client.get(
                "/api/steam/callback",
                params={"state": "validstate", "openid.claimed_id": ""},
            )

        assert resp.status_code == 400
        assert "steam id" in resp.json()["detail"].lower()

    def test_non_numeric_steam_id_returns_400(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)

        mock_http = self._make_mock_httpx(openid_valid=True)

        with (
            patch("app.steam.router._verify_state", AsyncMock(return_value=str(USER_ID))),
            patch("app.steam.router.httpx.AsyncClient", return_value=mock_http),
        ):
            resp = client.get(
                "/api/steam/callback",
                params={
                    "state": "validstate",
                    "openid.claimed_id": "https://steamcommunity.com/openid/id/not-a-number",
                },
            )

        assert resp.status_code == 400

    def test_successful_callback_redirects_to_frontend(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)

        conn = FakeConn()
        mock_http = self._make_mock_httpx(openid_valid=True)
        claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"

        with (
            patch("app.steam.router._verify_state", AsyncMock(return_value=str(USER_ID))),
            patch("app.steam.router.httpx.AsyncClient", return_value=mock_http),
            patch("app.steam.router.get_conn", make_get_conn(conn)),
            patch("app.steam.router.store_provider_data", AsyncMock()),
            patch("app.steam.router.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.steam_api_key = "key"
            settings.cors_origin_list = ["http://localhost:5173"]
            mock_settings.return_value = settings

            resp = client.get(
                "/api/steam/callback",
                params={"state": "validstate", "openid.claimed_id": claimed_id},
            )

        assert resp.status_code in (302, 307)
        assert "peripheral" in resp.headers["location"]
        assert "steam=connected" in resp.headers["location"]

    def test_successful_callback_stores_steam_id_in_db(self):
        app = _make_app()
        client = TestClient(app, follow_redirects=False)

        conn = FakeConn()
        mock_http = self._make_mock_httpx(openid_valid=True)
        claimed_id = "https://steamcommunity.com/openid/id/76561198000000001"

        with (
            patch("app.steam.router._verify_state", AsyncMock(return_value=str(USER_ID))),
            patch("app.steam.router.httpx.AsyncClient", return_value=mock_http),
            patch("app.steam.router.get_conn", make_get_conn(conn)),
            patch("app.steam.router.store_provider_data", AsyncMock()),
            patch("app.steam.router.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.steam_api_key = "key"
            settings.cors_origin_list = ["http://localhost:5173"]
            mock_settings.return_value = settings

            client.get(
                "/api/steam/callback",
                params={"state": "validstate", "openid.claimed_id": claimed_id},
            )

        # Verify steam_id written to users table
        update_calls = [c for c in conn.execute_calls if "UPDATE users" in c[0]]
        assert len(update_calls) == 1
        assert "76561198000000001" in update_calls[0][1]


# ── /steam/analyze ────────────────────────────────────────────────────────────


class TestSteamAnalyze:
    def test_404_when_no_steam_data(self):
        app = _make_app()
        client = TestClient(app)

        conn = FakeConn(fetchrow_results=[{"steam_data": None}])

        with patch("app.steam.router.get_conn", make_get_conn(conn)):
            resp = client.get("/api/steam/analyze")

        assert resp.status_code == 404
        assert "no steam data" in resp.json()["detail"].lower()

    def test_404_when_vibe_vectors_row_missing(self):
        app = _make_app()
        client = TestClient(app)

        conn = FakeConn(fetchrow_results=[None])

        with patch("app.steam.router.get_conn", make_get_conn(conn)):
            resp = client.get("/api/steam/analyze")

        assert resp.status_code == 404

    def test_analyze_returns_narrative(self):
        app = _make_app()
        client = TestClient(app)

        profile_json = json.dumps(SAMPLE_PROFILE)
        conn = FakeConn(fetchrow_results=[{"steam_data": profile_json}])

        with (
            patch("app.steam.router.get_conn", make_get_conn(conn)),
            patch("app.steam.router.chat_completion", AsyncMock(return_value="You dwell in dark worlds...")),
        ):
            resp = client.get("/api/steam/analyze")

        assert resp.status_code == 200
        data = resp.json()
        assert "narrative" in data
        assert data["narrative"] == "You dwell in dark worlds..."

    def test_analyze_accepts_dict_steam_data(self):
        """steam_data can be a dict (already parsed) or a JSON string — both should work."""
        app = _make_app()
        client = TestClient(app)

        conn = FakeConn(fetchrow_results=[{"steam_data": SAMPLE_PROFILE}])

        with (
            patch("app.steam.router.get_conn", make_get_conn(conn)),
            patch("app.steam.router.chat_completion", AsyncMock(return_value="Isolation metric computed.")),
        ):
            resp = client.get("/api/steam/analyze")

        assert resp.status_code == 200
        assert "narrative" in resp.json()
