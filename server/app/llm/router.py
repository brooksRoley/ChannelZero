"""LLM routes — server-side provider health check (BYOK key storage and proxy were removed)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .chat import llm_configured, chat_completion

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Health Check ─────────────────────────────────────────────────

@router.get("/health")
async def llm_health():
    """
    Test LLM connectivity end-to-end.

    Returns provider info + a live ping result. Use this to verify
    OpenRouter (or OpenAI) keys are configured and the upstream responds.
    """
    from ..config import get_settings

    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower()
    configured = llm_configured()

    result = {
        "configured": configured,
        "provider": provider,
        "model": settings.llm_model or None,
        "ping": None,
        "error": None,
    }

    if not configured:
        result["error"] = f"No API key set for provider '{provider}'"
        return result

    # Live ping: send a trivial completion to verify the key works
    try:
        reply = await chat_completion(
            "Respond with exactly: OK",
            max_tokens=5,
            timeout=15.0,
        )
        result["ping"] = "ok"
        result["reply"] = reply.strip()
    except HTTPException as exc:
        result["ping"] = "fail"
        result["error"] = exc.detail
    except Exception as exc:
        result["ping"] = "fail"
        result["error"] = str(exc)

    return result
