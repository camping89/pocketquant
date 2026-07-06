# Phase 03 — Docs Sync + Roadmap R5 Done + Journal

**Priority:** P2 · **Status:** done · Depends: Phase 02 (chỉ chạy khi code + test xanh).

## Overview

Đồng bộ docs với rename + broker-sourced equity, đánh dấu R5 done, viết journal. AS-IS only (mô tả hiện trạng, no change-narrative/banner).

## Related code files

- `docs/system-architecture.md` — 3 refs (dòng ~205 tree, ~522 bảng, ~578 sequence)
- `docs/project-overview-pdr.md` — dòng ~319 file tree
- `docs/code-standards.md` — dòng ~375 bảng naming (ví dụ App Services)
- `plans/trading-calulation-fix/roadmap.md` — R5 row → ✅ Done
- `plans/260630-0031-backtest-mae-mfe-excursion/plan.md` — frontmatter `blockedBy` thêm R5 (soft, bidirectional)

## Implementation steps

### 1. `docs/system-architecture.md`
- Dòng 205 tree: `backtest_result_app_service.py  # Result collection` → `backtest_report_app_service.py  # Report collection (Trade+equity → metrics)`.
- Dòng 522 bảng: `BacktestResultAppService | Backtest result collection | engine/backtest/backtest_result_app_service.py` → `BacktestReportAppService | Backtest report: collect Trade+equity, build metrics | engine/backtest/backtest_report_app_service.py`.
- Dòng 578 sequence: `BacktestResultAppService.on_trade(event)` → `BacktestReportAppService.on_trade(event)`.
- Nếu có mô tả equity accounting: cập nhật AS-IS "equity sourced from broker `get_balance()` (single source)". KHÔNG viết "previously/now".

### 2. `docs/project-overview-pdr.md`
- Dòng 319 tree: `backtest_result_app_service.py` → `backtest_report_app_service.py`.

### 3. `docs/code-standards.md`
- Dòng 375 bảng App Services ví dụ: `BacktestResultAppService` → `BacktestReportAppService`.

### 4. `roadmap.md` R5 row
Đổi status R5 sang **Done** + tóm tắt (giọng như R3/R4):
> **R5** ✅ | logic | Rename `BacktestResultAppService`→`BacktestReportAppService` + gut shadow equity ledger. **Done** — xoá `_current_equity`/`_peak_equity`/`_total_commission`; collector inject `IBrokerPort`, `on_trade` + `finalize` đọc `broker.get_balance().available_balance` (broker single source; verified dispatch ngoài lock → no deadlock, parity byte-exact). `total_commission` sum từ fills. `finalize` async. 1 file (không tách, user chọn minimal). `just test` … pass, ruff/pyright/lint-imports (8) xanh. | R1, R4

Cập nhật dependency graph note nếu cần (R5 done).

### 5. Cross-plan bidirectional
`260630-0031-backtest-mae-mfe-excursion/plan.md` frontmatter: thêm `260706-0004-r5-report-service-gut-equity` vào `blockedBy` (soft — đã note sẵn trong prose comment). Giữ prose note hiện có.

### 6. Journal
`/ck:journal` — entry ngắn (giọng kỹ thuật, tiếng Việt): rename + gut shadow ledger, insight "broker._balance == shadow cũ nên parity-exact", verified dispatch-outside-lock, finalize async, 1-file minimal.

## Todo
- [x] system-architecture.md 3 refs
- [x] project-overview-pdr.md tree
- [x] code-standards.md naming table
- [x] roadmap.md R5 → Done
- [x] mae-mfe plan blockedBy += R5 (đã có sẵn trong frontmatter)
- [x] `/ck:journal`

## Success criteria
- `git grep backtest_result_app_service docs/` → chỉ còn journal lịch sử (không phải doc mô tả hiện trạng).
- Roadmap R5 = Done; mae-mfe cross-ref cập nhật.
