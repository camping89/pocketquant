"""Characterization of the five scheduled sync jobs against real Mongo/Redis.

Pins what each job writes to ``bars``, ``sync_status`` and ``job_history`` and
what it asks the data provider for, independent of module paths and provider
wiring. Later refactors may change only the ``register_sync_jobs`` import line
and the fixture wiring (how ``FakeProvider`` reaches ``SyncService`` and the
container); the assertions stay fixed.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from pocketquant.core.common.constants import (
    COLLECTION_BARS,
    COLLECTION_JOB_HISTORY,
    COLLECTION_SYMBOLS,
    COLLECTION_SYNC_STATUS,
    COLLECTION_TRACKED_SYMBOLS,
)
from pocketquant.core.config import Settings
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder import get_bar_start
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import (
    _BAR_VALUE_CACHE,
    BarRepository,
)
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.sync_policy import SyncPolicies, binance_policy
from pocketquant.engine.market_data.sync_runner import register_sync_jobs
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand

pytestmark = pytest.mark.asyncio

SYMBOL = "BTCUSDT:BINANCE"
_COLLECTIONS = (
    COLLECTION_BARS,
    COLLECTION_SYNC_STATUS,
    COLLECTION_SYMBOLS,
    COLLECTION_JOB_HISTORY,
    COLLECTION_TRACKED_SYMBOLS,
)
_CASCADE_TFS = (
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
)
_MAX_BARS_PER_CALL = 100


class FakeProvider(IDataProvider):
    """Deterministic closed, aligned bars ending one step before the current bar.

    ``now`` is frozen at construction so repeated fetches in one test return the
    same bars even when a minute boundary passes mid-test.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, Interval, int]] = []
        self._now = datetime.now(UTC)

    async def fetch_ohlcv(self, symbol: str, interval: Interval, n_bars: int = 1000) -> list[Bar]:
        self.calls.append((symbol, interval, n_bars))
        step = timedelta(seconds=INTERVAL_SECONDS[interval])
        last = get_bar_start(self._now, interval) - step
        count = min(n_bars, _MAX_BARS_PER_CALL)
        bars = []
        for i in range(count):
            open_ = 100.0 + i
            bars.append(
                Bar(
                    symbol=symbol,
                    interval=interval,
                    datetime=last - (count - 1 - i) * step,
                    open=open_,
                    high=open_ + 2,
                    low=open_ - 1,
                    close=open_ + 1,
                    volume=float(1 + i % 3),
                    tick_count=1,
                )
            )
        return bars

    async def search_symbols(self, query: str) -> list[dict]:
        return []

    async def close(self) -> None:
        return None


class FakeContainer:
    def __init__(self, objects: dict[type, object]) -> None:
        self._objects = objects

    async def get(self, cls: type) -> object:
        return self._objects[cls]


class RecordingScheduler:
    def __init__(self) -> None:
        self.cron_jobs: list[tuple[str, str, dict]] = []
        self.one_off_jobs: list[tuple[str, str, dict]] = []

    def add_cron_job(self, func: str, *, job_id: str, **kw) -> None:
        self.cron_jobs.append((func, job_id, kw))

    def add_one_off_job(self, func: str, *, job_id: str, **kw) -> None:
        self.one_off_jobs.append((func, job_id, kw))


@dataclass
class Deps:
    db: Database
    cache: Cache
    bars: BarRepository
    symbols: SymbolRepository
    sync_status: SyncStatusRepository
    history: JobHistoryRepository
    tracked: TrackedSymbolRepository


@pytest_asyncio.fixture
async def deps(settings: Settings):
    db = Database()
    await db.connect(settings)
    cache = Cache()
    await cache.connect(settings)
    d = Deps(
        db=db,
        cache=cache,
        bars=BarRepository(db),
        symbols=SymbolRepository(db),
        sync_status=SyncStatusRepository(db),
        history=JobHistoryRepository(db),
        tracked=TrackedSymbolRepository(db),
    )
    for repo in (d.bars, d.symbols, d.sync_status, d.history, d.tracked):
        await repo.ensure_indexes()

    async def wipe() -> None:
        _BAR_VALUE_CACHE.clear()
        for name in _COLLECTIONS:
            await db.get_collection(name).delete_many({})

    await wipe()
    await d.tracked.upsert(TrackedSymbol(symbol=SYMBOL))
    try:
        yield d
    finally:
        await wipe()
        await cache.disconnect()
        await db.disconnect()


def _resolve(func_ref: str):
    module, name = func_ref.split(":")
    return getattr(importlib.import_module(module), name)


async def _latest_run(db: Database, job_id: str) -> dict:
    docs = (
        await db.get_collection(COLLECTION_JOB_HISTORY)
        .find({"job_id": job_id})
        .sort("started_at", -1)
        .limit(1)
        .to_list(1)
    )
    assert docs, f"no job_history doc for {job_id}"
    return docs[0]


async def _assert_cascade_matches_1m(db: Database) -> None:
    bars = db.get_collection(COLLECTION_BARS)
    for tf in _CASCADE_TFS:
        docs = await bars.find(
            {"symbol": SYMBOL, "interval": tf.value, "source": "cascade"}
        ).to_list(None)
        assert docs, f"no cascade docs for {tf.value}"
        for doc in docs:
            start = doc["datetime"]
            end = start + timedelta(seconds=INTERVAL_SECONDS[tf])
            src = (
                await bars.find(
                    {"symbol": SYMBOL, "interval": "1m", "datetime": {"$gte": start, "$lt": end}}
                )
                .sort("datetime", 1)
                .to_list(None)
            )
            assert src, f"cascade {tf.value} {start} has no 1m source"
            expected = (
                src[0]["open"],
                max(d["high"] for d in src),
                min(d["low"] for d in src),
                src[-1]["close"],
                sum(d["volume"] for d in src),
            )
            actual = (doc["open"], doc["high"], doc["low"], doc["close"], doc["volume"])
            assert actual == expected, f"cascade {tf.value} {start}"


