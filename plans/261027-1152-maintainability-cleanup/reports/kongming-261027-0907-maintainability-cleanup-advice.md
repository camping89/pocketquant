# Kongming counsel — PocketQuant maintainability pass

**TL;DR.** Do the all-red work first (one deletion batch of ~2.3k LOC gated by six quick decisions), one log-level pass, and one three-line fill-path safety fix; then the only two refactors that pay back in reading time (the `sync_jobs.py` wrapper and the backtest chain 6→3). Skip the DI, domain-event, micro-module, and paper-broker-builder proposals. Live trading is disarmed (verified), so this is the right window, but leave `exness_broker_adapter.py` untouched so the go-live plan's line citations stay valid.

## Reframed problem

The decision is not "which of 19 proposals to accept" but "which few changes reduce the files and hops a human reads during an incident, at near-zero prod risk, in a few evenings". Reading time lives in hops and copies (6-file backtest chain, 6 copies of job boilerplate, 1.4k LOC of OKX that docs call live, INFO noise in a 12-hour log window), not in LOC counts. Non-goals: new abstractions, new CI gates, touching the Exness adapter.

## Verified context the review did not have

- **Prod state (fact, `pocketquant/plans/261019-1957-exness-go-live/plan.md:68-69`):** phases 01-10 completed; live armed 2026-10-21, disarmed 2026-10-22; Phase 11 called off ("no profitable strategy yet"). Prod is paper-only. The plan cites adapter lines (`exness_broker_adapter.py:200-205`, `:239-240`, `:261-263`).
- **The high finding is paper-path only (fact):** `exness_broker_adapter.py:96` sets `fills_async = True`; `submit_order` returns `SUBMITTED` (`:365`); fills arrive via `_notify` (`:625-631`), which already wraps every callback in try/except + warning. So on Exness, a save failure after `on_order_update`'s `order.fill()` (`order_app_service.py:189-191`) leaves the order in RAM as FILLED but unsaved and unpublished (inference: strategy and mirror never learn of the fill, warning logged) — a desync, but not the "told rejected" path. The reject-after-fill path (`order_app_service.py:69-85` then `:116-120`, `entities.py:52-58` has no FILLED key) is real for the paper broker, i.e. live paper and every backtest.
- **Bruno collection exists at `tests/http/` (fact):** `trading/*.bru`, `sync-one.bru`, `sync-one-background.bru`, `sync-bulk.bru`, `get-symbol-sync-status.bru`, `get-current-bar.bru`. No `.bru` for `PUT /tracked-symbols/{symbol}` or `DELETE /strategies/{code}`. README:93-95 uses `POST /sync` and `/sync-status/{symbol}`.
- **CI (fact, `.github/workflows/cicd.yml:48,51`):** `lint-imports`, ratchet, pytest. Web: `eslint` only, no knip. Ratchet: `max_tiny_share = 0.4862`, `max_delegations = 93` (`pyproject.toml:178-180`).
- **`scripts/rubric/output`:** 4 tracked files, zero references in `docs/` or `scripts/README.md` (fact).
- **The deferred 04:00 integrity stall fix** goes to "a separate follow-up plan" (`plans/journals/2026-10-24-asset-class-index-futures-plan-closed.md:21`) and will touch `sync_jobs.py`/`integrity_jobs.py` (inference).
- **Working tree is not clean (fact):** staged renames archiving `plans/261009-0858-…` plus untracked `plans/261023-0056-…` and two journals.

## 1. Ranking by reading time saved per owner hour

