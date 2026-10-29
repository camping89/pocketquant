from __future__ import annotations

import argparse
import asyncio
import sys

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import (
    CALENDAR_EXNESS_CRYPTO,
    CALENDAR_EXNESS_FX,
    CALENDAR_EXNESS_XAUUSD,
    ContractSpec,
)
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

SEEDED_FROM = "script"

# Unseeded, a symbol takes its provider's defaults (the Exness FX calendar, no tick
# size), which is wrong for gold (daily break) and BTCUSD (24/7).
# Quantity is in instrument units and lot_step stays None: under the exposure cap a
# 10 000 USD account sizes about 0.24 oz of gold and 894 EUR, both below one recorded
# lot step (1 oz, 1000 EUR), so a grid lot_step would size every signal to zero. The
# Exness broker owns the lot grid. Tick sizes are 10 ** -point_digits from the
# recorded instrument conditions.
SEEDS: list[tuple[str, str, str, ContractSpec]] = [
    (
        "XAUUSD:EXNESS",
        "Gold vs US Dollar (Exness CFD)",
        CALENDAR_EXNESS_XAUUSD,
        ContractSpec(multiplier=1.0, tick_size=0.001, lot_step=None, currency="USD"),
    ),
    (
        "EURUSD:EXNESS",
        "Euro vs US Dollar (Exness CFD)",
        CALENDAR_EXNESS_FX,
        ContractSpec(multiplier=1.0, tick_size=0.00001, lot_step=None, currency="USD"),
    ),
    (
        "BTCUSD:EXNESS",
        "Bitcoin vs US Dollar (Exness CFD)",
        CALENDAR_EXNESS_CRYPTO,
        ContractSpec(multiplier=1.0, tick_size=0.01, lot_step=None, currency="USD"),
    ),
]


# One asset class spans three schedules, so the calendar is always explicit.
def _build(composite: str, name: str, calendar_id: str, spec: ContractSpec) -> Symbol:
    return Symbol.create(
        symbol=composite,
        name=name,
        asset_class=AssetClass.CFD,
        calendar_id=calendar_id,
        contract_spec=spec,
    )


async def seed(apply: bool) -> int:
    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]
    except Exception as exc:
        print(f"Cannot load settings: {type(exc).__name__}", file=sys.stderr)
        return 2

    database = Database()
    await database.connect(settings)
    symbols = SymbolRepository(database)
    tracked = TrackedSymbolRepository(database)

    try:
        for composite, name, calendar_id, spec in SEEDS:
            symbol = _build(composite, name, calendar_id, spec)
            print(
                f"{symbol.symbol:<16} asset_class={symbol.asset_class.value} "
                f"calendar_id={symbol.calendar_id} tick_size={spec.tick_size}"
            )
            if not apply:
                continue
            await symbols.upsert(symbol)
            await tracked.upsert(TrackedSymbol(symbol=symbol.symbol, seeded_from=SEEDED_FROM))

        if not apply:
            print("\nDry run — nothing written. Re-run with --apply to seed.")
            return 0

        print(f"\nSeeded {len(SEEDS)} symbol(s) into symbols + tracked_symbols.")
        return 0
    except Exception as exc:
        print(f"Seeding failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        await database.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the three Exness CFDs into symbols and tracked_symbols.",
        epilog=(
            "Run --apply before the first sync_1m reaches these symbols. No POST"
            " /tracked-symbols call is needed. Dry-run by default; idempotent. Exit codes:"
            " 0 = completed (or dry run); 1 = a write failed; 2 = configuration missing."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="write; default is a dry run")
    return asyncio.run(seed(parser.parse_args().apply))


if __name__ == "__main__":
    raise SystemExit(main())
