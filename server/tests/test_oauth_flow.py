"""The shared OAuth flow: authorize_url + finish_callback, with httpx mocked
by MockTransport so no provider is ever called."""

from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app import oauth_base
from app.config import get_settings
from app.oauth_base import OAuthProvider, authorize_url, finish_callback

from .conftest import FakeConn, make_get_conn

USER = "00000000-0000-0000-0000-000000000001"

ACME = OAuthProvider(
    name="acme", label="Acme",
    auth_url="https://acme.example/authorize", token_url="https://acme.example/token",
    scopes="read profile",
    client_id=lambda s: "cid", client_secret=lambda s: "csecret",
    redirect_uri=lambda s: "https://cz.example/acme/callback",
    authorize_params={"access_type": "offline"},
)


@pytest.fixture
def conn(monkeypatch) -> FakeConn:
    c = FakeConn()
    monkeypatch.setattr(oauth_base, "get_conn", make_get_conn(c))
    return c


def _provider_answers(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(oauth_base, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(record)))
    return seen


def _state_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def _form(req: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(req.content.decode()).items()}


class TestAuthorizeUrl:
    def test_carries_client_scope_redirect_extra_params_and_state(self):
        q = parse_qs(urlparse(authorize_url(ACME, USER)).query)
        assert q["client_id"] == ["cid"] and q["scope"] == ["read profile"]
        assert q["redirect_uri"] == ["https://cz.example/acme/callback"]
        assert q["access_type"] == ["offline"] and "code_challenge" not in q
        payload = jwt.decode(q["state"][0], get_settings().jwt_secret, algorithms=["HS256"])
        assert payload["sub"] == USER and payload["nonce"]

    def test_unconfigured_provider_is_503_not_configured(self):
        bare = OAuthProvider(**{**ACME.__dict__, "client_id": lambda s: ""})
        with pytest.raises(HTTPException) as e:
            authorize_url(bare, USER)
        assert e.value.status_code == 503 and e.value.detail["code"] == "not_configured"

    def test_tiktok_style_client_key(self):
        tt = OAuthProvider(**{**ACME.__dict__, "client_id_param": "client_key"})
        q = parse_qs(urlparse(authorize_url(tt, USER)).query)
        assert q["client_key"] == ["cid"] and "client_id" not in q


