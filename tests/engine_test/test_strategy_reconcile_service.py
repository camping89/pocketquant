"""Unit tests for StrategyReconcileService — pure fakes, no DB/containers.

The reconcile loop owns instance lifecycle (load missing, unload orphan) AND
converges run-state: it diffs desired_state (Mongo) vs actual run-state (RAM),
calls start/stop, then mirrors observed actual back on drift. Tests pin: the
four-combo decision table, idempotency (no churn writes), per-sub error
isolation, cancel-safety, instance-lifecycle specifics (load missing / unload
orphan / anti-clobber against synthetic backtest ids and legacy 16-hex keys),
and the load-bearing invariant that injected backtest strategies (synthetic
id, no sub row) are never unloaded.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import RunState, Subscription
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)
_STRATEGY = "hitnrun2"  # must be in STRATEGY_REGISTRY


def _sub(
    *,
    symbol: str = "BTCUSDT:BINANCE",
    interval: Interval = Interval.MINUTE_5,
    strategy_code: str = _STRATEGY,
    desired: RunState = "stopped",
    actual: RunState = "stopped",
) -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code=strategy_code,
        symbol=symbol,
        interval=interval,
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
    """Records start/stop/load/unload; mutates fake instances for idempotency."""

    def __init__(self) -> None:
        self._instances: dict[str, _FakeStrategy] = {}
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.load_calls: list[str] = []
        self.unload_calls: list[str] = []
        self.start_raises_for: set[str] = set()

    def load(self, sub_id: str, running: bool) -> None:
        self._instances[sub_id] = _FakeStrategy(running)

    def get_strategy(self, sub_id: str):
        return self._instances.get(sub_id)

    def loaded_strategy_ids(self) -> list[str]:
        return list(self._instances.keys())

    async def load_strategy(self, config, strategy_class=None) -> str:
        self.load_calls.append(config.id)
        self._instances[config.id] = _FakeStrategy(running=False)
        return config.id

    async def unload_strategy(self, sub_id: str) -> None:
        self.unload_calls.append(sub_id)
        self._instances.pop(sub_id, None)

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
        self._subs: dict[str, Subscription] = {str(s.id): s for s in subs}
        self.actual_writes: list[tuple[str, str]] = []

    async def list_all(self) -> list[Subscription]:
        return list(self._subs.values())

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        self.actual_writes.append((sub_id, state))
        self._subs[sub_id] = replace(self._subs[sub_id], actual_state=state)
        return 1


def _service(subs, svc) -> tuple[StrategyReconcileService, _FakeSubRepo]:
    repo = _FakeSubRepo(subs)
    recon = StrategyReconcileService(repo, svc, interval_s=0.01)  # pyright: ignore[reportArgumentType]
    return recon, repo


@pytest.mark.asyncio
async def test_running_desired_stopped_actual_starts_and_writes() -> None:
    sub = _sub(desired="running", actual="stopped")
    sid = str(sub.id)
    svc = _FakeStrategyService()
    svc.load(sid, running=False)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == [sid]
    assert svc.stop_calls == []
    assert sub_repo.actual_writes == [(sid, "running")]


@pytest.mark.asyncio
async def test_stopped_desired_running_actual_stops_and_writes() -> None:
    sub = _sub(desired="stopped", actual="running")
    sid = str(sub.id)
    svc = _FakeStrategyService()
    svc.load(sid, running=True)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.stop_calls == [sid]
    assert svc.start_calls == []
    assert sub_repo.actual_writes == [(sid, "stopped")]


@pytest.mark.asyncio
async def test_stable_running_is_idempotent_no_calls_no_writes() -> None:
    sub = _sub(desired="running", actual="running")
    svc = _FakeStrategyService()
    svc.load(str(sub.id), running=True)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_stable_stopped_is_idempotent_no_calls_no_writes() -> None:
    sub = _sub(desired="stopped", actual="stopped")
    svc = _FakeStrategyService()
    svc.load(str(sub.id), running=False)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_missing_instance_desired_running_loads_then_starts() -> None:
    """Sub with valid template but no RAM instance: ensure-instance loads it,
    then converge starts it — the control-plane now owns lifecycle."""
    svc = _FakeStrategyService()  # no instance loaded yet
    sub = _sub(desired="running", actual="stopped")
    sid = str(sub.id)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == [sid]
    assert svc.start_calls == [sid]
    assert sub_repo.actual_writes == [(sid, "running")]


@pytest.mark.asyncio
async def test_unknown_template_skips_load_no_start() -> None:
    """Sub whose template is not in the registry is skipped (warn), not loaded,
    so it never starts and drifts to stopped."""
    svc = _FakeStrategyService()
    sub = Subscription(
        id=generate_id(),
        strategy_code="does-not-exist",
        symbol="BTCUSDT:BINANCE",
        interval=Interval.MINUTE_5,
        created_at=NOW,
        desired_state="running",
        actual_state="running",  # DB stale → must drift to stopped
    )
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []
    assert svc.start_calls == []
    assert sub_repo.actual_writes == [(str(sub.id), "stopped")]  # drift mirrored once


@pytest.mark.asyncio
async def test_per_sub_error_isolation_other_subs_still_reconcile() -> None:
    bad = _sub(desired="running", actual="stopped")
    good = _sub(desired="running", actual="stopped")
    bad_id, good_id = str(bad.id), str(good.id)
    svc = _FakeStrategyService()
    svc.load(bad_id, running=False)
    svc.load(good_id, running=False)
    svc.start_raises_for.add(bad_id)
    recon, sub_repo = _service([bad, good], svc)

    # Must not raise — bad sub failure is isolated, good sub still converges.
    await recon._reconcile()

    assert bad_id in svc.start_calls
    assert good_id in svc.start_calls
    # bad never reached the actual write (start raised); good did.
    assert (good_id, "running") in sub_repo.actual_writes
    assert (bad_id, "running") not in sub_repo.actual_writes


@pytest.mark.asyncio
async def test_run_loop_cancellation_propagates() -> None:
    svc = _FakeStrategyService()
    recon, _sub_repo = _service([], svc)

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
    sub = _sub(desired="stopped", actual="stopped")
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.stop_calls == []  # synthetic instance never stopped
    assert svc.start_calls == []
    assert sub_repo.actual_writes == []
    strategy = svc.get_strategy("backtest-synthetic-id")
    assert strategy is not None
    assert strategy.is_running is True


@pytest.mark.asyncio
async def test_loads_instance_for_sub_without_one() -> None:
    svc = _FakeStrategyService()  # no instances
    sub = _sub(desired="stopped")
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == [str(sub.id)]
    assert svc.get_strategy(str(sub.id)) is not None


@pytest.mark.asyncio
async def test_unknown_template_not_loaded() -> None:
    svc = _FakeStrategyService()
    sub = _sub(strategy_code="does-not-exist", desired="running")
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []
    assert svc.get_strategy(str(sub.id)) is None


@pytest.mark.asyncio
async def test_instance_with_live_sub_doc_not_unloaded() -> None:
    """A RAM instance whose subscription doc still exists is never an orphan."""
    sub = _sub()
    svc = _FakeStrategyService()
    svc.load(str(sub.id), running=False)
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.unload_calls == []
    assert svc.get_strategy(str(sub.id)) is not None


@pytest.mark.asyncio
async def test_unloads_orphan_instance_when_sub_deleted() -> None:
    """A RAM instance keyed by a uuid7 sub id, but with no sub doc, is unloaded.

    Locks the shape-guard against silent no-op: if the guard regex still
    matched only the legacy 16-hex shape, this unload would never fire and
    every removed subscription would leak a running instance forever.
    """
    sub = _sub()
    svc = _FakeStrategyService()
    svc.load(str(sub.id), running=True)  # instance present...
    recon, _sub_repo = _service([], svc)  # ...but NO subscription rows

    await recon._reconcile()

    assert svc.unload_calls == [str(sub.id)]
    assert svc.get_strategy(str(sub.id)) is None


@pytest.mark.asyncio
async def test_synthetic_backtest_instance_never_unloaded() -> None:
    """Anti-clobber: a synthetic backtest id (``{code}::bt::{sub_id}``) is not a
    subscription-id shape, so orphan-unload skips it even with zero sub rows."""
    sub = _sub()
    synthetic_id = f"{_STRATEGY}::bt::{sub.id}"
    svc = _FakeStrategyService()
    svc.load(synthetic_id, running=True)
    recon, _sub_repo = _service([], svc)  # no sub rows → orphan pass runs

    await recon._reconcile()

    assert svc.unload_calls == []
    inst = svc.get_strategy(synthetic_id)
    assert inst is not None and inst.is_running is True


@pytest.mark.asyncio
async def test_legacy_16hex_key_skipped_not_unloaded() -> None:
    """A leftover legacy 16-hex RAM key no longer matches the uuid7 shape, so
    orphan-unload ignores it (no unload, no crash). A restart clears such keys;
    until then they are simply not the reconcile loop's to manage."""
    svc = _FakeStrategyService()
    svc.load("eef73dffbd77a20b", running=True)  # old deterministic-id shape
    recon, _sub_repo = _service([], svc)

    await recon._reconcile()

    assert svc.unload_calls == []
    assert svc.get_strategy("eef73dffbd77a20b") is not None


@pytest.mark.asyncio
async def test_load_then_converge_running_in_one_tick() -> None:
    """A desired=running sub with no instance is loaded AND started in one tick."""
    svc = _FakeStrategyService()
    sub = _sub(desired="running", actual="stopped")
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    inst = svc.get_strategy(str(sub.id))
    assert inst is not None
    assert inst.is_running is True


@pytest.mark.asyncio
async def test_existing_instance_not_reloaded() -> None:
    svc = _FakeStrategyService()
    sub = _sub(desired="stopped")
    svc.load(str(sub.id), running=False)
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []  # already present — not reloaded
