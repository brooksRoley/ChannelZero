"""
Spotify OAuth + data ingestion.

Flow:
  1. GET /spotify/connect  → redirect user to Spotify authorization page
  2. GET /spotify/callback → Spotify redirects back with ?code=&state=
                             → exchange code for tokens
                             → fetch top artists + audio features
                             → encrypt tokens, store in oauth_tokens
                             → store Spotify profile in vibe_vectors.spotify_data
                             → re-embed user's vibe vector with Spotify context blended in
                             → redirect to frontend
"""

from __future__ import annotations

import json
import time
from uuid import UUID

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..vector.service import upsert_user_vector
from ..llm.chat import chat_completion
from ..oauth_base import (
    build_authorize_url,
    make_oauth_state,
    store_oauth_tokens,
    store_provider_data,
    validate_connect_token,
    verify_oauth_state,
)

router = APIRouter()

_SPOTIFY_AUTH_URL  = "https://accounts.spotify.com/authorize"
_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_API_BASE = "https://api.spotify.com/v1"
_SCOPES = "user-top-read user-read-recently-played"


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_spotify_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Spotify profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT spotify_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["spotify_data"]:
        return None
    data = row["spotify_data"]
    return json.loads(data) if isinstance(data, str) else data


@router.post("/sync")
async def spotify_sync(user_id: UUID = Depends(get_current_user_id)):
    """Re-fetch Spotify profile using stored refresh token.

    Covers users who connected before data ingestion was wired into the
    callback, or whose token expired. Refreshes the access token, re-fetches
    top artists + tracks + audio features, and stores the distilled profile.
    """
    from ..oauth_base import get_stored_tokens

    settings = get_settings()
    tokens = await get_stored_tokens(str(user_id), "spotify")
    if not tokens or not tokens.get("refresh_token"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Spotify tokens found — please reconnect on /calibrate",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Refresh the access token
            refresh_resp = await client.post(
                _SPOTIFY_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                },
                auth=(settings.spotify_client_id, settings.spotify_client_secret),
            )
            if refresh_resp.status_code != 200:
                logger.warning("Spotify token refresh failed: %s %s", refresh_resp.status_code, refresh_resp.text[:200])
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Spotify token refresh failed — please reconnect on /calibrate",
                )
            refreshed = refresh_resp.json()
            access_token = refreshed["access_token"]
            new_refresh = refreshed.get("refresh_token", tokens["refresh_token"])
            expires_at = int(time.time()) + refreshed.get("expires_in", 3600)

            await store_oauth_tokens(
                str(user_id), "spotify", access_token, new_refresh, expires_at,
                refreshed.get("scope", ""),
            )

            headers = {"Authorization": f"Bearer {access_token}"}
            spotify_profile = await _ingest_spotify_data(client, headers, str(user_id))

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Spotify API timed out — try again")
    except Exception as exc:
        logger.exception("Spotify sync failed for user %s", user_id)
        raise HTTPException(status_code=502, detail=f"Spotify sync error: {exc}")

    # Re-trigger Oracle synthesis (non-blocking)
    try:
        from ..oracle.trigger import maybe_trigger_synthesis
        await maybe_trigger_synthesis(user_id)
    except Exception:
        logger.exception("Oracle synthesis trigger failed for user %s (non-blocking)", user_id)

    return {"status": "synced", "profile": spotify_profile}


@router.get("/connect")
async def spotify_connect(ct: str = Query(..., description="Short-lived connect token")):
    """
    Redirect the authenticated user to Spotify's authorization page.
    Accepts a short-lived connect token (?ct=) minted by POST /api/auth/connect-token.
    """
    settings = get_settings()
    if not settings.spotify_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Spotify not configured")

    payload = await validate_connect_token(ct)

    url = build_authorize_url(
        _SPOTIFY_AUTH_URL,
        client_id=settings.spotify_client_id,
        redirect_uri=settings.spotify_redirect_uri,
        scope=_SCOPES,
        state=make_oauth_state(payload["sub"]),
        extra_params={"show_dialog": "false"},
    )
    resp = RedirectResponse(url)
    # Prevent the ?ct= token from leaking to Spotify via the Referer header.
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/callback")
async def spotify_callback(code: str, state: str):
    """
    Spotify redirects here after user authorizes.
    Exchanges code for tokens, fetches audio profile, stores everything.
    """
    user_id = await verify_oauth_state(state)
    settings = get_settings()

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Exchange authorization code for access + refresh tokens
        token_resp = await client.post(
            _SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
            auth=(settings.spotify_client_id, settings.spotify_client_secret),
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)
        scope = tokens.get("scope", "")
        expires_at = int(time.time()) + expires_in

        headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Fetch, distill, and store the Spotify profile
        spotify_profile = await _ingest_spotify_data(client, headers, user_id)

    # 3. Store tokens via shared helper
    await store_oauth_tokens(
        user_id, "spotify", access_token, refresh_token, expires_at, scope,
    )

    # 4. Auto-trigger Oracle synthesis if enough providers connected
    from ..oracle.trigger import maybe_trigger_synthesis
    await maybe_trigger_synthesis(UUID(user_id))

    # 5. Re-embed with Spotify context — richer psychological coordinate.
    # Skip if intake hasn't been completed (attachment_style is null).
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT attachment_style, defense_mechanism, readiness_score FROM vibe_vectors WHERE user_id = $1",
            UUID(user_id),
        )

    if row and row["attachment_style"] and row["defense_mechanism"]:
        spotify_summary = _build_embedding_text(spotify_profile)
        confession_base = (
            f"Attachment: {row['attachment_style']}. "
            f"Defense: {row['defense_mechanism']}. "
            f"Readiness: {row['readiness_score']}."
        )
        await upsert_user_vector(
            user_id=user_id,
            confession_text=f"{confession_base} {spotify_summary}",
            attachment_style=row["attachment_style"],
            defense_mechanism=row["defense_mechanism"],
            readiness_score=row["readiness_score"],
        )

    # 6. Redirect back to frontend
    frontend = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return RedirectResponse(f"{frontend}/calibrate/spotify")


