"""Shared path-parameter validation for composite symbol identifier.

Composite symbol format: ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).
URL clients must percent-encode ``:`` as ``%3A``; FastAPI auto-decodes before
the value reaches this validator.
"""

from fastapi import HTTPException

from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN


def validate_composite_symbol(symbol: str) -> str:
    """Normalise and validate a composite ``{code}:{exchange}`` path value.

    Uppercases, then checks against COMPOSITE_SYMBOL_PATTERN.
    Raises HTTP 400 with INVALID_SYMBOL_FORMAT if validation fails.

    Returns:
        Upper-cased composite symbol string.
    """
    symbol = symbol.upper()
    if not COMPOSITE_SYMBOL_PATTERN.match(symbol):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_SYMBOL_FORMAT", "field": "symbol"},
        )
    return symbol
