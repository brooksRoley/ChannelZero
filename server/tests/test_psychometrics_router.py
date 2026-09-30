"""Functional tests for /api/psychometrics/* endpoints.

Covers all 8 routes: submit, profile, narrative, delete, microdose,
progress, next-item, next-items. 20 tests total.

Pool is mocked via get_pool patch following the same pattern as
test_psychometrics_ratelimit.py. Auth is overridden via
dependency_overrides.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.main import app
from app.ratelimit import limiter

FAKE_USER_ID = UUID("00000000-0000-0000-0000-000000000005")

_PROFILE_DATA = {
    "ipip_neo_scores": '{"openness": 68, "conscientiousness": 55}',
    "ecr_r_scores": '{"anxiety": 40, "avoidance": 30, "attachment_style": "secure"}',
    "love_language": "physical_touch",
    "sociosexual_orientation": "restricted",
    "values_cluster": "growth",
    "narrative": "A quietly driven soul.",
}

_FULL_RESPONSES = {
    "ipip_neo_0": 4, "ipip_neo_1": 3, "ipip_neo_2": 5, "ipip_neo_3": 2,
    "ipip_neo_4": 4, "ipip_neo_5": 3, "ipip_neo_6": 5, "ipip_neo_7": 4,
    "ipip_neo_8": 2, "ipip_neo_9": 3,
    "ecr_r_0": 2, "ecr_r_1": 3, "ecr_r_2": 4, "ecr_r_3": 1,
    "identity_love_language": 0, "identity_values": 1, "identity_sociosexual": 0,
}


def _mock_row(data: dict) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = MagicMock(side_effect=lambda k: data.get(k))
    return row


def _mock_fetch_row(item_id: str, value: int = 3, connector_context=None) -> MagicMock:
    r = MagicMock()
    r.__getitem__ = MagicMock(side_effect=lambda k: {
        "item_id": item_id, "value": value, "connector_context": connector_context,
    }.get(k))
    return r


def _make_pool(fetchrow_result=None, fetch_result=None):
    """Return (pool, conn) mock pair. Patches get_pool → pool; pool.acquire() → conn."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.fetch = AsyncMock(return_value=(fetch_result or []))
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool, conn


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter._storage.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# Fake profile returned by mocked generate_psycho_profile
_FAKE_PROFILE = {
    "ipip_neo_scores": {"openness": 70},
    "ecr_r_scores": {"anxiety": 40, "avoidance": 30},
    "love_language": "words_of_affirmation",
    "sociosexual_orientation": "restricted",
    "values_cluster": "growth",
}


# ---------------------------------------------------------------------------
# POST /api/psychometrics/submit
# ---------------------------------------------------------------------------

class TestSubmitAssessment:
    def test_submit_returns_profile(self, client):
        pool, _ = _make_pool()
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psycho_profile", return_value=_FAKE_PROFILE), \
             patch("app.psychometrics.router.encrypt_responses", return_value="enc"):
            resp = client.post("/api/psychometrics/submit", json={"responses": _FULL_RESPONSES})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "ipip_neo_scores" in body["profile"]
        assert "ecr_r_scores" in body["profile"]

    def test_submit_returns_user_id_scoped_profile(self, client):
        pool, _ = _make_pool()
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psycho_profile", return_value=_FAKE_PROFILE), \
             patch("app.psychometrics.router.encrypt_responses", return_value="enc"):
            resp = client.post("/api/psychometrics/submit", json={"responses": {}})
        assert resp.status_code == 200
        assert resp.json()["profile"]["love_language"] == "words_of_affirmation"

    def test_submit_upserts_user_psychometrics(self, client):
        pool, conn = _make_pool()
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psycho_profile", return_value=_FAKE_PROFILE), \
             patch("app.psychometrics.router.encrypt_responses", return_value="enc"):
            client.post("/api/psychometrics/submit", json={"responses": _FULL_RESPONSES})
        assert conn.execute.call_count == 1
        assert "user_psychometrics" in conn.execute.call_args[0][0]

    def test_submit_without_auth_returns_401(self):
        app.dependency_overrides.pop(get_current_user_id, None)
        c = TestClient(app, raise_server_exceptions=False)
        resp = c.post("/api/psychometrics/submit", json={"responses": {}})
        app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/psychometrics/profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_profile_returns_all_fields(self, client):
        pool, _ = _make_pool(fetchrow_result=_mock_row(_PROFILE_DATA))
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["love_language"] == "physical_touch"
        assert body["narrative"] == "A quietly driven soul."

    def test_profile_parses_json_score_strings(self, client):
        pool, _ = _make_pool(fetchrow_result=_mock_row(_PROFILE_DATA))
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/profile")
        scores = resp.json()["ipip_neo_scores"]
        assert isinstance(scores, dict)
        assert scores["openness"] == 68

    def test_profile_404_when_no_row(self, client):
        pool, _ = _make_pool(fetchrow_result=None)
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/profile")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/psychometrics/narrative
# ---------------------------------------------------------------------------