1. **Pure deletions** (proposals 1, 10, 19, the "confirmed dead" table, the seeder, tick trigger/YAML-era config, web dead files). About 2.3k LOC, 2-3 h, the diff is all red and the type checker and tests catch mistakes. Nothing else comes close.
2. **Log-level pass + `request_logging` DEBUG-only** (medium findings, proposal 9). 1-2 h. Pays on every prod incident because logs keep ~12 h and INFO noise currently crowds out `order_filled`/`integrity.issues_found`.
3. **Fill-path safety** (high + event-bus medium + `_on_order_filled` boundary). 1-2 h with one test. Not a reading win; it removes the most expensive future debugging session (silent paper desync in live and in backtests).
4. **`sync_jobs.py` one wrapper + per-symbol isolation** (proposal 2 plus the three sync lows). Half a day. This file is the first read in every market-data incident (journals: calendar bug, 04:00 stall, partial aggregates); six copies become one and both C901 hits drop.
5. **Backtest chain 6→3** (proposal 3). Half a day to a day. The largest hop reduction in the repo; the hitnrun2/engulfing characterization tests (`tests/backtest_test/engine/`) are the safety net. Depends on decision 9 (the `run_single` import in `recompute_backtest_costs.py`).
6. **Dead live-execution surface + `risk_check` cleanup** (proposal 4). 2-3 h. Makes `order/position_app_service.py` and `risk_check.py` read as what they do today.
7. **`EventRegistry` → explicit `bus.subscribe`** (proposal 6). About 1 h. Removes the one reflection trap (`_`-prefix scan) from the live wiring; subscriptions become greppable.
8. **`main_extensions.py`** (proposal 8): take only the free parts (dead `JobScheduler` methods go in item 1, `_cancel`, one `enable_jobs` gate, duplicate `set_container`). Move `/system/jobs` only if you are already in the file.

**Skip or defer:** proposal 12 (DI pass-throughs: unverified Dishka handling of defaulted params, no reading gain); 15 beyond deleting `SignalGeneratedEvent` and the `PositionOpenedEvent` publish (tests pin `_events`); 13 (micro-modules: test-import churn for 25-60 lines; inline `bar_alignment.py` only when `provider_fetch.py` is open); 16's stats-DTO half (OpenAPI snapshot churn; do only the `market_data.py` dict drift); 17's `components/strategy/` move (git churn; do it the next time those files change); 5's `_reject/_filled` builders (the paper broker is the fill oracle for live paper and backtests, had a fix on 2026-10-26, and E2 paper validation is still running on it); 18's `Trade.from_closed_event` and `BacktestConfig.to_dict` unless the collapse still leaves two copies.

## 2. Correctness: before/alongside vs later

**Before or alongside (same code or prod paper risk):**
- Reject-after-fill (high) + `EventBus.publish` isolation/list copy + `_on_order_filled` error boundary — one batch, before any order-path refactor. Fix shape: in the `except` at `order_app_service.py:116`, reject only when `order.status is PENDING`, else log with `exc_info` and re-raise; `for handler in list(handlers)` with per-handler try/except in `event_bus.py:31`.
- Ghost paper broker on unload + restart mirror (two mediums) — alongside batch 7, and before Phase 11 is re-run, because Phase 11 deletes a paper subscription (`phase-11…md:13`), which is exactly the ghost trigger. Needs decisions 3 and 4.
- INFO flood + body buffering — batch 2.
- Double-recorded failures, "all symbols failed = completed", per-symbol isolation, stored `bar_count` — alongside the `sync_jobs.py` wrapper; the re-raise that causes the double record is the wrapper.
- `risk_check` no-op/EXIT/zero guard and the `DELETE /strategies` cascade — alongside batch 4.
- Crosshair leak, `'1w'`, `fancy-canvas` — alongside the web deletions.
- Tick lock across publish (medium): can wait; with paper-only live the cost is a 50 ms stall per order (inference). Do it when `bar_app_service.py` is open.

**Can wait (fix when the file is open):** `spa_fallback` containment (decision 12 may delete it), index drop/recreate, `correlation_id`, backtest 202-then-fail, startup panel text, SSE `CancelledError`, `fmtPrice`, `consecutive_empty_fetches`, backfill checkpoint, float equality, comments and non-English text, cron log nit, asserts, `reconcile.load_failed` cadence (cheap enough to fold into batch 2), `still_missing` truncation (batch 2).

## 3. Batching and order

Use one plan directory (your convention) with these phases in run order. Each batch is one develop commit set reviewed as a unit; deploy only at the three marked points, each restart following the "Restart while live" runbook and confirming 01a178ef is still `running`.

