---
phase: 3
title: "Delete/merge redundant tests"
status: completed
priority: P2
effort: "2-3h"
dependencies: [2]
---

# Phase 3: Delete/merge redundant tests

## Overview

Remove obviously dead/dup tests: one-shot `resync_2y_from_binance` script test (607 LOC), and merge the 3 overlapping engine "declarative" test files into one (521 LOC → ~300). Also fix 2 characterization-test docstrings that still cite removed plan/phase taxonomy (comment-policy violation). Net: ~830 LOC, ~13 tests removed; coverage of live behavior preserved.

## Requirements

- Functional: every behavior assertion that pins **live** code keeps an owner. Deletions only target one-shot script coverage and duplicate assertions.
- Non-functional: docstrings carry no plan/phase/finding refs (CLAUDE.md comment policy). `just test` green.

## Architecture

### 3a. Delete resync script test (user-confirmed one-shot)
`tests/scripts/test_resync_2y_from_binance.py` (607 LOC) tests `scripts/resync_2y_from_binance.py` — a one-shot backfill already run. KEEP the other two script tests (`test_audit_bar_quality.py` 282 LOC, `test_binance_kline_mapping.py`) — those tools still run. Confirm no shared fixture in `tests/scripts/conftest.py` is used *only* by the resync test before deleting; if so, prune it too.

### 3b. Merge engine declarative trio
Three files with overlapping fixtures + duplicate start/stop/add-symbol assertions (verified test lists):
- `test_handlers_pure_declarative.py` (170 LOC, 2 tests: `test_remove_symbol_pure_db_delete`, `test_delete_strategy_cascades_all_subs`).
- `test_add_symbol_handler_pure_declarative.py` (116 LOC, 4 tests: persist-by-uuid7, two-adds-distinct-ids, 404 unknown template, 404 symbol-not-tracked).
- `test_strategy_handlers_declarative.py` (235 LOC, 7 tests: start/stop writes desired_state, missing-sub raises, add-symbol stopped write, list-symbols sources-from-db, is_running false).

Overlap: `add_symbol` behavior asserted in both file 2 and file 3; start/stop/list grouped in file 3. Target: single `test_strategy_handlers_declarative.py` holding the union of **distinct** assertions, one shared `repo`/`repos` fixture. Drop only true duplicates (same handler + same assertion). Estimate ~10 tests / ~300 LOC.

**Method (regression-safe):** before merging, dump each test's assertions; after merging, diff the assertion set — must be a superset-minus-exact-dups. Any assertion that exists in only one file MUST survive.

### 3c. Fix characterization docstrings (no behavior change)
- `tests/core_test/infra/persistence/sync_status_counter_characterization_test.py` — docstring cites "Phase 5", "Phase 8", `tests/api_test/...` (stale path; suite is now `app_test`). Rewrite to state the invariant only (atomic `$inc`/`$set` counter semantics), no phase/path refs. KEEP the test.
- `tests/engine_test/strategy_injection_roundtrip_characterization_test.py` — docstring references "three former private-member injection hacks" (change-narrative). Rewrite to state current contract of `inject_prepared_strategy`. KEEP the test.

## Related Code Files

- Delete: `tests/scripts/test_resync_2y_from_binance.py`.
- Modify: `tests/scripts/conftest.py` — prune resync-only fixtures if any.
- Delete: `tests/engine_test/test_handlers_pure_declarative.py`, `tests/engine_test/test_add_symbol_handler_pure_declarative.py`.
- Modify: `tests/engine_test/test_strategy_handlers_declarative.py` — absorb distinct tests from the two deleted files; single shared fixture.
- Modify: `tests/core_test/infra/persistence/sync_status_counter_characterization_test.py` — docstring only.
- Modify: `tests/engine_test/strategy_injection_roundtrip_characterization_test.py` — docstring only.

## Implementation Steps

1. **Baseline:** `just test` → record count + time (post-P2).
2. **3a:** grep `tests/scripts/conftest.py` for fixtures referenced only by the resync test; delete the test file + any orphaned fixture. `just test-pkg scripts` (or `pytest tests/scripts`) green.
3. **3b:** read all 3 declarative files in full. Build assertion inventory (handler × expected outcome). Write merged `test_strategy_handlers_declarative.py` covering the union of distinct cases with one `repo` fixture. Delete the other two files. `pytest tests/engine_test -q` green; diff test-id list vs baseline to confirm only true dups dropped.
4. **3c:** rewrite the 2 docstrings to invariant-only prose (no phase/path/narrative). Tests unchanged → still green.
5. `just lint`, `just types`, `uv run lint-imports`.
6. **Full run + measure:** `just test` → green; record LOC (`find tests -name "*.py" -exec wc -l {} + | tail -1`) and wall time.
7. **Decision gate for P4:** if test LOC < 12,000 → mark P4 skipped/cancelled. Else proceed to P4.

## Success Criteria

- [ ] `test_resync_2y_from_binance.py` deleted; `audit_bar_quality` + `kline_mapping` tests intact; `pytest tests/scripts` green.
- [ ] 3 declarative files → 1; every distinct assertion preserved (verified by assertion diff); `pytest tests/engine_test` green.
- [ ] 2 characterization docstrings carry zero plan/phase/path/narrative refs; tests still pass.
- [ ] `just test`/`just lint`/`just types` green.
- [ ] Measured test LOC recorded; P4 go/no-go decided.

## Risk Assessment

- **Dropping a unique assertion during merge:** highest risk. Mitigation: explicit assertion-inventory diff in Step 3 — superset rule; no assertion may vanish silently.
- **resync conftest fixture shared:** could break audit/kline tests. Mitigation: Step 2 grep before delete.
- **Docstring edit accidentally changes test body:** Mitigation: edit only the triple-quoted docstring block; re-run engine/core suites.
