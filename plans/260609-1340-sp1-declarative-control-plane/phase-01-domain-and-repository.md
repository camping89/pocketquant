---
phase: 1
title: "Domain and Repository"
status: completed
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: Domain and Repository

## Overview

Add `desired_state` + `actual_state` to `Subscription` (frozen dataclass, default `stopped`), update `to_mongo`/`from_mongo` with back-compat read, add repo write methods. This field is the control-plane contract every later phase depends on.

## Requirements

- Functional:
  - `Subscription.desired_state: Literal["running","stopped"]`, default `"stopped"`.
  - `Subscription.actual_state: Literal["running","stopped"]`, default `"stopped"`.
  - `from_mongo` tolerates docs without the new keys (old docs read before migration runs) → default `stopped`.
  - `to_mongo` always writes both keys.
  - `SubscriptionRepository.update_desired_state(sub_id, state) -> int` (modified_count).
  - `SubscriptionRepository.update_actual_state(sub_id, state) -> int` (modified_count).
- Non-functional:
  - Keep `frozen=True`; mutate via `dataclasses.replace`.
  - `deterministic_id` recipe unchanged — new fields are NOT part of the PK (hash stays `strategy_code|symbol|interval`).

## Architecture

- State is a 2-value `Literal`; encode as a module-level alias `RunState = Literal["running","stopped"]` in `subscription/entities.py` (no new enum file — YAGNI, matches D2).
- `desired_state` = control plane (what human/handler wants). `actual_state` = data plane truth mirrored from RAM by the reconcile loop (Phase 2).
- Repo `update_*` use `update_one({"_id": sub_id}, {"$set": {...}})`; return `modified_count` so callers/tests can assert.

## Related Code Files

- Modify: `packages/pocketquant-core/src/pocketquant/core/domain/subscription/entities.py`
- Modify: `packages/pocketquant-infrastructure/src/pocketquant/infrastructure/persistence/repositories/subscription_repository.py`
- Create: `tests/core_test/test_subscription_desired_actual_state.py` (entity round-trip + back-compat)
- Modify: `tests/trading_test/test_subscription_repository.py` (add `update_desired_state` / `update_actual_state` cases)

## Implementation Steps

1. **TEST FIRST** — `tests/core_test/test_subscription_desired_actual_state.py`:
   - `to_mongo` includes `desired_state` + `actual_state`.
   - `from_mongo` on a doc WITHOUT either key → both default `"stopped"` (back-compat lock).
   - `from_mongo` on a doc WITH `desired_state="running"` → preserved; round-trip `to_mongo`→`from_mongo` stable.
   - `deterministic_id` unchanged: same 3-tuple → same id regardless of state values.
   - `replace(sub, desired_state="running")` keeps `id` stable (state not in PK).
2. Edit `entities.py`:
   - Add `RunState = Literal["running", "stopped"]` alias (import `Literal`).
   - Add `desired_state: RunState = "stopped"` and `actual_state: RunState = "stopped"` fields. Frozen dataclass allows field defaults; ensure they come after `created_at` (no non-default-after-default error).
   - `to_mongo`: add `"desired_state": self.desired_state, "actual_state": self.actual_state`.
   - `from_mongo`: `desired_state=doc.get("desired_state", "stopped")`, `actual_state=doc.get("actual_state", "stopped")`.
3. **TEST FIRST** — extend `tests/trading_test/test_subscription_repository.py`:
   - `update_desired_state(sub.id, "running")` returns 1; `get` reflects `desired_state="running"`, `actual_state` untouched.
   - `update_actual_state(sub.id, "running")` returns 1; `get` reflects `actual_state="running"`.
   - `update_desired_state("missing", "running")` returns 0.
4. Edit `subscription_repository.py`: add `update_desired_state` + `update_actual_state` using `$set`, return `result.modified_count`. Log at debug.
5. Run `just test-pkg core` + targeted repo test → green.
6. Run `just lint` + `just types` on touched files.

## Success Criteria

- [ ] `Subscription` has `desired_state` + `actual_state`, default `stopped`, frozen preserved.
- [ ] `from_mongo` back-compat: legacy doc (no new keys) → both `stopped`, no crash.
- [ ] `update_desired_state` / `update_actual_state` persist + return modified_count.
- [ ] `deterministic_id` value identical to pre-change for same 3-tuple (regression locked by test).
- [ ] core + repo tests green; lint + types clean.

## Risk Assessment

- **Frozen field ordering**: new defaulted fields after non-default `created_at` is fine; mis-order → dataclass TypeError caught at import (test collection fails fast).
- **Back-compat read**: if `from_mongo` used `doc["desired_state"]` (not `.get`), every pre-migration read crashes. Test step 1 locks `.get` default. Mitigation: explicit back-compat test.
- **PK drift**: accidentally folding state into `deterministic_id` would orphan all existing subs. Test step 1 pins the hash. Do not touch the recipe.
