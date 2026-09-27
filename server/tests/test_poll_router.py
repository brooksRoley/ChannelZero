"""
Tests for poll token persistence routes.

Covers:
- POST /poll/tokens: create token (201), JSON serialization, optional fields
- GET /poll/tokens/latest: return latest token, 404 when none, JSON deserialization

Uses FakeConn from conftest — no real DB or external HTTP calls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.poll.router import router as poll_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000007")
TOKEN_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
NOW = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(poll_router, prefix="/api/poll")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _token_row(
    *,
    answers: dict | str | None = None,
    palette: dict | str | None = None,
    tone: str | None = "warm",
    archetype: str | None = "the_seeker",
) -> dict:
    if answers is None:
        answers = {"q1": "a", "q2": "b"}
    if palette is None:
        palette = {"primary": "#7c3aed", "secondary": "#0ea5e9"}
    return {
        "id": TOKEN_ID,
        "user_id": USER_ID,
        "answers": answers,
        "theme": "night_forest",
        "palette": palette,
        "tone": tone,
        "archetype": archetype,
        "keywords": ["depth", "solitude"],
        "created_at": NOW,
    }


_BODY = {
    "answers": {"q1": "a", "q2": "b"},
    "theme": "night_forest",
    "palette": {"primary": "#7c3aed", "secondary": "#0ea5e9"},
    "tone": "warm",
    "archetype": "the_seeker",
    "keywords": ["depth", "solitude"],
}


# ── POST /api/poll/tokens ─────────────────────────────────────────────────────


class TestSavePollToken:
    def test_save_returns_201(self):
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            resp = TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        assert resp.status_code == 201

    def test_save_returns_token_fields(self):
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            resp = TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        body = resp.json()
        assert body["theme"] == "night_forest"
        assert body["tone"] == "warm"
        assert body["archetype"] == "the_seeker"
        assert body["keywords"] == ["depth", "solitude"]
        assert body["answers"] == {"q1": "a", "q2": "b"}
        assert body["palette"] == {"primary": "#7c3aed", "secondary": "#0ea5e9"}

    def test_save_stores_answers_as_json_string(self):
        """Router should JSON-serialize answers before the INSERT."""
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        query, args = conn.fetchrow_calls[0]
        # args[1] is the answers param; it should be a JSON string
        answers_arg = args[1]
        assert isinstance(answers_arg, str)
        assert json.loads(answers_arg) == {"q1": "a", "q2": "b"}

    def test_save_stores_palette_as_json_string(self):
        """Router should JSON-serialize palette before the INSERT."""
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        query, args = conn.fetchrow_calls[0]
        # args[3] is the palette param
        palette_arg = args[3]
        assert isinstance(palette_arg, str)
        assert json.loads(palette_arg) == {"primary": "#7c3aed", "secondary": "#0ea5e9"}

    def test_save_with_no_tone_or_archetype(self):
        """tone and archetype are optional; None values should be accepted."""
        conn = FakeConn(fetchrow_results=[_token_row(tone=None, archetype=None)])
        body = {**_BODY, "tone": None, "archetype": None}
        with patch_conn(conn):
            resp = TestClient(_make_app()).post("/api/poll/tokens", json=body)
        assert resp.status_code == 201
        assert resp.json()["tone"] is None
        assert resp.json()["archetype"] is None

    def test_save_response_decodes_string_answers(self):
        """_row_to_response must decode JSON-string answers from DB rows."""
        conn = FakeConn(fetchrow_results=[_token_row(answers=json.dumps({"q1": "a"}))])
        with patch_conn(conn):
            resp = TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        assert resp.json()["answers"] == {"q1": "a"}

    def test_save_response_decodes_string_palette(self):
        """_row_to_response must decode JSON-string palette from DB rows."""
        conn = FakeConn(
            fetchrow_results=[_token_row(palette=json.dumps({"primary": "#7c3aed"}))]
        )
        with patch_conn(conn):
            resp = TestClient(_make_app()).post("/api/poll/tokens", json=_BODY)
        assert resp.json()["palette"] == {"primary": "#7c3aed"}


# ── GET /api/poll/tokens/latest ───────────────────────────────────────────────


class TestGetLatestToken:
    def test_get_latest_returns_200(self):
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            resp = TestClient(_make_app()).get("/api/poll/tokens/latest")
        assert resp.status_code == 200

    def test_get_latest_returns_token_fields(self):
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            resp = TestClient(_make_app()).get("/api/poll/tokens/latest")
        body = resp.json()
        assert body["theme"] == "night_forest"
        assert body["answers"] == {"q1": "a", "q2": "b"}
        assert body["id"] == str(TOKEN_ID)

    def test_get_latest_404_when_no_token(self):
        """Should return 404 when the user has no poll tokens."""
        conn = FakeConn(fetchrow_results=[None])
        with patch_conn(conn):
            resp = TestClient(_make_app()).get("/api/poll/tokens/latest")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No poll token found"

    def test_get_latest_decodes_string_answers(self):
        conn = FakeConn(fetchrow_results=[_token_row(answers=json.dumps({"q1": "x"}))])
        with patch_conn(conn):
            resp = TestClient(_make_app()).get("/api/poll/tokens/latest")
        assert resp.json()["answers"] == {"q1": "x"}

    def test_get_latest_decodes_string_palette(self):
        conn = FakeConn(
            fetchrow_results=[_token_row(palette=json.dumps({"primary": "#000"}))]
        )
        with patch_conn(conn):
            resp = TestClient(_make_app()).get("/api/poll/tokens/latest")
        assert resp.json()["palette"] == {"primary": "#000"}

    def test_get_latest_query_uses_user_id(self):
        """The SELECT query should filter by the authenticated user's ID."""
        conn = FakeConn(fetchrow_results=[_token_row()])
        with patch_conn(conn):
            TestClient(_make_app()).get("/api/poll/tokens/latest")
        query, args = conn.fetchrow_calls[0]
        assert str(USER_ID) in args or USER_ID in args


# ── helpers ───────────────────────────────────────────────────────────────────


from unittest.mock import patch as _patch
from contextlib import contextmanager


@contextmanager
def patch_conn(conn: FakeConn):
    with _patch("app.poll.router.get_conn", make_get_conn(conn)):
        yield
