"""Resolve a symbol's trading calendar from its persisted ``calendar_id``.

Implementations are instantiated once and shared. They hold only schedule
caches, so they are stateless from a caller's point of view.
"""

from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = get_logger(__name__)


class TradingCalendarFactory:
    """Maps a ``calendar_id`` to its implementation, defaulting to 24/7."""

    def __init__(self, symbol_lookup: SymbolLookupHelper) -> None:
        self._symbol_lookup = symbol_lookup
        self._default = Continuous24x7Calendar()
        self._calendars: dict[str, ITradingCalendarPort] = {
            c.calendar_id: c for c in (self._default, CmeGlobexCalendarAdapter())
        }
        self._warned_unknown: set[str] = set()

    def get(self, calendar_id: str | None) -> ITradingCalendarPort:
        """The calendar for ``calendar_id``; 24/7 when it is missing or unknown."""
        if calendar_id is None:
            return self._default

        calendar = self._calendars.get(calendar_id)
        if calendar is not None:
            return calendar

        # Warn once per id, not once per bar — this sits on the sync hot path.
        if calendar_id not in self._warned_unknown:
            self._warned_unknown.add(calendar_id)
            logger.warning("calendar.unknown_id_fallback_24x7", calendar_id=calendar_id)
        return self._default

    async def for_symbol(self, composite: str) -> ITradingCalendarPort:
        """The calendar for a composite symbol; 24/7 when the symbol is unknown."""
        symbol = await self._symbol_lookup.get(composite)
        return self.get(symbol.calendar_id if symbol else None)
