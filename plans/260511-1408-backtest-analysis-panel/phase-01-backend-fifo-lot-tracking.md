---
phase: 1
title: "Backend FIFO Lot Tracking"
status: pending
priority: P1
effort: "1.5d"
dependencies: []
---

# Phase 1: Backend FIFO Lot Tracking

## Overview

Refactor `BacktestResultCollector` từ scalar `_position_qty` sang FIFO open-lots queue. Hỗ trợ long/short/scale-in/scale-out/partial fills/flip. Expose `side` qua `OrderResult` để loại bỏ long-only assumption. Add `direction` field to `PositionRecord`.

## Requirements

- Functional:
  - Long-only flow vẫn pass (backward compat).
  - Short-only flow tạo SHORT positions với PnL = (entry - exit) * qty.
  - Scale-in (2 BUY consecutively) tạo 2 lots; scale-out (1 SELL partial) close lot đầu trước (FIFO).
  - Flip LONG→SHORT (SELL qty > current LONG lots): đóng hết LONG → mở SHORT với excess qty. Tạo 1 close PositionRecord / LONG lot + 1 open PositionRecord cho SHORT.
  - Flip SHORT→LONG đối xứng.
  - Open positions (chưa close) hiển thị với `exit_price=None`.

- Non-functional:
  - Tests cover ≥ 6 scenarios.
  - PnL aggregate khớp với current behavior trong long-only case (no regression).
  - Live broker (OKX) không break — `side` từ Order context có sẵn.

## Architecture

### Data structure: FIFO lots queue

```python
@dataclass
class _OpenLot:
    direction: Literal["LONG", "SHORT"]
    qty_remaining: float
    entry_price: float
    entry_time: datetime
    entry_order_id: str
    entry_commission: float  # commission proportional to original qty
    sl_price: float | None
    tp_price: float | None
```

Collector field: `_open_lots: deque[_OpenLot]`.

### Fill handling

```python
def on_fill(result: OrderResult):
    side = result.side  # NEW field
    qty = result.filled_quantity
    price = result.filled_price
    commission = qty * price * commission_percent

    if side == BUY:
        if has_short_lot():  # closing
            consumed = consume_lots_fifo(SHORT, qty)
            emit_close_positions(consumed, price, ...)
            remaining = qty - consumed.total_qty
            if remaining > 0:
                open_new_lot(LONG, remaining, price, ...)
        else:
            open_new_lot(LONG, qty, price, ...)
    else:  # SELL
        if has_long_lot():
            consumed = consume_lots_fifo(LONG, qty)
            emit_close_positions(consumed, price, ...)
            remaining = qty - consumed.total_qty
            if remaining > 0:
                open_new_lot(SHORT, remaining, price, ...)
        else:
            open_new_lot(SHORT, qty, price, ...)
```

PnL on close:
- LONG close: `(exit - entry) * qty - entry_commission_proportional - exit_commission_proportional`
- SHORT close: `(entry - exit) * qty - commissions`

Equity update per close PositionRecord (not per fill — emit equity points only when realized).

### `OrderResult.side`

Add field `side: OrderSide` (existing enum). Default value strategy:
- Optional (default `None`) cho backward compat khi đọc fills cũ.
- `PaperBroker._fill_order` đã có `order.side` → propagate vào OrderResult.
- OKX broker fill emission verify cùng pattern.

Collector fallback: nếu `result.side is None` → log warning + infer từ `_open_lots` state (legacy behavior).

## Related Code Files