class TestFinishCallback:
    def test_exchanges_stores_and_returns_the_grant(self, monkeypatch, conn):
        seen = _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={
            "access_token": "AT", "refresh_token": "RT", "expires_in": 60, "scope": "read"}))
        grant = asyncio.run(finish_callback(ACME, "the-code", _state_from(authorize_url(ACME, USER))))
        assert grant.user_id == USER and grant.access_token == "AT" and grant.refresh_token == "RT"
        assert grant.scope == "read"  # what was granted, not what was asked
        form = _form(seen[0])
        assert form["code"] == "the-code" and form["client_id"] == "cid" and form["client_secret"] == "csecret"
        stored = [a for q, a in conn.execute_calls if "oauth_tokens" in q][0]
        assert stored[1] == "acme" and stored[-1] == "read"

    def test_basic_auth_keeps_the_secret_out_of_the_body(self, monkeypatch, conn):
        basic = OAuthProvider(**{**ACME.__dict__, "token_auth": "basic", "token_headers": {"User-Agent": "cz/1"}})
        seen = _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "AT"}))
        asyncio.run(finish_callback(basic, "c", _state_from(authorize_url(basic, USER))))
        assert seen[0].headers["authorization"] == "Basic " + base64.b64encode(b"cid:csecret").decode()
        assert seen[0].headers["user-agent"] == "cz/1"
        assert "client_secret" not in _form(seen[0])

    def test_pkce_verifier_is_encrypted_in_state_and_sent_on_exchange(self, monkeypatch, conn):
        pk = OAuthProvider(**{**ACME.__dict__, "pkce": True, "token_auth": "basic"})
        url = authorize_url(pk, USER)
        challenge = parse_qs(urlparse(url).query)["code_challenge"][0]
        state = _state_from(url)
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
        seen = _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "AT"}))
        asyncio.run(finish_callback(pk, "c", state))
        verifier = _form(seen[0])["code_verifier"]
        assert oauth_base.pkce_challenge(verifier) == challenge
        assert verifier not in json.dumps(payload)  # never readable in the state

    def test_refused_exchange_never_echoes_the_provider_body(self, monkeypatch, conn):
        _provider_answers(monkeypatch, lambda r: httpx.Response(400, text="invalid_grant secret-detail"))
        with pytest.raises(HTTPException) as e:
            asyncio.run(finish_callback(ACME, "c", _state_from(authorize_url(ACME, USER))))
        assert e.value.status_code == 400 and e.value.detail["code"] == "token_exchange_failed"
        assert "secret-detail" not in json.dumps(e.value.detail)
        assert not any("oauth_tokens" in q for q, _ in conn.execute_calls)

    def test_200_without_a_token_is_a_failure(self, monkeypatch, conn):
        # GitHub answers 200 {"error": "bad_verification_code"}.
        _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"error": "bad_verification_code"}))
        with pytest.raises(HTTPException) as e:
            asyncio.run(finish_callback(ACME, "c", _state_from(authorize_url(ACME, USER))))
        assert e.value.detail["code"] == "token_exchange_failed"

    def test_a_state_is_good_once(self, monkeypatch):
        class OnceConn(FakeConn):
            used: set = set()

            async def execute(self, q, *a):
                if "_oauth_nonces" in q and q.lstrip().startswith("INSERT"):
                    if a[0] in self.used:
                        raise Exception("duplicate key")
                    self.used.add(a[0])
                return await super().execute(q, *a)

        monkeypatch.setattr(oauth_base, "get_conn", make_get_conn(OnceConn()))
        _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "AT"}))
        state = _state_from(authorize_url(ACME, USER))
        asyncio.run(finish_callback(ACME, "c", state))
        with pytest.raises(HTTPException) as e:
            asyncio.run(finish_callback(ACME, "c", state))
        assert e.value.status_code == 400

    def test_comma_scopes_and_list_scopes_are_normalised(self, monkeypatch, conn):
        _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "AT", "scope": "a,b"}))
        g = asyncio.run(finish_callback(ACME, "c", _state_from(authorize_url(ACME, USER)), store=False))
        assert g.scope == "a b"

    def test_tokens_that_never_expire_store_no_expiry(self, monkeypatch, conn):
        forever = OAuthProvider(**{**ACME.__dict__, "default_expires_in": None})
        _provider_answers(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "AT"}))
        g = asyncio.run(finish_callback(forever, "c", _state_from(authorize_url(forever, USER)), store=False))
        assert g.expires_at is None


# ── Guards: the duplication this replaced must not come back ──────────────────

import pathlib  # noqa: E402

ROUTERS = sorted(pathlib.Path(__file__).resolve().parent.parent.glob("app/*/router.py"))


@pytest.mark.parametrize("path", ROUTERS, ids=lambda p: p.parent.name)
def test_routers_use_the_shared_oauth_plumbing(path):
    src = path.read_text()
    assert "def _make_state" not in src and "def _verify_state" not in src, "use oauth_base's state helpers"
    assert "INSERT INTO oauth_tokens" not in src, "use store_oauth_tokens / finish_callback"


@pytest.mark.parametrize("path", ROUTERS, ids=lambda p: p.parent.name)
def test_no_provider_body_or_exception_text_reaches_the_client(path):
    import re
    src = path.read_text()
    assert not re.search(r'detail=f"[^"]*\{[a-z_]*resp\.text\}', src)
    assert not re.search(r'detail=f"[^"]*\{exc\}', src)
