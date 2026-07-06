# Brainstorm R4 — Broker phát Trade (average-cost) khi close, xoá FIFO

> Sub-brainstorm R4 của initiative `plans/trading-calulation-fix/roadmap.md`. Depends R3 (done). Model E. OKX ref: `okx-broker-verification.md`.

## Problem statement

Hai hệ kế toán position **song song** cùng lúc:
- **Paper broker** (`PaperBrokerAdapter`) giữ `dict[str, PositionAggregate]` (average-cost) → dùng cho balance/equity/`get_positions`.
- **Result collector** (`BacktestResultAppService`) chạy `LotTrackingHelper` (FIFO) thứ 2 → dựng Trade từ fill (1 Trade/lot), realized equity từ `_consumed_pnl`, `open_positions` từ FIFO lots.
- **Live path** (`PositionAppService`) cũng có `PositionAggregate` nhưng close chỉ **log** realized_pnl, không dựng Trade, không publish event.

Hệ quả: latent inconsistency (equity=avg-cost, trade/metric=FIFO — trùng chỉ khi không scale); `PositionAggregate` domain events (`PositionClosedEvent`) sinh ra nhưng `collect_events()` **0 call site** (produced-never-consumed).

**R4:** gộp về MỘT nguồn — `PositionAggregate` phát `TradeClosedEvent` lúc reduce/close (avg-cost); broker forward; collector chỉ subscribe. Xoá `LotTrackingHelper` + `_consumed_pnl`.

## Quyết định (locked)

| # | Câu hỏi | Chốt |
|---|---|---|
| Q1 | Phạm vi OKX | **Paper-only, defer OKX position→Trade emission → R8** (blocked demo payload; OKX adapter chưa wire event_bus/commission_model). R4 vẫn fix OKX order mapper `side`. |
| Q2 | Dựng + truyền Trade | **Option A** — PositionAggregate emit `TradeClosedEvent` + port callback `subscribe_trades`. DRY nhất; live path R8 thừa hưởng; giữ 1 idiom transport (đối xứng `subscribe_order_updates`). |
| Q3 | Ranh giới R4/R5 | **Minimal swap ở R4** — chỉ đổi NGUỒN trade; metrics vẫn build ở `finalize`. R5 lo rename→`BacktestReportAppService` + fully event-driven. |

### Q2 — options đã cân nhắc
- **A (chọn)**: extend PositionAggregate emit event → broker drain `collect_events` → `subscribe_trades`. Ưu: DRY, cohesion, live R8 free. Nhược: aggregate phình ~40-60 LOC, commission-aware (nhưng `Trade.commission`∈core.domain.trading nên nhất quán).
- **B**: broker sidecar `{entry_order_id, entry_commission}` dựng event, aggregate giữ nguyên. Nhược: KHÔNG DRY (live R8 lặp lại), sidecar drift — tái lập 2 hệ.
- **C**: aggregate emit + publish EventBus. Nhược: kéo bus vào hot loop backtest, phá đối xứng transport (order=callback, trade=bus), await=preemption (publish-before-subscribe gotcha).

## Thiết kế (Option A)

### 1. `TradeClosedEvent` — `core/domain/position/events.py`
DomainEvent cạnh `PositionClosedEvent`. Bắn **mỗi reduce** (khác `PositionClosedEvent` chỉ bắn qty→0). Economic-only, **không** `run_id`/`strategy_code`:
`position_id, subscription_id, symbol, direction, entry_order_id, entry_price, entry_time, quantity(đóng), exit_order_id, exit_price, exit_time, sl_price, tp_price, pnl, commission(entry_portion+exit), duration_seconds`.

### 2. `PositionAggregate` — `core/domain/position/entities.py`
- +field `entry_order_id: str|None=None`, `entry_commission: float=0.0`.
- `open(..., entry_order_id=None, entry_commission=0.0, opened_at=None)` — **`opened_at` param**: broker inject `get_current_time()` (sim-time). Bugfix: hiện `opened_at` default `utc_now()`=wall-clock (latent; FIFO override entry_time; giờ open_positions dùng nó).
- `add_quantity(qty, price, commission=0.0)` → `entry_commission += commission`.
- `reduce_quantity(qty, price, exit_commission=0.0, exit_order_id=None, exit_time=None)` → `entry_commission_portion = entry_commission*qty/qty_before`; `entry_commission -= portion`; append `TradeClosedEvent(pnl=realized_delta, commission=portion+exit_commission, duration=exit_time-entry_time)`; giữ decrement + close-if-zero.
- **Default arg toàn bộ** → sandbox/live/tests không vỡ.

