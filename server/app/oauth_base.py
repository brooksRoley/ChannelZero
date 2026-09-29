"""Shared OAuth2 connector base — eliminates boilerplate across provider routers.

Handles:
  - State JWT creation / verification with one-time nonce
  - Authorization URL construction
  - Code-for-token exchange (standard and Basic Auth variants)
  - Encrypted token storage (upsert into oauth_tokens)
  - Encrypted token retrieval

Provider-specific logic (profile fetching, data distillation, re-embedding)
stays in each router — this module only covers the OAuth plumbing.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status

from .config import get_settings
from .db import get_conn
from .llm.encryption import decrypt_api_key, encrypt_api_key


# ── State helpers ─────────────────────────────────────────────────────────────
# Identical across every connector — JWT with a one-time nonce.


def make_oauth_state(user_id: str) -> str:
    """Create a signed, time-limited, one-use state parameter."""
    nonce = secrets.token_urlsafe(16)
    payload = {"sub": user_id, "nonce": nonce, "exp": int(time.time()) + 600}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def verify_oauth_state(state: str) -> str:
    """Decode, verify, and consume the state JWT. Returns user_id."""
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

    return payload["sub"]


# ── Token helpers ─────────────────────────────────────────────────────────────


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


async def exchange_code_for_tokens(
    token_url: str,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
    extra_data: dict | None = None,
    use_basic_auth: bool = False,
    extra_headers: dict | None = None,
) -> dict:
    """Exchange an authorization code for tokens.

    Supports both standard POST body auth and HTTP Basic Auth.
    Returns the parsed JSON response from the token endpoint.
    """
    data: dict = {
        "grant_type": "authorization_code",
        "code": code,
    }
    if redirect_uri:
        data["redirect_uri"] = redirect_uri
    if extra_data:
        data.update(extra_data)

    headers = {}
    auth = None

    if use_basic_auth:
        import base64
        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {credentials}"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        # Some providers want client_id/secret in the body
        data["client_id"] = client_id
        data["client_secret"] = client_secret

    if extra_headers:
        headers.update(extra_headers)

    # GitHub specifically needs Accept: application/json
    if "Accept" not in headers and "accept" not in headers:
        pass  # most providers return JSON by default

    async with httpx.AsyncClient(timeout=20.0) as client:
        if use_basic_auth:
            resp = await client.post(token_url, data=data, headers=headers)
        else:
            resp = await client.post(
                token_url,
                data=data,
                headers=headers if headers else None,
                auth=(client_id, client_secret)
                if not any(k in data for k in ("client_id",))
                else None,
            )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {resp.text}",
        )

    return resp.json()


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
                   expires_at
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
    }


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
