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
from pocketquant.core.domain.order import OrderStatus
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.persistence.repositories.safeguards_repository import (
    SafeguardsRepository,
)
from tests.core_test.infra.brokers.exness.test_exness_broker_adapter import _Harness, _order

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
            yield client, app


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
    async with _client(settings) as (first, _):
        assert (await first.post(_path(settings, "/pause"))).status_code == 200

    async with _client(settings) as (second, _):
        assert (await second.get(_path(settings))).json()["entries_paused"] is True
        assert (await second.post(_path(settings, "/resume"))).status_code == 200

    async with _client(settings) as (third, _):
        assert (await third.get(_path(settings))).json()["entries_paused"] is False


@pytest.mark.asyncio
async def test_a_route_pause_refuses_the_next_open_of_another_adapter(settings: Settings) -> None:
    async with _client(settings) as (client, app):
        assert (await client.post(_path(settings, "/pause"))).status_code == 200
        repo = await app.state.dishka_container.get(SafeguardsRepository)
        h = _Harness()
        h.broker._safeguards_repo = repo

        result = await h.broker.submit_order(_order())

        assert result.status == OrderStatus.REJECTED
        assert result.error_message == "entries paused"
        assert h.client.ops("openPosition") == []
        assert (await client.post(_path(settings, "/resume"))).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_pause_write_returns_503(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail(self: SafeguardsRepository, paused: bool) -> None:
        raise RuntimeError("mongo down")

    monkeypatch.setattr(SafeguardsRepository, "save_entries_paused", _fail)
    async with _client(settings) as (client, _):
        response = await client.post(_path(settings, "/pause"))
        assert response.status_code == 503
        assert response.json() == {"detail": "pause not stored"}
        assert (await client.get(_path(settings))).json()["entries_paused"] is False


def test_safeguards_has_no_entries_paused_field() -> None:
    assert "entries_paused" not in Safeguards.__dataclass_fields__


@pytest.mark.asyncio
async def test_reads_within_a_second_share_one_store_read(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = SafeguardsRepository.load_entries_paused
    reads = 0

    async def _counting(self: SafeguardsRepository) -> bool:
        nonlocal reads
        reads += 1
        return await original(self)

    monkeypatch.setattr(SafeguardsRepository, "load_entries_paused", _counting)
    async with _client(settings) as (client, _):
        codes = [(await client.get(_path(settings))).status_code for _ in range(5)]

    assert codes == [200] * 5
    assert reads == 1
