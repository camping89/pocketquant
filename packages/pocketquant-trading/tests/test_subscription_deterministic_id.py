"""Unit tests for Subscription.deterministic_id — no Mongo, pure hashing.

Includes hash STABILITY assertion: the deterministic_id formula must produce
the SAME id for the same inputs regardless of refactors. Existing subscription
IDs in production depend on the exact hash recipe.
"""

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.trading.domain.subscription import Subscription

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEX_CHARS = frozenset("0123456789abcdef")


def _id(strategy_code: str, symbol: str, interval) -> str:
    return Subscription.deterministic_id(strategy_code, symbol, interval)


# Snapshot of a known good id — locks the hash formula so a future refactor
# can't silently change subscription PKs in production.
def test_back_compat_known_id_hitnrun2_btc_1m():
    """sha256('hitnrun2|BTCUSDT:BINANCE|1m')[:16] must equal this value forever."""
    import hashlib

    raw = "hitnrun2|BTCUSDT:BINANCE|1m"
    expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
    assert Subscription.deterministic_id("hitnrun2", "BTCUSDT:BINANCE", "1m") == expected


# ---------------------------------------------------------------------------
# Stability: same input → same id
# ---------------------------------------------------------------------------


def test_same_input_returns_same_id_case_1():
    a = _id("strategy-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strategy-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    assert a == b


def test_same_input_returns_same_id_case_2():
    a = _id("ma-cross", "ETH-USDT:OKX", Interval.MINUTE_5)
    b = _id("ma-cross", "ETH-USDT:OKX", Interval.MINUTE_5)
    assert a == b


def test_same_input_returns_same_id_case_3():
    a = _id("strat-z", "SOL-USDT:BYBIT", Interval.DAY_1)
    b = _id("strat-z", "SOL-USDT:BYBIT", Interval.DAY_1)
    assert a == b


def test_same_input_returns_same_id_case_4():
    a = _id("rsi-bot", "BNB-USDT:BINANCE", Interval.MINUTE_15)
    b = _id("rsi-bot", "BNB-USDT:BINANCE", Interval.MINUTE_15)
    assert a == b


def test_same_input_returns_same_id_case_5():
    a = _id("bb-strat", "XRP-USDT:KRAKEN", Interval.HOUR_4)
    b = _id("bb-strat", "XRP-USDT:KRAKEN", Interval.HOUR_4)
    assert a == b


# ---------------------------------------------------------------------------
# Uniqueness: different field values → different ids
# ---------------------------------------------------------------------------


def test_different_strategy_id_produces_different_id():
    a = _id("strat-a", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strat-b", "BTC-USDT:BINANCE", Interval.HOUR_1)
    assert a != b


def test_different_symbol_produces_different_id():
    a = _id("strat-x", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strat-x", "ETH-USDT:BINANCE", Interval.HOUR_1)
    assert a != b


def test_different_exchange_produces_different_id():
    a = _id("strat-x", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strat-x", "BTC-USDT:OKX", Interval.HOUR_1)
    assert a != b


def test_different_interval_produces_different_id():
    a = _id("strat-x", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strat-x", "BTC-USDT:BINANCE", Interval.MINUTE_5)
    assert a != b


# ---------------------------------------------------------------------------
# Format: exactly 16 lowercase hex chars
# ---------------------------------------------------------------------------


def test_id_is_16_chars():
    result = _id("strat-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    assert len(result) == 16


def test_id_is_all_lowercase_hex():
    result = _id("strat-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    assert all(c in _HEX_CHARS for c in result), f"Non-hex chars in: {result}"


# ---------------------------------------------------------------------------
# Normalisation: symbol case-insensitive
# ---------------------------------------------------------------------------


def test_symbol_uppercase_normalised():
    lower = _id("s", "btc-usdt:okx", Interval.HOUR_1)
    upper = _id("s", "BTC-USDT:OKX", Interval.HOUR_1)
    assert lower == upper


def test_exchange_uppercase_normalised():
    a = _id("s", "BTC-USDT:binance", Interval.HOUR_1)
    b = _id("s", "BTC-USDT:BINANCE", Interval.HOUR_1)
    assert a == b


def test_interval_as_string_vs_enum_equal():
    """deterministic_id accepts both Interval enum and its string value."""
    a = _id("strat-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    b = _id("strat-1", "BTC-USDT:BINANCE", "1h")
    assert a == b
