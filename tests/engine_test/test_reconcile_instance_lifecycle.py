"""Reconcile instance lifecycle — load missing, unload orphan, anti-clobber.

After the app/bff split the reconcile loop owns RAM instance lifecycle: it loads
an instance for every subscription that lacks one, unloads instances whose
subscription doc is gone, and converges run-state — all in one tick. The
load-bearing safety property: synthetic backtest instances (id shape
``{code}::bt::{sub_id}``, no sub row) are NEVER unloaded.

Pure fakes, no DB — the lifecycle logic is RAM-keys vs Mongo-keys, independent
of persistence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

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
    interval: Interval = Interval.HOUR_1,
    strategy_code: str = _STRATEGY,
    desired: RunState = "stopped",
    actual: RunState = "stopped",
) -> Subscription:
    sub_id = Subscription.deterministic_id(strategy_code, symbol, interval)
    return Subscription(
        id=sub_id,
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
    def __init__(self) -> None:
        self._instances: dict[str, _FakeStrategy] = {}
        self.load_calls: list[str] = []
        self.unload_calls: list[str] = []

    def inject(self, key: str, running: bool) -> None:
        self._instances[key] = _FakeStrategy(running)

    def get_strategy(self, key: str):
        return self._instances.get(key)

    def loaded_strategy_ids(self) -> list[str]:
        return list(self._instances.keys())

    async def load_strategy(self, config, strategy_class=None) -> str:
        self.load_calls.append(config.id)
        self._instances[config.id] = _FakeStrategy(running=False)
        return config.id

    async def unload_strategy(self, key: str) -> None:
        self.unload_calls.append(key)
        self._instances.pop(key, None)

    async def start_strategy(self, key: str) -> None:
        inst = self._instances.get(key)
        if inst:
            inst._running = True

    async def stop_strategy(self, key: str) -> None:
        inst = self._instances.get(key)
        if inst:
            inst._running = False


class _FakeSubRepo:
    def __init__(self, subs: list[Subscription]) -> None:
        self._subs: dict[str, Subscription] = {s.id: s for s in subs}

    async def list_all(self) -> list[Subscription]:
        return list(self._subs.values())

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        self._subs[sub_id] = replace(self._subs[sub_id], actual_state=state)
        return 1


def _service(subs, svc) -> StrategyReconcileService:
    return StrategyReconcileService(_FakeSubRepo(subs), svc, interval_s=0.01)


@pytest.mark.asyncio
async def test_loads_instance_for_sub_without_one() -> None:
    svc = _FakeStrategyService()  # no instances
    sub = _sub(desired="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == [sub.id]
    assert svc.get_strategy(sub.id) is not None


@pytest.mark.asyncio
async def test_unknown_template_not_loaded() -> None:
    svc = _FakeStrategyService()
    sub = _sub(strategy_code="does-not-exist", desired="running")
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []
    assert svc.get_strategy(sub.id) is None


@pytest.mark.asyncio
async def test_unloads_orphan_instance_when_sub_deleted() -> None:
    """A RAM instance keyed like a sub id, but with no sub doc, is unloaded."""
    sub = _sub()
    svc = _FakeStrategyService()
    svc.inject(sub.id, running=True)  # instance present...
    recon = _service([], svc)  # ...but NO subscription rows

    await recon._reconcile()

    assert svc.unload_calls == [sub.id]
    assert svc.get_strategy(sub.id) is None


@pytest.mark.asyncio
async def test_synthetic_backtest_instance_never_unloaded() -> None:
    """Anti-clobber: a synthetic backtest id (``{code}::bt::{sub_id}``) is not a
    subscription-id shape, so orphan-unload skips it even with zero sub rows."""
    sub = _sub()
    synthetic_id = f"{_STRATEGY}::bt::{sub.id}"
    svc = _FakeStrategyService()
    svc.inject(synthetic_id, running=True)
    recon = _service([], svc)  # no sub rows → orphan pass runs

    await recon._reconcile()

    assert svc.unload_calls == []
    inst = svc.get_strategy(synthetic_id)
    assert inst is not None and inst.is_running is True


@pytest.mark.asyncio
async def test_load_then_converge_running_in_one_tick() -> None:
    """A desired=running sub with no instance is loaded AND started in one tick."""
    svc = _FakeStrategyService()
    sub = _sub(desired="running", actual="stopped")
    recon = _service([sub], svc)

    await recon._reconcile()

    inst = svc.get_strategy(sub.id)
    assert inst is not None
    assert inst.is_running is True


@pytest.mark.asyncio
async def test_existing_instance_not_reloaded() -> None:
    svc = _FakeStrategyService()
    sub = _sub(desired="stopped")
    svc.inject(sub.id, running=False)
    recon = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []  # already present — not reloaded
