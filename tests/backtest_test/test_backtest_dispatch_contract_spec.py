from __future__ import annotations

from typing import Any

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.engine.backtest import backtest_execution_service
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService

XAUUSD_SYMBOL = "XAUUSD:EXNESS"
# 100 oz per lot in 0.01-lot steps; the per-lot fee exercises the per-contract model.
XAUUSD = ContractSpec(multiplier=100.0, tick_size=0.001, lot_step=0.01, commission_per_contract=2.5)


class _FakeLookup:
    async def contract_spec(self, composite: str) -> ContractSpec:
        return XAUUSD if composite == XAUUSD_SYMBOL else LINEAR_SPEC


class _FakeCalendars:
    async def for_symbol(self, composite: str) -> Continuous24x7Calendar:
        return Continuous24x7Calendar()


class _CapturingRunner:
    seen: dict[str, Any] = {}

    def __init__(self, *, broker: Any, **_: Any) -> None:
        _CapturingRunner.seen["broker"] = broker

    async def run(self, config: Any, run_id: str | None = None) -> str:
        _CapturingRunner.seen["config"] = config
        return "result"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("symbol", "spec"), [(XAUUSD_SYMBOL, XAUUSD), ("BTCUSDT:BINANCE", LINEAR_SPEC)]
)
async def test_backtest_config_and_broker_carry_the_symbol_spec(
    monkeypatch: pytest.MonkeyPatch, symbol: str, spec: ContractSpec
) -> None:
    monkeypatch.setattr(backtest_execution_service, "BacktestAppService", _CapturingRunner)
    execution = BacktestExecutionService(
        bar_repository=None,  # type: ignore[arg-type]
        backtest_repository=None,  # type: ignore[arg-type]
        backtest_order_repository=None,  # type: ignore[arg-type]
        backtest_trade_repository=None,  # type: ignore[arg-type]
        calendar_factory=_FakeCalendars(),  # type: ignore[arg-type]
        symbol_lookup=_FakeLookup(),  # type: ignore[arg-type]
    )

    await execution.run(
        {
            "strategy_code": "hitnrun2",
            "symbol": symbol,
            "interval": "1h",
            "start_date": "2026-09-01T00:00:00+00:00",
            "end_date": "2026-09-20T00:00:00+00:00",
        },
    )

    assert _CapturingRunner.seen["config"].contract_spec == spec
    broker = _CapturingRunner.seen["broker"]
    assert broker._contract_spec == spec
    # XAUUSD commission is per lot; crypto keeps the percentage model.
    assert broker._commission(2650.0, 2) == pytest.approx(
        5.0 if spec is XAUUSD else 2650 * 2 * 3e-4
    )
