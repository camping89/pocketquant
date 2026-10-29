"""ExnessBrokerAdapter: safety rules, event mapping, trade emission and recovery.

The fake client answers with the recorded shapes in
``tests/core_test/infra/exness/fixtures`` (conditions, deals envelope, snapshot,
events acknowledgement); close deals follow the spec schema inside that envelope.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import structlog

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, PositionSide, TradeClosedEvent
from pocketquant.core.infra.brokers.exness import exness_broker_adapter as adapter_module
from pocketquant.core.infra.brokers.exness.exness_broker_adapter import ExnessBrokerAdapter
from pocketquant.core.infra.brokers.exness.exness_safeguards import Safeguards
from pocketquant.core.infra.exness import exness_stream
from pocketquant.core.infra.exness.exness_client import ExnessApiError
from tests.core_test.infra.exness.test_exness_stream import _FakeSocket

FIXTURES = Path(__file__).parents[2] / "exness" / "fixtures"
SYMBOL = "XAUUSD:EXNESS"
API_KEY = "api-key-must-never-be-logged"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _deal(kind: str, **fields: Any) -> dict[str, Any]:
    deal: dict[str, Any] = {"deal_id": f"d-{kind}", "type": kind, **fields}
    deal.setdefault("create_time", "2026-10-14T10:00:00+00:00")
    return deal


def _page(deals: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    page = copy.deepcopy(_fixture("deals"))
    page["items"] = [{"event_time": d["create_time"], "deal": d} for d in deals]
    page["has_more"] = next_cursor is not None
    if next_cursor:
        page["next_cursor"] = next_cursor
    return page


class _FakeClient:
    """Routes ``call`` by operation id; records every call."""

    def __init__(self) -> None:
        self.account_id = "acc"
        self.api_key = API_KEY
        self.is_configured = True
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.deal_pages: list[dict[str, Any]] = [_page([])]
        self.snapshot = _fixture("snapshot")
        self.operation_status: dict[str, Any] = {"status": "pending"}
        self.order_error: ExnessApiError | None = None
        self.deals_error: ExnessApiError | None = None
        self.on_order_call: Any = None

    async def conditions(self, instrument: str) -> dict[str, Any]:
        return _fixture(f"conditions_{instrument}")

    async def deals_window_days(self) -> int:
        return 29

    async def ws_url(self, path: str) -> str:
        return f"wss://ap-x.exness.com{path}"

    def sign_ws_headers(self, path: str) -> dict[str, str]:
        return {}

    async def call(self, op: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((op, kwargs))
        if op == "getDealsHistory":
            if self.deals_error:
                raise self.deals_error
            cursor = kwargs["params"].get("cursor")
            return self.deal_pages[1 if cursor else 0]
        if op == "openPosition":
            if self.on_order_call:
                await self.on_order_call(kwargs)
            if self.order_error:
                raise self.order_error
            key = kwargs["idempotency_key"]
            return {"operation_id": "op1", "client_request_id": key, "status": "accepted"}
        if op == "getTradingStateSnapshot":
            return copy.deepcopy(self.snapshot)
        if op == "getOperationStatus":
            return self.operation_status
        if op == "getAccountDetails":
            return _fixture("account")
        raise AssertionError(op)

    def ops(self, name: str) -> list[dict[str, Any]]:
        return [kw for op, kw in self.calls if op == name]


class _Repo:
    def __init__(self, positions: list[PositionAggregate] | None = None) -> None:
        self.positions = positions or []
        # Set to park a snapshot rebuild inside its first await.
        self.gate: asyncio.Event | None = None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        if self.gate is not None:
            await self.gate.wait()
        return self.positions


class _PauseStore:
    """Stands in for the stored entry pause."""

    def __init__(self) -> None:
        self.paused: bool = False
        self.error: Exception | None = None

    async def load_entries_paused(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.paused


class _Harness:
    def __init__(
        self, cap: float | None = 50.0, repo: _Repo | None = None, max_lots: float | None = None
    ) -> None:
        self.client = _FakeClient()
        self.bus = EventBus()
        self.fills: list[OrderFilledEvent] = []
        self.bus.subscribe(OrderFilledEvent, lambda e: self.fills.append(e))
        self.safeguards = Safeguards(
            live_trading=True,
            daily_loss_cap=cap,
            max_lots=max_lots,
            leverage=1.0,
            risk_per_trade=0.02,
        )
        self.pause = _PauseStore()
        self.broker = ExnessBrokerAdapter(
            self.client,  # type: ignore[arg-type]
            self.bus,
            repo or _Repo(),  # type: ignore[arg-type]
            self.safeguards,
            self.pause,  # type: ignore[arg-type]
        )
        self.results: list[OrderResult] = []
        self.trades: list[TradeClosedEvent] = []

    async def start(self, snapshot: bool = True) -> _Harness:
        await self.broker.subscribe_order_updates(self.results.append)
        await self.broker.subscribe_trades(self.trades.append)
        if snapshot:
            await self.event("trading_state_snapshot", payload=self.client.snapshot)
        return self

    async def event(self, event_type: str, **fields: Any) -> None:
        await self.broker._on_event({"event_type": event_type, **fields})

    async def entry_fill(self, order: OrderAggregate) -> None:
        await self.event(
            "transaction_event",
            operation_id="op1",
            client_request_id=str(order.id),
            status="success",
            payload={"deals": [_open_deal()]},
        )


def _open_deal() -> dict[str, Any]:
    return _deal("open", volume="0.01", price="2345.100", position_id="p1", direction="buy")


def _order(
    side: OrderSide = OrderSide.BUY,
    quantity: float = 1.0,
    order_type: OrderType = OrderType.MARKET,
    sl_price: float | None = 2300.12345,
    subscription_id: str = "sub1",
) -> OrderAggregate:
    return OrderAggregate.create(
        subscription_id=subscription_id,
        symbol=SYMBOL,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=2345.0,
        sl_price=sl_price,
        tp_price=None,
    )


async def _drain() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _no_watch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the operation watcher from outliving a test unless a test drives it."""
    monkeypatch.setattr(adapter_module, "_STATUS_POLLS", 0)
    monkeypatch.setattr(adapter_module, "_FILL_TIMEOUT_S", 3600)


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(adapter_module, "logger", structlog.get_logger("test.exness_broker"))


