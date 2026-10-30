"""
Strava OAuth + somatic data ingestion.

Flow:
Routes are mounted at /api/strava.
  1. GET  /connect  → return auth URL for frontend redirect
  2. GET  /callback → the frontend forwards Strava's ?code=&state=&scope= (or ?error=)
                      → exchange code for tokens, encrypt + store them (with the granted scope)
                      → fetch athlete profile + recent activities
                      → store the distilled profile (with synced_at) in vibe_vectors.strava_data
                      → return JSON; the frontend navigates
  3. POST /sync     → refresh the token if needed, re-fetch, re-store
Failures come back as {detail: {code, message}}: app_inactive, reauth_required,
rate_limited, scope_missing, access_denied, strava_error.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..llm.chat import chat_completion
from ..oauth_base import (
    build_authorize_url,
    make_oauth_state,
    refresh_if_needed,
    store_oauth_tokens,
    store_provider_data,
    verify_oauth_state,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
_STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
_STRAVA_API_BASE = "https://www.strava.com/api/v3"
_SCOPES = "read,activity:read"


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def strava_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the Strava authorization URL for the authenticated user.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    """
    settings = get_settings()
    if not settings.strava_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Strava not configured")

    url = build_authorize_url(
        _STRAVA_AUTH_URL,
        client_id=settings.strava_client_id,
        redirect_uri=settings.strava_redirect_uri,
        scope=_SCOPES,
        state=make_oauth_state(str(user_id)),
        extra_params={"approval_prompt": "auto"},
    )
    return {"auth_url": url}


# ── Errors Strava can hand back, in words the card can show ─────────────────


def _strava_error(resp: httpx.Response) -> HTTPException:
    """Map a failed Strava API response to a code + plain message.

    Before this, any non-200 on the activity fetch read as "no data": a
    deactivated app stored an empty profile and the callback said
    "connected". Statuses are ChannelZero's own: 409 rather than 401 for a
    dead Strava token, because the frontend logs the user out on any 401.
    """
    try:
        body = resp.json()
    except ValueError:
        body = {}
    errors = body.get("errors", []) if isinstance(body, dict) else []
    inactive = any(isinstance(e, dict) and e.get("code") == "Inactive" for e in errors)
    logger.warning("Strava API %s: %s", resp.status_code, resp.text[:300])
    if resp.status_code == 403 and inactive:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "code": "app_inactive",
            "message": "Strava isn't sending activities right now: the app's API access is deactivated."})
    if resp.status_code in (401, 403):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "reauth_required", "message": "Strava needs you to reconnect."})
    if resp.status_code == 429:
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={
            "code": "rate_limited", "message": "Strava asked us to slow down. Try again in 15 minutes."})
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={
        "code": "strava_error", "message": "Strava didn't answer as expected. Try again later."})


