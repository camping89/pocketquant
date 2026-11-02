from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from tests.engine_test.test_paper_capabilities import (  # noqa: F401  (_sim_time is autouse)
    _MARKET,
    _SID,
    _SYM,
    _open_with_a_pending_stop,
    _Paper,
    _paper,
    _sim_time,
    _stop,
    _Store,
)
from tests.engine_test.test_strategy_snapshot import _Cache
from tests.strategy_doubles import ScriptedStrategy


async def _cached(*script: dict | None) -> _Paper:
    p = await _paper(*script)
    p.engine._cache = _Cache()  # type: ignore[assignment]
    return p


async def test_close_cancels_the_stop_and_closes_the_position() -> None:
    p = await _cached(_MARKET)
    await _open_with_a_pending_stop(p)

    assert await p.engine.manual_action(_SID, "close") == "accepted"

    assert len(p.trades) == 1
    assert p.orders.pending_stop(_SID) is None
    assert await p.broker.get_positions() == []
    record = p.engine._snapshots[_SID][-1]
    assert record["decision"] == {"action": "manual_close", "reason": "owner request"}
    assert record["interval"] is None
    assert record["outcome"] == "accepted"
    assert record["pending"] is None


async def test_close_runs_when_the_cancel_fails() -> None:
    p = await _cached(_MARKET)
    await _open_with_a_pending_stop(p)
    p.broker.cancel_order = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with structlog.testing.capture_logs() as logs:
        outcome = await p.engine.manual_action(_SID, "close")

    assert outcome == "accepted"
    assert len(p.trades) == 1
    failed = [e for e in logs if e["event"] == "strategy.pending_cancel_failed"]
    assert [e["log_level"] for e in failed] == ["warning"]


async def test_cancel_leaves_the_position_open() -> None:
    p = await _cached(_MARKET)
    await _open_with_a_pending_stop(p)

    assert await p.engine.manual_action(_SID, "cancel") == "accepted"

    assert p.orders.pending_stop(_SID) is None
    assert len(await p.broker.get_positions()) == 1
    assert p.trades == []


async def test_cancel_with_nothing_pending_is_rejected() -> None:
    p = await _cached(None)
    await p.bar()

    assert await p.engine.manual_action(_SID, "cancel") == "rejected:nothing_pending"


async def test_close_with_nothing_open_is_rejected() -> None:
    p = await _cached(None)
    await p.bar()

    assert await p.engine.manual_action(_SID, "close") == "rejected:nothing_open"


async def test_close_with_only_a_stop_cancels_it() -> None:
    p = await _cached(_stop(105.0))
    await p.bar()

    assert await p.engine.manual_action(_SID, "close") == "accepted"

    assert p.orders.pending_stop(_SID) is None


async def test_a_failed_close_is_rejected() -> None:
    p = await _cached(_MARKET)
    await p.bar()
    p.broker.close_position = AsyncMock(return_value=False)  # type: ignore[method-assign]

    assert await p.engine.manual_action(_SID, "close") == "rejected:close_failed"


async def test_no_broker_is_rejected() -> None:
    p = await _cached(None)
    await p.bar()
    p.engine._brokers.pop(_SID)

    assert await p.engine.manual_action(_SID, "close") == "rejected:no_broker"


async def test_drain_keeps_the_action_queued() -> None:
    p = await _cached(_MARKET)
    await p.bar()
    close = AsyncMock(return_value=True)
    p.broker.close_position = close  # type: ignore[method-assign]
    p.engine.trading_until = None

    assert await p.engine.manual_action(_SID, "close") is None

    close.assert_not_called()
    assert p.engine._snapshots[_SID][-1]["decision"] is None


class _OneOpen(_Store):
    def __init__(self, row: PositionAggregate) -> None:
        super().__init__()
        self.row = row

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [self.row.model_copy(deep=True)]


async def test_close_waits_for_a_price_after_a_takeover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScriptedStrategy, "SCRIPT", ())
    p = _Paper()
    row = PositionAggregate.open(
        subscription_id=_SID, symbol=_SYM, side=PositionSide.LONG, entry_price=1900.0, quantity=1.0
    )
    p.mirror._position_repo = _OneOpen(row)  # type: ignore[assignment]
    await p.mirror.start()
    await p.engine.start()
    config = StrategyConfig(id=_SID, name="t", symbol=_SYM, intervals=["1m"], broker="paper")
    await p.engine.load_strategy(config, ScriptedStrategy)
    await p.engine.start_strategy(_SID)
    await p.engine.take_over()

    assert await p.engine.manual_action(_SID, "close") is None
    assert p.trades == []

    await p.bar(o=2000.0, h=2000.5, low=1999.5, c=2000.0)

    assert await p.engine.manual_action(_SID, "close") == "accepted"
    [trade] = p.trades
    assert trade.exit_price == pytest.approx(2000.0)
