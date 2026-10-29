from fastapi import HTTPException

from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN


# URL clients send the `:` of a composite symbol as `%3A`; FastAPI decodes it
# before the value reaches this validator.
def validate_composite_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not COMPOSITE_SYMBOL_PATTERN.match(symbol):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_SYMBOL_FORMAT", "field": "symbol"},
        )
    return symbol
