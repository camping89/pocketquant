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
    ) -> list[Bar]: ...

    @abstractmethod
    async def search_symbols(
        self,
        query: str,
    ) -> list[dict]: ...

    @abstractmethod
    async def close(self) -> None: ...
