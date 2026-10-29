from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.exness.exness_mappers import (
    composite_for,
    instrument_name,
    tick_to_quote_dict,
)
from pocketquant.core.infra.exness.exness_stream import ExnessStream

logger = get_logger(__name__)

_TICKS_PATH = "/v1/server-events/accounts/{account_id}/ws/ticks"
_TRADING_DISABLED_MARKERS = ("MARKET_TRADE_DISABLED", "trading_disabled")


class ExnessQuoteAdapter:
    def __init__(self, client: ExnessClient) -> None:
        self._client = client
        # composite symbol -> (instrument name, callback)
        self._subscriptions: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {}
        self._rejected: set[str] = set()
        self._stream: ExnessStream | None = None
        self._last_tick_at: datetime | None = None

    @property
    def last_tick_at(self) -> datetime | None:
        return self._last_tick_at

    # No-op: the connection is made inside run_forever.
    async def connect(self) -> None: ...

    async def disconnect(self) -> None:
        if self._stream is not None:
            await self._stream.close()

    async def subscribe(self, symbol: str, callback: Callable[[dict[str, Any]], Any]) -> str:
        composite = symbol.upper()
        name = instrument_name(composite)
        if name is None or name not in await self._client.instruments():
            # Not stored, so the reconcile loop asks again; warn only the first time.
            if composite not in self._rejected:
                self._rejected.add(composite)
                logger.warning("exness_ws.unknown_instrument", symbol=composite)
            return composite
        self._subscriptions[composite] = (name, callback)
        # The spike recorded that a later subscribe adds to the earlier ones.
        if self.is_connected():
            await self._send_subscribe(f"sub-{name}", [name])
        return composite

    async def unsubscribe(self, symbol: str) -> None:
        # Local only: frames for instruments no longer stored are ignored.
        self._subscriptions.pop(symbol.upper(), None)

    # Idles when Exness is not configured instead of returning or raising: the realtime
    # router gathers every child's run_forever, and one that ends would stop every feed.
    async def run_forever(self) -> None:
        if not self._client.is_configured:
            logger.info("exness_ws.disabled")
            await asyncio.Event().wait()
            return
        self._stream = ExnessStream(
            self._client,
            _TICKS_PATH.format(account_id=self._client.account_id),
            on_message=self._on_frame,
            on_connect=self._resubscribe_all,
            # Ticks pause while the market is closed, so silence is not staleness.
            stale_after_s=None,
        )
        await self._stream.run_forever()

    def is_connected(self) -> bool:
        return self._stream is not None and self._stream.is_connected()

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @property
    def subscriptions(self) -> dict[str, tuple[str, Callable[[dict[str, Any]], Any]]]:
        return self._subscriptions

    async def _send_subscribe(self, request_id: str, names: list[str]) -> None:
        assert self._stream is not None
        await self._stream.send(
            {"id": request_id, "subscribe": {"event": "ticks", "instruments": names}}
        )

    async def _resubscribe_all(self) -> None:
        # A new connection holds no subscription, so re-send every stored one.
        names = [name for name, _ in self._subscriptions.values()]
        if names:
            await self._send_subscribe("sub-all", names)

    async def _on_frame(self, frame: dict[str, Any]) -> None:
        if "error_message" in frame:
            text = str(frame)
            if any(marker in text for marker in _TRADING_DISABLED_MARKERS):
                logger.warning("exness_ws.trading_disabled", id=frame.get("id"))
            else:
                logger.warning("exness_ws.error_frame", id=frame.get("id"), code=frame.get("code"))
            return
        if "instrument" in frame and "bid" in frame and "ask" in frame:
            await self._on_tick(frame)
            return
        if "id" in frame and "code" in frame:
            logger.debug("exness_ws.subscribe_ack", id=frame["id"], code=frame["code"])

    async def _on_tick(self, tick: dict[str, Any]) -> None:
        composite = composite_for(tick["instrument"])
        entry = self._subscriptions.get(composite) if composite else None
        if composite is None or entry is None:
            return
        self._last_tick_at = datetime.now(UTC)
        try:
            result = entry[1](tick_to_quote_dict(tick, composite))
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("exness_ws.callback_failed", symbol=composite, error=type(exc).__name__)
