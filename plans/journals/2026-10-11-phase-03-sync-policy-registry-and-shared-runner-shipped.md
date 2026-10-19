---
title: Phase 03 sync policy registry and shared runner shipped
date: 2026-10-11
summary: Per-exchange SyncPolicy registry and one sync runner replace sync_jobs/integrity_jobs/sync_internals; Binance behaviour unchanged in prod
---

# Phase 03 sync policy registry and shared runner shipped

## What happened
- Phase 03 of `plans/261009-0858-exness-venue-lean-sync-refactor` shipped as `c245ba9`. CI run 38142141699 is green with verdict `HEALTHY (20/20 passed, 0 warnings, 0 failures)`.
- New modules: `engine/market_data/sync_policy.py` (SyncPolicies registry resolves strictly by exchange suffix, session-based MarketCalendar), `sync_runner.py` (all 5 scheduled jobs), `bar_integrity.py` (calendar-aware integrity, repair, cascade verify), `scripts/migrate_okx_market_data.py`.
- Deleted `app_services/sync_jobs.py`, `app_services/integrity_jobs.py`, `sync_dtos.py` and `sync_internals/`. SyncService, QuoteAppService, WsSubscriptionManager and TrackedSymbolBackfillService now get providers only through the policy registry.
- Prod `:OKX` inventory was 0, so no backup or migration ran. The first post-deploy `sync_1m` completed, and `apscheduler_jobs` holds all 5 ids with 0 stale refs.

## Problems hit
- The plan's helper folds left `sync_one` at 93 lines (rule is 60). Split it into a guard method plus `_sync_with`.
- `test_no_progress_tracking.py` used the reversed symbol `BINANCE:BTCUSDT`. Strict suffix routing exposed it; the test data was corrected.
- `asyncio.create_task(asyncio.gather(...))` from the plan text would raise TypeError; wrapped in a coroutine instead.
- The structlog `cache_logger_on_first_use` made a capture_logs test fail only in the full suite; fixed by rebinding the module logger per test.
- pyright reportPrivateUsage on the cross-module `_verify_one_symbol`; renamed to `verify_one_symbol`.
- Docker Desktop was down, so testcontainers tests errored until it was started.

## Next steps
- Phase 04 (collapse DI, routes and wrappers).
- `docs/code-standards.md:722` still names `sync_jobs`; Phase 05 rewrites that standard.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
