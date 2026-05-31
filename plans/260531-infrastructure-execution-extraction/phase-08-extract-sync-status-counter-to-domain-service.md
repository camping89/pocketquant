---
phase: 8
title: "Extract sync-status counter to domain service"
status: pending
priority: P2
effort: "0.5d"
dependencies: [7]
---

# Phase 8: Extract sync-status counter to domain service

## Overview

Targeted logic-correctness fix (independent of the package moves): centralize the bump-vs-reset DECISION in a core domain service so the domain owns the invariant. **Correction to original premise:** the decision does NOT currently live in `SyncStatusRepository` — the repo methods `bump_empty_fetch`/`reset_empty_fetch` are already pure atomic `$inc`/`$set` ops (`sync_status_repository.py:58-84`). The actual rule lives in the api caller `market_data/handlers/sync/sync_one/handler.py:95-104` as a simple BINARY: `if inserted_count > 0: reset_empty_fetch else: bump_empty_fetch`. The repo is already slim. This phase extracts the handler's binary decision into a domain service; the repo stays as-is (atomic ops). Gated by the Phase 1 characterization test (decision pinned at the handler) — semantics must not change, and NO tri-state (`had_existing`/`no_existing`) is introduced (none exists today).

## Requirements
- Functional: a core domain service owns the bump/reset decision (extracted from the api handler); the repo continues to expose only its atomic persistence primitives (already the case). Counter characterization test green (identical `$inc` outcomes). The single caller (`sync_one/handler.py`) goes through the domain service.
- Non-functional: keep the atomic increment at the persistence boundary (the `$inc` is a Mongo atomic op — the domain service decides WHICH op, the repo executes the atomic write). Don't pull the atomicity up into a read-modify-write race. Keep the rule BINARY — do not invent `had_existing`/`no_existing` branches.

## Architecture

Current state (verified):
- `infrastructure/persistence/repositories/sync_status_repository.py:58-84` — `bump_empty_fetch()` is solely `find_one_and_update {$inc}`; `reset_empty_fetch()` is solely `update_one {$set:0}`. NO rule, NO read-modify-write. Already slim.
- The decision lives in `api/market_data/handlers/sync/sync_one/handler.py:95-104`: `if inserted_count > 0: reset_empty_fetch else: bump_empty_fetch` (binary on the in-hand sync outcome).

Target:
- `core/domain/sync_status/services/sync_progress_tracker.py` — `SyncProgressTracker` domain service: pure function deciding, given the sync outcome already in hand (`inserted_count`), whether the caller should call reset or bump. No Mongo, no extra read.
- Repo: unchanged (keeps the atomic `$inc`/`$set` ops + `find_one`/`upsert`). The "slim the repo" step from the original draft is a no-op — the repo is already slim; do NOT manufacture changes there.
- Caller (`sync_one/handler.py`): invoke the tracker to decide, then call the repo's atomic op. This handler is the PRIMARY edit site.

The atomic `$inc` stays in the repo (correctness: concurrent syncs must not lose increments). The domain service only encodes the *binary rule* — it does not read-then-write.

## Related Code Files
- Create: `core/domain/sync_status/services/{__init__.py,sync_progress_tracker.py}`
- Modify (PRIMARY): `api/market_data/handlers/sync/sync_one/handler.py:95-104` — the SOLE caller of `bump/reset_empty_fetch`; route its binary decision through `SyncProgressTracker`
- Repo: `infrastructure/persistence/repositories/sync_status_repository.py` — NO change required (already pure atomic ops); do not manufacture a "slim" edit
- Create test: `tests/core_test/unit/domain/sync_status/sync_progress_tracker_test.py` (pure-logic, no DB)
- Keep: Phase 1 characterization test (handler decision + repo atomic) green
- NOTE: `app_services/sync_jobs.py` and `handlers/status/*` do NOT call bump/reset (verified) — they are NOT edit sites; do not touch them.

## Implementation Steps
1. Test-first: write `SyncProgressTracker` unit tests encoding the EXACT current BINARY rule from `sync_one/handler.py:95-104` — outcome(`inserted_count > 0`) → reset; outcome(`inserted_count == 0`) → bump. Do NOT add `had_existing`/`no_existing` branches; confirm the current handler does not distinguish them before writing code.
2. Implement `SyncProgressTracker` (pure binary decision).
3. (No repo change — repo is already pure atomic ops. Skip any "slim the repo" work.)
4. Re-point the single caller `sync_one/handler.py`: compute decision via tracker → execute via repo atomic op.
5. Run Phase 1 characterization test (handler decision + repo atomic, end-to-end) + new tracker unit tests + full suite.
6. Commit: `refactor: extract sync-status progress rule into SyncProgressTracker domain service`.

## Success Criteria
- [ ] `SyncProgressTracker` owns the binary bump/reset decision (extracted from `sync_one/handler.py`); repo unchanged (already atomic-only).
- [ ] Characterization test green (unchanged BINARY semantics, no tri-state introduced); new pure-logic tracker tests green.
- [ ] `sync_one/handler.py` calls the tracker; no decision logic inlined in the handler.

## Risk Assessment
- Risk: splitting decision from atomic write introduces a read-modify-write race. Mitigation: keep `$inc` atomic in the repo; the tracker decides bump-vs-reset from the sync *outcome* already in hand (no extra read). 
- Risk: scope drift toward inventing a tri-state rule that doesn't exist today (the original draft fabricated `had_existing`/`no_existing`). Mitigation: the current rule is strictly binary on `inserted_count` (`sync_one/handler.py:95-104`); pin that exact behavior in Phase 1 and forbid new branches — a tri-state would be a behavior change, not a no-op extraction.
- Risk: this phase is optional-feeling and could be cut under time pressure. Mitigation: it's the only "incorrect logic" fix the user explicitly requested beyond the cycle break — keep it; it's cheap (0.5d) and isolated.
