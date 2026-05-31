---
title: "Extract infrastructure + execution packages (6-package layering)"
description: "Split persistence + adapters out of core into pocketquant-infrastructure; extract shared strategy engine into pocketquant-execution; break the backtest↔trading cycle; promote all persisted entities to core. TDD: characterization tests + import-linter gate each move."
status: done
priority: P1
branch: "develop"
tags: [refactor, monorepo, architecture, tdd, hexagonal]
blockedBy: []
blocks: []
created: "2026-05-31T03:18:58.709Z"
createdBy: "ck:plan"
source: skill
---

# Extract infrastructure + execution packages (6-package layering)

## Overview

Pure structural refactor (+4 targeted logic fixes). Today `pocketquant-core` carries `persistence/` and `infrastructure/` and depends on pymongo/redis/apscheduler/websockets/httpx. `backtest` and `trading` import each other (cycle, violating existing — but non-running — import-linter contracts). Goal: clean layered graph

```
core ──▶ infrastructure ──▶ execution ──▶ { backtest, trading } ──▶ api
```

6 Python packages. Core becomes pure domain/concepts/common/config + ports + DTOs + all persisted entities. New `pocketquant-infrastructure` holds all persistence + concrete adapters. New `pocketquant-execution` holds the shared strategy/order/position/risk app-services. `backtest` and `trading` become true siblings.

Source design: `plans/260531-infrastructure-execution-extraction-brainstorm.md` (all forks resolved there).

## TDD Strategy

This is a refactor with no behavior change, so TDD = **regression safety net first**, not red-green-new-feature. Each move phase is gated by:
1. **Characterization tests** (Phase 1) pinning load-bearing behavior BEFORE any code moves: sync-status bump/reset DECISION (binary, pinned at the api `sync_one` handler — NOT the repo) + repo atomic `$inc` semantics, PaperBroker fills, deterministic `Subscription.deterministic_id` (multiple input shapes), strategy injection round-trip (asserting `on_start()` + broker connected).
2. **import-linter** (repaired in Phase 1) re-run after every move — the structural assertion.
3. **Full pytest suite** green at every phase boundary.

New public methods (execution-service injection API, sync-status domain service) get fresh unit tests written test-first within their phase.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Safety net: import-linter repair + characterization tests](./phase-01-safety-net-import-linter-repair-characterization-tests.md) | Done |
| 2 | [Scaffold infrastructure + execution packages](./phase-02-scaffold-infrastructure-execution-packages.md) | Done |
| 3 | [Promote persisted entities to core](./phase-03-promote-persisted-entities-to-core.md) | Done |
| 4 | [Move ports + DTOs to core](./phase-04-move-ports-dtos-to-core.md) | Done |
| 5 | [Move persistence to infrastructure](./phase-05-move-persistence-to-infrastructure.md) | Done |
| 6 | [Move adapters to infrastructure](./phase-06-move-adapters-to-infrastructure.md) | Done |
| 7 | [Extract execution engine + kill private hack](./phase-07-extract-execution-engine-kill-private-hack.md) | Done |
| 8 | [Extract sync-status counter to domain service](./phase-08-extract-sync-status-counter-to-domain-service.md) | Done |
| 9 | [Finalize layered contracts + docs + full sweep](./phase-09-finalize-layered-contracts-docs-full-sweep.md) | Done |

## Phase Dependency Chain

Strictly sequential — each phase leaves the tree green and import-linter passing:
`1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9`

Rationale for order: safety net first; scaffolding empty packages is inert; entities must reach core (3) before ports (4) and before any repo can move to infra (5); adapters (6) depend on ports already in core; execution (7) depends on infra repos already moved; sync-status service (8) is independent but cheapest after persistence settles; finalize (9) locks contracts once the graph is physically correct.

## Out of Scope (deferred)

- **Subscription split** (Forward vs Backtest subscriptions) — separate brainstorm→plan AFTER this lands. This effort promotes the single `Subscription` unchanged. Rationale: touches load-bearing deterministic-ID recipe + boot migration; must not ride inside the package move. See brainstorm doc "Deferred Follow-up".

## Key Decisions (from brainstorm)

