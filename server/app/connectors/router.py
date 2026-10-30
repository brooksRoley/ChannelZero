"""
Cross-connector correlations — finds meaningful patterns across provider data.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.deps import get_current_user_id
from ..config import get_settings
from ..db import get_conn
from ..llm.chat import chat_completion, llm_configured
from ..providers import is_retired

router = APIRouter()
logger = logging.getLogger(__name__)

# All *_data columns in vibe_vectors
_DATA_COLUMNS = [
    "spotify_data",
    "twitter_data",
    "strava_data",
    "gcal_data",
    "github_data",
    "youtube_data",
    "reddit_data",
    "letterboxd_data",
    "instagram_data",
    "tiktok_data",
    "costar_data",
]
# Correlations go to an LLM: retired providers' columns never do.
_DATA_COLUMNS = [c for c in _DATA_COLUMNS if not is_retired(c.replace("_data", ""))]

# Map column name -> provider label
_COL_TO_PROVIDER = {col: col.replace("_data", "") for col in _DATA_COLUMNS}


# Each entry: (provider_key, [list of settings attrs that must be truthy])
# A provider is "available" only if every credential it needs is present.
_PROVIDER_REQS: list[tuple[str, list[str]]] = [
    ("spotify",    ["spotify_client_id", "spotify_client_secret"]),
    ("twitter",    ["x_client_id", "x_client_secret"]),
    ("strava",     ["strava_client_id", "strava_client_secret"]),
    ("google",     ["google_client_id", "google_client_secret"]),
    ("gcal",       ["google_client_id", "google_client_secret"]),
    ("youtube",    ["google_client_id", "google_client_secret"]),
    ("github",     ["github_client_id", "github_client_secret"]),
    ("reddit",     ["reddit_client_id", "reddit_client_secret"]),
    ("instagram",  ["instagram_client_id", "instagram_client_secret"]),
    ("tiktok",     ["tiktok_client_key", "tiktok_client_secret"]),
    ("letterboxd", ["letterboxd_api_key", "letterboxd_api_secret"]),
    ("steam",      ["steam_api_key"]),
    ("costar",     []),  # manual chart entry, no env-side OAuth client
]


@router.get("/available")
async def get_available_connectors():
    """
    Public availability map — frontend uses this to disable connectors whose
    credentials aren't configured on the server, instead of letting users
    click through and hit a 503 on /<provider>/connect.
    """
    settings = get_settings()
    out: dict[str, bool] = {}
    for key, reqs in _PROVIDER_REQS:
        out[key] = not is_retired(key) and all(bool(getattr(settings, attr, "")) for attr in reqs)
    return {
        "providers": out,
        "llm": llm_configured(),
    }


@router.get("/correlations")
async def get_correlations(
    provider: str = Query(..., description="Provider to find correlations for"),
    user_id: UUID = Depends(get_current_user_id),
):
    """Find cross-connector correlations between the given provider and all others.

    Returns [] (200) — not 503 — when the LLM isn't configured, so the calibrate
    page degrades gracefully instead of throwing console errors.
    """
    if not llm_configured():
        return []

    # Validate provider name
    target_col = f"{provider}_data"
    if target_col not in _DATA_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}",
        )

    # Fetch all data columns
    cols = ", ".join(_DATA_COLUMNS)
    async with get_conn() as conn:
        row = await conn.fetchrow(
            f"SELECT {cols} FROM vibe_vectors WHERE user_id = $1",
            user_id,
        )

    if not row:
        return []

    # Parse each column into a dict (or None)
    provider_data: dict[str, dict] = {}
    for col in _DATA_COLUMNS:
        raw = row[col]
        if raw is not None:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            provider_data[_COL_TO_PROVIDER[col]] = parsed

    # Check the requested provider has data
    if provider not in provider_data:
        return []

    # Need at least 2 providers with data (including the requested one)
    if len(provider_data) < 2:
        return []

    # Build LLM request
    correlations = await _find_correlations(
        target_provider=provider,
        all_data=provider_data,
    )
    return correlations


async def _find_correlations(
    target_provider: str,
    all_data: dict[str, dict],
) -> list[dict]:
    """Call the LLM to find cross-connector correlations."""

    other_providers = {k: v for k, v in all_data.items() if k != target_provider}

    prompt = f"""You are a data analyst finding meaningful correlations between a user's connected platform data.

TARGET PROVIDER: {target_provider}
TARGET DATA:
{json.dumps(all_data[target_provider], indent=2, default=str)}

OTHER CONNECTED PROVIDERS:
{json.dumps(other_providers, indent=2, default=str)}

Find 3-5 specific, meaningful correlations between {target_provider} and the other providers.
Each correlation should reference a specific field/metric from {target_provider} and a specific field/metric from another provider.

Return ONLY a valid JSON array with this exact schema (no markdown, no explanation):
[
  {{
    "source": {{ "provider": "{target_provider}", "field": "field.path", "value": <actual_value>, "label": "Human Label" }},
    "target": {{ "provider": "<other_provider>", "field": "field.path", "value": <actual_value>, "label": "Human Label" }},
    "explanation": "One sentence explaining the correlation"
  }}
]

Rules:
- Use actual values from the data above
- field paths should use dot notation for nested fields
- value should be the actual number, string, or boolean from the data
- Each correlation must involve {target_provider} as the source
- Return ONLY the JSON array, nothing else"""

    try:
        content = await chat_completion(prompt, max_tokens=1200)
    except HTTPException as exc:
        logger.warning("Correlations LLM call failed for %s: %s", target_provider, exc.detail)
        # Treat upstream failures as "no correlations" so the page stays usable.
        return []

    # Parse the LLM response as JSON
    try:
        # Strip markdown fences if the LLM wraps them
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Failed to parse correlations LLM response: %s", exc)
        return []