async def test_sync_pipeline_characterization(deps: Deps) -> None:
    db = deps.db
    fake = FakeProvider()
    policies = SyncPolicies([binance_policy(data_provider=fake, quote_provider=None)])
    sync_service = SyncService(
        policies=policies,
        cache=deps.cache,
        bar_repository=deps.bars,
        symbol_repository=deps.symbols,
        sync_status_repository=deps.sync_status,
    )
    container = FakeContainer(
        {
            SyncService: sync_service,
            JobHistoryRepository: deps.history,
            TrackedSymbolRepository: deps.tracked,
            BarRepository: deps.bars,
            SyncPolicies: policies,
        }
    )
    scheduler = RecordingScheduler()
    await register_sync_jobs(container, scheduler)  # type: ignore[arg-type]
    jobs = {job_id: _resolve(func) for func, job_id, _ in scheduler.cron_jobs}

    # (a) registrations
    assert [(job_id, kw) for _, job_id, kw in scheduler.cron_jobs] == [
        ("sync_1m", {"cron_expression": "*/1 * * * *", "second": 2, "misfire_grace_time": 120}),
        ("sync_verify_cascade", {"cron_expression": "0 * * * *", "misfire_grace_time": 600}),
        ("sync_backfill", {"hour": 3, "minute": 0, "misfire_grace_time": 3600}),
        ("sync_integrity", {"hour": 4, "minute": 0, "misfire_grace_time": 3600}),
        ("sync_repair", {"cron_expression": "0 */12 * * *", "misfire_grace_time": 1800}),
    ]
    assert scheduler.one_off_jobs == []

    # (b) sync_1m
    await jobs["sync_1m"]()
    assert fake.calls == [(SYMBOL, Interval.MINUTE_1, 100)]
    bars = db.get_collection(COLLECTION_BARS)
    assert await bars.count_documents({"interval": "1m", "source": "rest_sync_1m"}) == 100
    await _assert_cascade_matches_1m(db)
    run = await _latest_run(db, "sync_1m")
    assert run["status"] == "completed"
    assert run["total_inserted"] == 100
    assert run["total_fetched"] == 100
    assert len(run["details"]) == 1

    # (c) sync_1m again
    await jobs["sync_1m"]()
    assert (await _latest_run(db, "sync_1m"))["total_inserted"] == 0
    status = await deps.sync_status.find_one(SYMBOL, Interval.MINUTE_1)
    assert status is not None
    assert status.consecutive_empty_fetches == 1

    # (d) sync_backfill
    fake.calls.clear()
    await jobs["sync_backfill"]()
    assert fake.calls == [
        (SYMBOL, iv, 5000)
        for iv in (
            Interval.MINUTE_1,
            Interval.MINUTE_5,
            Interval.MINUTE_15,
            Interval.HOUR_1,
            Interval.HOUR_4,
            Interval.DAY_1,
            Interval.WEEK_1,
        )
    ]
    assert (await _latest_run(db, "sync_backfill"))["status"] == "completed"

    # (e) sync_repair
    hour_ago = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    victim = await bars.find_one(
        {"symbol": SYMBOL, "interval": "1m", "datetime": {"$gt": hour_ago}}
    )
    assert victim is not None
    assert await deps.bars.delete_many_by_ids([victim["_id"]]) == 1
    fake.calls.clear()
    # A warm _BAR_VALUE_CACHE makes upsert_bar skip re-writing an identical bar even
    # after its doc was deleted; clearing it models the restart/TTL expiry before repair.
    _BAR_VALUE_CACHE.clear()
    await jobs["sync_repair"]()
    assert (SYMBOL, Interval.MINUTE_1, 5000) in fake.calls
    assert await bars.count_documents(
        {"symbol": SYMBOL, "interval": "1m", "datetime": victim["datetime"]}
    ) == 1
    assert (await _latest_run(db, "sync_repair"))["status"] == "completed"

    # (f) sync_integrity
    await jobs["sync_integrity"]()
    assert (await _latest_run(db, "sync_integrity"))["status"] == "completed"

    # (g) sync_verify_cascade
    fake.calls.clear()
    await jobs["sync_verify_cascade"]()
    assert fake.calls == [(SYMBOL, Interval.MINUTE_5, 12)]
    assert (await _latest_run(db, "sync_verify_cascade"))["status"] == "completed"

    # (h) sync_one response shape
    response = await sync_service.sync_one(
        SyncSymbolCommand(
            symbol="btcusdt:binance",
            interval=Interval.MINUTE_1,
            n_bars=10,
            source="rest_backfill",
        )
    )
    assert response.model_dump().keys() == {
        "symbol",
        "interval",
        "status",
        "bars_synced",
        "bars_fetched",
        "filtered_existing",
        "filtered_misaligned",
        "total_bars",
        "last_bar_at",
        "message",
    }
    assert response.symbol == "BTCUSDT:BINANCE"
    assert response.status == "completed"
