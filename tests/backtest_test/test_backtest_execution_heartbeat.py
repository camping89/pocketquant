from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pocketquant.engine.backtest import backtest_execution_service as execution_module
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService


class _Repo:
    def __init__(self) -> None:
        self.touches = 0

    async def touch_heartbeat(self, run_id: str) -> None:
        self.touches += 1


async def test_heartbeat_refreshes_while_running_and_stops_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(execution_module, "_HEARTBEAT_S", 0.05)
    repo = _Repo()
    service = BacktestExecutionService(
        bar_repository=None,  # type: ignore[arg-type]
        backtest_repository=repo,  # type: ignore[arg-type]
        backtest_order_repository=None,  # type: ignore[arg-type]
        backtest_trade_repository=None,  # type: ignore[arg-type]
        calendar_factory=None,  # type: ignore[arg-type]
        symbol_lookup=None,  # type: ignore[arg-type]
    )

    async def run(config_payload: dict[str, Any], *, run_id: str) -> Any:
        await asyncio.sleep(0.2)
        return type("Result", (), {"status": "finished"})()

    monkeypatch.setattr(service, "run", run)

    await service.execute_and_persist("run-1", {})
    touches = repo.touches
    await asyncio.sleep(0.2)

    assert touches >= 3
    assert repo.touches == touches
