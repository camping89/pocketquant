"""Pin tracked_symbols behavior through the feature service (ex-CQRS handlers)."""

import fnmatch
from datetime import UTC, datetime

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.engine.market_data.tracked_symbols_service import (
    AddTrackedSymbolCommand,
    TrackedSymbolService,
)

_SCOPED = (
    "symbol_repository",
    "bar_repository",
    "sync_status_repository",
    "backtest_repository",
    "backtest_order_repository",
    "backtest_trade_repository",
    "order_repository",
    "position_repository",
    "trade_repository",
)


class FakeTrackedSymbolRepo:
    def __init__(self, existing: list[TrackedSymbol] | None = None) -> None:
        self.items = {ts.symbol: ts for ts in (existing or [])}
        self.upserted: list[TrackedSymbol] = []

    async def upsert(self, ts: TrackedSymbol) -> None:
        self.upserted.append(ts)
        self.items[ts.symbol] = ts

    async def update(self, symbol: str, fields: dict) -> bool:
        return symbol in self.items

    async def delete_by_symbol(self, symbol: str) -> int:
        return int(self.items.pop(symbol, None) is not None)

    async def list_all(self) -> list[TrackedSymbol]:
        return list(self.items.values())


class FakeScopedRepo:
    """Holds one symbol string per stored document."""

    def __init__(self, symbols: list[str]) -> None:
        self.docs = list(symbols)

    async def delete_by_symbol(self, symbol: str) -> int:
        before = len(self.docs)
        self.docs = [s for s in self.docs if s != symbol]
        return before - len(self.docs)


class FakeSubscriptionRepo:
    def __init__(self, subs: list[Subscription]) -> None:
        self.subs = {str(s.id): s for s in subs}

    async def list_by_symbol(self, symbol: str) -> list[Subscription]:
        return [s for s in self.subs.values() if s.symbol == symbol]


class FakeStrategyCommands:
    def __init__(self, sub_repo: FakeSubscriptionRepo) -> None:
        self._sub_repo = sub_repo
        self.calls: list[tuple[str, str]] = []

    async def stop(self, subscription_id: str) -> bool:
        self.calls.append(("stop", subscription_id))
        return True

    async def remove_symbol(self, sub_id: str) -> int:
        self.calls.append(("remove", sub_id))
        return int(self._sub_repo.subs.pop(sub_id, None) is not None)


class FakeJobHistoryRepo:
    def __init__(self, detail_symbols: list[list[str]]) -> None:
        self.runs = detail_symbols

    async def remove_symbol_details(self, symbol: str) -> int:
        touched = sum(symbol in run for run in self.runs)
        self.runs = [[s for s in run if s != symbol] for run in self.runs]
        return touched


class FakeCache:
    def __init__(self, keys: list[str]) -> None:
        self.keys = set(keys)
        self.patterns: list[str] = []

    async def delete_pattern(self, pattern: str) -> int:
        self.patterns.append(pattern)
        hit = {k for k in self.keys if fnmatch.fnmatchcase(k, pattern)}
        self.keys -= hit
        return len(hit)


def _ts(symbol: str) -> TrackedSymbol:
    return TrackedSymbol(
        symbol=symbol,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        seeded_from="admin",
    )


def _sub(symbol: str, state: str = "running") -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code="engulfing",
        symbol=symbol,
        interval=Interval.HOUR_1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        desired_state=state,  # type: ignore[arg-type]
        actual_state=state,  # type: ignore[arg-type]
    )


def _service(tracked: FakeTrackedSymbolRepo, **overrides) -> TrackedSymbolService:
    sub_repo = overrides.pop("subscription_repository", FakeSubscriptionRepo([]))
    deps = {
        "tracked_symbol_repository": tracked,
        "subscription_repository": sub_repo,
        "strategy_command_service": FakeStrategyCommands(sub_repo),
        "job_history_repository": FakeJobHistoryRepo([]),
        "cache": FakeCache([]),
        **{name: FakeScopedRepo([]) for name in _SCOPED},
        **overrides,
    }
    return TrackedSymbolService(**deps)


