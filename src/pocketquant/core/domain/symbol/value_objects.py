from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pocketquant.core.domain.shared.enums import AssetClass

# Calendar identifiers. These are REFERENCES persisted on the symbol record; the
# schedule rules stay in code behind ITradingCalendarPort, because venue holidays
# and session changes are code, not data.
CALENDAR_CRYPTO_24_7 = "CRYPTO_24_7"
# Exness CFD sessions: FX, gold with its daily break, and 24/7 crypto. Exness
# weeks open on Sunday, so BTCUSD cannot share CALENDAR_CRYPTO_24_7.
CALENDAR_EXNESS_FX = "EXNESS_FX"
CALENDAR_EXNESS_XAUUSD = "EXNESS_XAUUSD"
CALENDAR_EXNESS_CRYPTO = "EXNESS_CRYPTO"


# Contract units are data, not an assumption: crypto spot can treat price * quantity as
# notional, but one XAUUSD lot is 100 oz, size moves in lot steps and prices snap to a tick.
@dataclass(frozen=True)
class ContractSpec:
    # Account currency per 1.0 of price move, per contract.
    multiplier: float = 1.0
    # 0.0 means no tick rounding.
    tick_size: float = 0.0
    # None allows fractional size; 1.0 forces whole contracts.
    lot_step: float | None = None
    currency: str = "USD"
    # None falls back to the percentage commission model.
    commission_per_contract: float | None = None

    @property
    def is_contract(self) -> bool:
        return self.multiplier != 1.0

    def to_mongo(self) -> dict[str, Any]:
        return {
            "multiplier": self.multiplier,
            "tick_size": self.tick_size,
            "lot_step": self.lot_step,
            "currency": self.currency,
            "commission_per_contract": self.commission_per_contract,
        }

    # Linear units for a pre-migration document.
    @classmethod
    def from_mongo(cls, doc: dict[str, Any] | None) -> ContractSpec:
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


DEFAULT_CALENDAR_BY_ASSET_CLASS: dict[AssetClass, str] = {
    AssetClass.CRYPTO_SPOT: CALENDAR_CRYPTO_24_7,
    AssetClass.CRYPTO_PERP: CALENDAR_CRYPTO_24_7,
    AssetClass.CFD: CALENDAR_EXNESS_FX,
}
