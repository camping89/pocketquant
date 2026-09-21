"""Contract units and calendar references, keyed by asset class.

Crypto spot is priced one-for-one in the quote currency, so the pipeline could
treat ``price * quantity`` as notional. A futures contract cannot: one ES point
is 50 USD, size moves in whole contracts, and prices snap to a tick. Making
those units data rather than an assumption is what lets one pipeline serve both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pocketquant.core.domain.shared.enums import AssetClass

# Calendar identifiers. These are REFERENCES persisted on the symbol record; the
# schedule rules themselves stay in code behind ITradingCalendarPort, because CME
# holidays and early closes change yearly and a stored copy would have to be
# hand-synchronised against CME notices.
CALENDAR_CRYPTO_24_7 = "CRYPTO_24_7"
CALENDAR_CME_GLOBEX_EQUITY = "CME_GLOBEX_EQUITY"


@dataclass(frozen=True)
class ContractSpec:
    """How much one unit of an instrument is worth, and how it may be sized."""

    multiplier: float = 1.0
    """Account currency per 1.0 of price move, per contract."""

    tick_size: float = 0.0
    """Minimum price increment; 0.0 means no tick rounding."""

    lot_step: float | None = None
    """Size increment; None allows fractional size, 1.0 forces whole contracts."""

    currency: str = "USD"

    commission_per_contract: float | None = None
    """None falls back to the percentage commission model."""

    def to_mongo(self) -> dict[str, Any]:
        return {
            "multiplier": self.multiplier,
            "tick_size": self.tick_size,
            "lot_step": self.lot_step,
            "currency": self.currency,
            "commission_per_contract": self.commission_per_contract,
        }

    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> ContractSpec:
        """Rebuild a spec, falling back to linear units for a pre-migration document."""
        if not doc:
            return LINEAR_SPEC
        return cls(
            multiplier=doc.get("multiplier", 1.0),
            tick_size=doc.get("tick_size", 0.0),
            lot_step=doc.get("lot_step"),
            currency=doc.get("currency", "USD"),
            commission_per_contract=doc.get("commission_per_contract"),
        )


LINEAR_SPEC = ContractSpec()
"""One-for-one units: what crypto spot and perps have always implicitly used."""


DEFAULT_CALENDAR_BY_ASSET_CLASS: dict[AssetClass, str] = {
    AssetClass.CRYPTO_SPOT: CALENDAR_CRYPTO_24_7,
    AssetClass.CRYPTO_PERP: CALENDAR_CRYPTO_24_7,
    AssetClass.INDEX_FUTURE: CALENDAR_CME_GLOBEX_EQUITY,
}

DEFAULT_SPEC_BY_ASSET_CLASS: dict[AssetClass, ContractSpec] = {
    AssetClass.CRYPTO_SPOT: LINEAR_SPEC,
    AssetClass.CRYPTO_PERP: LINEAR_SPEC,
    # Per-symbol multipliers (ES 50, NQ 20, YM 5) are set at seed time; this is
    # only the shape every index future shares.
    AssetClass.INDEX_FUTURE: ContractSpec(
        multiplier=1.0, tick_size=0.25, lot_step=1.0, currency="USD"
    ),
}
