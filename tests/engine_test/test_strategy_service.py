from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.core.common.exceptions import DomainError, NotFoundError
from pocketquant.core.common.uuid import UUID, generate_id
from pocketquant.core.domain.position.entities import PositionAggregate
from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.engine.strategy.strategy_command_service import (
    StrategyCommandService,
)
from pocketquant.engine.strategy.strategy_query_service import (
    StrategyQueryService,
)

pytestmark = pytest.mark.usefixtures("probe_registry")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cmd_svc(
    *,
    sub_repo: object | None = None,
    tracked_repo: object | None = None,
    position_repo: object | None = None,
    order_repo: object | None = None,
) -> StrategyCommandService:
    sub_repo = sub_repo or MagicMock()
    tracked_repo = tracked_repo or MagicMock()
    return StrategyCommandService(
        subscription_repository=sub_repo,
        tracked_symbol_repository=tracked_repo,
        safeguards_repository=MagicMock(load_live_trading=AsyncMock(return_value=False)),
        position_repository=position_repo or MagicMock(),
        order_repository=order_repo or MagicMock(),
    )


def _tracked() -> MagicMock:
    return MagicMock(exists=AsyncMock(return_value=True))


def _stored_sub(**overrides) -> Subscription:
    base: dict = dict(
        id=generate_id(),
        strategy_code="probe",
        symbol="BTCUSDT:BINANCE",
        intervals=(Interval.HOUR_1,),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return Subscription(**base)


def _edit_svc(
    sub: Subscription | None,
    *,
    positions: list | None = None,
    pending: list | None = None,
    matched: int = 1,
) -> tuple[StrategyCommandService, MagicMock]:
    sub_repo = MagicMock(
        get=AsyncMock(return_value=sub), update_config=AsyncMock(return_value=matched)
    )
    svc = _cmd_svc(
        sub_repo=sub_repo,
        position_repo=MagicMock(find_open_by_subscription=AsyncMock(return_value=positions or [])),
        order_repo=MagicMock(find_pending=AsyncMock(return_value=pending or [])),
    )
    return svc, sub_repo


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
    ("op", "sub_id", "written_state"),
    [
        pytest.param("start", "sub-1", "running", id="start"),
        pytest.param("stop", "sub-1", "stopped", id="stop"),
    ],
)
@pytest.mark.asyncio
async def test_start_stop_writes_desired_state(op, sub_id, written_state) -> None:
    sub_repo = MagicMock()
    sub_repo.update_desired_state = AsyncMock(return_value=1)
    svc = _cmd_svc(sub_repo=sub_repo)

    result = await getattr(svc, op)(sub_id)

    assert result is True
    sub_repo.update_desired_state.assert_awaited_once_with("sub-1", written_state)


@pytest.mark.parametrize(
    ("op", "sub_id"),
    [
        pytest.param("start", "missing", id="start"),
        pytest.param("stop", "missing", id="stop"),
    ],
)
@pytest.mark.asyncio
async def test_start_stop_raises_not_found_when_no_sub_matches(op, sub_id) -> None:
    sub_repo = MagicMock()
    sub_repo.update_desired_state = AsyncMock(return_value=0)
    svc = _cmd_svc(sub_repo=sub_repo)

    with pytest.raises(NotFoundError):
        await getattr(svc, op)(sub_id)


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
    result = await svc.add_symbol("probe", "BTCUSDT:BINANCE", ["1h"], {})

    sub_repo.add.assert_awaited_once()
    persisted = sub_repo.add.await_args.args[0]
    assert UUID(str(persisted.id)).version == 7
    assert persisted.desired_state == "stopped"
    assert persisted.actual_state == "stopped"
    assert result["id"] == str(persisted.id)


@pytest.mark.asyncio
async def test_add_symbol_accepts_exness_only_while_the_trader_flag_is_on() -> None:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()
    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=True)

    def svc(live_trading: bool) -> StrategyCommandService:
        return StrategyCommandService(
            subscription_repository=sub_repo,
            tracked_symbol_repository=tracked_repo,
            safeguards_repository=MagicMock(load_live_trading=AsyncMock(return_value=live_trading)),
            position_repository=MagicMock(),
            order_repository=MagicMock(),
        )

    with pytest.raises(DomainError) as exc:
        await svc(False).add_symbol("probe", "XAUUSD:EXNESS", ["5m"], {}, broker="exness")
    assert exc.value.error_code == "BROKER_DISABLED"
    sub_repo.add.assert_not_called()

    result = await svc(True).add_symbol("probe", "XAUUSD:EXNESS", ["5m"], {}, broker="exness")
    assert sub_repo.add.await_args.args[0].broker == "exness"
    assert result["broker"] == "exness"


