"""Pure alignment-peek helpers used by retry policy. No I/O."""

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.bar.services.bar_builder import is_bar_aligned
from pocketquant.core.domain.shared.value_objects import Interval


def has_aligned_bar(records: list[Bar], interval: Interval) -> bool:
    """True if at least one record's datetime sits on the interval grid."""
    return any(b.datetime is not None and is_bar_aligned(b.datetime, interval) for b in records)
