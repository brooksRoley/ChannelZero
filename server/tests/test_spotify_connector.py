"""
Tests for the Spotify connector: _distill_profile (pure function),
_infer_valence_from_genres (pure function), /spotify/profile endpoint,
/spotify/analyze endpoint (mocked LLM), and /spotify/connect 503 guard.

Uses FakeConn from conftest — no real DB or external HTTP calls.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.spotify.router import (
    _distill_profile,
    _infer_valence_from_genres,
    _ingest_spotify_data,
    router as spotify_router,
)

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000003")

SAMPLE_ARTISTS = [
    {"name": "Portishead", "genres": ["trip hop", "downtempo", "neo-soul"], "id": "a1"},
    {"name": "Massive Attack", "genres": ["trip hop", "electronic"], "id": "a2"},
    {"name": "Bjork", "genres": ["art pop", "experimental"], "id": "a3"},
]

SAMPLE_FEATURES = [
    {
        "valence": 0.2, "danceability": 0.4, "energy": 0.5,
        "acousticness": 0.1, "instrumentalness": 0.05, "tempo": 90.0,
    },
    {
        "valence": 0.4, "danceability": 0.6, "energy": 0.6,
        "acousticness": 0.2, "instrumentalness": 0.1, "tempo": 110.0,
    },
]

SAMPLE_TRACKS = [
    {"id": "t1", "popularity": 70, "artists": [{"id": "a1"}, {"id": "e1"}]},
    {"id": "t2", "popularity": 80, "artists": [{"id": "a2"}]},
]

SAMPLE_EXTRA_ARTISTS = [
    {"id": "e1", "genres": ["ambient", "drone"]},
]


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(spotify_router, prefix="/api/spotify")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


# ── _infer_valence_from_genres (pure function) ────────────────────────────────────


class TestInferValenceFromGenres:
    def test_empty_list_returns_neutral_fallback(self):
        assert _infer_valence_from_genres([]) == 0.5

    def test_sad_genre_returns_low_valence(self):
        result = _infer_valence_from_genres(["sad indie", "doom metal"])
        assert result < 0.3

    def test_happy_genre_returns_high_valence(self):
        result = _infer_valence_from_genres(["reggaeton", "latin pop"])
        assert result > 0.7

    def test_electronic_genre_maps_to_expected_value(self):
        result = _infer_valence_from_genres(["electronic"])
        assert result == 0.7

    def test_ambient_genre_maps_to_expected_value(self):
        result = _infer_valence_from_genres(["ambient"])
        assert result == 0.3

    def test_average_taken_across_multiple_matched_genres(self):
        # neo-soul → 0.35, electronic → 0.7 → average 0.525
        result = _infer_valence_from_genres(["neo-soul", "electronic"])
        assert result == round((0.35 + 0.7) / 2, 3)


# ── _distill_profile (pure function) ────────────────────────────────────────────


class TestDistillProfile:
    def test_empty_artists_returns_empty_top_artists_and_genres(self):
        result = _distill_profile([], [], [])
        assert result["top_artists"] == []
        assert result["genres"] == []

    def test_empty_genres_returned_when_artists_have_no_genres(self):
        artists = [{"name": "Unknown", "genres": [], "id": "a1"}]
        result = _distill_profile(artists, [], [])
        assert result["genres"] == []

    def test_top_artists_limited_to_five_and_ordered(self):
        many_artists = [{"name": f"Artist{i}", "genres": [], "id": f"a{i}"} for i in range(10)]
        result = _distill_profile(many_artists, [], [])
        assert len(result["top_artists"]) <= 5
        assert result["top_artists"][0] == "Artist0"

    def test_genres_aggregated_from_top_artists(self):
        result = _distill_profile(SAMPLE_ARTISTS, [], [])
        assert "trip hop" in result["genres"]
        assert "neo-soul" in result["genres"]

    def test_genres_deduplicated_across_artists(self):
        # SAMPLE_ARTISTS[0] and [1] both carry "trip hop"
        result = _distill_profile(SAMPLE_ARTISTS, [], [])
        assert result["genres"].count("trip hop") == 1

    def test_genres_capped_at_eight(self):
        many_genre_artist = [{"name": "A", "genres": [f"genre{i}" for i in range(15)], "id": "a1"}]
        result = _distill_profile(many_genre_artist, [], [])
        assert len(result["genres"]) <= 8

    def test_audio_avg_computed_from_features(self):
        result = _distill_profile(SAMPLE_ARTISTS, SAMPLE_FEATURES, [])
        assert result["audio_avg"]["valence"] == round((0.2 + 0.4) / 2, 3)
        assert result["audio_avg"]["energy"] == round((0.5 + 0.6) / 2, 3)
        assert result["audio_avg"]["tempo"] == round((90.0 + 110.0) / 2, 3)

    def test_fallback_infers_valence_and_energy_when_no_features(self):
        # Empty features list → genre-inferred valence, popularity-based energy
        result = _distill_profile(SAMPLE_ARTISTS, [], SAMPLE_TRACKS)
        avg = result["audio_avg"]
        assert "valence" in avg
        assert "energy" in avg
        # Energy from average popularity: (70 + 80) / 2 / 100 = 0.75
        assert avg["energy"] == 0.75
        assert avg["tempo"] == 120.0

    def test_extra_artists_supplement_genres(self):
        result = _distill_profile(SAMPLE_ARTISTS, [], SAMPLE_TRACKS, SAMPLE_EXTRA_ARTISTS)
        all_genres = result["genres"]
        assert "ambient" in all_genres or "drone" in all_genres

    def test_extra_artist_genres_deduplicated_with_main_genres(self):
        dup_extra = [{"genres": ["trip hop"]}, {"genres": ["electronic"]}]
        result = _distill_profile(SAMPLE_ARTISTS, [], [], dup_extra)
        assert result["genres"].count("trip hop") == 1
        assert result["genres"].count("electronic") == 1


# ── /spotify/profile endpoint ───────────────────────────────────────────────────


class TestSpotifyProfileEndpoint:
    def test_returns_null_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_null_when_spotify_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"spotify_data": None}])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/profile")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_parsed_dict_when_data_is_json_string(self):
        stored = json.dumps({"top_artists": ["Portishead"], "genres": ["trip hop"]})
        conn = FakeConn(fetchrow_results=[{"spotify_data": stored}])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/profile")
        assert resp.status_code == 200
        assert resp.json()["top_artists"] == ["Portishead"]

    def test_returns_dict_passthrough_when_already_dict(self):
        stored = {"top_artists": ["Bjork"], "genres": ["art pop"], "audio_avg": {}}
        conn = FakeConn(fetchrow_results=[{"spotify_data": stored}])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/profile")
        assert resp.status_code == 200
        assert resp.json()["top_artists"] == ["Bjork"]


# ── /spotify/analyze endpoint ──────────────────────────────────────────────────


class TestSpotifyAnalyzeEndpoint:
    def test_404_when_no_vibe_vectors_row(self):
        conn = FakeConn(fetchrow_results=[None])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/analyze")
        assert resp.status_code == 404

    def test_404_when_spotify_data_is_null(self):
        conn = FakeConn(fetchrow_results=[{"spotify_data": None}])
        app = _make_app()
        with patch("app.spotify.router.get_conn", make_get_conn(conn)):
            resp = TestClient(app).get("/api/spotify/analyze")
        assert resp.status_code == 404

    def test_200_with_narrative_when_data_present(self):
        stored = json.dumps({
            "top_artists": ["Portishead"],
            "genres": ["trip hop"],
            "audio_avg": {
                "valence": 0.3, "danceability": 0.5, "energy": 0.5,
                "acousticness": 0.2, "instrumentalness": 0.05, "tempo": 95.0,
            },
        })
        conn = FakeConn(fetchrow_results=[{"spotify_data": stored}])
        app = _make_app()
        with (
            patch("app.spotify.router.get_conn", make_get_conn(conn)),
            patch(
                "app.spotify.router.chat_completion",
                new=AsyncMock(return_value="Your sound is a slow descent into self."),
            ),
        ):
            resp = TestClient(app).get("/api/spotify/analyze")
        assert resp.status_code == 200
        assert resp.json()["narrative"] == "Your sound is a slow descent into self."


# ── /spotify/connect 503 guard ────────────────────────────────────────────────────


class TestSpotifyConnectEndpoint:
    def test_503_when_spotify_client_id_not_configured(self):
        """Missing SPOTIFY_CLIENT_ID → 503 before any token validation or DB call."""
        app = _make_app()
        with patch("app.oauth_base.get_settings") as mock_settings:
            mock_settings.return_value.spotify_client_id = None
            resp = TestClient(app).get("/api/spotify/connect", params={"ct": "dummy-connect-token"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "not_configured"


# ── _ingest_spotify_data helper ───────────────────────────────────────────────


def _mock_resp(status_code: int, data: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = data
    return m


class TestIngestSpotifyData:
    """Tests for the shared fetch-distill-store helper used by /sync and /callback."""

    def test_builds_profile_with_artists_tracks_and_features(self):
        """Happy path: artists + tracks + features all 200 → audio_avg from real data."""
        client = AsyncMock()
        client.get.side_effect = [
            _mock_resp(200, {"items": SAMPLE_ARTISTS}),
            _mock_resp(200, {"items": SAMPLE_TRACKS}),
            _mock_resp(200, {"audio_features": SAMPLE_FEATURES}),
            _mock_resp(200, {"artists": SAMPLE_EXTRA_ARTISTS}),
        ]
        with patch("app.spotify.router.store_provider_data", new=AsyncMock()):
            result = asyncio.run(
                _ingest_spotify_data(client, {"Authorization": "Bearer tok"}, "user-1")
            )
        assert result["top_artists"][0] == "Portishead"
        assert result["audio_avg"]["valence"] == round((0.2 + 0.4) / 2, 3)
        assert result["audio_avg"]["tempo"] == round((90.0 + 110.0) / 2, 3)

    def test_audio_features_403_falls_back_to_genre_inference(self):
        """Spotify returning 403 on /audio-features triggers genre-based valence fallback."""
        client = AsyncMock()
        client.get.side_effect = [
            _mock_resp(200, {"items": SAMPLE_ARTISTS}),
            _mock_resp(200, {"items": SAMPLE_TRACKS}),
            _mock_resp(403, {}),
            _mock_resp(200, {"artists": []}),
        ]
        with patch("app.spotify.router.store_provider_data", new=AsyncMock()):
            result = asyncio.run(
                _ingest_spotify_data(client, {"Authorization": "Bearer tok"}, "user-1")
            )
        assert result["audio_avg"]["tempo"] == 120.0

    def test_empty_tracks_skips_audio_features_request(self):
        """No tracks → no track IDs → /audio-features not called; only 2 HTTP calls made."""
        client = AsyncMock()
        client.get.side_effect = [
            _mock_resp(200, {"items": []}),
            _mock_resp(200, {"items": []}),
        ]
        with patch("app.spotify.router.store_provider_data", new=AsyncMock()):
            result = asyncio.run(
                _ingest_spotify_data(client, {"Authorization": "Bearer tok"}, "user-1")
            )
        assert client.get.call_count == 2
        assert result["top_artists"] == []

    def test_store_provider_data_called_with_correct_user_id(self):
        """The helper must persist the profile under exactly the given user_id."""
        client = AsyncMock()
        client.get.side_effect = [
            _mock_resp(200, {"items": []}),
            _mock_resp(200, {"items": []}),
        ]
        store_mock = AsyncMock()
        with patch("app.spotify.router.store_provider_data", new=store_mock):
            asyncio.run(
                _ingest_spotify_data(client, {"Authorization": "Bearer tok"}, "user-xyz")
            )
        store_mock.assert_called_once_with("user-xyz", "spotify_data", ANY)
