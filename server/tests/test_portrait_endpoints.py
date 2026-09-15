"""
Contract tests for /api/portrait — GET state machine and POST /generate.

The portrait router is mounted on a bare FastAPI app with the auth
dependency overridden; DB and LLM are patched at the service module.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.portrait.router import router as portrait_router
from app.portrait.stitcher import PROVIDER_COLUMNS
from app.ratelimit import limiter

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime.now(timezone.utc)

SPOTIFY = {"genres": ["ambient"], "audio_avg": {"valence": 0.4}}
GITHUB = {"username": "dev", "top_languages": ["Python"]}

VALID_PORTRAIT = {
    "headline": "You archive what you cannot hold.",
    "sections": [
        {"title": "Night Cartographer", "body": "Prose.", "providers": ["spotify", "github"]}
    ],
    "throughline": "The pattern beneath.",
}


def _vibe_row(providers: dict | None = None, portrait=None, generated_at=None, source=None) -> dict:
    row = {col: None for col in PROVIDER_COLUMNS.values()}
    for key, data in (providers or {}).items():
        row[PROVIDER_COLUMNS[key]] = data
    row["portrait"] = portrait
    row["portrait_generated_at"] = generated_at
    row["portrait_source_providers"] = source
    return row


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(portrait_router, prefix="/api/portrait")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _client_with(rows: list, llm: bool = True) -> tuple[TestClient, FakeConn]:
    """TestClient with DB rows queued and llm_configured patched."""
    conn = FakeConn(fetchrow_results=rows)
    patches = [
        patch("app.portrait.service.get_conn", make_get_conn(conn)),
        patch("app.portrait.router.llm_configured", return_value=llm),
    ]
    client = TestClient(_make_app())
    for p in patches:
        p.start()
        client_patches.append(p)
    return client, conn


client_patches: list = []


@pytest.fixture(autouse=True)
def reset_limiter():
    """Reset rate-limit counters so portrait/generate POST tests don't bleed across tests."""
    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def _cleanup_patches():
    yield
    while client_patches:
        client_patches.pop().stop()


# ── GET /api/portrait — state machine ────────────────────────────────


class TestGetPortraitStates:
    def test_no_vibe_row_is_insufficient(self):
        client, _ = _client_with([None, None])
        body = client.get("/api/portrait").json()
        assert body["status"] == "insufficient_providers"
        assert body["connected_providers"] == []

    def test_one_provider_is_insufficient(self):
        client, _ = _client_with([_vibe_row({"spotify": SPOTIFY}), None])
        body = client.get("/api/portrait").json()
        assert body["status"] == "insufficient_providers"
        assert body["connected_providers"] == ["spotify"]

    def test_no_llm_still_returns_stored_portrait(self):
        row = _vibe_row(
            {"spotify": SPOTIFY, "github": GITHUB},
            portrait=json.dumps(VALID_PORTRAIT),
            generated_at=NOW,
            source=["spotify", "github"],
        )
        client, _ = _client_with([row, None], llm=False)
        body = client.get("/api/portrait").json()
        assert body["status"] == "no_llm"
        assert body["llm_available"] is False
        assert body["portrait"]["headline"] == VALID_PORTRAIT["headline"]

    def test_two_providers_no_portrait_is_empty(self):
        client, _ = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        body = client.get("/api/portrait").json()
        assert body["status"] == "empty"
        assert body["portrait"] is None

    def test_provider_set_change_is_stale(self):
        row = _vibe_row(
            {"spotify": SPOTIFY, "github": GITHUB},
            portrait=json.dumps(VALID_PORTRAIT),
            generated_at=NOW - timedelta(days=1),
            source=["spotify"],  # github connected since
        )
        client, _ = _client_with([row, None])
        assert client.get("/api/portrait").json()["status"] == "stale"

    def test_old_portrait_is_stale(self):
        row = _vibe_row(
            {"spotify": SPOTIFY, "github": GITHUB},
            portrait=json.dumps(VALID_PORTRAIT),
            generated_at=NOW - timedelta(days=30),
            source=["spotify", "github"],
        )
        client, _ = _client_with([row, None])
        assert client.get("/api/portrait").json()["status"] == "stale"

    def test_fresh_matching_portrait_is_ready(self):
        row = _vibe_row(
            {"spotify": SPOTIFY, "github": GITHUB},
            portrait=json.dumps(VALID_PORTRAIT),
            generated_at=NOW - timedelta(days=2),
            source=["spotify", "github"],
        )
        client, _ = _client_with([row, None])
        body = client.get("/api/portrait").json()
        assert body["status"] == "ready"
        assert body["portrait"]["sections"][0]["title"] == "Night Cartographer"

    def test_corrupt_stored_portrait_treated_as_empty(self):
        row = _vibe_row(
            {"spotify": SPOTIFY, "github": GITHUB},
            portrait='{"not": "a portrait"}',
            generated_at=NOW,
            source=["spotify", "github"],
        )
        client, _ = _client_with([row, None])
        assert client.get("/api/portrait").json()["status"] == "empty"


