"""``touch`` must not reset a seeded symbol's asset-class metadata.

``SyncService._persist_bars`` runs on every sync cycle. It used to call
``upsert(Symbol.create(symbol))``, which sends the whole document as ``$set`` —
and ``Symbol.create`` with no asset class produces crypto defaults. A seeded
``ES1!:CME_MINI`` would therefore have become crypto spot on its first 1m sync,
silently, and every calendar decision after that would have been wrong.
"""

from __future__ import annotations

import pytest

from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import (
    CALENDAR_CME_GLOBEX_EQUITY,
    ContractSpec,
    Symbol,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository

FUTURES_SYMBOL = "ES1!:CME_MINI"


@pytest.fixture
async def repo(database: Database) -> SymbolRepository:
    return SymbolRepository(database)


async def test_touch_preserves_seeded_asset_class(repo: SymbolRepository) -> None:
    seeded = Symbol.create(
        FUTURES_SYMBOL,
        asset_class=AssetClass.INDEX_FUTURE,
        contract_spec=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0),
    )
    await repo.upsert(seeded)

    # What every sync cycle does.
    await repo.touch(FUTURES_SYMBOL)

    stored = await repo.find_by_symbol(FUTURES_SYMBOL)
    assert stored is not None
    assert stored.asset_class is AssetClass.INDEX_FUTURE
    assert stored.calendar_id == CALENDAR_CME_GLOBEX_EQUITY
    assert stored.contract_spec.multiplier == 50.0


async def test_touch_creates_a_missing_symbol_with_defaults(repo: SymbolRepository) -> None:
    await repo.touch("DOGEUSDT:BINANCE")

    stored = await repo.find_by_symbol("DOGEUSDT:BINANCE")
    assert stored is not None
    assert stored.asset_class is AssetClass.CRYPTO_SPOT


async def test_upsert_still_overwrites_deliberately(repo: SymbolRepository) -> None:
    """Seeding and migration scripts rely on ``upsert`` replacing the document."""
    await repo.upsert(Symbol.create(FUTURES_SYMBOL, asset_class=AssetClass.INDEX_FUTURE))

    await repo.upsert(Symbol.create(FUTURES_SYMBOL, asset_class=AssetClass.CRYPTO_SPOT))

    stored = await repo.find_by_symbol(FUTURES_SYMBOL)
    assert stored is not None
    assert stored.asset_class is AssetClass.CRYPTO_SPOT
