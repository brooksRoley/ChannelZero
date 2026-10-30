"""
Tests for the Twitter/X connector: _distill_profile + _pkce_challenge (pure functions),
/twitter/profile endpoint, /twitter/analyze endpoint (mocked LLM),
and /twitter/connect 503 guard.

Uses FakeConn from conftest — no real DB, no real HTTP calls.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.oauth_base import pkce_challenge as _pkce_challenge
from app.twitter.router import _distill_profile, router as twitter_router

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000005")

SAMPLE_ME = {
    "username": "signal_ghost",
    "description": "Systems thinker. Building things that matter.",
    "created_at": "2015-06-20T12:00:00Z",
    "public_metrics": {
        "followers_count": 1200,
        "following_count": 340,
        "tweet_count": 4500,
        "listed_count": 18,
    },
}

SAMPLE_TWEETS = [
    {
        "text": "Rethinking how attention shapes identity.",
        "created_at": "2026-07-10T14:22:00Z",
        "lang": "en",
        "public_metrics": {"like_count": 42, "retweet_count": 8},
    },
    {
        "text": "The loop always returns to the origin https://t.co/abc123",
        "created_at": "2026-07-08T09:05:00Z",
        "lang": "en",
        "public_metrics": {"like_count": 15, "retweet_count": 2},
    },
    {
        "text": "Short enough to tweet but not enough to resolve.",
        "created_at": "2026-07-07T23:00:00Z",
        "lang": "en",
        "public_metrics": {"like_count": 66, "retweet_count": 12},
    },
]

SAMPLE_LIKES = [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}]

SAMPLE_FOLLOWING = [
    {"public_metrics": {"followers_count": 250_000}, "description": "Big account"},
    {"public_metrics": {"followers_count": 800}, "description": "Small account"},
    {"public_metrics": {"followers_count": 50_000}, "description": "Mid account"},
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(twitter_router, prefix="/api/twitter")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _pkce_challenge (pure function) ────────────────────────────────────────────


class TestPkceChallenge:
    def test_produces_base64url_sha256_of_verifier(self):
        verifier = "test_verifier_string_43chars_exactly_here!"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert _pkce_challenge(verifier) == expected

    def test_consistent_for_same_verifier(self):
        verifier = "stable_verifier_for_consistency_check"
        assert _pkce_challenge(verifier) == _pkce_challenge(verifier)

    def test_different_verifiers_produce_different_challenges(self):
        assert _pkce_challenge("verifier_alpha") != _pkce_challenge("verifier_beta")

    def test_no_padding_characters_in_output(self):
        challenge = _pkce_challenge("any_test_verifier_no_padding_check")
        assert "=" not in challenge


# ── _distill_profile (pure function) ──────────────────────────────────────────


class TestDistillProfile:
    def test_empty_inputs_return_safe_defaults(self):
        result = _distill_profile({}, [], [], [])
        assert result["username"] == ""
        assert result["followers"] == 0
        assert result["following_count"] == 0
        assert result["avg_tweet_length"] == 0
        assert result["recent_likes_given"] == 0
        assert result["tweet_samples"] == []
        assert result["high_profile_follows"] == 0

    def test_followers_and_metrics_extracted_from_public_metrics(self):
        result = _distill_profile(SAMPLE_ME, [], [], [])
        assert result["followers"] == 1200
        assert result["following_count"] == 340
        assert result["tweet_count"] == 4500
        assert result["listed_count"] == 18

    def test_avg_tweet_length_computed_from_raw_text(self):
        tweets = [
            {"text": "abcde", "created_at": "", "lang": "en", "public_metrics": {"like_count": 0, "retweet_count": 0}},
            {"text": "abcdefghij", "created_at": "", "lang": "en", "public_metrics": {"like_count": 0, "retweet_count": 0}},
        ]
        result = _distill_profile({}, tweets, [], [])
        assert result["avg_tweet_length"] == 7.5

    def test_urls_stripped_from_tweet_samples(self):
        result = _distill_profile(SAMPLE_ME, SAMPLE_TWEETS, [], [])
        for sample in result["tweet_samples"]:
            assert "https://" not in sample

    def test_recent_likes_given_is_length_of_likes_list(self):
        result = _distill_profile(SAMPLE_ME, SAMPLE_TWEETS, SAMPLE_LIKES, [])
        assert result["recent_likes_given"] == 4

    def test_high_profile_follows_threshold_is_100k(self):
        result = _distill_profile(SAMPLE_ME, [], [], SAMPLE_FOLLOWING)
        assert result["high_profile_follows"] == 1

    def test_posting_hours_extracted_from_timestamps(self):
        result = _distill_profile(SAMPLE_ME, SAMPLE_TWEETS, [], [])
        hours = result["posting_hours"]
        assert "14" in hours
        assert "9" in hours
        assert "23" in hours

    def test_engagement_avg_likes_and_retweets_computed(self):
        result = _distill_profile(SAMPLE_ME, SAMPLE_TWEETS, [], [])
        expected_likes = round((42 + 15 + 66) / 3, 1)
        assert result["engagement_avg"]["likes"] == expected_likes
        expected_rts = round((8 + 2 + 12) / 3, 1)
        assert result["engagement_avg"]["retweets"] == expected_rts

    def test_tweet_samples_capped_at_five(self):
        tweets = [
            {
                "text": f"This is a substantial tweet number {i} that exceeds the ten-char minimum",
                "created_at": "",
                "lang": "en",
                "public_metrics": {"like_count": 0, "retweet_count": 0},
            }
            for i in range(10)
        ]
        result = _distill_profile({}, tweets, [], [])
        assert len(result["tweet_samples"]) <= 5

    def test_short_cleaned_tweet_texts_excluded_from_samples(self):
        tweets = [
            {"text": "Hi", "created_at": "", "lang": "en", "public_metrics": {"like_count": 0, "retweet_count": 0}},
            {
                "text": "This tweet is long enough to qualify as a valid sample",
                "created_at": "",
                "lang": "en",
                "public_metrics": {"like_count": 0, "retweet_count": 0},
            },
        ]
        result = _distill_profile({}, tweets, [], [])
        assert len(result["tweet_samples"]) == 1

    def test_language_detected_as_most_common_across_tweets(self):
        tweets = [
            {"text": "uno dos tres", "created_at": "", "lang": "es", "public_metrics": {"like_count": 0, "retweet_count": 0}},
            {"text": "cuatro cinco", "created_at": "", "lang": "es", "public_metrics": {"like_count": 0, "retweet_count": 0}},
            {"text": "one two three", "created_at": "", "lang": "en", "public_metrics": {"like_count": 0, "retweet_count": 0}},
        ]
        result = _distill_profile({}, tweets, [], [])
        assert result["language"] == "es"


# ── /twitter/profile endpoint ────────────────────────────────────────────


class TestTwitterProfileEndpoint:
    def test_returns_null_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_twitter_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"twitter_data": None}])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_parsed_dict_when_data_is_json_string(self):
        stored = json.dumps({"username": "signal_ghost", "followers": 1200})
        conn = FakeConn(fetchrow_results=[{"twitter_data": stored}])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "signal_ghost"
        assert body["followers"] == 1200

    def test_returns_dict_passthrough_when_already_parsed(self):
        stored = {"username": "signal_ghost", "tweet_count": 4500}
        conn = FakeConn(fetchrow_results=[{"twitter_data": stored}])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/profile")
        assert resp.status_code == 200
        assert resp.json()["tweet_count"] == 4500


# ── /twitter/analyze endpoint ───────────────────────────────────────────


class TestTwitterAnalyzeEndpoint:
    def test_404_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/analyze")
        assert resp.status_code == 404

    def test_404_when_twitter_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"twitter_data": None}])
        app = _make_app()
        with patch("app.twitter.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/twitter/analyze")
        assert resp.status_code == 404

    def test_200_with_narrative_when_data_present(self):
        stored = json.dumps({"username": "signal_ghost", "followers": 1200})
        conn = FakeConn(fetchrow_results=[{"twitter_data": stored}])
        app = _make_app()
        with (
            patch("app.twitter.router.get_conn", make_get_conn(conn)),
            patch(
                "app.twitter.router.chat_completion",
                new=AsyncMock(return_value="Your signal echoes inward."),
            ),
        ):
            resp = TestClient(app).get("/api/twitter/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "Your signal echoes inward."


# ── /twitter/connect 503 guard ────────────────────────────────────────────


class TestTwitterConnectEndpoint:
    def test_503_when_x_client_id_not_configured(self):
        """Missing X_CLIENT_ID → 503 before any token validation or DB call."""
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            mock_settings.return_value.x_client_id = None
            resp = TestClient(app).get("/api/twitter/connect")
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "not_configured"
