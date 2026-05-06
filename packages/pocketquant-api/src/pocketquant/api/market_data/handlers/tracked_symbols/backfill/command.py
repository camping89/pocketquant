"""Command for backfilling historical bars for a tracked symbol."""

from __future__ import annotations

import re

from pocketquant.core.domain.shared.enums import Interval
from pydantic import BaseModel, Field, field_validator

_SYMBOL_RE = re.compile(r"^[A-Z0-9._-]+$")

# Intervals that default to cascade mode (derived from 1m source).
_CASCADE_DEFAULT_TFS = {
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
}


class BackfillTrackedSymbolCommand(BaseModel):
    """Backfill historical bars for one tracked symbol.

    mode=cascade  — REST-fetch 1m bars (n * tf_minutes), upsert, then cascade aggregate.
                    Default for tfs >= 5m.
    mode=direct   — REST-fetch the requested tf directly and upsert.
                    Default for 1m; always used when tf=1m regardless of mode param.
    """

    exchange: str = Field(..., min_length=1, max_length=32)
    symbol: str = Field(..., min_length=1, max_length=32)
    interval: Interval
    n: int = Field(default=100, ge=1, le=5000, description="Number of bars to backfill")
    mode: str = Field(default="auto", description="cascade | direct | auto")

    @field_validator("exchange", "symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("Must match ^[A-Z0-9._-]+$")
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
