from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import structlog

from pocketquant.app import roles
from pocketquant.core.common.time.simulation import (
    clear_simulation_time,
    get_current_time,
    set_simulation_time,
)

T0 = datetime(2026, 10, 28, 10, 0, 20, tzinfo=UTC)
B = datetime(2026, 10, 28, 10, 1, tzinfo=UTC)


# Publishes every boundary's bars `delays.get(boundary, 0.6)` seconds after it.
class _Bars:
    def __init__(self, delays: dict[datetime, float] | None = None) -> None:
        self._delays = delays or {}

    @property
    def last_closed_boundary(self) -> datetime | None:
        now = get_current_time()
        boundary = now.replace(second=0, microsecond=0)
        for _ in range(5):
            if now >= boundary + timedelta(seconds=self._delays.get(boundary, 0.6)):
                return boundary
            boundary -= timedelta(minutes=1)
        return None


# In flight until `busy_until` (None = always).
class _Engine:
    def __init__(self, busy_until: datetime | None = T0) -> None:
        self.trading_until: datetime | None = datetime.max.replace(tzinfo=UTC)
        self._busy_until = busy_until

    def inflight_count(self) -> int:
        return 1 if self._busy_until is None or get_current_time() < self._busy_until else 0


@pytest.fixture(autouse=True)
def _simulated_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def fake_sleep(seconds: float) -> None:
        set_simulation_time(get_current_time() + timedelta(seconds=seconds))

    set_simulation_time(T0)
    monkeypatch.setattr(roles, "_sleep", fake_sleep)
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(roles, "logger", structlog.get_logger("test.trader_drain"))
    yield
    clear_simulation_time()


def _since_b() -> float:
    return (get_current_time() - B).total_seconds()


async def test_idle_trader_releases_once_the_boundary_bars_are_published() -> None:
    engine = _Engine()

    result = await roles.drain_trader(engine, _Bars(), T0)  # type: ignore[arg-type]

    assert result == (0, B)
    assert 0.6 <= _since_b() <= 0.8
    assert engine.trading_until is None


async def test_release_waits_for_late_boundary_bars() -> None:
    result = await roles.drain_trader(_Engine(), _Bars({B: 3.0}), T0)  # type: ignore[arg-type]

    assert result == (0, B)
    assert 3.0 <= _since_b() <= 3.2


async def test_inflight_open_delays_release_until_it_settles() -> None:
    engine = _Engine(busy_until=B + timedelta(seconds=5))

    result = await roles.drain_trader(engine, _Bars(), T0)  # type: ignore[arg-type]

    assert result == (0, B)
    assert 5.0 <= _since_b() <= 5.2


async def test_busy_window_retries_once_at_the_next_boundary() -> None:
    engine = _Engine(busy_until=B + timedelta(seconds=40))

    with structlog.testing.capture_logs() as logs:
        result = await roles.drain_trader(engine, _Bars(), T0)  # type: ignore[arg-type]

    assert result == (0, B + timedelta(minutes=1))
    assert len([e for e in logs if e["event"] == "trader.drain_retry"]) == 1


async def test_never_idle_logs_drain_timeout_within_150_s_of_shutdown_start() -> None:
    engine = _Engine(busy_until=None)

    with structlog.testing.capture_logs() as logs:
        inflight, _ = await roles.drain_trader(engine, _Bars(), T0)  # type: ignore[arg-type]

    assert inflight == 1
    [timeout] = [e for e in logs if e["event"] == "trader.drain_timeout"]
    assert timeout["log_level"] == "error"
    assert (get_current_time() - T0).total_seconds() <= 150.2
    assert engine.trading_until is None
