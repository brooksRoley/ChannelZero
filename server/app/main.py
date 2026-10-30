"""\nChannelZero API — FastAPI application entry point.\n"""

from __future__ import annotations

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .config import get_settings
from .db import init_pool, close_pool
from .ratelimit import limiter
from .auth.router import router as auth_router
from .auth.oauth import router as oauth_router
from .poll.router import router as poll_router
from .llm.router import router as llm_router
from .intake.router import router as intake_router
from .spotify.router import router as spotify_router
from .oracle.router import router as oracle_router
from .strava.router import router as strava_router
from .psychometrics.router import router as psychometrics_router
from .gcal.router import router as gcal_router
from .steam.router import router as steam_router
from .twitter.router import router as twitter_router
from .letterboxd.router import router as letterboxd_router
from .connectors.router import router as connectors_router
from .portrait.router import router as portrait_router
from .costar.router import router as costar_router
from .github.router import router as github_router
from .youtube.router import router as youtube_router
from .reddit.router import router as reddit_router
from .instagram.router import router as instagram_router
from .tiktok.router import router as tiktok_router
from .analytics.router import router as analytics_router
from .brain.router import router as brain_router
from .vector.router import router as vector_router
from .practice.router import router as practice_router
from .movement.router import router as movement_router


logger = logging.getLogger("channelzero")


