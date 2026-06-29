"""PATCH /backtest/{run_id}/verdict over the HTTP API.

Sets a human-readable verdict on a finished run without touching metrics, and
404s on an unknown run. Seeds the run doc straight through the repository so the
test is independent of the engine path.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.config import Settings
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

pytestmark = pytest.mark.asyncio

_CONFIG = {"strategy_code": "engulfing", "symbol": "BTCUSDT:BINANCE", "interval": "1m"}


async def _seed_finished_run(settings: Settings) -> str:
    db = Database()
    await db.connect(settings)
    try:
        run_id = generate_id_str()
        run = BacktestResult.started(run_id, _CONFIG)
        run.status = "finished"
        await BacktestRepository(db).save(run)
        return run_id
    finally:
        await db.disconnect()


async def test_patch_sets_verdict_and_get_returns_it(
    app_client: AsyncClient, settings: Settings
) -> None:
    run_id = await _seed_finished_run(settings)
    verdict = "Fee-killed: 11451 trades, pf 0.095, negative edge."

    resp = await app_client.patch(
        f"{settings.api_prefix}/backtest/{run_id}/verdict", json={"verdict": verdict}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": run_id, "verdict": verdict}

    got = await app_client.get(f"{settings.api_prefix}/backtest/{run_id}")
    assert got.status_code == 200
    assert got.json()["verdict"] == verdict


async def test_patch_unknown_run_is_404(app_client: AsyncClient, settings: Settings) -> None:
    resp = await app_client.patch(
        f"{settings.api_prefix}/backtest/{generate_id_str()}/verdict",
        json={"verdict": "x"},
    )
    assert resp.status_code == 404
