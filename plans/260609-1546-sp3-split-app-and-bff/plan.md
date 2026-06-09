---
title: "SP3 — Split app (headless runtime) + bff (FE gateway)"
description: "Tách runtime trading (scheduler/WS/strategy/reconcile) ra khỏi tầng HTTP serve-FE. 2 package: pocketquant-app headless + pocketquant-bff stateless gateway. Mục tiêu: crash/restart bff không gián đoạn live trading."
status: pending
priority: P2
branch: "develop"
tags: [split, bff, isolation, control-plane, sp3]
blockedBy: []
blocks: []
created: "2026-06-09T09:07:52.831Z"
createdBy: "ck:plan"
source: skill
---

# SP3 — Split app (headless runtime) + bff (FE gateway)

## Overview

Runtime trading (scheduler, WS feed, strategy lifecycle, reconcile loop) và tầng HTTP serve-FE đang fused trong 1 process `pocketquant-app`. Nỗi đau: restart FE hoặc crash 1 HTTP request làm gián đoạn strategy live. Tách 2 process:

- **`pocketquant-app`** — headless runtime: DI core, migrations, indexes, scheduler (sync jobs), WS feed, strategy lifecycle, reconcile loop, **backtest-request worker**. Chạy full auto, không cần FE. Chỉ expose 1 endpoint liveness `/health`.
- **`pocketquant-bff`** — stateless FastAPI: serve `pocketquant-web/dist`, đọc Mongo/Redis, ghi desired-state, enqueue backtest-request. Chết/restart thoải mái, **không đụng RAM strategy, không chạy scheduler/WS/reconcile**.

Sau SP1 (declarative control plane) + SP2 (rename api→app) đều **completed**, ranh giới start/stop đã là Mongo. SP3 đóng nốt 3 write-path còn dính RAM/scheduler và đưa toàn bộ backtest execution sang app qua queue, để bff thật sự thin.

```
        ┌──────────── pocketquant-app (headless) ──────────┐
        │ DI(core+runtime) · migrations · indexes · recover │
        │ scheduler(sync) · WS feed · strategies            │
        │ RECONCILE LOOP · BACKTEST-REQUEST WORKER          │
        │ /health (liveness only)                           │
        └──────────┬────────────────────┬───────────────────┘
                   │ đọc desired_state   │ đọc/ghi
                   │ + backtest_requests │
              ┌────▼────┐          ┌────▼────┐
              │  Mongo  │          │  Redis  │
              └────┬────┘          └────┬────┘
                   │ ghi desired-state + enqueue request
        ┌──────────▼────────────────────────────────────────┐
        │ pocketquant-bff (stateless FastAPI) · serve web    │
        │ read routes + start/stop + add/remove/delete sub   │
        │ + sync/integrity + enqueue backtest                │
        │ (DI: core + read/write-DB only — no engine)        │
        └──────────┬─────────────────────────────────────────┘
                   │ HTTP (/api/v1)
                 [pocketquant-web]
```

## Locked decisions (user-confirmed 2026-06-09)

| # | Decision | Value | Ghi chú |
|---|----------|-------|---------|
| D1 | Code split shape | **2 packages** — `pocketquant-bff` mới (routes + serve web) + `pocketquant-app` giữ runtime/DI core | Hard import boundary, import-linter enforce |
| D2 | RAM-coupling fix | **Fully declarative** — bff = 100% Mongo writes; app control-plane sở hữu instance lifecycle | add_symbol chỉ persist sub; app load/unload + drain backtest queue |
| D3 | app health | **Minimal liveness HTTP** — single `/health` route, không full router stack | Giữ docker healthcheck pattern hiện có |
| D4 | web rename | **Giữ `pocketquant-web`** | FE chỉ đổi proxy target sang bff |
| D5 | Backtest execution | **Toàn bộ trên app** (single + run_all) | bff enqueue, FE poll |
| D6 | Queue mechanism | **Mongo collection `backtest_requests` + app poll-loop** | KHÔNG RabbitMQ/Kafka. Pattern poll-loop như reconcile + WsSubscriptionManager. Bỏ APScheduler `bt:*` jobs |
| D7 | Single backtest FE | **Sửa FE sang poll** | `use-backtest.ts` từ await synchronous → enqueue + poll, đồng nhất run_all |

## Hiện trạng đã verify (khác brainstorm — đọc kỹ)

Brainstorm report claim "sau SP1, ranh giới = 100% Mongo, command channel biến mất". **Verify PARTIALLY FALSE** — 4 write-path còn dính RAM/scheduler:

