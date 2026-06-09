"""Unit tests for StrategyReconcileService — pure fakes, no DB/containers.

The reconcile loop diffs desired_state (Mongo) vs actual run-state (RAM) and
converges by calling start/stop, then mirrors observed actual back to Mongo on
drift. Tests pin: the four-combo decision table, idempotency (no churn writes),
missing-instance warn path, per-sub error isolation, cancel-safety, and the
load-bearing invariant that injected backtest strategies (no sub row) are
untouched.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import RunState, Subscription
from pocketquant.execution.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)


def _sub(sub_id: str, desired: RunState, actual: RunState) -> Subscription:
    return Subscription(
        id=sub_id,
        strategy_code="hitnrun2",
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_5,
        created_at=NOW,
        desired_state=desired,
        actual_state=actual,
    )


class _FakeStrategy:
    def __init__(self, running: bool) -> None:
        self._running = running

    @property
    def is_running(self) -> bool:
        return self._running


class _FakeStrategyService:
    """Records start/stop calls; mutates fake instances so reconcile is idempotent."""

    def __init__(self) -> None:
        self._instances: dict[str, _FakeStrategy] = {}
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.start_raises_for: set[str] = set()

    def load(self, sub_id: str, running: bool) -> None:
        self._instances[sub_id] = _FakeStrategy(running)

    def get_strategy(self, sub_id: str):
        return self._instances.get(sub_id)

    async def start_strategy(self, sub_id: str) -> None:
        self.start_calls.append(sub_id)
        if sub_id in self.start_raises_for:
            raise RuntimeError(f"broker down: {sub_id}")
        inst = self._instances.get(sub_id)
        if inst:
            inst._running = True

    async def stop_strategy(self, sub_id: str) -> None:
        self.stop_calls.append(sub_id)
        inst = self._instances.get(sub_id)
        if inst:
            inst._running = False


class _FakeSubRepo:
    def __init__(self, subs: list[Subscription]) -> None:
        self._subs: dict[str, Subscription] = {s.id: s for s in subs}
        self.actual_writes: list[tuple[str, str]] = []

    async def list_all(self) -> list[Subscription]:
        return list(self._subs.values())

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        self.actual_writes.append((sub_id, state))
        self._subs[sub_id] = replace(self._subs[sub_id], actual_state=state)
        return 1


def _service(subs, svc) -> StrategyReconcileService:
    return StrategyReconcileService(_FakeSubRepo(subs), svc, interval_s=0.01)


@pytest.mark.asyncio
async def test_running_desired_stopped_actual_starts_and_writes() -> None:
    svc = _FakeStrategyService()
    svc.load("s1", running=False)
    sub = _sub("s1", desired="running", actual="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == ["s1"]
    assert svc.stop_calls == []
    assert recon._sub_repo.actual_writes == [("s1", "running")]


@pytest.mark.asyncio
async def test_stopped_desired_running_actual_stops_and_writes() -> None:
    svc = _FakeStrategyService()
    svc.load("s1", running=True)
    sub = _sub("s1", desired="stopped", actual="running")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.stop_calls == ["s1"]
    assert svc.start_calls == []
    assert recon._sub_repo.actual_writes == [("s1", "stopped")]


@pytest.mark.asyncio
async def test_stable_running_is_idempotent_no_calls_no_writes() -> None:
    svc = _FakeStrategyService()
    svc.load("s1", running=True)
    sub = _sub("s1", desired="running", actual="running")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert recon._sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_stable_stopped_is_idempotent_no_calls_no_writes() -> None:
    svc = _FakeStrategyService()
    svc.load("s1", running=False)
    sub = _sub("s1", desired="stopped", actual="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert recon._sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_missing_instance_desired_running_warns_no_start_persists_stopped() -> None:
    svc = _FakeStrategyService()  # no instance loaded for s1
    sub = _sub("s1", desired="running", actual="running")  # DB stale → must drift to stopped
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert recon._sub_repo.actual_writes == [("s1", "stopped")]


@pytest.mark.asyncio
async def test_missing_instance_legacy_stopped_actual_no_write_no_churn() -> None:
    """Legacy sub desired=running, actual already stopped, no RAM instance:
    no drift → no per-tick write (and the warn would not fire every tick)."""
    svc = _FakeStrategyService()  # no instance loaded for s1
    sub = _sub("s1", desired="running", actual="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert recon._sub_repo.actual_writes == []  # idempotent: nothing to write


@pytest.mark.asyncio
async def test_per_sub_error_isolation_other_subs_still_reconcile() -> None:
    svc = _FakeStrategyService()
    svc.load("bad", running=False)
    svc.load("good", running=False)
    svc.start_raises_for.add("bad")
    subs = [
        _sub("bad", desired="running", actual="stopped"),
        _sub("good", desired="running", actual="stopped"),
    ]
    recon = _service(subs, svc)

    # Must not raise — bad sub failure is isolated, good sub still converges.
    await recon._reconcile()

    assert "bad" in svc.start_calls
    assert "good" in svc.start_calls
    # bad never reached the actual write (start raised); good did.
    assert ("good", "running") in recon._sub_repo.actual_writes
    assert ("bad", "running") not in recon._sub_repo.actual_writes


@pytest.mark.asyncio
async def test_run_loop_cancellation_propagates() -> None:
    svc = _FakeStrategyService()
    recon = _service([], svc)

    task = asyncio.create_task(recon.run())
    await asyncio.sleep(0.05)  # let it spin a few ticks
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_injected_backtest_strategy_without_sub_row_is_untouched() -> None:
    """Load-bearing: reconcile is subscription-driven. A running instance under a
    synthetic id with NO subscription row must be neither stopped nor written."""
    svc = _FakeStrategyService()
    svc.load("backtest-synthetic-id", running=True)  # injected, no sub row
    sub = _sub("real-sub", desired="stopped", actual="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.stop_calls == []  # synthetic instance never stopped
    assert svc.start_calls == []
    assert recon._sub_repo.actual_writes == []
    assert svc.get_strategy("backtest-synthetic-id").is_running is True
