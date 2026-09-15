"""Intake routes — the psychoanalytic confessional pipeline."""

from __future__ import annotations

import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .models import ConfessRequest, ConfessResponse, FittingRequest
from ..auth.deps import get_current_user_id
from ..db import get_conn, get_tx
from ..llm.encryption import encrypt_api_key
from ..ratelimit import limiter
from ..vector.service import query_relevant_journal, upsert_user_vector, find_nearest_users

router = APIRouter()


# ── Keyword maps for local NLP fallback ────────────────────────────

_ATTACHMENT_PATTERNS: list[tuple[str, str]] = [
    (r"afraid|abandon|cling|need\s|anxious|worry|losing", "anxious-preoccupied"),
    (r"alone|independent|don.t need|walls|distance|space|self.sufficient", "dismissive-avoidant"),
    (r"push.{0,10}pull|want.{0,20}afraid|close.{0,10}away|hot.{0,10}cold|scared.{0,10}close", "fearful-avoidant"),
]

_DEFENSE_PATTERNS: list[tuple[str, str]] = [
    (r"joke|laugh|funny|humor|sarcas", "humor"),
    (r"project|blame|their fault|they always|they never", "projection"),
    (r"fine|whatever|doesn.t matter|don.t care|numb", "denial"),
    (r"think|analy[sz]|figure out|understand why|intellectu", "intellectualization"),
]

_ATTACHMENT_INSIGHTS = {
    "secure": "You form connections with relative ease — grounded and open.",
    "anxious-preoccupied": "You crave closeness but fear it will vanish. The wanting is the wound.",
    "dismissive-avoidant": "You built walls so well you forgot there was something inside worth protecting.",
    "fearful-avoidant": "You want to be seen but flinch when someone actually looks. Push and pull.",
}

_DEFENSE_INSIGHTS = {
    "humor": "You deflect with wit — the joke is the armor.",
    "projection": "You see your shadows in others before you see them in the mirror.",
    "denial": '"I\'m fine" is doing a lot of heavy lifting.',
    "intellectualization": "You analyze the feeling instead of feeling it.",
    "rationalization": "You find reasons. There are always reasons.",
}


def _analyze_local(confessions: list[str]) -> tuple[str, str, int]:
    """Keyword-based fallback analysis when no LLM key is available."""
    text = " ".join(confessions).lower()

    # Attachment style
    attachment = "secure"
    for pattern, style in _ATTACHMENT_PATTERNS:
        if re.search(pattern, text):
            attachment = style
            break

    # Defense mechanism
    defense = "rationalization"
    for pattern, mechanism in _DEFENSE_PATTERNS:
        if re.search(pattern, text):
            defense = mechanism
            break

    # Readiness: more text + more confessions = higher
    readiness = min(100, max(20, 40 + len(confessions) * 15 + (20 if len(text) > 200 else 0)))

    return attachment, defense, readiness


