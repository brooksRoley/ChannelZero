"""
Google Calendar OAuth + data ingestion.

Separate from the Google *auth* login flow — this requests calendar.readonly
scope to fetch event patterns and free/busy windows for the Oracle's
"Temporal Anxiety" dimension.

Flow:
  1. GET /gcal/connect?token=<JWT>  → redirect to Google with calendar scope
  2. GET /gcal/callback?code=&state= → exchange code, fetch events, store
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from uuid import UUID

import secrets

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..llm.encryption import encrypt_api_key
from ..oauth_base import store_provider_data, validate_connect_token
from ..llm.chat import chat_completion

router = APIRouter()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"
_SCOPES = "https://www.googleapis.com/auth/calendar.readonly"


# ── State helpers ─────────────────────────────────────────────────────────────

def _make_state(user_id: str) -> str:
    nonce = secrets.token_urlsafe(16)
    payload = {"sub": user_id, "nonce": nonce, "exp": int(time.time()) + 600}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def _verify_state(state: str) -> str:
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

    nonce = payload.get("nonce")
    if not nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state — missing nonce")

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


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def gcal_connect(ct: str = Query(..., description="Short-lived connect token")):
    """Redirect user to Google OAuth with calendar.readonly scope."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google OAuth not configured")

    payload = await validate_connect_token(ct)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.gcal_redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": _make_state(payload["sub"]),
        "access_type": "offline",
        "prompt": "consent",
    }
    resp = RedirectResponse(f"{_GOOGLE_AUTH_URL}?{urlencode(params)}")
    # Prevent the ?ct= token from leaking to Google via the Referer header.
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/callback")
async def gcal_callback(code: str, state: str):
    """Google redirects here. Exchange code, fetch calendar data, store."""
    user_id = await _verify_state(state)
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.gcal_redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token exchange failed")

        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)
        expires_at = int(time.time()) + expires_in

        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Fetch primary calendar event list (next 60 days)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=60)).isoformat()

        events_data = []
        events_resp = await client.get(
            f"{_GCAL_API_BASE}/calendars/primary/events",
            headers=headers,
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": 100,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        if events_resp.status_code == 200:
            events_data = events_resp.json().get("items", [])

        # 3. Fetch calendar list for context
        calendars = []
        cal_resp = await client.get(
            f"{_GCAL_API_BASE}/users/me/calendarList",
            headers=headers,
            params={"maxResults": 20},
        )
        if cal_resp.status_code == 200:
            calendars = cal_resp.json().get("items", [])

    # 4. Distill temporal profile
    gcal_profile = _distill_profile(events_data, calendars)

    # 5. Encrypt and store tokens
    enc_access, access_nonce = encrypt_api_key(access_token)
    enc_refresh, refresh_nonce = encrypt_api_key(refresh_token) if refresh_token else (None, None)

    from datetime import datetime as dt
    expires_dt = dt.fromtimestamp(expires_at, tz=timezone.utc)

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_tokens
                (user_id, provider, encrypted_access_token, access_nonce,
                 encrypted_refresh_token, refresh_nonce, expires_at, scope)
            VALUES ($1, 'gcal', $2, $3, $4, $5, $6, $7)
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
            enc_access, access_nonce,
            enc_refresh, refresh_nonce,
            expires_dt, _SCOPES,
        )

    await store_provider_data(user_id, "gcal_data", gcal_profile)

    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return RedirectResponse(f"{frontend}/calibrate?gcal=connected")


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(events: list[dict], calendars: list[dict]) -> dict:
    """Reduce raw Google Calendar data to temporal patterns."""
    total_events = len(events)
    calendar_count = len(calendars)

    # Bucket events by day-of-week and hour
    day_dist: dict[str, int] = {}
    hour_dist: dict[int, int] = {}
    recurring_count = 0
    all_day_count = 0

    for ev in events:
        start = ev.get("start", {})
        if "date" in start:
            all_day_count += 1
            continue

        dt_str = start.get("dateTime", "")
        if not dt_str:
            continue

        try:
            from datetime import datetime as dt
            parsed = dt.fromisoformat(dt_str.replace("Z", "+00:00"))
            day_name = parsed.strftime("%A")
            day_dist[day_name] = day_dist.get(day_name, 0) + 1
            hour_dist[parsed.hour] = hour_dist.get(parsed.hour, 0) + 1
        except (ValueError, TypeError):
            continue

        if ev.get("recurringEventId"):
            recurring_count += 1

    # Peak day and peak hour
    peak_day = max(day_dist, key=day_dist.get) if day_dist else None
    peak_hour = max(hour_dist, key=hour_dist.get) if hour_dist else None

    # Busyness: events per week (next 60 days ~ 8.5 weeks)
    events_per_week = round(total_events / 8.5, 1) if total_events else 0

    # Evening ratio (events after 6pm)
    evening_events = sum(v for k, v in hour_dist.items() if k >= 18)
    timed_events = sum(hour_dist.values())
    evening_ratio = round(evening_events / timed_events, 2) if timed_events else 0

    return {
        "total_events_60d": total_events,
        "events_per_week": events_per_week,
        "calendar_count": calendar_count,
        "recurring_ratio": round(recurring_count / total_events, 2) if total_events else 0,
        "all_day_count": all_day_count,
        "peak_day": peak_day,
        "peak_hour": peak_hour,
        "evening_ratio": evening_ratio,
        "day_distribution": day_dist,
    }


@router.get("/analyze")
async def gcal_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Google Calendar temporal patterns."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT gcal_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["gcal_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Google Calendar data found")

    data = row["gcal_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_gcal_profile(profile)
    return {"narrative": narrative}


async def _analyze_gcal_profile(profile: dict) -> str:
    total_events = profile.get("total_events_60d", 0)
    events_per_week = profile.get("events_per_week", 0)
    calendar_count = profile.get("calendar_count", 0)
    recurring_ratio = profile.get("recurring_ratio", 0)
    all_day_count = profile.get("all_day_count", 0)
    peak_day = profile.get("peak_day", "N/A")
    peak_hour = profile.get("peak_hour", "N/A")
    evening_ratio = profile.get("evening_ratio", 0)
    day_dist = profile.get("day_distribution", {})
    day_dist_str = ", ".join(f"{d}: {c}" for d, c in day_dist.items())

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Google Calendar data as a window into their relationship with time and control.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's temporal anxiety patterns and scheduling psychology.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Total events (next 60 days): {total_events}
- Events per week: {events_per_week}
- Number of calendars: {calendar_count}
- Recurring event ratio: {recurring_ratio}
- All-day events: {all_day_count}
- Peak scheduling day: {peak_day}
- Peak scheduling hour: {peak_hour}
- Evening event ratio (after 6pm): {evening_ratio}
- Day distribution: {day_dist_str}

Write 2-3 paragraphs analyzing:
1. Temporal anxiety — what event density, calendar count, and recurring ratios reveal about their need for structure and predictability
2. Relationship with time — peak hours and day distribution as signals of when they feel most alive, most productive, most anxious
3. Scheduling as control mechanism — what the balance of recurring vs. spontaneous, evening vs. daytime reveals about how they manage uncertainty

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


@router.get("/profile")
async def get_gcal_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Google Calendar profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT gcal_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["gcal_data"]:
        return None
    data = row["gcal_data"]
    return json.loads(data) if isinstance(data, str) else data
