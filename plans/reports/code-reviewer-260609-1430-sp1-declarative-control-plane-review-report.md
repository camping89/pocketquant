# SP1 Declarative Control Plane — Code Review

Scope: reconcile loop + declarative handler rewrite. 7 created, 12 modified files.
Verdict: **PASS-WITH-CONCERNS** (concerns = Low/observability only; no Critical/High).

## Acceptance criteria — all met

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Frozen sub, deterministic_id unchanged, from_mongo back-compat | PASS | entities.py:43-44 defaults stopped; deterministic_id:46-64 hashes 3-tuple only (state excluded); from_mongo:87-88 `.get(...,"stopped")`. Tests: test_subscription_desired_actual_state.py (id-stable, legacy-default, roundtrip) |
| 2 | Reconcile idempotent/converges/cancel-safe/crash-proof/sub-driven/never-loads | PASS | service drift-only write (line 84), CancelledError re-raise (58-60), per-tick backstop (61-63), per-sub isolation (76-80), list_all-driven, missing-instance warns+stopped (102-105). 8 unit tests cover all |
| 3 | Handlers write desired only, no AppService dep, 404, add=stopped, list from DB | PASS | start/stop handlers carry only sub_repo, NotFoundError on modified==0; add_symbol:79 desired="stopped" + start_strategy not called; list_symbols sources actual_state, is_running derived |
| 4 | Migration $exists:false idempotent, gating, ordering | PASS | migrate_subscription_desired_state:267-269; lifespan ordering rename→backfill→rehydrate→reconcile-last; teardown reconcile-first. Idempotency test simulates human-stop, no re-flip |
| 5 | remove/delete keep AppService for unload | PASS | remove_symbol.py:38-39, delete handler retain unload |

## Adversarial findings traced

### Concern A — remove_symbol vs reconcile race (theoretically-bad, PRACTICALLY SAFE)
File: remove_symbol/handler.py:38-42 vs strategy_reconcile_service.py:100-108.
Window: human removes a running sub. reconcile `_converge_one` snapshots `get_strategy` (line 100, no lock) then calls `start_strategy`. If `unload_strategy` pops the instance in between, `start_strategy` re-checks under `_lock` (strategy_app_service.py:120-121) and raises `ValueError("Strategy not found")`.
Outcome: ValueError caught by per-sub isolation (`reconcile.sub_failed` logged, loop continues). Sub row also deleted → vanishes from next `list_all()`. No crash, no orphan, self-heals in ≤1 tick. **No fix needed.** The lock-recheck in start_strategy is the real guard — correctly relied upon.

### Concern B — start/stop idempotency under manual-write race (SAFE)
`start_strategy`/`stop_strategy` are `_lock`-guarded and early-return when already in target state (strategy_app_service.py:124-125, 141-142). Reconcile re-reads `strategy.is_running` after the call (service:112) to compute observed actual. A concurrent desired flip just converges next tick. Idempotency is real, not assumed.

### Concern C — actual_state write-churn (SAFE, verified)
Write gated on `observed != sub.actual_state` (service:84). Steady states (running/running, stopped/stopped, missing+stopped) produce zero writes. Confirmed by `test_stable_*_idempotent_no_calls_no_writes` and `test_missing_instance_*persists_stopped`. No per-tick churn.

### Concern D — migration never re-flips human stop (SAFE, verified)
Filter `{"desired_state": {"$exists": False}}` (main_extensions.py:268). `$set` includes `actual_state:"stopped"` but only matched docs (legacy, lacking desired_state) are touched — a modern doc keeps its state. `test_idempotent_second_run_no_changes` proves a post-migration human-stop survives a redeploy. Mass-start risk is user-accepted + documented with pre-deploy count + rollback one-liners (main_extensions.py:259-263).

### Concern E — FE contract (SAFE)
list_symbols adds `desired_state`/`actual_state`, KEEPS `is_running` (handler.py:53). FE reads `sub.is_running` (strategy-api.ts:30, strategy-config-card.tsx:37) — extra keys are additive, TS interface ignores them. No breaking removal.

## Low

### L1 — Permanent missing-instance log-spam (observability)
File: strategy_reconcile_service.py:103-104.
A sub with `desired="running"` whose `strategy_code` is NOT in `STRATEGY_REGISTRY` is skipped by rehydrate (main_extensions.py:377-384, warn-once) but then logs `reconcile.missing_instance` **every tick forever** (5s → 17k warns/day). Same for a legacy migrated sub whose template was deleted from code. Not a correctness bug (actual stays stopped, observable), but will bury real signal.
Fix (optional, post-merge): throttle — only warn when `observed` drifts from stored `actual_state`, i.e. move the warn under the `observed != sub.actual_state` branch in `_reconcile`, or track a "already-warned" set per sub_id. Keeps first-occurrence visibility, drops the repeat.

### L2 — Migration `actual_state` redundant in `$set` (cosmetic)
File: main_extensions.py:269. Backfill sets `actual_state:"stopped"`, but reconcile recomputes actual within one tick regardless. Harmless; the explicit write makes FE state coherent pre-first-tick. Keep as-is (intentional, matches plan D3).

## Positive

- Lock-recheck reliance in start_strategy is the correct race guard — review confirms the reconcile code leans on it deliberately (docstring line 168-170 + service:75).
- Drift-only actual write is the right idempotency primitive; tests pin it precisely.
- Teardown ordering (reconcile-first) + start ordering (reconcile-last) both correct and commented with the WHY (main.py:83-84, 93-95).
- Migration idempotency test simulates the exact dangerous scenario (human-stop-then-redeploy) — not just a re-run.
- Comment policy clean: WHYs only (races, ordering, hash-stability), zero plan/phase/finding refs in code.
- Injected-backtest invariant (synthetic id, no sub row → untouched) has a dedicated load-bearing test.

## Metrics (user-verified, not re-run)
- Suite: 444 passed / 12 skipped / 0 failed
- import-linter: 7/7 contracts
- pyright: 0 errors on changed sources
- ruff: changed files clean (141 pre-existing repo errors NOT from this work)

## Unresolved questions
- L1 throttle: ship now and fix later, or gate merge? Recommend ship — it's pure log volume, no correctness/security impact. Confirm acceptable.
