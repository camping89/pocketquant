# R4 — Broker Trade Emission (avg-cost) + Remove FIFO

**Ngày:** 2026-07-05 · **Branch:** develop · **Commits:** `ac6315b` → `b872ab9` → `d1122811` → `1bd04be7`

Gộp 2 hệ kế toán position song song về MỘT nguồn: paper broker `PositionAggregate` (average-cost) phát `TradeClosedEvent`, collector subscribe thay vì tự dựng FIFO. Xoá `LotTrackingHelper`. Net **−510 dòng**.

## Vấn đề

Trước R4 có 2 chỗ "phát hiện close + dựng Trade":
- Broker reduce `PositionAggregate` (average-cost, commission debit per-fill).
- Collector dựng `LotTrackingHelper` FIFO riêng từ chuỗi fill, tự tính `_consumed_pnl`, emit `Trade` độc lập.

R3 mới thống nhất *nguồn commission* (`OrderResult.commission`) nhưng trade emission vẫn dual-track. Mỗi lần đổi cách ghi Trade (commission/pnl/timing) phải sửa 2 nơi; bug FIFO reconstruction tốn giờ vì sửa 1 ledger quên ledger kia.

## Thay đổi

| Layer | Nội dung |
|---|---|
| `core/domain/position/events.py` | `TradeClosedEvent` — frozen dataclass all-default, economic-only (`pnl` = gross delta của chunk, `commission`, `direction`, entry/exit price+time+order_id, sl/tp, duration). |
| `core/domain/position/entities.py` | +field `entry_order_id`/`entry_commission`; `reduce_quantity(quantity, price, exit_commission=0.0, exit_order_id=None, exit_time=None)` append `TradeClosedEvent` vào `_events`; `add_quantity(..., commission=0.0)` tích luỹ; `open(..., entry_order_id, entry_commission, opened_at)` inject sim-time. Default-arg toàn bộ → caller cũ additive. |
| `core/domain/brokers/broker_port.py` | `IBrokerPort.subscribe_trades/unsubscribe_trades` + `TradeCallback`. |
| paper broker | `_execute_fill(order, price, commission)` thread commission vào position rồi drain `collect_events()` lọc `TradeClosedEvent`; `_execute_fill_with_commission`→`(commission, trades)`; 4 fill path forward trade SAU fill `OrderResult`. OKX `subscribe_trades` no-op (defer R8), fix `okx_order_mapper` set `side`. |
| `backtest_result_app_service.py` | `on_fill` giữ OrderRecord/Fill + debit commission per-fill; `on_trade(event)` dựng `Trade` (stamp `run_id`/`strategy_code`) + credit `pnl` + back-link `resulting_trade_id`; `open_positions` từ `broker.get_positions()`. Xoá `LotTrackingHelper`/`_consumed_pnl`/`_emit_trades`/`_resolve_side`/`_build_open_positions` + 2 test FIFO. |

## Quyết định (non-obvious)

- **Subscriber-stamp:** `TradeClosedEvent` economic-only (KHÔNG mang run_id/strategy_code) — subscriber sở hữu context. Broker infra không cần biết run context. Giải open-Q R1/R4 về live-value mapping (defer R8). Event "dumb", handler "smart" → pluggable cho backtest vs live.
- **Commission single-debit giữ nguyên:** `on_fill` debit per-fill, `on_trade` CHỈ credit gross `pnl`; `TradeClosedEvent.commission` chỉ để ghi doc. Invariant: `closing_equity = initial − Σ commission + Σ gross_pnl`. Cộng commission ở `on_trade` sẽ double-count.
- **Thứ tự dispatch:** fill `OrderResult` TRƯỚC `TradeClosedEvent` → `on_trade` back-link được exit `OrderRecord` (đã tồn tại). Verified bằng test `fill_idx < trade_idx`.
- **Equity-curve granularity đổi:** bỏ điểm record-on-open (open-fill không còn tạo equity point). Chấp nhận vì: không có golden-number test; persisted curve dùng `_mtm_curve` per-bar (broker `total_equity`) không đổi; `total_return`/`cagr` phụ thuộc closing equity. **Điểm dễ bất ngờ tương lai** — flag ở docs.
- **OKX defer R8:** `OrderResult.commission` OKX là accumulated snapshot vs paper per-fill → emit Trade từ OKX giờ sẽ double-count. R4 paper-only tránh sạch; R8 xử snapshot-delta khi wire live.

## Verify

- `just test`: **560 passed, 1 skipped** (e2e hitnrun2/engulfing/persistence + `mark_to_market` metrics byte-identical MTM-on vs off).
- `ruff` clean · `pyright` 0 errors · `lint-imports` **8/8 kept**.
- `git grep 'LotTrackingHelper\|_consumed_pnl'` sạch ở src/tests/docs-AS-IS.

## Next

- **R5:** rename `BacktestResultAppService`→`BacktestReportAppService`, fully event-driven (gut residual equity accounting).
- **R8:** OKX position→Trade emission (chốt nguồn qua demo payload), live-value cho `Trade.run_id`/`strategy_code`.
- **Cross-plan:** `260630-0031` (MAE/MFE excursion) hết hard blocker (R2/R3/R4 done) nhưng approach cũ dựa `_lot_tracker.lots` đã bị xoá → cần redesign track trên `PositionAggregate`.
