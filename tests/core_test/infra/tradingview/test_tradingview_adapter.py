"""``TradingViewAdapter`` tests — entitlement cap, symbol split, in-progress drop.

No network and no clock dependence: the client is a fake and the calendar is a
stub whose ``bar_start`` returns a fixed instant, so the in-progress cutoff is an
input to the test rather than whatever the machine's wall clock says.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.tradingview.tradingview_adapter import TradingViewAdapter
from pocketquant.core.infra.tradingview.tradingview_client_interface import RawBar

_FIXTURE = Path(__file__).parent / "fixtures" / "es_1h_raw.json"
_ES = "ES1!:CME_MINI"


def _raw_bars() -> list[RawBar]:
    return [RawBar(**row) for row in json.loads(_FIXTURE.read_text())]


class _FakeClient:
    """Records the arguments it was called with and replays fixture bars."""

    def __init__(self, bars: list[RawBar] | None = None) -> None:
        self._bars = _raw_bars() if bars is None else bars
        self.calls: list[dict[str, object]] = []

    async def fetch_bars(
        self,
        code: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
        fut_contract: int | None,
    ) -> list[RawBar]:
        self.calls.append(
            {
                "code": code,
                "exchange": exchange,
                "interval": interval,
                "n_bars": n_bars,
                "fut_contract": fut_contract,
            }
        )
        return self._bars

    def is_authenticated(self) -> bool:
        return False


class _StubCalendar:
    """Only ``bar_start`` is reached by the adapter, and it is frozen."""

    def __init__(self, cutoff: datetime) -> None:
        self._cutoff = cutoff

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:  # noqa: ARG002
        return self._cutoff


class _StubCalendarFactory:
    def __init__(self, cutoff: datetime) -> None:
        self._calendar = _StubCalendar(cutoff)

    async def for_symbol(self, composite: str) -> _StubCalendar:  # noqa: ARG002
        return self._calendar


def _adapter(
    client: _FakeClient,
    cutoff: datetime | None = None,
    **overrides: Any,
) -> TradingViewAdapter:
    # Far future by default, so nothing is treated as in progress unless a test
    # sets the cutoff itself.
    far_future = datetime(2099, 1, 1, tzinfo=UTC)
    factory = _StubCalendarFactory(cutoff or far_future)
    return TradingViewAdapter(
        client=client,
        settings=Settings(**overrides),  # pyright: ignore[reportCallIssue]
        calendar_factory=cast("TradingCalendarFactory", factory),
    )


async def test_n_bars_is_clamped_to_max_bars() -> None:
    """A request above the plan's entitlement is lowered, never passed through."""
    client = _FakeClient()
    await _adapter(client).fetch_ohlcv(_ES, Interval.HOUR_1, n_bars=99_999)

    assert client.calls[0]["n_bars"] == 5_000


async def test_an_override_lowers_the_cap_further() -> None:
    """An explicit override may only make the request gentler."""
    client = _FakeClient()
    await _adapter(client, tradingview_max_bars=250).fetch_ohlcv(_ES, Interval.HOUR_1, 99_999)

    assert client.calls[0]["n_bars"] == 250


async def test_an_override_cannot_raise_the_cap_above_the_plan() -> None:
    """The load-bearing direction: an override may only ask for less.

    A lower override is operator caution; a higher one would claim an
    entitlement the account does not hold, and 5000 is the scraper's own
    per-request ceiling. An override below the cap cannot detect a missing
    clamp, because it is its own answer either way.
    """
    client = _FakeClient()
    await _adapter(client, tradingview_max_bars=9_999).fetch_ohlcv(_ES, Interval.HOUR_1, 99_999)

    assert client.calls[0]["n_bars"] == 5_000


async def test_futures_symbol_is_split_with_fut_contract_1() -> None:
    client = _FakeClient()
    await _adapter(client).fetch_ohlcv(_ES, Interval.HOUR_1, 10)

    call = client.calls[0]
    assert call["code"] == "ES"
    assert call["exchange"] == "CME_MINI"
    assert call["fut_contract"] == 1


async def test_in_progress_bar_is_dropped() -> None:
    """Bars at or after the current bar's open are still forming."""
    raws = _raw_bars()
    cutoff = datetime.fromtimestamp(raws[4].epoch_seconds, tz=UTC)

    bars = await _adapter(_FakeClient(), cutoff=cutoff).fetch_ohlcv(_ES, Interval.HOUR_1, 10)

    assert len(bars) == 4
    assert all(b.datetime is not None and b.datetime < cutoff for b in bars)


async def test_returned_bars_are_utc_aware_and_ascending() -> None:
    """Fed newest-first, the adapter still returns oldest-first.

    The fixture is already ascending, so a client that replays it in order
    cannot tell a real sort from a missing one. This one hands the bars back
    reversed, which is what makes the assertion load-bearing.
    """
    bars = await _adapter(_FakeClient(bars=list(reversed(_raw_bars())))).fetch_ohlcv(
        _ES, Interval.HOUR_1, 10
    )
    stamps = [b.datetime for b in bars]

    assert len(bars) == 6
    assert all(s is not None and s.tzinfo is UTC for s in stamps)
    assert stamps == sorted(stamps)  # pyright: ignore[reportArgumentType]


async def test_empty_client_result_returns_empty_list() -> None:
    assert await _adapter(_FakeClient(bars=[])).fetch_ohlcv(_ES, Interval.HOUR_1, 10) == []
