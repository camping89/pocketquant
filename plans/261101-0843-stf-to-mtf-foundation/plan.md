---
title: "Retire single-timeframe strategies; generic multi-timeframe foundation"
description: "Spike the whole MTF foundation in a throwaway worktree, deploy the 1d cascade for session calendars first, delete the three STF strategies, then build the generic contracts (subscription intervals + parameters, closed higher-timeframe context from Mongo, stop entry, strategy EXIT, manual close/cancel, generic snapshot, generic UI, backtest intervals), add Triple Screen as the first consumer, backtest it, run one paper subscription, and delete the STF prod data last."
status: pending
priority: P1
effort: "about 12-15d code + 2 deploys + 7 days 1d comparison + paper observation"
branch: develop
tags: [mtf, strategy, subscription, backtest, paper, exness, web, triple-screen]
blockedBy: []
blocks: []
created: 2026-11-01
---

# Retire single-timeframe strategies; generic multi-timeframe foundation

## Overview

PocketQuant decides on one timeframe per subscription, and its three strategies (hitnrun2, engulfing, engulfing_pullback30_touch) are single-timeframe (STF). The owner retires STF as a strategic call and wants a generic multi-timeframe (MTF) foundation. A subscription declares an ordered list of intervals (lowest = entry) and generic parameters. On each closed entry bar the engine hands the strategy the higher-timeframe bars that closed strictly before the entry bar's close, read from Mongo through a per-(symbol, interval) cache. The same rule runs in live, warm-up and backtest. Stop entries and strategy exits become platform capabilities. Strategies report a generic snapshot that the UI renders without knowing the strategy. Triple Screen is the first consumer only. Live trading stays disarmed for the whole plan.

The plan is written for a downstream executor model. Every phase carries tasks with Goal, Target files, Steps, Success criteria and a mechanical Verify, and ends with the same Failure Protocol block.

## Sources (read when a phase cites them)

