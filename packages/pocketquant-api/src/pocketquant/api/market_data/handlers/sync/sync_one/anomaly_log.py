"""No-progress sync anomaly log emission.

Single structured WARN per non-progress sync; ERROR exactly once at the moment
the streak crosses the 3× cadence stuck threshold. Subsequent stucks stay at
WARN to avoid alert fatigue during extended provider outages.
"""

from datetime import UTC, datetime

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.logging import get_logger
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.value_objects import Interval

logger = get_logger(__name__)

_STUCK_STREAK_THRESHOLD = 3


def emit_no_progress(
    symbol: str,
    exchange: str,
    interval: Interval,
    *,
    bars_fetched: int,
    filtered_misaligned: int,
    filtered_existing: int,
    attempts: int,
    streak: int,
    latest_bar: Bar | None,
) -> None:
    """Emit anomaly log for a no-progress sync (inserted == 0 with existing data)."""
    cadence = INTERVAL_SECONDS.get(interval.value, 0)
    age_s = (
        int((datetime.now(UTC) - latest_bar.datetime).total_seconds())
        if latest_bar and latest_bar.datetime
        else None
    )
    payload: dict[str, object] = {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval.value,
        "bars_fetched": bars_fetched,
        "filtered_misaligned": filtered_misaligned,
        "filtered_existing": filtered_existing,
        "attempts": attempts,
        "no_progress_streak": streak,
        "last_bar_age_seconds": age_s,
        "cadence_seconds": cadence,
    }
    crossed_threshold = (
        streak == _STUCK_STREAK_THRESHOLD
        and cadence
        and age_s is not None
        and age_s > _STUCK_STREAK_THRESHOLD * cadence
    )
    if crossed_threshold:
        logger.error("market_data.sync.stuck_threshold_crossed", **payload)
    else:
        logger.warning("market_data.sync.no_progress", **payload)
