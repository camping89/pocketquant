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
    """``bar_start`` and ``is_open`` are all the adapter reaches, and both are frozen."""

    def __init__(self, cutoff: datetime, is_open: bool) -> None:
        self._cutoff = cutoff
        self._is_open = is_open

    def bar_start(self, instant: datetime, interval: Interval) -> datetime:  # noqa: ARG002
        return self._cutoff

    def is_open(self, instant: datetime) -> bool:  # noqa: ARG002
        return self._is_open


class _StubCalendarFactory:
    def __init__(self, cutoff: datetime, is_open: bool) -> None:
        self._calendar = _StubCalendar(cutoff, is_open)

    async def for_symbol(self, composite: str) -> _StubCalendar:  # noqa: ARG002
        return self._calendar


def _adapter(
    client: _FakeClient,
    cutoff: datetime | None = None,
    *,
    is_open: bool = False,
    **overrides: Any,
) -> TradingViewAdapter:
    # Far future by default, so nothing is treated as in progress unless a test
    # sets the cutoff itself. Shut by default so the delayed-frontier drop stays
    # out of the way of tests about clamping, splitting and ordering; the tests
    # that are about that drop open the market explicitly.
    far_future = datetime(2099, 1, 1, tzinfo=UTC)
    factory = _StubCalendarFactory(cutoff or far_future, is_open)
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


async def test_delayed_feed_drops_the_vendor_frontier_bar_while_open() -> None:
    """On a delayed feed the newest bar is still forming, whatever our clock says.

    Measured on the free plan: the newest 1m bar was 633 seconds behind and its
    close and volume both moved between two fetches 75 seconds apart. Our cutoff
    cannot see that, because it is derived from our own clock and the bar sits
    well before it.
    """
    raws = _raw_bars()
    bars = await _adapter(_FakeClient(), is_open=True).fetch_ohlcv(_ES, Interval.HOUR_1, 10)

    assert len(bars) == len(raws) - 1
    newest_epoch = max(r.epoch_seconds for r in raws)
    assert all(b.datetime is not None and b.datetime.timestamp() != newest_epoch for b in bars)


async def test_delayed_feed_keeps_the_frontier_bar_once_the_market_shuts() -> None:
    """A shut market's frontier bar is complete, and stays the frontier.

    Dropping it while shut would never persist the last bar of any session — a
    permanent one-bar gap per session for the integrity scan to report forever.
    """
    bars = await _adapter(_FakeClient(), is_open=False).fetch_ohlcv(_ES, Interval.HOUR_1, 10)

    assert len(bars) == len(_raw_bars())


async def test_a_realtime_plan_keeps_the_frontier_bar() -> None:
    """The positional drop is a delayed-feed remedy, not a permanent tax.

    On a real-time feed the timestamp cutoff already excludes the forming bar, so
    dropping by position too would throw away a closed one.
    """
    bars = await _adapter(
        _FakeClient(), is_open=True, tradingview_plan="cme_non_pro"
    ).fetch_ohlcv(_ES, Interval.HOUR_1, 10)

    assert len(bars) == len(_raw_bars())
