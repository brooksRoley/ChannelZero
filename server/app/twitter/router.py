"""
Twitter/X OAuth 2.0 PKCE + data ingestion.

The auth/oauth.py module handles X login (identity only).
This module handles the *data* connector — a separate OAuth flow that
requests tweet.read + like.read + follows.read scopes, stores the token,
and fetches behavioral data for the Oracle's "Neurotic Output" dimension.

Flow:
  1. GET /twitter/connect  → Authorization: Bearer <JWT> header → return auth URL (PKCE, client-side redirect)
  2. GET /twitter/callback?code=&state= → exchange code, fetch data, store

NOTE: tweet.read beyond basic user.read requires X API Basic tier ($100/mo).
If the app only has Free tier, the data fetch gracefully degrades.
"""

from __future__ import annotations

import base64
import json
import time
import hashlib
from collections import Counter
from urllib.parse import urlencode
from uuid import UUID

import secrets

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse

from ..oauth_base import store_provider_data
from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..llm.encryption import encrypt_api_key
from ..llm.chat import chat_completion

router = APIRouter()

_X_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
_X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
_X_API_BASE = "https://api.twitter.com/2"
_SCOPES = "tweet.read users.read like.read follows.read offline.access"


# ── State helpers ─────────────────────────────────────────────────────────────

