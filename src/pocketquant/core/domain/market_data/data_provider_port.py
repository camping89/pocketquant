"""Data-provider port — REST/historical OHLCV fetch + symbol search.

Neutral domain location so no concrete provider implementation (Binance, OKX,
TradingView, etc.) is implied by the module path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval


class IDataProviderPort(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[Bar]:
        """Fetch OHLCV bars from data provider. ``symbol`` is composite ``{code}:{exchange}``."""
        ...

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
    ) -> list[dict]: ...

    @abstractmethod
    async def close(self) -> None: ...
