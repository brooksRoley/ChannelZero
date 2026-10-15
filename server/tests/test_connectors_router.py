"""
Tests for the connectors router:
  GET /available  — provider availability map (public)
  GET /correlations — cross-connector LLM correlation finder (auth-required)

Uses FakeConn from conftest — no real DB, no real HTTP, no real LLM calls.

Run:  cd server && python -m pytest tests/test_connectors_router.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.connectors.router import router as connectors_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000009")

_SPOTIFY_DATA = {"top_genres": ["ambient", "electronic"], "energy": 0.7}
_STRAVA_DATA = {"total_distance_km": 300.0, "activity_types": {"Run": 20}}

_NULL_ROW: dict = {
    "spotify_data": None,
    "twitter_data": None,
    "strava_data": None,
    "gcal_data": None,
    "github_data": None,
    "youtube_data": None,
    "reddit_data": None,
    "letterboxd_data": None,
    "instagram_data": None,
    "tiktok_data": None,
    "costar_data": None,
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(connectors_router, prefix="/api/connectors")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _row(**overrides) -> dict:
    """Return a full vibe_vectors row with all data columns, overriding as needed."""
    return {**_NULL_ROW, **overrides}


# ── GET /available ─────────────────────────────────────────────────────────────


class TestGetAvailableConnectors:
    def test_costar_always_available(self):
        """costar requires no env credentials — all([]) is True."""
        settings = MagicMock(spotify_client_id=None, spotify_client_secret=None)
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.status_code == 200
        assert resp.json()["providers"]["costar"] is True

    def test_spotify_true_when_both_creds_present(self):
        settings = MagicMock(spotify_client_id="id123", spotify_client_secret="secret456")
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["providers"]["spotify"] is True

    def test_spotify_false_when_secret_missing(self):
        settings = MagicMock()
        settings.spotify_client_id = "id123"
        settings.spotify_client_secret = ""
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["providers"]["spotify"] is False

    def test_spotify_false_when_id_missing(self):
        settings = MagicMock()
        settings.spotify_client_id = ""
        settings.spotify_client_secret = "secret456"
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["providers"]["spotify"] is False

    def test_steam_true_when_api_key_present(self):
        settings = MagicMock(steam_api_key="AAAA-BBBB-CCCC-DDDD")
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["providers"]["steam"] is True

    def test_steam_false_when_api_key_absent(self):
        settings = MagicMock()
        settings.steam_api_key = ""
        with patch("app.connectors.router.get_settings", return_value=settings), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["providers"]["steam"] is False

    def test_llm_true_when_configured(self):
        with patch("app.connectors.router.get_settings", return_value=MagicMock()), \
             patch("app.connectors.router.llm_configured", return_value=True):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["llm"] is True

    def test_llm_false_when_not_configured(self):
        with patch("app.connectors.router.get_settings", return_value=MagicMock()), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        assert resp.json()["llm"] is False

    def test_response_includes_all_expected_provider_keys(self):
        with patch("app.connectors.router.get_settings", return_value=MagicMock()), \
             patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/available")
        providers = resp.json()["providers"]
        expected = {
            "spotify", "twitter", "strava", "google", "gcal", "youtube",
            "github", "reddit", "instagram", "tiktok", "letterboxd", "steam", "costar",
        }
        assert expected == set(providers.keys())


# ── GET /correlations ─────────────────────────────────────────────────────────


class TestGetCorrelations:
    def test_returns_empty_list_when_llm_not_configured(self):
        """No DB hit — early return [] when LLM is absent."""
        with patch("app.connectors.router.llm_configured", return_value=False):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_400_on_unknown_provider(self):
        conn = FakeConn()
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=unknown_xyz")
        assert resp.status_code == 400

    def test_empty_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_empty_when_target_provider_has_null_data(self):
        conn = FakeConn(fetchrow_results=[_row(twitter_data=json.dumps({"username": "test"}))])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.json() == []

    def test_empty_when_only_one_provider_has_data(self):
        conn = FakeConn(fetchrow_results=[_row(spotify_data=json.dumps(_SPOTIFY_DATA))])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.json() == []

    def test_returns_correlations_when_multi_provider_data_present(self):
        llm_response = json.dumps([{
            "source": {"provider": "spotify", "field": "energy", "value": 0.7, "label": "Energy"},
            "target": {"provider": "strava", "field": "total_distance_km",
                       "value": 300.0, "label": "Distance"},
            "explanation": "High musical energy correlates with high training volume.",
        }])
        conn = FakeConn(fetchrow_results=[_row(
            spotify_data=json.dumps(_SPOTIFY_DATA),
            strava_data=json.dumps(_STRAVA_DATA),
        )])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)), \
             patch("app.connectors.router.chat_completion",
                   new=AsyncMock(return_value=llm_response)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["source"]["provider"] == "spotify"
        assert body[0]["target"]["provider"] == "strava"

    def test_returns_empty_when_llm_raises_http_exception(self):
        from fastapi import HTTPException as FastAPIHTTPException
        conn = FakeConn(fetchrow_results=[_row(
            spotify_data=json.dumps(_SPOTIFY_DATA),
            strava_data=json.dumps(_STRAVA_DATA),
        )])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)), \
             patch("app.connectors.router.chat_completion",
                   new=AsyncMock(side_effect=FastAPIHTTPException(429, "rate limited"))):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_empty_when_llm_returns_invalid_json(self):
        conn = FakeConn(fetchrow_results=[_row(
            spotify_data=json.dumps(_SPOTIFY_DATA),
            strava_data=json.dumps(_STRAVA_DATA),
        )])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)), \
             patch("app.connectors.router.chat_completion",
                   new=AsyncMock(return_value="not valid json {")):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.json() == []

    def test_strips_markdown_fences_from_llm_response(self):
        payload = json.dumps([{
            "source": {"provider": "spotify", "field": "energy", "value": 0.7,
                       "label": "Energy"},
            "target": {"provider": "strava", "field": "total_distance_km",
                       "value": 300.0, "label": "Distance"},
            "explanation": "correlation",
        }])
        fenced = f"```json\n{payload}\n```"
        conn = FakeConn(fetchrow_results=[_row(
            spotify_data=json.dumps(_SPOTIFY_DATA),
            strava_data=json.dumps(_STRAVA_DATA),
        )])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)), \
             patch("app.connectors.router.chat_completion",
                   new=AsyncMock(return_value=fenced)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert len(resp.json()) == 1

    def test_handles_jsonb_dict_without_double_decode(self):
        """asyncpg may return JSONB columns as dicts; router must handle both str and dict."""
        payload = json.dumps([{
            "source": {"provider": "spotify", "field": "energy", "value": 0.7,
                       "label": "Energy"},
            "target": {"provider": "strava", "field": "total_distance_km",
                       "value": 300.0, "label": "Distance"},
            "explanation": "correlation",
        }])
        conn = FakeConn(fetchrow_results=[_row(
            spotify_data=_SPOTIFY_DATA,   # dict, not JSON string
            strava_data=_STRAVA_DATA,     # dict, not JSON string
        )])
        with patch("app.connectors.router.llm_configured", return_value=True), \
             patch("app.connectors.router.get_conn", make_get_conn(conn)), \
             patch("app.connectors.router.chat_completion",
                   new=AsyncMock(return_value=payload)):
            resp = TestClient(_make_app()).get("/api/connectors/correlations?provider=spotify")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
