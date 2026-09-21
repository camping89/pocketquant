"""The app refuses to start unless the process timezone is UTC.

Bars, cron triggers and session calendars are UTC instants by construction. On
a non-UTC process they look correct on the VPS and wrong everywhere else, so
the guard fails startup rather than letting skewed data accumulate.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pocketquant.app.main_extensions import assert_utc_runtime


def test_utc_host_passes(host_timezone: Callable[..., None]) -> None:
    host_timezone("UTC")

    assert_utc_runtime()


def test_non_utc_host_raises(host_timezone: Callable[..., None]) -> None:
    host_timezone("Asia/Ho_Chi_Minh")

    with pytest.raises(RuntimeError, match="must be UTC"):
        assert_utc_runtime()


def test_unresolvable_zone_alias_raises(host_timezone: Callable[..., None]) -> None:
    """A zone the platform cannot resolve must not pass as UTC.

    ``Asia/Saigon`` is a ``tzdata-legacy`` alias absent from Debian/Ubuntu's
    default package. glibc degrades it to UTC, so ``time.timezone`` is 0 and the
    offset check alone would wave it through.
    """
    host_timezone("Asia/Saigon", require_resolved=False)

    with pytest.raises(RuntimeError, match="must be UTC"):
        assert_utc_runtime()
