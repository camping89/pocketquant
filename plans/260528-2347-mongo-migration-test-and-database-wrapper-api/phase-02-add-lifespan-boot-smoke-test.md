---
phase: 2
title: "Add a lifespan-level smoke test that boots api/main.py against testcontainer Mongo"
status: pending
priority: P2
effort: "2h"
dependencies: [1]
---

# Phase 2: Lifespan boot smoke test

## Overview

Add an integration test that wires up the real Dishka container, runs the FastAPI app's `lifespan(app)`, and asserts no exception is raised — for both a fresh Mongo and a legacy-state Mongo (with `strategy_subscriptions` + `strategy_id` docs present). This is the test that WOULD have caught the `db.database` AttributeError. Also fix any existing tests that reference the broken access pattern.

Depends on Phase 1's diagnosis — which paths are unrun, why, what fixture changes are needed.

## Requirements

- Functional:
  - New file: `packages/pocketquant-api/tests/integration/test_lifespan_boot.py`.
  - 3 tests:
    - `test_lifespan_boots_on_fresh_mongo` — no collections yet → lifespan completes without error.
    - `test_lifespan_boots_on_legacy_state` — seed `strategy_subscriptions` + legacy `strategy_id` docs → lifespan migrates them → no error → assert renamed collection + renamed fields exist.
    - `test_lifespan_idempotent_on_already_migrated_state` — seed the post-migration shape → lifespan completes without error → no double-rename, no schema corruption.
  - Re-write `packages/pocketquant-api/tests/unit/test_strategy_id_migration.py` to use the chosen Database API (either `db.database` once Phase 3 lands the property, or `db.get_database()` if Phase 3 keeps current). Either way: passing on `develop` HEAD.
  - CI: add a `tests` job to `.github/workflows/cicd.yml` that runs `uv run pytest packages/pocketquant-api/tests/` BEFORE `build-api` and `build-web` are allowed to push to Docker Hub. Smoke test failure must block the deploy.
- Non-functional:
  - Testcontainer cold-start <30s on GH-hosted ubuntu-latest runner.
  - Total tests added run in <90s wall clock.
  - No flakes on 3 consecutive runs.

## Architecture

```
.github/workflows/cicd.yml
  jobs:
    tests:                                                  (NEW)
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v5
        - uses: astral-sh/setup-uv@v6
        - run: uv sync
        - run: uv run pytest packages/pocketquant-api/tests/ -v
    build-api:
      needs: [tests]                                        (CHANGED)
      ...
    build-web:
      needs: [tests]                                        (CHANGED)
      ...
    deploy:
      needs: [build-api, build-web]
      ...

packages/pocketquant-api/tests/integration/
  test_lifespan_boot.py                                     (NEW)
    fixture: mongo_container        — testcontainers.MongoDbContainer
    fixture: settings               — points MONGODB_URL at the container
    fixture: container              — Dishka container with TestProvider
    fixture: app                    — FastAPI app with the same lifespan as prod
    test_lifespan_boots_on_fresh_mongo
    test_lifespan_boots_on_legacy_state
    test_lifespan_idempotent_on_already_migrated_state
```

## Related Code Files

- Create: `packages/pocketquant-api/tests/integration/test_lifespan_boot.py`
- Modify: `packages/pocketquant-api/tests/unit/test_strategy_id_migration.py` (fix `db.database` references per Phase 3 decision)
- Modify: `.github/workflows/cicd.yml` (add `tests` job, wire `needs:`)
- Optional modify: `packages/pocketquant-api/tests/conftest.py` (shared mongo_container fixture if reused)
- Read: `packages/pocketquant-api/src/pocketquant/api/main.py` (lifespan implementation)
- Read: `packages/pocketquant-api/src/pocketquant/api/main_extensions.py`
- Read: `packages/pocketquant-api/src/pocketquant/api/di/container.py` (DI wiring)

## Implementation Steps

1. Read Phase 1's diagnosis report. Adjust this phase's design if needed.
2. Add `packages/pocketquant-api/tests/integration/__init__.py` if missing.
3. Write `test_lifespan_boot.py` skeleton:
   ```python
   import pytest
   from httpx import ASGITransport, AsyncClient
   from testcontainers.mongodb import MongoDbContainer

   @pytest.fixture(scope="module")
   def mongo_container():
       with MongoDbContainer("mongo:7.0.31") as c:
           yield c

   @pytest.fixture
   async def settings(mongo_container):
       # build Settings instance pointing at the container URL
       ...

   @pytest.fixture
   async def app(settings):
       from pocketquant.api.main import create_app  # or factory
       return create_app(settings_override=settings)

   async def test_lifespan_boots_on_fresh_mongo(app):
       async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
           r = await ac.get("/health")
           assert r.status_code == 200
   ```
4. Add legacy-state seed + idempotent-state seed variants.
5. Fix `tests/unit/test_strategy_id_migration.py` per Phase 3's decision (4 `db.database` references).
6. Run `uv run pytest packages/pocketquant-api/tests/integration/test_lifespan_boot.py -v` locally. Iterate until green.
7. Run the full pocketquant-api test suite to make sure no regressions: `uv run pytest packages/pocketquant-api/tests/`.
8. Add `tests` job to `cicd.yml`. Wire `build-api.needs: [tests]` and `build-web.needs: [tests]`. Run lint locally: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/cicd.yml'))"`.
9. Push to a throwaway branch + `gh workflow run cicd.yml --ref <branch>`. Watch:
   - `tests` job runs and passes.
   - `build-api` / `build-web` wait on `tests`.
   - Full pipeline still green.
10. Negative smoke: temporarily revert the prod fix (`db.get_database()` → `db.database`), push, expect `tests` job RED + `build-*` skipped. Then revert the revert.

## Success Criteria

- [ ] 3 new tests pass on develop HEAD.
- [ ] Existing `test_strategy_id_migration.py` passes (`db.database` references resolved per Phase 3).
- [ ] CI `tests` job runs on every push + blocks `build-api` / `build-web` on failure.
- [ ] Negative smoke (revert prod fix) shows `tests` RED and image not pushed.
- [ ] Full pocketquant-api suite green: `uv run pytest packages/pocketquant-api/tests/`.
- [ ] No new lint/type errors: `uv run ruff check packages/pocketquant-api/` + `uv run pyright packages/pocketquant-api/`.

## Risk Assessment

| Risk | Mitigation |
|---|---|
| testcontainers cold-start slow on GH runners → tests time out | Cache pip wheels via `actions/cache`; pin mongo image to `mongo:7.0.31` to match prod. |
| `create_app` factory does not exist — current main.py builds at module level | Refactor first: extract `create_app(settings_override)` in main.py. Pure mechanical, no behavior change. |
| `lifespan` calls external services (Trading View, OKX) that fail without creds | Use TestProvider that mocks/stubs those clients. Keep only Mongo + Redis testcontainer-backed. |
| Integration test in CI doubles run time | Acceptable — first push is slow, subsequent push reuses cache. Hard cap at 5 min for `tests` job; fail noisily if exceeded. |
| Existing test file's `db.database` is actually fine because conftest swaps in a different Database class | Phase 1 diagnosis catches this; adjust accordingly in step 5. |

## Next Steps

- Phase 3 + 4 ship the wrapper API decision in parallel with this phase. Coordinate the `db.database` rewrite in step 5.
