"""Exness broker: market orders with a stop loss, sized in lots, filled from the events stream.

Every live-money rule is enforced before any HTTP call: market orders only, a
stop loss on every open, at most the minimum lot unless ``max_lots`` is raised,
a daily loss cap computed from real deals, and no order until the trading
snapshot is reconciled. ``openPosition`` and ``closePosition`` are acknowledged
asynchronously; the fill arrives on the events stream, or is recovered from the
operation status and the deals history when the stream missed it.

Order calls are additionally refused by the client while ``EXNESS_LIVE_TRADING``
is false, and ``BrokerFactory`` refuses to build this adapter in that case.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.domain.brokers.broker_port import IBrokerPort, OrderCallback, TradeCallback
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import (
    OrderAggregate,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from pocketquant.core.domain.position import PositionAggregate, PositionSide, TradeClosedEvent
from pocketquant.core.infra.exness.exness_client import ExnessApiError, ExnessClient
from pocketquant.core.infra.exness.exness_mappers import (
    composite_for,
    format_price,
    instrument_name,
    lots_to_units,
    units_to_lots,
)
from pocketquant.core.infra.exness.exness_stream import ExnessStream
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)

logger = get_logger(__name__)

_FILL_TIMEOUT_S = 15
_STATUS_POLLS = 4
_PAGE_LIMIT = 200
# Deal types whose profit is realized PnL; ``balance`` (deposits, withdrawals) never counts.
_PNL_DEAL_TYPES = frozenset({"close", "swap_fee", "admin_fee", "dividend"})
_SIDE_BY_DIRECTION = {"buy": PositionSide.LONG, "sell": PositionSide.SHORT}


@dataclass
class _Held:
    """An open Exness position mapped to the subscription that owns it."""

    subscription_id: str
    symbol: str
    side: PositionSide
    units: float
    open_price: float
    opened_at: datetime | None
    sl_price: float | None = None
    tp_price: float | None = None


@dataclass
class _Inflight:
    """An acknowledged order request waiting for its terminal outcome."""

    order: OrderAggregate
    instrument: str
    kind: str  # "open" | "close"
    position_id: str | None
    sent_at: datetime


# A closed position, its close deal and the closed units, emitted once the fill is delivered.
_Trade = tuple[_Held, dict[str, Any], float]


class ExnessBrokerAdapter(IBrokerPort):
    fills_async = True

    def __init__(
        self,
        client: ExnessClient,
        event_bus: EventBus,
        position_repository: PositionRepository,
        daily_loss_cap: float | None,
        max_lots: float | None,
    ) -> None:
        self._client = client
        self._event_bus = event_bus
        self._position_repository = position_repository
        self._daily_loss_cap = daily_loss_cap
        self._max_lots = Decimal(str(max_lots)) if max_lots else None
        self._order_callbacks: list[OrderCallback] = []
        self._trade_callbacks: list[TradeCallback] = []
        self._positions: dict[str, _Held] = {}
        # A snapshot rebuild replaces ``_positions`` across awaits; fills and broker
        # closes that land meanwhile must wait for it rather than write the old dict.
        self._state_lock = asyncio.Lock()
        self._held_unmapped: set[str] = set()
        self._inflight: dict[str, _Inflight] = {}
        self._pending_ack: set[str] = set()
        self._early: dict[str, tuple[OrderResult, _Trade | None]] = {}
        self._acked_at: dict[str, float] = {}
        self._seen_terminal: set[str] = set()
        self._snapshot_ready = False
        self._needs_snapshot = False
        self._currency: str | None = None
        self._stream: ExnessStream | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._connected = False

    @property
    def name(self) -> str:
        return "exness"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._stream = ExnessStream(
            self._client,
            f"/v1/server-events/accounts/{self._client.account_id}/ws/events",
            on_message=self._on_event,
            on_connect=self._on_stream_connect,
            stale_after_s=None,
        )
        self._stream_task = asyncio.create_task(self._stream.run_forever())
        self._connected = True
        logger.info("exness.broker_connected")

    async def disconnect(self) -> None:
        if self._stream is not None:
            await self._stream.close()
        if self._stream_task is not None:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream_task
        self._stream = None
        self._stream_task = None
        self._connected = False
        logger.info("exness.broker_disconnected")

    async def _on_stream_connect(self) -> None:
        self._snapshot_ready = False
        assert self._stream is not None
        await self._stream.send({"id": "tx", "subscribe": {"event": "transactions"}})

    # ── order path ──────────────────────────────────────────────────────────

    async def normalize_quantity(self, symbol: str, quantity: float) -> float | None:
        name = instrument_name(symbol)
        if name is None:
            logger.warning("exness.order_rejected_presubmit", reason="unknown_instrument")
            return None
        cond = await self._client.conditions(name)
        lots = self._lots(quantity, cond)
        if lots is None:
            logger.warning(
                "exness.order_rejected_presubmit",
                reason="below_min_lot",
                quantity=quantity,
                volume_min=cond["volume_min"],
            )
            return None
        contract_size = Decimal(cond["contract_size"])
        if lots < Decimal(str(quantity)) / contract_size:
            logger.warning("exness.lots_clamped", requested=quantity, sent=str(lots))
        return lots_to_units(lots, contract_size)

    def _lots(self, quantity: float, cond: dict[str, Any]) -> Decimal | None:
        return units_to_lots(
            Decimal(str(quantity)),
            contract_size=Decimal(cond["contract_size"]),
            volume_min=Decimal(cond["volume_min"]),
            volume_step=Decimal(cond["volume_step"]),
            volume_max=Decimal(cond["volume_max"]),
            max_lots=self._max_lots,
        )

    async def submit_order(self, order: OrderAggregate) -> OrderResult:
        reason = self._presubmit_reason(order)
        if reason:
            return _rejected(order, reason)
        held = self._held_for(order.subscription_id)
        if held is None:
            return await self._submit_open(order)
        pid, position = held
        if position.side == _position_side(order.side):
            return _rejected(order, "position already open for subscription")
        # An exit skips the stop-loss and loss-cap rules: blocking it would keep the risk open.
        if order.quantity != position.units:
            return _rejected(order, "close quantity must equal the held position")
        return await self._send_tracked(
            "closePosition", order, kind="close", position_id=pid, path_params={"position_id": pid}
        )

    async def _submit_open(self, order: OrderAggregate) -> OrderResult:
        if order.sl_price is None:
            return _rejected(order, "stop loss required")
        reason = await self._loss_cap_reason()
        if reason:
            return _rejected(order, reason)
        name = instrument_name(order.symbol)
        assert name is not None
        cond = await self._client.conditions(name)
        lots = self._lots(order.quantity, cond)
        if lots is None or lots_to_units(lots, Decimal(cond["contract_size"])) != order.quantity:
            logger.warning(
                "exness.order_rejected_presubmit", reason="not_normalized", quantity=order.quantity
            )
            return _rejected(order, "quantity not normalized to the exness lot grid")
        digits = int(cond["point_digits"])
        body: dict[str, Any] = {
            "instrument": name,
            "side": "buy" if order.side == OrderSide.BUY else "sell",
            "volume": str(lots),
            "stop_loss_price": format_price(order.sl_price, digits),
        }
        if order.tp_price:
            body["take_profit_price"] = format_price(order.tp_price, digits)
        return await self._send_tracked("openPosition", order, kind="open", json_body=body)

    def _presubmit_reason(self, order: OrderAggregate) -> str | None:
        if order.order_type != OrderType.MARKET:
            return "exness adapter supports market orders only"
        if self._daily_loss_cap is None:
            return "EXNESS_DAILY_LOSS_CAP not set"
        if not self._snapshot_ready or self._needs_snapshot:
            return "awaiting trading snapshot reconciliation"
        name = instrument_name(order.symbol)
        if name is None:
            return "unknown exness instrument"
        if name in self._held_unmapped:
            return f"unmapped exness position on {name}"
        return None

    async def _loss_cap_reason(self) -> str | None:
        assert self._daily_loss_cap is not None
        try:
            realized = await self._realized_today()
        except ExnessApiError as e:
            return f"daily loss check failed: {e.code}"
        if realized <= -self._daily_loss_cap:
            logger.warning("exness.daily_loss_cap_reached", realized=realized)
            return "daily loss cap reached"
        return None

    async def _realized_today(self) -> float:
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        total = 0.0
        async for deal in self._deals(since=midnight):
            kind = deal.get("type")
            if kind == "balance":
                continue
            if kind in _PNL_DEAL_TYPES and deal.get("profit"):
                total += float(deal["profit"]["amount"])
            # Commission is always a cost, whatever sign the API reports.
            total -= abs(float(deal.get("commission") or 0))
        return total

    async def _deals(self, *, since: datetime, **filters: str) -> AsyncIterator[dict[str, Any]]:
        """Deals from ``since`` (clamped to the history window), oldest first, across pages."""
        floor = datetime.now(UTC) - timedelta(days=await self._client.deals_window_days())
        params: dict[str, Any] = {
            "from": max(since, floor).isoformat(),
            **filters,
            "limit": _PAGE_LIMIT,
        }
        while True:
            body = await self._client.call("getDealsHistory", params=params)
            for item in body.get("items", []):
                yield item["deal"]
            cursor = body.get("next_cursor")
            if not body.get("has_more") or not cursor:
                return
            params = {"cursor": cursor, "limit": _PAGE_LIMIT}

    def _held_for(self, subscription_id: str) -> tuple[str, _Held] | None:
        return next(
            (
                (pid, h)
                for pid, h in self._positions.items()
                if h.subscription_id == subscription_id
            ),
            None,
        )

    async def _send_tracked(
        self,
        op: str,
        order: OrderAggregate,
        *,
        kind: str,
        position_id: str | None = None,
        path_params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> OrderResult:
        rid = str(order.id)
        name = instrument_name(order.symbol) or ""
        self._inflight[rid] = _Inflight(order, name, kind, position_id, datetime.now(UTC))
        self._pending_ack.add(rid)
        try:
            ack = await self._client.call(
                op, path_params=path_params, json_body=json_body, idempotency_key=rid
            )
        except ExnessApiError as e:
            if rid not in self._early:
                if e.code in ("TRANSPORT", "REQUEST_RATE_LIMIT"):
                    # The request may have reached the venue: wait for a snapshot reconcile.
                    self._needs_snapshot = True
                self._inflight.pop(rid, None)
                logger.warning("exness.order_rejected", order_id=rid, code=e.code)
                return _rejected(order, f"{e.code}: {e.message}")
            # Its outcome already arrived on the stream, so the venue took the request:
            # report SUBMITTED and let the hand-off below deliver that outcome.
            logger.warning("exness.order_ack_lost_after_outcome", order_id=rid, code=e.code)
            ack = {"operation_id": self._early[rid][0].broker_order_id}
        finally:
            self._pending_ack.discard(rid)
            if rid in self._early:
                # Hand off after OrderAppService.submit has recorded SUBMITTED.
                self._spawn(self._complete(*self._early.pop(rid)))
        self._acked_at[rid] = time.monotonic()
        logger.info(
            "exness.order_submitted",
            order_id=rid,
            operation_id=ack.get("operation_id"),
            instrument=name,
            kind=kind,
            volume=(json_body or {}).get("volume"),
        )
        self._spawn(self._watch_operation(rid, str(ack.get("operation_id", ""))))
        return OrderResult(
            order_id=rid,
            broker_order_id=str(ack.get("operation_id", "")),
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now(UTC),
            sl_price=order.sl_price,
            tp_price=order.tp_price,
            side=order.side,
        )

    async def _watch_operation(self, rid: str, operation_id: str) -> None:
        """Resolve an acknowledged request whose outcome the stream did not deliver."""
        try:
            await asyncio.sleep(_FILL_TIMEOUT_S)
            for _ in range(_STATUS_POLLS):
                if rid in self._seen_terminal:
                    return
                body = await self._client.call(
                    "getOperationStatus", path_params={"operation_id": operation_id}
                )
                status = body.get("status")
                if status == "confirmed":
                    await self._recover_fill(rid)
                    return
                if status in ("rejected", "failed"):
                    await self._finish(rid, _cancelled(rid, body))
                    return
                await asyncio.sleep(_FILL_TIMEOUT_S)
            if rid not in self._seen_terminal:
                logger.error("exness.operation_unresolved", order_id=rid, operation_id=operation_id)
                self._needs_snapshot = True
        except Exception as e:
            logger.error("exness.watch_failed", order_id=rid, error=str(e))
            self._needs_snapshot = True

    async def _recover_fill(self, rid: str) -> None:
        inflight = self._inflight.get(rid)
        if inflight is None or rid in self._seen_terminal:
            return
        async for deal in self._deals(since=inflight.sent_at, instrument=inflight.instrument):
            if deal.get("type") == inflight.kind:
                await self._apply_success(rid, None, deal)
                break
        else:
            logger.error("exness.recovered_fill_missing_deal", order_id=rid)
        await self._reconcile_snapshot()

    # ── events path ─────────────────────────────────────────────────────────

    async def _on_event(self, frame: dict[str, Any]) -> None:
        try:
            kind = frame.get("event_type")
            if kind is None and "id" in frame and "code" in frame:
                logger.debug("exness.events_ack", id=frame["id"], code=frame["code"])
            elif kind == "trading_state_snapshot":
                async with self._state_lock:
                    await self._on_snapshot(frame.get("payload") or {})
            elif kind == "transaction_event":
                await self._on_transaction(frame)
            elif kind in ("hmr_snapshot", "hmr_update"):
                logger.info("exness.hmr_event", event_type=kind)
        except Exception as e:
            logger.error("exness.event_handler_failed", error=str(e), exc_info=True)

    async def _on_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Rebuild the held positions from a venue snapshot; the caller holds ``_state_lock``."""
        repo_open = [
            p for p in await self._position_repository.find_open() if p.symbol.endswith(":EXNESS")
        ]
        positions: dict[str, _Held] = {}
        unmapped: set[str] = set()
        matched: set[str] = set()
        for pos in snapshot.get("positions", []):
            pid = str(pos["position_id"])
            if pid in self._positions:
                # Mapped from our own fill; the repo may lag behind it, and its
                # row (when saved) is this position, not one closed while away.
                held = positions[pid] = self._positions[pid]
                matched.update(
                    str(p.id)
                    for p in repo_open
                    if p.subscription_id == held.subscription_id and p.symbol == held.symbol
                )
                continue
            instrument = pos["instrument"]
            side = _SIDE_BY_DIRECTION.get(pos["direction"])
            composite = composite_for(instrument)
            candidates = [p for p in repo_open if p.symbol == composite and p.side == side]
            if len(candidates) != 1:
                unmapped.add(instrument)
                reason = "no_match" if not candidates else "ambiguous"
                logger.error("exness.position_unmapped", instrument=instrument, reason=reason)
                continue
            repo = candidates[0]
            matched.add(str(repo.id))
            positions[pid] = _held_from_repo(repo, float(pos["open_price"]))
        for gone in self._positions.keys() - positions.keys():
            logger.warning("exness.held_position_gone", position_id=gone)
        self._positions = positions
        self._held_unmapped = unmapped
        for repo in repo_open:
            if str(repo.id) not in matched:
                await self._close_missing(repo)
        if not self._inflight:
            self._snapshot_ready = True
            self._needs_snapshot = False
        logger.info("exness.snapshot_reconciled", positions=len(positions), unmapped=len(unmapped))

    async def _close_missing(self, pos: PositionAggregate) -> None:
        name = instrument_name(pos.symbol)
        latest: dict[str, Any] | None = None
        if name is not None:
            async for deal in self._deals(since=pos.opened_at, instrument=name):
                if deal.get("type") == "close":
                    latest = deal
        if latest is None:
            self._held_unmapped.add(name or pos.symbol)
            logger.error("exness.position_missing_close_deal", symbol=pos.symbol)
            return
        held = _held_from_repo(pos, pos.entry_price)
        await self._publish_close_fill(held, held.units, latest)
        await self._emit_trade((held, latest, held.units))
        logger.info("exness.position_closed_while_away", symbol=pos.symbol)

    async def _on_transaction(self, event: dict[str, Any]) -> None:
        rid = event.get("client_request_id")
        if rid and rid in self._seen_terminal:
            return
        deals = (event.get("payload") or {}).get("deals") or []
        if rid and rid in self._inflight:
            status = event.get("status")
            if status == "success":
                inflight = self._inflight[rid]
                deal = next((d for d in deals if d.get("type") == inflight.kind), None)
                if deal is not None:
                    await self._apply_success(rid, event.get("operation_id"), deal)
            elif status in ("rejected", "failed"):
                logger.warning(
                    "exness.order_rejected_async", order_id=rid, error=event.get("error_message")
                )
                await self._finish(rid, _cancelled(rid, event))
            return
        opened = next((d for d in deals if d.get("type") == "open"), None)
        if rid and opened is not None:
            # The request was dropped after a lost ACK, yet it opened a position.
            self._held_unmapped.add(str(opened.get("instrument")))
            self._needs_snapshot = True
            logger.error("exness.unknown_request_fill", order_id=rid)
        for deal in deals:
            if deal.get("type") == "close":
                await self._on_broker_close(deal, _close_reason(event, deal))

    async def _on_broker_close(self, deal: dict[str, Any], reason: str | None) -> None:
        """A close nobody here requested (SL, TP, stop-out); a partial close reduces the hold."""
        pid = str(deal["position_id"])
        async with self._state_lock:
            held = self._positions.get(pid)
            if held is None:
                return
            name = instrument_name(held.symbol) or ""
            cond = await self._client.conditions(name)
            lots = Decimal(deal["volume"])
            units = min(lots_to_units(lots, Decimal(cond["contract_size"])), held.units)
            await self._publish_close_fill(held, units, deal)
            await self._emit_trade((held, deal, units))
            held.units -= units
            if held.units <= 0:
                self._positions.pop(pid, None)
        logger.info("exness.position_closed_by_broker", reason=reason, remaining=held.units)

    async def _apply_success(
        self, rid: str, operation_id: str | None, deal: dict[str, Any]
    ) -> None:
        inflight = self._inflight[rid]
        order = inflight.order
        cond = await self._client.conditions(inflight.instrument)
        units = lots_to_units(Decimal(deal["volume"]), Decimal(cond["contract_size"]))
        pid = str(deal["position_id"])
        async with self._state_lock:
            held = self._positions.pop(pid, None) if inflight.kind == "close" else None
            if inflight.kind == "open":
                self._positions[pid] = _Held(
                    subscription_id=order.subscription_id,
                    symbol=order.symbol,
                    side=_position_side(order.side),
                    units=units,
                    open_price=float(deal["price"]),
                    opened_at=_parse_time(deal.get("create_time")),
                    sl_price=order.sl_price,
                    tp_price=order.tp_price,
                )
        result = OrderResult(
            order_id=rid,
            broker_order_id=operation_id or order.broker_order_id or "",
            status=OrderStatus.FILLED,
            filled_quantity=units,
            filled_price=float(deal["price"]),
            commission=abs(float(deal.get("commission") or 0)),
            side=order.side,
        )
        ack_to_fill_ms = int((time.monotonic() - self._acked_at.pop(rid, time.monotonic())) * 1000)
        logger.info("exness.order_filled", order_id=rid, ack_to_fill_ms=ack_to_fill_ms)
        await self._finish(rid, result, (held, deal, units) if held is not None else None)

    async def _finish(self, rid: str, result: OrderResult, trade: _Trade | None = None) -> None:
        """Deliver one terminal outcome for ``rid``; later duplicates are dropped."""
        self._seen_terminal.add(rid)
        self._inflight.pop(rid, None)
        if rid in self._pending_ack:
            # Delivered by submit's hand-off, after OrderAppService records SUBMITTED.
            self._early[rid] = (result, trade)
        else:
            await self._complete(result, trade)

    async def _complete(self, result: OrderResult, trade: _Trade | None) -> None:
        """Fill first, then its trade; run a deferred reconcile once nothing is in flight."""
        await self._notify(result)
        if trade is not None:
            await self._emit_trade(trade)
        if not self._inflight and (self._needs_snapshot or not self._snapshot_ready):
            try:
                await self._reconcile_snapshot()
            except Exception as e:
                logger.error("exness.reconcile_failed", error=str(e))

    async def _publish_close_fill(self, held: _Held, units: float, deal: dict[str, Any]) -> None:
        await self._event_bus.publish(
            OrderFilledEvent(
                order_id=generate_id_str(),
                subscription_id=held.subscription_id,
                symbol=held.symbol,
                side=OrderSide.SELL if held.side == PositionSide.LONG else OrderSide.BUY,
                filled_quantity=units,
                filled_price=float(deal["price"]),
            )
        )

    async def _emit_trade(self, trade: _Trade) -> None:
        """Report one closed position; always called after its fill was delivered."""
        held, deal, units = trade
        event = TradeClosedEvent(
            position_id=str(deal["position_id"]),
            subscription_id=held.subscription_id,
            symbol=held.symbol,
            direction="LONG" if held.side == PositionSide.LONG else "SHORT",
            entry_price=held.open_price,
            entry_time=held.opened_at,
            quantity=units,
            exit_price=float(deal["price"]),
            exit_time=_parse_time(deal.get("create_time")),
            sl_price=held.sl_price,
            tp_price=held.tp_price,
            pnl=float((deal.get("profit") or {}).get("amount") or 0),
            commission=abs(float(deal.get("commission") or 0)),
        )
        for callback in list(self._trade_callbacks):
            try:
                result = callback(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                logger.warning("exness.trade_callback_failed", error=str(e))

    async def _notify(self, result: OrderResult) -> None:
        for callback in list(self._order_callbacks):
            try:
                outcome = callback(result)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception as e:
                logger.warning("exness.callback_failed", order_id=result.order_id, error=str(e))

    async def _reconcile_snapshot(self) -> None:
        # The read sits inside the lock too: a fill applied between the read and the
        # rebuild would be missing from the snapshot and dropped as gone.
        async with self._state_lock:
            await self._on_snapshot(await self._client.call("getTradingStateSnapshot"))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ── account state ───────────────────────────────────────────────────────

    async def get_balance(self) -> AccountBalance:
        state = (await self._client.call("getTradingStateSnapshot"))["account_state"]
        if self._currency is None:
            details = await self._client.call("getAccountDetails")
            self._currency = str(details["settings"]["currency"])
        equity = float(state["equity"])
        used_margin = float(state["used_margin"])
        return AccountBalance(
            total_equity=equity,
            available_balance=equity - used_margin,
            currency=self._currency,
            margin_used=used_margin,
            unrealized_pnl=equity - float(state["balance"]),
        )

    async def get_positions(self) -> list[PositionAggregate]:
        snapshot = await self._client.call("getTradingStateSnapshot")
        result = []
        for pos in snapshot.get("positions", []):
            cond = await self._client.conditions(pos["instrument"])
            held = self._positions.get(str(pos["position_id"]))
            result.append(
                PositionAggregate.open(
                    subscription_id=held.subscription_id if held else "",
                    symbol=composite_for(pos["instrument"]) or pos["instrument"],
                    side=_SIDE_BY_DIRECTION[pos["direction"]],
                    entry_price=float(pos["open_price"]),
                    quantity=lots_to_units(Decimal(pos["volume"]), Decimal(cond["contract_size"])),
                )
            )
        return result

    async def cancel_order(self, broker_order_id: str) -> bool:
        logger.warning("exness.cancel_unsupported", broker_order_id=broker_order_id)
        return False

    async def subscribe_order_updates(self, callback: OrderCallback) -> None:
        self._order_callbacks.append(callback)

    async def unsubscribe_order_updates(self) -> None:
        self._order_callbacks.clear()

    async def subscribe_trades(self, callback: TradeCallback) -> None:
        self._trade_callbacks.append(callback)

    async def unsubscribe_trades(self) -> None:
        self._trade_callbacks.clear()


def _position_side(side: OrderSide) -> PositionSide:
    return PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT


def _held_from_repo(pos: PositionAggregate, open_price: float) -> _Held:
    return _Held(
        subscription_id=pos.subscription_id,
        symbol=pos.symbol,
        side=pos.side,
        units=pos.quantity,
        open_price=open_price,
        opened_at=pos.opened_at,
        sl_price=pos.sl_price,
        tp_price=pos.tp_price,
    )


def _rejected(order: OrderAggregate, reason: str) -> OrderResult:
    return OrderResult(
        order_id=str(order.id),
        broker_order_id="",
        status=OrderStatus.REJECTED,
        error_message=reason,
    )


def _cancelled(rid: str, body: dict[str, Any]) -> OrderResult:
    return OrderResult(
        order_id=rid,
        broker_order_id=str(body.get("operation_id", "")),
        status=OrderStatus.CANCELLED,
        error_message=f"{body.get('error_code')}: {body.get('error_message')}",
    )


def _close_reason(event: dict[str, Any], deal: dict[str, Any]) -> str | None:
    orders = (event.get("payload") or {}).get("orders") or []
    match = next((o for o in orders if o.get("position_id") == deal.get("position_id")), None)
    return (match or {}).get("order_type")


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None
