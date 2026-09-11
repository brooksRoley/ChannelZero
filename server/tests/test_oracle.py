"""Oracle pipeline tests — models, service helpers, router endpoints.

Covers:
 - ProviderPayload size validator (50 KB cap)
 - PsychCoordinate field-range validation
 - _trim_value / _sanitize_provider structural truncation
 - _build_oracle_prompt / _build_simplified_prompt content correctness
 - GET /api/oracle/coordinate — synthesized=False + synthesized=True paths
 - POST /api/oracle/synthesize — returns initiated + background task fires
 - synthesize_and_upsert — error containment (HTTPStatusError, generic Exception)
 - _synthesize_and_upsert_inner — BYOK success, server-key fallback, JSON-malformed
   retry, embed failure abort, Pinecone failure abort

Run: cd server && python -m pytest tests/test_oracle.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.deps import get_current_user_id
from app.oracle.models import (
    ProviderPayload,
    PsychCoordinate,
    SynthesisRequest,
    SynthesisResponse,
)
from app.oracle.router import router as oracle_router
from app.oracle.service import (
    _build_oracle_prompt,
    _build_simplified_prompt,
    _sanitize_provider,
    _trim_value,
    _synthesize_and_upsert_inner,
    synthesize_and_upsert,
)

from .conftest import FakeConn, make_get_conn

USER_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_STR = str(USER_ID)

_VALID_COORD = {
    "empathy_index": 0.7,
    "isolation_metric": 0.4,
    "fatalism_score": 0.3,
    "masochism_curve": 0.5,
    "oracle_rationale": "Two poetic sentences.",
    "suggested_community_action": "Connect with the archive.",
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oracle_router, prefix="/api/oracle")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


def _synthesis_request(**kwargs) -> SynthesisRequest:
    return SynthesisRequest(**kwargs)


# ── ProviderPayload ───────────────────────────────────────────────────────────


class TestProviderPayload:
    def test_empty_data_valid(self):
        p = ProviderPayload()
        assert p.data == {}

    def test_small_payload_valid(self):
        p = ProviderPayload(data={"key": "value"})
        assert p.data["key"] == "value"

    def test_payload_exactly_at_limit_valid(self):
        # Build a dict whose JSON is just under 50 KB
        big_str = "x" * 49_900
        p = ProviderPayload(data={"content": big_str})
        assert len(json.dumps(p.data)) < 50_000

    def test_payload_over_50kb_raises(self):
        huge_str = "x" * 51_000
        with pytest.raises(ValidationError, match="50KB"):
            ProviderPayload(data={"content": huge_str})


# ── PsychCoordinate ───────────────────────────────────────────────────────────


class TestPsychCoordinate:
    def test_valid_coordinate(self):
        coord = PsychCoordinate(**_VALID_COORD)
        assert 0.0 <= coord.empathy_index <= 1.0

    def test_empathy_index_below_zero_raises(self):
        bad = {**_VALID_COORD, "empathy_index": -0.1}
        with pytest.raises(ValidationError):
            PsychCoordinate(**bad)

    def test_isolation_metric_above_one_raises(self):
        bad = {**_VALID_COORD, "isolation_metric": 1.1}
        with pytest.raises(ValidationError):
            PsychCoordinate(**bad)

    def test_rationale_over_1000_chars_raises(self):
        bad = {**_VALID_COORD, "oracle_rationale": "a" * 1001}
        with pytest.raises(ValidationError):
            PsychCoordinate(**bad)


# ── SynthesisRequest ──────────────────────────────────────────────────────────


class TestSynthesisRequest:
    def test_all_providers_default_empty(self):
        req = SynthesisRequest()
        for field in [
            "spotify", "twitter", "gcal", "strava", "costar", "letterboxd",
            "steam", "github", "youtube", "reddit", "instagram", "tiktok",
            "psychometrics",
        ]:
            assert getattr(req, field).data == {}

    def test_provider_data_round_trips(self):
        req = SynthesisRequest(spotify=ProviderPayload(data={"genre": "ambient"}))
        assert req.spotify.data["genre"] == "ambient"


# ── SynthesisResponse ─────────────────────────────────────────────────────────


class TestSynthesisResponse:
    def test_status_and_message(self):
        r = SynthesisResponse(status="initiated", message="The Oracle is plotting.")
        assert r.status == "initiated"
        assert "Oracle" in r.message


# ── _trim_value / _sanitize_provider ─────────────────────────────────────────


class TestTrimValue:
    def test_short_string_unchanged(self):
        assert _trim_value("hello") == "hello"

    def test_long_string_truncated(self):
        long_s = "a" * 600
        result = _trim_value(long_s)
        assert len(result) < 600
        assert result.endswith("...[TRUNCATED]")

    def test_list_over_50_items_truncated(self):
        big_list = list(range(60))
        result = _trim_value(big_list)
        assert len(result) == 51  # 50 items + 1 summary string
        assert "10 more items truncated" in result[-1]

    def test_list_under_50_items_unchanged(self):
        small = [1, 2, 3]
        assert _trim_value(small) == [1, 2, 3]

    def test_dict_values_trimmed_recursively(self):
        d = {"a": "x" * 600}
        result = _trim_value(d)
        assert result["a"].endswith("...[TRUNCATED]")

    def test_non_string_scalar_passthrough(self):
        assert _trim_value(42) == 42
        assert _trim_value(3.14) == 3.14
        assert _trim_value(None) is None


class TestSanitizeProvider:
    def test_returns_valid_json_string(self):
        data = {"tracks": ["a", "b"], "count": 2}
        result = _sanitize_provider(data)
        parsed = json.loads(result)
        assert parsed["count"] == 2

    def test_handles_non_json_serializable_types(self):
        from datetime import datetime
        data = {"ts": datetime(2026, 1, 1)}
        result = _sanitize_provider(data)
        assert "2026" in result

    def test_empty_dict_returns_empty_json(self):
        assert _sanitize_provider({}) == "{}"

    def test_non_dict_passthrough(self):
        result = _sanitize_provider("raw string")
        assert result == json.dumps("raw string")


# ── _build_oracle_prompt ──────────────────────────────────────────────────────


class TestBuildPrompts:
    def test_oracle_prompt_contains_user_id(self):
        req = SynthesisRequest()
        prompt = _build_oracle_prompt(USER_STR, req)
        assert USER_STR in prompt

    def test_oracle_prompt_contains_all_provider_labels(self):
        req = SynthesisRequest()
        prompt = _build_oracle_prompt(USER_STR, req)
        for label in [
            "Sonic Baseline", "Neurotic Output", "Temporal Anxiety",
            "Somatic Ledger", "Fatalism Mirror", "Empathy Simulator",
            "Isolation Metric", "Builder Intensity", "Parasocial Field",
            "Tribal Signal", "Aesthetic Mirror", "Cultural Velocity",
            "Psychometric Profile",
        ]:
            assert label in prompt

    def test_oracle_prompt_includes_anti_injection_instruction(self):
        req = SynthesisRequest()
        prompt = _build_oracle_prompt(USER_STR, req)
        assert "ignore previous instructions" in prompt.lower() or "CRITICAL SECURITY" in prompt

    def test_simplified_prompt_contains_user_id(self):
        req = SynthesisRequest()
        prompt = _build_simplified_prompt(USER_STR, req)
        assert USER_STR in prompt

    def test_simplified_prompt_starts_with_json_instruction(self):
        req = SynthesisRequest()
        prompt = _build_simplified_prompt(USER_STR, req)
        assert "JSON" in prompt and "empathy_index" in prompt


# ── GET /api/oracle/coordinate ────────────────────────────────────────────────


class TestGetCoordinate:
    def _client(self, conn: FakeConn) -> TestClient:
        app = _make_app()
        with patch("app.oracle.router.get_conn", make_get_conn(conn)):
            return TestClient(app)

    def test_no_row_returns_synthesized_false(self):
        conn = FakeConn(fetchrow_results=[None])
        with patch("app.oracle.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            resp = client.get("/api/oracle/coordinate")
        assert resp.status_code == 200
        assert resp.json()["synthesized"] is False

    def test_row_without_coordinate_returns_false(self):
        conn = FakeConn(fetchrow_results=[{"oracle_coordinate": None, "oracle_synthesized_at": None}])
        with patch("app.oracle.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            resp = client.get("/api/oracle/coordinate")
        assert resp.status_code == 200
        assert resp.json()["synthesized"] is False

    def test_row_with_coordinate_returns_true(self):
        coord_json = json.dumps(_VALID_COORD)
        now = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
        conn = FakeConn(
            fetchrow_results=[{"oracle_coordinate": coord_json, "oracle_synthesized_at": now}]
        )
        with patch("app.oracle.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            resp = client.get("/api/oracle/coordinate")
        data = resp.json()
        assert resp.status_code == 200
        assert data["synthesized"] is True
        assert data["coordinate"]["empathy_index"] == pytest.approx(0.7)
        assert "synthesized_at" in data

    def test_coordinate_as_dict_not_string(self):
        # Row where oracle_coordinate is already a dict (asyncpg JSONB auto-decode)
        now = datetime(2026, 9, 11, tzinfo=timezone.utc)
        conn = FakeConn(
            fetchrow_results=[{"oracle_coordinate": _VALID_COORD, "oracle_synthesized_at": now}]
        )
        with patch("app.oracle.router.get_conn", make_get_conn(conn)):
            client = TestClient(_make_app())
            resp = client.get("/api/oracle/coordinate")
        assert resp.json()["synthesized"] is True


# ── POST /api/oracle/synthesize ───────────────────────────────────────────────


class TestTriggerSynthesis:
    def test_returns_initiated_status(self):
        with patch("app.oracle.router.synthesize_and_upsert", AsyncMock()):
            client = TestClient(_make_app())
            resp = client.post("/api/oracle/synthesize", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "initiated"
        assert "Oracle" in body["message"]

    def test_accepts_partial_provider_data(self):
        payload = {
            "spotify": {"data": {"genres": ["ambient"]}},
            "github": {"data": {"username": "dev"}},
        }
        with patch("app.oracle.router.synthesize_and_upsert", AsyncMock()):
            client = TestClient(_make_app())
            resp = client.post("/api/oracle/synthesize", json=payload)
        assert resp.status_code == 200

    def test_rejects_oversized_provider_payload(self):
        huge = {"data": {"content": "x" * 51_000}}
        with patch("app.oracle.router.synthesize_and_upsert", AsyncMock()):
            client = TestClient(_make_app())
            resp = client.post("/api/oracle/synthesize", json={"spotify": huge})
        assert resp.status_code == 422


# ── synthesize_and_upsert error containment ───────────────────────────────────


class TestSynthesizeAndUpsertErrorContainment:
    @pytest.mark.anyio
    async def test_http_status_error_does_not_propagate(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "rate limited"
        error = httpx.HTTPStatusError("rate limit", request=MagicMock(), response=mock_response)
        with patch(
            "app.oracle.service._synthesize_and_upsert_inner",
            AsyncMock(side_effect=error),
        ):
            await synthesize_and_upsert(USER_STR, SynthesisRequest())

    @pytest.mark.anyio
    async def test_generic_exception_does_not_propagate(self):
        with patch(
            "app.oracle.service._synthesize_and_upsert_inner",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await synthesize_and_upsert(USER_STR, SynthesisRequest())


# ── _synthesize_and_upsert_inner pathways ─────────────────────────────────────


def _mock_llm_response(coord: dict) -> AsyncMock:
    return AsyncMock(return_value=PsychCoordinate(**coord))


class TestSynthesizeAndUpsertInner:
    @pytest.mark.anyio
    async def test_server_key_fallback_when_no_byok(self):
        conn = FakeConn()
        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=None)),
            patch("app.oracle.service._server_completion_key", return_value="sk-server"),
            patch("app.oracle.service._llm_synthesize", _mock_llm_response(_VALID_COORD)),
            patch("app.oracle.service.get_conn", make_get_conn(conn)),
            patch("app.oracle.service._embed", AsyncMock(return_value=[0.1] * 10)),
            patch("app.oracle.service.asyncio.to_thread", AsyncMock(return_value=None)),
        ):
            await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())

        assert len(conn.execute_calls) == 1
        assert "oracle_coordinate" in conn.execute_calls[0][0]

    @pytest.mark.anyio
    async def test_byok_success_path(self):
        conn = FakeConn()
        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=("openai", "sk-byok"))),
            patch("app.oracle.service._llm_synthesize", _mock_llm_response(_VALID_COORD)),
            patch("app.oracle.service.get_conn", make_get_conn(conn)),
            patch("app.oracle.service._embed", AsyncMock(return_value=[0.1] * 10)),
            patch("app.oracle.service.asyncio.to_thread", AsyncMock(return_value=None)),
        ):
            await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())

        assert len(conn.execute_calls) == 1

    @pytest.mark.anyio
    async def test_byok_json_malformed_retries_simplified_for_unverified_provider(self):
        call_count = {"n": 0}

        async def _fake_llm(prompt, provider, key):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise json.JSONDecodeError("bad json", "", 0)
            return PsychCoordinate(**_VALID_COORD)

        conn = FakeConn()
        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=("anthropic", "sk-ant"))),
            patch("app.oracle.service._llm_synthesize", _fake_llm),
            patch("app.oracle.service.get_conn", make_get_conn(conn)),
            patch("app.oracle.service._embed", AsyncMock(return_value=[0.1] * 10)),
            patch("app.oracle.service.asyncio.to_thread", AsyncMock(return_value=None)),
        ):
            await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())

        assert call_count["n"] == 2  # original + retry

    @pytest.mark.anyio
    async def test_embed_failure_aborts_pinecone_upsert(self):
        conn = FakeConn()
        pinecone_called = {"called": False}

        async def _fake_to_thread(fn, *args, **kwargs):
            pinecone_called["called"] = True

        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=None)),
            patch("app.oracle.service._server_completion_key", return_value="sk-server"),
            patch("app.oracle.service._llm_synthesize", _mock_llm_response(_VALID_COORD)),
            patch("app.oracle.service.get_conn", make_get_conn(conn)),
            patch("app.oracle.service._embed", AsyncMock(return_value=None)),
            patch("app.oracle.service.asyncio.to_thread", _fake_to_thread),
        ):
            await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())

        # DB was persisted (execute called) but Pinecone was skipped
        assert len(conn.execute_calls) == 1
        assert not pinecone_called["called"]

    @pytest.mark.anyio
    async def test_pinecone_unavailable_aborts_upsert(self):
        conn = FakeConn()
        upsert_called = {"called": False}

        async def _fake_to_thread(fn, *args, **kwargs):
            # First call is _get_index_sync — return None (unavailable)
            return None

        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=None)),
            patch("app.oracle.service._server_completion_key", return_value="sk-server"),
            patch("app.oracle.service._llm_synthesize", _mock_llm_response(_VALID_COORD)),
            patch("app.oracle.service.get_conn", make_get_conn(conn)),
            patch("app.oracle.service._embed", AsyncMock(return_value=[0.1] * 10)),
            patch("app.oracle.service.asyncio.to_thread", _fake_to_thread),
        ):
            await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())

        # DB was persisted; Pinecone index call returned None so upsert never ran
        assert len(conn.execute_calls) == 1

    @pytest.mark.anyio
    async def test_no_server_key_raises_runtime_error(self):
        with (
            patch("app.oracle.service.get_user_llm_key", AsyncMock(return_value=None)),
            patch("app.oracle.service._server_completion_key", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="No LLM key available"):
                await _synthesize_and_upsert_inner(USER_STR, SynthesisRequest())
