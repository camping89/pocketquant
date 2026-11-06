from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog.testing

from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.infra.exness.exness_client import ExnessApiError
from tests.core_test.infra.brokers.exness.test_exness_broker_adapter import (
    SYMBOL,
    _deal,
    _drain,
    _Harness,
    _holding_p1,
    _order,
    _Repo,
    _venue_p1,
)

# ── close_position ──────────────────────────────────────────────────────────


def _close_event() -> dict[str, Any]:
    return {
        "status": "success",
        "payload": {
            "orders": [{"position_id": "p1", "order_type": "market"}],
            "deals": [
                _deal(
                    "close",
                    volume="0.01",
                    price="2341.600",
                    position_id="p1",
                    direction="sell",
                    profit={"amount": "-3.5", "currency": "USD"},
                )
            ],
        },
    }


async def test_close_sends_one_delete_for_the_held_position() -> None:
    h, _ = await _holding_p1()

    assert await h.broker.close_position("sub1", SYMBOL, reason="strategy_exit") is True

    (sent,) = h.client.ops("closePosition")
    assert sent["path_params"] == {"position_id": "p1"}
    assert sent.get("json_body") is None
    assert "p1" in h.broker._positions
    await h.event("transaction_event", **_close_event())
    assert len(h.fills) == 1
    assert len(h.trades) == 1
    # Our reason wins over the venue order type of a close we requested.
    assert h.trades[0].exit_reason == "strategy_exit"
    assert "p1" not in h.broker._positions


async def test_close_without_a_position_sends_nothing() -> None:
    h = await _Harness().start()

    assert await h.broker.close_position("sub1", SYMBOL, reason="strategy_exit") is False
    assert h.client.ops("closePosition") == []


async def test_a_failed_close_keeps_the_position() -> None:
    h, _ = await _holding_p1()
    h.client.order_error = ExnessApiError(429, "REQUEST_RATE_LIMIT", "limited")

    with structlog.testing.capture_logs() as logs:
        closed = await h.broker.close_position("sub1", SYMBOL, reason="strategy_exit")

    assert closed is False
    assert "p1" in h.broker._positions
    failed = [e for e in logs if e["event"] == "exness.close_failed"]
    assert len(failed) == 1
    assert failed[0]["log_level"] == "warning"


async def test_a_close_is_sent_while_entries_are_paused() -> None:
    h, _ = await _holding_p1()
    h.pause.paused = True

    assert await h.broker.close_position("sub1", SYMBOL, reason="manual") is True
    assert len(h.client.ops("closePosition")) == 1


async def test_a_close_past_its_deadline_is_not_sent() -> None:
    h, _ = await _holding_p1()
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    set_simulation_time(now)
    try:
        closed = await h.broker.close_position(
            "sub1", SYMBOL, reason="strategy_exit", deadline=now - timedelta(seconds=1)
        )
    finally:
        clear_simulation_time()

    assert closed is False
    assert h.client.ops("closePosition") == []


# ── pending stop ────────────────────────────────────────────────────────────


def _stop(subscription_id: str = "sub1") -> OrderAggregate:
    return _order(
        order_type=OrderType.STOP_MARKET, stop_price=2350.12345, subscription_id=subscription_id
    )


def _placed(order: OrderAggregate, venue_id: str = "v1") -> dict[str, Any]:
    return {
        "operation_id": "op1",
        "client_request_id": str(order.id),
        "status": "success",
        "payload": {
            "orders": [
                {"order_id": venue_id, "order_type": "stop", "state": "placed"},
                {"order_id": "v-sltp", "order_type": "sltp", "state": "placed"},
            ]
        },
    }


def _stop_fill(order_id: str = "v1", instrument: str = "XAUUSD") -> dict[str, Any]:
    deal = _deal(
        "open",
        volume="0.01",
        price="2350.200",
        position_id="p1",
        direction="buy",
        order_id=order_id,
        instrument=instrument,
    )
    return {"status": "success", "payload": {"deals": [deal]}}