# ── rejections before any order call ────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "cap", "snapshot", "reason"),
    [
        ({"order_type": OrderType.LIMIT}, 50.0, True, "market orders only"),
        ({"sl_price": None}, 50.0, True, "stop loss required"),
        ({}, None, True, "EXNESS_DAILY_LOSS_CAP not set"),
        ({}, 50.0, False, "awaiting trading snapshot reconciliation"),
        ({"quantity": 7.9}, 50.0, True, "quantity not normalized to the exness lot grid"),
    ],
)
async def test_presubmit_rejections_make_no_order_call(
    kwargs: dict[str, Any], cap: float | None, snapshot: bool, reason: str
) -> None:
    h = await _Harness(cap=cap).start(snapshot=snapshot)

    result = await h.broker.submit_order(_order(**kwargs))

    assert result.status == OrderStatus.REJECTED
    assert reason in (result.error_message or "")
    assert h.client.ops("openPosition") == []


async def test_unmapped_instrument_blocks_orders_on_it() -> None:
    h = await _Harness().start()
    h.broker._held_unmapped.add("XAUUSD")

    result = await h.broker.submit_order(_order())

    assert result.error_message == "unmapped exness position on XAUUSD"
    assert h.client.ops("openPosition") == []


async def test_inflight_count_counts_opens_and_acks_not_a_pending_snapshot() -> None:
    h = await _Harness().start()
    assert h.broker.inflight_count == 0

    h.broker._inflight["r1"] = SimpleNamespace(order=_order(), instrument="XAUUSD")  # type: ignore[assignment]
    h.broker._pending_ack.add("r2")
    h.broker._needs_snapshot = True

    assert h.broker.inflight_count == 2


