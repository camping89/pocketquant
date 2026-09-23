"""An ad-hoc backtest on a futures symbol runs with that symbol's contract spec."""

from __future__ import annotations

from typing import Any

import pytest

from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.engine.backtest import backtest_dispatch
from pocketquant.engine.backtest.backtest_dispatch import BacktestDispatchDeps, run_single

ES_SYMBOL = "ES1!:CME_MINI"
ES = ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, commission_per_contract=2.5)


class _FakeLookup:
    async def contract_spec(self, composite: str) -> ContractSpec:
        return ES if composite == ES_SYMBOL else LINEAR_SPEC


class _FakeCalendars:
    async def for_symbol(self, composite: str) -> Continuous24x7Calendar:
        return Continuous24x7Calendar()


class _CapturingRunner:
    """Replaces BacktestAppService: records what run_single hands the engine."""

    seen: dict[str, Any] = {}

    def __init__(self, *, broker: Any, **_: Any) -> None:
        _CapturingRunner.seen["broker"] = broker

    async def run(self, config: Any, run_id: str | None = None) -> str:
        _CapturingRunner.seen["config"] = config
        return "result"


@pytest.mark.asyncio
@pytest.mark.parametrize(("symbol", "spec"), [(ES_SYMBOL, ES), ("BTCUSDT:BINANCE", LINEAR_SPEC)])
async def test_backtest_config_and_broker_carry_the_symbol_spec(
    monkeypatch: pytest.MonkeyPatch, symbol: str, spec: ContractSpec
) -> None:
    monkeypatch.setattr(backtest_dispatch, "BacktestAppService", _CapturingRunner)
    deps = BacktestDispatchDeps(
        bar_repo=None,  # type: ignore[arg-type]
        backtest_repo=None,  # type: ignore[arg-type]
        order_repo=None,  # type: ignore[arg-type]
        trade_repo=None,  # type: ignore[arg-type]
        calendar_factory=_FakeCalendars(),  # type: ignore[arg-type]
        symbol_lookup=_FakeLookup(),  # type: ignore[arg-type]
    )

    await run_single(
        deps,
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
    # ES commission is per contract; crypto keeps the percentage model.
    assert broker._commission(4500.0, 2) == pytest.approx(5.0 if spec is ES else 4500 * 2 * 3e-4)
