from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import structlog

from pocketquant.app import roles
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.market_data.app_services import sync_jobs


class FakeLeaseRepo:
    def __init__(self, events: list[str] | None = None) -> None:
        self.entries: dict[str, tuple[str, datetime]] = {}
        self.releases: list[tuple[str, str]] = []
        self.acquires = 0
        self.fail_renew = False
        self._events = events

    async def acquire(self, name: str, owner: str, ttl_s: float) -> datetime | None:
        self.acquires += 1
        now = datetime.now(UTC)
        held = self.entries.get(name)
        if held and held[0] != owner and held[1] > now:
            return None
        if held and held[0] == owner and self.fail_renew:
            raise RuntimeError("renew failed")
        expires = now + timedelta(seconds=ttl_s)
        self.entries[name] = (owner, expires)
        return expires

    async def release(self, name: str, owner: str) -> None:
        self.releases.append((name, owner))
        if self._events is not None:
            self._events.append("release")
        held = self.entries.get(name)
        if held and held[0] == owner:
            self.entries[name] = (owner, datetime.now(UTC))


class _Calls:
    def __init__(self) -> None:
        self.acquired: list[datetime] = []
        self.lost = 0
        self.renewed: list[datetime] = []

    async def on_acquired(self, expires: datetime) -> None:
        self.acquired.append(expires)

    async def on_lost(self) -> None:
        self.lost += 1

    def on_renewed(self, expires: datetime) -> None:
        self.renewed.append(expires)


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name, value in {
        "LEASE_TTL_S": 1.0,
        "LEASE_RENEW_S": 0.1,
        "LEASE_RETRY_S": 0.1,
        "LEASE_POLL_S": 0.05,
        "ORDER_MARGIN_S": 0.5,
        "WORKER_STOP_S": 0.3,
    }.items():
        monkeypatch.setattr(roles, name, value)
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(roles, "logger", structlog.get_logger("test.roles"))
    yield


def _hold(
    repo: FakeLeaseRepo, owner: str, calls: _Calls, state: dict[str, str] | None = None
) -> tuple[asyncio.Task[None], dict[str, str]]:
    state = {} if state is None else state
    task = asyncio.create_task(
        roles.hold_lease(
            repo,  # type: ignore[arg-type]
            "trader",
            owner,
            state,
            calls.on_acquired,
            calls.on_lost,
            calls.on_renewed,
        )
    )
    return task, state


async def _stop(*tasks: asyncio.Task) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def test_only_one_of_two_contenders_acquires() -> None:
    repo, a, b = FakeLeaseRepo(), _Calls(), _Calls()
    task_a, state_a = _hold(repo, "a", a)
    task_b, state_b = _hold(repo, "b", b)
    await asyncio.sleep(0.3)

    assert len(a.acquired) + len(b.acquired) == 1
    assert {state_a["trader"], state_b["trader"]} == {"held", "standby"}
    await _stop(task_a, task_b)


async def test_waiting_contender_acquires_after_release() -> None:
    repo, a, b = FakeLeaseRepo(), _Calls(), _Calls()
    task_a, _ = _hold(repo, "a", a)
    await asyncio.sleep(0.05)
    task_b, _ = _hold(repo, "b", b)
    await asyncio.sleep(0.1)
    assert b.acquired == []

    await _stop(task_a)
    await repo.release("trader", "a")
    await asyncio.sleep(0.3)

    assert len(b.acquired) == 1
    await _stop(task_b)


async def test_renewal_taken_by_another_owner_calls_on_lost_once() -> None:
    repo, a = FakeLeaseRepo(), _Calls()
    with structlog.testing.capture_logs() as logs:
        task, state = _hold(repo, "a", a)
        await asyncio.sleep(0.05)
        repo.entries["trader"] = ("thief", datetime.now(UTC) + timedelta(seconds=60))
        await asyncio.sleep(0.3)

    assert a.lost == 1
    assert state["trader"] == "lost"
    assert len([e for e in logs if e["event"] == "lease.lost"]) == 1
    assert task.done()


async def test_failed_renewals_until_the_margin_call_on_lost_once() -> None:
    repo, a = FakeLeaseRepo(), _Calls()
    with structlog.testing.capture_logs() as logs:
        task, state = _hold(repo, "a", a)
        while not a.renewed:
            await asyncio.sleep(0.01)
        repo.fail_renew = True
        await asyncio.sleep(1.0)

    assert a.lost == 1
    assert state["trader"] == "lost"
    assert [e for e in logs if e["event"] == "lease.renew_failed"]
    assert task.done()