# ── daily loss cap ──────────────────────────────────────────────────────────


def _loss_pages(commission: str = "2", dividend: bool = True) -> list[dict[str, Any]]:
    page1 = [
        _deal("close", profit={"amount": "-40", "currency": "USD"}, commission=commission),
        _deal("balance", profit={"amount": "1000", "currency": "USD"}),
    ]
    page2 = [_deal("close", profit={"amount": "-5", "currency": "USD"})]
    if dividend:
        page2.append(_deal("dividend", profit={"amount": "-4", "currency": "USD"}))
    return [_page(page1, next_cursor="c2"), _page(page2)]


@pytest.mark.parametrize("commission", ["2", "-2"])
async def test_loss_cap_reached_across_pages(commission: str) -> None:
    h = await _Harness(cap=50.0).start()
    h.client.deal_pages = _loss_pages(commission)

    assert await h.broker._realized_today() == -51.0
    result = await h.broker.submit_order(_order())

    assert result.error_message == "daily loss cap reached"
    assert h.client.ops("openPosition") == []
    assert h.client.ops("getDealsHistory")[1]["params"] == {"cursor": "c2", "limit": 200}


@pytest.mark.parametrize("commission", ["2", "-2"])
async def test_loss_under_cap_sends_order(commission: str) -> None:
    h = await _Harness(cap=50.0).start()
    h.client.deal_pages = _loss_pages(commission, dividend=False)

    assert await h.broker._realized_today() == -47.0
    result = await h.broker.submit_order(_order())

    assert result.status == OrderStatus.SUBMITTED
    assert len(h.client.ops("openPosition")) == 1


async def test_withdrawal_is_not_a_loss() -> None:
    h = await _Harness(cap=50.0).start()
    h.client.deal_pages = [_page([_deal("balance", profit={"amount": "-1000", "currency": "USD"})])]

    assert await h.broker._realized_today() == 0.0
    assert (await h.broker.submit_order(_order())).status == OrderStatus.SUBMITTED


async def test_loss_check_fails_closed_on_api_error() -> None:
    h = await _Harness(cap=50.0).start()
    h.client.deals_error = ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")

    result = await h.broker.submit_order(_order())

    assert result.error_message == "daily loss check failed: REQUEST_RATE_LIMIT"
    assert h.client.ops("openPosition") == []


async def test_deals_from_is_clamped_to_history_window() -> None:
    h = _Harness()

    async for _ in h.broker._deals(since=datetime.now(UTC) - timedelta(days=60)):
        pass

    sent = datetime.fromisoformat(h.client.ops("getDealsHistory")[0]["params"]["from"])
    assert abs(sent - (datetime.now(UTC) - timedelta(days=29))) < timedelta(seconds=5)


# ── sizing ──────────────────────────────────────────────────────────────────


async def test_normalize_quantity_clamps_and_rejects_below_minimum() -> None:
    h = _Harness()
    with structlog.testing.capture_logs() as logs:
        clamped = await h.broker.normalize_quantity(SYMBOL, 7.9)
        below = await h.broker.normalize_quantity(SYMBOL, 0.5)

    assert clamped == 1.0
    assert below is None
    events = [e["event"] for e in logs]
    assert "exness.lots_clamped" in events
    assert "exness.order_rejected_presubmit" in events


@pytest.mark.parametrize(
    ("max_lots", "units", "volume"), [(None, 1.0, "0.01"), (0.05, 5.0, "0.05")]
)
async def test_safeguards_max_lots_clamps_and_unset_sends_the_minimum_lot(
    max_lots: float | None, units: float, volume: str
) -> None:
    h = await _Harness(max_lots=max_lots).start()

    assert await h.broker.normalize_quantity(SYMBOL, 500.0) == units
    await h.broker.submit_order(_order(quantity=units))

    assert h.client.ops("openPosition")[0]["json_body"]["volume"] == volume


