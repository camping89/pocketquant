---
title: "Strategy Subscriptions + Cached Backtest"
description: "1 strategy ↔ N symbol subscriptions; manual async backtest persisted in mongo; chart đọc cache; cascade delete"
status: pending
priority: P2
branch: "develop"
tags: [backtest, strategy, mongo, cqrs, frontend]
blockedBy: []
blocks: []
created: "2026-05-05T03:29:38.263Z"
createdBy: "ck:plan"
source: skill
brainstorm: ../reports/brainstorm-260505-1024-strategy-subscriptions-cached-backtest.md
---

# Strategy Subscriptions + Cached Backtest

## Why

Hiện chọn strategy → trigger `POST /backtest/run` → recalc đồng bộ → UX chậm. Mỗi strategy chỉ gắn 1 symbol qua YAML → không scale.

Mục tiêu: tách "compute" khỏi "view". User Run thủ công → persist → chart đọc cache đọc nhanh. 1 strategy ↔ N subscriptions (symbol/exchange/interval) qua mongo.

## Resolved Decisions

(xem brainstorm) Tóm tắt khoá:
- Manual trigger qua "Run All Backtests" (fan-out async)
- 1 backtest per subscription, upsert by `subscription_id`
- Range = full data có sẵn cho symbol+interval
- Cascade delete strategy → subscriptions → backtest_runs
- Stale = display `last_run_at`, manual refresh
- Auth/authz: skip

## Phases

| # | Phase | File | Status | Est |
|---|-------|------|--------|-----|
| 1 | Backend Domain & Repos | [phase-01-backend-domain-repos.md](./phase-01-backend-domain-repos.md) | Pending | 0.5d |
| 2 | Backend Job Worker & CQRS | [phase-02-backend-job-worker-cqrs.md](./phase-02-backend-job-worker-cqrs.md) | Pending | 1d |
| 3 | Frontend Subscription Panel | [phase-03-frontend-subscription-panel.md](./phase-03-frontend-subscription-panel.md) | Pending | 1d |
| 4 | Tests & Stale Recovery | [phase-04-tests-stale-recovery.md](./phase-04-tests-stale-recovery.md) | Pending | 0.5d |

## Dependencies

- P2 ⟵ P1 (CQRS handlers cần entity + repo)
- P3 ⟵ P2 (FE consume routes)
- P4 ⟵ P3 (E2E + recovery cần full stack)

## Success

1. Switch subscription → chart paint < 200ms (no recalc)
2. POST `/run-all` trả < 100ms với `[job_ids]`
3. Run-all N subs → N jobs song song, UI cập nhật từng cái
4. DELETE strategy → 0 docs còn lại trong `strategy_subscriptions` + `backtest_runs` với strategy_id đó
5. Concurrent run-all x2 → 1 job slot per subscription (replace_existing)

## Out of Scope

- Auth/authz
- Backtest history versioning
- Auto-refresh khi có bars mới
- Per-row Run button
- UI chỉnh range backtest
