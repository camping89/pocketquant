# R5 — BacktestReportAppService: Rename + Gut Shadow Equity (Broker Single-Source)

**Ngày:** 2026-07-06 · **Branch:** develop · **Commits:** `ac6315b` → `b872ab9` → `d1122811` → `1bd04be7` → R5 refactor

Rename `BacktestResultAppService` → `BacktestReportAppService`; xoá ledger bóng `_current_equity`, `_peak_equity`, `_total_commission`. Collector giờ chỉ là orchestrator pure event-driven; equity từ broker duy nhất.

## Vấn đề

R4 unified trade emission qua broker `PositionAggregate` nhưng collector vẫn giữ bộ ledger parallel (`_current_equity`, `_peak_equity`, `_total_commission`) để tracking. Loạn:
- `on_fill` vừa debit commission VÀO shadow ledger vừa ghi OrderRecord (mục đích?).
- `_current_equity` copy từ broker nhưng sao chép bất động (khi broker thay đổi balance, shadow "lag").
- Finalize phải tính `total_commission` từ shadow ledger (có sẵn ở broker order record).

Thực ra broker đã có single source (PaperBrokerAdapter `_balance`), collector không cần ghi nhận lại.

## Thay đổi

| Layer | Nội dung |
|---|---|
| File rename | `backtest_result_app_service.py` → `backtest_report_app_service.py` (git mv); class `BacktestResultAppService` → `BacktestReportAppService`. |
| Constructor | Inject `IBrokerPort` (có sẵn). |
| `on_trade(event)` | Đọc `broker.get_balance().available_balance` lúc call → `equity` (real-time). Không cache. |
| `on_fill(...)` | Xoá debit commission (`_current_equity -= result.commission`); chỉ ghi OrderRecord + Fill doc. Commission đã debit ở broker `_execute_fill_with_commission`. |
| `finalize` | Async (was sync). Tổng từ order records: `total_commission = sum(fill.commission for fill in order_fills)`. Đọc broker balance cuối: `finalize_equity = broker.get_balance().available_balance`. |
| Xoá | `_current_equity`, `_peak_equity`, `_total_commission` shadow fields; methods `_round_trip`, `_emit_trades`, `_build_open_positions`. |
| MTM & closing equity | Broker `_mtm_curve` per-bar + finalize closing point giữ nguyên. Invariant: `closing_equity = initial − Σ commission + Σ gross_pnl` (proof dưới). |

## Quyết định (non-obvious)

**Parity proof (economically exact; byte-identical trên tested runs):** PaperBrokerAdapter lock-timing ensures equity consistency.
- `_execute_fill_with_commission` → debit `_balance` inside `asyncio.Lock`
- `_notify_trade_callbacks` fires (dispatch `TradeClosedEvent`) OUTSIDE lock
- When collector `on_trade` calls `broker.get_balance()`, lock released → `available_balance` = `initial − Σcommission + Σrealized_pnl`
- Old shadow ledger computed exact same formula → every metric unchanged (max_drawdown, total_return, Sharpe, gross PnL, total trades).
- **Không còn MTM-only collapse** — broker balance IS the truth, not approximate.
- **Caveat (ULP):** thứ tự cộng đổi — cũ `(E − commission) + pnl` (on_fill rồi on_trade), mới `(E + realized) − commission` (broker fill). IEEE-754 non-associative → có thể lệch ≤1 ULP với float bất kỳ (economically irrelevant, ~1e-16 rel). Engulfing/hitnrun2 characterization runs land byte-identical (số không đổi), nên empirically byte-exact — không claim provable tổng quát.

**Scope:** Rename + gut only; File size ~380 lines (exceeds 200 guideline) — accepted minimal churn over splitting. Single orchestrator class.

**Finalize async:** 2 call sites in `BacktestAppService.run` (finished + failed path) → `await collector.finalize(...)`.

## Verify

| Thẩm định | Kết quả |
|---|---|
| `just test` | **560 passed, 1 skipped** (engulfing + hitnrun2 characterization tests; `mark_to_market` fixture unchanged). |
| `ruff` | Clean. |
| `pyright` | **0 errors** in R5 files (1 pre-existing unrelated in `test_engulfing.py` untouched). |
| `lint-imports` | **8/8 contracts kept** (no new violations). |
| Metrics parity | byte-identical: `max_drawdown`, `total_return`, `sharpe_ratio`, `total_trades`, gross PnL, cumulative realized. |

## Next

- **MAE/MFE excursion (260630-0031):** R1+R2+R3+R4 complete; R5 không hard-block. Old approach dùng `_lot_tracker.lots` (xoá R4) → cần redesign trên `PositionAggregate` (soft-blocker, defer phân tích).
- **R6+:** Live broker integration; fee currency, funding fee; tiered commission model.

---

**Status:** DONE  
**Summary:** R5 hoàn thành: rename service, xoá shadow equity ledger, broker single-source — tất cả metric parity, 560 test pass, 0 linting error.
