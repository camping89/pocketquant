"""Unit tests for TrackedSymbolRepository — persistence layer."""

import pytest
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


class TestTrackedSymbolRepository:
    """Test repository CRUD operations."""

    @pytest.mark.asyncio
    async def test_upsert_idempotent(self, repo: TrackedSymbolRepository):
        """Upsert same symbol twice → idempotent (no duplicates)."""
        symbol = TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test")

        await repo.upsert(symbol)
        await repo.upsert(symbol)

        all_symbols = await repo.list_all()
        btc_entries = [s for s in all_symbols if s.symbol == "BTC" and s.exchange == "BINANCE"]
        assert len(btc_entries) == 1

    @pytest.mark.asyncio
    async def test_list_all_returns_all(self, repo: TrackedSymbolRepository):
        """list_all returns all symbols."""
        symbols = [
            TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test"),
            TrackedSymbol(exchange="BINANCE", symbol="ETH", seeded_from="test"),
            TrackedSymbol(exchange="OKEX", symbol="BTC", seeded_from="test"),
        ]

        for s in symbols:
            await repo.upsert(s)

        all_symbols = await repo.list_all()
        assert len(all_symbols) >= 3

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_tracked(self, repo: TrackedSymbolRepository):
        """exists returns True for tracked symbol."""
        symbol = TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test")
        await repo.upsert(symbol)

        exists = await repo.exists("BINANCE", "BTC")
        assert exists

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_untracked(self, repo: TrackedSymbolRepository):
        """exists returns False for untracked symbol."""
        exists = await repo.exists("BINANCE", "NONEXISTENT")
        assert not exists

    @pytest.mark.asyncio
    async def test_delete_removes_symbol(self, repo: TrackedSymbolRepository):
        """delete removes symbol."""
        symbol = TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test")
        await repo.upsert(symbol)

        await repo.delete("BINANCE", "BTC")

        exists = await repo.exists("BINANCE", "BTC")
        assert not exists

    @pytest.mark.asyncio
    async def test_unique_index_prevents_duplicates(self, repo: TrackedSymbolRepository):
        """Unique compound index on (exchange, symbol) prevents duplicates."""
        # This would be enforced by MongoDB unique index
        symbol1 = TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test1")
        symbol2 = TrackedSymbol(exchange="BINANCE", symbol="BTC", seeded_from="test2")

        await repo.upsert(symbol1)
        # Second upsert should replace, not create duplicate
        await repo.upsert(symbol2)

        all_symbols = await repo.list_all()
        btc_entries = [s for s in all_symbols if s.symbol == "BTC" and s.exchange == "BINANCE"]
        assert len(btc_entries) == 1
        # Latest seeded_from is preserved
        assert btc_entries[0].seeded_from == "test2"


@pytest.fixture
async def repo(settings) -> TrackedSymbolRepository:
    """TrackedSymbolRepository connected to test MongoDB."""
    from pocketquant.core.persistence.mongodb import Database

    db = Database(settings)
    await db.connect()
    repo = TrackedSymbolRepository(db)
    yield repo
    await db.close()
