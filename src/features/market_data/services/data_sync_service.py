"""Service for synchronizing market data from providers."""

from datetime import datetime

from src.common.cache import Cache
from src.common.logging import get_logger
from src.config import Settings
from src.features.market_data.models.ohlcv import Interval
from src.features.market_data.models.symbol import SymbolCreate
from src.features.market_data.providers.tradingview import TradingViewProvider
from src.features.market_data.repositories.ohlcv_repository import OHLCVRepository
from src.features.market_data.repositories.symbol_repository import SymbolRepository

logger = get_logger(__name__)


class DataSyncService:
    """Service for synchronizing market data from external providers."""

    def __init__(self, settings: Settings):
        """Initialize the data sync service.

        Args:
            settings: Application settings.
        """
        self._settings = settings
        self._tv_provider = TradingViewProvider(settings)

    async def sync_symbol(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 5000,
    ) -> dict:
        """Synchronize data for a single symbol.

        Fetches data from TradingView and upserts into MongoDB.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.
            n_bars: Number of bars to fetch.

        Returns:
            Sync result with statistics.
        """
        symbol = symbol.upper()
        exchange = exchange.upper()

        logger.info(
            "sync_symbol_start",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
        )

        # Update sync status to syncing
        await OHLCVRepository.update_sync_status(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            status="syncing",
        )

        try:
            # Fetch data from TradingView
            records = await self._tv_provider.fetch_ohlcv(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                n_bars=n_bars,
            )

            if not records:
                await OHLCVRepository.update_sync_status(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval,
                    status="error",
                    error_message="No data returned from provider",
                )
                return {
                    "symbol": symbol,
                    "exchange": exchange,
                    "interval": interval.value,
                    "status": "error",
                    "message": "No data returned from provider",
                    "bars_synced": 0,
                }

            # Upsert records to MongoDB
            upserted_count = await OHLCVRepository.upsert_many(records)

            # Update symbol metadata
            await SymbolRepository.upsert(
                SymbolCreate(
                    symbol=symbol,
                    exchange=exchange,
                    is_active=True,
                )
            )

            # Get updated stats
            total_bars = await OHLCVRepository.get_bar_count(symbol, exchange, interval)
            latest_bar = await OHLCVRepository.get_latest_bar(symbol, exchange, interval)

            # Update sync status
            await OHLCVRepository.update_sync_status(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                status="completed",
                bar_count=total_bars,
                last_bar_at=latest_bar.datetime if latest_bar else None,
            )

            # Invalidate cache for this symbol
            cache_key = f"ohlcv:{symbol}:{exchange}:{interval.value}"
            await Cache.delete_pattern(f"{cache_key}:*")

            result = {
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval.value,
                "status": "completed",
                "bars_synced": upserted_count,
                "total_bars": total_bars,
                "last_bar_at": latest_bar.datetime.isoformat() if latest_bar else None,
            }

            logger.info("sync_symbol_complete", **result)
            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "sync_symbol_error",
                symbol=symbol,
                exchange=exchange,
                interval=interval.value,
                error=error_msg,
            )

            await OHLCVRepository.update_sync_status(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                status="error",
                error_message=error_msg,
            )

            return {
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval.value,
                "status": "error",
                "message": error_msg,
                "bars_synced": 0,
            }

    async def sync_multiple_symbols(
        self,
        symbols: list[dict],
        interval: Interval,
        n_bars: int = 5000,
    ) -> list[dict]:
        """Synchronize data for multiple symbols.

        Args:
            symbols: List of dicts with 'symbol' and 'exchange' keys.
            interval: Time interval.
            n_bars: Number of bars to fetch per symbol.

        Returns:
            List of sync results.
        """
        results = []

        for sym in symbols:
            result = await self.sync_symbol(
                symbol=sym["symbol"],
                exchange=sym["exchange"],
                interval=interval,
                n_bars=n_bars,
            )
            results.append(result)

        return results

    async def get_cached_bars(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Get OHLCV bars with caching.

        Args:
            symbol: Trading symbol.
            exchange: Exchange name.
            interval: Time interval.
            start_date: Optional start date filter.
            end_date: Optional end date filter.
            limit: Maximum number of bars.

        Returns:
            List of OHLCV bar dictionaries.
        """
        symbol = symbol.upper()
        exchange = exchange.upper()

        # Build cache key
        cache_key = f"ohlcv:{symbol}:{exchange}:{interval.value}:{limit}"
        if start_date:
            cache_key += f":from:{start_date.isoformat()}"
        if end_date:
            cache_key += f":to:{end_date.isoformat()}"

        # Try cache first
        cached = await Cache.get(cache_key)
        if cached:
            return cached

        # Fetch from database
        bars = await OHLCVRepository.get_bars(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        # Convert to serializable format
        result = [
            {
                "datetime": bar.datetime.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]

        # Cache the result (5 minutes for recent data)
        await Cache.set(cache_key, result, ttl=300)

        return result

    def close(self) -> None:
        """Close the service and cleanup resources."""
        self._tv_provider.close()