| # | Batch | Gate | Prod watch |
|---|---|---|---|
| 0 | Commit the staged plan-archive renames and untracked plan files so later diffs are pure. | `git status --porcelain -- src web deploy tests scripts docs` empty | none |
| 1 | Fill-path safety (3 edits + 1 test: save raises after fill → order stays FILLED, no reject). | `tests/engine_test/test_order_app_service_immediate_fill.py`, `test_order_filled_event_routing.py`, `test_strategy_reject_delivery.py`, `test_async_broker_fill_wiring.py`, event-bus tests | every `order_filled` followed by `position_opened`/`position_*`; zero `order_submit_error` |
| 2 | Log levels (list in finding) + `request_logging` DEBUG-only + `load_failed` once + `still_missing` truncate. **Deploy A.** | `tests/app_test/unit/market_data/*`; run locally at `LOG_LEVEL=INFO` for two minutes and confirm no per-minute lines | log volume/hour drops; `integrity.issues_found`, `data_lag.state_changed`, `order_filled` still visible |
| 3 | Pure deletions, three commits: (a) OKX + idempotency + seeder + one-time scripts + `scripts/rubric/output`; (b) confirmed-dead table + tick trigger/YAML config + `EventBus` test-only helpers + scheduler dead methods + `test_core_layout_contract.py` pins; (c) web dead files + `fetchOHLCV` etc. + crosshair + `'1w'` + `fancy-canvas`. Lower both ratchet ceilings to the new numbers in commit (b). | `ruff`, `pyright`, `lint-imports`, ratchet, full pytest; `web`: `eslint`, `tsc`, Vite production bundle | none (no behavior change); after Deploy B confirm startup has no `tracked_symbol_seeder` line |
| 4 | Dead live-execution surface + `risk_check` fixes + `DELETE /strategies` decision. | `tests/engine_test/test_strategy_service.py`, `test_orders_positions_service.py` deleted, layout contract | none |
| 5 | `sync_jobs.py` wrapper + per-symbol isolation + double-record + completed/failed semantics + stored `bar_count` + comment fixes. **Deploy B.** Sequence this before the 04:00 stall plan, not in parallel (same file). | `tests/app_test/unit/market_data/*`, `tests/engine_test/market_data/test_sync_service.py`, job-history tests | 24 h: one `job_history` row per run, no duplicate `failed`; `sync_1m` every minute; 04:00 `sync_integrity` completes |
| 6 | Backtest chain 6→3 (+ `BacktestConfig` round-trip only if two copies remain). | all `tests/backtest_test/**`, `tests/app_test/integration/test_app_standalone_runtime.py`; run one SPA backtest before and after and diff the stats | compare the two run ids |
| 7 | Paper position truth: ghost broker disconnect on unload, restart mirror policy, `EventRegistry` → explicit subscribe, paper `_orders`/decorator removal. **Deploy C.** | `tests/engine_test/test_strategy_reconcile_service.py`, `test_reconcile_restart_resume_integration.py`, `test_live_trade_collector_integration.py`, `tests/core_test/infra/brokers/*paper*` | restart: `loaded_open_positions` matches paper reality; delete a throwaway subscription: no trade with empty `strategy_code` |
| 8 | Optional polish: `main_extensions` free parts, SSE helper, `market_data.py` dict drift. | per file | none |

**Dead-code decisions that unblock the most:** decision 1 (OKX, 1.5k LOC plus its tests and the factory branch), decision 7 (tick trigger and LIMIT path: unblocks proposal 7 and ~200 paper-broker lines), decision 5 (`/trading/*`: unblocks proposal 4), decision 9 (deleting `recompute_backtest_costs.py` removes the `run_single` import that constrains proposal 3), decision 12 (SPA mount: deletes the traversal finding with the code).

## 4. The 12 decisions — recommended defaults

