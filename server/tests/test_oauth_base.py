"""
Tests for server/app/oauth_base.py — connect-token lifecycle, state helpers,
and URL construction.

Coverage targets:
  - validate_connect_token (security-critical: was zero-covered)
  - make_oauth_state / verify_oauth_state (one-time nonce replay protection)
  - build_authorize_url (pure function)

Note: these tests target the current main behavior of validate_connect_token
(SELECT then UPDATE in two connections). After PR #82 merges (atomic
UPDATE…RETURNING), the FakeConn queues for the "valid token" cases will need
to drop the expires_at/consumed_at keys — the status codes and return values
are identical in both versions.

Run:  cd server && python -m pytest tests/test_oauth_base.py -v
"""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from app.oauth_base import (
    build_authorize_url,
    make_oauth_state,
    validate_connect_token,
    verify_oauth_state,
)
from tests.conftest import FakeConn, make_get_conn

_USER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_FAKE_SECRET = "test-jwt-secret-for-oauth-base-tests-xyzzy"
_FUTURE = datetime.now(timezone.utc) + timedelta(hours=1)
_PAST = datetime.now(timezone.utc) - timedelta(hours=1)


def _fake_settings():
    s = MagicMock()
    s.jwt_secret = _FAKE_SECRET
    return s


# ── validate_connect_token ────────────────────────────────────────────────────


