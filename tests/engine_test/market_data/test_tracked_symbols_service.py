"""Pin tracked_symbols behavior through the feature service (ex-CQRS handlers)."""

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.engine.market_data.tracked_symbols_service import (
    AddTrackedSymbolCommand,
    ListTrackedSymbolsQuery,
    RemoveTrackedSymbolCommand,
    TrackedSymbolService,
    UpdateTrackedSymbolCommand,
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

    async def delete(self, symbol: str) -> bool:
        return self.items.pop(symbol, None) is not None

    async def list_all(self) -> list[TrackedSymbol]:
        return list(self.items.values())


def _ts(symbol: str) -> TrackedSymbol:
    return TrackedSymbol(
        symbol=symbol,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        seeded_from="admin",
    )


@pytest.mark.asyncio
async def test_add_upserts_and_returns_state():
    repo = FakeTrackedSymbolRepo()
    svc = TrackedSymbolService(tracked_symbol_repository=repo)  # type: ignore[arg-type]
    result = await svc.add(AddTrackedSymbolCommand(symbol="btcusdt:binance"))
    assert result["symbol"] == "BTCUSDT:BINANCE"  # command validator uppercases
    assert result["seeded_from"] == "admin"
    assert "created_at" in result
    assert len(repo.upserted) == 1


@pytest.mark.asyncio
async def test_update_validates_existence():
    repo = FakeTrackedSymbolRepo([_ts("BTCUSDT:BINANCE")])
    svc = TrackedSymbolService(tracked_symbol_repository=repo)  # type: ignore[arg-type]
    result = await svc.update(UpdateTrackedSymbolCommand(symbol="BTCUSDT:BINANCE"))
    assert result == {"symbol": "BTCUSDT:BINANCE", "status": "updated"}


@pytest.mark.asyncio
async def test_update_missing_raises_not_found():
    svc = TrackedSymbolService(tracked_symbol_repository=FakeTrackedSymbolRepo())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await svc.update(UpdateTrackedSymbolCommand(symbol="NOPE:BINANCE"))


@pytest.mark.asyncio
async def test_remove_deletes_and_404s_when_missing():
    repo = FakeTrackedSymbolRepo([_ts("ETHUSDT:BINANCE")])
    svc = TrackedSymbolService(tracked_symbol_repository=repo)  # type: ignore[arg-type]
    result = await svc.remove(RemoveTrackedSymbolCommand(symbol="ETHUSDT:BINANCE"))
    assert result == {"symbol": "ETHUSDT:BINANCE", "status": "removed"}
    with pytest.raises(NotFoundError):
        await svc.remove(RemoveTrackedSymbolCommand(symbol="ETHUSDT:BINANCE"))


@pytest.mark.asyncio
async def test_list_serializes_all():
    repo = FakeTrackedSymbolRepo([_ts("BTCUSDT:BINANCE"), _ts("ETHUSDT:BINANCE")])
    svc = TrackedSymbolService(tracked_symbol_repository=repo)  # type: ignore[arg-type]
    result = await svc.list_all(ListTrackedSymbolsQuery())
    assert {r["symbol"] for r in result} == {"BTCUSDT:BINANCE", "ETHUSDT:BINANCE"}
    assert all(set(r) == {"symbol", "created_at", "seeded_from"} for r in result)
