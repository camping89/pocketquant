---
title: "Backtest Research Workbench"
description: "Reframe /backtest thành workbench thống kê: stat dashboard giàu metric, history + compare deep-link, orders drill-down, verdict edit. Dùng lib charting sẵn có (echarts + lightweight-charts). TDD."
status: completed
priority: P2
branch: "develop"
tags: [backtest, web, statistics, tdd]
blockedBy: []
blocks: [260630-0031-backtest-mae-mfe-excursion]
created: "2026-06-30T01:59:20.499Z"
createdBy: "ck:plan"
source: skill
---

# Backtest Research Workbench

## Overview

Biến trang `/backtest` (hiện ad-hoc, single-run, ephemeral — reload là mất) thành **workbench phân tích cho trader định hướng thống kê**: KPI hero + metrics phân nhóm, equity+underwater full-width, phân phối PnL/duration, drawdown table; history list + compare nhiều run với deep-link reload-safe; orders/fills drill-down; verdict edit.

Tận dụng tối đa data + endpoint **đã build sẵn** + **lib charting đã cài** (echarts `^6.0.0`, lightweight-charts `^5.1.0`). Backend chỉ thêm: scoping denormalize + mở rộng 1 endpoint history + 1 endpoint orders.

Brainstorm: [`../reports/brainstorm-260630-0031-backtest-research-workbench-report.md`](../reports/brainstorm-260630-0031-backtest-research-workbench-report.md)
Tái dùng thiết kế history/compare: [`../reports/slice-3-backtest-history-comparison-260628-1959-strategy-tab-foundation-report.md`](../reports/slice-3-backtest-history-comparison-260628-1959-strategy-tab-foundation-report.md)

## Decisions (đã chốt với user + red-team)

- **Scope** = B (Research Workbench) + orders endpoint + verdict UI. **MAE/MFE tách sang plan riêng** `260630-0031-backtest-mae-mfe-excursion` (đụng engine + timing redesign).
- **Coupling B1** — workbench ở `/backtest` standalone, KHÔNG tái-couple subscription. Slice forward (1/2/5) ở `/strategies` không đụng.
- **Charting** = echarts (scatter/heatmap khi cần — đã cài, dùng ở `job-timeline-chart.tsx`) + lightweight-charts `HistogramSeries` (histogram/equity — đã wired theme qua `use-chart.ts`). **uPlot/visx bị loại** (dep thừa: 2 lib trên đã làm được).
- **Storage scoping A2** — denormalize `symbol`+`interval` top-level. **Mở rộng `GET /backtest/strategy/{id}` thêm optional `symbol`/`interval` query param** (KHÔNG tạo endpoint `/runs` mới — red-team H4: trùng chức năng). `symbol` là **composite `CODE:EXCHANGE`** (vd `BTCUSDT:BINANCE`) — không bao giờ bare code.
- **Layout single-run** = tab (Overview / Trades / Risk&Time / Orders).
- **Monthly returns heatmap HOÃN sang iteration 2** (red-team H3: equity downsample ≤5000 → sai số số-liệu với strategy thưa trade). Risk&Time MVP = equity+underwater (drawdown chính xác mỗi điểm) + drawdown table.
- **FE API module** = `web/src/api/backtest-api.ts` (KHÔNG `lib/` — red-team: path sai).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [BE Foundation (scoping + orders endpoint)](./phase-01-be-foundation-scoping-orders-endpoint.md) | Completed |
| 2 | [FE deep-link routing](./phase-02-fe-deep-link-routing.md) | Completed |
| 3 | [FE Stat Pack dashboard](./phase-03-fe-stat-pack-dashboard.md) | Completed |
| 4 | [FE history compare verdict orders](./phase-04-fe-history-compare-verdict-orders.md) | Completed |

## Phase dependencies

```
P1 (BE scoping+orders) ─► P2 (FE routing) ─► P3 (FE dashboard) ─► P4 (FE history/compare/orders/verdict)
```

Tuyến tính. P1 thuần BE. P2-P4 thuần FE, build dần trên shell.
Plan `backtest-mae-mfe-excursion` blockedBy plan này (FE scatter cần Trades tab + echarts wrapper từ P3).

## Acceptance criteria (toàn plan)

