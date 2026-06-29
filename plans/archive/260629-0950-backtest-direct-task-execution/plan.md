---
title: "Backtest single-run direct-task: remove queue/optimize/run-all, subscription→forward-only, new backtest UI"
description: >-
  Backtest chuyển sang DUY NHẤT single-run /backtest/run chạy bằng direct asyncio
  task (tạo run doc status=started → spawn task → engine persist runs+orders+trades+equity
  → finished/failed). Xóa hẳn: async queue (backtest_requests + worker, gated ENABLE_JOBS),
  /optimize grid, run-all-backtests fan-out. Subscription trở thành THUẦN forward-testing
  (gỡ backtest cache + endpoints khỏi subscription, không động start/stop/positions/trades).
  Status vocab running/completed → started/finished/failed (+ data migration prod). Thêm UI
  single-run mới (form + trang kết quả). No concurrency cap (user tự quản, đã chấp nhận
  evidence pool dùng chung live engine). Red-team 15 findings applied. TDD.
status: done
priority: P2
branch: "develop"
tags: [backtest, execution-model, refactor, di, tdd, fastapi, react, red-teamed]
blockedBy: []
blocks: []
created: "2026-06-29T03:54:34.998Z"
createdBy: "ck:plan"
source: skill
---

# Backtest single-run direct-task: remove queue/optimize/run-all, subscription→forward-only, new backtest UI

## Overview

Brainstorm: `plans/reports/brainstorm-260629-0950-backtest-direct-task-execution-report.md`.
Red-team adjudication: `reports/from-code-reviewer-to-planner-red-team-adjudication-report.md`.

**Kiến trúc mới (re-scope sau red-team):**
- **Backtest = CHỈ single-run** `POST /backtest/run` (ad-hoc config tự do) chạy bằng direct `asyncio.create_task`.
- **Subscription = THUẦN forward-testing** — gỡ backtest cache + `/subscriptions/{id}/backtest` + run-all khỏi subscription. KHÔNG động start/stop/positions/trades/reconcile.
- **Thêm UI single-run**: route FE `/backtest` (form trigger + trang kết quả metrics/equity/trades).
- **Xóa**: queue (`backtest_requests` + worker) + `/optimize` grid + `run-all-backtests` + coupling `ENABLE_JOBS` cho backtest.

**Quyết định đã chốt với user:**
- Execution: direct `asyncio.create_task` (engine async; KHÔNG OS thread). Single uvicorn worker.
- Status: `running/completed` → `started/finished/failed`. Error → `failed` + `error_message` (log only, no retry).
- **KHÔNG cap concurrency** — user tự quản traffic, đã chấp nhận rủi ro pool(50) dùng chung live engine (red-team C4).
- KHÔNG startup sweep ban đầu — NHƯNG red-team M2/C1 buộc giữ 1 sweep nhẹ rename `started` (xem phase 2) để tránh doc kẹt `started` + FE poll vô hạn.
- DI/scope: GIỮ NGUYÊN singleton `AsyncMongoClient` + pool(5/50) + repo `Scope.APP`.
- Key: single = `run_id` (lịch sử nhiều run).
- Drop prod `backtest_optimization_runs` + `backtest_requests` SAU deploy ổn + bake window (red-team H4).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Characterization tests](./phase-01-characterization-tests.md) | Done |
| 2 | [Backend single-run direct-task](./phase-02-backend-single-run-direct-task.md) | Done |
| 3 | [Remove queue optimize run-all](./phase-03-remove-queue-optimize-run-all.md) | Done |
| 4 | [Decouple subscription backtest](./phase-04-decouple-subscription-backtest.md) | Done |
| 5 | [Frontend single-run UI](./phase-05-frontend-single-run-ui.md) | Done |
| 6 | [Cleanup & prod migration](./phase-06-cleanup-prod-migration.md) | Done |

Thứ tự: 1 → 2 → 3 → 4 → 5 → 6. Phase 1 khóa hành vi engine/persist (TDD). Phase 2 core. Phase 3 gỡ queue/optimize/run-all. Phase 4 gỡ backtest khỏi subscription (backend + FE remove). Phase 5 thêm UI single-run. Phase 6 verify + prod.

## Red Team Review

