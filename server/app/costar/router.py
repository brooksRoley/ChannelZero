"""
Co-Star natal chart connector — manual entry.

Co-Star has no public API. An earlier version proxied the user's Co-Star
password to an undocumented login endpoint; it never succeeded in production
and was removed 2026-10-14. Users enter their placements directly instead.

This powers the Oracle's "Fatalism Mirror" dimension.
"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..oauth_base import store_provider_data
from ..llm.chat import chat_completion

router = APIRouter()

Sign = Literal[
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


class CoStarManualRequest(BaseModel):
    """Natal placements entered by the user (Venus and Mars optional)."""
    sun_sign: Sign
    moon_sign: Sign
    rising_sign: Sign
    venus_sign: Sign | Literal[""] = ""
    mars_sign: Sign | Literal[""] = ""


@router.post("/manual")
async def costar_manual(
    req: CoStarManualRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Manual natal chart entry — no credentials needed.
    Users can enter their Sun, Moon, Rising, Venus, Mars signs directly.
    """
    costar_profile = {
        "source": "manual_entry",
        "sun": req.sun_sign,
        "moon": req.moon_sign,
        "rising": req.rising_sign,
        "venus": req.venus_sign or None,
        "mars": req.mars_sign or None,
    }

    # Upsert: most users have no vibe_vectors row yet (intake is optional), and a
    # plain UPDATE would silently drop the chart for them.
    await store_provider_data(str(user_id), "costar_data", costar_profile)

    return {"status": "connected", "chart": costar_profile}


@router.get("/analyze")
async def costar_analyze(user_id: UUID = Depends(get_current_user_id)):
    """Generate an LLM psychoanalysis of the user's Co-Star natal chart data."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT costar_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row or not row["costar_data"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Co-Star data found")

    data = row["costar_data"]
    profile = json.loads(data) if isinstance(data, str) else data

    narrative = await _analyze_costar_profile(profile)
    return {"narrative": narrative}


async def _analyze_costar_profile(profile: dict) -> str:
    source = profile.get("source", "unknown")
    sun = profile.get("sun", "unknown")
    moon = profile.get("moon", "unknown")
    rising = profile.get("rising", "unknown")
    venus = profile.get("venus", "")
    mars = profile.get("mars", "")
    mercury = profile.get("mercury", "")
    jupiter = profile.get("jupiter", "")
    saturn = profile.get("saturn", "")

    placements_str = f"Sun: {sun}, Moon: {moon}, Rising: {rising}"
    if venus:
        placements_str += f", Venus: {venus}"
    if mars:
        placements_str += f", Mars: {mars}"
    if mercury:
        placements_str += f", Mercury: {mercury}"
    if jupiter:
        placements_str += f", Jupiter: {jupiter}"
    if saturn:
        placements_str += f", Saturn: {saturn}"

    prompt = f"""You are a perceptive behavioral psychologist with deep knowledge of archetypal astrology, analyzing a person's natal chart placements as a map of their psychological architecture.
Your task: write a sharp, warm, 2-3 paragraph psychoanalysis of how these planetary placements map to observable behavioral patterns.
Do not be clinical. Be insightful, specific, and draw connections between placements. Do NOT write a generic horoscope — write a psychological profile that uses astrological language as metaphor.

NATAL CHART DATA:
- Source: {source}
- {placements_str}

Write 2-3 paragraphs analyzing:
1. Core identity architecture — how the Sun-Moon-Rising triad creates a specific tension between who they are (Sun), what they need (Moon), and how they present (Rising), and what behavioral patterns emerge from that tension
2. Relational and drive patterns — what Venus and Mars placements reveal about how they love, what they're attracted to, how they pursue what they want, and the gap between desire and action
3. Growth edges — what the outer planet placements (Mercury, Jupiter, Saturn) suggest about their communication style, where they seek expansion, and what limitations they've internalized

Be direct, specific, a little poetic. Avoid generic statements. Return only the narrative."""

    return await chat_completion(prompt)


@router.get("/profile")
async def get_costar_profile(user_id: UUID = Depends(get_current_user_id)):
    """Return the stored Co-Star profile for the current user, or null."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT costar_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["costar_data"]:
        return None
    data = row["costar_data"]
    return json.loads(data) if isinstance(data, str) else data
