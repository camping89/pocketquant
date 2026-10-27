# Integrate develop, step 1: port the straightforward old-master commits

Three of the four old-master commits are now on `develop`. The fourth, `3bd4439`, was not needed. CI run 38362717425 passed, and the deploy verify step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Commits on develop (base 4b3a77a, pushed as 4b3a77a..3bb21cb)

| New | Source | Subject |
|---|---|---|
| e670304 | e96b2db | feat(exness): add read-only api spike script and single-line env guard |
| 1b6073e | 22f04b6 | test: read layout contract files as utf-8 and narrow optional take-profit |
| 91978b9 | 1189e3c | feat(market-data): cascade-delete every document and cache key of a removed symbol |
| 3bb21cb | — | docs(plans): add develop re-validation reports for the exness venue plan |
| skipped | 3bd4439 | style: separate first-party imports. `ruff check --select I001 tests` already passes on develop, and `tests/backtest_test/engine/test_lot_tracker.py` does not exist there. |

All ports used `git cherry-pick -x`.

## Conflicts and resolutions

**e96b2db (Exness spike)**
- `pyproject.toml`: kept develop's `tvdatafeed` git pin and added `cryptography>=46`. I regenerated `uv.lock` from develop's lock with `uv lock`, which resolved 102 packages.
- `scripts/exness_spike.py`: the import now points at `core.domain.bar.services.bar_builder_domain_service`. `candle_stats` passes `Continuous24x7Calendar()` to `is_bar_aligned`. That calendar delegates to `get_bar_start`, so this is the same UTC-epoch grid check the spike was written for.
- Verified: `tests/scripts/test_exness_spike.py` passes (17 tests), `exness_spike.py --help` runs, and a sample `candle_stats` call returns `all_aligned: True`.

**22f04b6 (utf-8 / take-profit)**
- Both problems exist on develop: `open(path)` had no encoding, and pyright reported `reportOptionalOperand` at `test_engulfing.py:177`. The commit applied cleanly.

**1189e3c (symbol cascade delete)**
- `app/routes/market_data.py`: kept develop's version, which is only a router aggregator. The route docstring moved to `app/routes/tracked_symbols.py`, where develop defines the DELETE route.
- `backtest_order_repository.py` and `backtest_trade_repository.py`: kept develop's `OrderRecord`/`Trade` imports and docstrings, and changed the base class to `SymbolScopedRepository`.
- `engine/strategy/strategy_command_service.py` (moved on develop): kept develop's command-object signature. `remove_symbol(cmd: RemoveSymbolCommand)` now returns the deleted count.
- `engine/market_data/tracked_symbols_service.py`: kept develop's command-object API (`remove(RemoveTrackedSymbolCommand)`). The cascade calls `stop(StopStrategyCommand)` and then `remove_symbol(RemoveSymbolCommand)` for each subscription.
- Collections and keys added to cover develop:
  - The live `trades` collection: `TradeRepository` now extends `SymbolScopedRepository`, and `Trade` has a `symbol` field.
  - The `data_lag:{symbol}` Redis key.
- No other symbol-keyed collection exists on develop. I checked every `_collection_name` and every `CACHE_KEY_*`. The `strategies` collection is only read by `tracked_symbol_seeder` and has no writer.
- `tests/baseline/openapi_app_snapshot.json` and `tests/app_test/market_data/test_tracked_symbol_repository.py` are deleted on develop, so I removed them rather than restoring them.
- `tests/core_test/infra/persistence/test_tracked_symbol_repository.py`: the old commit's version contained mojibake (`â€”`). I rebuilt the file from develop's version plus the two-line `delete_by_symbol` change.
- Tests ported and adapted: `tests/engine_test/market_data/test_tracked_symbols_service.py` and `tests/app_test/integration/test_tracked_symbol_cascade_delete_api.py`. The integration test runs against real Mongo and Redis. Both now also cover `trades` and `data_lag`.
- `docs/system-architecture.md`: added a "Symbol removal" section that lists `trades` and `data_lag`.
- Behaviour change: deleting a symbol is now idempotent. It returns 200 with per-collection counts under `deleted` and no longer returns 404 for an untracked symbol. Nothing under `web/src` calls this route.

## Gate

- **`just test` (Windows):** 920 passed, 1 skipped, 4 failed, 4 errors. All 8 come from `time.tzset`, which does not exist on Windows. They are in `test_utc_runtime_guard.py` and `test_cron_trigger_timezone.py`, which this work did not touch. On Linux CI, all three timezone legs passed; the UTC leg reported 924 passed and 1 skipped.
- **Focused tests:** 31 passed across the cascade, repository and strategy-service tests.
- **ruff:** `ruff check src tests scripts/exness_spike.py` is clean. `ruff check .` still reports 322 pre-existing errors outside `src/` and `tests/`. I formatted only the files whose formatting this work broke.
- **pyright:** `src/` and every touched file have 0 errors. The whole project has 34 errors, all pre-existing in untouched test files; there were 35 before the `22f04b6` fix. CI does not run pyright. The coordinator chose to accept this scope (option A).
- **lint-imports:** 10 contracts kept, 0 broken.

## CI and deploy

- Run 38362717425 on develop at 3bb21cb succeeded:
  - tests (UTC, Asia/Ho_Chi_Minh, America/Chicago)
  - build-app and build-web
  - cleanup-tags
  - deploy
- Deploy "Verify on VPS" printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Unresolved questions

- 34 pre-existing pyright errors in tests and 322 pre-existing ruff errors outside `src/` and `tests/` remain on develop. Fixing them is a separate cleanup.
