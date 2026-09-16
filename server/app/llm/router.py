"""LLM proxy routes — encrypted API key management + provider forwarding."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from .encryption import encrypt_api_key, decrypt_api_key, key_hint
from .chat import llm_configured, chat_completion
from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..ratelimit import limiter

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


# ── Models ──────────────────────────────────────────────────────

class StoreKeyRequest(BaseModel):
    provider: str  # 'anthropic', 'openai', 'together'
    api_key: str


class KeyInfo(BaseModel):
    id: UUID
    provider: str
    key_hint: str


_MAX_TOKENS_CEILING = 4096
_ALLOWED_PROVIDERS = {"anthropic", "openai", "together", "google", "xai"}


class LLMRequest(BaseModel):
    provider: str
    messages: list[dict]
    model: str | None = None
    max_tokens: int = 1024
    stream: bool = False

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _ALLOWED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {v}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def cap_max_tokens(cls, v: int) -> int:
        return min(max(1, v), _MAX_TOKENS_CEILING)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[dict]) -> list[dict]:
        if not v:
            raise ValueError("At least one message is required")
        if len(v) > 100:
            raise ValueError("Maximum 100 messages allowed")
        return v


# ── Key Management ──────────────────────────────────────────────

@router.post("/keys", response_model=KeyInfo, status_code=status.HTTP_201_CREATED)
async def store_key(
    body: StoreKeyRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    encrypted, nonce = encrypt_api_key(body.api_key)
    hint = key_hint(body.api_key)

    async with get_conn() as conn:
        # Upsert: one key per provider per user
        row = await conn.fetchrow(
            """
            INSERT INTO user_api_keys (user_id, provider, encrypted_key, key_nonce, key_hint)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, provider)
                WHERE user_id = $1 AND provider = $2
            DO UPDATE SET encrypted_key = $3, key_nonce = $4, key_hint = $5
            RETURNING id, provider, key_hint
            """,
            user_id, body.provider, encrypted, nonce, hint,
        )

    # If the upsert didn't return (no unique constraint on user_id+provider yet),
    # fall back to delete + insert
    if row is None:
        async with get_conn() as conn:
            await conn.execute(
                "DELETE FROM user_api_keys WHERE user_id = $1 AND provider = $2",
                user_id, body.provider,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO user_api_keys (user_id, provider, encrypted_key, key_nonce, key_hint)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, provider, key_hint
                """,
                user_id, body.provider, encrypted, nonce, hint,
            )

    return KeyInfo(**dict(row))


@router.get("/keys", response_model=list[KeyInfo])
async def list_keys(user_id: UUID = Depends(get_current_user_id)):
    async with get_conn() as conn:
        rows = await conn.fetch(
            "SELECT id, provider, key_hint FROM user_api_keys WHERE user_id = $1 ORDER BY provider",
            user_id,
        )
    return [KeyInfo(**dict(r)) for r in rows]


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    async with get_conn() as conn:
        result = await conn.execute(
            "DELETE FROM user_api_keys WHERE id = $1 AND user_id = $2",
            key_id, user_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")


# ── LLM Proxy ──────────────────────────────────────────────────

@router.post("/proxy")
@limiter.limit("30/hour")
async def proxy_llm(
    request: Request,
    body: LLMRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Forward a prompt to the user's LLM provider using their encrypted key."""
    import httpx

    # Fetch + decrypt the user's key for this provider
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT encrypted_key, key_nonce FROM user_api_keys WHERE user_id = $1 AND provider = $2",
            user_id, body.provider,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No API key stored for provider '{body.provider}'",
        )

    api_key = decrypt_api_key(row["encrypted_key"], row["key_nonce"])

    # Route to the correct provider
    router_map = {
        "anthropic": _proxy_anthropic,
        "openai": _proxy_openai,
        "together": _proxy_together,
        "google": _proxy_google,
        "xai": _proxy_xai,
    }
    handler = router_map.get(body.provider)
    if not handler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider: {body.provider}",
        )
    return await handler(api_key, body)


async def _proxy_anthropic(api_key: str, body: LLMRequest):
    import httpx

    model = body.model or "claude-sonnet-4-20250514"
    payload = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": body.messages,
    }
    if body.stream:
        payload["stream"] = True

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    if body.stream:
        return await _stream_proxy("https://api.anthropic.com/v1/messages", headers, payload)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
    return resp.json()


async def _proxy_openai(api_key: str, body: LLMRequest):
    import httpx

    model = body.model or "gpt-4o"
    payload = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": body.messages,
    }
    if body.stream:
        payload["stream"] = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if body.stream:
        return await _stream_proxy("https://api.openai.com/v1/chat/completions", headers, payload)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
    return resp.json()


async def _proxy_together(api_key: str, body: LLMRequest):
    import httpx

    model = body.model or "meta-llama/Llama-3-70b-chat-hf"
    payload = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": body.messages,
    }
    if body.stream:
        payload["stream"] = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if body.stream:
        return await _stream_proxy("https://api.together.xyz/v1/chat/completions", headers, payload)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post("https://api.together.xyz/v1/chat/completions", json=payload, headers=headers)
    return resp.json()


async def _proxy_google(api_key: str, body: LLMRequest):
    """Google Gemini — uses the OpenAI-compatible endpoint."""
    import httpx

    model = body.model or "gemini-2.5-flash"
    payload = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": body.messages,
    }
    if body.stream:
        payload["stream"] = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    if body.stream:
        return await _stream_proxy(url, headers, payload)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
    return resp.json()


async def _proxy_xai(api_key: str, body: LLMRequest):
    """xAI Grok — OpenAI-compatible endpoint."""
    import httpx

    model = body.model or "grok-3"
    payload = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": body.messages,
    }
    if body.stream:
        payload["stream"] = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://api.x.ai/v1/chat/completions"

    if body.stream:
        return await _stream_proxy(url, headers, payload)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload, headers=headers)
    return resp.json()


async def _stream_proxy(url: str, headers: dict, payload: dict) -> StreamingResponse:
    """Stream SSE responses from the upstream LLM provider."""
    import httpx

    async def generate():
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")