async def _fetch_profile(client: httpx.AsyncClient, access_token: str, athlete: dict) -> dict:
    """Recent activities + stats → the distilled profile, stamped `synced_at`.

    Raises the mapped error when the activity fetch fails, so a failure is
    never stored as an empty profile. Stats are optional unless the app is
    inactive (then the activity fetch has already failed).
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    activities_resp = await client.get(
        f"{_STRAVA_API_BASE}/athlete/activities", headers=headers, params={"per_page": 30})
    if activities_resp.status_code != 200:
        raise _strava_error(activities_resp)
    stats_data: dict = {}
    athlete_id = athlete.get("id")
    if athlete_id:
        stats_resp = await client.get(f"{_STRAVA_API_BASE}/athletes/{athlete_id}/stats", headers=headers)
        if stats_resp.status_code == 200:
            stats_data = stats_resp.json()
    profile = _distill_profile(athlete, activities_resp.json(), stats_data)
    profile["synced_at"] = datetime.now(timezone.utc).isoformat()
    return profile


@router.get("/callback")
async def strava_callback(code: str = "", state: str = "", scope: Optional[str] = None,
                          error: Optional[str] = None):
    """
    Strava redirects here (via frontend) after the user decides.
    Exchanges code for tokens, fetches the athlete profile + activities, stores everything.

    Strava sends `error=access_denied` when the user cancels, and `scope` with
    what they actually granted: unticking "View data about your activities"
    still returns a code, but every activity read would then fail.
    """
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "code": "access_denied", "message": "Strava wasn't connected: access was declined."})
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "code": "bad_request", "message": "Missing authorization code or state."})
    user_id = await verify_oauth_state(state)
    granted = scope if scope is not None else _SCOPES
    if "activity:read" not in {s.strip() for s in granted.split(",")}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "code": "scope_missing",
            "message": "Strava needs \"View data about your activities\" to connect. Try again with it ticked."})
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            _STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise _strava_error(token_resp)
        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_at = tokens.get("expires_at", int(time.time()) + 21600)
        athlete = tokens.get("athlete", {})

        # Tokens are stored before the data fetch: if Strava is down or the app
        # inactive, a later /sync can still pick up without a reconnect.
        strava_id = str(athlete.get("id", ""))
        if strava_id:
            async with get_conn() as conn:
                await conn.execute(
                    "UPDATE users SET strava_id = $1, updated_at = now() WHERE id = $2",
                    strava_id, UUID(user_id),
                )
        await store_oauth_tokens(user_id, "strava", access_token, refresh_token, expires_at, granted)

        strava_profile = await _fetch_profile(client, access_token, athlete)

    await store_provider_data(user_id, "strava_data", strava_profile)

    # Auto-trigger Oracle synthesis if enough providers connected
    from ..oracle.trigger import maybe_trigger_synthesis
    await maybe_trigger_synthesis(UUID(user_id))

    return JSONResponse({"status": "connected", "athlete": strava_profile.get("athlete_name", "")})


@router.post("/sync")
async def strava_sync(user_id: UUID = Depends(get_current_user_id)):
    """Re-fetch the profile with the stored tokens, refreshing them if needed.

    The callback used to be the only fetch, so the profile was a snapshot from
    the day of connecting and the 6-hour access token was never renewed.
    """
    settings = get_settings()
    access_token = await refresh_if_needed(
        user_id, "strava", _STRAVA_TOKEN_URL, settings.strava_client_id, settings.strava_client_secret)
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT strava_id FROM users WHERE id = $1", user_id)
    athlete = {"id": int(row["strava_id"])} if row and row["strava_id"] else {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            me = await client.get(f"{_STRAVA_API_BASE}/athlete",
                                  headers={"Authorization": f"Bearer {access_token}"})
            if me.status_code == 200:
                athlete = me.json()
            profile = await _fetch_profile(client, access_token, athlete)
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail={
            "code": "timeout", "message": "Strava timed out. Try again."})
    await store_provider_data(str(user_id), "strava_data", profile)
    return {"status": "synced", "profile": profile}


# ── Profile distillation ─────────────────────────────────────────────────────

@router.get("/profile")
async def get_strava_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Strava profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT strava_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["strava_data"]:
        return None
    data = row["strava_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def strava_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Strava somatic profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT strava_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["strava_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Strava data found")

    data = row["strava_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_strava_profile(profile)
    return {"narrative": narrative}


async def _analyze_strava_profile(profile: dict) -> str:
    activity_types = profile.get("activity_types", {})
    activities_str = ", ".join(f"{k}: {v}" for k, v in activity_types.items())
    recent_count = profile.get("recent_count", 0)
    total_elevation = profile.get("total_elevation_m", 0)
    total_distance = profile.get("total_distance_km", 0)
    total_hours = profile.get("total_moving_hours", 0)
    avg_hr = profile.get("avg_heartrate")
    max_hr = profile.get("max_heartrate")
    all_runs = profile.get("all_time_runs", 0)
    all_run_km = profile.get("all_time_run_distance_km", 0)
    all_rides = profile.get("all_time_rides", 0)
    all_ride_km = profile.get("all_time_ride_distance_km", 0)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Strava athletic data as a window into their relationship with their body and discipline.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's somatic patterns and what they reveal about their inner life.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Activity types (recent 30): {activities_str}
- Recent activities: {recent_count}
- Total elevation gain: {total_elevation}m
- Total distance: {total_distance}km
- Total moving time: {total_hours} hours
- Avg heart rate: {avg_hr or 'N/A'} bpm | Max heart rate: {max_hr or 'N/A'} bpm
- All-time runs: {all_runs} ({all_run_km}km)
- All-time rides: {all_rides} ({all_ride_km}km)

Write 2-3 paragraphs analyzing:
1. Relationship with the body — what activity choices and volume reveal about how they inhabit their physical form, whether movement is escape or communion
2. Discipline patterns — consistency, intensity preferences, competitive vs meditative tendencies
3. What elevation, distance, and heart rate patterns reveal about their relationship with suffering, endurance, and self-imposed limits

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(athlete: dict, activities: list[dict], stats: dict) -> dict:
    """Reduce raw Strava data to the somatic essentials."""
    # Athlete basics
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()

    # Activity type distribution
    type_counts: dict[str, int] = {}
    total_elevation = 0.0
    total_distance = 0.0
    total_moving_time = 0
    heartrates: list[float] = []

    for a in activities:
        sport = a.get("type", "Unknown")
        type_counts[sport] = type_counts.get(sport, 0) + 1
        total_elevation += a.get("total_elevation_gain", 0)
        total_distance += a.get("distance", 0)
        total_moving_time += a.get("moving_time", 0)
        if a.get("average_heartrate"):
            heartrates.append(a["average_heartrate"])

    # Stats summary
    all_run_totals = stats.get("all_run_totals", {})
    all_ride_totals = stats.get("all_ride_totals", {})

    return {
        "athlete_name": name,
        "activity_types": type_counts,
        "recent_count": len(activities),
        "total_elevation_m": round(total_elevation, 1),
        "total_distance_km": round(total_distance / 1000, 1),
        "total_moving_hours": round(total_moving_time / 3600, 1),
        "avg_heartrate": round(sum(heartrates) / len(heartrates), 1) if heartrates else None,
        "max_heartrate": round(max(heartrates), 1) if heartrates else None,
        "all_time_runs": all_run_totals.get("count", 0),
        "all_time_run_distance_km": round(all_run_totals.get("distance", 0) / 1000, 1),
        "all_time_rides": all_ride_totals.get("count", 0),
        "all_time_ride_distance_km": round(all_ride_totals.get("distance", 0) / 1000, 1),
    }