- Ports (IBroker, IBrokerFactory, IDataProvider, IRealtimeQuoteProvider) + DTOs (OrderResult, AccountBalance, OrderEvent) → **core**, not infrastructure.
- ALL persisted domain entities → **core** (BacktestResult + VOs, Subscription, existing) so every repo can live in infrastructure uniformly; zero repos remain in backtest/trading.
- trading→backtest "run backtests" orchestration (`backtest_jobs`, `backtest_strategy_loader`, `run_all_backtests` handler) → moves to **backtest** package (it runs backtests; belongs with the engine). Trading reads backtest *results* via infra repos only.
- 3 private-member hack sites → public execution-service methods: 2 WRITE sites (backtest `run/handler.py:100-109`, trading `backtest_strategy_loader.py:118-126`) use `inject_prepared_strategy` which MUST connect broker + call `on_start()` inside the lock (they do today); 1 READ site (`backtest_jobs.py:101`, keyed by live `strategy_code`) uses `get_config`. Do not conflate the two keyspaces.

## Dependencies

No cross-plan dependencies. Prior plans (docs-optimization, comment-sweep, move-tests-to-root) all completed. Builds on the root `tests/<pkg>_test/` layout established by move-tests-to-root.

## Red Team Review

### Session — 2026-05-31
**Findings:** 19 (13 accepted, 6 rejected)
**Severity breakdown:** 4 Critical, 7 High, 8 Medium
**Reviewers:** Security Adversary (Fact Checker), Failure Mode Analyst (Flow Tracer), Assumption Destroyer (Scope Auditor), Scope & Complexity Critic (Contract Verifier). All findings carried `file:line` evidence; none rejected on the evidence filter.

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| A1 | `inject_prepared_strategy` drops `broker.connect()` + `strategy.on_start()` done under the same lock (4/4 reviewers) | Critical | Accept | Phase 1, 7, plan.md |
| A2 | Phase 8 premise false — bump/reset rule lives in `sync_one/handler.py` (binary), not the repo; original draft fabricated a tri-state | High | Accept | Phase 1, 8, plan.md |
| A3 | `get_config(sid)` conflates synthetic-id vs live `strategy_code` keyspaces | High | Accept | Phase 7 |
| A4 | APScheduler `bt:*` persisted-job rename. apscheduler auto-drops unresolvable refs on load (no crash, no stuck status). Residual = in-flight fan-out jobs would be dropped. **Validation decision: server-boot step actively re-keys (delete stale + recreate with new func ref) so queued jobs still run — binding, not optional.** | ~~High~~ → Medium | Accept (mitigation now binding per validation) | Phase 7 |
| A5 | `core/common/health/__init__.py` eager import → permanent core→infra edge; left as "confirm during impl" | Critical | Accept | Phase 5 |
| A6 | Repo count 11 vs 12; JobHistoryRepository move was a risk-note "RECOMMENDED" not a step | High | Accept | Phase 5, 6 |
| A7 | Phase 5 undercounts `core.common.cache` consumers (4 api handlers) | Medium | Accept | Phase 5 |
| A8 | Phase 4 left "thin compat re-export" open → landmine deleted at Phase 6 | Medium | Accept | Phase 4 |
| A9 | trading→backtest coupling is 7 sites incl. `BacktestConfig` 5th edge; Phase 9 grep one-directional | High | Accept | Phase 7 |
| A10 | `from pocketquant.backtest.domain import OrderEvent` alias breaks at Phase 3 package deletion | Medium | Accept | Phase 3 |
| A11 | "Port verbatim" carries plan-ref rot (`entities.py:12-14` "After Phase 4 of the storage refactor") into core | Medium | Accept | Phase 3 |
| A12 | Golden deterministic-ID pins one input shape. Post-verification: `_id` re-key risk DISPROVEN — symbol idempotently `.upper()`'d, strategy_code is registry key, and the "dual `Interval`" is one enum (a re-export). Kept: multi-shape golden + single-import-path consolidation (Phase 9). | ~~Medium~~ → Low | Accept (hardening only) | Phase 1, 3, 9 |
| A13 | Phase 1 "likely REPORT" cycle → possible false-green baseline (function-local/TYPE_CHECKING edges) | Medium | Accept | Phase 1 |
| B1 | Drop `pocketquant-execution` package (keep engine in trading) | Critical (reviewer) | Reject | — |
| B2 | Cut "all repos → infra"; promote only `Subscription` | High (reviewer) | Reject | — |
| B3 | Cut Phase 8 entirely | High (reviewer) | Reject (kept, premise fixed via A2) | Phase 8 |
| B4 | Keep `forbidden` contracts, skip `layered` rewrite | Medium (reviewer) | Reject | — |
| B5 | Merge Phase 4 into Phase 6 | Medium (reviewer) | Reject | — |
| B6 | Trim Phase 1 to 2 characterization areas | Medium (reviewer) | Reject | — |