@router.post("/confess", response_model=ConfessResponse)
@limiter.limit("20/minute")
async def confess(
    request: Request,
    body: ConfessRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Receive raw confessional text, store in encrypted shadow log,
    run NLP extraction, update vibe vector.
    """
    raw_text = "\n\n".join(body.confessions)

    # 1. NLP extraction (local fallback — phase 2 adds LLM call)
    attachment, defense, readiness = _analyze_local(body.confessions)

    # 2. Query Pinecone for resonant journal memories
    memory_hits = await query_relevant_journal(str(user_id), raw_text, top_k=5)
    memory_previews = [m["text_preview"] for m in memory_hits if m.get("text_preview")]
    # Memories signal deeper engagement — nudge readiness up slightly
    readiness = min(100, readiness + len(memory_previews) * 3)

    # 3. Store shadow log + upsert vibe vector atomically
    encrypted_text, nonce = encrypt_api_key(raw_text)  # reuse AES-GCM encryption

    async with get_tx() as conn:
        await conn.execute(
            """
            INSERT INTO intake_shadow_logs (user_id, encrypted_text, text_nonce)
            VALUES ($1, $2, $3)
            """,
            user_id, encrypted_text, nonce,
        )

        await conn.execute(
            """
            INSERT INTO vibe_vectors (user_id, attachment_style, defense_mechanism, readiness_score, poll_theme)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO UPDATE SET
                attachment_style = EXCLUDED.attachment_style,
                defense_mechanism = EXCLUDED.defense_mechanism,
                readiness_score = EXCLUDED.readiness_score,
                poll_theme = COALESCE(EXCLUDED.poll_theme, vibe_vectors.poll_theme),
                updated_at = now()
            """,
            user_id, attachment, defense, readiness, body.poll_theme,
        )

    # 5. Plot user's psychological coordinate in Pinecone (fire-and-forget)
    import asyncio
    asyncio.create_task(upsert_user_vector(
        user_id=str(user_id),
        confession_text=raw_text,
        attachment_style=attachment,
        defense_mechanism=defense,
        readiness_score=readiness,
    ))

    # 6. Build insight
    a_insight = _ATTACHMENT_INSIGHTS.get(attachment, "")
    d_insight = _DEFENSE_INSIGHTS.get(defense, "")
    readiness_note = "You're ready to play." if readiness >= 70 else "Almost there. Keep journaling."
    insight = f"{a_insight} {d_insight} Readiness: {readiness}/100. {readiness_note}"

    return ConfessResponse(
        attachment_style=attachment,
        defense_mechanism=defense,
        readiness_score=readiness,
        insight=insight,
        memories=memory_previews,
    )


@router.get("/match")
async def find_matches(user_id: UUID = Depends(get_current_user_id)):
    """
    Return the 3 users psychologically closest to the current user in
    Pinecone's 1,536-dimensional space. Requires intake to have been completed.

    Enriched response includes Spotify overlap, match reasoning, and
    whether the target already accepted the current user (for mutual match).
    """
    matches = await find_nearest_users(str(user_id), top_k=3)
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matches found — complete intake first or embedding key not configured",
        )

    match_ids = [UUID(m["user_id"]) for m in matches if m.get("user_id")]

    async with get_conn() as conn:
        # Hydrate display names + avatar
        user_rows = await conn.fetch(
            "SELECT id, display_name, avatar_url FROM users WHERE id = ANY($1::uuid[])",
            match_ids,
        )
        user_map = {str(r["id"]): r for r in user_rows}

        # Fetch vibe vectors for matched users (spotify_data, attachment, etc.)
        vibe_rows = await conn.fetch(
            "SELECT user_id, spotify_data, twitter_data, strava_data, "
            "attachment_style, defense_mechanism, readiness_score, "
            "oracle_coordinate, oracle_synthesized_at "
            "FROM vibe_vectors WHERE user_id = ANY($1::uuid[])",
            match_ids,
        )
        vibe_map = {str(r["user_id"]): r for r in vibe_rows}

        # Fetch current user's vibe vector for comparison
        my_vibe = await conn.fetchrow(
            "SELECT spotify_data, twitter_data, strava_data, "
            "attachment_style, defense_mechanism, oracle_coordinate "
            "FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

        # Check which targets have already accepted the current user
        accepted_rows = await conn.fetch(
            "SELECT actor_id FROM match_interactions "
            "WHERE actor_id = ANY($1::uuid[]) AND target_id = $2 AND action = 'accept'",
            match_ids, user_id,
        )
        accepted_by = {str(r["actor_id"]) for r in accepted_rows}

        # Check current user's existing interactions with these targets
        my_actions = await conn.fetch(
            "SELECT target_id, action FROM match_interactions "
            "WHERE actor_id = $1 AND target_id = ANY($2::uuid[])",
            user_id, match_ids,
        )
        my_action_map = {str(r["target_id"]): r["action"] for r in my_actions}

    results = []
    for m in matches:
        mid = m["user_id"]
        u = user_map.get(mid, {})
        v = vibe_map.get(mid)
        reason = _build_match_reason(m, my_vibe, v)
        spotify = _extract_spotify_overlap(my_vibe, v) if my_vibe and v else None

        results.append({
            "user_id": mid,
            "display_name": u.get("display_name") or "Unknown",
            "avatar_url": u.get("avatar_url"),
            "attachment_style": m.get("attachment_style"),
            "defense_mechanism": m.get("defense_mechanism"),
            "similarity": m["score"],
            "match_reason": reason,
            "sonic_overlap": spotify,
            "twitter_overlap": _extract_twitter_overlap(my_vibe, v) if my_vibe and v else None,
            "strava_overlap": _extract_strava_overlap(my_vibe, v) if my_vibe and v else None,
            "oracle_insight": _extract_oracle_insight(v),
            "they_accepted": mid in accepted_by,
            "my_action": my_action_map.get(mid),
        })

    return results


def _build_match_reason(
    match: dict, my_vibe: object | None, their_vibe: object | None,
) -> str:
    """Generate a human-readable explanation for why two users matched."""
    reasons: list[str] = []
    score = match["score"]

    if score >= 0.92:
        reasons.append("Exceptionally close psychological coordinates")
    elif score >= 0.85:
        reasons.append("Strong alignment in psychological space")
    else:
        reasons.append("Complementary psychological profiles")

    my_attach = my_vibe["attachment_style"] if my_vibe else None
    their_attach = match.get("attachment_style")
    if my_attach and their_attach:
        if my_attach == their_attach:
            reasons.append(f"Shared attachment style: {their_attach}")
        else:
            reasons.append(f"Complementary attachment dynamics: {my_attach} + {their_attach}")

    my_defense = my_vibe["defense_mechanism"] if my_vibe else None
    their_defense = match.get("defense_mechanism")
    if my_defense and their_defense and my_defense != their_defense:
        reasons.append(f"Different defense patterns ({my_defense} / {their_defense}) — growth potential")

    # Oracle coordinate insights
    my_oracle = my_vibe.get("oracle_coordinate") if my_vibe else None
    their_oracle = their_vibe.get("oracle_coordinate") if their_vibe else None
    if my_oracle and their_oracle:
        if isinstance(my_oracle, str):
            my_oracle = json.loads(my_oracle)
        if isinstance(their_oracle, str):
            their_oracle = json.loads(their_oracle)
        empathy_diff = abs((my_oracle.get("empathy_index") or 0) - (their_oracle.get("empathy_index") or 0))
        if empathy_diff < 0.15:
            reasons.append("Closely aligned empathy signatures")

    return ". ".join(reasons) + "."


def _extract_twitter_overlap(my_vibe: object | None, their_vibe: object | None) -> dict | None:
    """Compare Twitter behavioral signals between two users."""
    my_twitter = my_vibe.get("twitter_data") if my_vibe else None
    their_twitter = their_vibe.get("twitter_data") if their_vibe else None
    if not my_twitter or not their_twitter:
        return None

    if isinstance(my_twitter, str):
        my_twitter = json.loads(my_twitter)
    if isinstance(their_twitter, str):
        their_twitter = json.loads(their_twitter)

    my_avg_len = my_twitter.get("avg_tweet_length", 0)
    their_avg_len = their_twitter.get("avg_tweet_length", 0)
    my_lang = my_twitter.get("language", "")
    their_lang = their_twitter.get("language", "")

    return {
        "both_connected": True,
        "communication_style_match": abs(my_avg_len - their_avg_len) < 50,
        "shared_language": my_lang == their_lang if my_lang and their_lang else None,
        "their_username": their_twitter.get("username"),
    }


def _extract_strava_overlap(my_vibe: object | None, their_vibe: object | None) -> dict | None:
    """Compare physical activity patterns between two users."""
    my_strava = my_vibe.get("strava_data") if my_vibe else None
    their_strava = their_vibe.get("strava_data") if their_vibe else None
    if not my_strava or not their_strava:
        return None

    if isinstance(my_strava, str):
        my_strava = json.loads(my_strava)
    if isinstance(their_strava, str):
        their_strava = json.loads(their_strava)

    my_types = set(my_strava.get("activity_types", []))
    their_types = set(their_strava.get("activity_types", []))
    shared_activities = sorted(my_types & their_types)

    return {
        "both_connected": True,
        "shared_activities": shared_activities,
        "their_activity_types": sorted(their_types)[:5],
    }


def _extract_oracle_insight(their_vibe: object | None) -> dict | None:
    """Extract Oracle coordinate metrics if synthesized."""
    if not their_vibe:
        return None
    coord = their_vibe.get("oracle_coordinate")
    if not coord:
        return None
    if isinstance(coord, str):
        coord = json.loads(coord)
    return {
        "empathy_index": coord.get("empathy_index"),
        "isolation_metric": coord.get("isolation_metric"),
        "fatalism_score": coord.get("fatalism_score"),
        "masochism_curve": coord.get("masochism_curve"),
        "oracle_rationale": coord.get("oracle_rationale"),
    }


def _extract_spotify_overlap(my_vibe: object | None, their_vibe: object | None) -> dict | None:
    """Compare Spotify data between two users for sonic overlap display."""
    import json as _json
    my_spotify = my_vibe.get("spotify_data") if my_vibe else None
    their_spotify = their_vibe.get("spotify_data") if their_vibe else None
    if not my_spotify or not their_spotify:
        return None

    # Handle JSONB — may already be dict or may be JSON string
    if isinstance(my_spotify, str):
        my_spotify = _json.loads(my_spotify)
    if isinstance(their_spotify, str):
        their_spotify = _json.loads(their_spotify)

    my_genres = set(my_spotify.get("genres", []))
    their_genres = set(their_spotify.get("genres", []))
    shared_genres = sorted(my_genres & their_genres)

    my_artists = set(my_spotify.get("top_artists", []))
    their_artists = set(their_spotify.get("top_artists", []))
    shared_artists = sorted(my_artists & their_artists)

    my_audio = my_spotify.get("audio_avg", {})
    their_audio = their_spotify.get("audio_avg", {})

    return {
        "shared_genres": shared_genres[:5],
        "shared_artists": shared_artists[:3],
        "their_top_genres": sorted(their_genres)[:5],
        "valence_delta": abs((my_audio.get("valence") or 0) - (their_audio.get("valence") or 0)),
        "energy_delta": abs((my_audio.get("energy") or 0) - (their_audio.get("energy") or 0)),
    }


@router.get("/vector")
async def get_vibe_vector(user_id: UUID = Depends(get_current_user_id)):
    """Retrieve the current user's vibe vector."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, attachment_style, defense_mechanism, readiness_score, poll_theme, created_at
            FROM vibe_vectors
            WHERE user_id = $1
            """,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No vibe vector found — complete the intake first")
    return dict(row)


@router.post("/fitting", status_code=204)
async def save_fitting(
    body: FittingRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Store self-avatar or ideal-partner avatar for the fitting ritual."""
    column = "fitting_self" if body.phase == "self" else "fitting_ideal"
    async with get_conn() as conn:
        await conn.execute(
            f"""
            UPDATE vibe_vectors
            SET {column} = $2::jsonb, updated_at = now()
            WHERE user_id = $1
            """,
            user_id, json.dumps(body.data),
        )