async def test_open_request_formats_stop_loss_to_point_digits() -> None:
    h = await _Harness().start()

    await h.broker.submit_order(_order())

    body = h.client.ops("openPosition")[0]["json_body"]
    assert body == {
        "instrument": "XAUUSD",
        "side": "buy",
        "volume": "0.01",
        "stop_loss_price": "2300.123",
    }


# ── entry pause ─────────────────────────────────────────────────────────────


async def test_paused_open_is_rejected_before_any_venue_call() -> None:
    h = await _Harness().start()
    h.pause.paused = True

    with structlog.testing.capture_logs() as logs:
        result = await h.broker.submit_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert result.error_message == "entries paused"
    assert h.client.calls == []
    paused = [e for e in logs if e.get("reason") == "entries_paused"]
    assert paused[0]["subscription_id"] == "sub1"
    assert paused[0]["symbol"] == SYMBOL


async def test_resumed_open_is_sent() -> None:
    h = await _Harness().start()
    h.pause.paused = True
    h.pause.paused = False

    result = await h.broker.submit_order(_order())

    assert result.status == OrderStatus.SUBMITTED
    assert len(h.client.ops("openPosition")) == 1


async def test_an_unreadable_pause_refuses_the_open() -> None:
    h = await _Harness().start()
    h.pause.error = RuntimeError("mongo down")

    with structlog.testing.capture_logs() as logs:
        result = await h.broker.submit_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert result.error_message == "entries pause unreadable"
    assert h.client.calls == []
    rejected = [e for e in logs if e["event"] == "exness.order_rejected_presubmit"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "pause_unreadable"


# ── events ──────────────────────────────────────────────────────────────────


async def test_entry_fill_delivered_once() -> None:
    h = await _Harness().start()
    order = _order()
    await h.broker.submit_order(order)

    await h.entry_fill(order)
    await h.entry_fill(order)

    assert len(h.results) == 1
    fill = h.results[0]
    assert fill.status == OrderStatus.FILLED
    assert fill.filled_quantity == 1.0
    assert fill.filled_price == 2345.1


# The fill reaches the stream while the order call runs; the call then succeeds or fails.
ACK_OUTCOMES = pytest.mark.parametrize(
    "ack_error", [None, ExnessApiError(0, "TRANSPORT", "x")], ids=["ack", "ack_lost"]
)


@ACK_OUTCOMES
async def test_fill_before_ack_is_delivered_once_after_submit_returns(
    ack_error: ExnessApiError | None,
) -> None:
    h = await _Harness().start()
    order = _order()

    async def fill_during_call(kwargs: dict[str, Any]) -> None:
        assert str(order.id) in h.broker._pending_ack
        await h.entry_fill(order)

    h.client.on_order_call = fill_during_call
    h.client.order_error = ack_error
    result = await h.broker.submit_order(order)

    assert result.status == OrderStatus.SUBMITTED
    assert h.results == []
    await _drain()
    assert [r.status for r in h.results] == [OrderStatus.FILLED]
    assert "p1" in h.broker._positions
    assert not h.broker._needs_snapshot


async def test_async_rejection_maps_to_cancelled() -> None:
    h = await _Harness().start()
    order = _order()
    await h.broker.submit_order(order)

    await h.event(
        "transaction_event",
        operation_id="op1",
        client_request_id=str(order.id),
        status="rejected",
        error_code=5006,
        error_message="TRADING_RULE_INSUFFICIENT_MARGIN",
        payload={},
    )

    assert len(h.results) == 1
    assert h.results[0].status == OrderStatus.CANCELLED
    assert "TRADING_RULE_INSUFFICIENT_MARGIN" in (h.results[0].error_message or "")


async def _holding_p1() -> tuple[_Harness, OrderAggregate]:
    h = await _Harness().start()
    order = _order()
    await h.broker.submit_order(order)
    await h.entry_fill(order)
    return h, order


async def test_broker_side_close_publishes_fill_then_trade() -> None:
    h, _ = await _holding_p1()

    await h.event(
        "transaction_event",
        status="success",
        payload={
            "orders": [{"position_id": "p1", "order_type": "sltp"}],
            "deals": [
                _deal(
                    "close",
                    volume="0.01",
                    price="2341.600",
                    position_id="p1",
                    direction="sell",
                    profit={"amount": "-3.5", "currency": "USD"},
                    commission="0.2",
                )
            ],
        },
    )

    assert len(h.fills) == 1
    assert h.fills[0].side == OrderSide.SELL
    assert h.fills[0].subscription_id == "sub1"
    assert len(h.trades) == 1
    trade = h.trades[0]
    assert (trade.pnl, trade.commission, trade.entry_price) == (-3.5, 0.2, 2345.1)
    assert "p1" not in h.broker._positions


async def test_opposite_order_is_rejected_and_keeps_the_position() -> None:
    h, _ = await _holding_p1()
    calls = len(h.client.calls)

    result = await h.broker.submit_order(_order(side=OrderSide.SELL))

    assert result.status == OrderStatus.REJECTED
    assert result.error_message == "position already open for subscription"
    assert len(h.client.calls) == calls
    assert h.broker._held_for("sub1") is not None


async def test_same_direction_order_is_rejected() -> None:
    h, _ = await _holding_p1()

    result = await h.broker.submit_order(_order())

    assert result.error_message == "position already open for subscription"


async def test_partial_broker_close_reduces_the_hold() -> None:
    h, _ = await _holding_p1()
    h.broker._positions["p1"].units = 2.0
    partial = _deal(
        "close",
        volume="0.01",
        price="2341.600",
        position_id="p1",
        profit={"amount": "-3.5", "currency": "USD"},
    )

    await h.event("transaction_event", status="success", payload={"deals": [partial]})

    assert h.fills[0].filled_quantity == 1.0
    assert h.trades[0].quantity == 1.0
    assert h.broker._positions["p1"].units == 1.0


async def test_fill_for_dropped_request_blocks_the_instrument() -> None:
    h = await _Harness().start()
    deal = {**_open_deal(), "instrument": "XAUUSD"}

    await h.event(
        "transaction_event",
        client_request_id="lost-ack-order",
        status="success",
        payload={"deals": [deal]},
    )

    assert h.broker._held_unmapped == {"XAUUSD"}
    assert h.broker._needs_snapshot
    assert h.results == []


# ── recovery ────────────────────────────────────────────────────────────────


async def test_missed_fill_recovered_from_operation_status_and_deals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter_module, "_FILL_TIMEOUT_S", 0)
    monkeypatch.setattr(adapter_module, "_STATUS_POLLS", 4)
    h = await _Harness().start()
    h.client.operation_status = {"operation_id": "op1", "status": "confirmed"}
    h.client.deal_pages = [_page([])]
    order = _order()
    await h.broker.submit_order(order)
    h.client.deal_pages = [_page([_open_deal()])]
    # The venue's snapshot holds the new position; the repo (no position service here) does not.
    h.client.snapshot["positions"] = [_snapshot_position(position_id="p1")]

    await _drain()

    assert [r.status for r in h.results] == [OrderStatus.FILLED]
    assert "p1" in h.broker._positions


