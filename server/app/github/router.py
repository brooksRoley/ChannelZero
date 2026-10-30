"""
GitHub OAuth + developer profile ingestion.

Flow:
  1. GET /github/connect  -> return auth URL for frontend redirect
  2. GET /github/callback -> GitHub redirects back with ?code=&state=
                           -> exchange code for tokens
                           -> fetch user profile + repos + starred repos
                           -> encrypt tokens, store in oauth_tokens
                           -> store GitHub profile in vibe_vectors.github_data
                           -> redirect to frontend
"""

from __future__ import annotations

import json
from collections import Counter
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..llm.chat import chat_completion
from ..oauth_base import (
    OAuthProvider,
    authorize_url,
    finish_callback,
    store_provider_data,
)

router = APIRouter()

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_API_BASE = "https://api.github.com"
_SCOPES = "read:user repo"

GITHUB = OAuthProvider(
    name="github", label="GitHub",
    auth_url=_GITHUB_AUTH_URL, token_url=_GITHUB_TOKEN_URL, scopes=_SCOPES,
    client_id=lambda s: s.github_client_id, client_secret=lambda s: s.github_client_secret,
    redirect_uri=lambda s: s.github_redirect_uri,
    default_expires_in=None,
)


# -- Routes --------------------------------------------------------------------

@router.get("/connect")
async def github_connect(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the GitHub authorization URL for the authenticated user.
    Frontend fetches with Authorization: Bearer header — no JWT in the URL.
    """
    return {"auth_url": authorize_url(GITHUB, str(user_id))}


@router.get("/callback")
async def github_callback(code: str, state: str):
    """
    GitHub redirects here (via frontend) after user authorizes.
    Exchanges code for tokens, fetches user profile + repos + stars, stores everything.
    """
    grant = await finish_callback(GITHUB, code, state)
    user_id, access_token = grant.user_id, grant.access_token
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }

        # 2. Fetch user profile
        user_resp = await client.get(f"{_GITHUB_API_BASE}/user", headers=headers)
        user_data = {}
        if user_resp.status_code == 200:
            user_data = user_resp.json()

        # 3. Fetch repos (up to 100, sorted by recent push)
        repos_resp = await client.get(
            f"{_GITHUB_API_BASE}/user/repos",
            headers=headers,
            params={"per_page": 100, "sort": "pushed", "direction": "desc"},
        )
        repos_data = []
        if repos_resp.status_code == 200:
            repos_data = repos_resp.json()

        # 4. Fetch starred repos (up to 100)
        starred_resp = await client.get(
            f"{_GITHUB_API_BASE}/user/starred",
            headers=headers,
            params={"per_page": 100},
        )
        starred_data = []
        if starred_resp.status_code == 200:
            starred_data = starred_resp.json()

    # 5. Distill the developer profile
    github_profile = _distill_profile(user_data, repos_data, starred_data)

    # 6. Store github_id on user
    async with get_conn() as conn:
        github_id = str(user_data.get("id", ""))
        if github_id:
            await conn.execute(
                "UPDATE users SET github_id = $1, updated_at = now() WHERE id = $2",
                github_id, UUID(user_id),
            )

    # 8. Store GitHub profile on vibe_vectors row (if intake already done)
    await store_provider_data(user_id, "github_data", github_profile)

    # Auto-trigger Oracle synthesis if enough providers connected
    from ..oracle.trigger import maybe_trigger_synthesis
    await maybe_trigger_synthesis(UUID(user_id))

    # 9. Return success — frontend handles navigation
    return JSONResponse({"status": "connected", "username": github_profile.get("username", "")})


# ── Psychoanalysis ────────────────────────────────────────────────────────────

@router.get("/analyze")
async def github_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's GitHub developer profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT github_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["github_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No GitHub data found")

    data = row["github_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_github_profile(profile)
    return {"narrative": narrative}


async def _analyze_github_profile(profile: dict) -> str:
    username = profile.get("username", "")
    bio = profile.get("bio", "")
    company = profile.get("company", "")
    public_repos = profile.get("public_repos", 0)
    followers = profile.get("followers", 0)
    following = profile.get("following", 0)
    top_langs = ", ".join(profile.get("top_languages", []))
    stars_given = profile.get("stars_given", 0)
    repos_owned = profile.get("repos_owned", 0)
    repos_forked = profile.get("repos_forked", 0)
    owned_to_forked = profile.get("owned_to_forked_ratio", 0)
    age = profile.get("account_age_years")
    topics = ", ".join(profile.get("topics", [])[:20])
    descriptions = profile.get("repo_descriptions", [])
    desc_text = "\n".join(f'- "{d}"' for d in descriptions[:10]) if descriptions else "(unavailable)"

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's GitHub profile as a window into their builder identity and creative patterns.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's developer psychology and what their code reveals about their thought patterns.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Username: {username}
- Bio: "{bio}"
- Company: "{company}"
- Public repos: {public_repos} | Followers: {followers} | Following: {following}
- Top languages: {top_langs}
- Stars given (curiosity signal): {stars_given}
- Repos owned: {repos_owned} | Repos forked: {repos_forked} | Owned/forked ratio: {owned_to_forked}
- Account age: {age} years
- Topics/interests: {topics}
- Repo descriptions:
{desc_text}

Write 2-3 paragraphs analyzing:
1. Builder identity — what language choices, repo descriptions, and topics reveal about how they think, what problems attract them, their aesthetic sensibility in code
2. Creative patterns — solo vs collaborative tendencies (owned vs forked ratio), curiosity breadth (stars given), and what their GitHub presence says about their relationship with making things
3. Social positioning in the developer world — followers, following, bio as identity performance, and what the gap between public repos and stars reveals about recognition needs

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


# -- Profile endpoint ----------------------------------------------------------

@router.get("/profile")
async def get_github_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored GitHub profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT github_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["github_data"]:
        return None
    data = row["github_data"]
    return json.loads(data) if isinstance(data, str) else data


# -- Profile distillation ------------------------------------------------------

def _distill_profile(user: dict, repos: list[dict], starred: list[dict]) -> dict:
    """Reduce raw GitHub data to the developer essentials."""
    # Language aggregation
    lang_counts: Counter[str] = Counter()
    forked_count = 0
    owned_count = 0
    topics: list[str] = []
    descriptions: list[str] = []

    for r in repos:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
        if r.get("fork"):
            forked_count += 1
        else:
            owned_count += 1
        for t in r.get("topics", []):
            topics.append(t)
        desc = r.get("description")
        if desc:
            descriptions.append(desc)

    top_languages = [lang for lang, _ in lang_counts.most_common(10)]

    # Account age
    created_at = user.get("created_at", "")
    account_age_years = None
    if created_at:
        from datetime import datetime, timezone
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            delta = datetime.now(tz=timezone.utc) - created
            account_age_years = round(delta.days / 365.25, 1)
        except (ValueError, TypeError):
            pass

    return {
        "username": user.get("login", ""),
        "bio": user.get("bio", ""),
        "company": user.get("company", ""),
        "location": user.get("location", ""),
        "public_repos": user.get("public_repos", 0),
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "top_languages": top_languages,
        "stars_given": len(starred),
        "repos_owned": owned_count,
        "repos_forked": forked_count,
        "owned_to_forked_ratio": round(owned_count / max(forked_count, 1), 2),
        "account_age_years": account_age_years,
        "topics": list(set(topics))[:30],
        "repo_descriptions": descriptions[:20],
    }