- [x] Reload `/backtest/$runId` giữ nguyên kết quả (hết ephemeral).
- [x] Single-run dashboard render đủ: KPI hero, metrics nhóm, equity+underwater, PnL/duration histogram, drawdown table, orders drill-down, verdict edit.
- [x] History list scope đúng theo (strategy_code + symbol composite + interval) — KHÔNG trộn run symbol khác; gửi `symbol=BTCUSDT:BINANCE` (composite) khớp doc.
- [x] Compare 2–3 run: equity overlay + diff table highlight ô best.
- [x] Orders tab: lazy-load, drawer fills/events, DTO key `order_id` (không `_id`).
- [x] BE pass + import-linter 7 contracts; FE `npm run lint && npm run build` pass.

**Lệnh build thực tế (đính chính plan):** `justfile` chỉ có `just test`. Các lệnh canonical (theo CI `cicd.yml` + `pyproject.toml`): lint = `uv run ruff check src/`, types = `uv run pyright`, contracts = `uv run lint-imports`, test = `uv run pytest`, baseline regen = `BASELINE_UPDATE=1 uv run pytest tests/baseline`. Shell env có `MONGODB_URL` trỏ prod → chạy pytest với `env -u MONGODB_URL -u REDIS_URL` (testcontainers tự spin ephemeral).

## Implementation outcome

- BE: 608 passed / 1 skipped · ruff ✓ · pyright ✓ · import-linter 7/7 ✓ · baseline regenerated additive-only (route `get_backtest_orders` + 2 query param). FE: lint 0 errors · build ✓ · vitest 8/8 (`stats-utils`).
- Tên file route theo convention repo (trailing-underscore `monitor_.jobs.$jobId`): `backtest_.$runId.tsx`, `backtest_.compare.tsx` (URL contract giữ đúng `/backtest/$runId`, `/backtest/compare`).
- Code review (DONE_WITH_CONCERNS) → đã xử lý: **H1** verdict mất text khi save fail (reset textarea chỉ khi đổi runId, không khi verdict cùng run đổi do optimistic/revert); **M1** normalize symbol uppercase tại write-side (started/finalize/from_mongo) khớp filter `.upper()`; **M2** thêm vitest cho `stats-utils`. L1/L2/L3 (dedupe timestamp, normalize off initial_capital literal, sampling caveat) ghi nhận — không block, tradeoff đã chấp nhận.

## Non-negotiable constraints (CLAUDE.md)

- Repo chỉ ở `core.infra.persistence.repositories`; query/command service ở `backtest`; route ở `app`; fastapi KHÔNG ngoài `app` (import-linter 7 contracts).
- Route dùng `FromDishka[...]` + `DishkaRoute`, KHÔNG `Depends()`. Service nhận command/query model, trả DTO.
- PK = UUIDv7 (`generate_id_str`), không bson/ObjectId.
- Single uvicorn worker — ad-hoc run giữ `asyncio.create_task` in-process.
- Mọi `await` là preemption point.
- FE: thuần CSS variables (KHÔNG Tailwind), TanStack Router + React Query, theme `data-theme` + CSS variables.

## Dependencies

- Plan hoàn thành `260629-2132-web-claude-theme-ui-tweaks` (done) — theme tokens + `datetime` form. Không blocking.
- `blocks`: `260630-0031-backtest-mae-mfe-excursion` (plan đó blockedBy plan này).

## Red Team Review

### Session — 2026-06-30
**Findings:** 15 (15 accepted, 0 rejected) — 3 reviewer (Failure Mode / Assumption Destroyer / Scope Critic)
**Severity breakdown:** 4 Critical, 4 High, 7 Medium

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| C1 | MAE/MFE timing paradox (`_mtm_on_bar` chạy sau lot remove) | Critical | Accept | Tách → mae-mfe plan (redesign broker-path) |
| C2 | `list_trades` không serialize field mới → cột luôn "—" | Critical | Accept | mae-mfe plan P2 (list_trades) |
| C3 | uPlot thừa (echarts + lightweight-charts HistogramSeries đã cài) | Critical | Accept | P3 (đổi charting) |
| C4 | P2 MAE/MFE đụng engine → tách critical path | Critical | Accept | Tách → mae-mfe plan |
| H1 | symbol composite mismatch (`BTCUSDT` ≠ `BTCUSDT:BINANCE`) → history rỗng âm thầm | High | Accept | P1 + P4 (scope composite) |
| H2 | baseline snapshot tests fail, thiếu `BASELINE_UPDATE=1 just baseline` | High | Accept | P1 (step regen) |
| H3 | monthly heatmap sai số số-liệu (downsample lệch) | High | Accept | Hoãn iter 2 (P3 bỏ heatmap) |
| H4 | `GET /runs` trùng `GET /strategy/{id}` đã có | High | Accept (modified) | P1 (mở rộng endpoint cũ + filter, bỏ /runs) |
| M1 | `Trade` field-order trap | Medium | Accept | mae-mfe plan P2 |
| M2 | regression-lock bỏ sót 2 test file | Medium | Accept | mae-mfe plan P1 |
| M3 | failed-run persist MAE/MFE rác | Medium | Accept | mae-mfe plan P2 (null-out) |
| M4 | Order serialize `_id` vs `order_id` chưa chốt | Medium | Accept | P1 (map service, key order_id) |
| M5 | acceptance "run cũ không lỗi" thiếu test | Medium | Accept | mae-mfe plan P3 (fixture null) |
| M6 | FE module path `lib/` sai → `api/backtest-api.ts` | Medium | Accept | P3+P4 (path đúng) |
| M7 | profit_factor recompute lệch BE | Medium | Accept | P3 (split-only, aggregate reuse BE) |

