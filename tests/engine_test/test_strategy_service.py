"""Pin StrategyCommandService + StrategyQueryService behavior.

Covers the same scenarios as the old handlers so the net behavior is preserved:
  - start/stop write desired_state declaratively
  - add_symbol: fail-fast 404 for untracked symbol or unknown template
  - add_symbol: persists desired_state="stopped", no auto-start
  - remove_symbol: deletes the subscription (forward-testing only, no backtest state)
  - delete_strategy: cascade-deletes all subs + ad-hoc backtest runs
  - get_all / get_one return from STRATEGY_REGISTRY
  - list_symbols: maps subscriptions + derives is_running (no backtest join)
  - get_positions / get_trades: map repo entities to FE shapes
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import UUID
from pocketquant.core.domain.position.entities import PositionAggregate
from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.engine.strategy.strategy_command_service import (
    AddSymbolCommand,
    DeleteStrategyCommand,
    RemoveSymbolCommand,
    StartStrategyCommand,
    StopStrategyCommand,
    StrategyCommandService,
)
from pocketquant.engine.strategy.strategy_query_service import (
    GetStrategiesQuery,
    GetStrategyPositionsQuery,
    GetStrategyQuery,
    GetStrategyTradesQuery,
    ListSymbolsQuery,
    StrategyQueryService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd_svc(
    *,
    sub_repo: object | None = None,
    bt_repo: object | None = None,
    tracked_repo: object | None = None,
) -> StrategyCommandService:
    sub_repo = sub_repo or MagicMock()
    bt_repo = bt_repo or MagicMock()
    tracked_repo = tracked_repo or MagicMock()
    return StrategyCommandService(
        subscription_repository=sub_repo,
        backtest_repository=bt_repo,
        tracked_symbol_repository=tracked_repo,
    )


def _query_svc(
    *,
    sub_repo: object | None = None,
    position_repo: object | None = None,
) -> StrategyQueryService:
    sub_repo = sub_repo or MagicMock()
    position_repo = position_repo or MagicMock()
    return StrategyQueryService(
        subscription_repository=sub_repo,
        position_repository=position_repo,
    )


def _open_position(subscription_id: str = "sub-1") -> PositionAggregate:
    return PositionAggregate(
        id=uuid5(NAMESPACE_OID, "pos-open"),
        subscription_id=subscription_id,
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=2.0,
        current_price=110.0,
        opened_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        sl_price=95.0,
        tp_price=120.0,
    )


def _closed_position(idx: int = 1, subscription_id: str = "sub-1") -> PositionAggregate:
    return PositionAggregate(
        id=uuid5(NAMESPACE_OID, f"pos-closed-{idx}"),
        subscription_id=subscription_id,
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.SHORT,
        entry_price=200.0,
        quantity=0.0,
        current_price=180.0,
        realized_pnl=20.0,
        is_closed=True,
        opened_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        closed_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# StrategyCommandService — start / stop
# ---------------------------------------------------------------------------


# start/stop are mirror operations: each writes one desired_state value via the
# same repo call, and each 404s when the update matches zero docs. Folded by op.
@pytest.mark.parametrize(
    ("op", "command", "written_state"),
    [
        pytest.param("start", StartStrategyCommand(subscription_id="sub-1"), "running", id="start"),
        pytest.param("stop", StopStrategyCommand(subscription_id="sub-1"), "stopped", id="stop"),
    ],
)
@pytest.mark.asyncio
async def test_start_stop_writes_desired_state(op, command, written_state) -> None:
    sub_repo = MagicMock()
    sub_repo.update_desired_state = AsyncMock(return_value=1)
    svc = _cmd_svc(sub_repo=sub_repo)

    result = await getattr(svc, op)(command)

    assert result is True
    sub_repo.update_desired_state.assert_awaited_once_with("sub-1", written_state)


@pytest.mark.parametrize(
    ("op", "command"),
    [
        pytest.param("start", StartStrategyCommand(subscription_id="missing"), id="start"),
        pytest.param("stop", StopStrategyCommand(subscription_id="missing"), id="stop"),
    ],
)
@pytest.mark.asyncio
async def test_start_stop_raises_not_found_when_no_sub_matches(op, command) -> None:
    sub_repo = MagicMock()
    sub_repo.update_desired_state = AsyncMock(return_value=0)
    svc = _cmd_svc(sub_repo=sub_repo)

    with pytest.raises(NotFoundError):
        await getattr(svc, op)(command)


# ---------------------------------------------------------------------------
# StrategyCommandService — add_symbol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_symbol_persists_stopped_state() -> None:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=True)

    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=tracked_repo)
    result = await svc.add_symbol(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    sub_repo.add.assert_awaited_once()
    persisted = sub_repo.add.await_args.args[0]
    assert UUID(str(persisted.id)).version == 7
    assert persisted.desired_state == "stopped"
    assert persisted.actual_state == "stopped"
    assert result["id"] == str(persisted.id)


@pytest.mark.asyncio
async def test_add_symbol_404_when_symbol_not_tracked() -> None:
    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=False)

    svc = _cmd_svc(tracked_repo=tracked_repo)

    with pytest.raises(NotFoundError) as exc:
        await svc.add_symbol(
            AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
        )
    assert exc.value.error_code == "SYMBOL_NOT_TRACKED"


@pytest.mark.asyncio
async def test_add_symbol_404_when_unknown_template() -> None:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=True)

    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=tracked_repo)

    with pytest.raises(NotFoundError):
        await svc.add_symbol(
            AddSymbolCommand(strategy_id="does-not-exist", symbol="BTCUSDT:BINANCE", interval="1h")
        )
    sub_repo.add.assert_not_called()


# ---------------------------------------------------------------------------
# StrategyCommandService — remove_symbol / delete_strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_symbol_deletes_subscription() -> None:
    sub_repo = MagicMock()
    sub_repo.delete = AsyncMock()

    svc = _cmd_svc(sub_repo=sub_repo)
    await svc.remove_symbol(RemoveSymbolCommand(sub_id="sub-1"))

    sub_repo.delete.assert_awaited_once_with("sub-1")


@pytest.mark.asyncio
async def test_delete_strategy_cascades_in_order() -> None:
    sub_repo = MagicMock()
    sub_repo.delete_by_strategy_code = AsyncMock()
    bt_repo = MagicMock()
    bt_repo.delete_by_strategy_code = AsyncMock()

    call_order: list[str] = []
    bt_repo.delete_by_strategy_code.side_effect = lambda _: call_order.append("bt")
    sub_repo.delete_by_strategy_code.side_effect = lambda _: call_order.append("sub")

    svc = _cmd_svc(sub_repo=sub_repo, bt_repo=bt_repo)
    await svc.delete_strategy(DeleteStrategyCommand(strategy_id="hitnrun2"))

    assert call_order == ["bt", "sub"]


# ---------------------------------------------------------------------------
# StrategyQueryService — get_all / get_one
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_returns_registry_codes() -> None:
    svc = _query_svc()
    result = await svc.get_all(GetStrategiesQuery())
    assert isinstance(result, list)
    # STRATEGY_REGISTRY may have entries in test env; just check shape
    for entry in result:
        assert "strategy_code" in entry


@pytest.mark.asyncio
async def test_get_one_returns_none_for_unknown_code() -> None:
    svc = _query_svc()
    result = await svc.get_one(GetStrategyQuery(strategy_code="definitely-does-not-exist-xyz"))
    assert result is None


# ---------------------------------------------------------------------------
# StrategyQueryService — list_symbols
# ---------------------------------------------------------------------------


# is_running derives purely from actual_state (desired_state held at "running"):
# actual "running" → True, actual "stopped" (still converging) → False.
@pytest.mark.parametrize(
    ("actual_state", "expected_is_running"),
    [
        pytest.param("running", True, id="actual_running"),
        pytest.param("stopped", False, id="actual_stopped_converging"),
    ],
)
@pytest.mark.asyncio
async def test_list_symbols_derives_is_running_from_actual_state(
    actual_state, expected_is_running
) -> None:
    from pocketquant.core.domain.shared.enums import Interval

    sub = MagicMock()
    sub.id = "sub-abc"
    sub.strategy_code = "hitnrun2"
    sub.symbol = "BTCUSDT:BINANCE"
    sub.interval = Interval.HOUR_1
    sub.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.desired_state = "running"
    sub.actual_state = actual_state

    sub_repo = MagicMock()
    sub_repo.list_all = AsyncMock(return_value=[sub])

    svc = _query_svc(sub_repo=sub_repo)
    rows = await svc.list_symbols(ListSymbolsQuery())

    assert len(rows) == 1
    assert rows[0]["is_running"] is expected_is_running
    assert rows[0]["desired_state"] == "running"
    assert rows[0]["actual_state"] == actual_state


@pytest.mark.asyncio
async def test_list_symbols_returns_empty_when_no_subs() -> None:
    sub_repo = MagicMock()
    sub_repo.list_all = AsyncMock(return_value=[])
    svc = _query_svc(sub_repo=sub_repo)
    assert await svc.list_symbols(ListSymbolsQuery()) == []


# ---------------------------------------------------------------------------
# StrategyQueryService — get_positions / get_trades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_positions_maps_open_positions() -> None:
    pos_repo = MagicMock()
    pos_repo.find_open_by_subscription = AsyncMock(return_value=[_open_position()])
    svc = _query_svc(position_repo=pos_repo)

    result = await svc.get_positions(GetStrategyPositionsQuery(subscription_id="sub-1"))

    pos_repo.find_open_by_subscription.assert_awaited_once_with("sub-1")
    assert len(result) == 1
    row = result[0]
    assert row["direction"] == "LONG"
    assert row["entry_price"] == 100.0
    assert row["unrealized_pnl"] == 20.0
    assert row["sl_price"] == 95.0
    assert row["tp_price"] == 120.0


@pytest.mark.asyncio
async def test_get_positions_returns_empty_when_none_open() -> None:
    pos_repo = MagicMock()
    pos_repo.find_open_by_subscription = AsyncMock(return_value=[])
    svc = _query_svc(position_repo=pos_repo)
    assert await svc.get_positions(GetStrategyPositionsQuery(subscription_id="sub-1")) == []


@pytest.mark.asyncio
async def test_get_trades_maps_closed_positions() -> None:
    pos_repo = MagicMock()
    pos_repo.find_closed_by_subscription = AsyncMock(
        return_value=[_closed_position(1), _closed_position(2)]
    )
    svc = _query_svc(position_repo=pos_repo)

    result = await svc.get_trades(GetStrategyTradesQuery(subscription_id="sub-1", limit=50))

    pos_repo.find_closed_by_subscription.assert_awaited_once_with("sub-1", limit=50)
    assert len(result) == 2
    row = result[0]
    assert row["id"] == str(uuid5(NAMESPACE_OID, "pos-closed-1"))
    assert row["direction"] == "SHORT"
    assert row["exit_price"] == 180.0
    assert row["pnl"] == 20.0
    assert row["exit_time"] is not None


@pytest.mark.asyncio
async def test_get_trades_returns_empty_when_no_closed() -> None:
    pos_repo = MagicMock()
    pos_repo.find_closed_by_subscription = AsyncMock(return_value=[])
    svc = _query_svc(position_repo=pos_repo)
    assert await svc.get_trades(GetStrategyTradesQuery(subscription_id="sub-1")) == []
