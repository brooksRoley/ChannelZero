"""Movement from Apple Health: the Shortcut's ingest, the app's reads, and the
promise that it never reaches an LLM."""

from __future__ import annotations

import inspect
from datetime import date
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.movement import router as movement
from app.ratelimit import limiter

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
RUN = {"start": "2026-10-30T07:05:00-07:00", "end": "2026-10-30T07:47:00-07:00", "type": "Running"}


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter._storage.reset()
    yield


def _client(conn: FakeConn, monkeypatch) -> TestClient:
    monkeypatch.setattr(movement, "get_conn", make_get_conn(conn))
    app = FastAPI()
    app.include_router(movement.router, prefix="/api/movement")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return TestClient(app)


class TestIngest:
    def test_saves_a_workout_on_the_local_day_it_started(self, monkeypatch):
        conn = FakeConn(fetchval_results=[USER_ID])
        late = {"start": "2026-10-29T23:30:00-07:00", "end": "2026-10-30T00:10:00-07:00", "type": "Walking"}
        r = _client(conn, monkeypatch).post("/api/movement/workouts", json={"workouts": [RUN, late]},
                                            headers={"Authorization": "Bearer tok"})
        assert r.status_code == 200 and r.json() == {"saved": 2, "refused": []}
        rows = conn.executemany_calls[0][1]
        assert [row[3] for row in rows] == [date(2026, 10, 30), date(2026, 10, 29)]
        assert "ON CONFLICT (user_id, started_at)" in conn.executemany_calls[0][0]

    def test_looks_the_token_up_by_hash_never_plain(self, monkeypatch):
        conn = FakeConn(fetchval_results=[USER_ID])
        seen: list = []
        orig = conn.fetchval

        async def spy(q, *a):
            seen.append(a)
            return await orig(q, *a)

        conn.fetchval = spy  # type: ignore[method-assign]
        _client(conn, monkeypatch).post("/api/movement/workouts", json={"workouts": [RUN]},
                                        headers={"Authorization": "Bearer tok"})
        assert seen[0] == (movement._hash("tok"),) and "tok" not in seen[0]

    @pytest.mark.parametrize("headers,code", [({}, "no_token"), ({"Authorization": "Bearer nope"}, "bad_token")])
    def test_refuses_without_a_known_token(self, monkeypatch, headers, code):
        r = _client(FakeConn(), monkeypatch).post("/api/movement/workouts", json={"workouts": [RUN]}, headers=headers)
        assert r.status_code == 401 and r.json()["detail"]["code"] == code

    def test_refuses_impossible_workouts_and_keeps_the_rest(self, monkeypatch):
        conn = FakeConn(fetchval_results=[USER_ID])
        backwards = {**RUN, "end": "2026-10-30T07:00:00-07:00"}
        future = {"start": "2099-01-01T07:00:00Z", "end": "2099-01-01T08:00:00Z", "type": "Running"}
        r = _client(conn, monkeypatch).post("/api/movement/workouts", json={"workouts": [backwards, RUN, future]},
                                            headers={"Authorization": "Bearer tok"})
        assert r.json()["saved"] == 1
        assert [x["index"] for x in r.json()["refused"]] == [0, 2]

    def test_needs_an_offset(self, monkeypatch):
        naive = {**RUN, "start": "2026-10-30T07:05:00"}
        r = _client(FakeConn(fetchval_results=[USER_ID]), monkeypatch).post(
            "/api/movement/workouts", json={"workouts": [naive]}, headers={"Authorization": "Bearer tok"})
        assert r.status_code == 422


class TestApp:
    def test_token_is_returned_once_and_stored_hashed(self, monkeypatch):
        conn = FakeConn()
        tok = _client(conn, monkeypatch).post("/api/movement/token").json()["token"]
        assert len(tok) > 30
        stored = conn.execute_calls[0][1]
        assert stored == (USER_ID, movement._hash(tok))

    def test_days_sum_minutes_per_day(self, monkeypatch):
        conn = FakeConn(fetch_results=[[
            {"day": date(2026, 10, 30), "kind": "Running", "seconds": 2520.0},
            {"day": date(2026, 10, 30), "kind": "Walking", "seconds": 1200.0},
            {"day": date(2026, 10, 28), "kind": "Strength Training", "seconds": 2700.0},
        ]])
        days = _client(conn, monkeypatch).get("/api/movement/days").json()["days"]
        assert days[0] == {"date": "2026-10-30", "minutes": 62,
                           "kinds": [{"kind": "Running", "minutes": 42}, {"kind": "Walking", "minutes": 20}]}
        assert days[1]["minutes"] == 45

    def test_delete_removes_workouts_and_token(self, monkeypatch):
        conn = FakeConn()
        _client(conn, monkeypatch).delete("/api/movement")
        sql = " ".join(q for q, _ in conn.execute_calls)
        assert "movement_workouts" in sql and "movement_tokens" in sql


class TestNeverReachesAnLLM:
    def test_no_ai_path_reads_movement(self):
        from app.connectors import router as connectors
        from app.oracle import service, trigger
        from app.portrait import stitcher

        for mod in (connectors, service, trigger, stitcher):
            assert "movement" not in inspect.getsource(mod), mod.__name__