### 3. IBrokerPort + paper broker
- IBrokerPort: `TradeCallback = Callable[[TradeClosedEvent], None|Awaitable]`; `subscribe_trades(cb)` + `unsubscribe_trades()`.
- OKX adapter: `subscribe_trades` = lưu callback, **không gọi** + comment defer R8.
- Paper broker: `_trade_callbacks` + `_notify_trade_callbacks`. `_execute_fill_with_commission` thành **điểm duy nhất**: commission TRƯỚC → `_execute_fill(order, price, commission)` (thread open/add=entry, reduce=exit) → debit balance → drain `collect_events` lọc `TradeClosedEvent` → return `(commission, trades)`. Caller async forward **sau** `_notify_callbacks(result)` (OrderResult trước → OrderRecord tồn tại → TradeClosedEvent → back-link). Notify ngoài lock.
- 1 fill = 1 vai trò (no flip) → commission cả fill vào đúng 1 phía.

### 4. Collector — minimal swap — `backtest_result_app_service.py`
- Xoá: `LotTrackingHelper`, `_lot_tracker`, `_resolve_side`, `_emit_trades`, `_consumed_pnl`, `_build_open_positions`(FIFO).
- `on_fill`: giữ OrderRecord/Fill + `_current_equity -= commission` + `_total_commission += commission`; bỏ FIFO feed. Commission **không** debit lần 2.
- `on_trade(event)` mới: stamp run_id/strategy_code từ config → `Trade` → append → `_current_equity += event.pnl` → `_record_equity_point(event.exit_time)` → back-link `resulting_trade_id`.
- `open_positions`: `finalize(positions: list[PositionAggregate])` từ `broker.get_positions()` → converter →OpenLot (dùng `entry_order_id`+`entry_commission`).
- Wiring `backtest_app_service.py`: `subscribe_trades(collector.on_trade)` + unsubscribe finally + truyền positions vào finalize.

### 5. Cheap win — OKX order mapper `side`
`OkxOrderMapper.to_order_result` set `side` từ `data["side"]`. Cần cho `OrderRecord.side` live. 2 dòng.

## Đổi hành vi
- FIFO→avg-cost granularity: khác chỉ khi scale-in/out (strategy hiện không scale → số liệu thực tế không đổi). `Trade.entry_time`=lần open đầu, duration=exit−first_open (convention position-level). Document `docs/`.
- Flip: cả cũ/mới đều không sinh fill flip → không mất gì.

## Success criteria
- `just test` xanh; ruff/pyright/lint-imports(8) xanh.
- Backtest end-to-end (strategy không scale): Trade/metrics/equity **y hệt** trước (parity regression anchor).
- `LotTrackingHelper` + `_consumed_pnl` biến mất; `git grep` sạch.
- Unit test mới: PositionAggregate open→add→reduce (partial/full), commission portion, avg-cost pnl, sim-time duration.

## Rủi ro / mitigation
| Rủi ro | Mitigation |
|---|---|
| Ripple chữ ký reduce/add | Default arg toàn bộ |
| Double-count commission | on_fill debit per-fill; on_trade chỉ credit pnl |
| Thứ tự OrderResult vs TradeClosedEvent | Broker notify fill callback TRƯỚC trade |
| `opened_at` wall-clock lọt open_positions | Broker inject sim-time opened_at |

## Invariants
import-linter 8 contract giữ (`TradeClosedEvent`∈core.domain.position, `subscribe_trades`∈IBrokerPort, no fastapi/bson); parity paper↔backtest; metrics source-agnostic.

## Unresolved (chuyển R5/R8)
- **R8**: OKX Trade source (orders.fillPnl vs positions.realizedPnl vs positions-history) — cần payload demo mode thật; wire event_bus/commission_model vào OKX adapter; giá trị live `Trade.run_id`/`strategy_code` (subscription_id→strategy_code, run_id=session).
- **R5**: rename `BacktestResultAppService`→`BacktestReportAppService`, fully event-driven, gỡ residual equity accounting trong collector (R4 để lại `on_fill` vẫn dựng OrderRecord/Fill).
- Convention `entry_order_id` dưới avg-cost scale-in (lấy lần open đầu) — xác nhận khi có strategy scale thật.
