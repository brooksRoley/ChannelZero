"""Shared OAuth2 connector base — eliminates boilerplate across provider routers.

Handles:
  - State JWT creation / verification with one-time nonce
  - Authorization URL construction
  - Code-for-token exchange (body or Basic auth, PKCE) via finish_callback
  - Encrypted token storage (upsert into oauth_tokens)
  - Encrypted token retrieval

Provider-specific logic (profile fetching, data distillation, re-embedding)
stays in each router — this module only covers the OAuth plumbing.

A connector describes itself with an `OAuthProvider` and calls two functions:
`authorize_url(provider, user_id)` from /connect and
`finish_callback(provider, code, state)` from /callback, which verifies the
state, exchanges the code, stores the encrypted tokens with the scope the
user actually granted, and returns a `Grant`. Only fetching and distilling the
provider's data is left to the router (docs/CONNECTORS.md).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status

from .config import Settings, get_settings
from .db import get_conn
from .llm.encryption import decrypt_api_key, encrypt_api_key

logger = logging.getLogger(__name__)


# ── State helpers ─────────────────────────────────────────────────────────────────────────
# Identical across every connector — JWT with a one-time nonce.


def make_oauth_state(user_id: str, code_verifier: str | None = None) -> str:
    """Create a signed, time-limited, one-use state parameter.

    A PKCE verifier rides along *encrypted*: the state is signed, not secret,
    and it passes through the browser and the provider. A readable verifier
    would let whoever sees the redirect redeem an intercepted code.
    """
    nonce = secrets.token_urlsafe(16)
    payload: dict = {"sub": user_id, "nonce": nonce, "exp": int(time.time()) + 600}
    if code_verifier:
        enc, iv = encrypt_api_key(code_verifier)
        payload["cv"] = base64.urlsafe_b64encode(enc).decode()
        payload["cvn"] = base64.urlsafe_b64encode(iv).decode()
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def verify_oauth_state(state: str) -> str:
    """Decode, verify, and consume the state JWT. Returns user_id."""
    return (await _consume_state(state))["sub"]


async def _consume_state(state: str) -> dict:
    """Verify and consume the state JWT; returns its payload."""
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
        ) from exc

    nonce = payload.get("nonce")
    if not nonce:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state — missing nonce",
        )

    async with get_conn() as conn:
        try:
            await conn.execute(
                "INSERT INTO _oauth_nonces (nonce, consumed_at) VALUES ($1, now())",
                nonce,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OAuth state already consumed — possible replay attack",
            )
        try:
            await conn.execute(
                "DELETE FROM _oauth_nonces WHERE consumed_at < now() - INTERVAL '24 hours'"
            )
        except Exception:
            pass  # best-effort; never block the auth flow

    return payload


def _state_verifier(payload: dict) -> str | None:
    if not payload.get("cv"):
        return None
    return decrypt_api_key(base64.urlsafe_b64decode(payload["cv"]), base64.urlsafe_b64decode(payload["cvn"]))


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ── Token helpers ─────────────────────────────────────────────────────────────────────────


async def validate_connect_token(ct: str) -> dict:
    """Validate and atomically consume a short-lived connect token.

    Uses a single UPDATE…RETURNING to eliminate the TOCTOU race that existed
    when a SELECT and a separate UPDATE ran in different connections — two
    concurrent requests could both pass the consumed_at IS NULL check before
    either UPDATE ran, allowing a captured token to be used twice.
    Returns {"sub": user_id_str} or raises 401.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            UPDATE connect_tokens
               SET consumed_at = now()
             WHERE token = $1
               AND consumed_at IS NULL
               AND expires_at > now()
            RETURNING user_id
            """,
            ct,
        )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already-used connect token",
        )
    return {"sub": str(row["user_id"])}


def build_authorize_url(
    auth_url: str,
    *,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    response_type: str = "code",
    extra_params: dict | None = None,
) -> str:
    """Construct a standard OAuth2 authorization URL."""
    params = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    if extra_params:
        params.update(extra_params)
    return f"{auth_url}?{urlencode(params)}"


async def store_oauth_tokens(
    user_id: str,
    provider: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: int | None = None,
    scope: str = "",
) -> None:
    """Encrypt and upsert tokens into the oauth_tokens table."""
    enc_access, access_nonce = encrypt_api_key(access_token)
    enc_refresh, refresh_nonce = (None, None)
    if refresh_token:
        enc_refresh, refresh_nonce = encrypt_api_key(refresh_token)

    expires_dt = None
    if expires_at:
        expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_tokens
                (user_id, provider, encrypted_access_token, access_nonce,
                 encrypted_refresh_token, refresh_nonce, expires_at, scope)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                encrypted_access_token  = EXCLUDED.encrypted_access_token,
                access_nonce            = EXCLUDED.access_nonce,
                encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                refresh_nonce           = EXCLUDED.refresh_nonce,
                expires_at              = EXCLUDED.expires_at,
                scope                   = EXCLUDED.scope,
                updated_at              = now()
            """,
            UUID(user_id),
            provider,
            enc_access, access_nonce,
            enc_refresh, refresh_nonce,
            expires_dt, scope,
        )


