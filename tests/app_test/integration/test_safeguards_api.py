"""Safeguards routes: read the caps, pause and resume entries, and keep the pause across a restart.

Each app built by ``make_test_app`` on the same database stands in for a restart.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from pocketquant.app.middleware import admin_auth_middleware
from pocketquant.core.config import Settings

from .app_factory import make_test_app

_TOKEN = "test-admin-token"


def _path(settings: Settings, action: str = "") -> str:
    return f"{settings.api_prefix}/admin/safeguards{action}"


@asynccontextmanager
async def _client(settings: Settings):
    app = make_test_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_pause_and_resume_flip_the_entry_pause(
    app_client: AsyncClient, settings: Settings
) -> None:
    initial = await app_client.get(_path(settings))
    assert initial.status_code == 200
    assert initial.json() == {
        "live_trading": settings.exness_live_trading,
        "daily_loss_cap": settings.exness_daily_loss_cap,
        "max_lots": settings.exness_max_lots,
        "leverage": settings.exness_leverage,
        "risk_per_trade": settings.exness_risk_per_trade,
        "entries_paused": False,
    }

    assert (await app_client.post(_path(settings, "/pause"))).json()["entries_paused"] is True
    assert (await app_client.get(_path(settings))).json()["entries_paused"] is True
    assert (await app_client.post(_path(settings, "/resume"))).json()["entries_paused"] is False
    assert (await app_client.get(_path(settings))).json()["entries_paused"] is False


@pytest.mark.asyncio
async def test_token_guards_pause_and_resume_but_not_the_read(
    app_client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    patched = settings.model_copy(update={"admin_token": SecretStr(_TOKEN)})
    monkeypatch.setattr(admin_auth_middleware, "get_settings", lambda: patched)

    assert (await app_client.post(_path(settings, "/pause"))).status_code == 401
    assert (await app_client.post(_path(settings, "/resume"))).status_code == 401
    assert (await app_client.get(_path(settings))).status_code == 200


@pytest.mark.asyncio
async def test_pause_survives_a_restart(settings: Settings) -> None:
    async with _client(settings) as first:
        assert (await first.post(_path(settings, "/pause"))).status_code == 200

    async with _client(settings) as second:
        assert (await second.get(_path(settings))).json()["entries_paused"] is True
        assert (await second.post(_path(settings, "/resume"))).status_code == 200

    async with _client(settings) as third:
        assert (await third.get(_path(settings))).json()["entries_paused"] is False
