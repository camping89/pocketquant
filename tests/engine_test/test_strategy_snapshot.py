from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import structlog

from pocketquant.core.common.time.simulation import set_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from tests.engine_test.test_paper_capabilities import (  # noqa: F401  (_sim_time is autouse)
    _EXIT,
    _MARKET,
    _SID,
    _SYM,
    _T0,
    _Paper,
    _paper,
    _sim_time,
    _stop,
)
from tests.strategy_doubles import ScriptedStrategy

_KEY = f"strategy:snapshot:{_SID}"


class _Cache:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sets: list[tuple[str, list[dict], int | None]] = []

    async def set(self, key: str, value: list[dict], ttl: int | None = None) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.sets.append((key, value, ttl))


async def _with_cache(*script: dict | None, fail: bool = False) -> tuple[_Paper, _Cache]:
    p = await _paper(*script)
    cache = _Cache(fail=fail)
    p.engine._cache = cache  # type: ignore[assignment]
    return p, cache


def _ring(p: _Paper) -> list[dict]:
    return list(p.engine._snapshots.get(_SID, []))


async def test_a_live_bar_writes_one_record_with_a_seven_day_ttl() -> None:
    p, cache = await _with_cache(None)
    p.strategy.snapshots = [{"readings": [{"name": "x", "value": 1.0}], "decision": {"a": 1}}]

    await p.bar()

    [(key, ring, ttl)] = cache.sets
    assert (key, ttl) == (_KEY, 604800)
    record = ring[-1]
    assert set(record) == {"bar_start", "interval", "readings", "decision", "outcome", "pending"}
    assert record["outcome"] == "no_signal"
    assert record["bar_start"] == _T0.isoformat()
    assert record["interval"] == "1m"
    assert record["readings"] == [{"name": "x", "value": 1.0}]
    assert record["decision"] == {"a": 1}
    assert record["pending"] is None


async def test_the_ring_keeps_the_last_twenty() -> None:
    p, cache = await _with_cache()

    for _ in range(25):
        await p.bar()

    ring = cache.sets[-1][1]
    assert len(ring) == 20
    assert ring[0]["bar_start"] == (_T0 + timedelta(minutes=5)).isoformat()


async def test_outcomes_name_what_happened() -> None:
    p, _ = await _with_cache(_MARKET)
    await p.bar()
    assert _ring(p)[-1]["outcome"] == "sent"

    p, _ = await _with_cache(_MARKET)
    p.engine._signal_tasks[_SID] = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    await p.bar()
    assert _ring(p)[-1]["outcome"] == "skipped:inflight"

    # A stop at the close leaves no price risk, so the size is zero.
    p, _ = await _with_cache({"stop_loss_price": 100.0})
    await p.bar()
    assert _ring(p)[-1]["outcome"] == "rejected:zero position size"

    p, _ = await _with_cache(_stop(105.0), _stop(105.0))
    await p.bar()
    await p.bar(h=102.0)
    assert [r["outcome"] for r in _ring(p)] == ["sent", "skipped:stop_unchanged"]

    p, _ = await _with_cache(_EXIT)
    await p.bar()
    assert _ring(p)[-1]["outcome"] == "skipped:nothing_open"


async def test_pending_shows_the_resting_stop() -> None:
    p, _ = await _with_cache(_stop(105.0))

    await p.bar()

    assert _ring(p)[-1]["pending"] == {"side": "buy", "price": 105.0}


async def test_nothing_is_written_without_the_lease() -> None:
    p, cache = await _with_cache(None)
    p.engine.trading_until = None

    await p.bar()

    assert cache.sets == []
    assert len(_ring(p)) == 1


class _StoredBars:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    # Newest first, as the repository returns them.
    async def find(self, *args: object, **kwargs: object) -> list[Bar]:
        return list(reversed(self._bars))


async def test_warm_up_fills_the_ring_without_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScriptedStrategy, "SCRIPT", (None, {}, None))
    p = _Paper()
    cache = _Cache()
    p.engine._cache = cache  # type: ignore[assignment]
    stored = [
        Bar(
            symbol=_SYM,
            interval=Interval.MINUTE_1,
            datetime=_T0 + timedelta(minutes=i),
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1.0,
        )
        for i in range(3)
    ]
    p.engine._bar_repository = _StoredBars(stored)  # type: ignore[assignment]
    # Past second 20, so the start does not wait for the settle.
    set_simulation_time(_T0 + timedelta(minutes=3, seconds=30))
    await p.mirror.start()
    await p.engine.start()
    config = StrategyConfig(id=_SID, name="t", symbol=_SYM, intervals=["1m"], broker="paper")
    await p.engine.load_strategy(config, ScriptedStrategy)
    await p.engine.start_strategy(_SID)

    assert [r["outcome"] for r in _ring(p)] == ["no_signal", "skipped:warmup", "no_signal"]
    assert cache.sets == []


async def test_a_failed_write_never_blocks_the_bar() -> None:
    p, _ = await _with_cache(_MARKET, fail=True)

    with structlog.testing.capture_logs() as logs:
        await p.bar()

    assert len(p.side_fills(OrderSide.BUY)) == 1
    failed = [e for e in logs if e["event"] == "strategy.snapshot_write_failed"]
    assert [(e["log_level"], e["subscription_id"]) for e in failed] == [("warning", _SID)]


async def test_unload_drops_the_ring() -> None:
    p, _ = await _with_cache(None)
    await p.bar()
    await p.strategy.on_stop()

    await p.engine.unload_strategy(_SID)

    assert _SID not in p.engine._snapshots