# ── Shared ingestion helper ──────────────────────────────────────────────────

async def _ingest_spotify_data(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    user_id: str,
) -> dict:
    """Fetch top artists/tracks/features, distill, persist, and return the profile.

    Called by both /sync (after token refresh) and /callback (after code exchange)
    to eliminate the duplicated ~80-line fetch-distill-store pipeline.
    """
    artists_data: list[dict] = []
    artists_resp = await client.get(
        f"{_SPOTIFY_API_BASE}/me/top/artists",
        headers=headers,
        params={"limit": 10, "time_range": "medium_term"},
    )
    if artists_resp.status_code == 200:
        artists_data = artists_resp.json().get("items", [])

    track_ids: list[str] = []
    tracks_data: list[dict] = []
    tracks_resp = await client.get(
        f"{_SPOTIFY_API_BASE}/me/top/tracks",
        headers=headers,
        params={"limit": 20, "time_range": "medium_term"},
    )
    if tracks_resp.status_code == 200:
        items = tracks_resp.json().get("items", [])
        track_ids = [t["id"] for t in items]
        tracks_data = items

    # NOTE: Spotify deprecated GET /audio-features (Nov 2024). We try and fall
    # back to genre-based heuristics if it returns 403/404 or empty data.
    audio_features: list[dict] = []
    if track_ids:
        features_resp = await client.get(
            f"{_SPOTIFY_API_BASE}/audio-features",
            headers=headers,
            params={"ids": ",".join(track_ids)},
        )
        if features_resp.status_code == 200:
            audio_features = [f for f in features_resp.json().get("audio_features", []) if f]

    top_artist_ids = {a["id"] for a in artists_data if a.get("id")}
    extra_artists = await _fetch_track_artist_genres(client, headers, tracks_data, top_artist_ids)

    profile = _distill_profile(artists_data, audio_features, tracks_data, extra_artists)
    await store_provider_data(user_id, "spotify_data", profile)
    return profile


# ── Profile distillation ─────────────────────────────────────────────────────

# Genre → estimated valence mapping for audio-features deprecation fallback.
# When Spotify stops returning audio features, we infer valence from genre strings.
_GENRE_VALENCE: list[tuple[str, float]] = [
    (r"sad|emo|doom|dark|goth|funeral|depressive", 0.2),
    (r"ambient|drone|shoegaze|post.?rock|atmospheric", 0.3),
    (r"blues|soul|neo.?soul|r&b|rnb", 0.35),
    (r"indie|alternative|lo.?fi|bedroom", 0.4),
    (r"rock|metal|punk|grunge|hard", 0.45),
    (r"folk|country|bluegrass|americana", 0.5),
    (r"jazz|classical|orchestral", 0.5),
    (r"hip.?hop|rap|trap", 0.55),
    (r"pop|teen|mainstream|k.?pop|j.?pop", 0.65),
    (r"electr|techno|house|edm|synth|drum|dance", 0.7),
    (r"reggaeton|salsa|cumbia|latin|party|happy", 0.8),
]


def _infer_valence_from_genres(genres: list[str]) -> float:
    """Estimate valence from genre keywords when audio-features API is unavailable."""
    import re
    scores = []
    for genre in genres:
        g = genre.lower()
        for pattern, val in _GENRE_VALENCE:
            if re.search(pattern, g):
                scores.append(val)
                break
    return round(sum(scores) / len(scores), 3) if scores else 0.5