1. **OKX: delete.** Three gates make it unreachable and docs call it live; git keeps it. One prod query first: `db.subscriptions.countDocuments({broker: "okx"})` (expected 0; such a doc already fails to load).
2. **Seeder: delete** after `db.strategies.countDocuments({})` and `db.orders.countDocuments({status: "open"})` both return 0 (expected; the status does not exist in the enum).
3. **On delete: close the paper position and disconnect a holder-less paper broker; leave an Exness position at the venue with a WARNING.** Paper has no one else to close it; Exness has the venue SL/TP and Phase 11 handles deletion by hand.
4. **Restart: drop paper rows from the mirror (close at boot with one log line).** Matches the accepted rule that strategy state does not survive a restart; restoring is more code.
5. **Endpoints:** keep `POST /sync`, `/sync/background`, `/sync/bulk`, `GET /sync-status/{symbol}`, `GET /quotes/current-bar/{symbol}` (Bruno + README callers); delete `/trading/*` with its four `.bru` files, `PUT /tracked-symbols/{symbol}`, and `DELETE /strategies/{code}` plus the two dead repo methods (symbol delete already cascades).
6. **Idempotency middleware: delete.** No client sends the header; the key design is unsafe anyway.
7. **Tick trigger and LIMIT path: remove both** with their tests. No strategy uses either; git keeps them for a future that has a real caller.
8. **Follow the DEBUG rule.** "Bounded" is wrong in practice: 12-hour retention and a journaled killed pipe.
9. **Delete both scripts if they ran; drop `scripts/rubric/output` from git** (4 files, no references) and gitignore it if the rubric regenerates it.
10. **Do not chase the double-persist race now.** The retry workaround lives in the script being deleted; re-check only if it reproduces after batch 6.
11. **Amend CLAUDE.md with one sentence:** a route may inject a repository or `Cache` directly when the handler adds no logic. Wrapping adds delegations the ratchet counts.
12. **Delete the SPA mount** — the prod Dockerfile ships no `web/dist` (review-verified) and the SPA has its own container; dev uses Vite.

## 5. Keeping it from regrowing

Nothing new. Two zero-cost habits already in your rules: lower both ratchet ceilings in the deletion batch and never raise them; apply "a new helper needs a second real caller today" at review. Do not add vulture or knip to CI — the review shows both produce a long false-positive list here (FastAPI, Dishka, Pydantic, file-router exports), so a gate would need an allowlist that costs more than it saves. Running `npx knip` or `vulture src` by hand once a quarter is enough.

## 6. What I would not do, and what the reviews overstated

- **Not touch `exness_broker_adapter.py`** (no proposal needs it; the go-live plan cites its lines and Phase 11 is re-runnable).
- **Not deploy per batch**; three deploys, each resets paper warmup (hitnrun2 ~8 h, engulfing ~21 h per the plan).
- **Not refactor `sync_jobs.py` while the 04:00 stall fix is in flight** — do the wrapper first so the stall fix lands on a smaller file.
- **Not do proposals 12, 13, 15 (beyond two deletions), the paper-broker builders, or the `components/strategy/` move now.**
- Overstated: the high finding's "after a live fill" — on Exness the mechanism and symptom differ (verified `_notify` isolation); the tick-lock medium is a 50 ms paper stall today; `spa_fallback` is dev-only; "`/trading/*` Bruno files not validated" — they exist under `tests/http`, so the surface has a manual caller, which is why decision 5 is yours; the 2.5-3.5k LOC headline is 60 percent OKX, and reading time comes from the hop reductions (batches 5 and 6), not from LOC.
- Unverified by me: that the reconcile loop never sees sandbox ids (the `::bt::` guard deletion in proposal 18) — check `strategy_reconcile_app_service.py:201-218` against how the sandbox names subscriptions before deleting the guard.

## Assumptions

- Prod remains disarmed as recorded on 2026-10-22 (high; a newer config flip would make batch 7 urgent and batch 1 a hotfix).
- No ops or curl use of `PUT /tracked-symbols/{symbol}` or `DELETE /strategies/{code}` (medium; a Bruno file or README line would flip decision 5 for that route).
- Owner effort budget is a few evenings spread over weeks, not a sprint (medium; with a full week, add proposals 8 and 11 in full).
- The two one-time scripts have run in prod (medium; if not, keep them until they do).

Status: DONE_WITH_CONCERNS
Summary: Ranked the merged review into eight batches (three deploys), with defaults for all 12 decisions; the main corrections are that the high finding is paper-path-only on Exness, that `/trading/*` has a Bruno caller under `tests/http`, and that live is disarmed since 2026-10-22, which makes now the right window. Concerns: the `::bt::` guard deletion and the sandbox-id claim are unverified, and the `sync_jobs.py` batch must be sequenced against the planned 04:00 stall fix.

mementomori - 2026-10-27