async def _resting() -> tuple[_Harness, OrderAggregate]:
    h = await _Harness().start()
    order = _stop()
    result = await h.broker.submit_order(order)
    assert result.status == OrderStatus.SUBMITTED
    # OrderAppService records the ack id on the order it passed in.
    order.submit(result.broker_order_id)
    await h.event("transaction_event", **_placed(order))
    return h, order


async def test_a_stop_order_is_sent_as_one_pending_order() -> None:
    h = await _Harness().start()

    result = await h.broker.submit_order(_stop())

    assert result.status == OrderStatus.SUBMITTED
    assert h.client.ops("openPosition") == []
    (sent,) = h.client.ops("placePendingOrder")
    assert sent["json_body"] == {
        "instrument": "XAUUSD",
        "side": "buy",
        "volume": "0.01",
        "type": "stop",
        "price": "2350.123",
        "stop_loss_price": "2300.123",
    }


async def test_a_placed_stop_rests_without_a_fill() -> None:
    h, order = await _resting()

    assert h.results == []
    assert h.broker.inflight_count == 0
    assert h.broker._parked[str(order.id)][1] == "v1"


async def test_a_resting_stop_fill_is_delivered_once() -> None:
    h, order = await _resting()

    await h.event("transaction_event", **_stop_fill())
    await h.event("transaction_event", **_stop_fill())

    assert [(r.order_id, r.status) for r in h.results] == [(str(order.id), OrderStatus.FILLED)]
    assert h.results[0].filled_price == 2350.2
    assert h.broker._held_for("sub1") is not None
    assert h.broker._parked == {}


async def test_cancel_sends_one_cancel_for_the_resting_stop() -> None:
    h, _ = await _resting()

    assert await h.broker.cancel_order("op1") is True
    assert await h.broker.cancel_order("op1") is False

    (sent,) = h.client.ops("cancelPendingOrder")
    assert sent["path_params"] == {"order_id": "v1"}
    assert sent["idempotency_key"]


async def test_cancel_after_a_restart_sends_nothing() -> None:
    h = await _Harness().start()

    assert await h.broker.cancel_order("op1") is False
    assert h.client.ops("cancelPendingOrder") == []


async def test_a_failed_cancel_keeps_the_stop_parked() -> None:
    h, order = await _resting()
    h.client.order_error = ExnessApiError(0, "TRANSPORT", "boom")

    with structlog.testing.capture_logs() as logs:
        assert await h.broker.cancel_order("op1") is False

    assert str(order.id) in h.broker._parked
    assert "exness.cancel_failed" in [e["event"] for e in logs]


async def test_a_second_stop_is_rejected_while_one_rests() -> None:
    h, _ = await _resting()

    result = await h.broker.submit_order(_stop())

    assert result.status == OrderStatus.REJECTED
    assert result.error_message == "pending order already resting for subscription"
    assert len(h.client.ops("placePendingOrder")) == 1


async def test_an_unlinked_open_deal_on_a_resting_instrument_blocks_it() -> None:
    h, order = await _resting()
    h.client.snapshot["orders"] = [{"order_id": "v1", "order_type": "stop", "state": "placed"}]
    h.client.snapshot["positions"] = [_venue_p1()]

    with structlog.testing.capture_logs() as logs:
        await h.event("transaction_event", **_stop_fill(order_id="other"))
        assert h.broker._needs_snapshot
        await _drain()

    assert h.results == []
    assert h.broker._held_unmapped == {"XAUUSD"}
    assert str(order.id) in h.broker._parked
    errors = [e for e in logs if e["event"] == "exness.unattributed_open_deal"]
    assert len(errors) == 1
    assert errors[0]["log_level"] == "error"


