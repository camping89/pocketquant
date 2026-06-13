---
phase: 2
title: "Consolidate testcontainers to root conftest"
status: completed
priority: P1
effort: "2h"
dependencies: [1]
---

# Phase 2: Consolidate testcontainers to root conftest

## Overview

4 suite conftests (`core_test`, `engine_test`, `backtest_test`, `app_test`) each define identical session-scoped `mongo_container` + `redis_container` fixtures. pytest session-scoped fixtures are scoped **per defining module path**, so a single run spins up Mongo+Redis up to 4× (verified: durations show repeated ~3.4–3.9s setups + ~5s teardowns across suites). Move ONE pair to root `tests/conftest.py`; delete the 4 duplicates. This is the primary speed win (~15–20s → run ~12–15s).

## Requirements

- Functional: every suite still resolves `mongo_container`/`redis_container` (now from root conftest via fixture inheritance). `settings`/`database`/`cache`/`event_bus` per-suite fixtures stay where they are.
- Functional: `just test-pkg core` (single suite) still works — root conftest fixtures are visible to any subtree.
- Non-functional: zero state bleed — per-test fresh DB-name + teardown drops already guarantee isolation; one shared container is safe.

## Architecture

Current (verified) duplication — identical bodies in all 4:
```python
@pytest.fixture(scope="session")
def mongo_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7.0") as mongo:
        yield mongo

@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7.2-alpine") as redis:
        yield redis
```

Target: this pair lives ONCE in `tests/conftest.py` (root). Root conftest already owns the sys.path bootstrap + prod-DB guard + env seeding — natural home for the shared container contract.

The per-suite `settings(mongo_container, redis_container)` fixtures stay in each suite conftest (they're near-identical but reference suite-local `database`/`cache`/`event_bus` chains; consolidating them too is out of scope — KISS, the container pair is 90% of the cost). They keep requesting `mongo_container`/`redis_container` by name; pytest resolves up the conftest tree to root.

Container image strings (`mongo:7.0`, `redis:7.2-alpine`) preserved verbatim — no version drift.

## Related Code Files

- Modify: `tests/conftest.py` — add the 2 session-scoped container fixtures + their `testcontainers` imports + `Iterator` import.
- Modify: `tests/core_test/conftest.py` — delete local `mongo_container`/`redis_container` (lines ~25–34) + now-unused `MongoDbContainer`/`RedisContainer` imports if no longer referenced (they ARE still referenced as type hints in `settings` — keep imports).
- Modify: `tests/engine_test/conftest.py` — same deletion.
- Modify: `tests/backtest_test/conftest.py` — same deletion.
- Modify: `tests/app_test/conftest.py` — same deletion.

## Implementation Steps

1. **Baseline:** `just test` → record wall time (post-P1, expect ~30s, ~582 tests).
2. Add `mongo_container` + `redis_container` session fixtures to `tests/conftest.py`, with `from testcontainers.mongodb import MongoDbContainer` / `from testcontainers.redis import RedisContainer` / `from collections.abc import Iterator`.
3. Delete the duplicate fixture defs from all 4 suite conftests. Keep the `MongoDbContainer`/`RedisContainer` imports there — still used as param type hints in each `settings` fixture.
4. **Verify resolution:** `uv run python -m pytest tests/core_test -q --co` (collect-only, single suite) — must not error on missing fixture.
5. **Full run:** `just test` → green, same test count, **one** Mongo + **one** Redis container started (watch durations: only one container setup/teardown pair should dominate now). Record wall time — target < 15s.
6. **Single-suite check:** `just test-pkg backtest` → green standalone.
7. `just lint` (catch unused imports), `just types`.

## Success Criteria

- [ ] `mongo_container`/`redis_container` defined exactly once (root `tests/conftest.py`); 4 duplicates deleted.
- [ ] `grep -rn "def mongo_container" tests` returns 1 hit.
- [ ] `just test` green, unchanged count, wall time < 15s.
- [ ] `just test-pkg core` and `just test-pkg backtest` pass standalone.
- [ ] `just lint`/`just types` green (no unused imports left behind).

## Risk Assessment

- **Cross-suite state bleed:** one Mongo shared by all suites. Mitigation: every suite uses `mongodb_database="pocketquant_test"` with per-test collection drops on teardown (verified in core/backtest conftests) — isolation already independent of container count. Confirm app_test teardown also drops or uses fresh names.
- **Fixture not found when running a sub-path:** importlib import-mode + root conftest should always be discovered. Mitigation: Step 4/6 explicit single-suite runs.
- **Teardown ordering:** session container now torn down once at end of whole run instead of per-suite — strictly fewer teardowns, no risk.
