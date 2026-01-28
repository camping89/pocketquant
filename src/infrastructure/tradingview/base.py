from abc import ABC, abstractmethod

from src.features.market_data.models.ohlcv import Interval, OHLCVCreate


class IDataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 1000,
    ) -> list[OHLCVCreate]:
        """Fetch OHLCV bars from data provider."""
        ...

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[dict]:
        """Search available symbols."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...
