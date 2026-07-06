---
title: "R8 — Live-Run Extraction + Live Trade Pipeline"
description: "Trích live-run orchestration vào engine (thin app driver) + dựng live Trade collector/metrics (model M1 relative-per-sub). Roadmap trading-calulation-fix hàng R8."
status: done
priority: P2
branch: "develop"
tags: [engine, live, structure, trading-calc, r8]
blockedBy: []   # R2 (structure) DONE → hết hard blocker. Soft-coupling: 260630-0031-backtest-mae-mfe-excursion đụng Trade VO + TradeClosedEvent (append-only) — không bên nào cần output bên kia; bên land sau rebase nhẹ.
blocks: []
created: "2026-07-06T02:00:00.000Z"
createdBy: "ck:plan"
source: skill
---

# R8 — Live-Run Extraction + Live Trade Pipeline

## Overview

Roadmap `plans/trading-calulation-fix/roadmap.md` hàng **R8** (track hybrid, dep R2 ✅).
Brainstorm: [`../reports/brainstorm-260706-0200-r8-live-run-extraction.md`](../reports/brainstorm-260706-0200-r8-live-run-extraction.md).

**Reframe (từ brainstorm):** R2 đã tách ~80% cấu trúc; reconcile là plain asyncio task (KHÔNG scheduler). Giá trị thật = **pipeline Trade/metrics cho live** (chưa tồn tại — live nay đọc closed Positions, không `Trade`/equity/metrics). `TradeClosedEvent` đã mang `subscription_id`+`symbol` → attribution giải sẵn.

## Scope (decisions locked)

- **Structural:** move `BrokerFactory`→`core/infra/brokers/`; move `QuoteAppService`+`WsSubscriptionAppService`→`engine/market_data/app_services/`; fold `rehydrate_strategies_from_subscriptions`→`StrategyReconcileAppService.bootstrap()`. **Thin app driver** (app giữ `create_task`/cancel + `enable_jobs` gate).
- **Logic (M1 relative-per-sub):** `LiveTradeCollector` (EventBus subscriber → build `Trade`, `run_id←subscription_id`) → persist `trades` collection; `LiveMetricsQueryService` on-demand `PerformanceCalculatorDomainService.build` (equity = cumsum pnl); route `GET /subscriptions/{id}/metrics`. Wire broker→bus qua `subscribe_trades(lambda e: bus.publish(e))`. Backtest collector KHÔNG đụng.
- **OKX** `subscribe_trades` giữ no-op (external dep: demo payload).

## Phases

| Phase | Name | Track | Status |
|-------|------|-------|--------|
| 1 | [Relocations (BrokerFactory + Quote/WsSubscription)](./phase-01-relocations.md) | structure | ✅ Done |
| 2 | [Fold rehydrate → reconcile.bootstrap()](./phase-02-fold-rehydrate-bootstrap.md) | structure | ✅ Done |
| 3 | [TradeRepository (live `trades`)](./phase-03-trade-repository.md) | logic | ✅ Done |
| 4 | [LiveTradeCollector + broker→bus wiring](./phase-04-live-trade-collector.md) | logic | ✅ Done |
| 5 | [LiveMetricsQueryService + metrics route](./phase-05-live-metrics-query-route.md) | logic | ✅ Done |
| 6 | [Closeout — OKX no-op, docs/roadmap sync](./phase-06-closeout-okx-docs.md) | docs | ✅ Done |

Thứ tự: structure (1→2) trước để logic không rebase path; logic 3→4→5 theo build order; 6 chốt.

## Invariants (mọi phase)

- `just test` (560 parity) + `uv run ruff check .` + `uv run pyright` + `uv run lint-imports` (8 contract) **xanh sau mỗi phase**.
- Structure phase = **move thuần, không đổi logic** — test đỏ vì logic ⇒ dừng, tách.
- `fastapi only in app`; `BrokerFactory` ở `core.infra` (infra→domain/common OK); engine không import app.
- Mỗi move: chạy `lint-imports` + `pytest` NGAY để bắt import app-only bị kéo theo.

## Acceptance criteria

- [x] `engine/live/`: reconcile + `bootstrap()` + `LiveTradeCollector` + `LiveMetricsQueryService`. App lifespan chỉ `inject → bootstrap() → create_task(run()) → cancel`.
- [x] `BrokerFactory` ở `core/infra/brokers/`; `Quote`/`WsSubscription` ở `engine/market_data/app_services/`; zero fastapi trong engine.
- [x] Paper subscription đóng trade → `trades` có `Trade` doc (`run_id`=sub_id, pnl/commission avg-cost đúng).
- [x] `GET /subscriptions/{id}/metrics` trả `PerformanceMetrics` (trade-derived + drawdown/Sharpe theo M1).
- [x] 8 import-linter contract xanh; 560 parity test xanh; ruff/pyright xanh.

## Constraints (CLAUDE.md)

- Repo chỉ ở `core`; engine framework-free; mọi `await` là preemption point; UUIDv7.
- Thêm field domain `Trade` → append SAU field cuối (dataclass non-default sau default = import error). R8 KHÔNG đổi shape `Trade` (chỉ dùng lại).

## Dependencies

- **blockedBy:** none (R2 done).
- **Soft-coupling:** `260630-0031-backtest-mae-mfe-excursion` (pending) append `mae/mfe/r_multiple` vào `Trade` + `TradeClosedEvent`. Không hard-block; bên land sau rebase nhẹ (live collector để field excursion = None, ngoài scope R8).
