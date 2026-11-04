# Prod trader logged binance_ws.callback_failed error="'ETHUSDT:BINANCE'" and reconnected the
# whole Binance stream: a TTLCache entry expired between the membership test and the read.

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cachetools import TTLCache

from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.infra.persistence import symbol_lookup_helper
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

SYMBOL = "ETHUSDT:BINANCE"


class _FakeSymbolRepository:
    def __init__(self, symbol: Symbol | None) -> None:
        self._symbol = symbol

    async def find_by_symbol(self, symbol: str) -> Symbol | None:
        return self._symbol


def _ticks() -> Iterator[int]:
    # Insert at 0, the next read sees 59 (still fresh), every later read sees 60 (expired).
    yield 0
    yield 59
    while True:
        yield 60


@pytest.mark.parametrize("stored", [Symbol.create(SYMBOL), None])
async def test_an_entry_expiring_between_reads_never_raises(
    monkeypatch: pytest.MonkeyPatch, stored: Symbol | None
) -> None:
    ticks = _ticks()
    monkeypatch.setattr(
        symbol_lookup_helper, "_CACHE", TTLCache(maxsize=500, ttl=60, timer=lambda: next(ticks))
    )
    helper = SymbolLookupHelper(_FakeSymbolRepository(stored))  # type: ignore[arg-type]

    assert await helper.get(SYMBOL) == stored
    assert await helper.get(SYMBOL) == stored
