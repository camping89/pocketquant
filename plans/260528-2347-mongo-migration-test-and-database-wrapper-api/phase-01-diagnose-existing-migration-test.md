---
phase: 1
title: "Diagnose why test_strategy_id_migration.py did not catch the AttributeError"
status: pending
priority: P2
effort: "30m"
dependencies: []
---

# Phase 1: Diagnose existing test_strategy_id_migration.py

## Overview

Find out HOW the bug at `main_extensions.py:138` (`db.database.list_collection_names()` → AttributeError) shipped despite `tests/unit/test_strategy_id_migration.py` existing and referencing the same broken access pattern. Without root cause, Phase 2's new test could fail the same way.

## Hypotheses to verify (in priority order)

1. **Test is not in any actively-run pytest path.** `pyproject.toml` lists `testpaths = ["packages/pocketquant-api/tests", ...]` but maybe Mongo-requiring tests are skipped without testcontainers.
2. **CI does not run pytest at all.** `cicd.yml` only does build + deploy — there is no `pytest` step. Local-only test workflow → developer must run before push, doesn't.
3. **`testcontainers` fixture unavailable in CI** → `pytest` skips all tests requiring Mongo (with `pytest.mark.skipif` or fixture init failure).
4. **The `settings` fixture in `conftest.py` points to a real Mongo where the rename had ALREADY happened** → migration is no-op → `db.database` was never reached.
5. **Test is actually broken on `develop` HEAD too** but not run since the strategy_id refactor merged.

## Requirements

- Functional:
  - Single concrete root cause statement (with file:line evidence) in a report at `plans/.../reports/phase-01-diagnose.md`.
  - List of every test file that depends on `db.database` (grep across the repo).
  - Verdict on which of the 5 hypotheses are true.
- Non-functional:
  - No code changes in this phase. Diagnosis only.

## Architecture

```
Repo state today:
  packages/pocketquant-api/tests/unit/test_strategy_id_migration.py  ── uses db.database
  packages/pocketquant-api/tests/conftest.py                         ── settings fixture
  packages/pocketquant-api/src/.../main_extensions.py                ── prod code (fixed in 260528-2000)
  pyproject.toml [tool.pytest.ini_options].testpaths                 ── what pytest discovers
  .github/workflows/cicd.yml                                         ── runs no pytest step
```

## Related Code Files

(Read-only)
- `packages/pocketquant-api/tests/unit/test_strategy_id_migration.py`
- `packages/pocketquant-api/tests/conftest.py`
- `packages/pocketquant-api/tests/integration/test_realtime_pipeline.py`
- `pyproject.toml` (pytest config)
- `.github/workflows/cicd.yml`
- `packages/pocketquant-core/src/pocketquant/core/persistence/mongodb.py`

## Implementation Steps

1. `uv run pytest packages/pocketquant-api/tests/unit/test_strategy_id_migration.py -v 2>&1 | head -50` — does it pass / fail / skip / error-collect?
2. If skipped: capture the skip reason. If failed: confirm `db.database` is the failure.
3. `grep -rn "db\.database\b" packages/ --include="*.py"` — every test or prod call site still using the broken pattern (should be only test files now, after 260528-2000 fix).
4. `grep -n "pytest" .github/workflows/cicd.yml` — confirm CI does NOT run pytest.
5. `cat packages/pocketquant-api/tests/conftest.py` — see what `settings` fixture provides. Does it connect to a real Mongo? An ephemeral one?
6. Run `uv run pytest --collect-only packages/pocketquant-api/tests/ 2>&1 | head -40` to see what gets discovered.
7. Write diagnosis report.

## Success Criteria

- [ ] Root cause sentence: "The bug shipped because <X>." (one sentence, file:line cited).
- [ ] Inventory of files using `db.database` (count + paths).
- [ ] List of hypotheses with verdicts (true / false / partial).
- [ ] Report saved at `plans/260528-2347-mongo-migration-test-and-database-wrapper-api/reports/phase-01-diagnose-existing-migration-test.md`.

## Risk Assessment

| Risk | Mitigation |
|---|---|
| `uv run pytest` itself fails to bootstrap (missing dep) | Capture the error verbatim; that IS the diagnosis. |
| Local mongo not running → all migration tests "error during collection" → no signal | Use testcontainer if `pyproject.toml` already wires it; otherwise note "no local mongo, can't reproduce" and pivot to static analysis. |
| Diagnosis reveals fix is bigger than expected | OK — Phase 2 + 3 plans adjust accordingly. No need to fix now. |

## Next Steps

- Phase 2 designs the new test that boots lifespan against a testcontainer mongo.
- Phase 3 separately debates the wrapper API; not blocked on Phase 1.
