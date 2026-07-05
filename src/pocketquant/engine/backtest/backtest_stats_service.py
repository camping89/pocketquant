"""Backtest stats service — read-side analytics + paged trades for the result view.

Centralizes every number the Trades tab shows so the browser loads results
instead of computing them over the full trade list:

- ``list_trades_paged`` — keyset (cursor) page of closed trades, server-side
  filtered (all/wins/losses) and sorted. Replaces the old load-everything read.
- ``list_markers`` — one lite row per trade for the chart's entry/exit arrows.
- ``get_stats`` — PnL / duration histograms, win-loss streaks, profit factor by
  direction, and worst-drawdown periods (ported verbatim from the FE).

Cursor is opaque base64(JSON) of the last row's ``(sort value, trade_id)``; the
codec lives here (app-side) so the repository stays a plain Mongo adapter.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.trading import Trade
from pocketquant.core.domain.trading.trade_stats import (
    drawdown_periods,
    histogram,
    profit_factor_by_direction,
    win_loss_streaks,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)

_HOUR_SECONDS = 3600.0
# Datetime sort keys need type-aware cursor decoding (ISO string -> datetime).
_DATETIME_SORT_KEYS = {"entry_time", "status"}


class TradeSortKey(str, Enum):
    entry_time = "entry_time"
    pnl = "pnl"
    quantity = "quantity"
    duration_seconds = "duration_seconds"
    entry_price = "entry_price"
    exit_price = "exit_price"
    commission = "commission"
    direction = "direction"
    status = "status"


class TradeSortDir(str, Enum):
    asc = "asc"
    desc = "desc"


class TradeFilter(str, Enum):
    all = "all"
    wins = "wins"
    losses = "losses"


class ListTradesQuery(BaseModel):
    run_id: str
    limit: int = 50
    cursor: str | None = None
    sort_key: TradeSortKey = TradeSortKey.entry_time
    sort_dir: TradeSortDir = TradeSortDir.desc
    filter: TradeFilter = TradeFilter.all


class TradeDto(BaseModel):
    trade_id: str
    direction: str
    entry_price: float
    entry_time: str
    exit_price: float
    exit_time: str | None
    quantity: float
    sl_price: float | None
    tp_price: float | None
    pnl: float
    commission: float
    duration_seconds: float


class PagedTradesResponse(BaseModel):
    items: list[TradeDto]
    next_cursor: str | None
    has_more: bool
    total: int
    total_pnl: float


class TradeMarkerDto(BaseModel):
    trade_id: str
    entry_time: str
    exit_time: str | None
    direction: str
    entry_price: float
    exit_price: float
    sl_price: float | None
    tp_price: float | None
    quantity: float
    pnl: float
    commission: float


class HistogramBinDto(BaseModel):
    lo: float
    hi: float
    count: int


class StreakStatsDto(BaseModel):
    max_win_streak: int
    max_loss_streak: int


class DirectionProfitFactorDto(BaseModel):
    long: float | None
    short: float | None


class DrawdownPeriodDto(BaseModel):
    depth: float
    start_time: str
    trough_time: str
    recovery_time: str | None
    duration_seconds: float


class BacktestStatsResponse(BaseModel):
    pnl_histogram: list[HistogramBinDto]
    duration_histogram: list[HistogramBinDto]
    streaks: StreakStatsDto
    profit_factor_by_direction: DirectionProfitFactorDto
    drawdowns: list[DrawdownPeriodDto]
    profit_factor_all: float


def _trade_to_dto(t: Trade) -> TradeDto:
    return TradeDto(
        trade_id=str(t.trade_id),
        direction=t.direction,
        entry_price=t.entry_price,
        entry_time=t.entry_time.isoformat(),
        exit_price=t.exit_price,
        exit_time=t.exit_time.isoformat() if t.exit_time else None,
        quantity=t.quantity,
        sl_price=t.sl_price,
        tp_price=t.tp_price,
        pnl=t.pnl,
        commission=t.commission,
        duration_seconds=t.duration_seconds,
    )


def _sort_value(t: Trade, sort_key: TradeSortKey) -> Any:
    """Raw value of the sort field on a trade, matched to the repo's Mongo field."""
    if sort_key == TradeSortKey.status:
        return t.exit_time
    return getattr(t, sort_key.value)