@pytest.mark.parametrize(
    "error",
    [ExnessApiError(0, "TRANSPORT", "x"), ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")],
)
async def test_lost_ack_blocks_opens_until_the_snapshot_it_schedules(
    error: ExnessApiError,
) -> None:
    h = await _Harness().start()
    h.client.order_error = error

    result = await h.broker.submit_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert len(h.client.ops("openPosition")) == 1
    h.client.order_error = None
    blocked = await h.broker.submit_order(_order())
    assert blocked.error_message == "awaiting trading snapshot reconciliation"
    await _drain()
    assert len(h.client.ops("getTradingStateSnapshot")) == 1
    assert (await h.broker.submit_order(_order())).status == OrderStatus.SUBMITTED


async def test_unresolved_operation_reopens_the_gate_after_a_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter_module, "_FILL_TIMEOUT_S", 0)
    monkeypatch.setattr(adapter_module, "_STATUS_POLLS", 1)
    h = await _Harness().start()
    order = _order()
    await h.broker.submit_order(order)

    await _drain()

    assert len(h.client.ops("getOperationStatus")) == 1
    assert str(order.id) not in h.broker._inflight
    assert len(h.client.ops("getTradingStateSnapshot")) == 1
    second = await h.broker.submit_order(_order(subscription_id="sub2"))
    assert second.status == OrderStatus.SUBMITTED