@pytest.mark.asyncio
async def test_add_symbol_404_when_symbol_not_tracked() -> None:
    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=False)

    svc = _cmd_svc(tracked_repo=tracked_repo)

    with pytest.raises(NotFoundError) as exc:
        await svc.add_symbol("probe", "BTCUSDT:BINANCE", ["1h"], {})
    assert exc.value.error_code == "SYMBOL_NOT_TRACKED"


@pytest.mark.asyncio
async def test_add_symbol_404_when_unknown_template() -> None:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=True)

    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=tracked_repo)

    with pytest.raises(NotFoundError):
        await svc.add_symbol("does-not-exist", "BTCUSDT:BINANCE", ["1h"], {})
    sub_repo.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_symbol_rejects_an_unsorted_interval_list() -> None:
    sub_repo = MagicMock(add=AsyncMock())
    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=_tracked())
    with pytest.raises(DomainError) as exc:
        await svc.add_symbol("probe", "BTCUSDT:BINANCE", ["1h", "15m"], {})
    assert exc.value.error_code == "INVALID_INTERVALS"
    sub_repo.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_symbol_rejects_an_unknown_parameter() -> None:
    sub_repo = MagicMock(add=AsyncMock())
    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=_tracked())
    with pytest.raises(DomainError) as exc:
        await svc.add_symbol("probe", "BTCUSDT:BINANCE", ["1h"], {"x": 1})
    assert exc.value.error_code == "INVALID_PARAMETERS"
    sub_repo.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_symbol_returns_intervals_and_parameters() -> None:
    sub_repo = MagicMock(add=AsyncMock())
    svc = _cmd_svc(sub_repo=sub_repo, tracked_repo=_tracked())
    result = await svc.add_symbol("probe", "BTCUSDT:BINANCE", ["15m", "1h"], {"min_bars": 2})
    persisted = sub_repo.add.await_args.args[0]
    assert persisted.intervals == (Interval.MINUTE_15, Interval.HOUR_1)
    assert result["intervals"] == ["15m", "1h"]
    assert result["parameters"] == {"min_bars": 2}


# ---------------------------------------------------------------------------
# StrategyCommandService — edit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_404_when_the_subscription_is_missing() -> None:
    svc, sub_repo = _edit_svc(None)
    with pytest.raises(NotFoundError):
        await svc.edit("missing", ["1h"], {})
    sub_repo.update_config.assert_not_called()


@pytest.mark.asyncio
async def test_edit_refuses_a_running_subscription() -> None:
    svc, sub_repo = _edit_svc(_stored_sub(desired_state="running"))
    with pytest.raises(DomainError) as exc:
        await svc.edit("sub-1", ["1h"], {})
    assert (exc.value.error_code, exc.value.status_code) == ("SUBSCRIPTION_RUNNING", 409)
    sub_repo.update_config.assert_not_called()


@pytest.mark.asyncio
async def test_edit_refuses_an_open_position() -> None:
    sub = _stored_sub()
    svc, sub_repo = _edit_svc(sub, positions=[_open_position(str(sub.id))])
    with pytest.raises(DomainError) as exc:
        await svc.edit(str(sub.id), ["1h"], {})
    assert (exc.value.error_code, exc.value.status_code) == ("SUBSCRIPTION_HAS_EXPOSURE", 409)
    sub_repo.update_config.assert_not_called()


@pytest.mark.asyncio
async def test_edit_refuses_a_pending_order() -> None:
    sub = _stored_sub()
    other = MagicMock(subscription_id="another-sub")
    mine = MagicMock(subscription_id=str(sub.id))
    svc, sub_repo = _edit_svc(sub, pending=[other, mine])
    with pytest.raises(DomainError) as exc:
        await svc.edit(str(sub.id), ["1h"], {})
    assert (exc.value.error_code, exc.value.status_code) == ("SUBSCRIPTION_HAS_EXPOSURE", 409)
    sub_repo.update_config.assert_not_called()


