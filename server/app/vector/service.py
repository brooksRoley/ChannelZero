"""
Pinecone vector service — dual-namespace psychological mapping layer.

Namespace "users":
  One vector per user (ID = user UUID). Generated from intake confession text
  via OpenAI text-embedding-3-small (1,536 dims). Used for ANN matching
  ("find the 3 people closest to this user in psychological space") and karma
  penalties (Gaussian perturbation pushes toxic users into the margins).

Namespace "journal":
  One vector per journal entry. Used for semantic RAG during intake — surfaces
  resonant past entries as context before analysis.

Both namespaces share one Pinecone index at 1,536 dims (cosine).
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from contextlib import asynccontextmanager

import httpx
import numpy as np
from pinecone import Pinecone, ServerlessSpec

from ..config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
NAMESPACE_USERS = "users"
NAMESPACE_JOURNAL = "journal"

_index_cache: dict = {}


def _embeddings_disabled(caller: str) -> bool:
    """
    Feature flag guard for the shelved embedding pipeline (ENABLE_EMBEDDINGS,
    default false — see CLAUDE.md Creative Direction). When disabled, every
    public entry point returns early and cleanly instead of burning a request
    against a dead embed key and silently failing.
    """
    if get_settings().enable_embeddings:
        return False
    logger.info("%s skipped: embedding pipeline disabled (ENABLE_EMBEDDINGS=false)", caller)
    return True


def _get_client() -> Pinecone | None:
    key = get_settings().pinecone_api_key
    if not key:
        return None
    # Not cached with lru_cache — settings may not be available at import time
    return Pinecone(api_key=key)


def _get_index_sync():
    pc = _get_client()
    if pc is None:
        return None
    name = get_settings().pinecone_index
    if name not in _index_cache:
        existing = [i.name for i in pc.list_indexes()]
        if name not in existing:
            pc.create_index(
                name=name,
                dimension=EMBEDDING_DIMS,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        _index_cache[name] = pc.Index(name)
    return _index_cache[name]


# ── Embedding ────────────────────────────────────────────────────────────────

EMBEDDING_ENDPOINT = "https://api.openai.com/v1/embeddings"


async def _embed(
    text: str,
    *,
    user_id: str | None = None,
    caller: str = "unknown",
) -> list[float]:
    """
    Call OpenAI text-embedding-3-small. Returns [] on any failure (missing key,
    auth error, transport error, malformed response) so callers' `if not vector`
    branches fire instead of the exception bubbling into a silent background task.

    Auth errors (401/403) are logged at ERROR with endpoint, model, status, and
    user_id so they surface in Render logs — these typically indicate a rotated
    or revoked OPENAI_EMBED_KEY and require operator action.
    """
    key = get_settings().openai_embed_key
    if not key:
        logger.error(
            "embed_skipped: OPENAI_EMBED_KEY not configured "
            "(caller=%s user_id=%s endpoint=%s model=%s)",
            caller, user_id, EMBEDDING_ENDPOINT, EMBEDDING_MODEL,
        )
        return []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                EMBEDDING_ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": EMBEDDING_MODEL, "input": text},
            )
            resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        body = e.response.text[:500]
        if status_code in (401, 403):
            logger.error(
                "embed_auth_error: %d from OpenAI — OPENAI_EMBED_KEY likely revoked/rotated "
                "(caller=%s user_id=%s endpoint=%s model=%s body=%s)",
                status_code, caller, user_id, EMBEDDING_ENDPOINT, EMBEDDING_MODEL, body,
            )
        else:
            logger.error(
                "embed_http_error: %d from OpenAI "
                "(caller=%s user_id=%s endpoint=%s model=%s body=%s)",
                status_code, caller, user_id, EMBEDDING_ENDPOINT, EMBEDDING_MODEL, body,
            )
        return []
    except Exception:
        logger.exception(
            "embed_failed: unexpected error (caller=%s user_id=%s endpoint=%s model=%s)",
            caller, user_id, EMBEDDING_ENDPOINT, EMBEDDING_MODEL,
        )
        return []


# ── User vibe vectors ────────────────────────────────────────────────────────

async def upsert_user_vector(
    user_id: str,
    confession_text: str,
    attachment_style: str,
    defense_mechanism: str,
    readiness_score: int,
) -> bool:
    """
    Generate a 1,536-dim embedding from the user's confession text and
    store it as their psychological coordinate in Pinecone.
    Returns True on success.
    """
    if _embeddings_disabled("upsert_user_vector"):
        return False
    try:
        vector = await _embed(confession_text, user_id=user_id, caller="upsert_user_vector")
        if not vector:
            logger.error("upsert_user_vector aborted: embed returned empty for %s", user_id)
            return False
        index = await asyncio.to_thread(_get_index_sync)
        if index is None:
            logger.error("upsert_user_vector aborted: Pinecone index unavailable for %s", user_id)
            return False
        await asyncio.to_thread(
            index.upsert,
            vectors=[{
                "id": user_id,
                "values": vector,
                "metadata": {
                    "user_id": user_id,
                    "attachment_style": attachment_style,
                    "defense_mechanism": defense_mechanism,
                    "readiness_score": readiness_score,
                },
            }],
            namespace=NAMESPACE_USERS,
        )
        return True
    except Exception:
        logger.exception("Pinecone user vector upsert failed for %s", user_id)
        return False


async def find_nearest_users(user_id: str, top_k: int = 3) -> list[dict]:
    """
    ANN lookup: return the top_k users psychologically closest to user_id.
    Excludes the querying user. Returns [] if user has no vector yet.
    """
    if _embeddings_disabled("find_nearest_users"):
        return []
    try:
        index = await asyncio.to_thread(_get_index_sync)
        if index is None:
            return []

        # Fetch the user's own vector to query against
        fetch_result = await asyncio.to_thread(
            index.fetch, ids=[user_id], namespace=NAMESPACE_USERS,
        )
        if user_id not in fetch_result.vectors:
            return []

        user_vector = fetch_result.vectors[user_id].values

        # top_k + 1 because the user will match themselves at score ~1.0
        query_result = await asyncio.to_thread(
            index.query,
            vector=user_vector,
            top_k=top_k + 1,
            include_metadata=True,
            namespace=NAMESPACE_USERS,
        )

        matches = [m for m in query_result.matches if m.id != user_id][:top_k]
        return [{"user_id": m.id, "score": round(m.score, 4), **m.metadata} for m in matches]
    except Exception:
        logger.exception("Pinecone ANN query failed for user %s", user_id)
        return []


# ── Per-user lock for read-modify-write on Pinecone vectors ───────────────────
# Pinecone has no native CAS/transactions, so we use an in-process asyncio lock
# keyed by user_id to serialize concurrent penalty operations for the same user.
# WeakValueDictionary: locks are collected as soon as no coroutine holds them,
# so the registry can't grow unboundedly on a long-running Render worker.
_user_locks: "weakref.WeakValueDictionary[str, asyncio.Lock]" = weakref.WeakValueDictionary()


def _get_user_lock(user_id: str) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


async def apply_karma_penalty(user_id: str, karma_delta: float) -> None:
    """
    When a user's karma drops, add scaled Gaussian noise to their vector —
    pushing their coordinate point away from healthy clusters into the margins.
    karma_delta should be negative (e.g. -10 for a 10-point drop).

    Uses a per-user asyncio lock to prevent concurrent read-modify-write races.
    """
    if _embeddings_disabled("apply_karma_penalty"):
        return
    if karma_delta >= 0:
        return

    # Scale noise: a 100-point drop → σ=0.5 perturbation; clamp at 0.5
    penalty_scale = min(0.5, abs(karma_delta) / 100.0)

    lock = _get_user_lock(user_id)
    async with lock:
        try:
            index = await asyncio.to_thread(_get_index_sync)
            if index is None:
                return

            fetch_result = await asyncio.to_thread(
                index.fetch, ids=[user_id], namespace=NAMESPACE_USERS,
            )
            if user_id not in fetch_result.vectors:
                return

            record = fetch_result.vectors[user_id]
            arr = np.array(record.values, dtype=np.float32)
            noise = np.random.randn(len(arr)).astype(np.float32) * penalty_scale
            perturbed = arr + noise
            norm = np.linalg.norm(perturbed)
            if norm == 0:
                logger.warning("Zero-norm vector after penalty for %s — skipping", user_id)
                return
            penalized = (perturbed / norm).tolist()

            await asyncio.to_thread(
                index.upsert,
                vectors=[{"id": user_id, "values": penalized, "metadata": record.metadata}],
                namespace=NAMESPACE_USERS,
            )
            logger.info("Karma penalty applied to %s (scale=%.3f)", user_id, penalty_scale)
        except Exception:
            logger.exception("Karma penalty failed for user %s", user_id)


# ── Journal RAG ──────────────────────────────────────────────────────────────

async def query_relevant_journal(user_id: str, query_text: str, top_k: int = 5) -> list[dict]:
    """Return metadata of top-K journal entries semantically closest to query_text."""
    if _embeddings_disabled("query_relevant_journal"):
        return []
    try:
        vector = await _embed(query_text, user_id=user_id, caller="query_relevant_journal")
        if not vector:
            return []
        index = await asyncio.to_thread(_get_index_sync)
        if index is None:
            return []
        results = await asyncio.to_thread(
            index.query,
            vector=vector,
            top_k=top_k,
            filter={"user_id": {"$eq": user_id}},
            include_metadata=True,
            namespace=NAMESPACE_JOURNAL,
        )
        return [m.metadata for m in results.matches if m.score > 0.5]
    except Exception:
        logger.exception("Pinecone journal query failed for user %s", user_id)
        return []