**Rejected-finding rationale (B1–B6):** All six are YAGNI/scope cuts that reverse decisions already locked in the brainstorm doc (`260531-...-brainstorm.md` "Agreed Decisions (locked)" + "Approaches Considered"). Per the project's decision-stickiness rule, an audit's minimalism argument alone does not reverse a confirmed decision without new data. Specifically: **B1** proposes exactly the `keep-in-trading` option already considered and rejected ("linearizing trading-below-backtest is inverted") — no new evidence; user confirmed keep execution package. **B2** reverses brainstorm decision #6 + would force flipping CLAUDE.md "Backtest repos in backtest package" anyway; user confirmed all→infra. **B3** premise was factually wrong (fixed by A2); user kept Phase 8. **B4/B5/B6** are structural-preference cuts with no correctness driver; user did not adopt. These remain available if the user later wants to reopen scope.

### Post-Review Codebase Verification (3 user questions)
Three accepted findings were re-verified against live code; results refined the plan:
- **Q1 (Subscription `_id` casing):** SAFE. `symbol` idempotently `.upper()`'d at recipe (`subscription.py:55`) + sole caller (`add_symbol/handler.py:45`); `strategy_code` = `STRATEGY_REGISTRY` literal key (`handler.py:52-53`); recipe unchanged by move. No production `_id` will mismatch the golden.
- **Q2 (dual `Interval`):** ONE enum, not two. `value_objects.py:4` is a `# noqa: F401` re-export of `enums.Interval`. No `.value` drift, no re-key risk. User wants a single internal path → Phase 9 now consolidates all ~22 `value_objects.Interval` imports to `enums.Interval` (drop the re-export; keep `INTERVAL_SECONDS`).
- **Q3 (`bt:*` persisted jobs):** Re-verified apscheduler 3.11.2: `MongoDBJobStore._get_jobs` auto-`delete_many`s a job whose ref fails to resolve (`ref_to_obj` → `LookupError`, caught) — self-healing, no scheduler crash. `status="running"` is on the BacktestRepository result doc (written inside the job, step 3 `backtest_jobs.py:88`), not the Subscription; existing `recover_stale_backtests` boot sweep covers stragglers. A4 downgraded High→Medium. **Validation Session 1 superseded the "optional/defensive" framing: the server-boot step now actively RE-KEYS stale `bt:*` jobs (delete + recreate with the new func ref) so queued fan-out jobs still run — binding, see Phase 7 step 6.** The erroneous "reset subscription status" instruction was removed (no subscription field carries `running`).

