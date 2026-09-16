"""
Integrated Portrait endpoints.

GET  /api/portrait           — always 200; state machine in PortraitStatus.status
POST /api/portrait/generate  — synchronous generation; regenerates when called
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.deps import get_current_user_id
from ..ratelimit import limiter
from ..config import get_settings
from ..llm.chat import llm_configured
from .models import PortraitStatus
from .service import fetch_portrait_data, generate_and_store
from .stitcher import MIN_PROVIDERS, is_stale

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=PortraitStatus)
@router.get("/", response_model=PortraitStatus, include_in_schema=False)
async def get_portrait(user_id: UUID = Depends(get_current_user_id)) -> PortraitStatus:
    data = await fetch_portrait_data(user_id)
    llm = llm_configured()

    base = dict(
        portrait=data.portrait,
        generated_at=data.generated_at,
        source_providers=data.source_providers,
        connected_providers=data.connected,
        llm_available=llm,
    )

    if len(data.connected) < MIN_PROVIDERS:
        return PortraitStatus(status="insufficient_providers", **base)
    if not llm:
        # A previously stored portrait stays readable even with the LLM down
        return PortraitStatus(status="no_llm", **base)
    if data.portrait is None:
        return PortraitStatus(status="empty", **base)
    if is_stale(
        data.generated_at,
        data.source_providers,
        data.connected,
        ttl_days=get_settings().portrait_ttl_days,
        now=datetime.now(timezone.utc),
    ):
        return PortraitStatus(status="stale", **base)
    return PortraitStatus(status="ready", **base)


@router.post("/generate", response_model=PortraitStatus)
@limiter.limit("5/hour")
async def generate_portrait(
    request: Request, user_id: UUID = Depends(get_current_user_id)
) -> PortraitStatus:
    data = await fetch_portrait_data(user_id)

    if len(data.connected) < MIN_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connect at least {MIN_PROVIDERS} data streams first",
        )
    if not llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Narrative engine offline — LLM not configured on the server",
        )

    try:
        portrait = await generate_and_store(user_id, data)
    except ValueError as exc:
        logger.error("Portrait generation unparseable for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Portrait generation failed upstream — try again",
        ) from exc

    return PortraitStatus(
        status="ready",
        portrait=portrait,
        generated_at=datetime.now(timezone.utc),
        source_providers=data.connected,
        connected_providers=data.connected,
        llm_available=True,
    )
