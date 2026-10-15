"""
Single chat-completion helper used by every connector's `/analyze` endpoint
and the cross-connector correlations endpoint.

Provider switch is driven by env (read via Settings):
  LLM_PROVIDER=openai      → OPENAI_EMBED_KEY  → api.openai.com
  LLM_PROVIDER=openrouter  → OPENROUTER_API_KEY → openrouter.ai/api/v1
  (unset)                  → openai (legacy)

Default model per provider is overridable via LLM_MODEL.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

from ..config import get_settings


_PROVIDERS = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        # Free default; user can override via LLM_MODEL.
        "default_model": "google/gemma-4-31b-it:free",
    },
}


def _resolve_provider() -> tuple[str, str, str]:
    """Return (provider_name, api_url, api_key). Raises 503 if unconfigured."""
    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower()

    if provider not in _PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown LLM_PROVIDER: {provider}",
        )

    if provider == "openrouter":
        key = settings.openrouter_api_key
    else:
        key = settings.openai_embed_key

    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM not configured ({provider})",
        )

    return provider, _PROVIDERS[provider]["url"], key


def llm_configured() -> bool:
    """Cheap check used to decide whether to expose narrative/correlations."""
    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower()
    if provider == "openrouter":
        return bool(settings.openrouter_api_key)
    return bool(settings.openai_embed_key)


async def chat_completion(
    prompt: str,
    *,
    max_tokens: int = 800,
    model: str | None = None,
    timeout: float = 60.0,
) -> str:
    """
    Send a single user-message prompt and return the assistant's text content.

    Raises 502 on upstream failure, 503 if no provider is configured.
    """
    provider, url, api_key = _resolve_provider()
    settings = get_settings()
    chosen_model = model or settings.llm_model or _PROVIDERS[provider]["default_model"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        # OpenRouter recommends sending these for attribution / rate limits.
        if settings.cors_origin_list:
            headers["HTTP-Referer"] = settings.cors_origin_list[0]
        headers["X-Title"] = "ChannelZero"

    payload = {
        "model": chosen_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        # Log the upstream body for debugging (truncated)
        try:
            err_body = resp.text[:300]
        except Exception:
            err_body = ""
        logger.error("LLM upstream error: %s %s — %s", provider, resp.status_code, err_body)
        if resp.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="LLM temporarily rate-limited — please retry in a moment.",
                headers={"Retry-After": "15"},
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM call failed ({provider} {resp.status_code}): {err_body[:120]}",
        )

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Malformed LLM response",
        ) from exc
