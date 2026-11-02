# Load-bearing invariant: injected backtest strategies (synthetic id, no sub row) are never
# unloaded.

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import structlog

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import RunState, Subscription
from pocketquant.engine.live import strategy_reconcile_app_service as reconcile_module
from pocketquant.engine.live.strategy_reconcile_app_service import (
    StrategyReconcileAppService,
)

pytestmark = pytest.mark.usefixtures("probe_registry")


@pytest.fixture(autouse=True)
def _fresh_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(reconcile_module, "logger", structlog.get_logger("test.reconcile"))

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)
_STRATEGY = "probe"  # must be in STRATEGY_REGISTRY


def _sub(
    *,
    symbol: str = "BTCUSDT:BINANCE",
    intervals: tuple[Interval, ...] = (Interval.MINUTE_5,),
    strategy_code: str = _STRATEGY,
    desired: RunState = "stopped",
    actual: RunState = "stopped",
) -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code=strategy_code,
        symbol=symbol,
        intervals=intervals,
        created_at=NOW,
        desired_state=desired,
        actual_state=actual,
    )


class _FakeStrategy:
    def __init__(self, running: bool, config) -> None:
        self._running = running
        self.config = config

    @property
    def is_running(self) -> bool:
        return self._running


class _FakeStrategyService:
    def __init__(self) -> None:
        self._instances: dict[str, _FakeStrategy] = {}
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.load_calls: list[str] = []
        self.unload_calls: list[str] = []
        self.start_raises_for: set[str] = set()
        self.manual_outcome: str | None = "accepted"
        self.manual_calls: list[tuple[str, str]] = []

    def load(self, sub: Subscription, running: bool) -> None:
        config = SimpleNamespace(
            intervals=[i.value for i in sub.intervals], parameters=dict(sub.parameters)
        )
        self._instances[str(sub.id)] = _FakeStrategy(running, config)

    def get_strategy(self, sub_id: str):
        return self._instances.get(sub_id)

    def loaded_strategy_ids(self) -> list[str]:
        return list(self._instances.keys())

    async def load_strategy(self, config, strategy_class=None) -> str:
        self.load_calls.append(config.id)
        self._instances[config.id] = _FakeStrategy(running=False, config=config)
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

    async def manual_action(self, sub_id: str, action: str) -> str | None:
        self.manual_calls.append((sub_id, action))
        return self.manual_outcome


class _FakeSubRepo:
    def __init__(self, subs: list[Subscription]) -> None:
        self._subs: dict[str, Subscription] = {str(s.id): s for s in subs}
        self.actual_writes: list[tuple[str, str]] = []
        self.cleared: list[tuple[str, str, str]] = []

    async def list_all(self) -> list[Subscription]:
        return list(self._subs.values())

    async def update_actual_state(self, sub_id: str, state: RunState) -> int:
        self.actual_writes.append((sub_id, state))
        self._subs[sub_id] = replace(self._subs[sub_id], actual_state=state)
        return 1

    async def clear_action(self, sub_id: str, action: str, outcome: str) -> int:
        self.cleared.append((sub_id, action, outcome))
        self._subs[sub_id] = replace(self._subs[sub_id], manual_action=None)
        return 1


def _service(subs, svc) -> tuple[StrategyReconcileAppService, _FakeSubRepo]:
    repo = _FakeSubRepo(subs)
    recon = StrategyReconcileAppService(repo, svc, interval_s=0.01)  # pyright: ignore[reportArgumentType]
    return recon, repo


@pytest.mark.asyncio
async def test_running_desired_stopped_actual_starts_and_writes() -> None:
    sub = _sub(desired="running", actual="stopped")
    sid = str(sub.id)
    svc = _FakeStrategyService()
    svc.load(sub, running=False)
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
    svc.load(sub, running=True)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.stop_calls == [sid]
    assert svc.start_calls == []
    assert sub_repo.actual_writes == [(sid, "stopped")]