def _encode_cursor(t: Trade, sort_key: TradeSortKey) -> str:
    value = _sort_value(t, sort_key)
    raw = value.isoformat() if isinstance(value, datetime) else value
    payload = json.dumps({"v": raw, "id": str(t.trade_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str, sort_key: TradeSortKey) -> tuple[Any, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        raw = payload["v"]
        trade_id = payload["id"]
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Invalid trades cursor") from exc
    value = datetime.fromisoformat(raw) if sort_key.value in _DATETIME_SORT_KEYS else raw
    return value, trade_id


class BacktestStatsService:
    """Read-side backtest analytics + paged trades — Mongo-backed, no engine coupling."""

    def __init__(
        self,
        backtest_repository: BacktestRepository,
        backtest_trade_repository: BacktestTradeRepository,
    ) -> None:
        self._backtest_repo = backtest_repository
        self._trade_repo = backtest_trade_repository

    async def list_trades_paged(self, query: ListTradesQuery) -> PagedTradesResponse:
        cursor_value: Any | None = None
        cursor_id: str | None = None
        if query.cursor:
            cursor_value, cursor_id = _decode_cursor(query.cursor, query.sort_key)

        pnl_filter = None if query.filter == TradeFilter.all else query.filter.value
        trades, has_more = await self._trade_repo.list_by_run_paged(
            query.run_id,
            limit=query.limit,
            sort_key=query.sort_key.value,
            sort_dir=query.sort_dir.value,
            pnl_filter=pnl_filter,
            cursor_value=cursor_value,
            cursor_id=cursor_id,
        )

        items = [_trade_to_dto(t) for t in trades]
        next_cursor = (
            _encode_cursor(trades[-1], query.sort_key) if has_more and trades else None
        )
        # Footer aggregates describe the whole filtered set, not a page — compute
        # them once on the first page (cursor absent). Later pages skip the extra
        # count + $sum scans; the FE only reads these off page 0.
        is_first_page = query.cursor is None
        total = 0
        total_pnl = 0.0
        if is_first_page:
            total = await self._trade_repo.count_by_run(query.run_id, pnl_filter)
            total_pnl = await self._trade_repo.sum_pnl_by_run(query.run_id, pnl_filter)
        return PagedTradesResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
            total_pnl=total_pnl,
        )

    async def list_markers(self, run_id: str) -> list[TradeMarkerDto]:
        rows = await self._trade_repo.list_markers_by_run(run_id)
        return [
            TradeMarkerDto(
                trade_id=str(r["_id"]),
                entry_time=r["entry_time"].isoformat(),
                exit_time=r["exit_time"].isoformat() if r.get("exit_time") else None,
                direction=r.get("direction", "LONG"),
                entry_price=r["entry_price"],
                exit_price=r["exit_price"],
                sl_price=r.get("sl_price"),
                tp_price=r.get("tp_price"),
                quantity=r["quantity"],
                pnl=r["pnl"],
                commission=r.get("commission", 0.0),
            )
            for r in rows
        ]

    async def get_stats(self, run_id: str) -> BacktestStatsResponse:
        result = await self._backtest_repo.get(run_id)
        if result is None:
            raise NotFoundError(f"Backtest not found: {run_id}")

        # Chronological closed trades drive the distributions + streaks; the FE
        # excluded open positions from all of these, so we read the closed set.
        trades = await self._trade_repo.list_by_run(run_id)

        pnls = [t.pnl for t in trades]
        durations_hours = [t.duration_seconds / _HOUR_SECONDS for t in trades]
        streaks = win_loss_streaks(pnls)
        pf = profit_factor_by_direction([(t.direction, t.pnl) for t in trades])
        periods = drawdown_periods(result.equity_curve, top_n=5)

        return BacktestStatsResponse(
            pnl_histogram=[
                HistogramBinDto(lo=b.lo, hi=b.hi, count=b.count) for b in histogram(pnls)
            ],
            duration_histogram=[
                HistogramBinDto(lo=b.lo, hi=b.hi, count=b.count)
                for b in histogram(durations_hours)
            ],
            streaks=StreakStatsDto(
                max_win_streak=streaks.max_win_streak,
                max_loss_streak=streaks.max_loss_streak,
            ),
            profit_factor_by_direction=DirectionProfitFactorDto(long=pf.long, short=pf.short),
            drawdowns=[
                DrawdownPeriodDto(
                    depth=p.depth,
                    start_time=p.start_time.isoformat(),
                    trough_time=p.trough_time.isoformat(),
                    recovery_time=p.recovery_time.isoformat() if p.recovery_time else None,
                    duration_seconds=p.duration_seconds,
                )
                for p in periods
            ],
            profit_factor_all=result.metrics.profit_factor,
        )
