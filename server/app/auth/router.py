"""Auth routes — register, login, me."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .models import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from .service import hash_password, verify_password, create_access_token
from .deps import get_current_user_id
from ..db import get_conn
from ..ratelimit import limiter

router = APIRouter()

# Pre-computed hash used when a login email is not found, so the response time
# for invalid emails matches the response time for valid-but-wrong-password
# attempts, preventing email enumeration via timing.
_DUMMY_HASH = hash_password("__dummy_constant_time_guard__")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, body: RegisterRequest):
    pw_hash = hash_password(body.password)

    async with get_conn() as conn:
        # Check if email already taken
        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", body.email
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        row = await conn.fetchrow(
            """
            INSERT INTO users (email, display_name, password_hash)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            body.email,
            body.display_name,
            pw_hash,
        )

    token = create_access_token(row["id"])
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest):
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE email = $1",
            body.email,
        )

    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
    )

    if row is None:
        verify_password(body.password, _DUMMY_HASH)  # constant-time guard
        raise _invalid

    if not verify_password(body.password, row["password_hash"]):
        raise _invalid

    token = create_access_token(row["id"])
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user_id: UUID = Depends(get_current_user_id)):
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, created_at, is_admin FROM users WHERE id = $1",
            user_id,
        )

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return UserResponse(**dict(row))


@router.post("/connect-token")
@limiter.limit("10/minute")
async def issue_connect_token(request: Request, user_id: UUID = Depends(get_current_user_id)):
    """Issue a 60-second single-use token for OAuth connect redirects.

    Redirect-based connect flows (Spotify, GCal) pass the full session JWT in
    the URL because browser navigation can't set headers — that leaks to server
    logs, browser history, and Referer. This endpoint mints a short-lived token
    that expires in 60 s and is consumed on first use, so a leak window is tiny.
    """
    ct = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO connect_tokens (token, user_id, expires_at) VALUES ($1, $2, $3)",
            ct, user_id, expires_at,
        )
        # Lazily prune expired tokens to keep the table bounded — connect tokens
        # are 60s TTL so anything 1h old is long-dead garbage.
        await conn.execute(
            "DELETE FROM connect_tokens WHERE expires_at < now() - INTERVAL '1 hour'"
        )
    return {"ct": ct}


@router.get("/connectors")
async def my_connectors(user_id: UUID = Depends(get_current_user_id)):
    """Return which OAuth providers the user has tokens for."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            "SELECT provider FROM oauth_tokens WHERE user_id = $1",
            user_id,
        )
    return [r["provider"] for r in rows]
