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
from uuid import UUID


import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..oauth_base import OAuthProvider, authorize_url, finish_callback, require_configured, store_provider_data, validate_connect_token
from ..llm.chat import chat_completion

router = APIRouter()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GCAL_API_BASE = "https://www.googleapis.com/calendar/v3"
_SCOPES = "https://www.googleapis.com/auth/calendar.readonly"


GCAL = OAuthProvider(
    name="gcal", label="Google Calendar",
    auth_url=_GOOGLE_AUTH_URL, token_url=_GOOGLE_TOKEN_URL, scopes=_SCOPES,
    client_id=lambda s: s.google_client_id, client_secret=lambda s: s.google_client_secret,
    redirect_uri=lambda s: s.gcal_redirect_uri,
    authorize_params={"access_type": "offline", "prompt": "consent"},
)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def gcal_connect(ct: str = Query(..., description="Short-lived connect token")):
    """Redirect user to Google OAuth with calendar.readonly scope."""
    require_configured(GCAL)  # before the one-use connect token is spent
    payload = await validate_connect_token(ct)
    resp = RedirectResponse(authorize_url(GCAL, payload["sub"]))
    # Prevent the ?ct= token from leaking to Google via the Referer header.
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/callback")
async def gcal_callback(code: str, state: str):
    """Google redirects here. Exchange code, fetch calendar data, store."""
    grant = await finish_callback(GCAL, code, state)
    user_id, access_token = grant.user_id, grant.access_token
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:

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
