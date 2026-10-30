"""
TikTok OAuth + attention data ingestion.

Flow:
  1. GET /tiktok/connect  → return auth URL for frontend redirect
  2. GET /tiktok/callback → TikTok redirects back with ?code=&state=
                          → exchange code for tokens
                          → fetch user info + video list
                          → encrypt tokens, store in oauth_tokens
                          → store TikTok profile in vibe_vectors.tiktok_data
                          → redirect to frontend
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from uuid import UUID


from ..oracle.trigger import maybe_trigger_synthesis

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from ..auth.deps import get_current_user_id
from ..oauth_base import OAuthProvider, authorize_url, finish_callback, store_provider_data
from ..config import get_settings
from ..db import get_conn
from ..llm.chat import chat_completion

router = APIRouter()

_TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
_SCOPES = "user.info.basic,video.list"


TIKTOK = OAuthProvider(
    name="tiktok", label="TikTok",
    auth_url=_TIKTOK_AUTH_URL, token_url=_TIKTOK_TOKEN_URL, scopes=_SCOPES,
    client_id=lambda s: s.tiktok_client_key, client_secret=lambda s: s.tiktok_client_secret,
    redirect_uri=lambda s: s.tiktok_redirect_uri,
    client_id_param="client_key", default_expires_in=86400,
)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def tiktok_connect(user_id: UUID = Depends(get_current_user_id)):
    """Return the TikTok authorization URL for the authenticated user.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL."""
    return {"auth_url": authorize_url(TIKTOK, str(user_id))}


@router.get("/callback")
async def tiktok_callback(code: str, state: str):
    """Exchange code for tokens, fetch profile data, store."""
    grant = await finish_callback(TIKTOK, code, state)
    user_id, access_token = grant.user_id, grant.access_token
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:

        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Fetch user info
        user_fields = "open_id,union_id,avatar_url,display_name,bio_description,is_verified,follower_count,following_count,likes_count,video_count"
        user_resp = await client.get(
            f"{_TIKTOK_API_BASE}/user/info/",
            headers=headers,
            params={"fields": user_fields},
        )
        user_data = {}
        if user_resp.status_code == 200:
            resp_json = user_resp.json()
            user_data = resp_json.get("data", {}).get("user", {})

        # 3. Fetch recent videos (POST endpoint)
        videos = []
        video_fields = "id,title,create_time,video_description,duration,like_count,comment_count,share_count,view_count"
        video_resp = await client.post(
            f"{_TIKTOK_API_BASE}/video/list/",
            headers={**headers, "Content-Type": "application/json"},
            params={"fields": video_fields},
            json={"max_count": 20},
        )
        if video_resp.status_code == 200:
            resp_json = video_resp.json()
            videos = resp_json.get("data", {}).get("videos", [])

    # 4. Distill profile
    tiktok_profile = _distill_profile(user_data, videos)

    await store_provider_data(user_id, "tiktok_data", tiktok_profile)

    await maybe_trigger_synthesis(UUID(user_id))

    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return RedirectResponse(f"{frontend}/calibrate?tiktok=connected")


@router.get("/analyze")
async def tiktok_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's TikTok behavioral profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT tiktok_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["tiktok_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No TikTok data found")

    data = row["tiktok_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_tiktok_profile(profile)
    return {"narrative": narrative}


async def _analyze_tiktok_profile(profile: dict) -> str:
    display_name = profile.get("display_name", "")
    bio = profile.get("bio", "")
    is_verified = profile.get("is_verified", False)
    follower_count = profile.get("follower_count", 0)
    following_count = profile.get("following_count", 0)
    likes_received = profile.get("likes_received", 0)
    video_count = profile.get("video_count", 0)
    avg_duration = profile.get("avg_duration_sec", 0)
    avg_likes = profile.get("avg_likes_per_video", 0)
    avg_comments = profile.get("avg_comments_per_video", 0)
    avg_shares = profile.get("avg_shares_per_video", 0)
    avg_views = profile.get("avg_views_per_video", 0)
    top_hashtags = ", ".join(profile.get("top_hashtags", []))
    posting_hours = profile.get("posting_hours", {})
    peak_hour = max(posting_hours, key=posting_hours.get) if posting_hours else "N/A"

    ff_ratio = round(follower_count / max(following_count, 1), 2)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's TikTok data as a window into their dopamine sensitivity and attention patterns.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's algorithmic self vs intentional self.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Display name: "{display_name}"
- Bio: "{bio}"
- Verified: {is_verified}
- Followers: {follower_count} | Following: {following_count} | Ratio: {ff_ratio}
- Total likes received: {likes_received}
- Videos: {video_count} | Avg duration: {avg_duration}s
- Avg likes/video: {avg_likes} | Avg comments: {avg_comments} | Avg shares: {avg_shares} | Avg views: {avg_views}
- Top hashtags: {top_hashtags}
- Peak posting hour (UTC): {peak_hour}

Write 2-3 paragraphs analyzing:
1. Dopamine sensitivity — what video duration, posting frequency, and engagement patterns reveal about their attention span, their tolerance for slow rewards, and how the algorithm has shaped their creative output
2. Algorithmic self vs intentional self — what hashtag choices and content patterns reveal about whether they're creating for the algorithm or for themselves, the tension between virality and authenticity
3. Attention economy position — follower/following ratio, engagement metrics, and what their relationship with TikTok reveals about their need for immediate feedback vs. sustained creative practice

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


@router.get("/profile")
async def get_tiktok_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored TikTok profile for the current user."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT tiktok_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["tiktok_data"]:
        return None
    data = row["tiktok_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(user: dict, videos: list[dict]) -> dict:
    """Reduce raw TikTok data to behavioral essentials."""
    display_name = user.get("display_name", "")
    bio = user.get("bio_description", "")
    follower_count = user.get("follower_count", 0)
    following_count = user.get("following_count", 0)
    likes_count = user.get("likes_count", 0)
    video_count = user.get("video_count", 0)
    is_verified = user.get("is_verified", False)

    # Video analysis
    durations: list[float] = []
    total_likes = 0
    total_comments = 0
    total_shares = 0
    total_views = 0
    descriptions: list[str] = []
    hashtags: Counter = Counter()
    hour_counts: Counter = Counter()

    for v in videos:
        dur = v.get("duration", 0)
        if dur:
            durations.append(dur)

        total_likes += v.get("like_count", 0)
        total_comments += v.get("comment_count", 0)
        total_shares += v.get("share_count", 0)
        total_views += v.get("view_count", 0)

        desc = v.get("video_description", "") or v.get("title", "")
        if desc:
            descriptions.append(desc)
            # Extract hashtags
            tags = re.findall(r"#(\w+)", desc)
            for tag in tags:
                hashtags[tag.lower()] += 1

        create_time = v.get("create_time", 0)
        if create_time:
            try:
                hour = time.gmtime(create_time).tm_hour
                hour_counts[str(hour)] += 1
            except (ValueError, OSError):
                pass

    n_videos = len(videos) if videos else 1

    # Engagement averages
    avg_likes = round(total_likes / n_videos, 1) if videos else 0
    avg_comments = round(total_comments / n_videos, 1) if videos else 0
    avg_shares = round(total_shares / n_videos, 1) if videos else 0
    avg_views = round(total_views / n_videos, 1) if videos else 0

    # Average duration
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

    # Top hashtags
    top_hashtags = [tag for tag, _ in hashtags.most_common(10)]

    return {
        "display_name": display_name,
        "bio": bio,
        "is_verified": is_verified,
        "follower_count": follower_count,
        "following_count": following_count,
        "likes_received": likes_count,
        "video_count": video_count,
        "recent_video_count": len(videos),
        "avg_duration_sec": avg_duration,
        "avg_likes_per_video": avg_likes,
        "avg_comments_per_video": avg_comments,
        "avg_shares_per_video": avg_shares,
        "avg_views_per_video": avg_views,
        "top_hashtags": top_hashtags,
        "posting_hours": dict(hour_counts),
    }
