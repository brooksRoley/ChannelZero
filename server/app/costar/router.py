"""
Co-Star credential-based data ingestion.

Co-Star has NO public API. Data ingestion uses a one-shot credential proxy:
the user provides their Co-Star username + password, we authenticate against
Co-Star's private API, extract their natal chart data, and immediately purge
the credentials from memory. The password is never stored.

This powers the Oracle's "Fatalism Mirror" dimension.

TODO: Co-Star may block automated login. If their private API changes,
      this connector will need updating. Consider offering manual chart
      entry as a fallback.
"""

from __future__ import annotations

import json
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..llm.chat import chat_completion

router = APIRouter()

# Co-Star's undocumented API base (may change without notice)
_COSTAR_API_BASE = "https://api.costarastrology.com"


class CoStarIngestRequest(BaseModel):
    costar_username: str
    costar_password: str


class CoStarManualRequest(BaseModel):
    """Manual chart entry fallback when credential proxy fails."""
    sun_sign: str
    moon_sign: str
    rising_sign: str
    venus_sign: str = ""
    mars_sign: str = ""


@router.post("/ingest")
async def costar_ingest(
    req: CoStarIngestRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Authenticate with Co-Star, extract natal chart, store, purge credentials.

    If the Co-Star API blocks us or changes, falls back to returning an
    error suggesting manual entry via /costar/manual.
    """
    chart_data = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Attempt Co-Star login
            login_resp = await client.post(
                f"{_COSTAR_API_BASE}/auth/login",
                json={
                    "email": req.costar_username,
                    "password": req.costar_password,
                },
            )

            if login_resp.status_code == 200:
                auth_data = login_resp.json()
                token = auth_data.get("token") or auth_data.get("access_token", "")

                if token:
                    # Fetch natal chart
                    chart_resp = await client.get(
                        f"{_COSTAR_API_BASE}/user/chart",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if chart_resp.status_code == 200:
                        chart_data = chart_resp.json()
            else:
                # Login failed — could be wrong credentials or API change
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Co-Star login failed. Check credentials or use manual chart entry at /api/costar/manual.",
                )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Co-Star. Use manual chart entry at /api/costar/manual instead.",
        )

    # Credentials purged — req goes out of scope here and is never stored.
    # Even if chart_data fetch failed, we still return something useful.

    if not chart_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Co-Star chart extraction failed. Use /api/costar/manual for manual entry.",
        )

    costar_profile = _distill_chart(chart_data)

    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE vibe_vectors
            SET costar_data = $2, updated_at = now()
            WHERE user_id = $1
            """,
            user_id, json.dumps(costar_profile),
        )

    return {"status": "connected", "chart": costar_profile}


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

    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE vibe_vectors
            SET costar_data = $2, updated_at = now()
            WHERE user_id = $1
            """,
            user_id, json.dumps(costar_profile),
        )

    return {"status": "connected", "chart": costar_profile}


# ── Profile distillation ─────────────────────────────────────────────────────

def _distill_chart(raw: dict) -> dict:
    """Extract the key astrological placements from raw Co-Star chart data."""
    # Co-Star's internal format varies, but generally contains placements
    placements = raw.get("placements", raw.get("chart", {}))

    if isinstance(placements, list):
        chart = {}
        for p in placements:
            planet = p.get("planet", p.get("name", "")).lower()
            sign = p.get("sign", "")
            if planet and sign:
                chart[planet] = sign
    elif isinstance(placements, dict):
        chart = placements
    else:
        chart = raw

    return {
        "source": "costar_api",
        "sun": chart.get("sun", ""),
        "moon": chart.get("moon", ""),
        "rising": chart.get("ascendant", chart.get("rising", "")),
        "venus": chart.get("venus", ""),
        "mars": chart.get("mars", ""),
        "mercury": chart.get("mercury", ""),
        "jupiter": chart.get("jupiter", ""),
        "saturn": chart.get("saturn", ""),
    }


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
