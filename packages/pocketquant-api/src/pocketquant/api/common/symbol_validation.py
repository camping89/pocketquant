"""Shared path-parameter validation for exchange/symbol pairs.

Enforces a safe character set on all routes that accept {exchange}/{symbol}
path segments — both public SSE routes and admin mutation routes.
"""

import re

from fastapi import HTTPException

# Allowed: uppercase letters, digits, dot, underscore, hyphen — max 32 chars.
# FastAPI auto-decodes %XX → actual chars before reaching path handler,
# so `:` injected via URL-encoding would pass through unless we validate here.
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,32}$")


def validate_symbol_pair(exchange: str, symbol: str) -> tuple[str, str]:
    """Normalise and validate an (exchange, symbol) path pair.

    Uppercases both values first, then checks against SYMBOL_PATTERN.
    Raises HTTP 400 with INVALID_SYMBOL_FORMAT if either value fails.

    Returns:
        (exchange_upper, symbol_upper) — safe, normalised strings.
    """
    exchange = exchange.upper()
    symbol = symbol.upper()

    if not SYMBOL_PATTERN.match(exchange):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_SYMBOL_FORMAT", "field": "exchange"},
        )
    if not SYMBOL_PATTERN.match(symbol):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_SYMBOL_FORMAT", "field": "symbol"},
        )

    return exchange, symbol
