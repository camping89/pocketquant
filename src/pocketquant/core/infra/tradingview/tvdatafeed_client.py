"""The real TradingView client, wrapping the synchronous ``tvDatafeed`` scraper.

Three facts about the library shape this module, all read off the installed
package rather than assumed:

**One instance cannot serve two callers.** ``get_hist`` calls
``__create_connection``, which assigns ``self.ws``, and then reads
``self.ws.recv()`` in a loop; ``self.chart_session`` is fixed at construction and
shared by every call. Two concurrent calls therefore overwrite each other's
socket and share one chart session, and the loser reads the winner's series —
bars for one symbol stored under another. That corruption passes bar alignment,
deduplication and the integrity scan, because every bar is individually
well-formed. ``sync_verify_cascade`` fires at ``:00:00`` and ``sync_1m`` at
``:00:02``, and APScheduler's ``max_instances=1`` is per job, so the overlap is
guaranteed rather than hypothetical. A lock serialises every call, which also
means this process never opens two scraper sockets at once — welcome on an
unofficial endpoint that can ban us.

**Login never raises.** The library's ``__auth`` catches every exception and
returns ``None``, and the constructor then substitutes the literal
``"unauthorized_user_token"`` and carries on. So authentication state is a
property of the token value, and an exception handler around construction cannot
observe it.

**The DataFrame index is naive host-local time.** ``__create_df`` builds each
entry with ``datetime.fromtimestamp(...)`` and no timezone, and the raw epoch is
not re-exposed. It is recovered here, at the boundary.

A fourth fact governs the error path: ``get_hist`` returns ``None`` when its
response regex finds no series, and TradingView serves the last N bars whatever
the session state. So an absent series is a rejection rather than a quiet
market, and this client raises instead of returning ``[]`` — see
:class:`TradingViewNoSeriesError`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
from tvDatafeed import TvDatafeed

from pocketquant.core.common.logging import get_logger
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.tradingview.tradingview_client_interface import RawBar
from pocketquant.core.infra.tradingview.tradingview_mappers import INTERVAL_TO_TRADINGVIEW

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

#: The library's own sentinel for "no account behind this session". It assigns
#: this string when login returns no token, so comparing against it is the only
#: way to tell an authenticated session from an anonymous one.
_UNAUTHORIZED_TOKEN = "unauthorized_user_token"  # noqa: S105 — sentinel, not a credential

#: Upstream's sign-in performs ``requests.post`` with NO timeout, and it runs
#: while this client holds its lock. Without a ceiling a stalled sign-in would
#: hold the lock forever, ``sync_1m`` would never finish, APScheduler's
#: per-job ``max_instances=1`` would skip every later tick, and BTC/ETH/SOL
#: would stop syncing — a crypto outage reachable purely from futures config.
_BUILD_TIMEOUT_S = 30.0

#: ``get_hist`` is loosely bounded already (its socket carries a 5s timeout),
#: but the read loop has no overall ceiling. Generous enough for a 5000-bar
#: backfill, small enough that one symbol cannot consume an entire cron cycle.
_FETCH_TIMEOUT_S = 60.0


class TradingViewNoSeriesError(RuntimeError):
    """The response carried no price series.

    Raised rather than reported as an empty market. TradingView returns the last
    N bars whatever the session state, so "no series" is never a quiet venue —
    it is a rejection (bad symbol, entitlement, or rate limit). Returning ``[]``
    here would be indistinguishable from emptiness to ``fetch_with_retry``,
    which retries on empty and would open two more sockets per symbol per
    minute against a venue that has just refused us. Correction 15 settled the
    principle: an outage must not become a successful sync that inserted
    nothing.
    """


class TvDatafeedClient:
    """Runs the blocking scraper off the event loop, one call at a time."""

    def __init__(
        self,
        settings: Settings,
        factory: Callable[..., TvDatafeed] | None = None,
    ) -> None:
        self._settings = settings
        # Injectable so a test can drive the concurrency guard without a network.
        self._factory = factory if factory is not None else TvDatafeed
        self._tv: TvDatafeed | None = None
        # Guards both the lazy construction and every fetch. See the module
        # docstring: the underlying instance holds per-call state on itself.
        self._lock = asyncio.Lock()

    # --- interface -------------------------------------------------------

    async def fetch_bars(
        self,
        code: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
        fut_contract: int | None,
    ) -> list[RawBar]:
        """Up to ``n_bars`` recent bars, serialised against every other fetch."""
        tv_interval = INTERVAL_TO_TRADINGVIEW[interval]

        async with self._lock:
            tv = await self._ensure_client()
            try:
                frame = await asyncio.wait_for(
                    asyncio.to_thread(
                        tv.get_hist,
                        symbol=code,
                        exchange=exchange,
                        interval=tv_interval,
                        n_bars=n_bars,
                        # cast, not a line-level ignore: upstream annotates this
                        # `fut_contract: int = None`, so None is correct at
                        # runtime and wrong per the signature. A `# type: ignore`
                        # here would suppress the whole call and hide a real
                        # break in any other argument, so the lie stays as
                        # narrow as the defect.
                        fut_contract=cast("int", fut_contract),
                    ),
                    timeout=_FETCH_TIMEOUT_S,
                )
            except TimeoutError:
                # Cancelling a to_thread does NOT stop the thread: it keeps
                # running and keeps writing to this instance's `ws`. Reusing the
                # instance would hand the next fetch a socket another thread is
                # still reading — the exact corruption the lock exists to
                # prevent. Discard it so the next call builds a fresh one.
                self._tv = None
                logger.warning(
                    "provider.tradingview.fetch_timeout",
                    code=code,
                    exchange=exchange,
                    interval=interval.value,
                    timeout_seconds=_FETCH_TIMEOUT_S,
                )
                raise

        if frame is None or frame.empty:
            raise TradingViewNoSeriesError(
                f"TradingView returned no series for {exchange}:{code} at {interval.value}"
            )

        bars = [self._to_raw_bar(index, row) for index, row in frame.iterrows()]
        logger.debug(
            "provider.tradingview.fetched",
            code=code,
            exchange=exchange,
            interval=interval.value,
            bars=len(bars),
        )
        return bars

    def is_authenticated(self) -> bool:
        """True when the session holds a real account token.

        Tests the token value rather than trusting a login exception, because
        the library raises none — see the module docstring. False before the
        first fetch, when no client has been built yet.
        """
        if self._tv is None:
            return False
        token = getattr(self._tv, "token", None)
        return bool(token) and token != _UNAUTHORIZED_TOKEN

    # --- internals -------------------------------------------------------

    async def _ensure_client(self) -> TvDatafeed:
        """The underlying client, built on first use. Caller holds the lock."""
        if self._tv is None:
            try:
                self._tv = await asyncio.wait_for(
                    asyncio.to_thread(self._build), timeout=_BUILD_TIMEOUT_S
                )
            except TimeoutError:
                # See _BUILD_TIMEOUT_S: the orphaned thread keeps its own
                # instance, so nothing is reused after a timeout.
                self._tv = None
                logger.warning(
                    "provider.tradingview.build_timeout",
                    timeout_seconds=_BUILD_TIMEOUT_S,
                )
                raise
        return self._tv

    def _build(self) -> TvDatafeed:
        """Construct and authenticate the scraper. Runs on a worker thread.

        A failure here is re-raised rather than degraded to anonymous mode. The
        library's own login failure is not an exception (it yields an
        unauthorized token, reported below as ``status="degraded"``), so
        anything that does raise is a genuine outage — and an outage reported as
        an empty result is how a dead provider becomes a successful sync that
        inserted nothing.
        """
        username = self._settings.tradingview_username
        password = self._settings.tradingview_password
        token = self._settings.tradingview_auth_token

        try:
            if username and password:
                tv = self._factory(username=username, password=password.get_secret_value())
            else:
                tv = self._factory()
        except Exception as exc:
            # Never the credentials, only the type.
            logger.warning(
                "provider.tradingview.auth",
                status="failed",
                error_type=type(exc).__name__,
            )
            raise

        if token is not None:
            # Not a constructor argument upstream; the session reads self.token
            # when it opens. Supplying one directly is the way past a login that
            # the scraper's maintainers have broken before.
            tv.token = token.get_secret_value()

        authenticated = bool(tv.token) and tv.token != _UNAUTHORIZED_TOKEN
        if (username or token) and not authenticated:
            logger.warning(
                "provider.tradingview.auth",
                status="degraded",
                reason="unauthorized_token",
            )
        # One-shot per process, so INFO rather than DEBUG.
        logger.info("provider.tradingview.client_ready", authenticated=authenticated)
        return tv

    @staticmethod
    def _to_raw_bar(index: Any, row: Any) -> RawBar:
        """One DataFrame row as a :class:`RawBar`, recovering the true epoch.

        A naive index entry is interpreted in the host zone — the same zone the
        library built it in — so the round trip recovers the real instant on any
        host, which is what lets the CI timezone matrix pass. An aware entry, if
        a future version produces one, is converted instead of reinterpreted.
        """
        # cast: a DataFrame index entry is typed as Hashable, and pd.Timestamp
        # accepts every shape this index actually holds.
        stamp = cast("datetime", pd.Timestamp(index).to_pydatetime())
        epoch = stamp.timestamp() if stamp.tzinfo is None else stamp.astimezone(UTC).timestamp()
        return RawBar(
            epoch_seconds=epoch,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
