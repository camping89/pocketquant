# Phase 03 — Collector minimal swap + wiring + delete FIFO

## Context Links
- Plan: [plan.md](plan.md) · Prev: [phase-02](phase-02-port-broker-transport.md)
- Files: `engine/backtest/backtest_result_app_service.py`, `engine/backtest/backtest_app_service.py`, `engine/backtest/lot_tracking_helper.py` (DELETE)

## Overview
- **Priority:** P2 · **Status:** done · **Depends:** 02
- Đổi NGUỒN trade của collector: từ FIFO tự dựng → subscribe `TradeClosedEvent` broker phát. Xoá `LotTrackingHelper` + `_consumed_pnl`. `open_positions` từ `broker.get_positions()`. Metrics build ở `finalize` GIỮ NGUYÊN (minimal swap — rename để R5).

## Key Insights
- `on_fill` hiện: debit commission + feed FIFO + emit trades + record equity. → Mới: giữ OrderRecord/Fill + debit commission; BỎ FIFO feed + emit.
- `on_trade` mới credit `pnl` (KHÔNG credit commission lần 2 — đã debit ở on_fill per-fill).
- Collector hiện KHÔNG có broker ref → `finalize` phải nhận `list[PositionAggregate]` từ caller (backtest_app_service `await broker.get_positions()`).
- `OpenLot` (core.domain.backtest) cần `entry_order_id` + `entry_commission_portion` → lấy từ PositionAggregate `entry_order_id` + `entry_commission` (đã là phần còn lại tỉ lệ sau các reduce ở Phase 01).
- `_resolve_side` (FIFO side inference) biến mất — side giờ nằm trong TradeClosedEvent.direction.
- Stamp `run_id`/`strategy_code`: collector có `self._run_id` + `self._config.strategy_code`.

## Requirements
**Functional**
- `on_trade(event: TradeClosedEvent)` dựng `Trade` (stamp run_id/strategy_code), append `_trades`, `_current_equity += pnl`, record equity point tại `exit_time`, back-link `resulting_trade_id` lên exit OrderRecord.
- `finalize(positions)` build `open_positions` từ PositionAggregate.
- Xoá hoàn toàn `LotTrackingHelper`, `_lot_tracker`, `_resolve_side`, `_emit_trades`, `_consumed_pnl`, `_build_open_positions`(FIFO).

**Non-functional**
- Parity: end-to-end backtest number (strategy không scale) KHÔNG đổi.

## Architecture
```
broker.subscribe_order_updates(collector.on_fill)   # OrderRecord/Fill + commission debit
broker.subscribe_order_event(collector.on_event)    # status mirror (giữ)
broker.subscribe_trades(collector.on_trade)         # NEW: Trade + equity credit
...
positions = await broker.get_positions()
collector.finalize(run_id, ..., positions=positions)  # PositionAggregate→OpenLot
```

## Related Code Files
**Modify**
- `backtest_result_app_service.py` — bỏ FIFO import/field/method; rewrite `on_fill`; thêm `on_trade`; `finalize(..., positions)`; thêm `_position_to_open_lot`.
- `backtest_app_service.py` — `await broker.subscribe_trades(collector.on_trade)` (sau 2 subscribe cũ); `await broker.unsubscribe_trades()` ở finally; `positions = await broker.get_positions()` trước finalize; truyền vào finalize.

**Delete**
- `src/pocketquant/engine/backtest/lot_tracking_helper.py`
- `tests/backtest_test/engine/test_lot_tracker.py`
- `tests/backtest_test/engine/test_result_collector_fifo.py`

## Implementation Steps
1. **`on_fill`** — bỏ `side_dir`/`_lot_tracker.feed`/`_emit_trades`/`_record_equity_point(else)`. Giữ: filled guard, `commission=result.commission`, `_total_commission += commission`, `_current_equity -= commission`, `_upsert_order`, `_append_fill`. (Không còn record equity point ở on_fill trừ khi muốn giữ granularity opens — cân nhắc: giữ 1 record equity point sau debit để drawdown-on-open như cũ.)
2. **`on_trade(event)`** — dựng `Trade(trade_id=generate_id(), run_id=self._run_id, strategy_code=self._config.strategy_code, symbol=event.symbol, direction=event.direction, entry_order_id=event.entry_order_id, entry_price=event.entry_price, entry_time=event.entry_time, quantity=event.quantity, exit_order_id=event.exit_order_id, exit_price=event.exit_price, exit_time=event.exit_time, sl_price=event.sl_price, tp_price=event.tp_price, pnl=event.pnl, commission=event.commission, duration_seconds=event.duration_seconds)`; `_trades.append`; `_current_equity += event.pnl`; `_record_equity_point(event.exit_time)`; back-link `resulting_trade_id` lên `_orders_by_id.get(event.exit_order_id)`.
3. **`_position_to_open_lot(pos)`** — `OpenLot(symbol=pos.symbol, direction=pos.side.name, entry_price=pos.entry_price, entry_time=pos.opened_at, quantity=pos.quantity, sl_price=pos.sl_price, tp_price=pos.tp_price, entry_order_id=pos.entry_order_id, entry_commission_portion=pos.entry_commission)`.
4. **`finalize`** — thêm param `positions: list[PositionAggregate]`; `open_positions=[_position_to_open_lot(p) for p in positions if not p.is_closed]`; phần metrics build GIỮ NGUYÊN.
5. **Xoá** FIFO import (`ConsumedLot, Direction, FillOutcome, LotTrackingHelper`) + `self._lot_tracker` + method liệt kê.
6. **Wiring** `backtest_app_service.py` — subscribe_trades + unsubscribe + get_positions + truyền finalize.
7. **Xoá file** `lot_tracking_helper.py` + 2 test FIFO.
8. Kiểm `git grep -n "LotTrackingHelper\|_consumed_pnl\|lot_tracker"` → chỉ còn (nếu có) trong docs sẽ update Phase 04.

## Todo List
- [x] `on_fill` bỏ FIFO, giữ OrderRecord/Fill + commission debit
- [x] `on_trade` dựng Trade + credit pnl + back-link
- [x] `_position_to_open_lot` (direction=.name)
- [x] `finalize(positions)` build open_positions từ PositionAggregate
- [x] Xoá LotTrackingHelper + field + 5 method
- [x] Wire subscribe_trades + unsubscribe + get_positions vào backtest_app_service
- [x] Delete lot_tracking_helper.py + 2 test FIFO
- [x] `pyright`/`ruff`/`lint-imports` xanh

## Success Criteria
- Backtest chạy end-to-end: `_trades`, metrics, equity curve khớp baseline (strategy không scale).
- `git grep LotTrackingHelper|_consumed_pnl` sạch (trừ docs → Phase 04).
- import-linter 8 contract xanh.

## Risk Assessment
- **Equity point granularity đổi** (bỏ record-on-open) → drawdown intra có thể mượt hơn/thô hơn. Mitigation: giữ 1 `_record_equity_point` sau commission debit ở on_fill nếu baseline lệch.
- **Back-link miss** nếu TradeClosedEvent tới trước OrderResult → Phase 02 đã đảm bảo fill notify trước trade.
- **open_positions rỗng** nếu get_positions filter closed — đúng ý (chỉ position còn mở).

## Security Considerations
Không I/O ngoài. Đọc broker in-process.

## Next Steps
Phase 04: regression parity number, docs, roadmap status, full validation.