@pytest.mark.asyncio
async def test_stable_running_is_idempotent_no_calls_no_writes() -> None:
    sub = _sub(desired="running", actual="running")
    svc = _FakeStrategyService()
    svc.load(sub, running=True)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_stable_stopped_is_idempotent_no_calls_no_writes() -> None:
    sub = _sub(desired="stopped", actual="stopped")
    svc = _FakeStrategyService()
    svc.load(sub, running=False)
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.start_calls == []
    assert svc.stop_calls == []
    assert sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_missing_instance_desired_running_loads_then_starts() -> None:
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
    svc = _FakeStrategyService()
    sub = Subscription(
        id=generate_id(),
        strategy_code="does-not-exist",
        symbol="BTCUSDT:BINANCE",
        intervals=(Interval.MINUTE_5,),
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
    svc.load(bad, running=False)
    svc.load(good, running=False)
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
    sub = _sub()
    svc = _FakeStrategyService()
    svc.load(sub, running=False)
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.unload_calls == []
    assert svc.get_strategy(str(sub.id)) is not None


# If the shape guard matched only the legacy 16-hex id, this unload would never fire and
# every removed subscription would leak a running instance forever.
@pytest.mark.asyncio
async def test_unloads_orphan_instance_when_sub_deleted() -> None:
    sub = _sub()
    svc = _FakeStrategyService()
    svc.load(sub, running=True)  # instance present...
    recon, _sub_repo = _service([], svc)  # ...but NO subscription rows

    await recon._reconcile()

    assert svc.unload_calls == [str(sub.id)]
    assert svc.get_strategy(str(sub.id)) is None


@pytest.mark.asyncio
async def test_load_then_converge_running_in_one_tick() -> None:
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
    svc.load(sub, running=False)
    recon, _sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.load_calls == []  # already present — not reloaded


@pytest.mark.asyncio
async def test_bootstrap_starts_running_subscriptions_without_writing_actual_state() -> None:
    svc = _FakeStrategyService()
    running, stopped = _sub(desired="running"), _sub(desired="stopped")
    recon, sub_repo = _service([running, stopped], svc)

    await recon.bootstrap()

    started, idle = svc.get_strategy(str(running.id)), svc.get_strategy(str(stopped.id))
    assert started is not None and started.is_running
    assert idle is not None and not idle.is_running
    assert sub_repo.actual_writes == []


@pytest.mark.asyncio
async def test_an_edited_stopped_subscription_reloads_its_config() -> None:
    loaded = _sub(desired="stopped")
    loaded = replace(loaded, parameters={"min_bars": 0})
    sid = str(loaded.id)
    svc = _FakeStrategyService()
    svc.load(loaded, running=False)
    recon, _ = _service([replace(loaded, parameters={"min_bars": 2})], svc)

    await recon._reconcile()

    assert svc.unload_calls == [sid]
    assert svc.load_calls == [sid]
    assert svc.get_strategy(sid).config.parameters == {"min_bars": 2}


@pytest.mark.asyncio
async def test_a_running_subscription_is_never_reloaded() -> None:
    loaded = replace(_sub(desired="running", actual="running"), parameters={"min_bars": 0})
    svc = _FakeStrategyService()
    svc.load(loaded, running=True)
    recon, _ = _service([replace(loaded, parameters={"min_bars": 2})], svc)

    await recon._reconcile()

    assert svc.unload_calls == []
    assert svc.load_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["accepted", "rejected:close_failed"])
async def test_an_attempted_action_is_cleared_with_its_outcome(outcome: str) -> None:
    sub = replace(_sub(desired="running", actual="running"), manual_action="close")
    sid = str(sub.id)
    svc = _FakeStrategyService()
    svc.load(sub, running=True)
    svc.manual_outcome = outcome
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.manual_calls == [(sid, "close")]
    assert sub_repo.cleared == [(sid, "close", outcome)]


@pytest.mark.asyncio
async def test_a_queued_action_stays_for_the_next_tick() -> None:
    sub = replace(_sub(desired="running", actual="running"), manual_action="cancel")
    svc = _FakeStrategyService()
    svc.load(sub, running=True)
    svc.manual_outcome = None
    recon, sub_repo = _service([sub], svc)

    await recon._reconcile()

    assert svc.manual_calls == [(str(sub.id), "cancel")]
    assert sub_repo.cleared == []


@pytest.mark.asyncio
async def test_an_action_without_an_instance_is_cleared_with_a_warning() -> None:
    sub = replace(_sub(strategy_code="no_such_template"), manual_action="close")
    sid = str(sub.id)
    svc = _FakeStrategyService()
    recon, sub_repo = _service([sub], svc)

    with structlog.testing.capture_logs() as logs:
        await recon._reconcile()

    assert svc.manual_calls == []
    assert sub_repo.cleared == [(sid, "close", "rejected:not_loaded")]
    dropped = [e for e in logs if e["event"] == "reconcile.manual_action_dropped"]
    assert [e["log_level"] for e in dropped] == ["warning"]
