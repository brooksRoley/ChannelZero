"""Tests: costar_password is SecretStr (never echoed in repr/logs)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user_id
from app.costar.router import CoStarIngestRequest
from app.main import app

FAKE_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user_id] = lambda: FAKE_USER_ID
    yield
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestCoStarSecretStr:
    def test_costar_password_not_in_repr(self):
        req = CoStarIngestRequest(costar_username="user@example.com", costar_password="s3cr3t!")
        assert "s3cr3t!" not in repr(req)
        assert "s3cr3t!" not in str(req)

    def test_costar_password_get_secret_value(self):
        req = CoStarIngestRequest(costar_username="user@example.com", costar_password="s3cr3t!")
        assert req.costar_password.get_secret_value() == "s3cr3t!"

    def test_ingest_sends_raw_password_to_costar_api(self, client):
        """Verify the raw password value (not '**') reaches the upstream HTTP call."""
        captured: list[dict] = []

        async def fake_post(url, json=None, **kwargs):
            captured.append({"url": url, "json": json})
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "token": "tok",
                "placements": [{"planet": "sun", "sign": "Scorpio"}],
            }
            return resp

        async def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"placements": [{"planet": "sun", "sign": "Scorpio"}]}
            return resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=fake_post)
        mock_client.get = AsyncMock(side_effect=fake_get)

        with (
            patch("app.costar.router.httpx.AsyncClient", return_value=mock_client),
            patch("app.costar.router.get_conn") as mock_get_conn,
        ):
            fake_execute = AsyncMock()
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=AsyncMock(execute=fake_execute))
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_conn.return_value = ctx

            resp = client.post(
                "/api/costar/ingest",
                json={"costar_username": "user@example.com", "costar_password": "s3cr3t!"},
            )

        assert resp.status_code == 200
        assert captured, "Expected at least one HTTP POST to Co-Star"
        login_call = captured[0]
        assert login_call["json"]["password"] == "s3cr3t!", (
            "raw password must reach the Co-Star API, not the masked '**' repr"
        )
