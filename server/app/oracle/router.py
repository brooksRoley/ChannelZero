"""Oracle routes — trigger the 12-dimensional psychological synthesis pipeline."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..ratelimit import limiter
from .models import SynthesisRequest, SynthesisResponse
from .service import synthesize_and_upsert

router = APIRouter()


@router.post("/synthesize", response_model=SynthesisResponse)
@limiter.limit("5/hour")
async def trigger_synthesis(
    request: Request,
    body: SynthesisRequest,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
):
    """
    Accept raw data from all seven OAuth providers and kick off
    Oracle synthesis as a background task.  The LLM call + embedding +
    Pinecone upsert runs async so the frontend feels instant.
    """
    background_tasks.add_task(synthesize_and_upsert, str(user_id), body)
    return SynthesisResponse(
        status="initiated",
        message="The Oracle is plotting your coordinate.",
    )


@router.get("/coordinate")
async def get_coordinate(user_id: UUID = Depends(get_current_user_id)):
    """Return the user's Oracle coordinate if synthesized."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT oracle_coordinate, oracle_synthesized_at FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )
    if not row or not row["oracle_coordinate"]:
        return {"synthesized": False}

    import json as _json
    coord = row["oracle_coordinate"]
    if isinstance(coord, str):
        coord = _json.loads(coord)

    return {
        "synthesized": True,
        "coordinate": coord,
        "synthesized_at": row["oracle_synthesized_at"].isoformat() if row["oracle_synthesized_at"] else None,
    }
