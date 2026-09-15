"""Intake routes — the psychoanalytic confessional pipeline."""

from __future__ import annotations

import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from .models import ConfessRequest, ConfessResponse, FittingRequest
from ..auth.deps import get_current_user_id
from ..db import get_conn, get_tx
from ..llm.encryption import encrypt_api_key
from ..vector.service import query_relevant_journal, upsert_user_vector

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
    "denial": "\"I'm fine\" is doing a lot of heavy lifting.",
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
async def confess(
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
