from fastapi import HTTPException

from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN


def validate_composite_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not COMPOSITE_SYMBOL_PATTERN.match(symbol):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_SYMBOL_FORMAT", "field": "symbol"},
        )
    return symbol
