"""The psychometrics narrative runs on the server LLM — no user API key lookup."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.llm.psychoanalysis import generate_psychoanalysis_narrative

from .conftest import FakeConn

USER = UUID("00000000-0000-0000-0000-000000000001")


def _pool(conn):
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


@pytest.mark.anyio
async def test_narrative_uses_server_chat_completion():
    conn = FakeConn(fetchrow_results=[{"spotify_data": '{"genres": ["ambient"], "top_artists": ["Eno"]}'}])
    llm = AsyncMock(return_value="A quietly driven soul.")
    with patch("app.llm.psychoanalysis.get_pool", return_value=_pool(conn)), \
         patch("app.llm.psychoanalysis.chat_completion", llm):
        out = await generate_psychoanalysis_narrative(USER, {"ipip_neo_scores": {"O": 70}})

    assert out == "A quietly driven soul."
    assert "ambient" in llm.call_args.args[0]
    # Only the Spotify read — no user_api_keys query.
    assert len(conn.fetchrow_calls) == 1
    assert "user_api_keys" not in conn.fetchrow_calls[0][0]
