# Phase 04 — Regression parity + docs + roadmap status + validation

## Context Links
- Plan: [plan.md](plan.md) · Prev: [phase-03](phase-03-collector-swap-remove-fifo.md)
- Docs: `docs/system-architecture.md`, `docs/code-standards.md` · Roadmap: `plans/trading-calulation-fix/roadmap.md`

## Overview
- **Priority:** P2 · **Status:** done · **Depends:** 03
- Chốt: regression parity number, cập nhật docs (convention avg-cost trade), đánh dấu roadmap R4 done, chạy full validation gate.

## Key Insights
- Parity anchor: strategy hiện KHÔNG scale → Trade/metrics/equity phải khớp bit-for-bit baseline trước R4 (trừ sai số float chấp nhận). Đây là bằng chứng "chỉ đổi cơ chế, không đổi số".
- Avg-cost đổi granularity CHỈ khi scale-in/out → document convention để tương lai không ngạc nhiên.
- OKX position→Trade defer R8 → docs phải ghi rõ trạng thái (paper emit, OKX chưa).

## Requirements
**Functional**
- `just test` full xanh; ruff/pyright/lint-imports(8) xanh.
- Docs phản ánh AS-IS: trade emission ở broker (paper), avg-cost, FIFO gỡ bỏ.
- Roadmap bảng R4 → Done + note.

**Non-functional**
- Parity number verified (chạy 1 backtest thật hoặc test golden so baseline).

## Related Code Files
**Modify**
- `docs/system-architecture.md` — mục strategy lifecycle / "Where does X live": Trade phát từ `PositionAggregate`→broker `subscribe_trades`→collector; gỡ FIFO/LotTrackingHelper.
- `docs/code-standards.md` — nếu có mục trade/position accounting: ghi convention average-cost (entry_time=lần open đầu, 1 Trade/reduce), commission single-debit.
- `plans/trading-calulation-fix/roadmap.md` — cột R4 → **Done** + 1 dòng note; giải open-Q R4 (pattern subscriber-stamp run_id; OKX defer R8); cập nhật dependency graph nếu cần.

**Verify (no edit)**
- `git grep -n "LotTrackingHelper\|_consumed_pnl"` → chỉ còn ở plans/reports lịch sử (chấp nhận), không còn ở `src/` `tests/` `docs/`.

## Implementation Steps
1. **Regression parity** — chạy 1 backtest cấu hình cố định (hitnrun2) trước/sau; so `metrics` + `total_trades` + `total_commission` + closing equity. Hoặc thêm golden test nếu chưa có. Ghi lại số vào report.
2. **Full gate** — `just test`; nếu đỏ, fix theo recommendation, lặp tới xanh (KHÔNG bỏ qua test đỏ).
3. `ruff` + `pyright` + `lint-imports` (8 contract).
4. **Docs** — cập nhật 2 docs AS-IS (không changelog/banner). Mermaid/ASCII cho flow Trade emission nếu giúp.
5. **Roadmap** — R4 Done + note ngắn; đánh dấu open-Q R4 đã giải (subscriber-stamp pattern), chuyển phần OKX/live-value sang R8; excursion plan (`260630-0031`) giờ unblock phần R4.
6. **Cross-plan** — xác nhận `260630-0031-backtest-mae-mfe-excursion` blockedBy vẫn còn R5 (chưa làm) nếu áp dụng; cập nhật nếu R4 là blocker cuối của nó.

## Todo List
- [x] Regression parity — analytical + test (không có golden-number test; xem Parity note dưới)
- [x] `just test` full xanh (560 passed, 1 skipped)
- [x] `ruff` + `pyright` + `lint-imports` (8) xanh
- [x] `docs/system-architecture.md` cập nhật (trade emission path, gỡ FIFO)
- [x] `docs/code-standards.md` + `project-overview-pdr.md` gỡ LotTrackingHelper ref
- [x] roadmap R4 → Done + giải 2 open-Q R4
- [x] `git grep` LotTrackingHelper/_consumed_pnl sạch ở src/tests/docs-AS-IS
- [x] Cross-plan excursion blockedBy annotate (R2/R3/R4 done → redesign approach)

## Parity note (AS-IS)
- Không có golden-number regression test trước R4 → parity chứng minh bằng: (1) money-math bất biến — closing equity = `initial − Σ(fill commissions) + Σ(gross pnl)`, không đổi vì on_fill debit per-fill + on_trade credit gross pnl y hệt FIFO cũ; (2) 560 test xanh gồm e2e (hitnrun2/engulfing/persistence) + `mark_to_market` (MTM-on vs off metrics byte-identical).
- Đổi granularity equity-curve realized: bỏ điểm record-on-open (open-fill không còn tạo equity point). KHÔNG ảnh hưởng: persisted curve dùng `_mtm_curve` (per-bar, broker `total_equity`) không đổi; `total_return`/`cagr` phụ thuộc closing equity không đổi. Strategy hiện không scale → Trade/metrics khớp.

## Success Criteria
- Toàn bộ gate xanh; parity number khớp baseline.
- Docs AS-IS đúng; roadmap R4 Done.
- Không còn tham chiếu FIFO trong code/tests/docs.

## Risk Assessment
- **Parity lệch** do equity-point granularity (xem Phase 03 risk) → điều chỉnh record-on-open trong on_fill để khớp drawdown baseline.
- **Test flaky do time** (duration dùng sim-time) → đảm bảo broker inject `get_current_time()` nhất quán.

## Security Considerations
Không.

## Next Steps
- R5: rename `BacktestResultAppService`→`BacktestReportAppService`, fully event-driven (subscribe Trade+equity→build→persist), gỡ residual equity accounting.
- R8: OKX position→Trade emission (chốt nguồn qua demo payload), wire event_bus/commission_model vào OKX adapter, live-value cho `Trade.run_id`/`strategy_code`.
