"""
Instagram OAuth + aesthetic data ingestion.

Flow:
  1. GET /instagram/connect  → return auth URL for frontend redirect
  2. GET /instagram/callback → Facebook redirects back with ?code=&state=
                              → exchange code for short-lived token
                              → exchange for long-lived Instagram token
                              → fetch user profile + recent media
                              → encrypt tokens, store in oauth_tokens
                              → store Instagram profile in vibe_vectors.instagram_data
                              → redirect to frontend
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from urllib.parse import urlencode
from uuid import UUID


from ..oracle.trigger import maybe_trigger_synthesis

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..oauth_base import make_oauth_state, store_oauth_tokens, store_provider_data, verify_oauth_state
from ..db import get_conn
from ..llm.chat import chat_completion

router = APIRouter()
logger = logging.getLogger(__name__)

_FB_AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
_FB_TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
_IG_API_BASE = "https://graph.instagram.com/v21.0"
_SCOPES = "instagram_basic,instagram_manage_insights"


# Instagram doesn't fit OAuthProvider: a GET exchange on Facebook, then a
# second exchange for a long-lived token on graph.instagram.com. It shares the
# state and storage helpers. NOTE: ig_exchange_token belongs to the Instagram
# Basic Display API, which Meta shut down in Dec 2024; verify before relying on it.
_EXCHANGE_FAILED = {"code": "token_exchange_failed",
                    "message": "Instagram didn't accept the sign-in. Try connecting again."}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def instagram_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the Instagram authorization URL for the authenticated user.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    """
    settings = get_settings()
    if not settings.instagram_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Instagram not configured")

    params = {
        "client_id": settings.instagram_client_id,
        "response_type": "code",
        "redirect_uri": settings.instagram_redirect_uri,
        "scope": _SCOPES,
        "state": make_oauth_state(str(user_id)),
    }
    return {"auth_url": f"{_FB_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
async def instagram_callback(code: str, state: str):
    """
    Facebook redirects here (via frontend) after user authorizes.
    Exchanges code for tokens, fetches profile + media, stores everything.
    """
    user_id = await verify_oauth_state(state)
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Exchange authorization code for short-lived token
        token_resp = await client.get(
            _FB_TOKEN_URL,
            params={
                "client_id": settings.instagram_client_id,
                "client_secret": settings.instagram_client_secret,
                "redirect_uri": settings.instagram_redirect_uri,
                "code": code,
            },
        )
        if token_resp.status_code != 200:
            logger.warning("instagram token exchange failed (%s): %s", token_resp.status_code, token_resp.text[:300])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_EXCHANGE_FAILED)
        short_lived_token = token_resp.json().get("access_token", "")

        # 2. Exchange short-lived token for long-lived Instagram token
        long_resp = await client.get(
            f"{_IG_API_BASE}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.instagram_client_secret,
                "access_token": short_lived_token,
            },
        )
        if long_resp.status_code != 200:
            logger.warning("instagram long-lived exchange failed (%s): %s", long_resp.status_code, long_resp.text[:300])
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_EXCHANGE_FAILED)
        long_data = long_resp.json()
        access_token = long_data.get("access_token", short_lived_token)
        expires_in = long_data.get("expires_in", 5184000)  # default 60 days

        # 3. Fetch user profile
        profile_resp = await client.get(
            f"{_IG_API_BASE}/me",
            params={
                "fields": "id,username,account_type,media_count",
                "access_token": access_token,
            },
        )
        profile_data = {}
        if profile_resp.status_code == 200:
            profile_data = profile_resp.json()

        # 4. Fetch recent media
        media_resp = await client.get(
            f"{_IG_API_BASE}/me/media",
            params={
                "fields": "id,caption,media_type,timestamp,like_count,comments_count",
                "limit": 25,
                "access_token": access_token,
            },
        )
        media_data = []
        if media_resp.status_code == 200:
            media_data = media_resp.json().get("data", [])

    # 5. Distill the aesthetic profile
    instagram_profile = _distill_profile(profile_data, media_data)

    # 6. Store tokens (no refresh token: Instagram's long-lived token is refreshed by its own endpoint)
    await store_oauth_tokens(user_id, "instagram", access_token, None, int(time.time()) + expires_in, _SCOPES)

    # 7. Store Instagram profile (upserts into vibe_vectors).
    await store_provider_data(user_id, "instagram_data", instagram_profile)

    # Auto-trigger Oracle synthesis if enough providers connected
    await maybe_trigger_synthesis(UUID(user_id))

    # 8. Return success — frontend handles navigation
    return JSONResponse({"status": "connected", "username": instagram_profile.get("username", "")})


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def instagram_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Instagram aesthetic profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT instagram_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["instagram_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Instagram data found")

    data = row["instagram_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_instagram_profile(profile)
    return {"narrative": narrative}


async def _analyze_instagram_profile(profile: dict) -> str:
    username = profile.get("username", "")
    account_type = profile.get("account_type", "personal")
    media_count = profile.get("media_count", 0)
    media_types = profile.get("media_types", {})
    types_str = ", ".join(f"{k}: {v}" for k, v in media_types.items())
    avg_caption_len = profile.get("avg_caption_length", 0)
    posts_per_week = profile.get("posts_per_week")
    top_hashtags = ", ".join(profile.get("top_hashtags", [])[:10])
    avg_likes = profile.get("avg_likes", 0)
    avg_comments = profile.get("avg_comments", 0)
    total_likes = profile.get("total_likes", 0)
    total_comments = profile.get("total_comments", 0)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Instagram data as a window into their curated vs authentic self and visual identity.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's performance patterns and what their Instagram presence reveals about their inner life.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Username: {username}
- Account type: {account_type}
- Total media: {media_count}
- Media type distribution: {types_str}
- Posts per week: {posts_per_week or 'N/A'}
- Average caption length: {avg_caption_len} chars
- Top hashtags: {top_hashtags}
- Average likes per post: {avg_likes} | Average comments: {avg_comments}
- Total likes: {total_likes} | Total comments: {total_comments}

Write 2-3 paragraphs analyzing:
1. Curated vs authentic self — what media types, posting frequency, and caption length reveal about how carefully they construct their public image, the gap between the feed and the person
2. Visual identity — what hashtag choices and content patterns reveal about the aesthetic world they want to inhabit, the tribe they're signaling to
3. Performance patterns — what engagement metrics (likes, comments) reveal about their relationship with external validation, and how posting frequency maps to their need to be seen

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# ── Profile distillation ─────────────────────────────────────────────────────

@router.get("/profile")
async def get_instagram_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Instagram profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT instagram_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["instagram_data"]:
        return None
    data = row["instagram_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(profile: dict, media: list[dict]) -> dict:
    """Reduce raw Instagram data to the aesthetic essentials."""
    import re
    from datetime import datetime

    username = profile.get("username", "")
    account_type = profile.get("account_type", "personal")
    media_count = profile.get("media_count", 0)

    # Media type distribution
    type_counts: dict[str, int] = {}
    total_likes = 0
    total_comments = 0
    caption_lengths: list[int] = []
    all_hashtags: list[str] = []
    timestamps: list[datetime] = []

    for item in media:
        media_type = item.get("media_type", "UNKNOWN")
        type_counts[media_type] = type_counts.get(media_type, 0) + 1

        total_likes += item.get("like_count", 0)
        total_comments += item.get("comments_count", 0)

        caption = item.get("caption", "") or ""
        caption_lengths.append(len(caption))

        # Extract hashtags from captions
        hashtags = re.findall(r"#(\w+)", caption)
        all_hashtags.extend(hashtags)

        ts = item.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except (ValueError, AttributeError):
                pass

    n = len(media) or 1

    # Posting frequency (posts per week from recent media timestamps)
    posts_per_week = None
    if len(timestamps) >= 2:
        timestamps.sort()
        span_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400
        if span_days > 0:
            posts_per_week = round(len(timestamps) / (span_days / 7), 1)

    # Top hashtags
    hashtag_counts = Counter(all_hashtags)
    top_hashtags = [tag for tag, _ in hashtag_counts.most_common(15)]

    return {
        "username": username,
        "account_type": account_type,
        "media_count": media_count,
        "media_types": type_counts,
        "recent_count": len(media),
        "avg_caption_length": round(sum(caption_lengths) / n, 1),
        "posts_per_week": posts_per_week,
        "top_hashtags": top_hashtags,
        "avg_likes": round(total_likes / n, 1),
        "avg_comments": round(total_comments / n, 1),
        "total_likes": total_likes,
        "total_comments": total_comments,
    }
