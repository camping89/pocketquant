from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
    provider_id_for,
)
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


# No network here: the container health check polls /health every 30s and a blocking
# session probe would time it out. A symbol whose suffix names no provider is reported with
# provider null and an error, never as a failed check, so one bad row hides nothing.
# degraded (credentialed but no session) never reads unhealthy, so the container is not
# restarted for it.
async def check_market_data_providers(
    authenticated: Mapping[str, Callable[[], bool]],
    credentialed: Collection[str],
    calendar_factory: TradingCalendarFactory,
    tracked_symbols: TrackedSymbolRepository,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    symbols: dict[str, dict[str, Any]] = {}
    for tracked in await tracked_symbols.list_all():
        try:
            provider_id = provider_id_for(tracked.symbol)
            if provider_id not in authenticated:
                raise UnknownDataProviderError(
                    f"suffix names {provider_id!r}, which is not registered"
                )
            calendar = await calendar_factory.for_symbol(tracked.symbol)
        except UnknownDataProviderError as exc:
            symbols[tracked.symbol] = {"provider": None, "error": str(exc)}
            continue
        symbols[tracked.symbol] = {
            "provider": provider_id,
            "calendar_id": calendar.calendar_id,
            "is_market_open": calendar.is_open(now),
        }

    providers = {
        pid: {"authenticated": probe(), "credentialed": pid in credentialed}
        for pid, probe in authenticated.items()
    }
    in_use = {s["provider"] for s in symbols.values()}
    degraded = sorted(
        pid
        for pid, state in providers.items()
        if state["credentialed"] and pid in in_use and not state["authenticated"]
    )

    result: dict[str, Any] = {"providers": providers, "symbols": symbols}
    if degraded:
        result["status"] = "degraded"
        result["degraded_providers"] = degraded
    return result
