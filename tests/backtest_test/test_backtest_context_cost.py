from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.mongodb import Database
from tests.backtest_test.test_higher_timeframe_context import _backtest, _CountingBars
from tests.strategy_doubles import ScriptedStrategy

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_DAYS = 30


def _minute_bars() -> list[Bar]:
    bars = []
    for i in range(_DAYS * 24 * 60):
        price = 100.0 + (i % 240) * 0.01
        bars.append(
            Bar(
                symbol=_SYM,
                interval=Interval.MINUTE_1,
                datetime=_T0 + timedelta(minutes=i),
                open=price,
                high=price + 0.05,
                low=price - 0.05,
                close=price,
                volume=1.0,
            )
        )
    return bars


def _aggregate(minutes: list[Bar], interval: Interval, size: int) -> list[Bar]:
    out = []
    for i in range(0, len(minutes), size):
        chunk = minutes[i : i + size]
        out.append(
            Bar(
                symbol=_SYM,
                interval=interval,
                datetime=chunk[0].datetime,
                open=chunk[0].open,
                high=max(b.high for b in chunk),
                low=min(b.low for b in chunk),
                close=chunk[-1].close,
                volume=float(len(chunk)),
            )
        )
    return out


@pytest.mark.usefixtures("probe_registry")
async def test_a_multi_timeframe_backtest_reads_each_higher_interval_once(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ScriptedStrategy, "SCRIPT", ())
    coll = database.get_collection(COLLECTION_BARS)
    await coll.drop()
    minutes = _minute_bars()
    hours = _aggregate(minutes, Interval.HOUR_1, 60)
    fours = _aggregate(minutes, Interval.HOUR_4, 240)
    await coll.insert_many([b.to_mongo() for b in minutes + hours + fours])
    bars = _CountingBars(database)
    await bars.ensure_indexes()
    end = _T0 + timedelta(days=_DAYS) - timedelta(minutes=1)

    # Timing noise only adds, so the fastest of three interleaved runs is each leg's own cost;
    # interleaving charges warm-up and load drift to both legs alike.
    stf, mtf = [], []
    finds: dict[str, int] = {}
    for _ in range(3):
        started = time.perf_counter()
        await _backtest(database, bars, "probe", ["1m"], end, start=_T0)
        stf.append(time.perf_counter() - started)
        started = time.perf_counter()
        await _backtest(database, bars, "probe", ["1m", "1h", "4h"], end, start=_T0)
        mtf.append(time.perf_counter() - started)
        finds = finds or dict(bars.finds)
    t_stf_s, t_mtf_s = min(stf), min(mtf)

    print(
        f"context_cost find_1h={finds.get('1h', 0)} find_4h={finds.get('4h', 0)} "
        f"t_mtf_s={t_mtf_s:.2f} t_stf_s={t_stf_s:.2f}"
    )
    assert finds.get("1h") == 1
    assert finds.get("4h") == 1
    # The ratio depends on the runner's Mongo speed, so CI checks the read count and the ratio
    # is recorded locally.
    if not os.environ.get("CI"):
        assert t_mtf_s <= 2 * t_stf_s
