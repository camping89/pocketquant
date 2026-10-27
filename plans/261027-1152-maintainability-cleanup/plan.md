---
title: "Maintainability cleanup"
description: "Cut reading and maintenance cost: fix the paper fill-path desync, demote hot-path INFO logs, delete dead and unreachable code, collapse the sync-job and backtest boilerplate, and make paper position ownership explicit."
status: implemented-deploys-pending
priority: P2
effort: 2-3d code + 3 deploys
branch: develop
tags: [cleanup, dead-code, logging, paper-broker, backtest, sync-jobs]
created: 2026-10-27
---
# Maintainability cleanup

## Outcome

A maintainer reads fewer files and hops to follow each flow, prod logs at INFO show only lifecycle and trade events, and no code remains that production cannot reach. Behaviour stays the same except for the listed correctness fixes.

Sources: `plans/261027-1152-maintainability-cleanup/reports/scout-261027-0907-verified-merged-maintainability-review.md` (verified findings, dead-code list) and `plans/261027-1152-maintainability-cleanup/reports/kongming-261027-0907-maintainability-cleanup-advice.md` (ranking, batching, defaults).

## Owner decisions (approved 2026-10-27)

1. Delete the OKX broker. Prod check 2026-10-27: 0 subscriptions with `broker: "okx"`.
2. Delete `tracked_symbol_seeder`. Prod check: no `strategies` collection, 0 orders with status `open` or `partially_filled`.
3. On subscription unload: drop the paper position and disconnect a paper broker with no holders; leave an Exness venue position in place with a WARNING.
4. On restart: the position mirror does not keep paper rows (close them at boot, one log line).
5. Keep `POST /market-data/sync`, `/sync/background`, `/sync/bulk`, `GET /sync-status/{symbol}`, `GET /quotes/current-bar/{symbol}`. Delete `/trading/*` (+ its four `.bru` files), `PUT /tracked-symbols/{symbol}`, `DELETE /strategies/{code}`.
6. Delete `IdempotencyMiddleware`.
7. Remove the tick trigger and the paper LIMIT/pending path with their tests.
8. Follow the CLAUDE.md DEBUG rule for per-minute, per-request and per-fill events.
9. Delete `scripts/recompute_backtest_costs.py` (it ran, 2026-07-10 journal). Keep `scripts/migrate_symbol_asset_class.py`: prod check shows 3 symbols without `asset_class`, so it has not run. Untrack `scripts/rubric/output/` and gitignore it.
10. Do not chase the backtest double-persist race now.
11. Amend CLAUDE.md: a route may inject a repository or `Cache` directly when the handler adds no logic.
12. Delete the in-process SPA mount (`spa_fallback`).

## Non-goals

No change to `core/infra/brokers/exness/exness_broker_adapter.py`. No DI one-liner conversion, no `sync_internals` inlining, no paper-broker result builders, no `components/strategy/` move, no new CI gates. Prod subscription `01a178ef` (ES 15m engulfing paper) is never stopped or deleted.

## Phases (run order)

| # | Phase | Status |
|---|---|---|
| 01 | [Commit pending plan files](phase-01-commit-pending-plan-files.md) | done |
| 02 | [Fill-path safety](phase-02-fill-path-safety.md) | done |
| 03 | [Log levels](phase-03-log-levels.md) — Deploy A point | done |
| 04 | [Backend dead-code deletion](phase-04-backend-dead-code-deletion.md) | done |
| 05 | [Web dead code and small web fixes](phase-05-web-dead-code-and-fixes.md) | done |
| 06 | [Dead live-execution surface and risk check](phase-06-dead-execution-surface-and-risk-check.md) | done |
| 07 | [Sync-job wrapper](phase-07-sync-job-wrapper.md) — Deploy B point | done |
| 08 | [Backtest chain 6 to 3 files](phase-08-backtest-chain-collapse.md) | done |
| 09 | [Paper position ownership and explicit subscriptions](phase-09-paper-position-ownership.md) — Deploy C point | done |
| 10 | [Polish and docs](phase-10-polish-and-docs.md) | done |

## Conventions

- Work on `develop`; one focused conventional commit per phase (a phase may split into 2-3 commits). No push to `master` without the owner's explicit yes: every `master` push deploys.
- Deploy points are where a release is safe; deploying is a separate owner decision. Each deploy follows the "Restart while live" runbook in `docs/deployment.md` and confirms `01a178ef` is still running.
- Gates per phase: `uv run ruff check src scripts tests`, `uv run pyright`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`, then the phase's tests; full `uv run pytest tests` before each deploy point (Docker must run; 4 Windows `tzset` reds are expected). Web: `npm run lint`, `npx tsc -b`, `npm run build` in `web/`.
- Lower the `[tool.code-metrics]` ceilings when a phase lowers the numbers; raise them only with a stated reason.

## Acceptance

- [x] An exception after a paper fill never rejects a FILLED order; the strategy sees the fill.
- [x] One failing event handler no longer stops the others.
- [x] At `LOG_LEVEL=INFO` no line repeats per symbol per minute or per HTTP request.
- [x] Every item in the "confirmed dead" and approved "unreachable" lists is gone, or kept with a stated reason.
- [x] `sync_jobs.py` has one job-history wrapper; a failed run is recorded once.
- [x] A backtest run reads in at most three engine files; stats of a fixed run are unchanged.
- [x] Unloading a paper subscription leaves no broker subscribed to bars; restart leaves no paper rows in the mirror.
- [x] Docs no longer describe OKX, `/trading/*` or removed routes.