### Session — 2026-06-29
**Findings:** 15 (13 accepted, 2 user-decision)
**Severity breakdown:** 6 Critical, 6 High, 3 Medium
**Reviewers:** Failure Mode Analyst, Assumption Destroyer, Security/Data-Integrity Adversary

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| C1 | `BacktestAppService.run()` catch+return, không re-raise → plan's mark_failed dead code | Critical | Accept | Phase 2 |
| C2 | `run()` sinh run_id nội bộ (line 72) → started doc ≠ finished doc mismatch | Critical | Accept | Phase 2 |
| C3 | `StrategyCommandService` hard-dep `BacktestRequestRepository` → app không boot khi xóa | Critical | Accept | Phase 3/4 |
| C4 | No cap + pool chung live engine → starve live order persistence | Critical | User: giữ no cap | Phase 2 (doc risk) |
| C5 | `list_by_strategy_code`/`get_best_by_metric` hardcode `status=="completed"` | Critical | Accept | Phase 2 |
| C6 | FE poll-start keyed `'running'`; blanket grep phá domain khác | Critical | Accept | Phase 4/5 |
| H1 | `BacktestConfig` nằm trong `optimization/` dir định xóa | High | Accept | Phase 3 |
| H2 | `run_subscription` persist flag flip corrupt cache | High | Moot (xóa run_subscription) | Phase 4 |
| H3 | Vocab rename không migrate prod docs cũ | High | Accept | Phase 6 |
| H4 | Drop prod collection race VPS old code (auto-deploy) | High | Accept | Phase 6 |
| H5 | FE không consume single-run path | High | Resolve (thêm UI) | Phase 5 |
| H6 | "yield mỗi bar" sai (YIELD_INTERVAL=100) → starve event loop | High | Accept | Phase 2 |
| M1 | `BacktestResult.started()` cần full zero metrics + completed_at | Medium | Accept | Phase 2 |
| M2 | Shutdown cancel+mark_failed unreliable (CancelledError BaseException) | Medium | Accept | Phase 2 |
| M3 | Phase 6 re-smoke dùng /optimize đã xóa; .env naming | Medium | Accept | Phase 6 |

### Whole-Plan Consistency Sweep
Re-read toàn bộ plan.md + 6 phase sau khi áp findings. Verified: "run-all"/"queue"/"optimize" chỉ xuất hiện ở ngữ cảnh xóa/gỡ (không còn KEEP); "no cap" nhất quán (phase 2 + risk); status vocab `started/finished/failed` nhất quán xuyên phase 1/2/5/6; "subscription backtest" chỉ ở ngữ cảnh remove/decouple (forward-testing giữ); H2 đánh dấu moot (xóa run_subscription thay vì fix flag); C3 thứ tự gỡ-dep-trước-xóa-repo nhất quán phase 3↔4; 6 phase khớp table. Không còn mâu thuẫn unresolved.

## Validation Log

### Session — 2026-06-29
Verification pass SKIPPED (Red Team Review đã có verification evidence file:line; không có `[UNVERIFIED]` tags). 4 câu hỏi decision-point còn mở, tất cả chốt option recommended:

1. **Startup sweep**: CHẤP NHẬN sweep nhẹ (boot flip `started`→`failed` interrupted_by_restart). Reconcile mâu thuẫn "KHÔNG sweep" ban đầu → plan đã đưa sweep nhẹ vào phase 2 (M2). Confirmed.
2. **Trades display (phase 5)**: endpoint riêng `GET /backtest/{run_id}/trades` (song song `/equity`). Nâng từ "maybe-modify" → BẮT BUỘC. Backend nhỏ thêm ở phase 2 hoặc 5.
3. **H6 event loop**: GIẢM `YIELD_INTERVAL` 100 → ~10 (không chỉ document). Bảo vệ WS/reconcile/health cùng process.
4. **H3 migration**: prod `running` cũ → `failed` (error_message `interrupted_by_migration`). Confirmed như phase 6.

### Whole-Plan Consistency Sweep (post-validation)
Re-read sau propagate: trades endpoint giờ BẮT BUỘC (phase 5 + phase 2 success criteria); YIELD_INTERVAL giảm 10 (phase 2); sweep nhẹ confirmed (phase 2); H3 running→failed (phase 6). Không mâu thuẫn mới. Plan sẵn sàng implement.

## Acceptance Criteria

- `POST /backtest/run` → 202 `{run_id}`; doc `backtest_runs {status:"started"}` tức thì; engine xong → `finished` + metrics + equity + orders + trades; lỗi → `failed` + error_message.
- run_id route-allocated == persisted run doc `_id` == `backtest_orders.run_id` == `backtest_trades.run_id` (C2).
- Subscription KHÔNG còn backtest: `/subscriptions/{id}/backtest` + run-all xóa; subscription card chỉ forward-testing. Forward (start/stop/positions/trades) KHÔNG đổi.
- Không còn `/backtest/optimize`, `/backtest/requests`, `backtest_requests`, `BacktestRequestWorker`, `GridOptimizationAppService`, coupling `ENABLE_JOBS` cho backtest.
- App boot OK sau khi xóa `BacktestRequestRepository` (StrategyCommandService dep gỡ — C3).
- `list_by_strategy_code`/`get_best_by_metric` trả run `finished` (C5).
- FE: route `/backtest` mới (form + kết quả); badge/poll dùng `started/finished/failed`; KHÔNG phá job-history/sync/forward badge (C6).
- Prod docs cũ migrate `completed→finished`, `running→started` (H3).
- `ruff`+`pyright`+`lint-imports`(7)+`pytest` xanh; `cd web && npm run lint && npm run build` xanh.

## Dependencies

Không có cross-plan dependency. Plans backtest trước đã `done`. Forward-testing (subscription start/stop/reconcile) OUT OF SCOPE — không động.