@pytest.mark.asyncio
async def test_add_upserts_and_returns_state():
    repo = FakeTrackedSymbolRepo()
    svc = _service(repo)
    result = await svc.add(AddTrackedSymbolCommand(symbol="btcusdt:binance"))
    assert result["symbol"] == "BTCUSDT:BINANCE"  # command validator uppercases
    assert result["seeded_from"] == "admin"
    assert "created_at" in result
    assert len(repo.upserted) == 1


@pytest.mark.asyncio
async def test_update_validates_existence():
    svc = _service(FakeTrackedSymbolRepo([_ts("BTCUSDT:BINANCE")]))
    result = await svc.update("BTCUSDT:BINANCE")
    assert result == {"symbol": "BTCUSDT:BINANCE", "status": "updated"}


@pytest.mark.asyncio
async def test_update_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        await _service(FakeTrackedSymbolRepo()).update("NOPE:BINANCE")


@pytest.mark.asyncio
async def test_remove_cascades_every_collection_and_spares_other_symbols():
    gone, kept = "ETHUSDT:BINANCE", "BTCUSDT:BINANCE"
    tracked = FakeTrackedSymbolRepo([_ts(gone), _ts(kept)])
    scoped = {name: FakeScopedRepo([gone, gone, kept]) for name in _SCOPED}
    sub_gone, sub_kept = _sub(gone), _sub(kept)
    sub_repo = FakeSubscriptionRepo([sub_gone, sub_kept])
    commands = FakeStrategyCommands(sub_repo)
    job_history = FakeJobHistoryRepo([[gone, kept], [kept], [gone]])
    cache = FakeCache(
        [
            f"quote:latest:{gone}",
            f"bar:current:{gone}:1m",
            f"bar:current:{gone}:1d",
            f"ohlcv:{gone}:1h:500",
            f"data_lag:{gone}",
            f"quote:latest:{kept}",
            f"bar:current:{kept}:1m",
            f"ohlcv:{kept}:1h:500",
            f"data_lag:{kept}",
        ]
    )
    svc = _service(
        tracked,
        subscription_repository=sub_repo,
        strategy_command_service=commands,
        job_history_repository=job_history,
        cache=cache,
        **scoped,
    )

    result = await svc.remove(gone)

    assert result["symbol"] == gone
    assert result["status"] == "removed"
    assert result["deleted"] == {
        "tracked_symbols": 1,
        "subscriptions": 1,
        "symbols": 2,
        "bars": 2,
        "sync_status": 2,
        "backtest_orders": 2,
        "backtest_trades": 2,
        "backtest_runs": 2,
        "orders": 2,
        "positions": 2,
        "trades": 2,
        "job_history_runs": 2,
        "cache_keys": 5,
    }
    # Stop through the strategy command path before the doc is removed.
    assert commands.calls == [("stop", str(sub_gone.id)), ("remove", str(sub_gone.id))]
    assert set(tracked.items) == {kept}
    assert all(repo.docs == [kept] for repo in scoped.values())
    assert list(sub_repo.subs) == [str(sub_kept.id)]
    assert job_history.runs == [[kept], [kept], []]
    assert cache.keys == {
        f"quote:latest:{kept}",
        f"bar:current:{kept}:1m",
        f"ohlcv:{kept}:1h:500",
        f"data_lag:{kept}",
    }


@pytest.mark.asyncio
async def test_remove_is_idempotent_and_finishes_partial_prior_state():
    symbol = "ETHUSDT:BINANCE"
    bars = FakeScopedRepo([symbol] * 3)
    svc = _service(FakeTrackedSymbolRepo(), bar_repository=bars)

    first = await svc.remove(symbol)
    second = await svc.remove(symbol)

    assert first["deleted"]["tracked_symbols"] == 0
    assert first["deleted"]["bars"] == 3
    assert bars.docs == []
    assert set(second["deleted"].values()) == {0}


@pytest.mark.asyncio
async def test_list_serializes_all():
    repo = FakeTrackedSymbolRepo([_ts("BTCUSDT:BINANCE"), _ts("ETHUSDT:BINANCE")])
    result = await _service(repo).list_all()
    assert {r["symbol"] for r in result} == {"BTCUSDT:BINANCE", "ETHUSDT:BINANCE"}
    assert all(set(r) == {"symbol", "created_at", "seeded_from"} for r in result)