async def _probe_embed_key_on_boot() -> None:
    """
    Fire-and-forget startup probe: make one cheap embedding call so an invalid
    OPENAI_EMBED_KEY (revoked, wrong scope, or — as of 2026-06 — an exhausted
    billing quota returning 429 insufficient_quota) surfaces in Render logs on
    every deploy instead of failing silently inside background synthesis tasks.

    Never blocks or crashes boot — any failure is logged, not raised.

    Only runs when ENABLE_EMBEDDINGS=true — the pipeline is formally shelved
    (see Creative Direction in CLAUDE.md), so by default there is nothing to
    probe and no point burning a request against a known-dead key.
    """
    settings = get_settings()
    if not settings.enable_embeddings:
        logger.info(
            "BOOT embed check: skipped — embedding pipeline disabled "
            "(ENABLE_EMBEDDINGS=false; matching/vibe-vector network is shelved)"
        )
        return
    if not settings.openai_embed_key:
        logger.error("BOOT embed check: OPENAI_EMBED_KEY not configured — matching pipeline is dead")
        return
    try:
        import httpx
        from .vector.service import EMBEDDING_MODEL, EMBEDDING_ENDPOINT
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                EMBEDDING_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.openai_embed_key}", "Content-Type": "application/json"},
                json={"model": EMBEDDING_MODEL, "input": "boot health check"},
            )
        if resp.status_code == 200:
            logger.info("BOOT embed check: OPENAI_EMBED_KEY healthy (%s)", EMBEDDING_MODEL)
        else:
            logger.error(
                "BOOT embed check: OPENAI_EMBED_KEY UNHEALTHY — status=%d body=%s "
                "→ matching/Oracle/journal embeddings will silently no-op until fixed",
                resp.status_code, resp.text[:300],
            )
    except Exception:
        logger.exception("BOOT embed check: probe failed (transport error)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect to DB + probe embed key. Shutdown: drain pool."""
    import asyncio

    settings = get_settings()
    pool = await init_pool()

    # Run migrations check / stamp (lightweight — just verifies tables exist)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'users')"
        )
        if not exists and settings.debug:
            print("⚠  Tables not found. Run: python -m server.migrate")

    # Non-blocking embed-key probe — surfaces a dead matching pipeline on
    # deploy. No-ops unless ENABLE_EMBEDDINGS=true (pipeline shelved).
    asyncio.create_task(_probe_embed_key_on_boot())

    yield

    await close_pool()


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 with a Retry-After header so blocked clients know when to back off.

    We avoid slowapi's global ``headers_enabled`` mode because it tries to inject
    headers into every (success) response and errors on endpoints that return a
    Pydantic ``response_model`` rather than a raw Response. Adding Retry-After
    only on the 429 path sidesteps that entirely.
    """
    try:
        retry_after = int(exc.limit.limit.get_expiry())
    except Exception:
        retry_after = 60
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down and try again."},
        headers={"Retry-After": str(retry_after)},
    )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ChannelZero API",
        version="0.1.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # ── Rate limiting ───────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────
    prefix = settings.api_prefix
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(oauth_router, prefix=f"{prefix}/auth", tags=["oauth"])
    app.include_router(poll_router, prefix=f"{prefix}/poll", tags=["poll"])
    app.include_router(llm_router, prefix=f"{prefix}/llm", tags=["llm"])
    app.include_router(intake_router, prefix=f"{prefix}/intake", tags=["intake"])
    app.include_router(spotify_router, prefix=f"{prefix}/spotify", tags=["spotify"])
    app.include_router(oracle_router, prefix=f"{prefix}/oracle", tags=["oracle"])
    app.include_router(strava_router, prefix=f"{prefix}/strava", tags=["strava"])
    app.include_router(psychometrics_router, prefix=f"{prefix}/psychometrics", tags=["psychometrics"])
    app.include_router(gcal_router, prefix=f"{prefix}/gcal", tags=["gcal"])
    app.include_router(steam_router, prefix=f"{prefix}/steam", tags=["steam"])
    app.include_router(twitter_router, prefix=f"{prefix}/twitter", tags=["twitter"])
    app.include_router(letterboxd_router, prefix=f"{prefix}/letterboxd", tags=["letterboxd"])
    app.include_router(connectors_router, prefix=f"{prefix}/connectors", tags=["connectors"])
    app.include_router(portrait_router, prefix=f"{prefix}/portrait", tags=["portrait"])
    app.include_router(costar_router, prefix=f"{prefix}/costar", tags=["costar"])
    app.include_router(github_router, prefix=f"{prefix}/github", tags=["github"])
    app.include_router(youtube_router, prefix=f"{prefix}/youtube", tags=["youtube"])
    app.include_router(reddit_router, prefix=f"{prefix}/reddit", tags=["reddit"])
    app.include_router(instagram_router, prefix=f"{prefix}/instagram", tags=["instagram"])
    app.include_router(tiktok_router, prefix=f"{prefix}/tiktok", tags=["tiktok"])
    app.include_router(analytics_router, prefix=f"{prefix}/analytics", tags=["analytics"])
    app.include_router(brain_router, prefix=f"{prefix}/brain", tags=["brain"])
    app.include_router(practice_router, prefix=f"{prefix}/practice", tags=["practice"])
    app.include_router(movement_router, prefix=f"{prefix}/movement", tags=["movement"])
    app.include_router(vector_router, prefix=f"{prefix}/vector", tags=["vector"])

    # ── Global exception handler (ensures CORS headers on 500s) ──
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.getLogger("channelzero").exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ── Health ──────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "channelzero-api"}

    @app.get("/api/health/embeddings")
    async def health_embeddings():
        """
        Diagnostic: test OpenAI embed key + Pinecone connectivity.
        Returns status, latency, and error details for each dependency.
        """
        import time
        import httpx
        from .vector.service import _get_index_sync, EMBEDDING_MODEL

        result: dict = {"openai": {"status": "unknown"}, "pinecone": {"status": "unknown"}}

        # ── OpenAI embed key check ──
        embed_key = settings.openai_embed_key
        if not embed_key:
            result["openai"] = {"status": "error", "error": "OPENAI_EMBED_KEY not configured"}
        else:
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {embed_key}", "Content-Type": "application/json"},
                        json={"model": EMBEDDING_MODEL, "input": "health check"},
                    )
                    resp.raise_for_status()
                latency = round((time.monotonic() - t0) * 1000)
                dims = len(resp.json()["data"][0]["embedding"])
                result["openai"] = {"status": "ok", "latency_ms": latency, "dimensions": dims}
            except httpx.HTTPStatusError as e:
                result["openai"] = {"status": "error", "code": e.response.status_code, "error": e.response.text[:500]}
            except Exception as e:
                result["openai"] = {"status": "error", "error": str(e)[:500]}

        # ── Pinecone check ──
        import asyncio
        t0 = time.monotonic()
        try:
            index = await asyncio.to_thread(_get_index_sync)
            if index is None:
                result["pinecone"] = {"status": "error", "error": "PINECONE_API_KEY not configured or index unavailable"}
            else:
                stats = await asyncio.to_thread(index.describe_index_stats)
                latency = round((time.monotonic() - t0) * 1000)
                result["pinecone"] = {
                    "status": "ok",
                    "latency_ms": latency,
                    "total_vectors": stats.total_vector_count,
                    "namespaces": {k: v.vector_count for k, v in stats.namespaces.items()},
                }
        except Exception as e:
            result["pinecone"] = {"status": "error", "error": str(e)[:500]}

        overall = "ok" if all(r["status"] == "ok" for r in result.values()) else "degraded"
        return {"status": overall, **result}

    return app


app = create_app()
