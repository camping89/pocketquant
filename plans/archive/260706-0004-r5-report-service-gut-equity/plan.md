---
title: "R5 — Report Service Rename + Gut Residual Equity Accounting"
description: "Rename BacktestResultAppService→BacktestReportAppService + gut shadow equity ledger (_current_equity/_peak_equity/_total_commission). Broker-sourced recorder: equity từ IBrokerPort.get_balance() (parity-exact, broker._balance == shadow cũ). Single file, không tách. Kế thừa Model E."
status: done
priority: P2
branch: develop
tags: [trading-calc, backtest, engine, report-service, equity-accounting, rename]
blockedBy: []
blocks: [260630-0031-backtest-mae-mfe-excursion]
created: "2026-07-06T00:04:00+07:00"
createdBy: "ck:plan"
source: "plans/trading-calulation-fix/roadmap.md (R5) + design-execution-metrics-separation.md"
---

# R5 — Report Service Rename + Gut Residual Equity Accounting

Rút ruột collector: rename `BacktestResultAppService`→`BacktestReportAppService` + **xoá shadow equity ledger** (`_current_equity`/`_peak_equity`/`_total_commission`) — collector thôi tự tính equity, đọc broker `get_balance()` (single source of truth). R4 đã bỏ FIFO/commission-calc; R5 hoàn tất phần equity accounting.

## Context

- Roadmap hàng R5: `plans/trading-calulation-fix/roadmap.md` · Model E §5/§8: `design-execution-metrics-separation.md`
- Handoff R4 (journal `docs/journals/2026-07-05-r4-broker-trade-emission-remove-fifo.md`): *"R5: rename BacktestResultAppService→BacktestReportAppService, fully event-driven (gut residual equity accounting)."*
- Depends: R1 (done) + R4 (done, `260705-2216-r4-broker-trade-emission-remove-fifo`). Soft-blocks: `260630-0031-backtest-mae-mfe-excursion` (pending — đụng cùng file collector).

## Quyết định khoá (chốt với user)

- **D1 — Equity gut = broker-sourced recorder (parity-exact).** Xoá `_current_equity`/`_peak_equity`/`_total_commission`; equity đọc từ `IBrokerPort.get_balance()`. **Verified**: `broker._balance` cập nhật realized-pnl + commission TRONG lock, dispatch `TradeClosedEvent` NGOÀI lock (contract broker dòng 17) → `on_trade` `await broker.get_balance()` an toàn (không deadlock), `available_balance` == shadow ledger cũ byte-for-byte. → **MỌI metric giữ nguyên** (max_drawdown/total_return/Sharpe/…). KHÔNG collapse về MTM-only.
- **D2 — Chỉ rename + gut, KHÔNG tách file.** Giữ 1 class orchestrator (single subscriber 3 kênh). Không extract order-audit/downsampler ra module. File ~416→~380 dòng (vẫn > guideline 200 nhưng user chọn minimal churn).

## Phases

| # | Phase | Status | Depends |
|---|---|---|---|
| 01 | [Rename + gut equity + wire broker](phase-01-rename-gut-wire.md) | done | — |
| 02 | [Test rework (fake broker) + full validation parity](phase-02-test-validation.md) | done | 01 |
| 03 | [Docs sync + roadmap R5 done + journal](phase-03-docs-roadmap-journal.md) | done | 02 |

## Invariants (mọi phase giữ)

- **Parity byte-for-byte**: engulfing/hitnrun2 characterization tests pass KHÔNG sửa số (max_drawdown/total_return/Sharpe/total_trades/gross PnL). Đây là bằng chứng broker-sourced == shadow cũ.
- **Single equity source**: sau R5 collector KHÔNG còn tự tính equity — mọi giá trị equity từ `broker.get_balance()`.
- **Commission KHÔNG double**: `on_fill` chỉ stamp `result.commission` lên `Fill` doc (broker đã trừ balance); collector không cộng dồn debit.
- import-linter 8 contract xanh; collector (`engine.backtest`) import `IBrokerPort` từ `core.domain.brokers` — hợp lệ `app ◁ engine ◁ core`. No fastapi/bson.
- `git grep '_current_equity\|_peak_equity\|_total_commission\|BacktestResultAppService'` sạch (chỉ còn trong journal lịch sử).

## Validation cuối

`just test` (560 pass, parity number không đổi) · `ruff` · `pyright` · `lint-imports` (8) — tất cả xanh.

## Key risks

- **Test isolation rework** (`test_result_collector_mark_to_market.py`): test hiện drive collector standalone (no broker); giờ cần fake broker cho `get_balance().available_balance`. → Phase 02 dựng minimal fake broker, script balance mirror fills/trades. Invariant "MTM không mutate realized accounting" giờ trivially-true (collector không còn realized accounting) nhưng vẫn assert.
- **`finalize` async**: đọc broker balance → `finalize` chuyển `async`; 2 call site trong `BacktestAppService.run` thêm `await` + test thêm `await`.
