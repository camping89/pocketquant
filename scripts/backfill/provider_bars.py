from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from pocketquant.app.di import create_container
from pocketquant.core.config import get_settings
from pocketquant.core.domain.bar.entities import SOURCE_REST_BACKFILL
from pocketquant.core.domain.market_data.data_provider_port import IDataProviderPort
from pocketquant.core.domain.market_data.provider_routing_domain_service import (
    UnknownDataProviderError,
)
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.exness.exness_client import ExnessApiError
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

_CHUNK = 5000


@dataclass(frozen=True)
class BackfillConfig:
    symbol: str
    interval: Interval
    days: int
    rate_fraction: float
    dry_run: bool


def parse_args(argv: list[str]) -> BackfillConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Deep backfill of one composite symbol through the routed data provider its"
            " suffix names (XAUUSD:EXNESS -> Exness), beyond the 5000-bar request cap."
        ),
        epilog="""\
Example:
    uv run python scripts/backfill/provider_bars.py \\
        --symbol XAUUSD:EXNESS --interval 1m --days 30 [--rate-fraction 0.5] [--dry-run]

On the VPS: docker exec pocketquant-app python scripts/backfill/provider_bars.py ...

Uses --rate-fraction of the Exness request rate, shared with the running app.
Refuses to run while EXNESS_LIVE_TRADING is true.

Prints one line: fetched=<n> inserted=<n> total_bars=<n> (total_bars=-1 on a dry run).

Exit codes: 0 = bars fetched; 1 = nothing fetched or a provider error;
2 = no data provider for the symbol; 3 = refused because live trading is on.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", required=True, help="composite, e.g. XAUUSD:EXNESS")
    parser.add_argument("--interval", required=True, choices=[i.value for i in Interval])
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--rate-fraction", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not 0 < args.rate_fraction <= 1:
        parser.error("--rate-fraction must be in (0, 1]")
    return BackfillConfig(
        symbol=args.symbol.upper(),
        interval=Interval(args.interval),
        days=args.days,
        rate_fraction=args.rate_fraction,
        dry_run=args.dry_run,
    )


async def run(cfg: BackfillConfig) -> int:
    settings = get_settings()
    # A backfill must never compete with order calls for the Exness request rate.
    if settings.exness_live_trading:
        print("refusing: EXNESS_LIVE_TRADING is true")
        return 3
    # The two processes do not share a pacer, so this one takes only a fraction of the
    # rate and the client's bounded 429 retries absorb an overlap. Only the data port
    # and the bar repository are resolved, so no scheduler or job starts.
    container = create_container(
        settings.model_copy(update={"exness_rate_fraction": cfg.rate_fraction})
    )
    try:
        provider = await container.get(IDataProviderPort)
        n_bars = cfg.days * 86400 // INTERVAL_SECONDS[cfg.interval]
        try:
            bars = await provider.fetch_ohlcv(cfg.symbol, cfg.interval, n_bars)
        except UnknownDataProviderError:
            print(f"no data provider for {cfg.symbol}")
            return 2
        except ExnessApiError as exc:
            print(exc.code)
            return 1
        inserted, total = 0, -1
        if not cfg.dry_run:
            repo = await container.get(BarRepository)
            for start in range(0, len(bars), _CHUNK):
                chunk = bars[start : start + _CHUNK]
                inserted += await repo.insert_many(chunk, source=SOURCE_REST_BACKFILL)
            total = await repo.count(cfg.symbol, cfg.interval)
        print(f"fetched={len(bars)} inserted={inserted} total_bars={total}")
        return 0 if bars else 1
    finally:
        await container.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    raise SystemExit(main())
