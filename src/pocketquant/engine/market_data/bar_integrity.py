"""Bar integrity: calendar-aware gap and alignment checks, repair, and cascade verification.

All functions accept composite ``symbol`` (``{code}:{exchange}``) — no separate exchange param.
Grid slots outside the symbol's trading sessions are not expected, so they never count as gaps.
"""

from datetime import UTC, datetime, timedelta

from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.services.bar_builder import get_bar_start, is_bar_aligned
from pocketquant.core.domain.market_data.interfaces import IDataProvider
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.market_data.sync_policy import ALWAYS_OPEN, MarketCalendar
from pocketquant.engine.market_data.sync_service import SyncService, SyncSymbolCommand

logger = get_logger(__name__)

# Verify cascade thresholds (per-field).
# Price relative threshold catches scale-aware drift across assets:
#   BTC $80k → $8 trigger; ETH $3k → $0.30 trigger.
# Volume gets its own threshold because exchange-side rounding is noisier than price.
PRICE_THRESHOLD_PCT = 0.0001  # 0.01%
VOLUME_THRESHOLD_PCT = 0.05  # 5%
DIVERGENCE_ALERT_FRACTION = 0.05  # alert when >5% of compared bars diverge on any field


def _group_gaps(missing: list[datetime], step: timedelta) -> list[tuple[datetime, datetime]]:
    if not missing:
        return []
    ranges: list[tuple[datetime, datetime]] = []
    start = missing[0]
    prev = missing[0]
    for ts in missing[1:]:
        if ts - prev > step:
            ranges.append((start, prev))
            start = ts
        prev = ts
    ranges.append((start, prev))
    return ranges


async def check_integrity(
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
    days_back: int = 7,
    calendar: MarketCalendar = ALWAYS_OPEN,
) -> dict:
    """Check bar alignment + gaps for composite ``symbol``.

    Returns misaligned docs, missing count, gap ranges. Only slots where ``calendar`` is
    open are expected.
    """
    # Grid ends at last CLOSED bar — current incomplete bar can't exist in DB yet
    now = datetime.now(UTC).replace(tzinfo=None)
    end = get_bar_start(now, interval)
    start = end - timedelta(days=days_back)
    docs = await bar_repo.find_datetimes(symbol, interval, start, end)

    misaligned, aligned_times = [], set()
    for d in docs:
        if is_bar_aligned(d["datetime"], interval):
            aligned_times.add(d["datetime"])
        else:
            misaligned.append(d)

    step = timedelta(seconds=INTERVAL_SECONDS[interval])
    expected = {
        t
        for t in (start + i * step for i in range(int((end - start) / step)))
        if calendar.is_open(t)
    }

    missing = sorted(expected - aligned_times)
    gap_ranges = _group_gaps(missing, step)

    return {
        "symbol": symbol.upper(),
        "interval": interval.value,
        "total": len(docs),
        "misaligned_count": len(misaligned),
        "misaligned_ids": [str(d["_id"]) for d in misaligned],
        "missing_count": len(missing),
        "gap_ranges": [(s.isoformat(), e.isoformat()) for s, e in gap_ranges],
    }


