from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import structlog

from pocketquant.app import roles
from pocketquant.app.di import create_container
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.scheduling import scheduler as scheduler_module
from pocketquant.core.infra.scheduling.scheduler import JobScheduler

pytestmark = pytest.mark.integration


async def _noop_register(**kwargs: object) -> None:
    return None


async def _wait_for(check, timeout_s: float) -> bool:  # noqa: ANN001
    for _ in range(int(timeout_s / 0.05)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return check()


async def test_second_worker_starts_scheduler_only_after_the_first_releases(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(roles, "register_sync_jobs", _noop_register)
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(scheduler_module, "logger", structlog.get_logger("test.scheduler"))
    containers = [create_container(settings), create_container(settings)]
    await (await containers[0].get(Database)).get_collection("leases").drop()
    # The unique name index is what makes the second contender lose.
    await (await containers[0].get(LeaseRepository)).ensure_indexes()
    apps = [SimpleNamespace(state=SimpleNamespace(lease_state={})) for _ in containers]
    owners = ["w1:1", "w2:1"]
    try:
        with structlog.testing.capture_logs() as logs:
            roles.start_worker(containers[0], apps[0], owners[0])  # type: ignore[arg-type]
            assert await _wait_for(lambda: apps[0].state.lease_state.get("worker") == "held", 2.0)
            roles.start_worker(containers[1], apps[1], owners[1])  # type: ignore[arg-type]
            await asyncio.sleep(1.0)

        second = await containers[1].get(JobScheduler)
        assert apps[1].state.lease_state["worker"] == "standby"
        assert second._scheduler is None
        assert len([e for e in logs if e["event"] == "scheduler.started"]) == 1

        await roles.stop_worker(containers[0], apps[0], owners[0], get_current_time())  # type: ignore[arg-type]
        assert await _wait_for(lambda: apps[1].state.lease_state.get("worker") == "held", 2.0)
        assert second._scheduler is not None
    finally:
        for container, app, owner in zip(containers, apps, owners, strict=True):
            await roles.stop_worker(container, app, owner, get_current_time())  # type: ignore[arg-type]
            await container.close()
