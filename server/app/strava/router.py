"""
Strava: retired 2026-10-30 (see app/providers.py).

Strava's API now requires a paid subscription on the developer account, and
its API Policy §5.3 forbids any AI use of API data, which is what this
connector was for. New connections, syncs and narratives answer 410
{code: "retired"}. A user who connected before can still read their own
stored snapshot (GET /api/strava/profile); it never reaches an LLM.

The planned replacement reads the user's own Strava data export on the
device, never uploaded.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..providers import RETIRED_PROVIDERS

router = APIRouter()


def _retired() -> HTTPException:
    return HTTPException(status_code=status.HTTP_410_GONE,
                         detail={"code": "retired", "message": RETIRED_PROVIDERS["strava"]})


@router.get("/connect")
async def strava_connect():
    raise _retired()


@router.get("/callback")
async def strava_callback():
    raise _retired()


@router.post("/sync")
async def strava_sync():
    raise _retired()


@router.get("/analyze")
async def strava_analyze():
    """Retired: Strava data may not be sent to an AI model (API Policy §5.3)."""
    raise _retired()


@router.get("/profile")
async def get_strava_profile(user_id: UUID = Depends(get_current_user_id)):
    """The stored snapshot for the current user, or null. Shown only to them."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT strava_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["strava_data"]:
        return None
    data = row["strava_data"]
    return json.loads(data) if isinstance(data, str) else data
