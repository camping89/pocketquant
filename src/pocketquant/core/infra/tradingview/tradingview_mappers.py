"""TradingView translations — composite symbol, interval, raw bar to ``Bar``.

Every TradingView-specific field translation lives here, so the client stays a
transport and the adapter stays policy. No network call belongs in this module,
mirroring ``core/infra/binance/binance_mappers.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tvDatafeed import Interval as TvInterval

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.tradingview.tradingview_client_interface import RawBar

# Domain Interval -> the scraper's own enum. Member names were read off the
# installed package rather than assumed; it also carries 3m/30m/45m/2h/3h/1M
# members the domain has no equivalent for.
INTERVAL_TO_TRADINGVIEW: dict[Interval, TvInterval] = {
    Interval.MINUTE_1: TvInterval.in_1_minute,
    Interval.MINUTE_5: TvInterval.in_5_minute,
    Interval.MINUTE_15: TvInterval.in_15_minute,
    Interval.HOUR_1: TvInterval.in_1_hour,
    Interval.HOUR_4: TvInterval.in_4_hour,
    Interval.DAY_1: TvInterval.in_daily,
    Interval.WEEK_1: TvInterval.in_weekly,
}

# The continuous front-month suffix TradingView uses, e.g. ES1! -> ES contract 1.
_FRONT_MONTH_SUFFIX = "1!"
_FRONT_MONTH_CONTRACT = 1

# The composite suffix names the data provider (``ES1!:TRADINGVIEW``), not the
# exchange, so the exchange TradingView files each code under lives here.
TRADINGVIEW_EXCHANGE_BY_CODE: dict[str, str] = {
    "ES1!": "CME_MINI",
    "NQ1!": "CME_MINI",
    "YM1!": "CBOT_MINI",
}


def split_futures_symbol(composite: str) -> tuple[str, str, int | None]:
    """Split ``{CODE}:TRADINGVIEW`` into the three arguments ``get_hist`` wants.

    The exchange comes from :data:`TRADINGVIEW_EXCHANGE_BY_CODE`. A continuous
    front-month code carries its contract in the name, which the scraper takes
    as a separate argument instead: ``ES1!:TRADINGVIEW`` becomes
    ``("ES", "CME_MINI", 1)``.

    Raises:
        ValueError: when ``composite`` carries no suffix, or its code has no
            entry in the exchange table. Guessing an exchange would send a
            silently wrong request to an unofficial scraper.
    """
    code, separator, suffix = composite.upper().partition(":")
    if not separator or not suffix:
        raise ValueError(
            f"TradingView needs a composite symbol: {composite!r} is not '{{CODE}}:TRADINGVIEW'"
        )

    exchange = TRADINGVIEW_EXCHANGE_BY_CODE.get(code)
    if exchange is None:
        raise ValueError(
            f"No TradingView exchange known for {code!r} (from {composite!r}); "
            "add it to TRADINGVIEW_EXCHANGE_BY_CODE"
        )

    if code.endswith(_FRONT_MONTH_SUFFIX):
        return code[: -len(_FRONT_MONTH_SUFFIX)], exchange, _FRONT_MONTH_CONTRACT
    return code, exchange, None


def raw_bar_to_bar(raw: RawBar, symbol: str, interval: Interval) -> Bar:
    """Map a :class:`RawBar` to a ``Bar`` with a UTC-aware instant.

    ``tick_count`` is 0: the scraper reports no trade count, and ``Bar`` treats
    a positive count as "this bar was built from ticks", which it was not.
    """
    return Bar(
        symbol=symbol.upper(),
        interval=interval,
        # Aware by construction — Bar's validator rejects a naive datetime.
        datetime=datetime.fromtimestamp(raw.epoch_seconds, tz=UTC),
        open=raw.open,
        high=raw.high,
        low=raw.low,
        close=raw.close,
        volume=raw.volume,
        tick_count=0,
    )