async def get_stored_tokens(
    user_id: str | UUID,
    provider: str,
) -> dict | None:
    """Retrieve and decrypt stored OAuth tokens for a user+provider.

    Returns {"access_token": str, "refresh_token": str|None} or None.
    """
    uid = UUID(user_id) if isinstance(user_id, str) else user_id
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT encrypted_access_token, access_nonce,
                   encrypted_refresh_token, refresh_nonce,
                   expires_at, scope
            FROM oauth_tokens
            WHERE user_id = $1 AND provider = $2
            """,
            uid, provider,
        )

    if not row or not row["encrypted_access_token"]:
        return None

    access_token = decrypt_api_key(
        row["encrypted_access_token"], row["access_nonce"]
    )
    refresh_token = None
    if row["encrypted_refresh_token"] and row["refresh_nonce"]:
        refresh_token = decrypt_api_key(
            row["encrypted_refresh_token"], row["refresh_nonce"]
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": row["expires_at"],
        "scope": row.get("scope") or "",
    }


# Seconds before expiry at which a token counts as expired: a fetch that
# starts on a token with seconds left can fail halfway through.
_REFRESH_SKEW_SECONDS = 300


async def refresh_if_needed(
    user_id: str | UUID,
    provider: str,
    token_url: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Return a live access token for user+provider, refreshing it if needed.

    Stores the *rotated* refresh token: providers like Strava issue a new one
    on refresh, and the old one stops working once the new token is used.

    Raises HTTPException 404 {code: not_connected} with no stored tokens, and
    409 {code: reauth_required} when there is no refresh token or the refresh
    is refused. 409, not 401: the frontend treats any 401 as an expired
    ChannelZero session and logs the user out.
    """
    tokens = await get_stored_tokens(user_id, provider)
    if not tokens:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_connected", "message": f"{provider.title()} isn't connected."})
    expires = tokens.get("expires_at")
    if expires is not None and expires.timestamp() > time.time() + _REFRESH_SKEW_SECONDS:
        return tokens["access_token"]
    reauth = HTTPException(status_code=status.HTTP_409_CONFLICT,
                           detail={"code": "reauth_required",
                                   "message": f"{provider.title()} needs you to reconnect."})
    if not tokens.get("refresh_token"):
        raise reauth

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(token_url, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        })
    if resp.status_code != 200:
        logger.warning("%s token refresh failed (%s): %s", provider, resp.status_code, resp.text[:300])
        raise reauth
    body = resp.json()
    expires_at = body.get("expires_at") or int(time.time()) + int(body.get("expires_in", 3600))
    await store_oauth_tokens(
        str(user_id), provider, body["access_token"],
        body.get("refresh_token") or tokens["refresh_token"], expires_at, tokens.get("scope", ""),
    )
    return body["access_token"]


_PROVIDER_DATA_COLUMNS = {
    "spotify_data", "twitter_data", "strava_data", "gcal_data",
    "github_data", "youtube_data", "reddit_data", "letterboxd_data",
    "instagram_data", "tiktok_data", "costar_data", "steam_data",
}


async def store_provider_data(
    user_id: str,
    column: str,
    data: dict,
) -> None:
    """Upsert distilled provider data into vibe_vectors.

    Creates the row if intake hasn't run yet — avoids silently dropping
    OAuth-fetched data for users who connect a provider before completing
    intake. Requires migration 023 (nullable intake columns).
    """
    import json

    if column not in _PROVIDER_DATA_COLUMNS:
        raise ValueError(f"Unknown provider data column: {column}")

    async with get_conn() as conn:
        await conn.execute(
            f"""
            INSERT INTO vibe_vectors (user_id, {column})
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET {column} = EXCLUDED.{column},
                updated_at = now()
            """,
            UUID(user_id), json.dumps(data),
        )


