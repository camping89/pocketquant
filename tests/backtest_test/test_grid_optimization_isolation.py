"""GridOptimizationAppService — per-run sandbox isolation + non-zero trades.

Phase 5 fix: each combination injects its strategy into its own sandbox (own
EventBus + StrategyAppService), so concurrent runs produce real trades (was 0)
and never cross-talk on bar dispatch / fills.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest

from pocketquant.backtest.optimization.grid_optimization_app_service import (
    GridOptimizationAppService,
)
from pocketquant.backtest.optimization.models.optimization_config import OptimizationConfig
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval

_SYM = "BTCUSDT:BINANCE"


@pytest.fixture(autouse=True)
def _reset_sim_time():
    clear_simulation_time()
    yield
    clear_simulation_time()


class _InMemoryBacktestRepo:
    async def save(self, result: BacktestResult) -> str:
        return "x"


class _FakeBarRepo:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def stream(self, *args, **kwargs) -> AsyncIterator[Bar]:
        for b in self._bars:
            yield b

    async def find_datetimes(self, *args, **kwargs) -> list:
        return []


def _bar(idx: int, o: float, h: float, lo: float, c: float, t0: datetime) -> Bar:
    return Bar(
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        datetime=t0 + timedelta(minutes=idx),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1.0,
    )


def _oscillating_bars(cycles: int = 4) -> list[Bar]:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[Bar] = []
    idx = 0
    lvl = 100.0
    for _ in range(25):
        bars.append(_bar(idx, lvl, lvl + 0.05, lvl - 0.05, lvl, t0))
        idx += 1
    for cyc in range(cycles):
        low = lvl - 1.0 - cyc * 0.5
        bars.append(_bar(idx, lvl, lvl + 0.05, low - 0.05, low, t0))
        idx += 1
        bars.append(_bar(idx, low, lvl + 0.5, low - 0.05, lvl, t0))
        idx += 1
        for _ in range(3):
            bars.append(_bar(idx, lvl, lvl + 0.05, lvl - 0.05, lvl, t0))
            idx += 1
    return bars


def _config(max_workers: int) -> OptimizationConfig:
    return OptimizationConfig(
        strategy_code="hitnrun2",
        symbol=_SYM,
        interval="1m",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        parameter_grid={
            "entry_lookback_bars": [10, 5],
            "sl_lookback_bars": [20],
            "tp_lookback_bars": [5],
            "max_loss_pct": [0.05],
            "min_profit_pct": [0.002],
            "direction": ["long"],
        },
        target_metric="sharpe_ratio",
        max_workers=max_workers,
    )


async def test_each_combination_produces_trades() -> None:
    opt = GridOptimizationAppService(
        backtest_repository=_InMemoryBacktestRepo(),  # pyright: ignore[reportArgumentType]
        bar_repository=_FakeBarRepo(_oscillating_bars()),  # pyright: ignore[reportArgumentType]
    )
    result = await opt.optimize(_config(max_workers=2))

    assert result.status == "completed"
    assert result.completed_combinations == 2
    assert result.failed_combinations == 0
    for entry in result.results:
        assert entry.metrics.total_trades > 0


async def test_concurrent_runs_isolated_same_symbol() -> None:
    """Two combinations on the same symbol/interval run concurrently without
    cross-talk: each independent run reports its own trades (no doubling)."""
    serial = GridOptimizationAppService(
        backtest_repository=_InMemoryBacktestRepo(),  # pyright: ignore[reportArgumentType]
        bar_repository=_FakeBarRepo(_oscillating_bars()),  # pyright: ignore[reportArgumentType]
    )
    serial_result = await serial.optimize(_config(max_workers=1))

    concurrent = GridOptimizationAppService(
        backtest_repository=_InMemoryBacktestRepo(),  # pyright: ignore[reportArgumentType]
        bar_repository=_FakeBarRepo(_oscillating_bars()),  # pyright: ignore[reportArgumentType]
    )
    concurrent_result = await concurrent.optimize(_config(max_workers=2))

    # Isolation: trade counts identical whether run serially or concurrently.
    serial_trades = sorted(e.metrics.total_trades for e in serial_result.results)
    concurrent_trades = sorted(e.metrics.total_trades for e in concurrent_result.results)
    assert serial_trades == concurrent_trades