async def test_on_renewed_gets_each_new_expiry() -> None:
    repo, a = FakeLeaseRepo(), _Calls()
    task, _ = _hold(repo, "a", a)
    while len(a.renewed) < 3:
        await asyncio.sleep(0.01)

    first, second, third = a.renewed[:3]
    assert first < second < third
    await _stop(task)


async def test_state_is_held_only_after_on_acquired_returns() -> None:
    repo, a = FakeLeaseRepo(), _Calls()
    gate = asyncio.Event()

    async def slow_takeover(expires: datetime) -> None:
        await gate.wait()

    a.on_acquired = slow_takeover  # type: ignore[method-assign]
    task, state = _hold(repo, "a", a)
    await asyncio.sleep(0.1)
    assert state["trader"] == "standby"

    gate.set()
    await asyncio.sleep(0.1)
    assert state["trader"] == "held"
    await _stop(task)


async def test_failed_takeover_releases_and_runs_on_lost() -> None:
    repo, a = FakeLeaseRepo(), _Calls()

    async def broken_takeover(expires: datetime) -> None:
        raise RuntimeError("takeover failed")

    a.on_acquired = broken_takeover  # type: ignore[method-assign]
    with structlog.testing.capture_logs() as logs:
        task, state = _hold(repo, "a", a)
        await asyncio.sleep(0.05)
        acquires = repo.acquires
        await asyncio.sleep(0.3)

    [failed] = [e for e in logs if e["event"] == "lease.takeover_failed"]
    assert failed["log_level"] == "error"
    assert failed["exc_info"] is True
    assert state["trader"] == "lost"
    assert repo.releases == [("trader", "a")]
    assert a.lost == 1
    assert repo.acquires == acquires
    assert task.done()


async def test_slow_takeover_fails_before_the_order_margin() -> None:
    repo, a = FakeLeaseRepo(), _Calls()

    async def slow_takeover(expires: datetime) -> None:
        await asyncio.sleep(2.0)

    a.on_acquired = slow_takeover  # type: ignore[method-assign]
    with structlog.testing.capture_logs() as logs:
        task, _ = _hold(repo, "a", a)
        await asyncio.sleep(0.7)

    assert [e for e in logs if e["event"] == "lease.takeover_failed"]
    assert a.lost == 1
    assert task.done()


class _FakeScheduler:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def pause(self) -> None:
        self._events.append("pause")

    def shutdown(self, wait: bool = True) -> None:
        self._events.append("shutdown")


class _Container:
    def __init__(self, scheduler: _FakeScheduler, repo: FakeLeaseRepo) -> None:
        self._items = {JobScheduler: scheduler, LeaseRepository: repo}

    async def get(self, kind: type) -> object:
        return self._items[kind]


def _worker_app() -> SimpleNamespace:
    lease_task = asyncio.create_task(asyncio.sleep(10))
    return SimpleNamespace(
        state=SimpleNamespace(lease_state={"worker": "held"}, worker_lease_task=lease_task)
    )


async def test_worker_stop_waits_for_a_running_job_then_releases() -> None:
    events: list[str] = []
    container = _Container(_FakeScheduler(events), FakeLeaseRepo(events))
    app = _worker_app()

    async def job() -> None:
        await asyncio.sleep(0.1)
        events.append("job_done")

    running = asyncio.create_task(job())
    sync_jobs._RUNNING["job"] = running
    try:
        with structlog.testing.capture_logs() as logs:
            await roles.stop_worker(container, app, "w:1", get_current_time())  # type: ignore[arg-type]
    finally:
        sync_jobs._RUNNING.pop("job", None)

    assert events == ["pause", "job_done", "shutdown", "release"]
    assert len([e for e in logs if e["event"] == "worker.lease_released"]) == 1
    assert app.state.lease_state["worker"] == "released"


async def test_worker_stop_cancels_a_job_that_outlives_the_bound_then_releases() -> None:
    events: list[str] = []
    container = _Container(_FakeScheduler(events), FakeLeaseRepo(events))
    app = _worker_app()
    running = asyncio.create_task(asyncio.Event().wait())
    sync_jobs._RUNNING["job"] = running
    started = get_current_time()
    try:
        with structlog.testing.capture_logs() as logs:
            await roles.stop_worker(container, app, "w:1", started)  # type: ignore[arg-type]
        released_after = (get_current_time() - started).total_seconds()
    finally:
        sync_jobs._RUNNING.pop("job", None)
        await _stop(running)

    assert released_after < 0.5
    assert events[-1] == "release"
    assert running.cancelled()
    [cut] = [e for e in logs if e["event"] == "worker.jobs_interrupted"]
    assert cut["count"] == 1
