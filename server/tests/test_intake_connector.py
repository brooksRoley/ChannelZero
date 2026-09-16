"""Tests for the intake confessional pipeline.

Covers: POST /intake/confess (NLP extraction, shadow-log insert, vibe-vector upsert),
        GET  /intake/vector  (fetch or 404),
        POST /intake/fitting (self/ideal phase, invalid phase rejection).

All DB and Pinecone calls are mocked — no real connections required.
"""

from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from fastapi.testclient import TestClient

from app.intake.router import router
from app.auth.deps import get_current_user_id
from tests.conftest import FakeConn, make_get_conn

USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_FAKE_ENCRYPTED = (b"enc", b"nonce")


# ── helpers ──────────────────────────────────────────────────────────────────────────────


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/intake")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _make_tx(conn: FakeConn):
    """Return a get_tx-compatible async context manager factory."""
    @asynccontextmanager
    async def _tx():
        yield conn
    return _tx


# ── /confess  — async tests ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
class TestConfess:
    """POST /intake/confess — NLP, shadow log, vibe vector upsert."""

    async def _post(self, confessions, *, memories=None, extra=None):
        conn = FakeConn()
        app = _build_app()
        body = {"confessions": confessions, **(extra or {})}
        with (
            patch("app.intake.router.query_relevant_journal",
                  new_callable=AsyncMock, return_value=memories or []),
            patch("app.intake.router.encrypt_api_key", return_value=_FAKE_ENCRYPTED),
            patch("app.intake.router.get_tx", new=_make_tx(conn)),
            patch("app.intake.router.upsert_user_vector", new_callable=AsyncMock),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/intake/confess", json=body)
        return resp, conn

    async def test_200_with_required_fields(self):
        resp, _ = await self._post(["I feel something today."])
        assert resp.status_code == 200
        data = resp.json()
        for key in ("attachment_style", "defense_mechanism", "readiness_score", "insight", "memories"):
            assert key in data

    async def test_readiness_in_range(self):
        resp, _ = await self._post(["neutral text"])
        score = resp.json()["readiness_score"]
        assert 20 <= score <= 100

    async def test_attachment_anxious_preoccupied(self):
        resp, _ = await self._post(["I am so afraid of being abandoned by everyone I love."])
        assert resp.json()["attachment_style"] == "anxious-preoccupied"

    async def test_attachment_dismissive_avoidant(self):
        resp, _ = await self._post(["I prefer to be alone; I am completely self-sufficient."])
        assert resp.json()["attachment_style"] == "dismissive-avoidant"

    async def test_attachment_fearful_avoidant(self):
        # Pattern: push.{0,10}pull — "push and pull" matches in 5 chars.
        # Must not contain anxious/dismissive trigger words (afraid, alone, etc.)
        resp, _ = await self._post(["I push and pull in every relationship — I can never decide."])
        assert resp.json()["attachment_style"] == "fearful-avoidant"

    async def test_defense_humor(self):
        resp, _ = await self._post(["I always joke and use humor to hide everything."])
        assert resp.json()["defense_mechanism"] == "humor"

    async def test_defense_projection(self):
        resp, _ = await self._post(["I blame them — it's always their fault."])
        assert resp.json()["defense_mechanism"] == "projection"

    async def test_defense_denial(self):
        resp, _ = await self._post(["I'm fine, it doesn't matter, I don't care at all."])
        assert resp.json()["defense_mechanism"] == "denial"

    async def test_memory_hits_appear_in_response(self):
        memories = [{"text_preview": "echo one"}, {"text_preview": "echo two"}]
        resp, _ = await self._post(["something"], memories=memories)
        assert resp.json()["memories"] == ["echo one", "echo two"]

    async def test_readiness_nudged_by_memories(self):
        # 2 memories add 6 to readiness; confirm score is >= baseline
        memories = [{"text_preview": "a"}, {"text_preview": "b"}]
        resp_no_mem, _ = await self._post(["neutral"])
        resp_with_mem, _ = await self._post(["neutral"], memories=memories)
        assert resp_with_mem.json()["readiness_score"] >= resp_no_mem.json()["readiness_score"]

    async def test_shadow_log_inserted(self):
        _, conn = await self._post(["secret"])
        sqls = [c[0].lower() for c in conn.execute_calls]
        assert any("intake_shadow_logs" in sql for sql in sqls)

    async def test_vibe_vector_upserted(self):
        _, conn = await self._post(["secret"])
        sqls = [c[0].lower() for c in conn.execute_calls]
        assert any("vibe_vectors" in sql for sql in sqls)

    async def test_exactly_two_db_writes(self):
        _, conn = await self._post(["one thought"])
        assert len(conn.execute_calls) == 2

    async def test_multiple_confessions_ok(self):
        resp, _ = await self._post(["first.", "second.", "third."])
        assert resp.status_code == 200

    async def test_with_poll_theme(self):
        resp, _ = await self._post(["thought"], extra={"poll_theme": "shadow"})
        assert resp.status_code == 200

    async def test_longer_text_increases_readiness(self):
        short_resp, _ = await self._post(["hi"])
        long_text = "I feel deeply and completely overwhelmed by everything around me. " * 5
        long_resp, _ = await self._post([long_text])
        assert long_resp.json()["readiness_score"] >= short_resp.json()["readiness_score"]


# ── /confess — pydantic validation (sync) ────────────────────────────────────────────────────────


class TestConfessValidation:
    """Pydantic model validation returns 422 without touching the DB."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(_build_app(), raise_server_exceptions=False)

    def test_empty_list_rejected(self, client):
        assert client.post("/intake/confess", json={"confessions": []}).status_code == 422

    def test_too_many_confessions_rejected(self, client):
        assert client.post("/intake/confess", json={"confessions": ["x"] * 21}).status_code == 422

    def test_confession_too_long_rejected(self, client):
        assert client.post("/intake/confess", json={"confessions": ["a" * 5001]}).status_code == 422

    def test_missing_confessions_field_rejected(self, client):
        assert client.post("/intake/confess", json={}).status_code == 422


# ── GET /intake/vector ──────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
class TestVibeVector:
    async def test_200_with_data(self):
        row = {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "user_id": USER_ID,
            "attachment_style": "secure",
            "defense_mechanism": "humor",
            "readiness_score": 75,
            "poll_theme": "shadow",
            "created_at": datetime.datetime(2026, 1, 1),
        }
        conn = FakeConn(fetchrow_results=[row])
        app = _build_app()
        with patch("app.intake.router.get_conn", new=make_get_conn(conn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/intake/vector")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_style"] == "secure"
        assert data["readiness_score"] == 75

    async def test_404_when_no_vector(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _build_app()
        with patch("app.intake.router.get_conn", new=make_get_conn(conn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/intake/vector")

        assert resp.status_code == 404


# ── POST /intake/fitting ──────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
class TestFitting:
    async def _post_fitting(self, phase: str, data: dict):
        conn = FakeConn()
        app = _build_app()
        with patch("app.intake.router.get_conn", new=make_get_conn(conn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/intake/fitting", json={"phase": phase, "data": data})
        return resp, conn

    async def test_self_phase_204(self):
        resp, conn = await self._post_fitting("self", {"height": "tall"})
        assert resp.status_code == 204
        assert len(conn.execute_calls) == 1
        assert "fitting_self" in conn.execute_calls[0][0].lower()

    async def test_ideal_phase_204(self):
        resp, conn = await self._post_fitting("ideal", {"energy": "calm"})
        assert resp.status_code == 204
        assert "fitting_ideal" in conn.execute_calls[0][0].lower()

    async def test_invalid_phase_422(self):
        resp, _ = await self._post_fitting("other", {})
        assert resp.status_code == 422
