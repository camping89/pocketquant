"""``touch`` must not reset a seeded symbol's asset-class metadata.

``SyncService._persist_bars`` runs on every sync cycle. It used to call
``upsert(Symbol.create(symbol))``, which sends the whole document as ``$set`` —
and ``Symbol.create`` with no asset class produces crypto defaults. A seeded
``XAUUSD:EXNESS`` would therefore have become crypto spot on its first 1m sync,
silently, and every calendar decision after that would have been wrong.
"""

from __future__ import annotations

import pytest

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import ContractSpec, Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_EXNESS_FX,
    CALENDAR_EXNESS_XAUUSD,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository

CFD_SYMBOL = "XAUUSD:EXNESS"
# The seeded XAUUSD record (scripts/seed_exness_symbols.py): its own calendar,
# not the provider's EXNESS_FX default, and a tick size the default spec lacks.
XAUUSD_SPEC = ContractSpec(multiplier=1.0, tick_size=0.001, lot_step=None, currency="USD")


@pytest.fixture
async def repo(database: Database) -> SymbolRepository:
    return SymbolRepository(database)


async def test_touch_preserves_seeded_asset_class(repo: SymbolRepository) -> None:
    seeded = Symbol.create(
        CFD_SYMBOL,
        asset_class=AssetClass.CFD,
        calendar_id=CALENDAR_EXNESS_XAUUSD,
        contract_spec=XAUUSD_SPEC,
    )
    await repo.upsert(seeded)

    # What every sync cycle does.
    await repo.touch(CFD_SYMBOL)

    stored = await repo.find_by_symbol(CFD_SYMBOL)
    assert stored is not None
    assert stored.asset_class is AssetClass.CFD
    assert stored.calendar_id == CALENDAR_EXNESS_XAUUSD
    assert stored.contract_spec == XAUUSD_SPEC


async def test_touch_creates_a_missing_symbol_with_defaults(repo: SymbolRepository) -> None:
    await repo.touch("DOGEUSDT:BINANCE")

    stored = await repo.find_by_symbol("DOGEUSDT:BINANCE")
    assert stored is not None
    assert stored.asset_class is AssetClass.CRYPTO_SPOT


async def test_upsert_still_overwrites_deliberately(repo: SymbolRepository) -> None:
    """Seeding and migration scripts rely on ``upsert`` replacing the document."""
    await repo.upsert(Symbol.create(CFD_SYMBOL, asset_class=AssetClass.CFD))

    await repo.upsert(Symbol.create(CFD_SYMBOL, asset_class=AssetClass.CRYPTO_SPOT))

    stored = await repo.find_by_symbol(CFD_SYMBOL)
    assert stored is not None
    assert stored.asset_class is AssetClass.CRYPTO_SPOT


async def test_touch_stamps_an_unseeded_symbol_with_its_providers_defaults(
    repo: SymbolRepository,
) -> None:
    """A session-hours symbol synced before seeding must not become 24/7 crypto."""
    await repo.touch("EURUSD:EXNESS")

    stored = await repo.find_by_symbol("EURUSD:EXNESS")
    assert stored is not None
    assert stored.asset_class is AssetClass.CFD
    assert stored.calendar_id == CALENDAR_EXNESS_FX


async def test_touch_refuses_a_symbol_whose_provider_is_not_registered(
    repo: SymbolRepository,
) -> None:
    with pytest.raises(UnknownDataProviderError):
        await repo.touch("XAUUSD:MT5")

    assert await repo.find_by_symbol("XAUUSD:MT5") is None
