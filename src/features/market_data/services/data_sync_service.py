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
    def __init__(self, settings: Settings):
        self._settings = settings
        self._tv_provider = TradingViewProvider(settings)

    async def sync_symbol(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int = 5000,
    ) -> dict:
        symbol = symbol.upper()
        exchange = exchange.upper()

        logger.info(
            "sync_symbol_start",
            symbol=symbol,
            exchange=exchange,
            interval=interval.value,
        )

        await OHLCVRepository.update_sync_status(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            status="syncing",
        )

        try:
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

            upserted_count = await OHLCVRepository.upsert_many(records)
            await SymbolRepository.upsert(
                SymbolCreate(symbol=symbol, exchange=exchange, is_active=True)
            )

            total_bars = await OHLCVRepository.get_bar_count(symbol, exchange, interval)
            latest_bar = await OHLCVRepository.get_latest_bar(symbol, exchange, interval)
            await OHLCVRepository.update_sync_status(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                status="completed",
                bar_count=total_bars,
                last_bar_at=latest_bar.datetime if latest_bar else None,
            )

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
        symbol = symbol.upper()
        exchange = exchange.upper()
        cache_key = f"ohlcv:{symbol}:{exchange}:{interval.value}:{limit}"
        if start_date:
            cache_key += f":from:{start_date.isoformat()}"
        if end_date:
            cache_key += f":to:{end_date.isoformat()}"

        cached = await Cache.get(cache_key)
        if cached:
            return cached

        bars = await OHLCVRepository.get_bars(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

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

        await Cache.set(cache_key, result, ttl=300)

        return result

    def close(self) -> None:
        self._tv_provider.close()
