"""Centralized constants with prefixed sections for discoverability."""

# ============================================================
# COLLECTIONS - MongoDB collection names
# ============================================================
COLLECTION_OHLCV = "ohlcv"
COLLECTION_SYNC_STATUS = "sync_status"
COLLECTION_SYMBOLS = "symbols"

# ============================================================
# CACHE_KEYS - Redis key patterns (use .format() for interpolation)
# ============================================================
CACHE_KEY_QUOTE_LATEST = "quote:latest:{exchange}:{symbol}"
CACHE_KEY_BAR_CURRENT = "bar:current:{exchange}:{symbol}:{interval}"
CACHE_KEY_OHLCV = "ohlcv:{symbol}:{exchange}:{interval}:{limit}"

# ============================================================
# TTL - Cache time-to-live (seconds)
# ============================================================
TTL_QUOTE_LATEST = 60
TTL_BAR_CURRENT = 300
TTL_OHLCV_QUERY = 300
TTL_DEFAULT = 3600

# ============================================================
# LIMITS - System constraints
# ============================================================
LIMIT_TVDATAFEED_MAX_BARS = 5000
LIMIT_BULK_SYNC_MAX = 50
LIMIT_OHLCV_QUERY_MAX = 5000

# ============================================================
# HEADERS - HTTP header names
# ============================================================
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"

# ============================================================
# INTERVALS - Time intervals in seconds (for bar aggregation)
# ============================================================
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1M": 2592000,
}
