"""
Strava connector honesty: a failure is said plainly, never stored as an empty
profile and reported "connected"; the token is refreshed (and the rotated
refresh token kept); the granted scope is checked and stored.

Covers:
- _strava_error: 403 Inactive → app_inactive (503), 401 → reauth_required (409,
  never 401: the frontend logs out on 401), 429 → rate_limited
- GET /strava/callback: access_denied, scope_missing, Inactive app (tokens kept,
  no profile stored), happy path (granted scope stored, synced_at set),
  a failed token exchange never echoes Strava's body
- refresh_if_needed: live token untouched, expired token refreshed + rotated
  refresh token stored, refused refresh → 409, nothing stored → 404
- POST /strava/sync: refreshes, re-fetches, stores

Run:  cd server && python -m pytest tests/test_strava_honesty.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import oauth_base
from app.auth.deps import get_current_user_id
from app.strava.router import _strava_error, router as strava_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000002")
INACTIVE = {"message": "Forbidden",
            "errors": [{"resource": "Application", "field": "Status", "code": "Inactive"}]}
ACTIVITY = {"type": "Run", "distance": 8000, "moving_time": 2400, "total_elevation_gain": 40}


def _resp(status_code: int, data: dict | list | None = None) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = data if data is not None else {}
    m.text = "raw provider body with secrets"
    return m


class _Client:
    """httpx.AsyncClient stand-in: queued responses for post and get."""

    def __init__(self, posts: list, gets: list):
        self.post = AsyncMock(side_effect=posts)
        self.get = AsyncMock(side_effect=gets)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(strava_router, prefix="/api/strava")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _patches(client: _Client, conn: FakeConn | None = None):
    conn = conn or FakeConn()
    return [
        patch("app.strava.router.httpx.AsyncClient", return_value=client),
        patch("app.strava.router.verify_oauth_state", new=AsyncMock(return_value=str(USER_ID))),
        patch("app.strava.router.get_conn", make_get_conn(conn)),
        patch("app.strava.router.store_oauth_tokens", new=AsyncMock()),
        patch("app.strava.router.store_provider_data", new=AsyncMock()),
        patch("app.oracle.trigger.maybe_trigger_synthesis", new=AsyncMock()),
    ]


def _run(patches, fn):
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in reversed(patches):
            p.stop()


TOKENS = {"access_token": "a", "refresh_token": "r", "expires_at": 9999999999,
          "athlete": {"id": 7, "firstname": "Test", "lastname": "Runner"}}


# ── _strava_error ─────────────────────────────────────────────────────────────


class TestStravaError:
    def test_inactive_app_is_named(self):
        e = _strava_error(_resp(403, INACTIVE))
        assert e.status_code == 503 and e.detail["code"] == "app_inactive"

    def test_dead_token_is_409_never_401(self):
        e = _strava_error(_resp(401, {"message": "Authorization Error"}))
        assert e.status_code == 409 and e.detail["code"] == "reauth_required"

    def test_rate_limit(self):
        assert _strava_error(_resp(429)).detail["code"] == "rate_limited"

    def test_body_is_never_in_the_message(self):
        e = _strava_error(_resp(500))
        assert "raw provider body" not in e.detail["message"]


# ── /callback ─────────────────────────────────────────────────────────────────


class TestCallback:
    def test_declined_access(self):
        resp = TestClient(_app()).get("/api/strava/callback?error=access_denied&state=s")
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "access_denied"

    def test_missing_activity_scope_is_refused(self):
        client = _Client([], [])
        resp = _run(_patches(client), lambda: TestClient(_app()).get(
            "/api/strava/callback?code=c&state=s&scope=read"))
        assert resp.status_code == 400 and resp.json()["detail"]["code"] == "scope_missing"
        client.post.assert_not_called()

    def test_inactive_app_keeps_tokens_and_stores_no_profile(self):
        client = _Client([_resp(200, TOKENS)], [_resp(403, INACTIVE)])
        patches = _patches(client)
        resp = _run(patches, lambda: TestClient(_app()).get(
            "/api/strava/callback?code=c&state=s&scope=read,activity:read"))
        assert resp.status_code == 503 and resp.json()["detail"]["code"] == "app_inactive"
        # tokens stored (a later /sync can pick up), profile not
        assert patches[3].new.await_count == 1
        assert patches[4].new.await_count == 0

    def test_happy_path_stores_granted_scope_and_synced_at(self):
        client = _Client([_resp(200, TOKENS)], [_resp(200, [ACTIVITY]), _resp(200, {})])
        patches = _patches(client)
        resp = _run(patches, lambda: TestClient(_app()).get(
            "/api/strava/callback?code=c&state=s&scope=read,activity:read"))
        assert resp.status_code == 200 and resp.json()["status"] == "connected"
        patches[3].new.assert_awaited_once_with(str(USER_ID), "strava", "a", "r", 9999999999,
                                                "read,activity:read")
        stored = patches[4].new.await_args.args[2]
        assert stored["recent_count"] == 1 and "synced_at" in stored

    def test_failed_token_exchange_never_echoes_strava(self):
        client = _Client([_resp(400, {"message": "Bad Request"})], [])
        resp = _run(_patches(client), lambda: TestClient(_app()).get(
            "/api/strava/callback?code=c&state=s&scope=read,activity:read"))
        assert resp.status_code >= 400
        assert "raw provider body" not in resp.text


# ── refresh_if_needed ─────────────────────────────────────────────────────────


def _tokens(expires_in: timedelta, refresh: str | None = "r-old") -> dict:
    return {"access_token": "a-old", "refresh_token": refresh,
            "expires_at": datetime.now(timezone.utc) + expires_in, "scope": "read,activity:read"}


def _refresh(tokens, client=None, store=None):
    store = store or AsyncMock()
    with patch.object(oauth_base, "get_stored_tokens", new=AsyncMock(return_value=tokens)), \
         patch.object(oauth_base, "store_oauth_tokens", new=store), \
         patch.object(oauth_base.httpx, "AsyncClient", return_value=client or _Client([], [])):
        return asyncio.run(oauth_base.refresh_if_needed(USER_ID, "strava", "https://t", "id", "sec")), store


class TestRefreshIfNeeded:
    def test_live_token_is_returned_without_a_call(self):
        token, store = _refresh(_tokens(timedelta(hours=2)))
        assert token == "a-old"
        store.assert_not_awaited()

    def test_expired_token_is_refreshed_and_the_rotated_refresh_token_kept(self):
        client = _Client([_resp(200, {"access_token": "a-new", "refresh_token": "r-new",
                                      "expires_at": 2000000000})], [])
        token, store = _refresh(_tokens(timedelta(minutes=2)), client)
        assert token == "a-new"
        store.assert_awaited_once_with(str(USER_ID), "strava", "a-new", "r-new", 2000000000,
                                       "read,activity:read")

    def test_refused_refresh_is_409(self):
        client = _Client([_resp(400)], [])
        with pytest.raises(HTTPException) as e:
            _refresh(_tokens(-timedelta(hours=1)), client)
        assert e.value.status_code == 409 and e.value.detail["code"] == "reauth_required"

    def test_nothing_stored_is_404(self):
        with pytest.raises(HTTPException) as e:
            _refresh(None)
        assert e.value.status_code == 404


# ── /sync ─────────────────────────────────────────────────────────────────────


class TestSync:
    def test_sync_refreshes_fetches_and_stores(self):
        client = _Client([], [_resp(200, {"id": 7, "firstname": "T"}), _resp(200, [ACTIVITY]), _resp(200, {})])
        conn = FakeConn(fetchrow_results=[{"strava_id": "7"}])
        patches = _patches(client, conn) + [
            patch("app.strava.router.refresh_if_needed", new=AsyncMock(return_value="a-live"))]
        resp = _run(patches, lambda: TestClient(_app()).post("/api/strava/sync"))
        assert resp.status_code == 200 and resp.json()["profile"]["recent_count"] == 1
        patches[4].new.assert_awaited_once_with(str(USER_ID), "strava_data", ANY)

    def test_sync_on_an_inactive_app_says_so(self):
        client = _Client([], [_resp(403, INACTIVE), _resp(403, INACTIVE)])
        conn = FakeConn(fetchrow_results=[{"strava_id": "7"}])
        patches = _patches(client, conn) + [
            patch("app.strava.router.refresh_if_needed", new=AsyncMock(return_value="a-live"))]
        resp = _run(patches, lambda: TestClient(_app()).post("/api/strava/sync"))
        assert resp.status_code == 503 and resp.json()["detail"]["code"] == "app_inactive"
        assert patches[4].new.await_count == 0
