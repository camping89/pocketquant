"""ExnessBrokerAdapter open path: one open in flight per subscription, checks under one lock."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import structlog

from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.order import OrderStatus
from pocketquant.core.infra.brokers.exness import exness_broker_adapter as adapter_module
from pocketquant.core.infra.exness.exness_client import ExnessApiError
from tests.core_test.infra.brokers.exness.test_exness_broker_adapter import (
    _deal,
    _Harness,
    _holding_p1,
    _order,
)

# ── in-flight guard and the account open lock ───────────────────────────────


async def test_a_second_open_for_a_subscription_is_rejected_while_the_first_is_in_flight() -> None:
    h = await _Harness().start()
    first = await h.broker.submit_order(_order())
    assert first.status == OrderStatus.SUBMITTED

    second = await h.broker.submit_order(_order())

    assert second.status == OrderStatus.REJECTED
    assert second.error_message == "entry already in flight for subscription"
    assert len(h.client.ops("openPosition")) == 1
    other = await h.broker.submit_order(_order(subscription_id="sub2"))
    assert other.status == OrderStatus.SUBMITTED
    assert len(h.client.ops("openPosition")) == 2


async def test_check_sections_do_not_overlap() -> None:
    h = await _Harness().start()
    record: list[str] = []
    original = h.broker._loss_cap_reason

    async def slow_check() -> str | None:
        record.append("enter")
        await asyncio.sleep(0.05)
        record.append("exit")
        return await original()

    h.broker._loss_cap_reason = slow_check  # type: ignore[method-assign]

    await asyncio.gather(
        h.broker.submit_order(_order(subscription_id="sub1")),
        h.broker.submit_order(_order(subscription_id="sub2")),
    )

    assert record == ["enter", "exit", "enter", "exit"]


async def test_three_opens_send_concurrently() -> None:
    h = await _Harness().start()
    starts: list[float] = []

    async def slow_send(_kwargs: dict[str, Any]) -> None:
        starts.append(time.monotonic())
        await asyncio.sleep(0.5)

    h.client.on_order_call = slow_send
    began = time.monotonic()

    results = await asyncio.gather(
        *(h.broker.submit_order(_order(subscription_id=f"sub{i}")) for i in (1, 2, 3))
    )

    assert [r.status for r in results] == [OrderStatus.SUBMITTED] * 3
    assert max(starts) - min(starts) < 0.7
    assert time.monotonic() - began < 1.2


# ── cached balance and realized loss ────────────────────────────────────────


def _close_event() -> dict[str, Any]:
    return {
        "status": "success",
        "payload": {
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
    }


async def test_fresh_caches_make_one_call_per_open() -> None:
    h = await _Harness().start()
    await h.broker._refresh_caches()
    h.client.calls.clear()

    await h.broker.get_balance()
    await h.broker.submit_order(_order())

    assert [op for op, _ in h.client.calls] == ["openPosition"]


async def test_a_broker_close_makes_the_next_open_read_deals_first() -> None:
    h, _ = await _holding_p1()
    await h.broker._refresh_caches()
    await h.event("transaction_event", **_close_event())
    h.client.calls.clear()

    await h.broker.submit_order(_order(subscription_id="sub2"))

    assert [op for op, _ in h.client.calls] == ["getDealsHistory", "openPosition"]


async def test_a_failed_deals_read_after_a_close_refuses_the_open() -> None:
    h, _ = await _holding_p1()
    await h.broker._refresh_caches()
    await h.event("transaction_event", **_close_event())
    h.client.deals_error = ExnessApiError(500, "X", "y")
    h.client.calls.clear()

    result = await h.broker.submit_order(_order(subscription_id="sub2"))

    assert result.status == OrderStatus.REJECTED
    assert (result.error_message or "").startswith("daily loss check failed")
    assert h.client.ops("openPosition") == []


async def test_an_old_balance_cache_is_read_again() -> None:
    h = await _Harness().start()
    await h.broker._refresh_caches()
    cache = h.broker._balance_cache
    assert cache is not None
    h.broker._balance_cache = (cache[0] - 91, cache[1])
    h.client.calls.clear()

    await h.broker.get_balance()

    assert [op for op, _ in h.client.calls] == ["getTradingStateSnapshot"]


async def test_a_close_during_the_deals_read_keeps_the_cache_stale() -> None:
    h, _ = await _holding_p1()
    original = h.broker._realized_today

    async def close_while_reading() -> float:
        await h.event("transaction_event", **_close_event())
        return await original()

    h.broker._realized_today = close_while_reading  # type: ignore[method-assign]

    await h.broker._refresh_caches()

    assert h.broker._realized is None


# ── deadline ────────────────────────────────────────────────────────────────

T = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


async def test_an_order_whose_deadline_passes_inside_the_open_lock_is_not_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(adapter_module, "logger", structlog.get_logger("test.exness_open_path"))
    h = await _Harness().start()
    original = h.broker._loss_cap_reason

    async def late_check() -> str | None:
        set_simulation_time(T + timedelta(seconds=2))
        return await original()

    h.broker._loss_cap_reason = late_check  # type: ignore[method-assign]
    try:
        set_simulation_time(T)
        with structlog.testing.capture_logs() as logs:
            result = await h.broker.submit_order(_order(), deadline=T + timedelta(seconds=1))
    finally:
        clear_simulation_time()

    assert result.status == OrderStatus.REJECTED
    assert result.error_message == "order deadline passed"
    assert h.client.ops("openPosition") == []
    assert h.broker._inflight == {}
    rejected = [e for e in logs if e["event"] == "exness.order_rejected_presubmit"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "deadline"


async def test_an_order_inside_its_deadline_is_sent() -> None:
    h = await _Harness().start()
    try:
        set_simulation_time(T)
        result = await h.broker.submit_order(_order(), deadline=T + timedelta(seconds=60))
    finally:
        clear_simulation_time()

    assert result.status == OrderStatus.SUBMITTED
    assert len(h.client.ops("openPosition")) == 1
