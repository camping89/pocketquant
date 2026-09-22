"""``TvDatafeedClient`` tests — the two things the mapper suite cannot reach.

Task 3's own Verify points at the mapper tests, which never construct this
client, so nothing there would notice if the epoch recovery or the concurrency
guard were removed. Both are pinned here against a fake scraper.

The re-entrancy test is the important one. Upstream ``get_hist`` assigns
``self.ws`` and then reads from it, and shares one ``chart_session`` across every
call, so two concurrent calls on one instance let the loser read the winner's
series — ES bars stored under NQ. Every such bar is individually well-formed, so
alignment, deduplication and the integrity scan all pass it.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
from tvDatafeed import TvDatafeed

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.tradingview.tvdatafeed_client import TvDatafeedClient

_FIXTURE = Path(__file__).parent / "fixtures" / "es_1h_raw.json"
_UNAUTHORIZED = "unauthorized_user_token"  # noqa: S105 — upstream's sentinel


def _epochs() -> list[float]:
    return [row["epoch_seconds"] for row in json.loads(_FIXTURE.read_text())]


def _naive_local_frame(epochs: list[float]) -> pd.DataFrame:
    """A frame shaped exactly like ``__create_df`` builds one: naive host-local.

    This is the trap in fixture form. The index carries no timezone, so its
    meaning depends on the zone of the process that built it.
    """
    index = pd.DatetimeIndex(
        [datetime.fromtimestamp(e) for e in epochs],  # noqa: DTZ006 — mirrors the library
        name="datetime",
    )
    return pd.DataFrame(
        {
            "symbol": ["CME_MINI:ES1!"] * len(epochs),
            "open": [5810.0] * len(epochs),
            "high": [5820.0] * len(epochs),
            "low": [5800.0] * len(epochs),
            "close": [5815.0] * len(epochs),
            "volume": [1000.0] * len(epochs),
        },
        index=index,
    )


class _FakeTv:
    """Stands in for ``TvDatafeed``, recording calls and refusing to overlap."""

    def __init__(self, frame: pd.DataFrame | None, token: str = _UNAUTHORIZED) -> None:
        self.token = token
        self._frame = frame
        self.calls: list[dict[str, object]] = []
        self.overlapped = False
        self._active = 0
        self._guard = threading.Lock()

    def get_hist(self, **kwargs: object) -> pd.DataFrame | None:
        with self._guard:
            self._active += 1
            self.calls.append(kwargs)
            if self._active > 1:
                self.overlapped = True
        # Widen the window: without a lock the two to_thread workers overlap here.
        time.sleep(0.05)
        with self._guard:
            self._active -= 1
        return self._frame


def _client(fake: _FakeTv, **overrides: Any) -> TvDatafeedClient:
    settings = Settings(**overrides)  # pyright: ignore[reportCallIssue]
    # cast: _FakeTv duck-types only the two members the client touches (token and
    # get_hist), which is the point — the real class opens a websocket.
    return TvDatafeedClient(
        settings=settings,
        factory=cast("Callable[..., TvDatafeed]", lambda **_: fake),
    )


async def test_naive_index_recovers_the_true_epoch() -> None:
    """The recovered epoch matches the source epoch, whatever ``TZ`` says.

    Run under the timezone matrix: reading the naive index as if it were UTC
    passes under ``TZ=UTC`` and is wrong by the host offset everywhere else.
    """
    epochs = _epochs()
    fake = _FakeTv(_naive_local_frame(epochs))
    bars = await _client(fake).fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 10, 1)

    assert [b.epoch_seconds for b in bars] == epochs


async def test_concurrent_fetches_never_re_enter_get_hist() -> None:
    """One scraper instance serves one call at a time.

    ``sync_verify_cascade`` fires at :00:00 and ``sync_1m`` at :00:02, and
    APScheduler's ``max_instances=1`` is per job, so this overlap happens in
    production rather than only in a test.
    """
    fake = _FakeTv(_naive_local_frame(_epochs()))
    client = _client(fake)

    await asyncio.gather(
        client.fetch_bars("ES", "CME_MINI", Interval.MINUTE_1, 10, 1),
        client.fetch_bars("NQ", "CME_MINI", Interval.MINUTE_1, 10, 1),
    )

    assert len(fake.calls) == 2, "both fetches must reach the scraper"
    assert not fake.overlapped, "get_hist was re-entered — one call can read another's series"


async def test_symbol_and_contract_reach_get_hist_unchanged() -> None:
    fake = _FakeTv(_naive_local_frame(_epochs()))
    await _client(fake).fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 42, 1)

    call = fake.calls[0]
    assert call["symbol"] == "ES"
    assert call["exchange"] == "CME_MINI"
    assert call["n_bars"] == 42
    assert call["fut_contract"] == 1


async def test_none_result_becomes_an_empty_list() -> None:
    """``get_hist`` returns None when its response regex finds no series."""
    fake = _FakeTv(None)
    assert await _client(fake).fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 10, 1) == []


async def test_unauthorized_token_is_not_authenticated() -> None:
    """Authentication is a property of the token value, not of a raised error.

    Upstream ``__auth`` swallows every exception and the constructor substitutes
    this sentinel, so nothing raises on a failed login.
    """
    fake = _FakeTv(_naive_local_frame(_epochs()), token=_UNAUTHORIZED)
    client = _client(fake)

    assert client.is_authenticated() is False  # no client built yet
    await client.fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 1, 1)
    assert client.is_authenticated() is False


async def test_a_real_token_is_authenticated() -> None:
    fake = _FakeTv(_naive_local_frame(_epochs()), token="a-real-looking-token")
    client = _client(fake)
    await client.fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 1, 1)

    assert client.is_authenticated() is True


async def test_configured_auth_token_overrides_the_login_result() -> None:
    """A supplied token wins: it is the way past a login the scraper has broken."""
    fake = _FakeTv(_naive_local_frame(_epochs()), token=_UNAUTHORIZED)
    client = _client(fake, tradingview_auth_token="supplied-token")
    await client.fetch_bars("ES", "CME_MINI", Interval.HOUR_1, 1, 1)

    assert fake.token == "supplied-token"
    assert client.is_authenticated() is True
