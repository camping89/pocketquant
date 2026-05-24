"""Command for backfilling historical bars for a tracked symbol."""

from __future__ import annotations

from pocketquant.api.common.symbol_validation import COMPOSITE_SYMBOL_PATTERN
from pocketquant.core.domain.shared.enums import Interval
from pydantic import BaseModel, Field, field_validator

# Intervals that default to cascade mode (derived from 1m source).
_CASCADE_DEFAULT_TFS = {
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
}


class BackfillTrackedSymbolCommand(BaseModel):
    """Backfill historical bars for one composite symbol.

    ``symbol`` is composite ``{code}:{exchange}`` (e.g. ``BTCUSDT:BINANCE``).

    mode=cascade  — REST-fetch 1m bars (n * tf_minutes), upsert, then cascade aggregate.
                    Default for tfs >= 5m.
    mode=direct   — REST-fetch the requested tf directly and upsert.
                    Default for 1m; always used when tf=1m regardless of mode param.
    """

    symbol: str = Field(
        ...,
        min_length=3,
        max_length=65,
        description="Composite symbol e.g. BTCUSDT:BINANCE",
    )
    interval: Interval
    n: int = Field(default=100, ge=1, le=5000, description="Number of bars to backfill")
    mode: str = Field(default="auto", description="cascade | direct | auto")

    @field_validator("symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not COMPOSITE_SYMBOL_PATTERN.match(v):
            raise ValueError("Must be composite {CODE}:{EXCHANGE} format")
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("cascade", "direct", "auto"):
            raise ValueError("mode must be 'cascade', 'direct', or 'auto'")
        return v

    def resolved_mode(self) -> str:
        """Return the effective mode after applying defaults.

        auto → cascade for tfs >= 5m, direct for 1m.
        """
        if self.mode != "auto":
            return self.mode
        return "cascade" if self.interval in _CASCADE_DEFAULT_TFS else "direct"