def _make_state(user_id: str, code_verifier: str) -> str:
    """Encode user_id + PKCE verifier into the state JWT."""
    nonce = secrets.token_urlsafe(16)
    payload = {
        "sub": user_id,
        "nonce": nonce,
        "cv": code_verifier,
        "exp": int(time.time()) + 600,
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def _verify_state(state: str) -> tuple[str, str]:
    """Returns (user_id, code_verifier)."""
    try:
        payload = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc

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

    return payload["sub"], payload["cv"]


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/connect")
async def twitter_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the X OAuth2 authorization URL with data scopes.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    PKCE verifier is generated server-side and embedded in the state JWT.
    """
    settings = get_settings()
    if not settings.x_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="X/Twitter not configured")

    code_verifier = secrets.token_urlsafe(43)
    code_challenge = _pkce_challenge(code_verifier)
    state = _make_state(str(user_id), code_verifier)

    params = {
        "response_type": "code",
        "client_id": settings.x_client_id,
        "redirect_uri": settings.twitter_data_redirect_uri,
        "scope": _SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return {"auth_url": f"{_X_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
async def twitter_callback(code: str, state: str):
    """Exchange code for tokens, fetch behavioral data, store."""
    user_id, code_verifier = await _verify_state(state)
    settings = get_settings()

    auth_str = base64.b64encode(
        f"{settings.x_client_id}:{settings.x_client_secret}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Exchange code for tokens
        token_resp = await client.post(
            _X_TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth_str}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": settings.x_client_id,
                "redirect_uri": settings.twitter_data_redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"X token exchange failed: {token_resp.text}",
            )

        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 7200)
        expires_at = int(time.time()) + expires_in

        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Fetch user profile
        me_resp = await client.get(
            f"{_X_API_BASE}/users/me",
            headers=headers,
            params={"user.fields": "public_metrics,description,created_at"},
        )
        me_data = {}
        if me_resp.status_code == 200:
            me_data = me_resp.json().get("data", {})

        # 3. Fetch recent tweets (may require Basic tier)
        tweets = []
        user_x_id = me_data.get("id", "")
        if user_x_id:
            tweets_resp = await client.get(
                f"{_X_API_BASE}/users/{user_x_id}/tweets",
                headers=headers,
                params={
                    "max_results": 20,
                    "tweet.fields": "created_at,public_metrics,lang",
                    "exclude": "retweets",
                },
            )
            if tweets_resp.status_code == 200:
                tweets = tweets_resp.json().get("data", [])

        # 4. Fetch liked tweets (may require Basic tier)
        likes = []
        if user_x_id:
            likes_resp = await client.get(
                f"{_X_API_BASE}/users/{user_x_id}/liked_tweets",
                headers=headers,
                params={"max_results": 20, "tweet.fields": "created_at,public_metrics"},
            )
            if likes_resp.status_code == 200:
                likes = likes_resp.json().get("data", [])

        # 5. Fetch following count
        following = []
        if user_x_id:
            follow_resp = await client.get(
                f"{_X_API_BASE}/users/{user_x_id}/following",
                headers=headers,
                params={"max_results": 50, "user.fields": "public_metrics,description"},
            )
            if follow_resp.status_code == 200:
                following = follow_resp.json().get("data", [])

    # 6. Distill neurotic profile
    twitter_profile = _distill_profile(me_data, tweets, likes, following)

    # 7. Store tokens
    enc_access, access_nonce = encrypt_api_key(access_token)
    enc_refresh, refresh_nonce = encrypt_api_key(refresh_token) if refresh_token else (None, None)

    from datetime import datetime, timezone
    expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO oauth_tokens
                (user_id, provider, encrypted_access_token, access_nonce,
                 encrypted_refresh_token, refresh_nonce, expires_at, scope)
            VALUES ($1, 'twitter', $2, $3, $4, $5, $6, $7)
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

    await store_provider_data(user_id, "twitter_data", twitter_profile)

    # Auto-trigger Oracle synthesis if enough providers connected
    from ..oracle.trigger import maybe_trigger_synthesis
    await maybe_trigger_synthesis(UUID(user_id))

    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return RedirectResponse(f"{frontend}/calibrate?twitter=connected")


# ── Profile read ──────────────────────────────────────────────────────────────

@router.get("/profile")
async def twitter_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Twitter/X distilled profile for the current user."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT twitter_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["twitter_data"]:
        return None
    data = row["twitter_data"]
    return json.loads(data) if isinstance(data, str) else data


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def twitter_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's X/Twitter profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT twitter_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["twitter_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Twitter data found")

    data = row["twitter_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_twitter_profile(profile)
    return {"narrative": narrative}


async def _analyze_twitter_profile(profile: dict) -> str:
    followers = profile.get("followers", 0)
    following = profile.get("following_count", 0)
    tweet_count = profile.get("tweet_count", 0)
    listed = profile.get("listed_count", 0)
    bio = profile.get("bio", "")
    avg_len = profile.get("avg_tweet_length", 0)
    likes_given = profile.get("recent_likes_given", 0)
    high_profile = profile.get("high_profile_follows", 0)
    samples = profile.get("tweet_samples", [])
    engagement_avg = profile.get("engagement_avg", {})
    top_lang = profile.get("language", "en")

    ff_ratio = round(followers / following, 2) if following > 0 else followers
    sample_text = "\n".join(f'- "{s}"' for s in samples[:5]) if samples else "(unavailable)"

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's X/Twitter digital footprint.
Your task: write a sharp, warm, 3-paragraph psychoanalysis of this user's neurotic output patterns.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Followers: {followers} | Following: {following} | Follower/Following ratio: {ff_ratio}
- Total tweets ever: {tweet_count} | Listed by others: {listed}
- Bio: "{bio}"
- Recent avg tweet length: {avg_len} chars
- Likes given (passive engagement): {likes_given} in last 20 loaded
- High-profile accounts followed (100k+ followers): {high_profile}
- Avg engagement received per tweet: {engagement_avg.get('likes', 0):.1f} likes, {engagement_avg.get('retweets', 0):.1f} retweets
- Primary language: {top_lang}
- Sample tweets:
{sample_text}

Write 3 paragraphs analyzing:
1. Communication style and self-presentation — what tweet length, language, and bio reveal
2. Social positioning — follower/following ratio, high-profile follows, listed count as influence signals
3. Engagement psychology — passive consumption vs. active expression, what they amplify and why

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_profile(
    me: dict, tweets: list[dict], likes: list[dict], following: list[dict]
) -> dict:
    """Reduce raw X data to neurotic output patterns."""
    metrics = me.get("public_metrics", {})
    username = me.get("username", "")

    # Tweet posting patterns
    tweet_texts = [t.get("text", "") for t in tweets]
    avg_tweet_len = round(
        sum(len(t) for t in tweet_texts) / len(tweet_texts), 1
    ) if tweet_texts else 0

    # Per-tweet engagement averages
    likes_per_tweet = [t.get("public_metrics", {}).get("like_count", 0) for t in tweets]
    rt_per_tweet = [t.get("public_metrics", {}).get("retweet_count", 0) for t in tweets]
    avg_likes = round(sum(likes_per_tweet) / len(likes_per_tweet), 1) if likes_per_tweet else 0
    avg_rts = round(sum(rt_per_tweet) / len(rt_per_tweet), 1) if rt_per_tweet else 0

    # Posting hour distribution (UTC)
    hour_counts: Counter = Counter()
    for t in tweets:
        created = t.get("created_at", "")
        if created and "T" in created:
            try:
                hour = int(created.split("T")[1][:2])
                hour_counts[str(hour)] += 1
            except (ValueError, IndexError):
                pass

    # Language distribution
    lang_counts: Counter = Counter(t.get("lang", "und") for t in tweets if t.get("lang"))
    top_lang = lang_counts.most_common(1)[0][0] if lang_counts else "en"

    # Tweet samples — clean URLs, keep first 120 chars
    samples = []
    for t in tweets[:5]:
        text = t.get("text", "")
        # Strip URLs
        cleaned = " ".join(w for w in text.split() if not w.startswith("http"))
        if len(cleaned) > 10:
            samples.append(cleaned[:120])

    # Engagement ratios
    total_likes_given = len(likes)
    total_tweets_fetched = len(tweets)

    # Following analysis — high-follower accounts they follow
    high_profile_follows = sum(
        1 for f in following
        if f.get("public_metrics", {}).get("followers_count", 0) > 100_000
    )

    return {
        "username": username,
        "followers": metrics.get("followers_count", 0),
        "following_count": metrics.get("following_count", 0),
        "tweet_count": metrics.get("tweet_count", 0),
        "listed_count": metrics.get("listed_count", 0),
        "bio": me.get("description", ""),
        "recent_tweet_count": total_tweets_fetched,
        "avg_tweet_length": avg_tweet_len,
        "recent_likes_given": total_likes_given,
        "high_profile_follows": high_profile_follows,
        "account_created": me.get("created_at", ""),
        "engagement_avg": {"likes": avg_likes, "retweets": avg_rts},
        "posting_hours": dict(hour_counts),
        "language": top_lang,
        "tweet_samples": samples,
    }
