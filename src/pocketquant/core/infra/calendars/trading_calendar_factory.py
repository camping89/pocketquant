from __future__ import annotations

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    provider_defaults_for,
)
from pocketquant.core.domain.market_data.trading_calendar_port import ITradingCalendarPort
from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper

logger = get_logger(__name__)


# Implementations are shared: they hold only schedule caches. A missing or unknown
# calendar_id falls back to 24/7.
class TradingCalendarFactory:
    def __init__(self, symbol_lookup: SymbolLookupHelper) -> None:
        self._symbol_lookup = symbol_lookup
        self._default = Continuous24x7Calendar()
        self._calendars: dict[str, ITradingCalendarPort] = {
            c.calendar_id: c for c in (self._default, *EXNESS_CALENDARS)
        }
        self._warned_unknown: set[str] = set()

    def get(self, calendar_id: str | None) -> ITradingCalendarPort:
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

    # An unseeded symbol takes its data provider's default calendar, so bars from a
    # session-hours venue are never read as 24/7 just because nobody seeded the symbol.
    async def for_symbol(self, composite: str) -> ITradingCalendarPort:
        symbol = await self._symbol_lookup.get(composite)
        if symbol is None:
            return self.get(provider_defaults_for(composite).calendar_id)
        return self.get(symbol.calendar_id)
