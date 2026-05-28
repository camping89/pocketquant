---
title: "Mongo migration test coverage + Database wrapper API debate"
description: "Close 2 deferred items from cook of 260528-2000: (1) boot-time mongo migration AttributeError slipped past existing test_strategy_id_migration.py because the test uses the same broken db.database access pattern AND was not being run in CI; (2) Database wrapper API (name-mangled __database + get_database() accessor) is fighting consumers — debate exposing AsyncDatabase as a public `database` property vs locking down all .database access."
status: pending
priority: P2
branch: "develop"
tags: [tests, mongo, api-design, ci]
blockedBy: []
blocks: []
created: "2026-05-28T16:47:00Z"
createdBy: "ck:cook (deferred-item followup)"
source: skill
---

# Mongo migration test coverage + Database wrapper API debate

## Overview

Two items deferred during `/ck:cook` of plan `260528-2000-config-fetch-via-deploy-key`:

1. **Test coverage gap.** `migrate_strategy_id_fields` shipped with an `AttributeError` (`db.database` does not exist — name-mangled to `_Database__database`). A unit test (`packages/pocketquant-api/tests/unit/test_strategy_id_migration.py`) DID exist and used the same broken access pattern, yet nothing caught the bug before prod. Two things to fix:
   - the test file itself uses `db.database` (line 40, 94, 122) → either suite was never running, or fixture override masked the bug.
   - migration changes need a CI gate that boots the lifespan in a testcontainer Mongo, not just unit assertions.

2. **Database wrapper API debate.** Today `Database` wraps an `AsyncDatabase` in `self.__database` (name-mangled) and exposes `get_database()` + `get_collection(name)`. Consumers keep wanting raw collection access for one-off ops (rename collection, list collection names, drop index by name). The accessor is awkward (`db.get_database()[coll].rename(new)`). Debate: (a) add public `database` property that returns the underlying `AsyncDatabase`; (b) keep encapsulation strict and add domain-level helpers to `Database` for each pattern (`rename_collection`, `list_collections`, `drop_named_index`, etc.); (c) hybrid — public `database` property but mark it `# advanced`.

Source: `plans/260528-2000-config-fetch-via-deploy-key/cook-deferred-items-and-questions.md` "Tech debt to address in a future plan" section.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Diagnose why test_strategy_id_migration.py did not catch the AttributeError](./phase-01-diagnose-existing-migration-test.md) | Pending |
| 2 | [Add a lifespan-level smoke test that boots api/main.py against testcontainer Mongo](./phase-02-add-lifespan-boot-smoke-test.md) | Pending |
| 3 | [Brainstorm + decide on Database wrapper API (property vs domain helpers vs hybrid)](./phase-03-brainstorm-database-wrapper-api.md) | Pending |
| 4 | [Apply the chosen Database API + sweep call sites](./phase-04-apply-database-api-decision.md) | Pending |

## Key decisions (to be locked during brainstorm phase)

- Whether to use testcontainers (slow, real Mongo) or in-memory mock (fast, less faithful) for lifespan smoke.
- Whether the chosen Database API is backward-compatible (i.e. keep `get_database()` as a deprecated alias) or a hard break.
- Whether tests live under `pocketquant-api/tests/integration/` (likely yes — lifespan + real DB).

## Dependencies

- Requires CI to be running on develop (✓ already).
- Requires testcontainers + mongo runtime in CI (pyproject already lists `testcontainers[mongodb,redis]>=4.8.0` — may not yet be wired into the CI workflow).

## Out of scope

- Migration design itself (the strategy_id rename is correct and already shipped).
- Replacing `Database` with a different DI pattern (Dishka providers stay).
- Coverage targets for the rest of `pocketquant-api`. This plan only owns boot-lifespan + migration paths.
- Adding a separate "validate `pocketquant-config/.env` against schema" CI job — already delivered in the deferred-fix pass (`deploy/vps/required-env-vars.txt` + new Validate step in cicd.yml).
