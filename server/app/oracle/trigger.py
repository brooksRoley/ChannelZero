"""Auto-trigger Oracle synthesis when a user connects enough providers."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from ..db import get_conn
from .models import SynthesisRequest, ProviderPayload
from .service import synthesize_and_upsert

logger = logging.getLogger(__name__)

_PROVIDER_COLUMNS = {
    "spotify": "spotify_data",
    "twitter": "twitter_data",
    "gcal": "gcal_data",
    "costar": "costar_data",
    "letterboxd": "letterboxd_data",
    "steam": "steam_data",
    "github": "github_data",
    "youtube": "youtube_data",
    "reddit": "reddit_data",
    "tiktok": "tiktok_data",
}

_MIN_PROVIDERS = 2  # Minimum connected providers to trigger synthesis


async def maybe_trigger_synthesis(user_id: UUID) -> None:
    """
    Check if the user has enough connected providers to trigger Oracle synthesis.
    If so, build a SynthesisRequest from real DB data and fire it as a background task.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT spotify_data, twitter_data, strava_data,
                   gcal_data, costar_data, letterboxd_data, steam_data,
                   github_data, youtube_data, reddit_data,
                   instagram_data, tiktok_data
            FROM vibe_vectors
            WHERE user_id = $1
            """,
            user_id,
        )
        psych_row = await conn.fetchrow(
            """
            SELECT ipip_neo_scores, ecr_r_scores, love_language,
                   sociosexual_orientation, values_cluster
            FROM user_psychometrics
            WHERE user_id = $1
            """,
            user_id,
        )

    if not row:
        return

    # Count non-null, non-empty provider data
    connected = 0
    for col in _PROVIDER_COLUMNS.values():
        val = row[col]
        if val and val != {} and val != "{}":
            connected += 1

    if connected < _MIN_PROVIDERS:
        logger.debug("User %s has %d providers — need %d for synthesis", user_id, connected, _MIN_PROVIDERS)
        return

    # Build SynthesisRequest from real data
    def _parse(val) -> dict:
        if not val:
            return {}
        if isinstance(val, str):
            return json.loads(val)
        return dict(val)

    # Build psychometrics payload from scored assessment data
    psych_data: dict = {}
    if psych_row:
        for key in ("ipip_neo_scores", "ecr_r_scores", "love_language",
                     "sociosexual_orientation", "values_cluster"):
            val = psych_row[key]
            if val is not None:
                psych_data[key] = json.loads(val) if isinstance(val, str) else val

    request = SynthesisRequest(
        spotify=ProviderPayload(data=_parse(row["spotify_data"])),
        twitter=ProviderPayload(data=_parse(row["twitter_data"])),
        strava=ProviderPayload(),  # retired: never sent to the LLM (app/providers.py)
        gcal=ProviderPayload(data=_parse(row["gcal_data"])),
        costar=ProviderPayload(data=_parse(row["costar_data"])),
        letterboxd=ProviderPayload(data=_parse(row["letterboxd_data"])),
        steam=ProviderPayload(data=_parse(row["steam_data"])),
        github=ProviderPayload(data=_parse(row["github_data"])),
        youtube=ProviderPayload(data=_parse(row["youtube_data"])),
        reddit=ProviderPayload(data=_parse(row["reddit_data"])),
        instagram=ProviderPayload(),  # retired: never sent to the LLM (app/providers.py)
        tiktok=ProviderPayload(data=_parse(row["tiktok_data"])),
        psychometrics=ProviderPayload(data=psych_data),
    )

    logger.info("Auto-triggering Oracle synthesis for %s (%d providers)", user_id, connected)
    asyncio.create_task(synthesize_and_upsert(str(user_id), request))
