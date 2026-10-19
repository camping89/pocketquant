# Symbol cascade delete — 2026-10-12

Prod cleanup for `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` is done and verified: no document or Redis key references them any more. The code cascade is implemented and passes the full local gate. It sits on the pushed branch `feat/symbol-cascade-delete` (commit `1189e3c`). It is not on master and has not been deployed, because `origin/master` was rewritten during the run (see Blocker below).

## Part 1: prod cleanup

### Backup

- Fresh backup taken before deleting: `/opt/pocketquant/backup-symbol-cascade-20261012T0056/`, 260 MB.
- It holds one gzip `mongodump` archive per touched collection (`bars`, `sync_status`, `symbols`, `tracked_symbols`, `subscriptions`, `backtest_runs`, `backtest_orders`, `backtest_trades`, `job_history`, `orders`, `positions`) and `redis-keys.json`, which stores `DUMP` payloads plus TTLs for the 6 Redis keys.
- The earlier full backup is still in place: `/opt/pocketquant/backup-pre-phase02-invalid-symbols-20261011T1209.archive`.

### Inventory and deleted counts

Every collection was scanned by its `symbol` field, and the smaller collections were also deep-scanned with a regex over the full document.

| Collection / store | Before | Deleted | After |
|---|---|---|---|
| `bars` | 160,395 (ES 53,662 / NQ 53,563 / YM 53,170) | 160,395 | 0 |
| `sync_status` | 21 | 21 | 0 |
| `backtest_runs` | 2 (`engulfing` ES, `engulfing_pullback30_touch` NQ) | 2 | 0 |
| `backtest_orders` | 265 (all belonging to those 2 runs) | 265 | 0 |
| `backtest_trades` | 132 (all belonging to those 2 runs) | 132 | 0 |
| `job_history` | 76,596 `details[]` entries across 25,424 run docs | entries `$pull`ed from 25,424 docs | 0 (all 67,531 run docs kept; none held only these symbols) |
| Redis | 6 `bar:current:*` keys (1d and 1w for each symbol) | 6 | 0 |
| `symbols`, `tracked_symbols`, `subscriptions`, `orders`, `positions`, `trades`, `apscheduler_jobs` | 0 | — | 0 |

Collection totals went from 4,854,635 to 4,694,240 for `bars`, 42 to 21 for `sync_status`, and 17 to 15 for `backtest_runs`.

A concurrent `develop` deploy (run 38161730479) recreated every container right after the deletes. After it finished, I re-checked the counts and all of them were still 0.

## Part 2: code cascade

- `DELETE /api/v1/market-data/tracked-symbols/{symbol}` calls `TrackedSymbolService.remove`, which deletes in this order:
  1. `tracked_symbols`;
  2. each subscription: `StrategyCommandService.stop`, then `remove_symbol`;
  3. `symbols`;
  4. `bars`, which also purges the in-process `_BAR_VALUE_CACHE`;
  5. `sync_status`;
  6. `backtest_orders`, `backtest_trades`, `backtest_runs` (also matching legacy `config_snapshot.symbol`);
  7. live `orders` and `positions`;
  8. the symbol's `job_history.details[]` entries;
  9. the Redis keys `quote:latest:{s}`, `bar:current:{s}:*` and `ohlcv:{s}:*`.
- The route is idempotent: it always returns 200 with `{"symbol", "status": "removed", "deleted": {per-collection counts}}`.
- There is a new `SymbolScopedRepository.delete_by_symbol` in `core.infra.persistence.base_repository`. The repos that hold a symbol extend it, and the unused `TrackedSymbolRepository.delete` was removed.
- Tests:
  - A unit test checks the cascade, the order of the stop-before-remove calls, that other symbols are untouched, and idempotency on partial state.
  - An integration test goes through the route against real Mongo and Redis and checks every collection and cache key for both symbols, plus a second call that returns all zeros.
  - The OpenAPI snapshot was regenerated; only the route description changed.
- Gate on `1189e3c`:
  - `just test`: 687 passed, 1 skipped, 0 failed.
  - `ruff check`: clean.
  - `pyright`: 0 errors.
  - `lint-imports`: 3 kept, 0 broken.
  - `code_metrics.py --ratchet`: exit 0, tiny share 0.4733 against a ceiling of 0.4754, delegations 63 against 63.

## Blocker: master was rewritten, no deploy

- Around 01:06 +07, `origin/master` was pushed from the `pq-develop` worktree to `4b3a77a`, which is the develop history.
- The old master `6a0d01c`, which this work builds on, is no longer an ancestor of it: 411 commits are only on the old master and 547 only on the new one.
- The new master has no `scripts/code_metrics.py`, and `strategy_command_service.py` lives in a different place there.
- The coordinator chose to push the branch only. Pushing `feat/symbol-cascade-delete` started no CI run and no deploy, because CI triggers only on master and develop. So there is no commit on master, no CI run and no deploy Verdict to report.
- The local `pocketquant` worktree is back on `master` at `6a0d01c`.

## Unresolved questions

- The cascade still has to be ported onto the new `origin/master` (`4b3a77a`) and pushed there, with CI watched and the deploy Verdict confirmed.
- The rewrite left local `master` diverged from `origin/master` (411 ahead, 547 behind), so whoever owns master needs to decide which history wins.
- The cascade also deletes live `orders` and `positions` for the symbol, to leave no orphans. If an open live position should block removal instead, that is a product decision.
