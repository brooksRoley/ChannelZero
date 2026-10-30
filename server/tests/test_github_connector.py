"""
Tests for the GitHub connector: _distill_profile (pure function),
/github/profile endpoint, /github/analyze endpoint (mocked LLM),
and /github/connect 503 guard.

Uses FakeConn from conftest — no real DB or external HTTP calls.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.github.router import _distill_profile, router as github_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000002")

SAMPLE_USER = {
    "login": "codemancer",
    "bio": "I speak in functions",
    "company": "Aether Labs",
    "location": "Los Angeles",
    "public_repos": 42,
    "followers": 150,
    "following": 88,
    "created_at": "2018-03-15T00:00:00Z",
    "id": 9999,
}

SAMPLE_REPOS = [
    {"language": "Python", "fork": False, "topics": ["ml", "audio"], "description": "A synthesizer in code"},
    {"language": "TypeScript", "fork": False, "topics": ["web"], "description": "Portal to nowhere"},
    {"language": "Python", "fork": True, "topics": [], "description": None},
    {"language": None, "fork": False, "topics": ["audio"], "description": "Ambient generator"},
]

SAMPLE_STARRED = [{"id": 1}, {"id": 2}, {"id": 3}]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(github_router, prefix="/api/github")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _distill_profile (pure function) ─────────────────────────────────────────


class TestDistillProfile:
    def test_empty_inputs_return_defaults(self):
        result = _distill_profile({}, [], [])
        assert result["username"] == ""
        assert result["top_languages"] == []
        assert result["stars_given"] == 0
        assert result["repos_owned"] == 0
        assert result["repos_forked"] == 0
        assert result["owned_to_forked_ratio"] == 0.0
        assert result["account_age_years"] is None

    def test_language_aggregation_orders_by_count(self):
        repos = [
            {"language": "Python", "fork": False, "topics": [], "description": None},
            {"language": "Python", "fork": False, "topics": [], "description": None},
            {"language": "TypeScript", "fork": False, "topics": [], "description": None},
        ]
        result = _distill_profile({}, repos, [])
        assert result["top_languages"][0] == "Python"
        assert "TypeScript" in result["top_languages"]

    def test_fork_count_separated_from_owned(self):
        result = _distill_profile(SAMPLE_USER, SAMPLE_REPOS, SAMPLE_STARRED)
        assert result["repos_forked"] == 1
        assert result["repos_owned"] == 3

    def test_owned_to_forked_ratio_calculation(self):
        result = _distill_profile(SAMPLE_USER, SAMPLE_REPOS, SAMPLE_STARRED)
        assert result["owned_to_forked_ratio"] == round(3 / 1, 2)

    def test_stars_given_from_starred_list(self):
        result = _distill_profile(SAMPLE_USER, SAMPLE_REPOS, SAMPLE_STARRED)
        assert result["stars_given"] == 3

    def test_topics_deduplicated(self):
        repos = [
            {"language": None, "fork": False, "topics": ["audio", "audio", "synth"], "description": None},
        ]
        result = _distill_profile({}, repos, [])
        assert len([t for t in result["topics"] if t == "audio"]) == 1

    def test_account_age_computed_from_created_at(self):
        result = _distill_profile(SAMPLE_USER, [], [])
        assert result["account_age_years"] is not None
        assert result["account_age_years"] > 7

    def test_invalid_created_at_returns_none(self):
        user = {**SAMPLE_USER, "created_at": "not-a-date"}
        result = _distill_profile(user, [], [])
        assert result["account_age_years"] is None

    def test_descriptions_exclude_none(self):
        result = _distill_profile(SAMPLE_USER, SAMPLE_REPOS, [])
        assert None not in result["repo_descriptions"]
        assert "A synthesizer in code" in result["repo_descriptions"]


# ── /github/profile endpoint ──────────────────────────────────────────────────


class TestGithubProfileEndpoint:
    def test_returns_null_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_github_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"github_data": None}])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_parsed_dict_when_data_is_json_string(self):
        stored = json.dumps({"username": "codemancer", "public_repos": 42})
        conn = FakeConn(fetchrow_results=[{"github_data": stored}])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "codemancer"
        assert body["public_repos"] == 42

    def test_returns_dict_passthrough_when_already_dict(self):
        stored = {"username": "codemancer", "stars_given": 50}
        conn = FakeConn(fetchrow_results=[{"github_data": stored}])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/profile")
        assert resp.status_code == 200
        assert resp.json()["stars_given"] == 50


# ── /github/analyze endpoint ──────────────────────────────────────────────────


class TestGithubAnalyzeEndpoint:
    def test_404_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/analyze")
        assert resp.status_code == 404

    def test_404_when_github_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"github_data": None}])
        app = _make_app()
        with patch("app.github.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/github/analyze")
        assert resp.status_code == 404

    def test_200_with_narrative_when_data_present(self):
        stored = json.dumps({"username": "codemancer", "top_languages": ["Python"]})
        conn = FakeConn(fetchrow_results=[{"github_data": stored}])
        app = _make_app()
        with (
            patch("app.github.router.get_conn", make_get_conn(conn)),
            patch("app.github.router.chat_completion", new=AsyncMock(return_value="You build in silence.")),
        ):
            resp = TestClient(app).get("/api/github/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "You build in silence."


# ── /github/connect 503 guard ─────────────────────────────────────────────────


class TestGithubConnectEndpoint:
    def test_503_when_github_client_id_not_configured(self):
        """Missing GITHUB_CLIENT_ID → 503 before any token validation or DB call."""
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            mock_settings.return_value.github_client_id = None
            resp = TestClient(app).get("/api/github/connect", params={"token": "dummy"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "not_configured"
