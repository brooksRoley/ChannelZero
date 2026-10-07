"""
Letterboxd API data ingestion.

Letterboxd uses a proprietary API with HMAC-signed requests and an
API key + secret issued via their developer program.

Flow:
  1. GET /letterboxd/connect  → Authorization: Bearer <JWT> header → return auth URL
  2. GET /letterboxd/callback?code=&state= → exchange code, fetch diary, store

TODO: Requires LETTERBOXD_API_KEY + LETTERBOXD_API_SECRET.
      Apply at https://letterboxd.com/api-beta/
      Until approved, this connector returns 503 with a clear message.

Alternative (no API key): RSS feed scraping from letterboxd.com/<username>/rss/
is possible but rate-limited and less rich.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid as _uuid
from urllib.parse import urlencode
from uuid import UUID

import secrets

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..auth.deps import get_current_user_id
from ..oauth_base import store_provider_data
from ..config import get_settings
from ..db import get_conn
from ..llm.chat import chat_completion

router = APIRouter()

_LB_API_BASE = "https://api.letterboxd.com/api/v0"


# ── State helpers ─────────────────────────────────────────────────────────────

def _make_state(user_id: str) -> str:
    nonce = secrets.token_urlsafe(16)
    payload = {"sub": user_id, "nonce": nonce, "exp": int(time.time()) + 600}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def _verify_state(state: str) -> str:
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state") from exc

    nonce = payload.get("nonce")
    if not nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state — missing nonce")

    async with get_conn() as conn:
        try:
            await conn.execute(
                "INSERT INTO _oauth_nonces (nonce, consumed_at) VALUES ($1, now())",
                nonce,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="State already consumed — possible replay attack",
            )

    return payload["sub"]


def _sign_request(method: str, url: str, body: str = "") -> dict:
    """Generate HMAC-SHA256 signature headers for Letterboxd API."""
    settings = get_settings()
    timestamp = str(int(time.time()))
    nonce = _uuid.uuid4().hex

    # Letterboxd signature: HMAC-SHA256(apiSecret, method + url + body + timestamp + nonce)
    msg = f"{method}\u0000{url}\u0000{body}\u0000{timestamp}\u0000{nonce}"
    signature = hmac.new(
        settings.letterboxd_api_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "Authorization": f"Signature {signature}",
        "X-Api-Key": settings.letterboxd_api_key,
        "X-Api-Timestamp": timestamp,
        "X-Api-Nonce": nonce,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def letterboxd_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Initiate Letterboxd auth. Since Letterboxd uses API key auth (not OAuth),
    we ask the user for their Letterboxd username and fetch their public data.
    Returns an auth URL that collects the username on the frontend side.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    """
    settings = get_settings()
    if not settings.letterboxd_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Letterboxd API not configured. Requires LETTERBOXD_API_KEY — apply at https://letterboxd.com/api-beta/",
        )

    state = _make_state(str(user_id))

    # For Letterboxd, we direct the user to a frontend form that collects their
    # username and POSTs back to /letterboxd/ingest — no OAuth redirect needed.
    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return {"auth_url": f"{frontend}/peripheral?letterboxd_state={state}"}