### Modify
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/models.py` — add `side: OrderSide | None = None` to `OrderResult`
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/brokers/paper_broker.py` — emit `side=order.side` in fill result (find file via Grep `_fill_order` or `OrderResult(`)
- `packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py` — emit `side` (verify existing impl, add if missing)
- `packages/pocketquant-backtest/src/pocketquant/backtest/engine/result_collector.py` — refactor `__init__`, `on_fill`, `_calculate_trade_pnl` (remove), `_build_positions`. Fix docstring `_collector.py:24`.
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/value_objects.py` — add `direction: Literal["LONG", "SHORT"]` to `PositionRecord`, update `to_mongo`/`from_mongo`

### Create
- `packages/pocketquant-backtest/src/pocketquant/backtest/engine/lot_tracker.py` — new module: `_OpenLot` dataclass + `LotTracker` class (consume FIFO, open new lot, emit closes). Keeps `result_collector.py` under 200 LOC.
- `packages/pocketquant-backtest/tests/engine/test_lot_tracker.py` — unit tests cho LotTracker
- `packages/pocketquant-backtest/tests/engine/test_result_collector_fifo.py` — integration tests scenarios

## Implementation Steps

1. **Add `side` to OrderResult** — `models.py`. Default `None` cho backward compat.
2. **Update `PaperBroker`** emit `side=order.side` trong fill OrderResult. Grep `OrderResult(` trong paper_broker.py để locate.
3. **Verify OKX broker** emit `side` (likely đã có vì OKX API cần). Update nếu missing.
4. **Add `direction` to PositionRecord** — `value_objects.py`. Update `to_mongo`/`from_mongo` (default `LONG` khi `from_mongo` cho doc cũ).
5. **Create `lot_tracker.py`** — `_OpenLot` + `LotTracker` class với methods: `open(side, qty, price, time, sl, tp, commission, order_id)`, `consume(opposite_side, qty) → list[ConsumedLot]`, `iter_open() → list[_OpenLot]`.
6. **Refactor `result_collector.py`**:
   - Replace `_position_qty`/`_position_cost` với `self._lot_tracker = LotTracker()`.
   - `on_fill`: derive side (from `result.side` or fallback warning); branch open vs close; emit equity point per realized close.
   - Replace `_build_positions`: từ `(consumed_lots, exit_event)` build PositionRecord list + open positions từ `lot_tracker.iter_open()`.
   - Drop `_is_buy_order` + `_calculate_trade_pnl`.
   - Fix line 24 docstring.
7. **Tests**:
   - `test_lot_tracker.py`: open/consume FIFO/partial fills/empty consume.
   - `test_result_collector_fifo.py` scenarios:
     - 1 BUY → 1 SELL same qty (long round-trip, baseline)
     - 1 SELL → 1 BUY same qty (short round-trip)
     - 2 BUY (different prices) → 1 SELL full qty (FIFO PnL khác avg-cost)
     - 1 BUY qty=10 → 2 SELL (4+6) (partial close)
     - LONG 10 → SELL 15 (flip: close LONG + open SHORT 5)
     - SHORT 10 → BUY 15 (flip reverse)
     - Open positions at end (1 BUY no SELL)
   - Test `BacktestMetrics.total_return` không regression cho long-only.
8. **Compile check** — `uv run pyright packages/pocketquant-backtest` + `uv run pytest packages/pocketquant-backtest/tests -k "test_lot_tracker or test_result_collector"`.

## Success Criteria

- [ ] `OrderResult.side` field added, default `None`, backward compat preserved
- [ ] `PaperBroker` emit `side` trong fill result
- [ ] `LotTracker` module dưới 200 LOC, fully typed
- [ ] `result_collector.py` dưới 200 LOC sau refactor
- [ ] All 7 test scenarios pass
- [ ] `PositionRecord.direction` field persisted to Mongo + read-back correct
- [ ] Pyright passes
- [ ] Existing long-only tests vẫn pass (no regression)

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Adding `side` to OrderResult fail OKX broker | Field optional (default None); verify OKX impl trước commit |
| Mongo docs cũ thiếu `direction` field | `from_mongo` default `LONG` cho missing field |
| FIFO PnL khác sequential pairing → metrics doc cũ in DB sai | Acceptable — doc cũ tính qua sequential, recompute on next run. Flag `schema_version=2` nếu cần audit |
| Equity curve point count tăng (per-close thay per-fill) | Spot check: backtests có nhiều partial fills sẽ có ít equity points hơn (chỉ khi close); long-only round-trips → cùng count |

## Notes

- `commission_percent` property đã đúng (BacktestConfig:62). Chỉ fix comment misleading.
- `LotTracker` thiết kế pure — không depend datetime/config, dễ unit test.
- Emit equity points **chỉ khi realized close** (Phase 6 sẽ render equity curve trên FE).