| Handler | Coupling | File:line |
|---------|----------|-----------|
| `start` / `stop` | ✅ pure Mongo write (đã sạch sau SP1) | `start/handler.py:25`, `stop/handler.py` |
| `add_symbol` | ❌ `load_strategy()` vào RAM | `add_symbol/handler.py:58-67` |
| `remove_symbol` | ❌ `unload_strategy()` + `scheduler.remove_job` | `remove_symbol/handler.py:34,39` |
| `delete` | ❌ `unload_strategy()` + `scheduler.remove_job` | `delete/handler.py:44-50` |
| `run_all_backtests` | ❌ `scheduler.add_one_off_job` (RuntimeError nếu scheduler chưa start) + bt job cần strategy config trong RAM | `run_all_backtests/handler.py:38`, `subscription_backtest_jobs.py:102` |
| `backtest/run` (single) | ❌ synchronous, tự inject strategy vào shared `StrategyAppService`, replay CPU-heavy | `run/handler.py:78-96` |

Đã bff-safe sẵn (không đụng RAM/scheduler):
- Mọi read route (chart/ohlcv/status/positions/trades/list_symbols/get_all). FE live data qua Redis/Mongo (`stream_bars/route.py`).
- WS feed declarative sẵn: `WsSubscriptionManager` reconcile `tracked_symbols` (Mongo) mỗi 5s (`ws_subscription_manager.py:45-60`). `tracked_symbols/add|remove|update` = pure DB write.
- `sync` / `sync/bulk` / `integrity check|repair` = stateless DB writes (gọi REST Binance + ghi Mongo, không đụng RAM/scheduler).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Bff package scaffold](./phase-01-bff-package-scaffold.md) | Completed |
| 2 | [Backtest request queue](./phase-02-backtest-request-queue.md) | Completed |
| 3 | [Control-plane instance lifecycle](./phase-03-control-plane-instance-lifecycle.md) | Completed |
| 4 | [DI split and two entrypoints](./phase-04-di-split-and-two-entrypoints.md) | Completed |
| 5 | [FE single-backtest poll](./phase-05-fe-single-backtest-poll.md) | Pending |
| 6 | [Deploy CI import-linter](./phase-06-deploy-ci-import-linter.md) | Pending |
| 7 | [Verify isolation](./phase-07-verify-isolation.md) | Pending |

## Key dependencies (phase ordering)

- **Phase 2 + 3 phải xong trước Phase 4.** Hai phase này biến add/remove/delete + backtest thành fully-declarative; chỉ khi đó bff mới có thể bỏ engine/scheduler khỏi DI subset.
- Phase 2 (queue) cung cấp backtest-request worker → gỡ APScheduler `bt:*` ⇒ remove/delete mất luôn coupling `scheduler.remove_job` (Phase 3 nhẹ đi).
- Phase 1 (scaffold bff package) độc lập, làm trước/song song Phase 2-3.
- Phase 4 (DI split + 2 entrypoint) là điểm hợp nhất — cần Phase 1,2,3 xong.
- Phase 5 (FE poll) cần Phase 2 (queue + status doc) xong để có endpoint enqueue + status.
- Phase 6 (deploy/CI/import-linter) cần Phase 4 (2 entrypoint tồn tại).
- Phase 7 verify toàn bộ isolation + full suite.

## TDD note

Mode `--tdd`: đụng critical runtime split. Mỗi phase viết behavior/characterization test trước:
- Phase 2: queue enqueue→worker→status round-trip; idempotent re-enqueue.
- Phase 3: add_symbol KHÔNG load RAM; control-plane load missing instance + unload orphan; KHÔNG clobber synthetic backtest instances.
- Phase 4: bff container resolve KHÔNG có JobScheduler/StrategyAppService/WS provider; app container resolve KHÔNG có public feature routers.
- Phase 7: kill bff khi strategy running → trades/positions tiếp tục; app standalone → reconcile+WS+worker chạy.

## Dependencies

Cross-plan:
- **Blocked by** SP1 (`260609-1340-sp1-declarative-control-plane`) — **completed**. Cung cấp desired/actual_state + reconcile loop.
- **Blocked by** SP2 (`260609-1450-sp2-rename-api-to-app`) — **completed**. Package đã là `pocketquant-app`, module `pocketquant.app.*`.
- Cả 2 đã merge ⇒ SP3 không bị chặn. Đây là sub-project cuối (3/3).
