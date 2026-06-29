def build_bar_cache_key(symbol: str, interval: str) -> str:
    """Build base bar cache key for pattern matching.

    ``symbol`` is composite ``{code}:{exchange}``.
    """
    return f"ohlcv:{symbol.upper()}:{interval}"


# MongoDB collection names
COLLECTION_BARS = "bars"
COLLECTION_SYNC_STATUS = "sync_status"
COLLECTION_SYMBOLS = "symbols"
COLLECTION_ORDERS = "orders"
COLLECTION_POSITIONS = "positions"
COLLECTION_BACKTEST_RUNS = "backtest_runs"
COLLECTION_BACKTEST_ORDERS = "backtest_orders"
COLLECTION_BACKTEST_TRADES = "backtest_trades"
COLLECTION_JOB_HISTORY = "job_history"
COLLECTION_TRACKED_SYMBOLS = "tracked_symbols"

# Redis key patterns (use .format() for interpolation)
# Symbol values are composite "{code}:{exchange}" - templates kept generic.
CACHE_KEY_QUOTE_LATEST = "quote:latest:{symbol}"
CACHE_KEY_BAR_CURRENT = "bar:current:{symbol}:{interval}"
CACHE_KEY_OHLCV = "ohlcv:{symbol}:{interval}:{limit}"

# Cache time-to-live (seconds)
TTL_QUOTE_LATEST = 60
TTL_BAR_CURRENT = 300
TTL_OHLCV_QUERY = 300
TTL_DEFAULT = 3600

# System constraints
LIMIT_TVDATAFEED_MAX_BARS = 5000
LIMIT_BULK_SYNC_MAX = 50
LIMIT_OHLCV_QUERY_MAX = 5000

# HTTP header names
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"

# Time intervals in seconds (for bar aggregation)
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}
