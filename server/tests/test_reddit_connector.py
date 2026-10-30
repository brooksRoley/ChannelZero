"""
Tests for the Reddit connector: _distill_profile (pure function),
/reddit/profile endpoint, /reddit/analyze endpoint (mocked LLM),
and /reddit/connect 503 guard.

Uses FakeConn from conftest — no real DB or external HTTP calls.

Run:  cd server && python -m pytest tests/test_reddit_connector.py -v
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.reddit.router import _distill_profile, router as reddit_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000003")

# created ~= 500 days ago
_CREATED_UTC = time.time() - 500 * 86400

SAMPLE_ME = {
    "name": "night_owl_dev",
    "link_karma": 1200,
    "comment_karma": 3800,
    "created_utc": _CREATED_UTC,
}

SAMPLE_SUBREDDITS = [
    {"data": {"display_name": "programming", "subscribers": 4_000_000}},
    {"data": {"display_name": "Meditation", "subscribers": 900_000}},
    {"data": {"display_name": "obscurehobby", "subscribers": 1_200}},
]

# two comments in Meditation, one in programming; hours derived from created_utc
SAMPLE_COMMENTS = [
    {"data": {"subreddit": "Meditation", "created_utc": 3 * 3600}},      # hour 3
    {"data": {"subreddit": "Meditation", "created_utc": 3 * 3600 + 60}}, # hour 3
    {"data": {"subreddit": "programming", "created_utc": 14 * 3600}},    # hour 14
    {"data": {"subreddit": "", "created_utc": 0}},                       # ignored
]

SAMPLE_SAVED = [{"data": {"id": "a"}}, {"data": {"id": "b"}}]

SAMPLE_TROPHIES = [
    {"data": {"name": "Verified Email"}},
    {"data": {"name": "Five-Year Club"}},
    {"data": {}},  # no name — excluded
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(reddit_router, prefix="/api/reddit")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _distill_profile (pure function) ─────────────────────────────────────────


class TestDistillProfile:
    def test_empty_inputs_return_defaults(self):
        result = _distill_profile({}, [], [], [], [])
        assert result["username"] == ""
        assert result["total_karma"] == 0
        assert result["link_karma"] == 0
        assert result["comment_karma"] == 0
        assert result["comment_karma_ratio"] is None
        assert result["account_age_days"] == 0
        assert result["top_subreddits"] == []
        assert result["comment_subreddits"] == []
        assert result["active_hours"] == {}
        assert result["subreddit_diversity"] == 0
        assert result["trophy_count"] == 0
        assert result["trophies"] == []
        assert result["recent_comments_analyzed"] == 0
        assert result["saved_posts_analyzed"] == 0

    def test_total_karma_is_sum_of_link_and_comment(self):
        result = _distill_profile(SAMPLE_ME, [], [], [], [])
        assert result["link_karma"] == 1200
        assert result["comment_karma"] == 3800
        assert result["total_karma"] == 5000

    def test_karma_ratio_is_comment_over_total(self):
        result = _distill_profile(SAMPLE_ME, [], [], [], [])
        assert result["comment_karma_ratio"] == round(3800 / 5000, 3)

    def test_account_age_days_from_created_utc(self):
        result = _distill_profile(SAMPLE_ME, [], [], [], [])
        # ~500 days ago, allow a small window
        assert 498 <= result["account_age_days"] <= 501

    def test_top_subreddits_sorted_by_subscribers_desc(self):
        result = _distill_profile(SAMPLE_ME, SAMPLE_SUBREDDITS, [], [], [])
        names = [s["name"] for s in result["top_subreddits"]]
        assert names == ["programming", "Meditation", "obscurehobby"]
        assert result["top_subreddits"][0]["subscribers"] == 4_000_000

    def test_comment_subreddits_counted_and_ranked(self):
        result = _distill_profile(SAMPLE_ME, [], SAMPLE_COMMENTS, [], [])
        cs = result["comment_subreddits"]
        assert cs[0] == {"name": "Meditation", "count": 2}
        assert {"name": "programming", "count": 1} in cs
        # empty-subreddit comment is not counted
        assert all(entry["name"] != "" for entry in cs)

    def test_active_hours_bucketed_by_utc_hour(self):
        result = _distill_profile(SAMPLE_ME, [], SAMPLE_COMMENTS, [], [])
        # JSON-round-trip note: keys stay ints in-process
        assert result["active_hours"][3] == 2
        assert result["active_hours"][14] == 1

    def test_subreddit_diversity_unions_subs_and_comment_subs(self):
        # subscribed: programming, Meditation, obscurehobby
        # comment subs: Meditation, programming → union has obscurehobby extra = 3 unique
        result = _distill_profile(SAMPLE_ME, SAMPLE_SUBREDDITS, SAMPLE_COMMENTS, [], [])
        assert result["subreddit_diversity"] == 3

    def test_trophies_extracted_and_named_only(self):
        result = _distill_profile(SAMPLE_ME, [], [], [], SAMPLE_TROPHIES)
        assert result["trophy_count"] == 3
        assert result["trophies"] == ["Verified Email", "Five-Year Club"]

    def test_counts_of_comments_and_saved(self):
        result = _distill_profile(
            SAMPLE_ME, SAMPLE_SUBREDDITS, SAMPLE_COMMENTS, SAMPLE_SAVED, SAMPLE_TROPHIES
        )
        assert result["recent_comments_analyzed"] == len(SAMPLE_COMMENTS)
        assert result["saved_posts_analyzed"] == len(SAMPLE_SAVED)

    def test_top_subreddits_capped_at_30(self):
        subs = [
            {"data": {"display_name": f"sub{i}", "subscribers": i}}
            for i in range(50)
        ]
        result = _distill_profile(SAMPLE_ME, subs, [], [], [])
        assert len(result["top_subreddits"]) == 30
        # highest subscriber count first
        assert result["top_subreddits"][0]["name"] == "sub49"


# ── /reddit/profile endpoint ─────────────────────────────────────────────────


class TestRedditProfileEndpoint:
    def test_returns_null_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_reddit_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"reddit_data": None}])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_parsed_dict_when_data_is_json_string(self):
        stored = json.dumps({"username": "night_owl_dev", "total_karma": 5000})
        conn = FakeConn(fetchrow_results=[{"reddit_data": stored}])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "night_owl_dev"
        assert body["total_karma"] == 5000

    def test_returns_dict_passthrough_when_already_dict(self):
        stored = {"username": "night_owl_dev", "comment_karma": 3800}
        conn = FakeConn(fetchrow_results=[{"reddit_data": stored}])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/profile")
        assert resp.status_code == 200
        assert resp.json()["comment_karma"] == 3800


# ── /reddit/analyze endpoint ─────────────────────────────────────────────────


class TestRedditAnalyzeEndpoint:
    def test_404_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/analyze")
        assert resp.status_code == 404

    def test_404_when_reddit_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"reddit_data": None}])
        app = _make_app()
        with patch("app.reddit.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/reddit/analyze")
        assert resp.status_code == 404

    def test_200_with_narrative_when_data_json_string(self):
        stored = json.dumps({
            "username": "night_owl_dev",
            "total_karma": 5000,
            "link_karma": 1200,
            "comment_karma": 3800,
            "comment_karma_ratio": 0.76,
            "account_age_days": 500,
            "top_subreddits": [{"name": "Meditation", "subscribers": 900000}],
            "comment_subreddits": [{"name": "Meditation", "count": 2}],
            "active_hours": {"3": 2, "14": 1},
            "subreddit_diversity": 3,
            "trophies": ["Five-Year Club"],
        })
        conn = FakeConn(fetchrow_results=[{"reddit_data": stored}])
        app = _make_app()
        with (
            patch("app.reddit.router.get_conn", make_get_conn(conn)),
            patch(
                "app.reddit.router.chat_completion",
                new=AsyncMock(return_value="You lurk in the quiet hours."),
            ),
        ):
            resp = TestClient(app).get("/api/reddit/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "You lurk in the quiet hours."

    def test_200_with_narrative_when_data_already_dict(self):
        stored = {"username": "night_owl_dev", "top_subreddits": [], "active_hours": {}}
        conn = FakeConn(fetchrow_results=[{"reddit_data": stored}])
        app = _make_app()
        mock_llm = AsyncMock(return_value="A profile in negative space.")
        with (
            patch("app.reddit.router.get_conn", make_get_conn(conn)),
            patch("app.reddit.router.chat_completion", new=mock_llm),
        ):
            resp = TestClient(app).get("/api/reddit/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "A profile in negative space."
        # LLM was actually invoked with the built prompt
        assert mock_llm.await_count == 1
        prompt = mock_llm.await_args.args[0]
        assert "night_owl_dev" in prompt


# ── /reddit/connect 503 guard ────────────────────────────────────────────────


class TestRedditConnectEndpoint:
    def test_503_when_reddit_client_id_not_configured(self):
        """Missing reddit_client_id → 503 before any token/DB work."""
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            mock_settings.return_value.reddit_client_id = None
            resp = TestClient(app).get("/api/reddit/connect")
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "not_configured"

    def test_returns_auth_url_when_configured(self):
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            s = mock_settings.return_value
            s.reddit_client_id = "abc123"
            s.reddit_redirect_uri = "https://channelzero.example/reddit/callback"
            s.jwt_secret = "test-secret"
            resp = TestClient(app).get("/api/reddit/connect")
        assert resp.status_code == 200
        auth_url = resp.json()["auth_url"]
        assert auth_url.startswith("https://www.reddit.com/api/v1/authorize?")
        assert "client_id=abc123" in auth_url
        assert "duration=permanent" in auth_url