@router.post("/ingest")
async def letterboxd_ingest(
    username: str = Query(...),
    state: str = Query(...),
):
    """
    Fetch a Letterboxd user's public film diary and ratings.
    Called after the frontend collects the username.
    """
    user_id = await _verify_state(state)
    settings = get_settings()

    if not settings.letterboxd_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Letterboxd API not configured",
        )

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Search for the member by username
        search_url = f"{_LB_API_BASE}/search"
        headers = _sign_request("GET", search_url)
        search_resp = await client.get(
            search_url,
            headers=headers,
            params={"input": username, "include": "MemberSearchItem", "perPage": 1},
        )

        member_id = None
        if search_resp.status_code == 200:
            items = search_resp.json().get("items", [])
            for item in items:
                if item.get("type") == "MemberSearchItem":
                    member = item.get("member", {})
                    if member.get("username", "").lower() == username.lower():
                        member_id = member.get("id")
                        break

        if not member_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Letterboxd user '{username}' not found",
            )

        # 2. Fetch recent log entries (diary)
        entries_url = f"{_LB_API_BASE}/member/{member_id}/log-entries"
        headers = _sign_request("GET", entries_url)
        entries_resp = await client.get(
            entries_url,
            headers=headers,
            params={"perPage": 30},
        )
        log_entries = []
        if entries_resp.status_code == 200:
            log_entries = entries_resp.json().get("items", [])

        # 3. Fetch watchlist
        watchlist_url = f"{_LB_API_BASE}/member/{member_id}/watchlist"
        headers = _sign_request("GET", watchlist_url)
        watchlist_resp = await client.get(
            watchlist_url,
            headers=headers,
            params={"perPage": 20},
        )
        watchlist = []
        if watchlist_resp.status_code == 200:
            watchlist = watchlist_resp.json().get("items", [])

    # 4. Distill empathy profile
    letterboxd_profile = _distill_profile(username, log_entries, watchlist)

    # 5. Store
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE users SET letterboxd_username = $1, updated_at = now() WHERE id = $2",
            username, UUID(user_id),
        )
    await store_provider_data(user_id, "letterboxd_data", letterboxd_profile)

    return JSONResponse({"status": "connected", "username": username})


# ── Callback (placeholder for OAuth-style flow if API supports it later) ────

@router.get("/callback")
async def letterboxd_callback(code: str = "", state: str = ""):
    """
    Placeholder callback. Letterboxd doesn't use standard OAuth yet.
    If their API adds OAuth in the future, this handles the redirect.
    """
    if not state:
        raise HTTPException(status_code=400, detail="Missing state")

    user_id = await _verify_state(state)

    frontend = get_settings().cors_origin_list[0] if get_settings().cors_origin_list else "http://localhost:5173"
    return JSONResponse({"status": "pending", "message": "Use /letterboxd/ingest with your username"})


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(username: str, entries: list[dict], watchlist: list[dict]) -> dict:
    """Reduce Letterboxd data to empathy/aesthetic patterns."""
    ratings = []
    films_logged = []

    for entry in entries:
        film = entry.get("film", {})
        title = film.get("name", "Unknown")
        rating = entry.get("rating")
        films_logged.append(title)
        if rating is not None:
            ratings.append(rating)

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

    # Watchlist titles
    watchlist_titles = [
        item.get("film", {}).get("name", "Unknown")
        for item in watchlist[:10]
    ]

    return {
        "username": username,
        "diary_count": len(entries),
        "recent_films": films_logged[:15],
        "avg_rating": avg_rating,
        "watchlist_sample": watchlist_titles,
        "ratings_given": len(ratings),
    }


@router.get("/analyze")
async def letterboxd_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Letterboxd film profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT letterboxd_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["letterboxd_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Letterboxd data found")

    data = row["letterboxd_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_letterboxd_profile(profile)
    return {"narrative": narrative}


async def _analyze_letterboxd_profile(profile: dict) -> str:
    username = profile.get("username", "")
    diary_count = profile.get("diary_count", 0)
    recent_films = ", ".join(profile.get("recent_films", [])[:10])
    avg_rating = profile.get("avg_rating")
    watchlist = ", ".join(profile.get("watchlist_sample", [])[:8])
    ratings_given = profile.get("ratings_given", 0)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Letterboxd film diary as a window into their empathic range and emotional processing.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's narrative preferences and what their film taste reveals about their inner life.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Username: {username}
- Diary entries (recent): {diary_count}
- Recent films watched: {recent_films}
- Average rating: {avg_rating or 'N/A'} / 5.0
- Ratings given: {ratings_given}
- Watchlist sample: {watchlist}

Write 2-3 paragraphs analyzing:
1. Empathic range — what the breadth or narrowness of their film choices reveals about the emotional experiences they seek out, the lives they want to inhabit vicariously
2. Narrative preferences — what genres, directors, and film styles they gravitate toward as signals of how they process complexity, ambiguity, and emotional difficulty
3. The rating psychology — what their average rating and rating frequency reveal about their relationship with judgment, criticism, and aesthetic standards

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


@router.get("/profile")
async def get_letterboxd_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Letterboxd profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT letterboxd_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["letterboxd_data"]:
        return None
    data = row["letterboxd_data"]
    return json.loads(data) if isinstance(data, str) else data
