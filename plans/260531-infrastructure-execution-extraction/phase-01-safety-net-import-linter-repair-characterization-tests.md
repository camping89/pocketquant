---
phase: 1
title: "Safety net: import-linter repair + characterization tests"
status: done
priority: P1
effort: "0.5d"
dependencies: []
---

# Phase 1: Safety net: import-linter repair + characterization tests

## Overview

Build the regression net BEFORE any code moves. Repair the broken import-linter config so the structural assertion actually runs, and write characterization tests pinning the load-bearing behaviors that later phases risk disturbing. No production code moves in this phase.

## Requirements
- Functional: `uv run lint-imports` runs without crashing and reports current contract state. Characterization tests pass against the CURRENT (unmoved) tree.
- Non-functional: tests must be import-path-agnostic where feasible (assert behavior, not module location) so they survive the moves — but pin exact current import paths in at least one "guard" test per moved symbol so the move is observable.

## Architecture

Today `pyproject.toml` `[tool.importlinter]` declares a `forbidden` contract on external module `bson` but lacks `include_external_packages = True` at top level → `lint-imports` hard-crashes ("must have include_external_packages=True when there are external forbidden modules"). Fix = add the top-level flag. This unblocks ALL contracts (the core/backtest/trading sibling contracts currently never evaluate because the run aborts).

Characterization targets (behaviors that MUST be identical after the refactor):
1. **Sync-status bump/reset decision** — the bump-vs-reset RULE lives in the api sync caller `market_data/handlers/sync/sync_one/handler.py:95-104` (binary: `if inserted_count > 0: reset_empty_fetch else: bump_empty_fetch`), NOT in the repository. `SyncStatusRepository.bump_empty_fetch`/`reset_empty_fetch` are already pure atomic `$inc`/`$set` ops (`persistence/repositories/sync_status_repository.py:58-84`). Pin BOTH: (a) the atomic counter semantics at the repo, and (b) the decision at the handler. Phase 8 extracts the handler-level decision to a domain service and must keep the existing BINARY semantics — do NOT introduce a tri-state (`had_existing`/`no_existing`); none exists today.
2. **Deterministic Subscription ID** — `Subscription.deterministic_id` exact hash recipe (`trading/domain/subscription.py:36`, normalization at :55, warning at :52-54). Phase 3 promotes the entity to core; ID output must not change. The recipe normalizes interval via `interval.value if isinstance(interval, Interval) else str(interval)` and uppercases symbol — the persisted `_id` depends on it.
3. **PaperBroker fills** — market + limit + SL/TP fill behavior (`infrastructure/brokers/paper/paper_broker.py`). Phase 6 moves it to infra.
4. **Strategy injection round-trip** — load → get_strategy → unload through current `StrategyAppService` public surface. Phase 7 extracts it + replaces private-member injection with a public method; behavior must match. **The injection sites do MORE than dict-assignment** — under the same `_lock` they also `await broker.connect()` (if not connected) and `await strategy.on_start()` (`backtest/handlers/run/handler.py:100-109`, `trading/jobs/backtest_strategy_loader.py:118-126`, with a comment requiring "both in one critical section"). This test MUST assert `on_start()` fired AND broker is connected after injection, or it cannot catch the Phase-7 regression where the public method drops connect/on_start.

## Related Code Files
- Modify: `pyproject.toml` (add `include_external_packages = True` under `[tool.importlinter]`)
- Create: `tests/core_test/unit/persistence/sync_status_counter_characterization_test.py` (repo atomic semantics — if not already covered; check existing `tests/core_test/unit/persistence/`)
- Create/extend: a test pinning the bump-vs-reset DECISION at the api caller `tests/api_test/.../sync_one/` (the rule lives in `sync_one/handler.py:95-104`, not the repo)
- Create: `tests/trading_test/subscription_deterministic_id_characterization_test.py`
- Create/extend: `tests/core_test/unit/infrastructure/brokers/paper_broker_fills_characterization_test.py` (extend existing brokers test if present)
- Create: `tests/trading_test/strategy_injection_roundtrip_characterization_test.py`

