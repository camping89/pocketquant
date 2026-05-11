"""FIFO lot tracker — open-lots queue for backtest position bookkeeping.

Supports long-only, short-only, scale-in / scale-out, partial fills, and flip
(LONG↔SHORT) per Backtrader / QuantConnect convention.

Pure module: no datetime / config dependencies — easy to unit test.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Direction = Literal["LONG", "SHORT"]


@dataclass
class OpenLot:
    """A single open lot — one entry fill with remaining qty to close."""

    direction: Direction
    qty_remaining: float
    qty_original: float
    entry_price: float
    entry_time: datetime
    entry_order_id: str
    entry_commission: float  # commission paid on full original entry qty
    sl_price: float | None = None
    tp_price: float | None = None


@dataclass
class ConsumedLot:
    """Represents how much qty was taken from a single lot during a close.

    Used to build closed PositionRecords (one per consumed lot).
    """

    lot: OpenLot  # reference to the underlying lot (qty_remaining already decremented)
    qty_closed: float
    entry_commission_portion: float  # commission proportional to qty_closed
    exit_commission_portion: float  # commission proportional to qty_closed (from exit fill)


@dataclass
class FillOutcome:
    """Result of feeding one fill into the tracker."""

    consumed: list[ConsumedLot] = field(default_factory=list)
    opened: OpenLot | None = None  # new lot opened (if any qty remained after closing)


class LotTracker:
    """FIFO open-lots queue.

    BUY fill: consumes SHORT lots first, opens LONG lot with any excess.
    SELL fill: consumes LONG lots first, opens SHORT lot with any excess.
    """

    def __init__(self) -> None:
        self._lots: deque[OpenLot] = deque()

    @property
    def lots(self) -> list[OpenLot]:
        return list(self._lots)

    def has_long_lot(self) -> bool:
        return any(lot.direction == "LONG" and lot.qty_remaining > 0 for lot in self._lots)

    def has_short_lot(self) -> bool:
        return any(lot.direction == "SHORT" and lot.qty_remaining > 0 for lot in self._lots)

    def net_qty(self) -> float:
        """Signed net qty: positive=long-biased, negative=short-biased."""
        net = 0.0
        for lot in self._lots:
            sign = 1.0 if lot.direction == "LONG" else -1.0
            net += sign * lot.qty_remaining
        return net

    def feed(
        self,
        side: Direction,
        qty: float,
        price: float,
        time: datetime,
        order_id: str,
        commission: float,
        sl_price: float | None = None,
        tp_price: float | None = None,
    ) -> FillOutcome:
        """Feed a fill into the tracker.

        ``side`` here means the *opening* direction of the fill: a BUY fill
        opens LONG (or closes SHORT); a SELL fill opens SHORT (or closes LONG).

        ``commission`` is the total commission for ``qty`` at ``price``.

        Returns:
            FillOutcome with consumed lots and (optionally) a new opened lot.
        """
        if qty <= 0:
            return FillOutcome()

        opposite: Direction = "SHORT" if side == "LONG" else "LONG"
        outcome = FillOutcome()

        remaining = qty
        # Drain opposite-direction lots FIFO
        while remaining > 0 and self._first_open_of(opposite) is not None:
            lot = self._first_open_of(opposite)
            assert lot is not None
            take = min(lot.qty_remaining, remaining)

            entry_comm_portion = (
                lot.entry_commission * (take / lot.qty_original) if lot.qty_original > 0 else 0.0
            )
            exit_comm_portion = commission * (take / qty) if qty > 0 else 0.0

            lot.qty_remaining -= take
            remaining -= take

            outcome.consumed.append(
                ConsumedLot(
                    lot=lot,
                    qty_closed=take,
                    entry_commission_portion=entry_comm_portion,
                    exit_commission_portion=exit_comm_portion,
                )
            )

            if lot.qty_remaining <= 1e-12:
                # Remove the closed lot from the deque (FIFO front of its direction).
                try:
                    self._lots.remove(lot)
                except ValueError:
                    pass

        # Any leftover qty opens a new lot in the requested direction
        if remaining > 0:
            # Commission attributable to the new-lot portion of the fill
            new_lot_commission = commission * (remaining / qty)
            new_lot = OpenLot(
                direction=side,
                qty_remaining=remaining,
                qty_original=remaining,
                entry_price=price,
                entry_time=time,
                entry_order_id=order_id,
                entry_commission=new_lot_commission,
                sl_price=sl_price,
                tp_price=tp_price,
            )
            self._lots.append(new_lot)
            outcome.opened = new_lot

        return outcome

    def _first_open_of(self, direction: Direction) -> OpenLot | None:
        for lot in self._lots:
            if lot.direction == direction and lot.qty_remaining > 0:
                return lot
        return None