- Accepted advice and owner decisions: `plans/reports/advise-261101-0847-stf-to-mtf-migration.md`; interview record `plans/reports/advise-261101-0847-stf-to-mtf-migration-state.md`; confirmed UI mockup `plans/reports/advise-261101-0847-stf-to-mtf-migration-ui-mockup.html`.
- Evidence packet with the owner contract C1-C13 and the scout findings: `reports/debate-evidence-packet.md`.
- Exact code locations: `reports/scout-backend.md`, `reports/scout-web-docs-ops.md`.
- Synthesis that fixed this plan's structure and design verdicts: `reports/kongming-261101-1630-debate-synthesis.md`.
- Candidates it drew from: `reports/planner-debate-candidate-1.md` (KISS), `-2.md` (money path), `-3.md` (executability).
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`.

## Owner decisions

C1-C13 in `reports/debate-evidence-packet.md` are the contract. Added while planning (2026-11-01, asked in Vietnamese, recorded in English):

| # | Decision |
|---|---|
| D1 | The reconcile loop may gain two steps: apply and clear a subscription's `manual_action`, and reload the config of a non-running instance whose `(intervals, parameters)` changed. Its period, lease gating and load/unload ownership stay unchanged. This is an allowed exception to C13. |
| D2 | Add a CI `web` job (lint, `tsc -b`, vitest) that `build-web` depends on; fix the two existing `tsc` errors first. |
| D3 | Triple Screen backtests on `XAUUSD:EXNESS` use three interval sets: `15m,1h,4h`, `1h,4h,1d` and `5m,15m,1h`. Each set runs with both parameter settings: `entry_type=market, exit_mode=sl_tp` and `entry_type=stop, exit_mode=strategy`. Six runs. The compare view keeps its cap of 3 runs, so the runs are read across several compare views plus a metrics table. Do not call the settings "versions" or "V1/V2"; name them by their parameter values. |
| D4 | The first paper subscription uses `entry_type=stop, exit_mode=strategy` on the interval set the owner picks from the backtests, so the pending stop and the strategy EXIT are observed on prod. After the observation the owner may switch parameters. Amended 2026-11-02 by the owner: three paper subscriptions, one per D3 set; `15m,1h,4h` is the primary for the Phase 16-17 contracts. |
| D5 | At the prod delete, positions, orders and trades that belong to no existing subscription (orphans) are deleted too, listed separately and confirmed by their own explicit yes. No backup (C12). |
| D6 | A manual close or cancel has no expiry: an action requested while the trader is down runs when the trader holds the lease again. The row shows the pending action. |
| D7 | `closePosition` and `cancelPendingOrder` are not fenced by the live-trading flag (they only reduce exposure); `openPosition` and `placePendingOrder` stay fenced. Every attempt to apply a manual action clears it and records its outcome (`accepted` or `rejected:<code>`); the owner retries if needed. Checked in the Exness spec 2026-11-01: close and cancel are unavailable only when the instrument `trade_mode` is `trading_disabled`; a close may still fail asynchronously with `MARKET_SESSION_CLOSED` or `MARKET_NO_QUOTES`. |
| D8 | The new reads (`GET /subscriptions/{id}/snapshot`, `GET /subscriptions/{id}/orders`, the enriched subscription list) and the existing positions and trades reads require the admin token; the web sends the token on these reads. |
| D9 | No freshness column in the subscription row. |
| D10 | Backtest context cost (spike S4, asked 2026-11-01): a backtest loads each higher interval from Mongo once for the run and slices it in memory, as warm-up does, and keeps the bound `t_mtf_s <= 2 * t_stf_s`. Phase 08 Task 08.3 builds and tests it. The live path is unchanged. Amended 2026-11-02 after CI run 41332031144 measured 2.03x on one runner (owner answer "1+2"): CI asserts only one Mongo read per higher interval; the time ratio is measured locally and recorded in each phase report, not a CI gate; and the context lists are handed to strategies without a per-bar copy, so a strategy must never mutate them. |

## Design verdicts (from the synthesis; do not re-decide in a phase)

- **Closed higher-timeframe bar**: a bar `b` of a higher interval is visible to an entry bar when `b.datetime + step(b.interval) <= entry_bar_start`. The instant is the entry bar's start (`bar["timestamp"]`) in every path. No clock, no wait, no lag constant, no `updated_at` check.
- **Cache**: `StrategyAppService` holds `self._context[(symbol, interval)] = (window_start, bars, complete)` and re-reads Mongo only when the calendar's bucket for the instant moves. A miss is cached only when the previous bucket is present or has no trading minutes; otherwise re-query on the next entry bar and log one WARNING per (symbol, interval, window). No new module, class or lock.
- **Warm-up** calls the strategy directly, not `_on_bar_completed`. It prefetches each context interval once before `on_start()` and slices in memory with the same filter. It waits to second 20 whenever `now.second < _WARMUP_READY_SECOND` and stored entry bars exist (with no stored bars nothing is replayed, so no partial bar can be).
- **Backtest sandbox** gets the real bar repository and calendar factory and starts the position tracker.
- **Pending stop** rests in the broker (paper and Exness). `on_order_update` is subscribed for every broker and returns early for `OrderStatus.PENDING`. Every new signal cancels the subscription's resting stop, then places.
- **Resting stop trigger order**: the paper broker receives each bar after the strategies, so the engine calls `PaperBrokerAdapter.fill_resting_stops(event, running)` before any strategy decides on that bar; otherwise a stop re-placed every bar would be cancelled before it could fill. A resting stop never survives a stop, unload, edit or trader handover: `stop_strategy`, `unload_strategy` and engine `stop()` cancel it, takeover restores none and cancels any stored PENDING order, and the strategy re-places on its next bar. `fill_resting_stops` acts only for running instances while `trading_until` is set, re-runs the pause and loss-cap check at the trigger, and is followed in the same pre-strategy pass by the SL/TP check (on a stop-fill bar the SL is checked against that bar's range). An unchanged re-placed stop (same side and price) is kept, not cancelled and re-sent.
- **EXIT** means go flat: cancel the pending stop, then `IBrokerPort.close_position(subscription_id, symbol, *, reason, deadline)` if a position is open (`reason` is `strategy_exit` or `manual_close`). The close is sent even when the cancel fails. `close_position` is a no-op when the position is already closed (decided by state, never by object identity). EXIT is exempt from the stale and gap skips; an in-flight block keeps it for the next bar. Paper closes under its own lock through `_fire_synthetic_exit`; Exness calls `closePosition` (DELETE by position id) and the fill arrives through the existing close path. No `reduce_only` flag.
- **Orders persist `sl_price` and `tp_price`.**
- **Snapshot**: the strategy sets `snapshot = {"readings": [...], "decision": {...}}`; the engine appends `{bar_start, interval, readings, decision, outcome, pending}` (`pending = {side, price} | null`, `price` = stop price, per C7) to a ring of 20 and writes it as one JSON value to Redis key `strategy:snapshot:{subscription_id}` with a 7-day TTL, only for live bars while the trader holds the lease. No cleanup job.
- **Manual action**: `manual_action: "close" | "cancel" | None` on the subscription document; the route sets it only when it is null (409 `ACTION_PENDING` otherwise); the lease holder's reconcile tick applies it through the same engine paths strategies use, then clears it with a filter on the same value. `manual_action(sid, action)` returns None (action stays queued) only in standby or drain, or while the broker has no current price for the symbol; otherwise it attempts the action, and every attempt clears the field and records `accepted` or `rejected:<code>` (D7).
- **Test doubles**: `tests/strategy_doubles.py` holds one double, `ScriptedStrategy` (Phase 05 creates it; later phases add per-bar scripted signals and snapshots to it); the `probe_registry` fixture lives in `tests/conftest.py`.
- **Subscription uniqueness**: Mongo stores `intervals_key` (comma-joined intervals) written in `to_mongo` only; unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`. A multikey index on the list would make `["15m","1h"]` and `["15m","4h"]` collide.
- **Validation**: one function `check_strategy_inputs(code, intervals, parameters)` beside the registry, used by subscription create, subscription edit and backtest run. Unsorted or duplicate interval lists are 422, never silently sorted. Defaults live on `IStrategyService.DEFAULTS: ClassVar[dict]`.
- **Backtest results** keep the top-level `interval` = entry interval, so the existing index and rail filter stay.
- **Compare view** keeps its cap of 3.
- **Prod migration**: before the D-2 push, one idempotent script, re-run before every push attempt, adds `intervals`, `intervals_key` and `parameters` (written as `{"$literal": {}}` inside the update pipeline) to legacy subscriptions and drops `ix_subscriptions_dedup_triple`. Legacy backtest runs are not migrated (all are STF and Phase 17 deletes them). The rollback drops `ix_subscriptions_dedup_intervals`. No compatibility code and no index-drop code in `src`.
- **1d comparison**: after one week, compare the stored cascaded 1d bars with bars fetched fresh from Exness (`ExnessAdapter.fetch_ohlcv`), because the cascade overwrites the stored REST bar.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one fresh worker per phase. File order is execution order.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`. Every Verify is one self-contained command run from there. The shell keeps no variables between commands.
- **Reports** go to `plans/261101-0843-stf-to-mtf-foundation/reports/phase-NN-<slug>.md`. Each phase writes its own report and ends it with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git rev-parse HEAD` equals `git rev-parse origin/develop` (Phase 01 pushes the plan first); (3) the previous phase report exists and ends with `Result: PASS`; (4) any phase-specific lines. A resumed phase may show its own task files as uncommitted, and `HEAD` may be ahead of `origin/develop` by its own unpushed commits when `origin/develop` is not ahead of `HEAD`; each phase entry gate states that exception. A miss is not a failed verification: edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Every `develop:master` push is an [ASK]. **[USER]** = the owner acts and replies with the stated token.
- **Search** uses `git grep` (`rg` is not installed in Git Bash): `git grep -n -i -E "<pattern>" -- <paths> ':!plans' ':!docs/journals'`; counts pipe to `wc -l`.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the tail line contains `4 failed` and `4 errors`, and the count prints `0`. About 109 setup errors mean Docker is down, not a code failure.
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` exits 0. When web files changed, in `web/`: `npx tsc -b` exits 0 (from Phase 04 on), `npm run lint` reports `0 errors`, `npx vitest run` exits 0. If only the metric ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the phase report; never pad or split code to satisfy it.
- **CLOSE** (end of every code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references); push `develop` with the Ops recipe; then `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`. Commits that touch only `**/*.md` trigger no CI.
- **No plan ids**, phase numbers, decision codes or finding codes in code, comments, test names, log events or commit messages.
- **Code** follows `CLAUDE.md`: no docstrings (WHY goes in a `#` or `//` comment), a flow reads in at most 3 files, at most 2 hops to I/O, a new class/flag/config key needs a second real caller today, delete dead code in the same change, log level by frequency (per-bar logs are DEBUG), UUIDv7 ids, repositories only in `core.infra.persistence.repositories`, routes use `FromDishka` + `DishkaRoute`.
- **Strategy-agnostic UI**: `git grep -n -i -E "triple[ _-]?screen|force[ _-]?index|elder" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0` at the end of every phase from 11 on (the generic MACD chart indicator in `web/src` is not strategy-specific and is allowed). Triple Screen names live only in its strategy file, its tests and the registry entry.
- **Secrets** never go on a command line or into the repo. Prod Mongo reads and admin calls run as a Python script inside the `api` container (PRODPY).
- **Failure Protocol**: each phase file carries the literal block below. A failed Verify stops the phase and goes to `kongming`; a `NOT_YET` exit does not.

## Ops recipe (each phase inlines what it needs)

- SSH: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`; then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit.
- Compose on the VPS: `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`; services `api`, `worker`, `trader`, `web`.
- **PRODPY f**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py'`. Scripts read Mongo and the admin token through `pocketquant.core.config.get_settings()`; they never print a secret.
- Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; a release is `develop:master` in the same command and is always an [ASK]. Check: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. Never print a token.
- Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Wait `sleep 15` before looking up a run id.
- Prod logs are console format with ANSI colours: strip with `sed 's/\x1b\[[0-9;]*m//g'` and parse `key=value`.
- Every deploy records `free -m` on the VPS before and after in the phase report.

## Phases

| # | Phase | Deploy | Depends on | Status |
|---|---|---|---|---|
| 01 | [Spike A: worktree, cascade-lag measurement, subscription key, context in three paths, backtest cost](./phase-01-spike-a-data-path.md) | none | — | Complete |
| 02 | [Spike B: paper EXIT, resting stop, manual action, snapshot to UI, Exness spec; go/no-go table](./phase-02-spike-b-money-path-and-ui.md) | none | 01 | Complete |
| 03 | [1d cascade for session calendars](./phase-03-1d-cascade-session-calendars.md) | D-1 [ASK] | 02 | Complete |
| 04 | [Web gate: fix `tsc`, add the CI web job](./phase-04-web-gate.md) | none (CI) | 03 | Complete |
| 05 | [Delete STF code, tests, docs, web comments; shared test doubles](./phase-05-delete-stf-code.md) | none (CI) | 04 | Complete |
| 06 | [Subscription contract: intervals, parameters, edit, defaults, reload](./phase-06-subscription-contract.md) | none (CI) | 05 | Complete |
| 07 | [Higher-timeframe context: live and warm-up](./phase-07-htf-context-live-and-warmup.md) | none (CI) | 06 | Complete |
| 08 | [Backtest intervals, real sandbox wiring, backtest-path context test](./phase-08-backtest-intervals-backend.md) | none (CI) | 07 | Completed |
| 09 | [Capabilities in paper: stop entry, EXIT, risk, order SL/TP persistence, restore; architecture doc](./phase-09-capabilities-in-paper.md) | none (CI) | 08 | Completed |
| 10 | [Exness close, pending stop and cancel; only exposure ops behind the live flag](./phase-10-exness-close-pending-cancel.md) | none (CI) | 09 | Completed |
| 11 | [Snapshot ring, manual actions, read endpoints](./phase-11-snapshot-manual-actions-endpoints.md) | none (CI) | 10 | Completed |
| 12 | [Backtest UI: intervals, defaults, labels](./phase-12-backtest-ui.md) | none (CI) | 08 | Completed |
| 13 | [Generic subscription UI: form, row, drawer, actions](./phase-13-subscription-ui.md) | none (CI) | 11, 12 | Completed |
| 14 | [Triple Screen strategy and tests](./phase-14-triple-screen.md) | none (CI) | 09, 11 | Completed |
| 15 | [D-2 release: prod migration, index drop, deploy, post-checks](./phase-15-release-d2.md) | D-2 [ASK] | 03-14 | Completed |
| 16 | [Prod backtests, pick the live set, start one paper subscription](./phase-16-backtests-and-paper-start.md) | none | 15 | Completed |
| 17 | [Observe; one-week 1d comparison; prod STF delete; close](./phase-17-observe-compare-delete.md) | none | 16, D-1 + 7 days | Pending |

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| A1 | Spike go/no-go recorded per piece before the full build | `reports/spike-go-no-go.md` table, every row `go` or an owner [ASK] answer |
| A2 | No STF code | `git grep -n -E "hitnrun2\|engulfing_pullback30\|engulfing_detector\|\"engulfing\"" -- src tests scripts \| wc -l` prints `0`; `STRATEGY_REGISTRY` keys are `["triple_screen"]` |
| A3 | Subscription carries `intervals`, `parameters` and a unique `intervals_key` | Phase 06 tests; prod index list in Phase 15 shows `ix_subscriptions_dedup_intervals` and no `ix_subscriptions_dedup_triple` |
| A4 | No look-ahead in live, warm-up and backtest | Phase 07 and 08 context tests pass: the first entry bar of a new bucket sees the previous bucket's close; the partial current bucket is never served; backtest contexts equal live at every boundary |
| A5 | No per-bar context reads | Phase 07 test: two instances on one symbol cause at most one `find` per (symbol, interval) rollover |
| A6 | 1d cascade correct for one week | Phase 17: `mismatches=0 repair_1d=0` against fresh Exness 1d bars |
| A7 | Stop entry, strategy EXIT, manual close and manual cancel work in paper | Phase 17 observations with order or trade ids |
| A8 | Exness pending placement is fenced by the live flag; close and cancel are not (D7) | Phase 10: a `LIVE_TRADING_DISABLED` test for `placePendingOrder` passes, and tests show `closePosition` and `cancelPendingOrder` are sent while the flag is off |
| A9 | Snapshot visible and changing in the UI | Phase 16 ring has at least 2 distinct `bar_start`; Phase 13 and 17 [USER] tokens |
| A10 | Six backtests comparable | Phase 16 metrics table with 6 run ids and the compare URLs |
| A11 | Prod STF and orphan data gone, tracked symbols and bars untouched | Phase 17 re-list prints zero; `tracked_symbols` count unchanged |
| A12 | Gates | FULLSUITE expected red only; `Contracts: 6 kept, 0 broken.`; ratchet exits 0; CI `web` job green |
| A13 | Architecture doc rewritten | Phase 09 `git grep` for "SL/TP only" and "One take-profit per entry" in `docs/` prints `0` |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | `sync_1m` runs late (worker handover, slow REST) and a partial previous bucket is cached for one window | L x H | Live reads happen at least one entry step after the bucket end; the existing data-lag monitor; stated as negative knowledge in `docs/system-architecture.md` |
| R2 | Subscribing `on_order_update` for every broker double-processes paper immediate fills | M x H | `OrderStatus.PENDING` guard plus a test asserting exactly one `OrderFilledEvent` |
| R3 | Starting the position tracker in backtests changes outcomes of old configurations | M x L | Old runs keep stored results; backtest now rejects entries against an open position like live |
| R4 | Exness pending-fill link field is unverified against the venue | H x M | Live stays disarmed; tested with fakes; negative knowledge recorded; out of scope by C13 |
| R5 | A venue pending stop survives a trader restart and a pause on the Exness side | M x M | Takeover cancels stored PENDING orders; the runbook says to cancel venue pending stops before a pause; negative knowledge recorded; live stays disarmed |
| R6 | Paper stop fills from next-bar high/low are optimistic | H x L | Stated approximation (advice A-3) |
| R7 | The old unique index or legacy documents break D-2 startup | M x H | Phase 15 migration before the push; rollback deletes new-shape subscriptions before re-rolling the old image |
| R8 | A wrong delete filter is unrecoverable (no backup) | L x H | Exact `_id` lists, orphans listed separately, two explicit owner yeses, `deleted_count` asserted per collection |
| R9 | Code-metric ratchet has zero headroom | H x L | Raise it in its own commit (Conventions) |

## Unresolved

1. The Exness field that links a pending-order fill deal to its order is unknown until Phase 02 reads the spec; if the spec does not name it, Phase 10 records it as negative knowledge and tests with the fakes only.
2. Settled: no freshness column (D9).

## Failure Protocol (copied verbatim into every phase file)

```markdown
## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
```

## Red Team Review

### Session — 2026-11-01
**Findings:** 15 groups after merging 37 raw findings from four reviewers (15 accepted, 2 raw findings rejected).
**Severity breakdown:** 1 Critical, 10 High, 4 Medium.
Details, evidence and the owner decisions D7-D9 taken during adjudication: `reports/red-team-adjudication.md`; raw reviews `reports/red-team-{security,failure-mode,assumptions,scope-critic}.md`.

| # | Finding | Severity | Disposition | Applied to |
|---|---|---|---|---|
| 1 | Resting stops outlive their owner (takeover, stop, lost lease, edit) | Critical | Accept | plan.md, 02, 09, 10, 14 |
| 2 | EXIT blocked by entry-only skips; strategy drops its state on rejection | High | Accept | 09, 14 |
| 3 | Manual close after takeover fills at the entry price | High | Accept | 11, 17 |
| 4 | Second close reverses a position | High | Accept | 09 |
| 5 | Failed cancel blocks the close | High | Accept | 09, 11 |
| 6 | Pause and loss cap do not stop a resting stop | High | Accept | 09, 10 |
| 7 | Queued real-money action cannot be withdrawn | High | Resolved by D7 | plan.md, 10, 11, 13 |
| 8 | Snapshot `pending` and `/orders` shapes differ across C7, 11, 13 | High | Accept | 11, 13 |
| 9 | Missing callers make Verify steps unpassable; parameter type checks | High | Accept | 06, 08, 09 |
| 10 | Spike B tests the rejected trigger placement | High | Accept | 02 |
| 11 | Corrupted Exness doc bullet; go-live warning missing | High | Accept | 10 |
| 12 | Backtest SL skipped on EXIT and stop-fill bars | Medium | Accept | 09 |
| 13 | D-2 rollback and resume holes; live-off check in the wrong container | Medium | Accept | 15 |
| 14 | Verification gaps (warm-up snapshot, data coverage, 5m cost, INFO per bar) | Medium | Accept | 09, 16, 17 |
| 15 | Unrequested or duplicated scope (web interval map and validation, run migration, test doubles, freshness, stale Open issues) | Medium | Accept | 05, 06, 08, 09, 11, 12, 13, 14, 15 |

### Whole-Plan Consistency Sweep — 2026-11-01

**Checks run:** read plan.md and all 17 phase files; built a seam table of every name, field, route, signature, fixture, report key and file one phase consumes from another; grepped all files for superseded terms (`ProbeStrategy`, `_LongThenShort`, freshness column, V1/V2 or "versions", handover-kept stops, `{side, stop_price`, backtest-run migration, close/cancel behind the live flag, four backtest runs, `updated_at` final check, 45 s lag, `reduce_only`); checked every entry gate against the previous phase's report name and commits, and every Verify count against what earlier phases create. Behavioural claims a seam depends on were re-checked on `e4a998b8` (enum values, the in-flight guard, `reconcile.unknown_template`, list-route fields, order and position Mongo keys).

**Verified seams (brief):** `ScriptedStrategy` / key `"probe"` / `probe_registry` (05) through 06, 08, 09, 11, 14; `SCRIPT` ClassVar + instance `script` (08) used identically by 09; `snapshots` (11). `check_strategy_inputs`, `DEFAULTS`, `intervals_key`, `ix_subscriptions_dedup_intervals`, PATCH `/subscriptions/{sub_id}`, error codes, mutation guard 17 → 18 (06) → 20 (11). `StrategyConfig.intervals` (06) gated by 07. `bar["context"]` (07) consumed by 08 and 14; context test counts 7 → 9 (07) → 11 (08). `RunBacktestCommand.intervals` and the 422 `error.message` path (08) used by 12, 14, 16; the list route already returns `parameters`. `NoStoredBars` importers 18 → 15 and five `BacktestConfig(` sites match HEAD. `fill_resting_stops(event, running)`, `close_position(..., *, reason, deadline=None)`, `pending_stop`, `_cancel_stop`, order `sl_price`/`tp_price` (09) used by 10, 11, 13, 17; `def close_position` count 3 for the Phase 10 gate. The engine answers an in-flight EXIT with `on_order_rejected("inflight")` through `_notify_rejected` (HEAD `strategy_app_service.py:407-420`), as 09 and 14 assume. `_EXPOSURE_OPS` (10). `manual_action`, `manual_action_outcome {action, outcome, at}`, ring entry keys with `interval: null` for manual records, `pending {side, price}` with `side` = `"buy"`/`"sell"`, `/orders` row keys, `has_price`, `require_admin_token` on five reads, `position.unrealized_pnl` (11) match the 13 types and the 15/16/17 scripts. Report keys `d1_deployed_at=` (03 → 04, 15, 17), `## Exness spec` (02 → 10), `d2_pushed_at=` (15 → 16), `paper_sub_id=` and `paper_started_at=` (16 → 17). Triple Screen `DEFAULTS` has 8 keys (15 `params=8`) and needs 36 top bars (16). Route prefixes `/api/v1/strategies`, `/api/v1/subscriptions`, `/api/v1/backtest` match HEAD. No superseded term survives outside "dropped" or "superseded" statements.

**Changes made:**
- phase-07, phase-08: entry gate states the resume exception for lines 1-2 (plan.md Conventions requires every phase gate to state it).
- phase-09, phase-10, phase-11: the resume sentence also covers `HEAD` ahead of `origin/develop` by the phase's own commits.
- phase-09: `REASON_STRATEGY_EXIT = "strategy_exit"` stated; Phase 10's tests and Phase 17's log grep depend on the value.
- phase-11: `list_symbols` position `direction` is `p.side.value.upper()` (`PositionSide` values are lower case; Phase 13 types expect `LONG`/`SHORT`); the 409 test checks `error.code`; the in-flight outcome test names how to make a paper engine see an in-flight order.
- phase-13: the Task 13.1 key-copy grep names the Phase 11 functions (`get_subscription_snapshot`, `get_subscription_orders`, `_record_snapshot`) instead of the non-existent `get_snapshot`/`list_orders`.
- phase-14: readings `value` is `None` only while warming up; `x or None` would turn the asserted `0.0` into `None`.
- phase-15: `reconcile.unknown_template` is logged once per subscription (so `4`), not per code; the owner-decision line no longer says D3-D5 shipped in Phases 06-13.
- phase-17: `D11`/`D12` relabelled as synthesis D11/D12 (plan.md owner decisions end at D9).

**Contradictions found and resolved** (plan.md design-verdict wording aligned to the phase files by the planner on 2026-11-01; these are planner verdicts, not owner decisions):
1. Verdict "Cache" says `(window_start, bars)`; Phase 07 stores `(window_start, bars, complete)`. Same behaviour as the verdict's miss rule.
2. Verdict "Warm-up" says it waits "whenever `now.second < _WARMUP_READY_SECOND`"; Phase 07 waits only when stored entry bars exist (`... and bars`). This narrows the verdict literally; flagged by the scope critic, not settled in `reports/red-team-adjudication.md`.
3. Verdict "Manual action" says `manual_action(sid, action)` "returns False" while queued; Phase 11 returns `None` as the queued value and a `str` outcome otherwise. Same rule, different sentinel.
4. Verdict "Resting stop trigger order" names `fill_resting_stops(event)`; Phase 09 passes `running` as a second argument to implement "acts only for running instances". Wording only.

**Unresolved:** none. Phase 17's open-position count now accepts 0-2, since an STF paper position may close on its SL or TP before the delete.

## Validation Log

### Session 1 — 2026-11-01
Questions asked during synthesis and red-team adjudication: 12 (asked in Vietnamese, recorded in English as D1-D9 above, plus the red-team "apply all" confirmation).
- **Verification:** four red-team reviewers fact-checked paths, symbols and flows in every phase (`reports/red-team-*.md`); the consistency sweep re-checked every cross-phase seam on `e4a998b8`. `[UNVERIFIED]` tags remaining: the Exness pending-order field names in Phase 10 (resolved by Phase 02 from the spec, fallback recorded), and the `$literal` empty-object write in Phase 15 (checked by the migration's own Verify).
- **Decisions confirmed:** D1-D6 before writing phases; D7 after the owner asked to re-check the broker close behaviour (spec read 2026-11-01); D8, D9 during adjudication.
- **Propagation:** applied to the phase files by the red-team editors and the consistency sweep.