async def _fetch_track_artist_genres(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    tracks_data: list[dict],
    top_artist_ids: set[str],
) -> list[dict]:
    """Fetch artist objects for artists appearing in top tracks but not top artists.

    Spotify increasingly returns empty genres[] on top-artist objects.
    Track artists are a supplemental source of genre data.
    """
    seen_ids: set[str] = set()
    extra_ids: list[str] = []
    for track in tracks_data:
        for artist in track.get("artists", []):
            aid = artist.get("id")
            if aid and aid not in top_artist_ids and aid not in seen_ids:
                seen_ids.add(aid)
                extra_ids.append(aid)

    if not extra_ids:
        return []

    # Fetch only the first 50 — artists beyond this are low-signal collaborators
    batch = extra_ids[:50]
    resp = await client.get(
        f"{_SPOTIFY_API_BASE}/artists",
        headers=headers,
        params={"ids": ",".join(batch)},
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("artists", [])


def _distill_profile(
    artists: list[dict],
    features: list[dict],
    tracks: list[dict] | None = None,
    extra_artists: list[dict] | None = None,
) -> dict:
    """Reduce raw Spotify data to the essentials we care about."""
    top_artist_names = [a["name"] for a in artists[:5]]
    genres: list[str] = []
    for a in artists[:5]:
        genres.extend(a.get("genres", []))
    # Supplement with genres from track artists (always additive, deduped below)
    if extra_artists:
        for a in extra_artists:
            genres.extend(a.get("genres", []))
    # Deduplicate while preserving order
    seen: set = set()
    unique_genres = [g for g in genres if not (g in seen or seen.add(g))][:8]  # type: ignore[func-returns-value]

    avg: dict[str, float] = {}
    keys = ["valence", "danceability", "energy", "acousticness", "instrumentalness", "tempo"]
    if features:
        for k in keys:
            vals = [f[k] for f in features if k in f]
            avg[k] = round(sum(vals) / len(vals), 3) if vals else 0.0

    # Fallback: if audio-features returned nothing (deprecated API), infer from genres + track popularity
    if not avg or not any(avg.get(k) for k in keys):
        avg["valence"] = _infer_valence_from_genres(unique_genres)
        # Use average track popularity (0-100) normalized to 0-1 as energy proxy
        if tracks:
            pops = [t.get("popularity", 50) for t in tracks]
            avg["energy"] = round(sum(pops) / len(pops) / 100, 3) if pops else 0.5
        else:
            avg["energy"] = 0.5
        avg["danceability"] = round((avg["valence"] + avg["energy"]) / 2, 3)
        avg["acousticness"] = round(1 - avg["energy"], 3)
        avg["tempo"] = 120.0

    return {
        "top_artists": top_artist_names,
        "genres": unique_genres,
        "audio_avg": avg,
    }


@router.get("/analyze")
async def spotify_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Spotify sonic profile."""
    settings = get_settings()

    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT spotify_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["spotify_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Spotify data found")

    data = row["spotify_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_spotify_profile(profile)
    return {"narrative": narrative}


async def _analyze_spotify_profile(profile: dict) -> str:
    artists = ", ".join(profile.get("top_artists", []))
    genres = ", ".join(profile.get("genres", []))
    avg = profile.get("audio_avg", {})
    valence = avg.get("valence", 0)
    danceability = avg.get("danceability", 0)
    energy = avg.get("energy", 0)
    acousticness = avg.get("acousticness", 0)
    instrumentalness = avg.get("instrumentalness", 0)
    tempo = avg.get("tempo", 0)

    prompt = f"""You are a perceptive behavioral psychologist analyzing a person's Spotify listening data as a window into their inner life.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of this user's sonic identity and emotional palette.
Do not be clinical. Be insightful, specific, and draw connections between data points.

SIGNAL DATA:
- Top artists: {artists}
- Genres: {genres}
- Average valence (emotional positivity): {valence:.3f}
- Average danceability: {danceability:.3f}
- Average energy: {energy:.3f}
- Average acousticness: {acousticness:.3f}
- Average instrumentalness: {instrumentalness:.3f}
- Average tempo: {tempo:.1f} BPM

Write 2-3 paragraphs analyzing:
1. Sonic identity — what their artist and genre choices reveal about how they construct their emotional world
2. Emotional palette — what valence, energy, and acousticness patterns reveal about their inner life, their relationship with stillness vs. intensity
3. The tension between their public taste (artists) and their private emotional needs (audio features)

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


def _build_embedding_text(profile: dict) -> str:
    """Convert Spotify profile to natural-language text for blending into embedding."""
    artists = ", ".join(profile.get("top_artists", []))
    genres = ", ".join(profile.get("genres", []))
    avg = profile.get("audio_avg", {})

    valence = avg.get("valence", 0)
    valence_label = "euphoric" if valence > 0.7 else ("melancholic" if valence < 0.35 else "ambivalent")
    energy = avg.get("energy", 0)
    energy_label = "high-intensity" if energy > 0.7 else ("introspective" if energy < 0.35 else "mid-energy")

    return (
        f"Top artists: {artists}. "
        f"Genres: {genres}. "
        f"Sonic valence: {valence:.2f} ({valence_label}), "
        f"danceability: {avg.get('danceability', 0):.2f}, "
        f"energy: {energy:.2f} ({energy_label})."
    )