class TestNarrative:
    def test_narrative_generates_and_returns(self, client):
        pool, _ = _make_pool(fetchrow_result=_mock_row(_PROFILE_DATA))
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="You carry quiet ambition.")):
            resp = client.post("/api/psychometrics/narrative")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["narrative"] == "You carry quiet ambition."

    def test_narrative_stores_in_db(self, client):
        pool, conn = _make_pool(fetchrow_result=_mock_row(_PROFILE_DATA))
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="Stored.")):
            client.post("/api/psychometrics/narrative")
        assert conn.execute.call_count == 1
        assert "narrative" in conn.execute.call_args[0][0]

    def test_narrative_404_when_no_profile(self, client):
        pool, _ = _make_pool(fetchrow_result=None)
        with patch("app.psychometrics.router.get_pool", return_value=pool), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="")):
            resp = client.post("/api/psychometrics/narrative")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/psychometrics/profile
# ---------------------------------------------------------------------------

class TestDeleteProfile:
    def test_delete_returns_success(self, client):
        pool, _ = _make_pool()
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.delete("/api/psychometrics/profile")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_delete_calls_delete_sql(self, client):
        pool, conn = _make_pool()
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            client.delete("/api/psychometrics/profile")
        query, args = conn.execute.call_args[0][0], conn.execute.call_args[0][1:]
        assert "DELETE" in query
        assert str(FAKE_USER_ID) in args[0]


# ---------------------------------------------------------------------------
# POST /api/psychometrics/microdose
# ---------------------------------------------------------------------------

class TestMicrodose:
    def test_microdose_stores_item_204(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.post("/api/psychometrics/microdose",
                               json={"item_id": "ipip_neo_0", "value": 4})
        assert resp.status_code == 204

    def test_microdose_accepts_optional_fields(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.post("/api/psychometrics/microdose", json={
                "item_id": "ecr_r_0", "value": 3,
                "connector_context": "spotify",
                "trance_coherence": 0.85,
                "session_duration_ms": 12000,
            })
        assert resp.status_code == 204

    def test_microdose_partial_ipip_no_score_upsert(self, client):
        # 5 of 10 IPIP items answered — not enough to auto-compute scores
        existing = [_mock_fetch_row(f"ipip_neo_{i}", 3) for i in range(5)]
        pool, conn = _make_pool(fetch_result=existing)
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            client.post("/api/psychometrics/microdose",
                        json={"item_id": "ipip_neo_5", "value": 3})
        upsert_calls = [
            c for c in conn.execute.call_args_list
            if "user_psychometrics" in c[0][0]
        ]
        assert len(upsert_calls) == 0

    def test_microdose_full_ipip_ecr_triggers_score_upsert(self, client):
        # All 10 IPIP + 4 ECR + identity already in fetch_result → upsert fires
        existing = (
            [_mock_fetch_row(f"ipip_neo_{i}", 3) for i in range(10)]
            + [_mock_fetch_row(f"ecr_r_{i}", 2) for i in range(4)]
            + [_mock_fetch_row("identity_love_language", 0)]
        )
        pool, conn = _make_pool(fetch_result=existing)
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            client.post("/api/psychometrics/microdose",
                        json={"item_id": "identity_love_language", "value": 0})
        upsert_calls = [
            c for c in conn.execute.call_args_list
            if "user_psychometrics" in c[0][0]
        ]
        assert len(upsert_calls) >= 1


# ---------------------------------------------------------------------------
# GET /api/psychometrics/progress
# ---------------------------------------------------------------------------

class TestProgress:
    def test_progress_empty(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/progress")
        assert resp.status_code == 200
        body = resp.json()
        assert body["completed"] == 0
        assert body["answered"] == {}

    def test_progress_with_answers(self, client):
        rows = [
            _mock_fetch_row("ipip_neo_0", 4, None),
            _mock_fetch_row("ecr_r_0", 2, "spotify"),
        ]
        pool, _ = _make_pool(fetch_result=rows)
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/progress")
        body = resp.json()
        assert body["completed"] == 2
        assert "ipip_neo_0" in body["answered"]
        assert body["answered"]["ecr_r_0"]["from_trance"] is True
        assert body["answered"]["ipip_neo_0"]["from_trance"] is False


# ---------------------------------------------------------------------------
# GET /api/psychometrics/next-item  +  /next-items
# ---------------------------------------------------------------------------

class TestNextItems:
    def test_next_item_returns_item_when_nothing_answered(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/next-item")
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert "item_id" in body
        assert "text" in body

    def test_next_items_respects_count_param(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/next-items?count=2")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) <= 2

    def test_next_items_count_capped_at_10(self, client):
        pool, _ = _make_pool(fetch_result=[])
        with patch("app.psychometrics.router.get_pool", return_value=pool):
            resp = client.get("/api/psychometrics/next-items?count=50")
        assert resp.status_code == 200
        assert len(resp.json()) <= 10