**Đính chính rationale (controller):** lý do loại visx ban đầu ("React 19 chưa release") SAI — React 19.2.4 stable. Kết luận không-visx vẫn đúng nhờ echarts đã có sẵn.

### Whole-Plan Consistency Sweep
- Đã renumber 5→4 phase (MAE/MFE tách). Mọi tham chiếu "Phase 2 MAE/MFE", "uPlot", "monthly heatmap MVP", "GET /runs", "visx", "lib/backtest-api.ts" đã reconcile khỏi plan này.
- Cross-plan: mae-mfe plan `blockedBy` plan này; plan này `blocks` mae-mfe. Bidirectional set.
- Không còn contradiction chưa giải quyết.

## Validation Log

### Session — 2026-06-30 (6 câu, guard: red-team đã verify → skip verification pass)

| # | Câu hỏi | Quyết định | Propagate |
|---|---------|-----------|-----------|
| 1 | KPI hero 5 metric | Total Return / CAGR / Sharpe / Max DD / Win Rate | P3 |
| 2 | Compare scope | **Cross-scope** (khác strategy/symbol OK), equity overlay bắt buộc normalize % từ initial_capital | P4 |
| 3 | Drawdown table | **Top 5**; recovery = equity chạm lại peak trước drawdown; cột: depth %, start→trough, recovery date, duration | P3 |
| 4 | Diff table "best" | **Per-metric direction map** (xem dưới); highlight ô best mỗi hàng | P4 |
| 5 | History default scope | **Rỗng đến khi chọn strategy** (dropdown registry); chọn strategy → load run gần nhất; symbol/interval optional filter | P4 |
| 6 | Verdict PATCH fail | **Optimistic + revert on fail**, GIỮ text textarea, toast lỗi, cho retry | P4 |

**Per-metric direction map (Q4)** — hướng "tốt" để highlight ô best:
- **Cao = tốt:** total_return, cagr, sharpe_ratio, sortino_ratio, win_rate, profit_factor, avg_win.
- **Cao/gần-0 = tốt** (ít âm hơn): max_drawdown, avg_loss.
- **Thấp = tốt:** total_commission, avg_trade_duration_seconds.
- **Trung tính** (không highlight): total_trades, winning_trades, losing_trades.

**Metrics 3 nhóm (Q1 phụ — chốt phân nhóm cho MetricGroup):**
- **Returns:** total_return, cagr, avg_win, avg_loss.
- **Risk:** sharpe_ratio, sortino_ratio, max_drawdown, profit_factor.
- **Trade Stats:** total_trades, winning_trades, losing_trades, win_rate, avg_trade_duration_seconds, total_commission.

### Whole-Plan Consistency Sweep (validation)
- Q2 cross-scope compare: KHÔNG cần đổi BE (compare fetch từng run qua `useBacktestRun` đã có); chỉ ràng buộc FE normalize %. Không mâu thuẫn P1.
- **Sweep bắt 1 stale claim:** Phase 4 Risk Assessment cũ ghi "compare mặc định cùng scope" — trái Q2. Đã sửa thành cross-scope + normalize % bắt buộc.
- Phân biệt rõ: **history rail** scope theo (strategy, symbol, interval) — không trộn symbol (P1 H1); **compare** thì cross-scope (Q2). Hai khái niệm scope khác nhau, không mâu thuẫn.
- Q5 default scope rỗng: KHÔNG cần endpoint list-all (giữ A2 scoped). Khớp Phase 1. Dropdown strategy dùng `GET /backtest/strategies` (đã có).
- Q1/Q3 thuần FE render — không đụng contract BE.
- Sau sửa: không còn contradiction. Plan sẵn sàng cook.
