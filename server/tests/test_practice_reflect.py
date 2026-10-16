"""Tests for POST /api/practice/reflect (stateless sentiment + mirror)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.practice.router import parse_reply
from app.ratelimit import limiter

BODY = {"method": "zeromind", "moment": "during", "prompt": "What do you notice?", "text": "my shoulders are dropping"}
GOOD = '{"valence": 0.6, "energy": 0.2, "tone": "Settling!", "reflection": "Your shoulders are letting go. Let the next exhale be a little longer."}'


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter._storage.reset()
    yield


def client():
    return TestClient(app, raise_server_exceptions=False)


def test_returns_parsed_reflection_without_auth():
    with patch("app.practice.router.llm_configured", return_value=True), \
         patch("app.practice.router.chat_completion", AsyncMock(return_value=GOOD)):
        resp = client().post("/api/practice/reflect", json=BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tone"] == "settling"
    assert data["source"] == "llm"
    assert 0.5 < data["valence"] <= 1


def test_503_when_llm_unconfigured():
    with patch("app.practice.router.llm_configured", return_value=False):
        resp = client().post("/api/practice/reflect", json=BODY)
    assert resp.status_code == 503


def test_502_on_malformed_reply():
    with patch("app.practice.router.llm_configured", return_value=True), \
         patch("app.practice.router.chat_completion", AsyncMock(return_value="sure! here you go")):
        resp = client().post("/api/practice/reflect", json=BODY)
    assert resp.status_code == 502


def test_rejects_overlong_text():
    resp = client().post("/api/practice/reflect", json={**BODY, "text": "x" * 601})
    assert resp.status_code == 422


def test_rate_limited_after_20():
    with patch("app.practice.router.llm_configured", return_value=False):
        for _ in range(20):
            client().post("/api/practice/reflect", json=BODY)
        resp = client().post("/api/practice/reflect", json=BODY)
    assert resp.status_code == 429


def test_parse_reply_clamps_and_extracts_from_prose():
    r = parse_reply('Here: {"valence": 3, "energy": -1, "tone": "", "reflection": "  You   noticed it. "} thanks')
    assert r.valence == 1 and r.energy == 0
    assert r.tone == "present"
    assert r.reflection == "You noticed it."
