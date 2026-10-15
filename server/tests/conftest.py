"""
Shared test fixtures — a fake asyncpg connection and a get_conn patcher.

The fake conn is a recorder: queue fetchrow/fetchval/fetch results in order, and
every execute/fetchrow call is captured for assertion. Designed so future
connector-router tests can reuse it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest


class FakeConn:
    """Minimal asyncpg.Connection stand-in.

    fetchrow_results and fetchval_results are consumed FIFO; fetch_results
    is a list-of-lists where each item is the full return value of one
    fetch() call. execute and fetchrow calls are recorded for assertion.
    """

    def __init__(
        self,
        fetchrow_results: list | None = None,
        fetchval_results: list | None = None,
        fetch_results: list | None = None,
    ):
        self.fetchrow_results = list(fetchrow_results or [])
        self.fetchval_results = list(fetchval_results or [])
        self.fetch_results = list(fetch_results or [])
        self.fetchrow_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []
        self.executemany_calls: list[tuple] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_results.pop(0) if self.fetchrow_results else None

    async def fetchval(self, query, *args):
        return self.fetchval_results.pop(0) if self.fetchval_results else None

    async def fetch(self, query, *args):
        """Return the next queued result list; defaults to [] when queue is empty."""
        return self.fetch_results.pop(0) if self.fetch_results else []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def executemany(self, query, args_seq):
        self.executemany_calls.append((query, list(args_seq)))
        return None


def make_get_conn(conn: FakeConn):
    """Return an asynccontextmanager factory yielding the given FakeConn,
    suitable for patching module-level `get_conn` imports."""

    @asynccontextmanager
    async def _get_conn():
        yield conn

    return _get_conn


@pytest.fixture
def fake_conn():
    return FakeConn()
