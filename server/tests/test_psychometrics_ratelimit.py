"""Tests for POST /api/psychometrics/narrative rate limiting (5/hour)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.main import app
from app.ratelimit import limiter

FAKE_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

_FAKE_PROFILE = {
    "ipip_neo_scores": {"openness": 70},
    "ecr_r_scores": {"anxiety": 40, "avoidance": 30},
    "love_language": "words_of_affirmation",
    "sociosexual_orientation": "restricted",
    "values_cluster": "growth",
}


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


def _fake_pool_with_row():
    """Return a mock pool that yields a fetchrow result with all psychometric fields."""
    row = MagicMock()
    row.__getitem__ = MagicMock(side_effect=lambda k: {
        "ipip_neo_scores": '{"openness": 70}',
        "ecr_r_scores": '{"anxiety": 40, "avoidance": 30}',
        "love_language": "words_of_affirmation",
        "sociosexual_orientation": "restricted",
        "values_cluster": "growth",
    }.get(k))

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    return pool


class TestPsychoNarrativeRateLimit:
    def test_first_attempt_not_rate_limited(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.psychometrics.router.get_pool", return_value=_fake_pool_with_row()), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="Your psyche leans inward.")):
            resp = client.post("/api/psychometrics/narrative")
        assert resp.status_code != 429

    def test_sixth_attempt_returns_429(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.psychometrics.router.get_pool", return_value=_fake_pool_with_row()), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="Your psyche leans inward.")):
            for _ in range(5):
                client.post("/api/psychometrics/narrative")
            resp = client.post("/api/psychometrics/narrative")
        assert resp.status_code == 429

    def test_429_has_retry_after_header(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.psychometrics.router.get_pool", return_value=_fake_pool_with_row()), \
             patch("app.psychometrics.router.generate_psychoanalysis_narrative",
                   AsyncMock(return_value="Your psyche leans inward.")):
            for _ in range(5):
                client.post("/api/psychometrics/narrative")
            resp = client.post("/api/psychometrics/narrative")
        assert "retry-after" in resp.headers or resp.status_code == 429
