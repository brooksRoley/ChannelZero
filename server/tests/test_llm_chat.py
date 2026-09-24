"""
Tests for app.llm.chat — provider resolution, failure modes, and live ping.

Run:  cd server && python -m pytest tests/ -v
"""

from __future__ import annotations

from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from fastapi import HTTPException

from app.llm.chat import (
    _resolve_provider,
    llm_configured,
    chat_completion,
    _PROVIDERS,
)


# ── _resolve_provider ────────────────────────────────────────────────


class TestResolveProvider:
    """Unit tests for the provider resolution logic."""

    def _make_settings(self, **overrides):
        defaults = {
            "llm_provider": "openai",
            "openai_embed_key": "",
            "openrouter_api_key": "",
            "llm_model": "",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_no_key_raises_503(self):
        with patch("app.llm.chat.get_settings", return_value=self._make_settings()):
            with pytest.raises(HTTPException) as exc_info:
                _resolve_provider()
            assert exc_info.value.status_code == 503
            assert "LLM not configured" in exc_info.value.detail

    def test_openai_provider_resolves(self):
        settings = self._make_settings(openai_embed_key="sk-test-key")
        with patch("app.llm.chat.get_settings", return_value=settings):
            provider, url, key = _resolve_provider()
            assert provider == "openai"
            assert url == _PROVIDERS["openai"]["url"]
            assert key == "sk-test-key"

    def test_openrouter_provider_resolves(self):
        settings = self._make_settings(
            llm_provider="openrouter",
            openrouter_api_key="sk-or-test-key",
        )
        with patch("app.llm.chat.get_settings", return_value=settings):
            provider, url, key = _resolve_provider()
            assert provider == "openrouter"
            assert url == _PROVIDERS["openrouter"]["url"]
            assert key == "sk-or-test-key"

    def test_unknown_provider_raises_503(self):
        settings = self._make_settings(llm_provider="unknown_vendor")
        with patch("app.llm.chat.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc_info:
                _resolve_provider()
            assert exc_info.value.status_code == 503
            assert "Unknown LLM_PROVIDER" in exc_info.value.detail

    def test_openrouter_no_key_raises_503(self):
        settings = self._make_settings(llm_provider="openrouter", openrouter_api_key="")
        with patch("app.llm.chat.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc_info:
                _resolve_provider()
            assert exc_info.value.status_code == 503


# ── llm_configured ───────────────────────────────────────────────────


class TestLlmConfigured:
    def _make_settings(self, **overrides):
        defaults = {
            "llm_provider": "openai",
            "openai_embed_key": "",
            "openrouter_api_key": "",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_false_when_no_key(self):
        with patch("app.llm.chat.get_settings", return_value=self._make_settings()):
            assert llm_configured() is False

    def test_true_with_openai_key(self):
        settings = self._make_settings(openai_embed_key="sk-test")
        with patch("app.llm.chat.get_settings", return_value=settings):
            assert llm_configured() is True

    def test_true_with_openrouter_key(self):
        settings = self._make_settings(
            llm_provider="openrouter",
            openrouter_api_key="sk-or-test",
        )
        with patch("app.llm.chat.get_settings", return_value=settings):
            assert llm_configured() is True


# ── chat_completion ──────────────────────────────────────────────────


class TestChatCompletion:
    """Tests for the chat_completion function with mocked HTTP."""

    def _make_settings(self, **overrides):
        defaults = {
            "llm_provider": "openrouter",
            "openai_embed_key": "",
            "openrouter_api_key": "sk-or-test",
            "llm_model": "",
            "cors_origin_list": ["https://channelzero.vercel.app"],
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_successful_completion(self):
        settings = self._make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await chat_completion("Hello")
                assert result == "Test response"

    @pytest.mark.asyncio
    async def test_upstream_rate_limit_raises_429(self):
        settings = self._make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = '{"error": "rate limited"}'

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(HTTPException) as exc_info:
                    await chat_completion("Hello")
                assert exc_info.value.status_code == 429
                assert "rate-limited" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_upstream_error_raises_502(self):
        settings = self._make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "internal server error"}'

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(HTTPException) as exc_info:
                    await chat_completion("Hello")
                assert exc_info.value.status_code == 502
                assert "LLM call failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_malformed_response_raises_502(self):
        settings = self._make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}  # empty choices

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(HTTPException) as exc_info:
                    await chat_completion("Hello")
                assert exc_info.value.status_code == 502
                assert "Malformed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_openrouter_headers_include_referer_and_title(self):
        settings = self._make_settings()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await chat_completion("Hello")

                # Verify headers passed to OpenRouter
                call_kwargs = mock_client.post.call_args
                headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
                assert headers["X-Title"] == "ChannelZero"
                assert headers["HTTP-Referer"] == "https://channelzero.vercel.app"

    @pytest.mark.asyncio
    async def test_model_override(self):
        settings = self._make_settings(llm_model="nvidia/nemotron-3-super-120b-a12b:free")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.llm.chat.get_settings", return_value=settings):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await chat_completion("Hello")

                call_kwargs = mock_client.post.call_args
                payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
                assert payload["model"] == "nvidia/nemotron-3-super-120b-a12b:free"