# ── Provider spec + the shared flow ───────────────────────────────────────────


@dataclass(frozen=True)
class OAuthProvider:
    """Everything the OAuth dance needs to know about one provider."""

    name: str                                   # oauth_tokens.provider
    label: str                                  # for messages: "Reddit"
    auth_url: str
    token_url: str
    scopes: str
    client_id: Callable[[Settings], str]
    client_secret: Callable[[Settings], str]
    redirect_uri: Callable[[Settings], str]
    client_id_param: str = "client_id"          # TikTok calls it client_key
    token_auth: Literal["body", "basic"] = "body"
    authorize_params: dict[str, str] = field(default_factory=dict)  # access_type=offline …
    token_headers: dict[str, str] = field(default_factory=dict)     # User-Agent, Accept …
    pkce: bool = False
    default_expires_in: int | None = 3600     # None: tokens that never expire (GitHub OAuth apps)


@dataclass(frozen=True)
class Grant:
    user_id: str
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    scope: str                                  # what the user granted
    raw: dict                                   # the token response (open_id, user_id …)


def _http() -> httpx.AsyncClient:
    """One place to build the client, so tests can hand it a MockTransport."""
    return httpx.AsyncClient(timeout=20.0)


def require_configured(provider: OAuthProvider) -> None:
    """503 {code: not_configured} when the server has no client id for it.

    Call it before spending anything single-use, like a connect token.
    """
    if not provider.client_id(get_settings()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_configured", "message": f"{provider.label} isn't set up on this server."},
        )


def authorize_url(provider: OAuthProvider, user_id: str) -> str:
    """The provider's consent URL, with a one-use state (and PKCE when asked)."""
    require_configured(provider)
    settings = get_settings()
    params = {
        provider.client_id_param: provider.client_id(settings),
        "response_type": "code",
        "redirect_uri": provider.redirect_uri(settings),
        "scope": provider.scopes,
        **provider.authorize_params,
    }
    verifier = secrets.token_urlsafe(48) if provider.pkce else None
    params["state"] = make_oauth_state(user_id, verifier)
    if verifier:
        params["code_challenge"] = pkce_challenge(verifier)
        params["code_challenge_method"] = "S256"
    return f"{provider.auth_url}?{urlencode(params)}"


async def finish_callback(provider: OAuthProvider, code: str, state: str, *, store: bool = True) -> Grant:
    """Verify the state, exchange the code and store the tokens.

    Never returns the provider's error body to the client: it can carry
    request details, and the user can't act on it anyway. It goes to the log.
    """
    payload = await _consume_state(state)
    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": provider.redirect_uri(settings),
    }
    headers = {"Accept": "application/json", **provider.token_headers}
    if provider.token_auth == "basic":
        creds = f"{provider.client_id(settings)}:{provider.client_secret(settings)}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(creds).decode()}"
    else:
        data[provider.client_id_param] = provider.client_id(settings)
        data["client_secret"] = provider.client_secret(settings)
    verifier = _state_verifier(payload)
    if verifier:
        data["code_verifier"] = verifier
        if provider.token_auth == "basic":
            data["client_id"] = provider.client_id(settings)

    async with _http() as client:
        resp = await client.post(provider.token_url, data=data, headers=headers)
    body: dict = {}
    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            body = {}
    if not body.get("access_token"):
        logger.warning("%s token exchange failed (%s): %s", provider.name, resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "token_exchange_failed",
                    "message": f"{provider.label} didn't accept the sign-in. Try connecting again."},
        )

    expires_in = body.get("expires_in", provider.default_expires_in)
    expires_at = int(time.time()) + int(expires_in) if expires_in is not None else None
    granted = body.get("scope")
    if isinstance(granted, list):
        granted = " ".join(granted)
    grant = Grant(
        user_id=payload["sub"],
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token") or None,
        expires_at=expires_at,
        scope=(granted or provider.scopes).replace(",", " "),
        raw=body,
    )
    if store:
        await store_oauth_tokens(grant.user_id, provider.name, grant.access_token,
                                 grant.refresh_token, grant.expires_at, grant.scope)
    return grant
