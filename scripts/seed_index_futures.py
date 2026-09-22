"""Seed the three CME/CBOT continuous index futures into symbols + tracked_symbols.

These are the first non-crypto instruments in the system, and seeding must happen
BEFORE the first sync cycle reaches them. ``SyncService._persist_bars`` returns
early when no bars arrive, so ``SymbolRepository.touch`` is never called; an
unseeded futures symbol is assumed to be crypto spot, routes to a crypto venue
that has no such instrument, receives nothing, and therefore never gets the
document that would have corrected the assumption. See
``core/infra/market_data/symbol_provider_resolver.py``.

The full ``upsert`` is used here rather than ``touch``: this is the deliberate
metadata write, and re-running it is how a corrected multiplier or tick size
reaches an existing document.

Usage:
    uv run python scripts/seed_index_futures.py [--apply]

Dry-run by default: prints what would be written and writes nothing. ``--apply``
performs the upserts. Idempotent — safe to re-run.

Exit codes: 0 = completed (or dry run); 1 = a write failed; 2 = configuration missing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import AssetClass
from pocketquant.core.domain.symbol import Symbol
from pocketquant.core.domain.symbol.value_objects import ContractSpec
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

SEEDED_FROM = "script"

# multiplier = account currency per 1.0 of index move, per contract. These are
# CME/CBOT contract specifications, not preferences.
SEEDS: list[tuple[str, str, ContractSpec]] = [
    (
        "ES1!:CME_MINI",
        "E-mini S&P 500 continuous",
        ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, currency="USD"),
    ),
    (
        "NQ1!:CME_MINI",
        "E-mini Nasdaq-100 continuous",
        ContractSpec(multiplier=20.0, tick_size=0.25, lot_step=1.0, currency="USD"),
    ),
    (
        "YM1!:CBOT_MINI",
        "E-mini Dow continuous",
        ContractSpec(multiplier=5.0, tick_size=1.0, lot_step=1.0, currency="USD"),
    ),
]


def _build(composite: str, name: str, spec: ContractSpec) -> Symbol:
    """A futures Symbol whose calendar is derived from its asset class.

    ``calendar_id`` is deliberately not passed: ``Symbol.create`` derives it from
    ``asset_class``, so the two cannot disagree.
    """
    return Symbol.create(
        symbol=composite,
        name=name,
        asset_class=AssetClass.INDEX_FUTURE,
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
        for composite, name, spec in SEEDS:
            symbol = _build(composite, name, spec)
            print(
                f"{symbol.symbol:<16} asset_class={symbol.asset_class.value} "
                f"calendar_id={symbol.calendar_id} "
                f"multiplier={spec.multiplier} tick_size={spec.tick_size}"
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; default is a dry run")
    return asyncio.run(seed(parser.parse_args().apply))


if __name__ == "__main__":
    raise SystemExit(main())
