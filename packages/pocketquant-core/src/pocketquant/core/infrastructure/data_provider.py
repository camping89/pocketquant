"""IDataProvider — abstract base class for REST/historical market data providers.

Moved from infrastructure/tradingview/base.py to a neutral path so no concrete
provider implementation (Binance, OKX, etc.) is implied by the module location.
"""

from abc import ABC, abstractmethod

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval


class IDataProvider(ABC):
    """Abstract base class for data providers."""

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
    ) -> list[dict]:
        """Search available symbols."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...