@pytest.mark.asyncio
async def test_edit_writes_the_new_config() -> None:
    sub = _stored_sub()
    svc, sub_repo = _edit_svc(sub, pending=[MagicMock(subscription_id="another-sub")])
    result = await svc.edit(str(sub.id), ["15m", "1h"], {"min_bars": 2})
    written = sub_repo.update_config.await_args.args[0]
    assert written.id == sub.id
    assert written.intervals == (Interval.MINUTE_15, Interval.HOUR_1)
    assert written.parameters == {"min_bars": 2}
    assert result["intervals"] == ["15m", "1h"]
    assert result["parameters"] == {"min_bars": 2}


@pytest.mark.asyncio
async def test_edit_refuses_when_the_subscription_started_meanwhile() -> None:
    svc, _ = _edit_svc(_stored_sub(), matched=0)
    with pytest.raises(DomainError) as exc:
        await svc.edit("sub-1", ["1h"], {})
    assert exc.value.error_code == "SUBSCRIPTION_RUNNING"


# ---------------------------------------------------------------------------
# StrategyCommandService — remove_symbol / delete_strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_symbol_deletes_subscription() -> None:
    sub_repo = MagicMock()
    sub_repo.delete = AsyncMock()

    svc = _cmd_svc(sub_repo=sub_repo)
    await svc.remove_symbol("sub-1")

    sub_repo.delete.assert_awaited_once_with("sub-1")


# ---------------------------------------------------------------------------
# StrategyQueryService — get_all / get_one
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_returns_registry_codes() -> None:
    svc = _query_svc()
    result = await svc.get_all()
    assert isinstance(result, list)
    # STRATEGY_REGISTRY may have entries in test env; just check shape
    for entry in result:
        assert "strategy_code" in entry


@pytest.mark.asyncio
async def test_get_one_returns_none_for_unknown_code() -> None:
    svc = _query_svc()
    result = await svc.get_one("definitely-does-not-exist-xyz")
    assert result is None


@pytest.mark.asyncio
async def test_get_one_serves_the_default_parameters() -> None:
    result = await _query_svc().get_one("probe")
    assert result is not None
    assert result["parameters"] == {"min_bars": 0}


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
    sub = MagicMock()
    sub.id = "sub-abc"
    sub.strategy_code = "probe"
    sub.symbol = "BTCUSDT:BINANCE"
    sub.intervals = (Interval.HOUR_1, Interval.HOUR_4)
    sub.parameters = {"min_bars": 2}
    sub.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    sub.desired_state = "running"
    sub.actual_state = actual_state

    sub_repo = MagicMock()
    sub_repo.list_all = AsyncMock(return_value=[sub])

    svc = _query_svc(sub_repo=sub_repo)
    rows = await svc.list_symbols()

    assert len(rows) == 1
    assert rows[0]["is_running"] is expected_is_running
    assert rows[0]["desired_state"] == "running"
    assert rows[0]["actual_state"] == actual_state
    assert rows[0]["intervals"] == ["1h", "4h"]
    assert rows[0]["parameters"] == {"min_bars": 2}


@pytest.mark.asyncio
async def test_list_symbols_returns_empty_when_no_subs() -> None:
    sub_repo = MagicMock()
    sub_repo.list_all = AsyncMock(return_value=[])
    svc = _query_svc(sub_repo=sub_repo)
    assert await svc.list_symbols() == []


# ---------------------------------------------------------------------------
# StrategyQueryService — get_positions / get_trades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_positions_maps_open_positions() -> None:
    pos_repo = MagicMock()
    pos_repo.find_open_by_subscription = AsyncMock(return_value=[_open_position()])
    svc = _query_svc(position_repo=pos_repo)

    result = await svc.get_positions("sub-1")

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
    assert await svc.get_positions("sub-1") == []


@pytest.mark.asyncio
async def test_get_trades_maps_closed_positions() -> None:
    pos_repo = MagicMock()
    pos_repo.find_closed_by_subscription = AsyncMock(
        return_value=[_closed_position(1), _closed_position(2)]
    )
    svc = _query_svc(position_repo=pos_repo)

    result = await svc.get_trades("sub-1", 50)

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
    assert await svc.get_trades("sub-1") == []
