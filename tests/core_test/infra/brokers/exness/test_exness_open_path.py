"""ExnessBrokerAdapter open path: one open in flight per subscription, checks under one lock."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pocketquant.core.domain.order import OrderStatus
from tests.core_test.infra.brokers.exness.test_exness_broker_adapter import (
    _Harness,
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