async def repair_integrity(
    symbol: str,
    interval: Interval,
    bar_repo: BarRepository,
    sync_service: SyncService,
    *,
    source: str,
    days_back: int = 7,
    calendar: MarketCalendar = ALWAYS_OPEN,
) -> dict:
    """Delete misaligned bars + resync gaps via sync pipeline (skip_filter=True).

    ``symbol`` is composite ``{code}:{exchange}``.
    """
    report = await check_integrity(symbol, interval, bar_repo, days_back, calendar)

    deleted = 0
    if report["misaligned_ids"]:
        deleted = await bar_repo.delete_many_by_ids(report["misaligned_ids"])

    resynced = 0
    if report["gap_ranges"]:
        try:
            command = SyncSymbolCommand(
                symbol=symbol, interval=interval, n_bars=5000, skip_filter=True, source=source
            )
            await sync_service.sync_one(command)
            resynced = len(report["gap_ranges"])
        except Exception as e:
            logger.error(
                "integrity.resync_failed",
                symbol=symbol,
                interval=interval.value,
                error=str(e),
            )

    verify = await check_integrity(symbol, interval, bar_repo, days_back, calendar)
    still_missing = verify["missing_count"]
    still_missing_ranges = verify["gap_ranges"]

    if still_missing > 0:
        logger.warning(
            "integrity.repair.still_missing",
            symbol=symbol,
            interval=interval.value,
            still_missing=still_missing,
            ranges=still_missing_ranges,
        )

    return {
        "symbol": symbol.upper(),
        "interval": interval.value,
        "deleted": deleted,
        "gaps_resynced": resynced,
        "missing_before": report["missing_count"],
        "still_missing": still_missing,
        "still_missing_ranges": still_missing_ranges,
    }


def _diff_pct(a: float, b: float) -> float:
    if abs(a) < 1e-12:
        return 0.0
    return abs(a - b) / abs(a)


def compare_bar_fields(rest_bar, db_bar) -> dict[str, bool]:  # noqa: ANN001
    """Per-field divergence map (True == divergent beyond threshold).

    Pure function to keep `sync_verify_cascade` thin and unit-testable. Price
    fields share PRICE_THRESHOLD_PCT; volume gets its looser VOLUME_THRESHOLD_PCT.
    """
    return {
        "open": _diff_pct(rest_bar.open, db_bar.open) > PRICE_THRESHOLD_PCT,
        "high": _diff_pct(rest_bar.high, db_bar.high) > PRICE_THRESHOLD_PCT,
        "low": _diff_pct(rest_bar.low, db_bar.low) > PRICE_THRESHOLD_PCT,
        "close": _diff_pct(rest_bar.close, db_bar.close) > PRICE_THRESHOLD_PCT,
        "volume": _diff_pct(rest_bar.volume, db_bar.volume) > VOLUME_THRESHOLD_PCT,
    }


async def verify_one_symbol(
    symbol: str,
    *,
    provider: IDataProvider,
    bar_repo: BarRepository,
) -> dict:
    """Compare REST 5m bars against cascade-stored 5m bars for composite ``symbol``.

    Returns a per-symbol summary dict with compared / divergence_count / sample_divergences.
    Raises on REST/DB failures so the caller can record per-symbol error state.
    """
    rest_bars = await provider.fetch_ohlcv(
        symbol=symbol,
        interval=Interval.MINUTE_5,
        n_bars=12,
    )
    if not rest_bars:
        return {"symbol": symbol, "compared": 0, "rest_empty": True}

    oldest_rest = min(b.datetime for b in rest_bars if b.datetime)
    newest_rest = max(b.datetime for b in rest_bars if b.datetime)
    cascade_bars = await bar_repo.find(
        symbol=symbol,
        interval=Interval.MINUTE_5,
        start_date=oldest_rest,
        end_date=newest_rest + timedelta(minutes=5),
        limit=20,
    )
    if not cascade_bars:
        return {"symbol": symbol, "compared": 0, "cascade_empty": True}

    cascade_by_dt: dict = {b.datetime: b for b in cascade_bars if b.datetime}

    compared = 0
    divergence_count = 0
    samples: list[dict] = []
    for rest_bar in rest_bars:
        if not rest_bar.datetime:
            continue
        cascade_bar = cascade_by_dt.get(rest_bar.datetime)
        if cascade_bar is None:
            continue
        compared += 1
        fields_diff = compare_bar_fields(rest_bar, cascade_bar)
        if any(fields_diff.values()):
            divergence_count += 1
            if len(samples) < 3:
                samples.append({"datetime": rest_bar.datetime.isoformat(), "fields": fields_diff})

    return {
        "symbol": symbol,
        "compared": compared,
        "divergence_count": divergence_count,
        "samples": samples,
    }
