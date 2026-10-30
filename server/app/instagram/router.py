"""
Instagram: retired 2026-10-30 (see app/providers.py).

Since the Basic Display API ended (Dec 2024), Instagram's only API serves
Business and Creator accounts, so a personal account can't connect at all.
The old flow also mixed Facebook Login (facebook.com dialog, instagram_basic
scopes) with Instagram Login's token host, so it could never have completed.

New connections and narratives answer 410 {code: "retired"}. A user who has a
stored snapshot can still read it (GET /api/instagram/profile); it never
reaches an LLM. Instagram activity now comes from the user's own data export,
read on the device and never uploaded (src/composables/instagramExport.ts).
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
                         detail={"code": "retired", "message": RETIRED_PROVIDERS["instagram"]})


@router.get("/connect")
async def instagram_connect():
    raise _retired()


@router.get("/callback")
async def instagram_callback():
    raise _retired()


@router.get("/analyze")
async def instagram_analyze():
    raise _retired()


@router.get("/profile")
async def get_instagram_profile(user_id: UUID = Depends(get_current_user_id)):
    """The stored snapshot for the current user, or null. Shown only to them."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT instagram_data FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["instagram_data"]:
        return None
    data = row["instagram_data"]
    return json.loads(data) if isinstance(data, str) else data
