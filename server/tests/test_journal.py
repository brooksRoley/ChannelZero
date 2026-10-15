"""
Tests for the Journal CRUD + sync endpoints.

Covers:
- POST /journal/entries: create entry (201), embed task fires
- GET /journal/entries: list all, date filter, drawings JSON-string decode
- PATCH /journal/entries/{id}: update happy path, 404 when missing
- DELETE /journal/entries/{id}: delete happy path, 404 when "DELETE 0"
- POST /journal/sync: bulk upsert + fetch, last_sync filter, entries cap >200 → 422

Uses FakeConn from conftest — no real DB or external HTTP calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.journal.router import router as journal_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000004")
ENTRY_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(journal_router, prefix="/api/journal")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _entry_row(*, text: str = "Today I felt the ocean.", mood: str | None = "reflective") -> dict:
    return {
        "id": ENTRY_ID,
        "user_id": USER_ID,
        "text": text,
        "drawings": [],
        "mood": mood,
        "poll_token_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


class FakeConnDeleteMiss(FakeConn):
    """FakeConn variant whose execute() returns 'DELETE 0' to trigger the 404 path."""

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "DELETE 0"


# ── POST /api/journal/entries ─────────────────────────────────────────────────


class TestCreateEntry:
    def test_creates_entry_returns_201(self):
        conn = FakeConn(fetchrow_results=[_entry_row()])
        with (
            patch("app.journal.router.get_conn", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/entries",
                json={"text": "Today I felt the ocean.", "mood": "reflective"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["text"] == "Today I felt the ocean."
        assert body["mood"] == "reflective"
        assert body["drawings"] == []

    def test_creates_entry_fires_embed_task(self):
        mock_embed = AsyncMock()
        conn = FakeConn(fetchrow_results=[_entry_row(text="Introspection.")])
        with (
            patch("app.journal.router.get_conn", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=mock_embed),
        ):
            TestClient(_make_app()).post(
                "/api/journal/entries",
                json={"text": "Introspection."},
            )
        mock_embed.assert_called_once()

    def test_create_entry_with_empty_body_uses_defaults(self):
        conn = FakeConn(fetchrow_results=[_entry_row(text="", mood=None)])
        with (
            patch("app.journal.router.get_conn", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post("/api/journal/entries", json={})
        assert resp.status_code == 201

    def test_create_entry_with_drawings(self):
        row = {**_entry_row(), "drawings": [{"type": "path", "points": [[0, 0], [1, 1]]}]}
        conn = FakeConn(fetchrow_results=[row])
        with (
            patch("app.journal.router.get_conn", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/entries",
                json={"text": "", "drawings": [{"type": "path", "points": [[0, 0], [1, 1]]}]},
            )
        assert resp.status_code == 201
        assert resp.json()["drawings"][0]["type"] == "path"


# ── GET /api/journal/entries ──────────────────────────────────────────────────


class TestListEntries:
    def test_returns_empty_list_when_no_entries(self):
        conn = FakeConn(fetch_results=[[]])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/journal/entries")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_entries(self):
        rows = [_entry_row(text="Entry one"), _entry_row(text="Entry two")]
        conn = FakeConn(fetch_results=[rows])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/journal/entries")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        assert resp.json()[0]["text"] == "Entry one"

    def test_date_filter_returns_matching_entries(self):
        conn = FakeConn(fetch_results=[[_entry_row()]])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/journal/entries", params={"date": "2026-08-09"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_drawings_json_string_decoded_transparently(self):
        """asyncpg may return drawings JSONB as a string; _row_to_response decodes it."""
        import json
        row = {**_entry_row(), "drawings": json.dumps([{"type": "circle"}])}
        conn = FakeConn(fetch_results=[[row]])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).get("/api/journal/entries")
        assert resp.status_code == 200
        assert resp.json()[0]["drawings"] == [{"type": "circle"}]


# ── PATCH /api/journal/entries/{id} ──────────────────────────────────────────


class TestUpdateEntry:
    def test_updates_entry_returns_200(self):
        updated = _entry_row(text="Revised reflection.", mood="calm")
        conn = FakeConn(fetchrow_results=[updated])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).patch(
                f"/api/journal/entries/{ENTRY_ID}",
                json={"text": "Revised reflection.", "mood": "calm"},
            )
        assert resp.status_code == 200
        assert resp.json()["text"] == "Revised reflection."
        assert resp.json()["mood"] == "calm"

    def test_returns_404_when_entry_not_found(self):
        conn = FakeConn()  # fetchrow_results empty → returns None
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).patch(
                f"/api/journal/entries/{ENTRY_ID}",
                json={"mood": "lost"},
            )
        assert resp.status_code == 404

    def test_partial_update_mood_only(self):
        conn = FakeConn(fetchrow_results=[_entry_row(mood="serene")])
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).patch(
                f"/api/journal/entries/{ENTRY_ID}",
                json={"mood": "serene"},
            )
        assert resp.status_code == 200
        assert resp.json()["mood"] == "serene"


# ── DELETE /api/journal/entries/{id} ─────────────────────────────────────────


class TestDeleteEntry:
    def test_deletes_entry_returns_204(self):
        conn = FakeConn()  # execute returns "UPDATE 1" (≠ "DELETE 0") → success path
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).delete(f"/api/journal/entries/{ENTRY_ID}")
        assert resp.status_code == 204

    def test_returns_404_when_entry_not_found(self):
        conn = FakeConnDeleteMiss()
        with patch("app.journal.router.get_conn", make_get_conn(conn)):
            resp = TestClient(_make_app()).delete(f"/api/journal/entries/{ENTRY_ID}")
        assert resp.status_code == 404


# ── POST /api/journal/sync ────────────────────────────────────────────────────


class TestSyncEntries:
    def test_sync_empty_payload_returns_all_entries(self):
        conn = FakeConn(fetch_results=[[_entry_row()]])
        with (
            patch("app.journal.router.get_tx", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/sync",
                json={"entries": [], "last_sync": None},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "server_time" in data
        assert len(data["entries"]) == 1

    def test_sync_client_entries_execute_upserts(self):
        conn = FakeConn(fetch_results=[[]])
        with (
            patch("app.journal.router.get_tx", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/sync",
                json={"entries": [{"text": "Synced thought.", "mood": "open"}]},
            )
        assert resp.status_code == 200
        # executemany fires once with one arg-tuple for the single entry
        assert conn.executemany_calls, "expected executemany to be called"
        args_rows = conn.executemany_calls[0][1]
        assert len(args_rows) == 1
        assert args_rows[0][2] == "Synced thought."  # text is 3rd param (after id, user_id)

    def test_sync_with_client_supplied_id_enables_idempotent_upsert(self):
        """When the client sends a server-assigned id, ON CONFLICT (id) fires correctly."""
        existing_id = str(ENTRY_ID)
        conn = FakeConn(fetch_results=[[_entry_row()]])
        with (
            patch("app.journal.router.get_tx", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/sync",
                json={"entries": [{"id": existing_id, "text": "Re-synced.", "mood": "centered"}]},
            )
        assert resp.status_code == 200
        args_rows = conn.executemany_calls[0][1]
        assert str(args_rows[0][0]) == existing_id  # id forwarded to DB

    def test_sync_with_last_sync_timestamp(self):
        conn = FakeConn(fetch_results=[[_entry_row()]])
        with (
            patch("app.journal.router.get_tx", make_get_conn(conn)),
            patch("app.journal.router.embed_and_upsert_journal", new=AsyncMock()),
        ):
            resp = TestClient(_make_app()).post(
                "/api/journal/sync",
                json={"entries": [], "last_sync": "2026-08-01T00:00:00Z"},
            )
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 1

    def test_sync_over_200_entries_returns_422(self):
        """Pydantic Field(max_length=200) rejects payloads that exceed the cap."""
        entries = [{"text": f"entry {i}"} for i in range(201)]
        resp = TestClient(_make_app()).post(
            "/api/journal/sync",
            json={"entries": entries},
        )
        assert resp.status_code == 422