async def test_a_venue_order_we_do_not_track_blocks_the_instrument() -> None:
    h = await _Harness().start()
    snapshot = {
        **h.client.snapshot,
        "orders": [
            {"order_id": "x9", "order_type": "stop", "instrument": "XAUUSD", "state": "placed"},
            {"order_id": "x8", "order_type": "sltp", "position_id": "p7", "state": "placed"},
        ],
    }

    with structlog.testing.capture_logs() as logs:
        await h.event("trading_state_snapshot", payload=snapshot)

    assert h.broker._held_unmapped == {"XAUUSD"}
    errors = [e for e in logs if e["event"] == "exness.pending_order_unmapped"]
    assert len(errors) == 1
    assert errors[0]["log_level"] == "error"
    result = await h.broker.submit_order(_order(side=OrderSide.SELL))
    assert result.error_message == "unmapped exness position on XAUUSD"


async def test_a_parked_stop_is_not_unmapped_by_a_snapshot() -> None:
    h, _ = await _resting()
    snapshot = {
        **h.client.snapshot,
        "orders": [{"order_id": "v1", "order_type": "stop", "instrument": "XAUUSD"}],
    }

    await h.event("trading_state_snapshot", payload=snapshot)

    assert h.broker._held_unmapped == set()


def _resting_v1() -> list[dict[str, Any]]:
    return [{"order_id": "v1", "order_type": "stop", "state": "placed", "instrument": "XAUUSD"}]


# ── ack and stream order ────────────────────────────────────────────────────


async def test_a_placement_event_before_the_ack_parks_the_stop() -> None:
    h = await _Harness().start()
    order = _stop()

    async def placed_first(_kwargs: dict[str, Any]) -> None:
        await h.event("transaction_event", **_placed(order))

    h.client.on_order_call = placed_first
    result = await h.broker.submit_order(order)

    assert result.status == OrderStatus.SUBMITTED
    assert str(order.id) in h.broker._parked
    assert h.broker._acked_at == {}
    assert h.results == []


async def test_a_stop_parked_before_an_http_error_closes_the_gate() -> None:
    h = await _Harness().start()
    order = _stop()

    async def placed_first(_kwargs: dict[str, Any]) -> None:
        await h.event("transaction_event", **_placed(order))

    h.client.on_order_call = placed_first
    h.client.order_error = ExnessApiError(500, "SYSTEM_INTERNAL_ERROR", "boom")
    h.client.snapshot["orders"] = _resting_v1()
    result = await h.broker.submit_order(order)

    assert result.status == OrderStatus.REJECTED
    assert h.broker._parked == {}
    assert h.broker._needs_snapshot
    await _drain()
    assert h.broker._held_unmapped == {"XAUUSD"}


async def test_a_placement_event_after_an_http_error_closes_the_gate() -> None:
    h = await _Harness().start()
    order = _stop()
    h.client.order_error = ExnessApiError(500, "SYSTEM_INTERNAL_ERROR", "boom")
    assert (await h.broker.submit_order(order)).status == OrderStatus.REJECTED
    h.client.snapshot["orders"] = _resting_v1()

    with structlog.testing.capture_logs() as logs:
        await h.event("transaction_event", **_placed(order))

    assert "exness.unattributed_pending_order" in [e["event"] for e in logs]
    assert h.broker._needs_snapshot
    await _drain()
    assert h.broker._held_unmapped == {"XAUUSD"}


# ── cancel and close results on the stream ──────────────────────────────────


async def test_a_fill_after_the_cancel_was_accepted_closes_the_gate() -> None:
    h, _ = await _resting()
    assert await h.broker.cancel_order("op1") is True
    h.client.snapshot["positions"] = [_venue_p1()]

    await h.event("transaction_event", **_stop_fill())

    assert h.results == []
    assert h.broker._needs_snapshot
    await _drain()
    assert h.broker._held_unmapped == {"XAUUSD"}


async def test_a_cancel_the_venue_refuses_later_blocks_the_instrument() -> None:
    h, _ = await _resting()
    assert await h.broker.cancel_order("op1") is True
    key = h.client.ops("cancelPendingOrder")[0]["idempotency_key"]
    h.client.snapshot["orders"] = _resting_v1()

    with structlog.testing.capture_logs() as logs:
        await h.event("transaction_event", client_request_id=key, status="rejected", error_code="X")

    assert "exness.async_op_failed" in [e["event"] for e in logs]
    await _drain()
    assert h.broker._held_unmapped == {"XAUUSD"}