# ── POST /api/portrait/generate ──────────────────────────────────────


class TestGeneratePortrait:
    def test_insufficient_providers_400(self):
        client, _ = _client_with([_vibe_row({"spotify": SPOTIFY}), None])
        resp = client.post("/api/portrait/generate")
        assert resp.status_code == 400
        assert "at least 2" in resp.json()["detail"]

    def test_no_llm_503(self):
        client, _ = _client_with(
            [_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None], llm=False
        )
        resp = client.post("/api/portrait/generate")
        assert resp.status_code == 503

    def test_success_persists_and_returns_portrait(self):
        client, conn = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        with patch(
            "app.portrait.service.chat_completion",
            AsyncMock(return_value=json.dumps(VALID_PORTRAIT)),
        ) as mock_llm:
            resp = client.post("/api/portrait/generate")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["portrait"]["headline"] == VALID_PORTRAIT["headline"]
        assert sorted(body["source_providers"]) == ["github", "spotify"]
        assert sorted(body["connected_providers"]) == ["github", "spotify"]
        assert body["llm_available"] is True
        mock_llm.assert_awaited_once()

        assert len(conn.execute_calls) == 1
        query, args = conn.execute_calls[0]
        assert "SET portrait" in query
        persisted = json.loads(args[0])
        assert persisted["headline"] == VALID_PORTRAIT["headline"]
        assert sorted(args[1]) == ["github", "spotify"]
        assert args[2] == USER_ID

    def test_hallucinated_section_providers_dropped_before_persist(self):
        payload = json.loads(json.dumps(VALID_PORTRAIT))
        payload["sections"][0]["providers"] = ["spotify", "linkedin"]
        client, conn = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        with patch(
            "app.portrait.service.chat_completion",
            AsyncMock(return_value=json.dumps(payload)),
        ):
            resp = client.post("/api/portrait/generate")

        assert resp.status_code == 200
        persisted = json.loads(conn.execute_calls[0][1][0])
        assert persisted["sections"][0]["providers"] == ["spotify"]

    def test_unparseable_output_retries_once_then_502(self):
        client, conn = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        with patch(
            "app.portrait.service.chat_completion",
            AsyncMock(return_value="I am not JSON, I am prose."),
        ) as mock_llm:
            resp = client.post("/api/portrait/generate")

        assert resp.status_code == 502
        assert mock_llm.await_count == 2
        # Retry carries the strict-JSON reminder
        retry_prompt = mock_llm.await_args_list[1].args[0]
        assert "ONLY the raw JSON object" in retry_prompt
        assert conn.execute_calls == []  # nothing persisted on failure

    def test_retry_success_persists(self):
        client, conn = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        with patch(
            "app.portrait.service.chat_completion",
            AsyncMock(side_effect=["```\nnot json\n```" , json.dumps(VALID_PORTRAIT)]),
        ) as mock_llm:
            resp = client.post("/api/portrait/generate")

        assert resp.status_code == 200
        assert mock_llm.await_count == 2
        assert len(conn.execute_calls) == 1

    def test_llm_502_passes_through(self):
        client, conn = _client_with([_vibe_row({"spotify": SPOTIFY, "github": GITHUB}), None])
        with patch(
            "app.portrait.service.chat_completion",
            AsyncMock(side_effect=HTTPException(status_code=502, detail="LLM call failed")),
        ):
            resp = client.post("/api/portrait/generate")

        assert resp.status_code == 502
        assert conn.execute_calls == []