async def _park_snapshot_rebuild(h: _Harness, repo: _Repo) -> asyncio.Task[None]:
    """Start a snapshot rebuild and leave it suspended inside ``find_open``."""
    repo.gate = asyncio.Event()
    rebuild = asyncio.create_task(h.broker._reconcile_snapshot())
    await _drain()
    return rebuild


async def test_fill_during_snapshot_rebuild_is_kept() -> None:
    repo = _Repo()
    h = await _Harness(repo=repo).start()
    order = _order()
    await h.broker.submit_order(order)
    rebuild = await _park_snapshot_rebuild(h, repo)

    fill = asyncio.create_task(h.entry_fill(order))
    await _drain()
    assert repo.gate is not None
    repo.gate.set()
    await asyncio.gather(rebuild, fill)

    assert "p1" in h.broker._positions
    assert [r.status for r in h.results] == [OrderStatus.FILLED]


async def test_broker_close_during_snapshot_rebuild_stays_closed() -> None:
    repo = _Repo()
    h = await _Harness(repo=repo).start()
    order = _order()
    await h.broker.submit_order(order)
    await h.entry_fill(order)
    # The position service saved the row; the venue snapshot is read before the stop loss hits.
    repo.positions = [_repo_position()]
    h.client.snapshot["positions"] = [_snapshot_position(position_id="p1")]
    rebuild = await _park_snapshot_rebuild(h, repo)

    stop = _deal("close", volume="0.01", price="2341.600", position_id="p1")
    close = asyncio.create_task(
        h.event("transaction_event", status="success", payload={"deals": [stop]})
    )
    await _drain()
    assert repo.gate is not None
    repo.gate.set()
    await asyncio.gather(rebuild, close)

    assert "p1" not in h.broker._positions
    assert len(h.trades) == 1


def _repo_position(
    symbol: str = SYMBOL, side: PositionSide = PositionSide.LONG
) -> PositionAggregate:
    return PositionAggregate.open(
        subscription_id="sub1",
        symbol=symbol,
        side=side,
        entry_price=2345.1,
        quantity=1.0,
        opened_at=datetime.now(UTC) - timedelta(hours=2),
    )


def _snapshot_position(direction: str = "buy", position_id: str = "p9") -> dict[str, Any]:
    return {
        "position_id": position_id,
        "direction": direction,
        "instrument": "XAUUSD",
        "volume": "0.01",
        "open_price": "2345.100",
    }


async def test_restart_maps_matching_position() -> None:
    h = _Harness(repo=_Repo([_repo_position()]))
    h.client.snapshot["positions"] = [_snapshot_position()]

    await h.start()

    assert h.broker._positions["p9"].subscription_id == "sub1"
    assert h.broker._held_unmapped == set()


async def test_restart_unmatched_snapshot_position_is_held_unmapped() -> None:
    h = _Harness()
    h.client.snapshot["positions"] = [_snapshot_position()]

    await h.start()

    assert h.broker._held_unmapped == {"XAUUSD"}


async def test_reconnect_keeps_own_position_whose_repo_row_was_saved() -> None:
    repo = _Repo()
    h = await _Harness(repo=repo).start()
    order = _order()
    await h.broker.submit_order(order)
    await h.entry_fill(order)
    # The position service saved the row from the fill; the venue snapshot holds p1.
    repo.positions = [_repo_position()]
    h.client.snapshot["positions"] = [_snapshot_position(position_id="p1")]
    h.client.deal_pages = [_page([_deal("close", price="2339.000", position_id="p0")])]

    await h.broker._reconcile_snapshot()

    assert "p1" in h.broker._positions
    assert h.broker._held_unmapped == set()
    assert h.fills == []
    assert h.trades == []