async def test_a_close_the_venue_refuses_later_keeps_the_position() -> None:
    h, _ = await _holding_p1()
    assert await h.broker.close_position("sub1", SYMBOL, reason="strategy_exit") is True
    key = h.client.ops("closePosition")[0]["idempotency_key"]
    h.client.snapshot["positions"] = [_venue_p1()]

    with structlog.testing.capture_logs() as logs:
        await h.event(
            "transaction_event",
            client_request_id=key,
            status="rejected",
            error_code="MARKET_SESSION_CLOSED",
        )
    await _drain()

    failed = [e for e in logs if e["event"] == "exness.async_op_failed"]
    assert failed[0]["error_code"] == "MARKET_SESSION_CLOSED"
    assert "p1" in h.broker._positions

    # A later venue SL close keeps the venue's reason, not the refused close's.
    venue_close = _close_event()
    venue_close["payload"]["orders"][0]["order_type"] = "sltp"
    await h.event("transaction_event", **venue_close)
    assert [t.exit_reason for t in h.trades] == ["sltp"]


# ── snapshot ────────────────────────────────────────────────────────────────


async def test_a_stop_gone_from_the_snapshot_is_released() -> None:
    h, order = await _resting()

    await h.event("trading_state_snapshot", payload=h.client.snapshot)

    assert [(r.order_id, r.status) for r in h.results] == [(str(order.id), OrderStatus.CANCELLED)]
    assert h.broker._parked == {}
    assert (await h.broker.submit_order(_stop())).status == OrderStatus.SUBMITTED


async def test_a_stop_parked_after_the_snapshot_read_is_kept() -> None:
    h, order = await _resting()

    async with h.broker._state_lock:
        await h.broker._on_snapshot(h.client.snapshot, known=set())

    assert str(order.id) in h.broker._parked
    assert h.results == []


async def test_parking_reruns_a_snapshot_that_waited_for_the_stop() -> None:
    h = await _Harness().start()
    order = _stop()
    await h.broker.submit_order(order)
    h.broker._snapshot_ready = False
    await h.event("trading_state_snapshot", payload=h.client.snapshot)
    assert h.broker._snapshot_ready is False
    h.client.snapshot["orders"] = _resting_v1()

    await h.event("transaction_event", **_placed(order))

    assert h.broker._snapshot_ready is True
    assert str(order.id) in h.broker._parked


async def test_a_placement_without_a_stop_order_is_dropped() -> None:
    h = await _Harness().start()
    order = _stop()
    await h.broker.submit_order(order)
    h.client.snapshot["orders"] = _resting_v1()

    await h.event(
        "transaction_event",
        operation_id="op1",
        client_request_id=str(order.id),
        status="success",
        payload={"orders": []},
    )

    assert [(r.order_id, r.status) for r in h.results] == [(str(order.id), OrderStatus.CANCELLED)]
    assert h.broker._held_unmapped == {"XAUUSD"}


async def test_a_manual_position_never_takes_a_subscription_row() -> None:
    row = PositionAggregate.open(
        subscription_id="sub1",
        symbol=SYMBOL,
        side=PositionSide.LONG,
        entry_price=2345.1,
        quantity=1.0,
    )
    h = await _Harness(repo=_Repo([row])).start(snapshot=False)
    await h.event(
        "trading_state_snapshot", payload={**h.client.snapshot, "positions": [_venue_p1()]}
    )
    assert set(h.broker._positions) == {"p1"}
    manual = {**_venue_p1(), "position_id": "p2"}

    await h.event(
        "trading_state_snapshot",
        payload={**h.client.snapshot, "positions": [manual, _venue_p1()]},
    )

    assert set(h.broker._positions) == {"p1"}
    assert h.broker._held_unmapped == {"XAUUSD"}
