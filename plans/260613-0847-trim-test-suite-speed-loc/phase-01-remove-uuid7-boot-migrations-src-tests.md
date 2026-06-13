---
phase: 1
title: "Remove uuid7 boot migrations (src + tests)"
status: completed
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Remove uuid7 boot migrations (src + tests)

## Overview

The 7 uuid7 re-key boot migrations are deployed + verified on prod (git log `791cbbe`, `2cd9813`, …); prod data is fully migrated and no other env boots legacy-shape data (user-confirmed). Remove the migration functions from `main_extensions.py`, their call sites in `main.py` + `app_factory.py`, and the 7 unit test files. Net: ~700 src LOC, ~1,223 test LOC, 30 tests gone.

## Requirements

- Functional: app boot (`main.py` lifespan + `app_factory.make_test_app`) still completes on fresh and already-migrated Mongo. Live boot steps (`ensure_all_indexes`, `recover_*`, `seed_tracked_symbols`, `rehydrate_*`) unchanged.
- Non-functional: `just lint`, `just types`, import-linter all green. No dangling imports.

## Architecture

7 migration functions in `src/pocketquant/app/main_extensions.py` (verified line ranges):
- `migrate_strategy_id_fields` (217), `migrate_subscription_desired_state` (250), `migrate_tracked_symbols_uuid_ids` (282), `migrate_job_history_uuid_ids` (333), `migrate_backtest_request_ids` (387), `migrate_backtest_run_cache_ids` (427), `migrate_subscription_uuid_ids` (480, ends ~592).

3 helpers used **only** by `migrate_strategy_id_fields` (verified — sole callers at lines 233/237/242):
- `_rename_collection_if_needed` (144), `_rename_field_if_needed` (167), `_drop_legacy_indexes` (196).

KEEP (live boot/runtime): `ensure_all_indexes` (90), `recover_stale_backtests` (594), `recover_orphan_jobs` (605), `rehydrate_strategies_from_subscriptions` (622), all `start_*`/`stop_*` lifecycle, `register_*`, `configure_middleware`, `_list_jobs_from_mongo`, `handle_startup_failure`.

Call sites to remove:
- `main.py`: 7 imports (lines 15–21) + 7 `await migrate_*` calls in lifespan (lines 70–82, verified). Delete the explanatory comment blocks tied to each migration call.
- `app_factory.py`: 1 import (`migrate_strategy_id_fields`, line 29) + 1 call (line 96) + its mirror comment.

`test_lifespan_boot.py` (integration, 3 tests) currently asserts migration outcome:
- `test_lifespan_boots_on_fresh_mongo` — KEEP (empty Mongo boots clean; no migration needed).
- `test_lifespan_boots_on_legacy_state` — REMOVE (seeds legacy strategy_id docs + asserts migrated shape; the migration that did this is gone). Also remove its `_seed_legacy_state` helper + the legacy-only branch of `_assert_migrated_shape`.
- `test_lifespan_idempotent_on_already_migrated_state` — KEEP, rename intent: seeds already-correct shape, asserts boot is a clean no-op. Drop the word "migrated" from name/docstring (now just "seeded current shape").

## Related Code Files

- Modify: `src/pocketquant/app/main_extensions.py` — delete 7 `migrate_*` + 3 `_rename*/_drop*` helpers (~470 LOC; 944 → ~480).
- Modify: `src/pocketquant/app/main.py` — drop 7 imports + 7 calls + comments.
- Modify: `tests/app_test/integration/app_factory.py` — drop `migrate_strategy_id_fields` import + call.
- Modify: `tests/app_test/integration/test_lifespan_boot.py` — remove legacy-state test + seed helper; rename idempotent test.
- Delete: `tests/app_test/unit/test_strategy_id_migration.py`, `test_subscription_desired_state_migration.py`, `test_tracked_symbols_uuid_migration.py`, `test_job_history_uuid_migration.py`, `test_backtest_request_uuid_migration.py`, `test_backtest_run_cache_uuid_migration.py`, `test_subscription_uuid_migration.py` (7 files, 1,223 LOC, 30 tests).

## Implementation Steps

1. **Baseline:** `just test` → record pass/skip count + wall time. Confirm 612p/5s/35s.
2. Grep every `migrate_` reference: `grep -rn "migrate_" src tests --include="*.py"`. Confirm the only callers are `main.py`, `app_factory.py`, and the 7 unit test files. (If any *other* live caller appears, STOP — surface it.)
3. Delete the 7 unit test files.
4. Edit `test_lifespan_boot.py`: remove `test_lifespan_boots_on_legacy_state` + `_seed_legacy_state` + legacy branch of `_assert_migrated_shape`; rename idempotent test.
5. Edit `main.py`: remove 7 imports (15–21) + 7 `await migrate_*` calls + comment blocks (70–82). Verify the surviving lifespan order: `ensure_all_indexes` → `recover_stale_backtests` → `recover_orphan_jobs` → `seed_tracked_symbols` → `rehydrate_strategies_from_subscriptions` → … .
6. Edit `app_factory.py`: remove migration import + call.
7. Edit `main_extensions.py`: delete the 7 `migrate_*` funcs + 3 helpers. Re-grep to confirm helpers have zero remaining callers before deleting.
8. **Compile + static gates:** `uv run python -c "import pocketquant.app.main"`, then `just types`, `just lint`, and `uv run lint-imports` (import-linter).
9. **Re-run:** `just test` → expect ~582 passed (30 fewer), same skips, green. Boot smoke covered by `test_lifespan_boot.py` + `test_app_boot_smoke.py`.

## Success Criteria

- [ ] 7 migration unit test files deleted; `test_lifespan_boot.py` legacy test removed, idempotent test renamed.
- [ ] 7 `migrate_*` + 3 private helpers gone from `main_extensions.py`; no other live caller existed.
- [ ] `main.py` + `app_factory.py` lifespans build and boot with no migration calls.
- [ ] `just types`, `just lint`, import-linter green; `import pocketquant.app.main` succeeds.
- [ ] `just test` green, ~30 fewer tests, no new skips/failures.

## Risk Assessment

- **Dropped boot self-heal:** if some unmigrated DB ever boots, app no longer auto-fixes it → read crash. Mitigation: user confirmed prod-only + fully migrated; the removal commit is git-recoverable if a stray env surfaces. Tag commit message clearly (no plan refs per comment policy — describe the change: "remove deployed uuid7 boot migrations").
- **Helper shared unexpectedly:** `_rename_field_if_needed` etc. might be reused elsewhere. Mitigation: Step 2/7 re-grep gate before deletion.
- **`_assert_migrated_shape` shared by idempotent test:** editing the legacy branch could break the kept test. Mitigation: read full helper, keep the already-migrated-shape assertions intact.
