"""
Reddit OAuth + psychographic data ingestion.

Flow:
  1. GET /reddit/connect  → return auth URL for frontend redirect
  2. GET /reddit/callback → Reddit redirects back with ?code=&state=
                          → exchange code for tokens (Basic Auth)
                          → fetch user profile + subreddits + comments + saved
                          → encrypt tokens, store in oauth_tokens
                          → store Reddit profile in vibe_vectors.reddit_data
                          → redirect to frontend
"""

from __future__ import annotations

import json
import time
from uuid import UUID


import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..oauth_base import OAuthProvider, authorize_url, finish_callback, store_provider_data
from ..db import get_conn
from ..llm.chat import chat_completion

router = APIRouter()

_REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/authorize"
_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_API_BASE = "https://oauth.reddit.com"
_SCOPES = "identity read history"
_USER_AGENT = "channelzero/1.0"


REDDIT = OAuthProvider(
    name="reddit", label="Reddit",
    auth_url=_REDDIT_AUTH_URL, token_url=_REDDIT_TOKEN_URL, scopes=_SCOPES,
    client_id=lambda s: s.reddit_client_id, client_secret=lambda s: s.reddit_client_secret,
    redirect_uri=lambda s: s.reddit_redirect_uri,
    token_auth="basic", token_headers={"User-Agent": _USER_AGENT},
    authorize_params={"duration": "permanent"},
)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def reddit_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the Reddit authorization URL for the authenticated user.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    """
    return {"auth_url": authorize_url(REDDIT, str(user_id))}


@router.get("/callback")
async def reddit_callback(code: str, state: str):
    """
    Reddit redirects here (via frontend) after user authorizes.
    Exchanges code for tokens, fetches profile + subreddits + comments, stores everything.
    """
    grant = await finish_callback(REDDIT, code, state)
    user_id, access_token = grant.user_id, grant.access_token

    async with httpx.AsyncClient(timeout=20.0) as client:

        api_headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": _USER_AGENT,
        }

        # 2. Fetch user profile
        me_resp = await client.get(f"{_REDDIT_API_BASE}/api/v1/me", headers=api_headers)
        me_data = {}
        if me_resp.status_code == 200:
            me_data = me_resp.json()

        # 3. Fetch subscribed subreddits
        subs_resp = await client.get(
            f"{_REDDIT_API_BASE}/subreddits/mine/subscriber",
            headers=api_headers,
            params={"limit": 100},
        )
        subs_data = []
        if subs_resp.status_code == 200:
            subs_data = subs_resp.json().get("data", {}).get("children", [])

        # 4. Fetch recent comments
        username = me_data.get("name", "")
        comments_data = []
        if username:
            comments_resp = await client.get(
                f"{_REDDIT_API_BASE}/user/{username}/comments",
                headers=api_headers,
                params={"limit": 50, "sort": "new"},
            )
            if comments_resp.status_code == 200:
                comments_data = comments_resp.json().get("data", {}).get("children", [])

        # 5. Fetch saved posts
        saved_data = []
        if username:
            saved_resp = await client.get(
                f"{_REDDIT_API_BASE}/user/{username}/saved",
                headers=api_headers,
                params={"limit": 50},
            )
            if saved_resp.status_code == 200:
                saved_data = saved_resp.json().get("data", {}).get("children", [])

        # 6. Fetch trophies
        trophies_data = []
        if username:
            trophies_resp = await client.get(
                f"{_REDDIT_API_BASE}/api/v1/me/trophies",
                headers=api_headers,
            )
            if trophies_resp.status_code == 200:
                trophies_data = trophies_resp.json().get("data", {}).get("trophies", [])

    # 7. Distill the psychographic profile
    reddit_profile = _distill_profile(me_data, subs_data, comments_data, saved_data, trophies_data)

    # 9. Store Reddit profile (upserts into vibe_vectors).
    await store_provider_data(user_id, "reddit_data", reddit_profile)

    # Auto-trigger Oracle synthesis if enough providers connected
    from ..oracle.trigger import maybe_trigger_synthesis
    await maybe_trigger_synthesis(UUID(user_id))

    # 10. Return success — frontend handles navigation
    return JSONResponse({"status": "connected", "username": reddit_profile.get("username", "")})


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def reddit_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Reddit psychographic profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT reddit_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["reddit_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Reddit data found")

    data = row["reddit_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_reddit_profile(profile)
    return {"narrative": narrative}


async def _analyze_reddit_profile(profile: dict) -> str:
    username = profile.get("username", "")
    total_karma = profile.get("total_karma", 0)
    link_karma = profile.get("link_karma", 0)
    comment_karma = profile.get("comment_karma", 0)
    karma_ratio = profile.get("comment_karma_ratio")
    account_age = profile.get("account_age_days", 0)
    top_subs = profile.get("top_subreddits", [])
    top_subs_str = ", ".join(s.get("name", "") for s in top_subs[:15])
    comment_subs = profile.get("comment_subreddits", [])
    comment_subs_str = ", ".join(f'{s.get("name", "")}: {s.get("count", 0)}' for s in comment_subs[:10])
    diversity = profile.get("subreddit_diversity", 0)
    trophies = ", ".join(profile.get("trophies", []))
    active_hours = profile.get("active_hours", {})
    peak_hour = max(active_hours, key=active_hours.get) if active_hours else "N/A"

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Reddit data as a window into their anonymous self and hidden interests.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's community belonging patterns and what their subreddit choices reveal about their inner life.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Username: {username}
- Total karma: {total_karma} (link: {link_karma}, comment: {comment_karma})
- Comment karma ratio: {karma_ratio or 'N/A'} (1.0 = pure commenter, 0.0 = pure poster)
- Account age: {account_age} days
- Subreddit diversity: {diversity} unique communities
- Top subscribed subreddits: {top_subs_str}
- Most active comment subreddits: {comment_subs_str}
- Peak activity hour (UTC): {peak_hour}
- Trophies: {trophies or 'none'}

Write 2-3 paragraphs analyzing:
1. The anonymous self — what subreddit subscriptions reveal about the interests, curiosities, and vulnerabilities they explore when nobody from their real life is watching
2. Community belonging patterns — where they comment vs. where they lurk, what the gap between subscriptions and active participation reveals about their social needs
3. The lurker-contributor spectrum — karma ratio, posting patterns, and what their relationship with Reddit reveals about their need for validation vs. voyeuristic consumption

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# ── Profile distillation ─────────────────────────────────────────────────────

@router.get("/profile")
async def get_reddit_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Reddit profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT reddit_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["reddit_data"]:
        return None
    data = row["reddit_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(
    me: dict,
    subreddits: list[dict],
    comments: list[dict],
    saved: list[dict],
    trophies: list[dict],
) -> dict:
    """Reduce raw Reddit data to psychographic essentials."""
    # Identity basics
    username = me.get("name", "")
    link_karma = me.get("link_karma", 0)
    comment_karma = me.get("comment_karma", 0)
    total_karma = link_karma + comment_karma
    created_utc = me.get("created_utc", 0)
    account_age_days = int((time.time() - created_utc) / 86400) if created_utc else 0

    # Karma ratio — lurker vs contributor signal
    karma_ratio = None
    if total_karma > 0:
        karma_ratio = round(comment_karma / total_karma, 3)

    # Top subreddits
    top_subs = []
    for s in subreddits:
        sub = s.get("data", {})
        top_subs.append({
            "name": sub.get("display_name", ""),
            "subscribers": sub.get("subscribers", 0),
        })
    top_subs.sort(key=lambda x: x["subscribers"], reverse=True)
    top_subs = top_subs[:30]

    # Comment activity — subreddit distribution + active hours
    comment_subs: dict[str, int] = {}
    active_hours: dict[int, int] = {}
    for c in comments:
        cd = c.get("data", {})
        sub = cd.get("subreddit", "")
        if sub:
            comment_subs[sub] = comment_subs.get(sub, 0) + 1
        created = cd.get("created_utc", 0)
        if created:
            hour = int((created % 86400) / 3600)
            active_hours[hour] = active_hours.get(hour, 0) + 1

    # Sort comment subs by frequency
    top_comment_subs = sorted(comment_subs.items(), key=lambda x: x[1], reverse=True)[:20]

    # Subreddit category diversity (unique subreddits across all signals)
    all_sub_names = set()
    for s in subreddits:
        name = s.get("data", {}).get("display_name", "")
        if name:
            all_sub_names.add(name)
    for sub_name, _ in top_comment_subs:
        all_sub_names.add(sub_name)

    # Trophy count
    trophy_count = len(trophies)
    trophy_names = [t.get("data", {}).get("name", "") for t in trophies if t.get("data", {}).get("name")]

    return {
        "username": username,
        "total_karma": total_karma,
        "link_karma": link_karma,
        "comment_karma": comment_karma,
        "comment_karma_ratio": karma_ratio,
        "account_age_days": account_age_days,
        "top_subreddits": top_subs,
        "comment_subreddits": [{"name": n, "count": c} for n, c in top_comment_subs],
        "active_hours": active_hours,
        "subreddit_diversity": len(all_sub_names),
        "trophy_count": trophy_count,
        "trophies": trophy_names[:10],
        "recent_comments_analyzed": len(comments),
        "saved_posts_analyzed": len(saved),
    }
