"""DTOs for quote operations."""

from dataclasses import dataclass

from src.features.market_data.models.quote import Quote


@dataclass
class QuoteResult:
    """Result of a quote query."""

    symbol: str
    exchange: str
    timestamp: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None

    @classmethod
    def from_quote(cls, quote: Quote) -> QuoteResult:
        return cls(
            symbol=quote.symbol,
            exchange=quote.exchange,
            timestamp=quote.timestamp.isoformat(),
            last_price=quote.last_price,
            bid=quote.bid,
            ask=quote.ask,
            volume=quote.volume,
            change=quote.change,
            change_percent=quote.change_percent,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
        )
