"""
YouTube OAuth + attention data ingestion.

Flow:
  1. GET /youtube/connect  → return auth URL for frontend redirect
  2. GET /youtube/callback → Google redirects back with ?code=&state=
                           → exchange code for tokens
                           → fetch channel info + subscriptions + liked videos
                           → encrypt tokens, store in oauth_tokens
                           → store YouTube profile in vibe_vectors.youtube_data
                           → redirect to frontend
"""

from __future__ import annotations

import json
import logging
from uuid import UUID


import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..oauth_base import OAuthProvider, authorize_url, finish_callback, store_provider_data
from ..llm.chat import chat_completion

logger = logging.getLogger(__name__)
from ..vector.service import upsert_user_vector

router = APIRouter()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
_SCOPES = "https://www.googleapis.com/auth/youtube.readonly"


YOUTUBE = OAuthProvider(
    name="youtube", label="YouTube",
    auth_url=_GOOGLE_AUTH_URL, token_url=_GOOGLE_TOKEN_URL, scopes=_SCOPES,
    client_id=lambda s: s.google_client_id, client_secret=lambda s: s.google_client_secret,
    redirect_uri=lambda s: s.youtube_redirect_uri,
    authorize_params={"access_type": "offline", "prompt": "consent"},
)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def youtube_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the YouTube authorization URL for the authenticated user.
    Frontend fetches this endpoint with Authorization: Bearer header and then
    redirects to the returned auth_url — no JWT in the URL.
    """
    return {"auth_url": authorize_url(YOUTUBE, str(user_id))}


@router.get("/callback")
async def youtube_callback(code: str, state: str):
    """
    Google redirects here (via frontend) after user authorizes.
    Exchanges code for tokens, fetches channel + subscriptions + liked videos, stores everything.
    """
    grant = await finish_callback(YOUTUBE, code, state)
    user_id, access_token = grant.user_id, grant.access_token
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:

            headers = {"Authorization": f"Bearer {access_token}"}

            # 2. Fetch authenticated user's channel info
            channel_resp = await client.get(
                f"{_YOUTUBE_API_BASE}/channels",
                headers=headers,
                params={"part": "snippet,statistics", "mine": "true"},
            )
            channel_data = {}
            if channel_resp.status_code == 200:
                items = channel_resp.json().get("items", [])
                if items:
                    channel_data = items[0]

            # 3. Fetch subscriptions (up to 50)
            subs_resp = await client.get(
                f"{_YOUTUBE_API_BASE}/subscriptions",
                headers=headers,
                params={"part": "snippet", "mine": "true", "maxResults": 50, "order": "relevance"},
            )
            subs_data = []
            if subs_resp.status_code == 200:
                subs_data = subs_resp.json().get("items", [])

            # 4. Fetch liked videos playlist (contentDetails has relatedPlaylists.likes)
            liked_count = 0
            if channel_data:
                content_resp = await client.get(
                    f"{_YOUTUBE_API_BASE}/channels",
                    headers=headers,
                    params={"part": "contentDetails", "mine": "true"},
                )
                if content_resp.status_code == 200:
                    content_items = content_resp.json().get("items", [])
                    if content_items:
                        likes_playlist = (
                            content_items[0]
                            .get("contentDetails", {})
                            .get("relatedPlaylists", {})
                            .get("likes", "")
                        )
                        if likes_playlist:
                            likes_resp = await client.get(
                                f"{_YOUTUBE_API_BASE}/playlists",
                                headers=headers,
                                params={"part": "contentDetails", "id": likes_playlist},
                            )
                            if likes_resp.status_code == 200:
                                pl_items = likes_resp.json().get("items", [])
                                if pl_items:
                                    liked_count = pl_items[0].get("contentDetails", {}).get("itemCount", 0)

        # 5. Distill the attention profile
        youtube_profile = _distill_profile(channel_data, subs_data, liked_count)

        # 7. Store YouTube profile (upserts into vibe_vectors).
        await store_provider_data(user_id, "youtube_data", youtube_profile)

        # 7.5 Auto-trigger Oracle synthesis if enough providers connected
        from ..oracle.trigger import maybe_trigger_synthesis
        await maybe_trigger_synthesis(UUID(user_id))

    except HTTPException:
        raise
    except Exception:
        logger.exception("YouTube callback failed for user %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="YouTube callback failed — check server logs",
        )

    # 8. Fetch intake row to re-embed with YouTube context blended in
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT attachment_style, defense_mechanism, readiness_score FROM vibe_vectors WHERE user_id = $1",
            UUID(user_id),
        )

    # 9. Re-embed with YouTube data so attention signal participates in matching.
    # Skip if intake hasn't been completed (attachment_style is null).
    if row and row["attachment_style"] and row["defense_mechanism"]:
        youtube_summary = _build_embedding_text(youtube_profile)
        confession_base = (
            f"Attachment: {row['attachment_style']}. "
            f"Defense: {row['defense_mechanism']}. "
            f"Readiness: {row['readiness_score']}."
        )
        await upsert_user_vector(
            user_id=user_id,
            confession_text=f"{confession_base} {youtube_summary}",
            attachment_style=row["attachment_style"],
            defense_mechanism=row["defense_mechanism"],
            readiness_score=row["readiness_score"],
        )

    # 10. Redirect to frontend
    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return RedirectResponse(f"{frontend}/calibrate?youtube=connected")


def _build_embedding_text(profile: dict) -> str:
    """Convert YouTube profile to natural-language text for blending into embedding."""
    top_subs = ", ".join(profile.get("top_subscriptions", [])[:10])
    cats = profile.get("subscription_categories", {})
    cats_sorted = sorted(cats.items(), key=lambda kv: -kv[1])[:5]
    cats_str = ", ".join(f"{k} ({v})" for k, v in cats_sorted)
    total = profile.get("total_subscriptions", 0)
    liked = profile.get("liked_videos_count", 0)
    return (
        f"YouTube subscriptions: {top_subs}. "
        f"Attention categories: {cats_str}. "
        f"Total subscriptions: {total}, liked videos: {liked}."
    )


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def youtube_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's YouTube attention profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT youtube_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["youtube_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No YouTube data found")

    data = row["youtube_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_youtube_profile(profile)
    return {"narrative": narrative}


async def _analyze_youtube_profile(profile: dict) -> str:
    channel_name = profile.get("channel_name", "")
    channel_desc = profile.get("channel_description", "")
    subscriber_count = profile.get("subscriber_count", 0)
    video_count = profile.get("video_count", 0)
    view_count = profile.get("view_count", 0)
    top_subs = ", ".join(profile.get("top_subscriptions", [])[:15])
    sub_cats = profile.get("subscription_categories", {})
    cats_str = ", ".join(f"{k}: {v}" for k, v in sub_cats.items())
    total_subs = profile.get("total_subscriptions", 0)
    liked_count = profile.get("liked_videos_count", 0)
    sub_diversity = profile.get("subscription_diversity", 0)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's YouTube data as a window into their attention patterns and aspirations.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's consumption habits and what their subscription choices reveal about their inner life.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Channel name: "{channel_name}"
- Channel description: "{channel_desc[:200]}"
- Subscribers: {subscriber_count} | Videos uploaded: {video_count} | Total views: {view_count}
- Total subscriptions: {total_subs} | Subscription diversity: {sub_diversity} unique channels
- Top subscriptions: {top_subs}
- Subscription categories: {cats_str}
- Liked videos: {liked_count}

Write 2-3 paragraphs analyzing:
1. Attention patterns — what subscription choices and categories reveal about where they direct their finite attention, what they're hungry for, what they're avoiding
2. Consumption vs creation — the ratio of videos uploaded to subscriptions and likes as a signal of passive vs active engagement with the world
3. Aspirational self — what their subscription list reveals about who they want to become, what skills they're acquiring by osmosis, what communities they orbit

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# ── Profile distillation ─────────────────────────────────────────────────────

@router.get("/profile")
async def get_youtube_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored YouTube profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT youtube_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["youtube_data"]:
        return None
    data = row["youtube_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(channel: dict, subscriptions: list[dict], liked_count: int) -> dict:
    """Reduce raw YouTube data to the attention essentials."""
    snippet = channel.get("snippet", {})
    statistics = channel.get("statistics", {})

    # Channel basics
    channel_name = snippet.get("title", "")
    channel_description = snippet.get("description", "")
    published_at = snippet.get("publishedAt", "")

    subscriber_count = int(statistics.get("subscriberCount", 0))
    video_count = int(statistics.get("videoCount", 0))
    view_count = int(statistics.get("viewCount", 0))

    # Top subscriptions (channel names, up to 20)
    top_subs = []
    sub_categories: dict[str, int] = {}
    for sub in subscriptions[:20]:
        sub_snippet = sub.get("snippet", {})
        title = sub_snippet.get("title", "")
        if title:
            top_subs.append(title)
        # Extract category from description if available
        description = sub_snippet.get("description", "")
        if description:
            # Simple keyword-based categorization
            desc_lower = description.lower()
            for category in ["music", "gaming", "education", "comedy", "news", "sports",
                             "science", "technology", "entertainment", "cooking", "fitness",
                             "art", "travel", "fashion", "film"]:
                if category in desc_lower:
                    sub_categories[category] = sub_categories.get(category, 0) + 1

    # Subscription diversity: unique channels / total
    total_subs = len(subscriptions)

    return {
        "channel_name": channel_name,
        "channel_description": channel_description[:500] if channel_description else "",
        "subscriber_count": subscriber_count,
        "video_count": video_count,
        "view_count": view_count,
        "top_subscriptions": top_subs,
        "subscription_categories": sub_categories,
        "total_subscriptions": total_subs,
        "liked_videos_count": liked_count,
        "account_created": published_at,
        "subscription_diversity": len(top_subs),
    }
