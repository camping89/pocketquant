"""Answer "why are there no bars for this symbol" from one ``/health`` request.

Reports each registered provider's session state and, per tracked symbol, the
provider it routes to and whether its calendar says the market is open now.

Nothing here touches the network. Authentication is read from a cached flag,
because the container health check polls ``/health`` every 30s and a blocking
scraper call would time it out. A lost TradingView session reports
``degraded``, never ``unhealthy``: the scraper re-logs on its next fetch, and a
health check that fails for it would restart the container for nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.market_data.symbol_provider_resolver import SymbolProviderResolver
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

#: Providers whose sessions matter to the data they return. An anonymous
#: TradingView session still answers, but with delayed data and a shorter history.
SESSION_PROVIDERS = frozenset({"tradingview"})


async def check_market_data_providers(
    authenticated: Mapping[str, Callable[[], bool]],
    resolver: SymbolProviderResolver,
    calendar_factory: TradingCalendarFactory,
    tracked_symbols: TrackedSymbolRepository,
) -> dict[str, Any]:
    """Provider sessions plus per-symbol routing and market state.

    ``authenticated`` maps each registered provider id to a cached,
    non-blocking session probe. The payload is bounded by the tracked-symbol
    list and never carries bars.
    """
    now = datetime.now(UTC)
    symbols: dict[str, dict[str, Any]] = {}
    for tracked in await tracked_symbols.list_all():
        provider_ids = await resolver.provider_ids(tracked.symbol)
        calendar = await calendar_factory.for_symbol(tracked.symbol)
        symbols[tracked.symbol] = {
            "provider": provider_ids[0] if provider_ids else None,
            "calendar_id": calendar.calendar_id,
            "is_market_open": calendar.is_open(now),
        }

    providers = {pid: {"authenticated": probe()} for pid, probe in authenticated.items()}
    in_use = {s["provider"] for s in symbols.values()}
    degraded = sorted(
        pid
        for pid, state in providers.items()
        if pid in SESSION_PROVIDERS and pid in in_use and not state["authenticated"]
    )

    result: dict[str, Any] = {"providers": providers, "symbols": symbols}
    if degraded:
        result["status"] = "degraded"
        result["degraded_providers"] = degraded
    return result
