"""A weekly bar opens on Monday, never on the epoch's Thursday.

The in-progress cutoff used to floor the epoch directly: ``floor(now / 604800)``
lands on a Thursday because 1970-01-01 was one. From Thursday to Sunday that put
the cutoff inside the current week, so the partial week-to-date bar was treated
as closed and persisted. Deriving the cutoff from ``get_bar_start`` — the same
alignment the drop filter uses — makes the two impossible to disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start
from pocketquant.core.domain.shared.enums import Interval

# The week opening Monday 2026-06-01 00:00 UTC.
WEEK_OPEN = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "now",
    [
        pytest.param(datetime(2026, 6, 4, 12, 0, tzinfo=UTC), id="thursday"),
        pytest.param(datetime(2026, 6, 5, 12, 0, tzinfo=UTC), id="friday"),
        pytest.param(datetime(2026, 6, 6, 12, 0, tzinfo=UTC), id="saturday"),
        pytest.param(datetime(2026, 6, 7, 23, 59, tzinfo=UTC), id="sunday"),
    ],
)
def test_weekly_cutoff_is_the_monday_that_opened_the_week(now: datetime) -> None:
    cutoff = get_bar_start(now, Interval.WEEK_1)

    assert cutoff == WEEK_OPEN
    assert cutoff <= now
    assert now - cutoff < timedelta(days=7)