## Implementation Steps
1. Read existing tests under `tests/core_test/unit/persistence/`, `tests/core_test/unit/infrastructure/brokers/`, `tests/trading_test/` to avoid duplicating coverage. Extend rather than create where overlap exists.
2. Add `include_external_packages = True` to `[tool.importlinter]` in `pyproject.toml`. Run `uv run lint-imports`. Record the ACTUAL contract output verbatim (not "likely report"). Confirm whether the backtest↔trading contract is RED — top-level edges exist (`backtest/handlers/run/handler.py:14` → trading; `trading/handlers/strategy/{delete,get_subscription_backtest,list_symbols,remove_symbol}/handler.py:3` → backtest), but some trading→backtest edges are function-local/`TYPE_CHECKING` (`trading/jobs/backtest_jobs.py:63-64`) which import-linter may NOT flag. If the contract reports PASS despite the runtime cycle, that is a false-green baseline — note it explicitly and rely on the Phase 7 two-directional grep gate as the real cycle-break assertion. Do NOT fix violations here (later phases do).
3. Write sync-status characterization test at TWO levels: (a) repo atomic semantics — insert a sync_status doc, call `bump_empty_fetch` twice → assert `consecutive_empty_fetches == 2`; call `reset_empty_fetch` → assert `== 0`; (b) decision semantics — drive the actual caller path `sync_one/handler.py` with `inserted_count > 0` (expect reset) and `inserted_count == 0` (expect bump), asserting final counter. Include a concurrent-sync interleaving (two workers on the same symbol/interval, one inserting, one empty) asserting the `$inc` does not lose increments. Use the existing test DB/testcontainers fixture pattern from `tests/core_test/conftest.py`.
4. Write deterministic-ID test: assert `Subscription.deterministic_id("hitnrun2", "btcusdt:okx", "1h")` equals the exact current 16-hex output (compute once, hard-code the literal as the golden value). Pin MULTIPLE input shapes that must collapse to the SAME hash: lowercase symbol, uppercase symbol, `Interval` enum instance, and `Interval` as raw string — this protects the persisted `_id` against a normalization regression. VERIFIED SAFE for the move: `symbol` is `.upper()`-normalized idempotently at both the recipe (`subscription.py:55`) and the sole caller (`add_symbol/handler.py:45`); `strategy_code` is the `STRATEGY_REGISTRY` key (literal, e.g. `"hitnrun2"`), validated at `handler.py:52-53`; the recipe is unchanged by promotion. There is only ONE `Interval` enum — `core.domain.shared.value_objects.Interval` is a `# noqa: F401` re-export of `core.domain.shared.enums.Interval` (same object, identical `.value`), so no `_id` re-key risk. See Phase 3 step (c) for the consolidation to a single import path.
5. Write PaperBroker fills characterization test (extend existing if present): market order fills at bar close; limit order pends then fills on `BarCompletedEvent`; SL/TP synthetic exit. Assert resulting `PositionAggregate` state + emitted order events.
6. Write strategy injection round-trip test against current `StrategyAppService`: load a fake `IStrategy`, assert `get_strategy(id)` returns it, `unload_strategy(id)` clears it, AND assert the injection path connected the broker (`broker.is_connected`) and invoked `strategy.on_start()` exactly once. This becomes the contract the new public injection method must satisfy in Phase 7 — the connect/on_start assertions are what catch the dict-only-method regression.
7. Run full suite (`uv run pytest`) — all green. Commit: `test: characterization net + repair import-linter config`.

## Success Criteria
- [x] `uv run lint-imports` executes (no config crash) and its VERBATIM report is recorded in the phase notes, with explicit note whether the backtest↔trading contract is RED or false-green.
- [x] 4 characterization areas covered by passing tests against the current tree, including: sync decision at the handler (binary, not tri-state) + repo atomic + concurrency; injection round-trip asserting `on_start()` + broker connected.
- [x] Golden deterministic-ID literals captured for all 4 input shapes (collapsing to one hash) + `Interval` import-path guard.
- [x] Full `uv run pytest` green.

## Implementation Notes (as-built)

**lint-imports baseline (verbatim, after `include_external_packages = true`):**
```
Analyzed 159 files, 549 dependencies.
Core has zero sibling dependencies KEPT
Backtest depends only on Core BROKEN
Trading depends only on Core BROKEN
No bson/ObjectId usage — UUID7 only KEPT
Contracts: 2 kept, 2 broken.

Backtest depends only on Core:
  pocketquant.backtest.handlers.run.handler -> pocketquant.trading.app_services.strategy_app_service (l.14)
Trading depends only on Core:
  pocketquant.trading.jobs.backtest_jobs -> pocketquant.backtest.engine.backtest_app_service (l.63)
  pocketquant.trading.jobs.backtest_jobs -> pocketquant.backtest.persistence.backtest_repository (l.64)
  pocketquant.trading.jobs.backtest_strategy_loader -> pocketquant.backtest.optimization.models.backtest_config (l.10)
```
The backtest↔trading contract is **RED, not false-green** — import-linter flags BOTH directions, including the function-local `backtest_jobs.py:63-64` edges. The real baseline cycle is observable. (Phase 7 two-directional grep gate remains the cycle-break assertion.)

**Characterization coverage (extend-not-duplicate):**
- Sync decision (handler, binary) — already pinned by existing `tests/api_test/unit/handlers/sync/test_no_progress_tracking.py` (bump vs reset, 7 cases). Repo atomic `$inc`/`$set` + 20-way concurrency added: `tests/core_test/unit/persistence/sync_status_counter_characterization_test.py` (integration).
- Deterministic Subscription ID — already pinned by existing `tests/trading_test/test_subscription_deterministic_id.py` (golden literal + 4 input shapes + `Interval` enum-vs-string guard). No duplication added.
- PaperBroker fills — SL/TP already covered; MARKET + LIMIT entry-fill state machine added: `tests/core_test/unit/infrastructure/brokers/paper_broker_fills_characterization_test.py`.
- Strategy injection round-trip — added `tests/trading_test/strategy_injection_roundtrip_characterization_test.py` asserting get/unload + `broker.connect()` called once + `on_start()` fired once + already-connected guard. This is the contract Phase-7 `inject_prepared_strategy` must satisfy.

Full suite: 404 passed, 12 skipped.

## Risk Assessment
- Risk: characterization tests accidentally assert module location, breaking trivially on move. Mitigation: assert behavior; keep exactly one explicit import-path guard per moved symbol, updated deliberately in the moving phase.
- Risk: testcontainers (mongo/redis) unavailable in some environments. Mitigation: mark DB-backed characterization tests `@pytest.mark.integration`; ensure pure-logic ones (deterministic ID, paper-broker with simulated time) need no container.