async def test_restart_closes_repo_position_missing_from_snapshot() -> None:
    h = _Harness(repo=_Repo([_repo_position()]))
    close = _deal(
        "close", price="2340.000", position_id="p9", profit={"amount": "-5.1", "currency": "USD"}
    )
    h.client.deal_pages = [_page([_deal("close", price="2339.000", position_id="p8"), close])]

    await h.start()

    assert len(h.fills) == 1
    assert h.fills[0].side == OrderSide.SELL
    assert h.fills[0].filled_price == 2340.0
    assert len(h.trades) == 1
    assert h.trades[0].pnl == -5.1


async def test_replayed_reconnect_delivers_the_fill_of_an_inflight_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recorded frames through ``ExnessStream``: snapshot, order, reconnect, snapshot, fill."""
    monkeypatch.setattr(exness_stream, "_BACKOFF_INITIAL_S", 0)
    ack = json.dumps(_fixture("events_snapshot"))
    snapshot = {"event_type": "trading_state_snapshot", "payload": _fixture("snapshot")}
    scripts: list[list[str]] = [[ack, json.dumps(snapshot)], []]
    resume = asyncio.Event()

    async def connect(url: str, **kwargs: Any) -> _FakeSocket:
        if len(scripts) == 1:
            await resume.wait()
        if not scripts:
            await asyncio.Event().wait()
        return _FakeSocket(scripts.pop(0))

    monkeypatch.setattr(exness_stream.websockets, "connect", connect)
    h = await _Harness().start(snapshot=False)
    await h.broker.connect()
    await _drain()
    assert h.broker._snapshot_ready
    order = _order()
    assert (await h.broker.submit_order(order)).status == OrderStatus.SUBMITTED

    # The venue filled the order while the stream was down; its snapshot already holds p1.
    h.client.snapshot["positions"] = [_snapshot_position(position_id="p1")]
    fill = {
        "event_type": "transaction_event",
        "operation_id": "op1",
        "client_request_id": str(order.id),
        "status": "success",
        "payload": {"deals": [_open_deal()]},
    }
    snapshot["payload"] = h.client.snapshot
    scripts[0] += [ack, json.dumps(snapshot), json.dumps(fill)]
    resume.set()
    await _drain()
    await h.broker.disconnect()

    assert [r.status for r in h.results] == [OrderStatus.FILLED]
    assert h.broker._positions["p1"].subscription_id == "sub1"
    assert h.broker._held_unmapped == set()
    assert h.broker._snapshot_ready
    assert not h.broker._needs_snapshot


# ── listener robustness and secrets ─────────────────────────────────────────


async def test_raising_callback_does_not_kill_listener() -> None:
    h = await _Harness().start()
    h.broker._order_callbacks.insert(0, AsyncMock(side_effect=RuntimeError("boom")))
    first, second = _order(), _order(subscription_id="sub2")
    await h.broker.submit_order(first)
    await h.entry_fill(first)

    await h.broker.submit_order(second)
    await h.event(
        "transaction_event",
        client_request_id=str(second.id),
        status="rejected",
        error_message="x",
        payload={},
    )
    await h.broker._on_event(_fixture("events_snapshot"))

    assert [r.status for r in h.results] == [OrderStatus.FILLED, OrderStatus.CANCELLED]


async def test_logs_never_contain_api_key() -> None:
    with structlog.testing.capture_logs() as logs:
        h, _ = await _holding_p1()
        h.client.order_error = ExnessApiError(0, "TRANSPORT", "x")
        await h.broker.submit_order(_order(subscription_id="sub2"))

    assert logs
    assert all(API_KEY not in str(entry) for entry in logs)