### Whole-Plan Consistency Sweep
Re-read `plan.md` + all 9 phase files after applying A1–A13 and the post-review refinements. Reconciled:
- Repo count unified to **12** (Phase 5 body/steps/criteria/risk + Phase 6 overview consistent; JobHistoryRepository moves in Phase 5, only `scheduler.py` in Phase 6).
- Injection contract (connect+on_start inside lock; write-vs-read keyspace split) consistent across plan.md Key Decisions, Phase 1 target #4, Phase 7 API + steps + criteria.
- Sync-status premise corrected everywhere (Phase 1 target #1, Phase 8 overview/architecture/steps/criteria/risk, plan.md TDD Strategy) — rule at `sync_one/handler.py`, binary, no tri-state.
- `core.common.{cache,health}` re-point + 4 cache consumers + health-shim resolution consistent in Phase 5.
- Two-directional cycle grep + `BacktestConfig` 5th edge consistent in Phase 7.
- A4 (`bt:*` rename) consistent across Phase 7 architecture/step 6/criteria/risk + plan.md table: self-healing, mitigation optional, no subscription-status reset.
- `Interval` consolidation consistent: Phase 1 (note), Phase 3 step (c) (no new value_objects imports), Phase 9 (the actual repoint + criterion).
- No stale "11 repos", "RECOMMENDED relocate", "document drain OR", "binding boot purge", "reset subscription running", or fabricated tri-state terms remain (grep-verified).
- Graph + import-linter `layered` contract (Phase 9) unchanged — B1/B4 rejected.

**Unresolved contradictions:** none. Plan is internally consistent and ready for implementation.

## Validation Log

### Session 1 — 2026-05-31

**Verification (guard: Red Team + post-review evidence already present; limited to spot-check + `[UNVERIFIED]` scan):**
- Claims checked: 7 critical | Verified: 7 | Failed: 0 | Unverified-tags: 0
- import-linter crash (missing `include_external_packages`) — VERIFIED by running `uv run lint-imports` (crashes verbatim).
- A2 binary bump/reset at `sync_one/handler.py:95-104`, no tri-state — VERIFIED verbatim (comment confirms uniform single decision).
- A1 3 hack sites + connect+on_start inside `_lock` at both write sites (`run/handler.py:101-108`, `backtest_strategy_loader.py:119-126`) — VERIFIED.
- 7 trading→backtest edges incl. BacktestConfig 5th edge (`backtest_strategy_loader.py:10`) — VERIFIED (4 repo readers + BacktestConfig + 2 in backtest_jobs).
- A5 `health/__init__.py` eager-imports `check_database`/`check_redis` — VERIFIED.
- A6 JobHistoryRepository extends BaseRepository → 12 repos (4 core + 3 trading + 4 backtest + job_history) — VERIFIED.
- A12 single `Interval` enum, `value_objects` re-exports `enums` (`# noqa: F401`), ~22 import sites — VERIFIED.

**Decisions confirmed (3 questions):**
1. **`bt:*` stale persisted-job handling (Phase 7) — CHANGED from plan's optional/defensive stance.** User decision: on server (VPS) boot, **delete the stale `bt:*` job and re-create it with the correct (new) func-ref path** — active re-key, idempotent boot step. NOT a deploy note, NOT a passive purge. No doc/log entry for this. Supersedes the prior "(a) deploy note OR (b) eager logged purge" choice and the "mitigation optional/defensive" framing. apscheduler self-healing still holds (no crash), but we proactively re-register so the in-flight fan-out job actually runs post-deploy.
2. **OrderEvent public-alias break (Phase 3) — Direct fix (DRY).** Re-point all `from pocketquant.backtest.domain import OrderEvent` consumers to the true source; no alias re-export carried into core. (Matches plan lean; now binding.)
3. **Backtest VO layout (Phase 3) — Single `value_objects.py`.** User explicitly chose one consolidated file over the per-file dir split, **overriding the >200 LOC modularization guideline** for this module. Phase 3 architecture updated: `core/domain/backtest/value_objects.py` (single file), not a `value_objects/` dir.

### Whole-Plan Consistency Sweep (Validation Session 1)
Re-read plan.md + all 9 phase files after propagating the 3 decisions. Reconciled:
- **bt:* re-key:** consistent across plan.md A4 row + Q3 note + Phase 7 architecture/step 6/criteria/risk. All now say "active delete+recreate on server boot, binding"; removed the prior "optional/defensive/deploy-note OR purge" framing everywhere (grep clean).
- **OrderEvent alias:** Phase 3 step 5 binding direct-fix; plan.md decision #2 matches. No "keep alias / decide whether" left open.
- **Single value_objects.py:** Phase 3 architecture + Related Code Files both say single file; "value_objects/ dir" / "keep dir split" removed. Remaining `domain/value_objects/*` mentions are the CURRENT source tree being moved FROM (correct, not stale).
- No stale superseded terms remain (grep-verified for: optional/defensive bt purge, deploy-note alternative, value_objects dir split, alias re-export decision).

**Unresolved contradictions:** none. Plan ready for implementation.