class TestValidateConnectToken:
    """Security-critical path — was zero-covered before this suite."""

    def test_valid_token_returns_sub(self):
        row = {"user_id": _USER_ID, "expires_at": _FUTURE, "consumed_at": None}
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            result = asyncio.run(validate_connect_token("valid-token"))
        assert result == {"sub": str(_USER_ID)}

    def test_valid_token_issues_consumed_at_update(self):
        """Consuming a valid token must record consumed_at via UPDATE."""
        row = {"user_id": _USER_ID, "expires_at": _FUTURE, "consumed_at": None}
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            asyncio.run(validate_connect_token("valid-token"))
        assert any("UPDATE connect_tokens" in call[0] for call in conn.execute_calls), (
            "validate_connect_token did not UPDATE connect_tokens after a valid token"
        )

    def test_missing_token_raises_401(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(validate_connect_token("ghost-token"))
        assert exc.value.status_code == 401

    def test_already_consumed_token_raises_401(self):
        row = {
            "user_id": _USER_ID,
            "expires_at": _FUTURE,
            "consumed_at": datetime.now(timezone.utc),
        }
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(validate_connect_token("already-used-token"))
        assert exc.value.status_code == 401

    def test_expired_token_raises_401(self):
        row = {"user_id": _USER_ID, "expires_at": _PAST, "consumed_at": None}
        conn = FakeConn(fetchrow_results=[row])
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(validate_connect_token("expired-token"))
        assert exc.value.status_code == 401

    def test_all_rejection_cases_return_401(self):
        """Verify all three rejection paths return 401, not 400 or 410."""
        cases = [
            FakeConn(fetchrow_results=[None]),  # not found
            FakeConn(fetchrow_results=[{  # already consumed
                "user_id": _USER_ID, "expires_at": _FUTURE,
                "consumed_at": datetime.now(timezone.utc),
            }]),
            FakeConn(fetchrow_results=[{  # expired
                "user_id": _USER_ID, "expires_at": _PAST, "consumed_at": None,
            }]),
        ]
        for conn in cases:
            with patch("app.oauth_base.get_conn", make_get_conn(conn)):
                with pytest.raises(HTTPException) as exc:
                    asyncio.run(validate_connect_token("tok"))
            assert exc.value.status_code == 401


# ── make_oauth_state ──────────────────────────────────────────────────────────


class TestMakeOauthState:
    def test_returns_decodable_jwt_with_sub_and_nonce(self):
        with patch("app.oauth_base.get_settings", _fake_settings):
            token = make_oauth_state(str(_USER_ID))
        payload = pyjwt.decode(token, _FAKE_SECRET, algorithms=["HS256"])
        assert payload["sub"] == str(_USER_ID)
        assert "nonce" in payload
        assert len(payload["nonce"]) > 0

    def test_token_has_future_expiry(self):
        with patch("app.oauth_base.get_settings", _fake_settings):
            token = make_oauth_state(str(_USER_ID))
        payload = pyjwt.decode(token, _FAKE_SECRET, algorithms=["HS256"])
        assert payload["exp"] > int(time.time())

    def test_nonce_is_unique_across_calls(self):
        with patch("app.oauth_base.get_settings", _fake_settings):
            t1 = make_oauth_state(str(_USER_ID))
            t2 = make_oauth_state(str(_USER_ID))
        p1 = pyjwt.decode(t1, _FAKE_SECRET, algorithms=["HS256"])
        p2 = pyjwt.decode(t2, _FAKE_SECRET, algorithms=["HS256"])
        assert p1["nonce"] != p2["nonce"]


# ── verify_oauth_state ────────────────────────────────────────────────────────


class _ReplayConn(FakeConn):
    """FakeConn variant whose execute raises on _oauth_nonces INSERT, simulating
    a UniqueViolation from a replayed state parameter."""

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        if "_oauth_nonces" in query:
            raise Exception("UniqueViolation: nonce already consumed")
        return "UPDATE 1"


class TestVerifyOauthState:
    def _make_state(self, user_id: str = str(_USER_ID)) -> str:
        with patch("app.oauth_base.get_settings", _fake_settings):
            return make_oauth_state(user_id)

    def test_valid_state_returns_user_id(self):
        state = self._make_state()
        conn = FakeConn()
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with patch("app.oauth_base.get_settings", _fake_settings):
                result = asyncio.run(verify_oauth_state(state))
        assert result == str(_USER_ID)

    def test_valid_state_inserts_nonce(self):
        """Consuming a state must INSERT the nonce to prevent replay."""
        state = self._make_state()
        conn = FakeConn()
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with patch("app.oauth_base.get_settings", _fake_settings):
                asyncio.run(verify_oauth_state(state))
        assert any("_oauth_nonces" in call[0] for call in conn.execute_calls)

    def test_replay_raises_400(self):
        """Reusing the same state JWT must be rejected (replay attack)."""
        state = self._make_state()
        conn = _ReplayConn()
        with patch("app.oauth_base.get_conn", make_get_conn(conn)):
            with patch("app.oauth_base.get_settings", _fake_settings):
                with pytest.raises(HTTPException) as exc:
                    asyncio.run(verify_oauth_state(state))
        assert exc.value.status_code == 400

    def test_tampered_jwt_raises_400(self):
        with patch("app.oauth_base.get_settings", _fake_settings):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(verify_oauth_state("not.a.valid.jwt"))
        assert exc.value.status_code == 400

    def test_jwt_signed_with_wrong_secret_raises_400(self):
        payload = {"sub": str(_USER_ID), "nonce": secrets.token_urlsafe(16), "exp": int(time.time()) + 600}
        token_wrong_secret = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        with patch("app.oauth_base.get_settings", _fake_settings):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(verify_oauth_state(token_wrong_secret))
        assert exc.value.status_code == 400

    def test_expired_jwt_raises_400(self):
        payload = {
            "sub": str(_USER_ID),
            "nonce": secrets.token_urlsafe(16),
            "exp": int(time.time()) - 10,
        }
        expired = pyjwt.encode(payload, _FAKE_SECRET, algorithm="HS256")
        with patch("app.oauth_base.get_settings", _fake_settings):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(verify_oauth_state(expired))
        assert exc.value.status_code == 400


# ── build_authorize_url ───────────────────────────────────────────────────────


class TestBuildAuthorizeUrl:
    def test_contains_required_params(self):
        url = build_authorize_url(
            "https://auth.example.com/authorize",
            client_id="my-client-id",
            redirect_uri="https://app.example.com/callback",
            scope="read write",
            state="abc123",
        )
        assert url.startswith("https://auth.example.com/authorize?")
        assert "client_id=my-client-id" in url
        assert "redirect_uri=" in url
        assert "state=abc123" in url
        assert "response_type=code" in url

    def test_scope_encoded_in_url(self):
        url = build_authorize_url(
            "https://auth.example.com/authorize",
            client_id="cid",
            redirect_uri="https://app.example.com/cb",
            scope="user:read user:write",
            state="s",
        )
        assert "user" in url and "read" in url

    def test_extra_params_included(self):
        url = build_authorize_url(
            "https://auth.example.com/authorize",
            client_id="cid",
            redirect_uri="https://app.example.com/cb",
            scope="read",
            state="s",
            extra_params={"show_dialog": "true"},
        )
        assert "show_dialog=true" in url

    def test_custom_response_type(self):
        url = build_authorize_url(
            "https://auth.example.com/authorize",
            client_id="cid",
            redirect_uri="https://app.example.com/cb",
            scope="read",
            state="s",
            response_type="token",
        )
        assert "response_type=token" in url
