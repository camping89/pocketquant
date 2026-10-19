"""seed_exness_symbols: CFD symbols on their own calendars, dry run by default."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.infra.exness.exness_mappers import EXNESS_INSTRUMENTS
from scripts import seed_exness_symbols
from scripts.seed_exness_symbols import SEEDS, _build
from tests.core_test.infra.market_data.conftest import build_settings

CALENDARS = {
    "XAUUSD:EXNESS": "EXNESS_XAUUSD",
    "EURUSD:EXNESS": "EXNESS_FX",
    "BTCUSD:EXNESS": "EXNESS_CRYPTO",
}


def test_each_seed_is_a_cfd_on_its_own_calendar() -> None:
    for composite, name, calendar_id, spec in SEEDS:
        symbol = _build(composite, name, calendar_id, spec)

        assert symbol.asset_class is AssetClass.CFD
        assert symbol.calendar_id == CALENDARS[composite]
        assert symbol.contract_spec.lot_step is None


def test_the_seeds_are_exactly_the_exness_instruments() -> None:
    assert {composite for composite, *_ in SEEDS} == set(EXNESS_INSTRUMENTS)


async def test_a_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    database = MagicMock()
    database.connect = AsyncMock()
    database.disconnect = AsyncMock()
    symbols, tracked = MagicMock(), MagicMock()
    symbols.upsert = AsyncMock()
    tracked.upsert = AsyncMock()
    monkeypatch.setattr(seed_exness_symbols, "Settings", build_settings)
    monkeypatch.setattr(seed_exness_symbols, "Database", lambda: database)
    monkeypatch.setattr(seed_exness_symbols, "SymbolRepository", lambda _db: symbols)
    monkeypatch.setattr(seed_exness_symbols, "TrackedSymbolRepository", lambda _db: tracked)

    assert await seed_exness_symbols.seed(apply=False) == 0

    symbols.upsert.assert_not_awaited()
    tracked.upsert.assert_not_awaited()
    database.disconnect.assert_awaited_once()
