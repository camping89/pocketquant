---
title: "Exness-only data, api/worker/trader split, zero-downtime trader handover"
description: "Delete TradingView/CME, fix the single-process live path, then split one image into lease-holding api/worker/trader services with a bar-boundary trader handover."
status: pending
priority: P1
effort: 6.5d engineering + 14d paper observation
branch: develop
tags: [exness, tradingview-removal, parallel-runtime, lease, zero-downtime, live-safety]
created: 2026-10-28
---

# Candidate 1 (lens: KISS, smallest diff)

Labels: **[V]** I read it at the cited `file:line` on `develop` @ 453e8e90 today. **[I]** my inference. **[UNVERIFIED]** I could not confirm it. All times UTC.

## 1. Overview

**Outcome.** One host runs `api`, `worker` and `trader` from one image. `worker` and `trader` each hold a Mongo lease; a `trader` without the lease is in standby and sends no order. TradingView, the CME calendar, `ES1!/NQ1!/YM1!:TRADINGVIEW`, subscription `01a178ef` and their data are gone. Exness is the only live venue and the only FX/metals/CFD data source; Binance stays data + paper. A 1m entry reaches Exness within about 2 s of bar end. A deploy restarts every role with no missed bar and no missed order.

**Constraints.** Owner decisions D1-D24 (brainstorm report + evidence packet) and `CLAUDE.md` limits: a flow reads in ≤3 files, ≤2 hops to I/O, a new class/flag/config key needs a second real caller today, dead code is deleted in the same change, log level = frequency, English only. No free-threaded Python, no `--workers N`, no Redis Streams, no shared pacer, no Mongo replica set. The two `CLAUDE.md` rules are rewritten (D16), not silently broken.

**Non-goals.** A trader per venue; a process pool or symbol sharding; deterministic order ids (H1b); retrying an order after a 429; moving backtests to the worker; keeping ES history; the CME bisect rewrite; US indices (D22/D23: Phase 4 of the brainstorm is dropped).

**KISS choices this candidate makes (and why).**
- One `trading_until` timestamp on `StrategyAppService` is the only standby switch: the lease loop writes it, `_process_signal` and broker connect read it. No standby flag elsewhere.
- Direction restore uses one base-class method `IStrategyService.restore_direction` with two callers (strategy start, takeover). No per-strategy code.
- Gap detection is one rule in `BarAppService` (tick silence over 60 s of trading time, plus the restart seed rule) carried as one `gap` field on `BarCompletedEvent`, plus one successor check in `StrategyAppService`.
- Orders get their own `_RequestPacer` instance (no new class); the priority heap is then deleted.
- The cutover from `app` to three services is done in two deploys so it needs no special trading logic: Phase 07 ships leases inside the single `app`; Phase 08 starts the three services in standby next to it and then stops `app`.

### Acceptance criteria (brainstorm §4 with D19-D24 applied; Indices row removed)

| Area | Criterion |
|---|---|
| Stalls | `/health` of every role reports `role`, `lease` and `event_loop_lag_max_s`. Trader: 0 `event_loop.lag` WARNING lines per day (threshold 0.5 s), including 00:00, 03:00, 04:00, 12:00Z. After TV removal `sync_integrity` p50 < 10 s and `sync_repair` p50 < 120 s over 7 days of `job_history`. 0 "Error notifying listener" lines; `skipped_max_instances` rows appear when a run is dropped. |
| Parallelism | `docker ps` shows `api`, `worker`, `trader`. `leases` holds exactly one unexpired owner each for `worker` and `trader`. A second `trader` run for 10 min logs `trader.standby`, sends 0 orders, makes 0 `positions`/`orders` writes, and runs no backtest sweep. A second `worker` starts no scheduler (`scheduler.started` count stays 1). |
| TV removal | The repo grep in Phase 03 Task 3.6 returns 0 hits. Mongo `tracked_symbols` and `bars` have 0 rows matching `/TRADINGVIEW$/`; subscription `01a178ef-5027-73ba-a98e-b7d6de8e2cc9` is gone. `lint-imports` prints `Contracts: 6 kept, 0 broken.` (see Unresolved 1: the 2 deleted contracts exist only for the removed packages). |
| C1 | CI: a pause through the `api` route makes the trader's next open refused. A failed store read refuses the open (fail closed). The pause route returns an error when the store write fails. `Safeguards.entries_paused` no longer exists. |
| C2 | CI: of two lease contenders only one acquires. A lost renewal clears `trading_until`, stops strategies and asks the process to exit. |
| H1 | CI: a second signal for a subscription is rejected while an `_inflight` open exists for it. |
| H2 / D10 | CI with a fake clock: a 1m bar 11 s late (15m 61 s, 1h 121 s) skips the entry and logs exactly one `strategy.entry_skipped reason=stale`. The paper SL/TP path still runs on that bar. |
| H3 / D10 | CI: a non-successor bucket, or a bar with tick silence over 60 s of trading time, logs `reason=gap` and skips the entry. Prod: `strategy.entry_skipped` count reported per week. |
| M1 / 1m latency | CI: with fresh caches the open path makes exactly 1 REST call (`openPosition`). Prod paper: `live.signal_latency` p95 of `t5_ms` ≤ 1,000 on 1m Exness symbols. Before re-arming live: D12 canary, first 20 live min-lot entries, p95 `t6_ms` ≤ 2,000. |
| M2 / D21 | CI: two subscriptions signal on one bar; their check sections run one after the other and their `openPosition` calls overlap (bar lock not held). A close event marks the loss-cap cache stale; the next open re-reads synchronously or refuses. |
| M3 / D9 / D11 | CI: after a restart with a LONG mirror row, the strategy's direction is LONG. An opposite entry is rejected and never becomes a close; `closePosition` no longer exists in `src/`. hitnrun2 can signal on the first live bar after a restart. |
| D13 | CI: after takeover a paper broker's balance = initial balance + Σ `trades.pnl` of its subscriptions, and its open positions equal the mirror rows. |
| Handover (D8) | Over 10 deploys in market hours, every `trader.lease_released` has `inflight=0` and a timestamp inside [B+0 s, B+30 s] of a 1m boundary B. `handover_gap_ms` ≤ 2,000; `takeover_ms` ≤ 5,000. 0 `reason=gap` skips on the first bar after a handover. A probe through nginx every 0.5 s during each deploy sees 0 non-200 answers. |
| Rate budget (D19) | 0 terminal `exness.rate_limited` on `openPosition`. `exness.rate_limited_retry` ≤ 72 per 7 days. |

## 2. Conventions and ops recipe

- Ops recipe: reuse `plans/261019-1957-exness-go-live/plan.md` "Ops recipe" (SSH key copy, token-URL push, `GH_TOKEN` on every `gh` call, `sleep 15` before a run id lookup, `11-verify.sh` verdict grep). Every `develop:master` push is a deploy: **[ASK]** the owner before each one. Delete `.cache/ssh/vps_key` at the end of every phase that used it.
- Container lookup after Phase 08 (no fixed names): `C=$(docker ps -q --filter label=com.docker.compose.project=pocketquant-prod --filter label=com.docker.compose.service=<api|worker|trader> --filter status=running | head -1)`. Before Phase 08 the backend is `pocketquant-app`.
- Mongo read inside a backend container: `docker exec -i $C python -c "from pymongo import MongoClient; from pocketquant.core.config import get_settings as g; s=g(); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]; ..."` (pattern from go-live Phase 11).
- Tests: Docker Desktop must run. Full suite: `uv run python -m pytest tests/ -q 2>&1 | tail -1`. **Expected local red is exactly `4 failed` and `4 errors`, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.** Check: `uv run python -m pytest tests/ -q 2>&1 | grep -E "^(FAILED|ERROR)" | grep -vcE "test_utc_runtime_guard|test_cron_trigger_timezone"` prints `0`. Import contracts: `uv run lint-imports | tail -1`. Ratchet: `uv run python scripts/code_metrics.py --ratchet; echo $?` prints `0` (raise `[tool.code-metrics]` in its own commit rather than pad code).
- Deploy windows: never 23:50-00:50, 02:50-04:50, 11:50-12:50 UTC.
- Code comments, test names and commits carry no phase numbers or finding codes.

## 3. Phases (file order = run order)

| # | Phase | Effort | Depends on | Deploys |
|---|---|---|---|---|
| 01 | Spike: two ticks sessions on one key (D15/D24) | 2h | none | none (read-only prod probe) |
| 02 | Observe and stop lying: loop-lag probe, skip listener, C3 docstring, `python:3.14-slim` | 3h | none | D-1 |
| 03 | Delete TradingView and the CME calendar, code and prod data | 1d | 02 | D-2 |
| 04 | Exness order path: C1, H1, M2, M1 caches, order pacer, M3/D11 | 1d | 03 | none |
| 05 | Bar building: timer close, gap flag, Redis seed | 0.5d | 04 | none |
| 06 | Strategy runtime: H2/H3 guards, D21 tasks, D9 warm-up, D13 paper restore, `live.signal_latency` | 1d | 05 | D-3 |
| 07 | Roles and leases in one process: `APP_ROLES`, worker lease, trader standby/handover, D18 heartbeat, `CLAUDE.md` rules | 1d | 06 and 01 = PASS | D-4 |
| 08 | Compose split, nginx re-resolve, rolling deploy, one-time cutover, rate fractions | 0.75d | 07 | D-5 (cutover) |
| 09 | Docs and cleanup | 0.25d | 08 | D-6 (= deploy 1 of 10) |
| 10 | Prod verification: 10 handover deploys, second-copy tests, 14 days paper | 14d calendar | 09 | 9 more |
| 11 | Re-arm live gate (pointer to go-live phases 11-12 + D12 canary) | per go-live | 10 | per go-live |

---

## Phase 01 — Spike: two ticks sessions on one key (D15/D24)

**Entry gate:** a weekday, outside 21:00-22:05Z and the deploy blackout windows; prod `app` running. D17: no approval window needed (`EXNESS_LIVE_TRADING=false`). This phase runs before any handover code.

**Design facts.** Exness WS limits are per account per node, `max_active_connections` 10 [V spike journal `docs/journals/2026-10-13-exness-api-spike.md:37`]. The trader holds two sessions (ticks, events). A second ticks session uses a third. Prod writes `quote:latest:{symbol}` on every tick [V `quote_app_service.py:70-71`, `constants.py:25`], so its freshness measures whether the second session disturbs the first.

### Task 1.1 — Write the throwaway spike script (not committed)
- **Goal:** one script that measures prod quote freshness and runs a second ticks session.
- **Target files:** `.cache/spike/two_tick_sessions.py` (gitignored `.cache`; never committed).
- **Steps:**
  1. Settings: `get_settings().model_copy(update={"exness_rate_fraction": 0.2})`; build `ExnessClient(settings)` and `ExnessQuoteAdapter(client)` (`core/infra/exness/exness_quote_adapter.py:32-86`).
  2. Segment A (10 min, no WS): every 1 s read `quote:latest:{EURUSD,XAUUSD,BTCUSD}:EXNESS` from Redis, record `now - timestamp` per symbol.
  3. Segment B (15 min): run the adapter, subscribe the same three symbols, record every own tick; keep sampling Redis.
  4. Segment C (10 min): close the adapter, keep sampling Redis.
  5. Print one JSON line: per segment and symbol `p99_quote_age_s`, own-session `ticks` and `max_gap_s`, plus the UTC window.
- **Success criteria:** the script runs locally with `uv run python -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" .cache/spike/two_tick_sessions.py` and exits 0.
- **Verify:** that command exits `0`.

### Task 1.2 — Run it inside the prod backend and read prod logs
- **Goal:** measure interference on the real account.
- **Steps:** `ssh ... 'docker exec -i pocketquant-app python -' < .cache/spike/two_tick_sessions.py > .cache/spike/result.json`; then count prod WS failure lines over the same window: `ssh ... "docker logs --since <A_start> --until <C_end> pocketquant-app 2>&1 | grep -cE 'exness_ws\.(reconnecting|circuit_breaker_open|stale_detected|connection_failed)'"`.
- **Success criteria (PASS = all four):** (1) prod WS failure count = 0; (2) segment B `p99_quote_age_s` ≤ segment A value + 1.0 for every symbol; (3) own-session `max_gap_s` ≤ 10 for EURUSD and XAUUSD; (4) 0 `exness.rate_limited` lines in the window.
- **Verify:** `cat .cache/spike/result.json` and the grep count; compare against the four pass conditions. Record PASS or FAIL with the numbers in `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` (a stateful record, allowed).

### Task 1.3 — Gate decision
- **Goal:** fix F1 for Phase 07.
- **Steps:** PASS → F1-A (hot standby with tick overlap) stands. FAIL → **[ASK]** the owner (D24: second Exness account, or another fallback); Phases 02-06 continue; Phase 07 does not start until the owner answers and this plan is amended.
- **Success criteria:** the record states PASS, or the owner's fallback decision is recorded.
- **Verify:** `grep -cE "^Result: (PASS|FAIL)" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` prints `1`.

**Rollback:** kill the script; nothing is deployed. Delete `.cache/ssh/vps_key`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 02 — Observe and stop lying

**Entry gate:** none. Deploy outside the blackout windows.

### Task 2.1 — Skip listener reads the right field
- **Goal:** `EVENT_JOB_MAX_INSTANCES` rows get recorded instead of raising.
- **Target:** `core/infra/scheduling/scheduler.py:95-99` `_on_skip`. APScheduler 3.11.2 emits `EVENT_JOB_MISSED` with `scheduled_run_time` and `EVENT_JOB_MAX_INSTANCES` as a submission event with `scheduled_run_times` [V installed package via `inspect`; evidence packet].
- **Steps:** for `EVENT_JOB_MAX_INSTANCES` pass `event.scheduled_run_times[-1]`; for `EVENT_JOB_MISSED` keep `event.scheduled_run_time`.
- **Tests to write:** `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py`: a fake submission event with `scheduled_run_times=[t1, t2]` calls `record_skip(scheduled_run_time=t2, status="skipped_max_instances")`; a missed event records `status="missed"`.
- **Verify:** `uv run python -m pytest tests/core_test/infra/scheduling/test_scheduler_skip_listener.py -q 2>&1 | tail -1` shows `passed` and no `failed`.

### Task 2.2 — Correct the scheduler docstring (C3)
- **Target:** `scheduler.py:1-10` and `:53-55` claim shared-jobstore coordination [V].
- **Steps:** replace with: "Exactly one process runs the scheduler. Sharing the Mongo job store between processes is unsupported (APScheduler 3.x FAQ): jobs run twice or are skipped."
- **Verify:** `grep -c "first to update next_run_time wins\|distributed coordination" src/pocketquant/core/infra/scheduling/scheduler.py` prints `0`.

### Task 2.3 — Event-loop lag probe
- **Goal:** `event_loop_lag_max_s` on `/health`, one WARNING per lag above 0.5 s.
- **Target:** `app/main_extensions.py` (new `start_loop_lag_probe(app)` next to `start_quote_feed`, `:185`), health route `:372-380`, `app/main.py` lifespan (start after `assert_utc_runtime`, cancel in `finally` with `_cancel`).
- **Steps:** a task loops `t = loop.time(); await asyncio.sleep(0.5); lag = loop.time() - t - 0.5`; keeps the max of the current and previous 60 s bucket on `app.state.loop_lag_max_s`; logs `event_loop.lag lag_s=...` at WARNING when `lag > 0.5`. The health route adds `result["event_loop_lag_max_s"]`.
- **Tests to write:** `tests/app_test/unit/test_loop_lag_probe.py`: blocking the loop with `time.sleep(0.7)` makes the reported max ≥ 0.5 and emits exactly one `event_loop.lag`.
- **Verify:** `uv run python -m pytest tests/app_test/unit/test_loop_lag_probe.py -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 2.4 — Stable Python image
- **Target:** `deploy/Dockerfile:4,28` `python:3.14-rc-slim` [V].
- **Steps:** change both to `python:3.14-slim`.
- **Verify:** `grep -c "3.14-rc" deploy/Dockerfile` prints `0`.

### Task 2.5 — Gates, push, deploy D-1
- **Steps:** full suite, `lint-imports`, ratchet; commit `fix(scheduler): record skipped runs and expose loop lag`; push `develop`; **[ASK]** then push `develop:master`.
- **Success criteria:** CI green; `11-verify.sh` verdict has 0 failures.
- **Verify:** local red exactly as in §2; `uv run lint-imports | tail -1` prints `Contracts: 8 kept, 0 broken.`; after deploy `ssh ... "docker exec pocketquant-app curl -s localhost:41921/health" | grep -c event_loop_lag_max_s` prints `1`; 24 h later `ssh ... "docker logs --since 24h pocketquant-app 2>&1 | grep -c 'Error notifying listener'"` prints `0`.

**Rollback:** `git revert` the commit and redeploy; no data change.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 03 — Delete TradingView and the CME calendar

**Entry gate:** Phase 02 deployed. Owner already confirmed D1/D4. Prod data goes first (the old code still routes the symbols), then the code.

### Task 3.1 — Stop subscription `01a178ef` (prod)
- **Steps:** admin call (go-live recipe) `POST /api/v1/subscriptions/01a178ef-5027-73ba-a98e-b7d6de8e2cc9/stop` [V route `app/routes/strategy.py:96-102`].
- **Verify:** Mongo read `db.subscriptions.find_one({'_id':'01a178ef-5027-73ba-a98e-b7d6de8e2cc9'})['actual_state']` prints `stopped` within 15 s.

### Task 3.2 — Delete the three symbols through the API (cascade, prod)
- **Steps:** `DELETE /api/v1/market-data/tracked-symbols/ES1%21%3ATRADINGVIEW`, then `NQ1%21%3ATRADINGVIEW`, `YM1%21%3ATRADINGVIEW` [V route `routes/market_data.py:296-310`; cascades bars, sync_status, subscriptions, backtests, live rows, job_history details, cache keys].
- **Verify:** Mongo read prints `0 0 0`: `db.tracked_symbols.count_documents({'symbol':{'$regex':'TRADINGVIEW$'}})`, `db.bars.count_documents({'symbol':{'$regex':'TRADINGVIEW$'}})`, `db.subscriptions.count_documents({'_id':'01a178ef-5027-73ba-a98e-b7d6de8e2cc9'})`.

### Task 3.3 — Delete the TradingView code
- **Target (delete):** `src/pocketquant/core/infra/tradingview/` (6 modules); `scripts/seed_index_futures.py` and its line in `scripts/README.md`; `tests/core_test/infra/tradingview/`; `tests/app_test/unit/test_tradingview_credentialed.py`.
- **Target (edit):** `app/di/adapters.py` (TV imports `:43-45`, client provider and both router entries [explore §1]); `core/domain/market_data/provider_routing_domain_service.py` (`"tradingview"` default); `core/config.py:66-107` TV fields; `core/domain/shared/enums.py` `TradingViewPlan` and capabilities; `app/main_extensions.py:66,275-305` (`_tradingview_credentialed`, TV health entry); `core/infra/market_data/provider_health_check.py`; `engine/market_data/app_services/quote_app_service.py:32-34` (TTL becomes `TTL_QUOTE_LATEST`); `engine/market_data/data_lag_service.py`; `core/domain/market_data/data_provider_port.py` and `realtime_quote_provider_port.py` docstrings; `core/domain/symbol/__init__.py`, `value_objects.py`; `scripts/backfill/binance_bars.py` comment; `pyproject.toml:29-30` (`tvdatafeed`), `:54` direct-reference allowance if only TV needed it, `:160-171` contract; `uv.lock` via `uv lock`.
- **Web:** remove TV branches in `web/src/lib/symbol-format.ts`, `components/chart/trading-chart.tsx`, `components/backtest/backtest-form.tsx`, `components/ticker-widget/ticker-widget.tsx`, `components/data-lag-badge.tsx`, `components/controls/symbol-selector.tsx`, `types/quote.ts`, `types/market-data.ts`, `lib/datetime.test.ts`.
- **Verify:** `rg -il "tradingview|tvdatafeed" src tests web/src scripts pyproject.toml | grep -vc __pycache__` prints `0`.

### Task 3.4 — Delete the CME calendar
- **Target (delete):** `core/infra/calendars/cme_globex_calendar_adapter.py`; `tests/core_test/infra/calendars/test_cme_globex_calendar.py`.
- **Target (edit):** `core/infra/calendars/__init__.py`, `trading_calendar_factory.py` (CME id and branch), `pyproject.toml:13` (`pandas-market-calendars`) and `:142-152` contract; every test that uses the CME calendar only as a fixture switches to the Exness or 24/7 calendar, or loses the CME-only case: `test_cascade_aggregator.py`, `test_integrity_calendar.py`, `test_sync_status_calendar.py`, `test_bar_filters.py`, `test_closed_market_skip_precedes_provider_loops.py`, `test_quote_app_service.py`, `test_sync_jobs_calendar_gate.py`, `test_performance_calculator_calendar_annualization.py`, `test_report_annualization_source.py`, `test_backtest_dispatch_contract_spec.py`, `test_paper_broker_contract_spec.py`, `test_trading_calendar_factory_unseeded_default.py`, `test_provider_health_check.py`, `test_routing_data_provider_adapter.py`, `test_routing_realtime_quote_adapter.py`, `test_symbol_repository_touch.py`, `test_bar_builder.py`, `test_provider_routing.py`, `test_backfill_calendar_stamp.py`, `test_backfill_daily_mode.py`, `test_data_lag_service.py`, `test_ws_subscription_reconcile_logging.py`, `test_contract_spec_wiring.py`, `test_futures_sync_end_to_end.py`, `test_market_data_routing_characterization.py`, `test_bar_app_service_unit.py` (paths from `rg -il` today).
- **Verify:** `uv lock && uv sync` exit 0; `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`

### Task 3.5 — Docs lines
- **Target:** `docs/system-architecture.md`, `docs/deployment.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, `docs/code-standards.md`, `README.md`: delete TV/CME/ES lines (AS-IS, one idea per sentence). Journals under `docs/journals/` are dated records and stay (Unresolved 2).
- **Verify:** Task 3.6.

### Task 3.6 — Gates, push, deploy D-2, memory note
- **Steps:** full suite; commit `refactor: remove TradingView and the CME calendar`; push `develop`; **[ASK]** push `develop:master`. After deploy delete `C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md` and its index line in that folder's `MEMORY.md` (the note says so itself).
- **Verify:**
  1. `rg -i "tradingview|cme_globex|pandas_market_calendars|seed_index_futures" src tests web/src docs pyproject.toml -g '!docs/journals/**' -c | grep -v __pycache__ | wc -l` prints `0`.
  2. Local red exactly as §2; `cd web && npm run build` exits 0.
  3. Seven days after D-2: Mongo read of `job_history` p50 `duration` for `sync_integrity` < 10 s and `sync_repair` < 120 s [field name in `job_history_repository.py` UNVERIFIED; read it before writing the query].

**Rollback:** code: `git revert` and redeploy. Data: not reversible (owner accepted D4).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 04 — Exness order path (single process)

**Entry gate:** Phase 03 merged on `develop`. File ownership: this phase alone edits `exness_broker_adapter.py`, `exness_client.py`, `exness_safeguards.py`, `routes/safeguards.py`, `di/adapters.py`.

**Data flow after this phase.** `submit_order` → `_submit_open` takes `self._open_lock` → pause read from Mongo (fail closed) → H1 check → snapshot gate → loss cap (cache, or synchronous read when stale) → conditions (cached 1 h) → register `_inflight[rid]` → release the lock → `openPosition` on the order pacer. Only the check section is serialized (M2); the HTTP call is not (D21).

### Task 4.1 — C1: the pause lives only in the store
- **Target:** `exness_safeguards.py:24-31` (delete `entries_paused` and `set_entries_paused`); `di/adapters.py:49-59` (drop the load); `exness_broker_adapter.py:98-108` (take `SafeguardsRepository`), `:245-253`; the broker factory wiring in `di/adapters.py`; `routes/safeguards.py:24-49`; the stale comment in `di/services.py` `get_reconcile_service` ("Taking the safeguards also loads the stored entry pause").
- **Steps:** `_presubmit_reason` becomes async and reads `await self._safeguards_repo.load_entries_paused()`; on any exception return `"entries pause unreadable"` and log `exness.order_rejected_presubmit reason=pause_read_failed` (WARNING). Routes: GET returns `{**asdict(safeguards), "entries_paused": await repo.load_entries_paused()}`; POST writes the store and returns the same shape; a store exception propagates (HTTP 500). The pause/resume WARNING log moves into the route.
- **Tests to write:** in `tests/app_test/integration/test_safeguards_api.py`: pause through the route, then an adapter open on the same Mongo is rejected with `entries paused`; a failing store write makes POST return 500. In `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`: a repo whose `load_entries_paused` raises refuses the open.
- **Verify:** `grep -rc "entries_paused" src/pocketquant/core/infra/brokers/exness/exness_safeguards.py` prints `0`; the two test files: `uv run python -m pytest tests/app_test/integration/test_safeguards_api.py tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 4.2 — M3/D11: reject opposite entries; delete the close path
- **Target:** `exness_broker_adapter.py:7` docstring, `:80-88` `_Inflight.kind/position_id`, `:199-214`, `:317-334` (`kind`, `position_id`, `path_params` params), `:497-498` deal-type match, `:543` close branch; `exness_client.py:57` `closePosition` op and `:59` `_ORDER_OPS`; close-path tests in `test_exness_broker_adapter.py`.
- **Steps:** `submit_order`: held and same side → reject `position already open for subscription`; held and opposite side → reject `opposite position open; exits are venue SL/TP` with WARNING `exness.order_rejected_presubmit reason=opposite_side`. Delete everything reached only by `closePosition`. The success handler matches `deal.type == "open"`.
- **Tests to write:** opposite-side entry with a held position is rejected and makes 0 client calls.
- **Verify:** `rg -c "closePosition" src | wc -l` prints `0`; adapter tests pass.

### Task 4.3 — H1 and M2: one open lock around the check section
- **Target:** `exness_broker_adapter.py:216-243` `_submit_open`, `:317-334` `_send_tracked`.
- **Steps:** add `self._open_lock = asyncio.Lock()`. Inside it: presubmit (Task 4.1), then reject if any `_inflight` value has `order.subscription_id == order.subscription_id` (`open already in flight for subscription`), stop-loss check, loss cap, conditions, lots, then `self._inflight[rid] = ...` and `self._pending_ack.add(rid)` (moved from `_send_tracked`). `_send_tracked` keeps the HTTP call and its error handling, outside the lock.
- **Tests to write:** (a) second open for a subscription while the first is in `_inflight` is rejected; (b) two subscriptions on one bar: record entry/exit timestamps of the check section with a fake slow loss-cap read; the sections do not overlap, while two fake `openPosition` calls of 1 s each finish within 1.3 s total.
- **Verify:** adapter tests pass.

### Task 4.4 — M1: cached balance and loss cap
- **Target:** `exness_broker_adapter.py:265-288` `_loss_cap_reason`/`_realized_today`, `:516` `_on_broker_close`, `:472` `_close_missing`, `:656-669` `get_balance`, `connect`/`disconnect` `:137-159`.
- **Steps:** fields `_balance_cache: tuple[float, AccountBalance] | None`, `_realized: tuple[date, float] | None`. A refresh task (started in `connect`, cancelled in `disconnect`) sleeps to second 30 of each minute, then refreshes both (2 data calls). `get_balance` returns the cache if younger than 90 s, else reads. `_loss_cap_reason` uses `_realized` when it is for today's UTC date, else reads synchronously; a failed read refuses (today's behaviour). Every broker close and `_close_missing` sets `_realized = None`. Note: the synchronous fallback costs about 2 data calls (≈2 s at the trader's 0.6 fraction) on the first entry after a close (verifier item 5).
- **Tests to write:** with fresh caches an open makes exactly one client call, `openPosition`; after a close event the next open calls `getDealsHistory` first; if that raises, the open is refused.
- **Verify:** adapter tests pass.

### Task 4.5 — Order pacer lane (needed by D21 and D12)
- **Target:** `exness_client.py:147-195` `_RequestPacer`, `:289-312` `_send_paced`, `:348-356` `_pacer_for`.
- **Steps:** keep one `_RequestPacer` for data ops (strictest data-method rate × 1.2 / fraction) and a second instance for `_PRIORITY_OPS` (`openPosition` and `getOperationStatus` limits × 1.2 / fraction; 4/s and 10/s [V spike journal `:35-36`] → 0.3 s / fraction). Delete the priority heap ordering and the `priority` argument (orders no longer queue behind data). Data + order lanes stay under `global_account_rate` 10/s at fraction 1.0 (1.67 + 3.33 = 5/s) [I].
- **Tests to write:** `tests/core_test/infra/exness/test_exness_client_pacer.py`: an `openPosition` issued while 5 candle calls are queued leaves without waiting for them; two `openPosition` calls are spaced ≥ 0.3 s / fraction.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 4.6 — Gates and commit (no deploy)
- **Steps:** full suite, `lint-imports`, ratchet; commit `fix(exness): store-read pause, single open per subscription, cached pre-order reads`; push `develop`.
- **Verify:** local red exactly as §2; `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; CI run on `develop` concludes `success` (`GH_TOKEN=... gh run list --branch develop --limit 1 --json conclusion -q '.[0].conclusion'`).

**Rollback:** `git revert`; nothing deployed.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 05 — Bar building: timer close, gap flag, Redis seed

**Entry gate:** Phase 04 on `develop`. Only this phase edits `bar_app_service.py`, `bar_builder_domain_service.py`, `core/domain/bar/events.py`.

**Facts.** A bar closes only on a later tick [V `bar_app_service.py:117-132`]; EURUSD max tick gap 4.30 s [brainstorm F2b]. A new builder seeds from Mongo [V `:110-114,180-208`]. `bar:current` is refreshed at most every 0.2 s with `last_update` [V `:24-25,225-236`]. `flush_all_bars` is dead [V `:270-289`, reviewer Low]. The docstrings promise at-least-once [V `:54,149`].

### Task 5.1 — Event and builder fields
- **Target:** `core/domain/bar/events.py:8-22`; `core/domain/bar/services/bar_builder_domain_service.py:61-110`.
- **Steps:** add `gap: bool = False` to `BarCompletedEvent`. Add `gap: bool = False` and `published: bool = False` to the builder.
- **Verify:** `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`

### Task 5.2 — Timer close
- **Target:** `bar_app_service.py` (new `run_close_timer()` started by `QuoteAppService.start` next to the WS task; cancelled with it in `stop_quote_feed`, `main_extensions.py:202-208`).
- **Steps:** loop: sleep to the next whole second + 0.5 s; under `self._lock`, for every builder with interval ≤ 1h, not `published`, and `bar_start + INTERVAL_SECONDS[interval] + 0.5 s <= now`, call `_save_completed_bar` and set `published = True`. In `_process_tick_for_interval`, a tick for a `published` builder's bucket is dropped; a later bucket replaces the builder without publishing it again. 4h/1d/1w keep tick close (DST-length buckets, `:117-119`).
- **Tests to write** (in `tests/app_test/market_data/test_bar_app_service_unit.py`): with no tick after 12:00:59.9, the 12:00 1m bar is published at 12:01:00.5 ± 0.1 by the timer; the 12:01 first tick does not publish it twice; a 4h bar is not timer-closed.
- **Verify:** `uv run python -m pytest tests/app_test/market_data/test_bar_app_service_unit.py -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 5.3 — Gap flag from tick silence (H3, D20 = 60 s trading time)
- **Steps:** keep `_last_tick_at[symbol_key]`. When `tick.timestamp - last > 60 s` and `len(calendar.trading_minutes(last, tick.timestamp)) > 1`, set `gap = True` on every builder of that symbol before processing the tick, and on builders created by this tick. `trading_minutes` interval semantics are [UNVERIFIED]; the test pins them.
- **Tests to write:** 61 s silence inside EURUSD trading hours sets `gap` on the closed and the new 1m bar; the same silence across the 21:00-22:00Z Exness break does not [calendar table: `exness_session_calendar_adapter.py`].
- **Verify:** the bar test file passes.

### Task 5.4 — Seed from Redis, gap-flag an uncovered mid-bucket start
- **Target:** replace `_seed_builder_from_mongo` (`:180-208`) and its call (`:110-114`).
- **Steps:** on first builder creation for a key in this process, read `bar:current:{symbol}:{interval}`. Covering seed = same `bar_start` and `tick.timestamp - last_update <= 1.0 s` → copy OHLCV. No covering seed and `tick.timestamp - bar_start > 1.0 s` → `gap = True`. Keep `_bar_repo` only for `get_current_bar`. Delete `flush_all_bars`. Fix the two "at-least-once" docstrings to "at most once; a restart or feed gap loses or gap-flags bars".
- **Tests to write:** covering seed → open from seed, `gap False`; stale seed (2 s) mid-bucket → `gap True`; first tick 0.4 s after bucket start without seed → `gap False`.
- **Verify:** `grep -c "_seed_builder_from_mongo\|flush_all_bars\|at-least-once" src/pocketquant/engine/market_data/app_services/bar_app_service.py` prints `0`; bar tests pass.

### Task 5.5 — Gates and commit (no deploy)
- **Verify:** full suite red exactly as §2; commit `feat(bars): timer close, gap flag, seed from the live bar`; CI on `develop` = `success`.

**Rollback:** `git revert`; nothing deployed.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 06 — Strategy runtime (single process)

**Entry gate:** Phase 05 on `develop`. Only this phase edits `engine/strategy/strategy_app_service.py`, `strategy_service_interface.py`, `paper_broker_adapter.py`, `position_app_service.py`, `trade_repository.py`, `di/services.py`.

**Facts.** Signals are processed inline under the bar lock [V `strategy_app_service.py:241-270`, `bar_app_service.py:90-92,162`]. `on_start` clears `_open_direction` in all three strategies [V `hitnrun2_strategy_service.py:73`, `engulfing_pullback30_touch_strategy_service.py:93`, engulfing `:74-79`]. hitnrun2 buffers 481 bars [V `:36,60`]. The boot path deletes paper mirror rows [V `position_app_service.py:36-53`, `di/services.py:122-133`]. Paper balance resets [V `paper_broker_adapter.py:98`]. The backtest sandbox builds the same engine [V `backtest_sandbox_app_service.py:136-142`].

### Task 6.1 — Live-only dependencies
- **Target:** `StrategyAppService.__init__` (`:42-66`); `di/services.py:137-161`.
- **Steps:** add optional `bar_repository`, `calendar_factory`, `trade_repository`. DI passes all three; the sandbox passes none. Docstring: "a live engine gets the three repositories; the backtest sandbox gets none and keeps inline order handling". Add `self.trading_until: datetime | None = datetime.max.replace(tzinfo=UTC)` (Phase 07 makes it lease-driven) and `self._signal_tasks: dict[str, asyncio.Task]`.
- **Verify:** `uv run python -m pytest tests/backtest_test -q 2>&1 | tail -1` shows `passed`, no `failed` (backtests unchanged).

### Task 6.2 — H2/H3 entry guards and one latency line
- **Target:** `_on_bar_completed` `:241-270`, `_process_signal` `:323-390`.
- **Steps (live engine only):** `bar_end = bar_start + INTERVAL_SECONDS[interval]`; `age = get_current_time() - bar_end`; budgets `{1m: 10, 15m: 60, 1h: 120}` s (D10). Keep `_last_bar_start[strategy.id]`; non-successor = `len(calendar.trading_minutes(last_end, event.bar_start)) > 0`. Compute the signal always (state stays warm). If a signal exists and `age > budget` → WARNING `strategy.entry_skipped reason=stale age_s=...`; elif `event.gap` or non-successor → WARNING `reason=gap`; then `on_order_rejected(reason)` and stop. Paper SL/TP runs in the broker's own handler, untouched. After submit, one INFO `live.signal_latency` per signal: `subscription_id`, `bar_start`, `t3_ms` (publish − T0), `t4_ms` (signal), `t5_ms` (just before `order_app_service.submit`), `t6_ms` (`result.submitted_at` − T0).
- **Tests to write:** `tests/engine_test/test_strategy_entry_guards.py` with `set_simulation_time`: 1m 10 s late trades, 11 s late skips with exactly one `reason=stale`; 15m 61 s, 1h 121 s skip; a paper position's SL is still hit on the stale bar; `gap=True` and a non-successor bucket skip with `reason=gap`; one `live.signal_latency` per traded signal.
- **Verify:** `uv run python -m pytest tests/engine_test/test_strategy_entry_guards.py -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 6.3 — D21: orders leave the bar lock
- **Steps (live engine only):** `_on_bar_completed` computes signals inline, then runs each `_process_signal` as a task held in `_signal_tasks[strategy.id]`; if that subscription's previous task is not done, skip with WARNING `strategy.entry_skipped reason=inflight`. The task logs errors as today (`strategy_on_bar_error`) and notifies rejection. The sandbox keeps `await` inline. Expose `pending_signal_count`.
- **Tests to write:** three live subscriptions signal on one bar with a broker whose submit sleeps 1 s: `_on_bar_completed` returns in < 0.1 s and all three submits start within 0.1 s.
- **Verify:** test file passes.

### Task 6.4 — D9 warm-up and direction restore
- **Target:** `strategy_service_interface.py:35-38` (add `self._open_direction = None` and `restore_direction(direction)`); `start_strategy` `:139-154`; new `take_over()` on `StrategyAppService`.
- **Steps:** in `start_strategy`, after `on_start`: replay `bar_repository.find(symbol, interval, end_date=now, limit=500)` oldest first through `on_bar_completed`, discarding signals; then `restore_direction(LONG/SHORT/None)` from `position_app_service.get(id)`. Broker connect stays at `:149-150` but only when `trading_until` is in the future. `take_over()`: `await order_app_service.load_pending_orders()`, `await position_app_service.load_open_positions()` (replaces its dict; no paper delete), restore paper brokers (Task 6.5), `restore_direction` for every running strategy, connect brokers of running strategies.
- **Tests to write:** `tests/engine_test/test_strategy_restart_restore.py`: a LONG mirror row → direction LONG after start; hitnrun2 with 481 stored bars returns a signal on the first live bar that fits its rule (assert `len(strategy._closes) == 481` before the bar, no signal when the buffer is short).
- **Verify:** test file passes.

### Task 6.5 — D13 paper restore and boot-path move
- **Target:** `paper_broker_adapter.py` (new `restore(positions, realized_pnl)`: `_balance = _initial_balance + realized_pnl`; positions keyed `f"{sub}:{symbol}"` as `:378`); `trade_repository.py` (new `sum_pnl(subscription_ids) -> float`, one `$group`); `position_app_service.py:31-53` (`start` subscribes only; `load_open_positions()` loads all open rows); `di/services.py:115-133` (no load at build); `app/main.py:63` (call `take_over()` after `bootstrap_live_instances`).
- **Tests to write:** two paper subs on one broker, trades pnl +50 and −20, one open mirror row → balance = initial + 30 and one restored position whose SL fires on the next bar.
- **Verify:** `uv run python -m pytest tests/engine_test -q 2>&1 | tail -1` shows `passed`, no `failed`.

### Task 6.6 — Gates, NTP check, deploy D-3
- **Steps:** full suite, `lint-imports`, ratchet; commit `feat(strategy): entry guards, concurrent opens, restart restore`; push `develop`. Check VPS clock sync (D20): `ssh ... "timedatectl show -p NTPSynchronized --value"`. **[ASK]** push `develop:master`.
- **Verify:** NTP prints `yes` (else STOP: the timer close depends on it); local red as §2; after deploy, 2 h of logs show `ssh ... "docker logs --since 2h pocketquant-app 2>&1 | grep -c live.signal_latency"` ≥ 1 if any paper signal fired, and `grep -c 'paper_dropped'` prints `0`.

**Rollback:** `git revert` the three commits of Phases 04-06 and redeploy. Paper mirror rows written meanwhile stay valid for the old code, which deletes them at boot.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 07 — Roles and leases in one process

**Entry gate:** Phase 06 deployed; Phase 01 record says `PASS` (or the owner's fallback is in this plan). C1 is in (brainstorm: C1 before the split).

**Lease design.** Collection `leases`, `_id` UUIDv7, unique index on `name` (`worker`, `trader`); fields `owner` (`hostname:pid`), `expires_at`, `released_at`. Acquire = `find_one_and_update({name, $or:[{expires_at:{$lt:now}}, {owner:me}]}, {$set:{owner, expires_at: now+30 s}, $setOnInsert:{_id}}, upsert=True)`; a duplicate-key error means someone else holds it. TTL 30 s, renew 10 s, poll 0.5 s while waiting, order margin 5 s. One host, one clock: no fencing token [I, brainstormer §6].

**Trader handover sequence (D8).** New trader: quote feed, bar building, strategies loaded, started, warmed; brokers not connected; `trading_until = None` (`trader.standby`). Old trader on SIGTERM: wait for boundary B + 1 s; wait until `pending_signal_count == 0` and Exness `_inflight`/`_pending_ack` are empty, up to B+30 s; else retry once at the next boundary; then `trading_until = None`, stop the reconcile loop and collector, disconnect brokers, release (`expires_at = now`, `released_at = now`), log `trader.lease_released inflight=N`. New trader acquires within 0.5 s, runs `take_over()`, starts collector and reconcile loop, sets `trading_until = expires_at - 5 s` on every renew, logs `trader.takeover takeover_ms handover_gap_ms` (gap = takeover end − `released_at`). Worst-case drain = 60 + 30 + 60 = 150 s → `stop_grace_period: 180s` (verifier asked ~120 s; the retry needs more).

### Task 7.1 — `APP_ROLES` replaces `enable_jobs`
- **Target:** `core/config.py:64`; `di/infrastructure.py:95-105` (scheduler built, never started here); `main_extensions.py:161-172,211-238`; `app/main.py:36-86`; test conftests `tests/app_test/conftest.py:37`, `tests/backtest_test/conftest.py:40`, `tests/core_test/conftest.py:94`, `tests/core_test/infra/market_data/conftest.py:26`, `tests/engine_test/conftest.py:38`, `tests/app_test/integration/app_factory.py`; `justfile:33-36`.
- **Steps:** `app_roles: frozenset[Literal["api","worker","trader"]]`, env `APP_ROLES=api,worker,trader` (default = today's behaviour), parsed from a comma list. Lifespan: all roles: indexes, health, loop-lag probe. `api`: backtest task set and drain. `worker`: lease loop (Task 7.3). `trader`: standby + lease loop (Task 7.4). Delete `enable_jobs` everywhere; tests use `app_roles=frozenset({"api"})`.
- **Tests to write:** `tests/core_test/unit/test_settings_app_roles.py`: `"api,worker"` parses; `"api,bogus"` raises.
- **Verify:** `rg -c "enable_jobs|ENABLE_JOBS" src tests justfile | wc -l` prints `0`.

### Task 7.2 — `LeaseRepository`
- **Target:** new `core/infra/persistence/repositories/lease_repository.py`; `core/common/constants.py` (`COLLECTION_LEASES`); `main_extensions.py:109-122` `_REPO_TYPES`; `di/infrastructure.py` provider.
- **Steps:** `acquire(name, owner, ttl_s) -> datetime | None`, `release(name, owner)`, `get(name)`; `ensure_indexes` creates the unique `name` index.
- **Tests to write:** `tests/core_test/infra/persistence/test_lease_repository.py`: two owners race, exactly one gets a datetime; the holder renews; an expired lease goes to the other owner; release sets `released_at`.
- **Verify:** test file passes.

### Task 7.3 — Worker lease
- **Target:** new `app/roles.py` (`hold_lease(repo, name, owner, on_acquired, on_lost)` plus `run_worker`, `run_trader`); `main_extensions.py:144-158` (`recover_orphan_jobs` runs only after the worker lease).
- **Steps:** `run_worker`: wait for the lease, then `recover_orphan_jobs`, `scheduler.initialize`, `scheduler.start`, `register_sync_jobs`. On SIGTERM: `scheduler.shutdown(wait=True)`, release. Lost renewal → `on_lost`: shut the scheduler down, log ERROR `lease.lost name=worker`, `os.kill(os.getpid(), signal.SIGTERM)`.
- **Tests to write:** `tests/app_test/unit/test_roles.py`: two worker runtimes on one Mongo log `scheduler.started` exactly once; the waiting one starts it after the first releases.
- **Verify:** test file passes.

### Task 7.4 — Trader standby, takeover, drain
- **Target:** `app/roles.py` `run_trader`; `strategy_reconcile_app_service.py:70-86` (`bootstrap` also converges each sub without writing `actual_state`); `StrategyAppService` (`trading_until` default becomes `None` in the live engine; `_process_signal` returns with DEBUG `strategy.signal_discarded reason=standby` unless `trading_until > now`); `exness_broker_adapter.py` (expose `inflight_count = len(_inflight) + len(_pending_ack)`); `main.py` (quote feed and bootstrap move under the trader role).
- **Steps:** implement the sequence above. Standby never runs `take_over()`, the collector, the reconcile loop or any sweep. Health adds `role` and `lease` (`held`/`standby`).
- **Tests to write:** in `test_roles.py`: a standby trader sends 0 orders on a signalling bar and connects no broker; a lost renewal clears `trading_until`, stops strategies and calls the exit hook; the drain releases only after a fake in-flight open finishes and logs `inflight=0`.
- **Verify:** test file passes.

### Task 7.5 — D18 heartbeat sweep
- **Target:** `backtest_repository.py:92-107`; `backtest_app_service.py:139-141`; `main.py:61` and `main_extensions.py:132-141` (delete boot sweep); `sync_jobs.py` `register_sync_jobs` (new job `backtest_orphan_sweep`, every 5 min); `tests/core_test/infra/persistence/test_stale_recovery.py`; `tests/app_test/integration/app_factory.py:22,55`.
- **Steps:** at the 10-bar yield, at most every 10 s, `$set heartbeat_at`. Sweep fails `started` rows whose `heartbeat_at` (or `created_at` when absent) is older than 60 s.
- **Tests to write:** fresh heartbeat survives, 61 s old heartbeat fails.
- **Verify:** `uv run python -m pytest tests/core_test/infra/persistence/test_stale_recovery.py -q 2>&1 | tail -1` shows `passed`.

### Task 7.6 — `CLAUDE.md` rules (D16) and remote-DB profile
- **Target:** `CLAUDE.md:15` and `:26`; `../pocketquant-config/local/remote-db.env` and `remote-db-local-redis.env`.
- **Steps:** line 15 → "**One lease-holding trader and one lease-holding worker** — the `trader` role (feeds, strategies, brokers, reconcile) and the `worker` role (scheduler, jobs) act only while holding their Mongo lease; never `--workers N`; `api` may run several copies." Line 26 → "Choose the smallest change that meets the requirement; net line count is not a stop gate." Config files: replace `ENABLE_JOBS=false` with `APP_ROLES=api`; commit and push `pocketquant-config` (recipe).
- **Verify:** `grep -c "Single uvicorn worker only\|more code than the code it replaces" CLAUDE.md` prints `0`; `grep -c "^APP_ROLES=api$" ../pocketquant-config/local/remote-db.env` prints `1`.

### Task 7.7 — Gates and deploy D-4 (still one `app` service)
- **Steps:** full suite, `lint-imports`, ratchet; commit `feat(runtime): role-gated lifespan with worker and trader leases`; **[ASK]** push `develop:master`.
- **Verify:** after deploy, `ssh ... "docker logs --since 10m pocketquant-app 2>&1 | grep -cE 'trader.takeover|scheduler.started'"` prints `2`; Mongo read `list(db.leases.find({}, {'name':1,'owner':1}))` shows exactly `worker` and `trader` with one owner each.

**Rollback:** `git revert` and redeploy; drop the `leases` collection afterwards (no other reader).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 08 — Compose split, rolling deploy, one-time cutover

**Entry gate:** Phase 07 deployed and its Verify passed. `ssh ... docker compose version` recorded (researcher Unresolved 1). Market hours not required.

### Task 8.1 — Three services
- **Target:** `deploy/compose.prod.yml:53-91` (`app` → `api`, `worker`, `trader`), `:12-14` (`web.depends_on: api`), `:113-114` (Vietnamese comments → English), `deploy/Dockerfile:62-63` comment.
- **Steps:** same image, `env_file: .env`, `TZ: UTC`, no `container_name`, no host port. `environment`: `APP_ROLES` = `api` / `worker` / `trader`; `EXNESS_RATE_FRACTION` = `0.05` / `0.3` / `0.6` (F3-A). `api` command adds `--timeout-graceful-shutdown 10`, `stop_grace_period: 30s`; `worker` `stop_grace_period: 120s`; `trader` `stop_grace_period: 180s`. Healthcheck `curl -f localhost:41921/health`, `interval: 10s`, `start_period: 30s`.
- **Verify:** `docker compose -f deploy/compose.prod.yml --env-file /dev/null config --services | sort | tr '\n' ' '` prints `api cloudflared mongodb portainer redis trader web worker ` (today's services are `web`, `cloudflared`, `app`, `mongodb`, `redis`, `portainer` [V `compose.prod.yml:4,29,58,93,121,143`]); `grep -c "container_name: pocketquant-app" deploy/compose.prod.yml` prints `0`.

### Task 8.2 — `sync_1m` off the entry window
- **Target:** `engine/market_data/app_services/sync_jobs.py:703-708`.
- **Steps:** `second=2` → `second=12`; update the grace comment.
- **Verify:** `grep -c "second=12" src/pocketquant/engine/market_data/app_services/sync_jobs.py` prints `1`.

### Task 8.3 — nginx re-resolves `api`
- **Target:** `web/nginx.conf:24-26`.
- **Steps:** at server level `resolver 127.0.0.11 valid=5s ipv6=off;`; in `/api/`: `set $api_upstream http://api:41921; proxy_pass $api_upstream; proxy_connect_timeout 2s; proxy_next_upstream error timeout;` No static `proxy_pass` to `api` anywhere (researcher Q4 trap).
- **Verify:** `docker run --rm -v "$PWD/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27.5-alpine nginx -t 2>&1 | grep -c "syntax is ok"` prints `1`.

### Task 8.4 — Rolling deploy and one-time cutover
- **Target:** `deploy/vps/10-deploy.sh:49-72`; `deploy/vps/11-verify.sh:67,79,93,110,120,172,177,188,228,240` (fixed name → `$(dc ps -q api | head -1)`; container lists use service labels).
- **Steps:** add the researcher's `dc()` and `roll()` (`researcher-261028-1400-compose-rolling-deploy.md:70-91`); before `docker rm "$old"`, `roll` saves `docker logs --since 15m "$old" > /tmp/old-$svc.log` so Phase 10 can read the old trader's release line. Main path: pull; `roll api 120; roll worker 120; roll trader 240; dc up -d --no-deps web cloudflared; dc up -d --remove-orphans`. One-time branch, first: if `docker ps -a --format '{{.Names}}' | grep -qx pocketquant-app`: `dc up -d --no-deps api worker trader`, wait healthy (new worker and trader stay in standby: `app` holds both leases), `dc up -d --no-deps web` (nginx now proxies `api`), `docker stop pocketquant-app` (drains, releases; new ones take over), `docker rm pocketquant-app`, `dc up -d --remove-orphans`.
- **Verify:** `bash -n deploy/vps/10-deploy.sh && bash -n deploy/vps/11-verify.sh && echo ok` prints `ok`; `grep -c "pocketquant-app" deploy/vps/11-verify.sh` prints `0`.

### Task 8.5 — Gates and cutover deploy D-5
- **Steps:** commit `feat(deploy): api, worker and trader services with rolling deploys`; **[ASK]** push `develop:master` in market hours; run the 0.5 s probe during the deploy: `ssh ... 'for i in $(seq 1200); do docker exec pocketquant-web curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/v1/market-data/symbols; sleep 0.5; done | sort | uniq -c'`.
- **Verify:** probe output has only `200` lines (the `web` recreate gap is Unresolved 4; record it); `docker ps --format '{{.Names}}' | grep -cE 'pocketquant-prod-(api|worker|trader)-'` prints `3`; trader logs show one `trader.takeover` with `handover_gap_ms` ≤ 2000; `11-verify.sh` verdict 0 failures.

**Rollback:** redeploy the previous master commit; its `10-deploy.sh` brings back `app` with `container_name`. First stop the three new services (`dc stop api worker trader` then `dc rm -f`), so `app` takes the leases after they expire (≤ 30 s gap).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 09 — Docs and cleanup

**Entry gate:** Phase 08 cutover verified.

### Task 9.1 — Delete the one-time cutover branch
- **Target:** `deploy/vps/10-deploy.sh` (the `pocketquant-app` branch).
- **Verify:** `grep -c "pocketquant-app" deploy/vps/10-deploy.sh` prints `0`.

### Task 9.2 — Docs (AS-IS, each under 800 lines)
- **Target:** `docs/system-architecture.md` (roles, leases, standby and handover sequence, timer close and gap flag, entry guards, pause read per open, order pacer lane); `docs/deployment.md` (three services, rolling deploy, label-based container lookup replacing `pocketquant-app` at `:51,64,142,184-186,256-259,267`, `APP_ROLES=api` for remote-DB, stop grace periods); `docs/codebase-summary.md`; `docs/project-overview-pdr.md:110`; `README.md:39,54,75`; `scripts/audit_bar_quality.py:15,24`, `scripts/backfill/*.py` usage lines.
- **Verify:** `rg -c "pocketquant-app|ENABLE_JOBS|enable_jobs|Single uvicorn" docs README.md scripts -g '!docs/journals/**' | wc -l` prints `0`; `wc -l docs/*.md | awk '$1>800 && $2!="total"' | wc -l` prints `0`.

### Task 9.3 — Commit and deploy D-6 (deploy 1 of 10 in Phase 10)
- **Steps:** commit `docs: describe the role split and rolling deploys`; **[ASK]** push `develop:master` in market hours.
- **Verify:** as Task 10.1 for this deploy.

**Rollback:** `git revert`; docs only plus a script branch already unused.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 10 — Prod verification

**Entry gate:** Phase 09 deployed. **[ASK]** start one paper subscription on a 1m Exness symbol (prod has XAUUSD 1m stopped [kongming-1020 §0]) so `live.signal_latency` has samples. Record a state file `plans/261028-0652-exness-only-parallel-runtime/reports/prod-verification-log.md` (one row per deploy, one row per day).

### Task 10.1 — Ten handover deploys in market hours
- **Steps:** each deploy is a real change or `GH_TOKEN=... gh workflow run cicd.yml --ref master` (go-live recipe). Run the 0.5 s probe of Task 8.5 during each. After each, pull trader logs since the deploy start.
- **Success criteria per deploy:** one `trader.lease_released` with `inflight=0` whose seconds-of-minute ≤ 30; one `trader.takeover` with `handover_gap_ms` ≤ 2000 and `takeover_ms` ≤ 5000; 0 `strategy.entry_skipped reason=gap` in the two minutes after the release; probe only `200`.
- **Verify:** `ssh ... "docker logs --since <start> \$(docker ps -q --filter label=com.docker.compose.service=trader | head -1) 2>&1 | grep -E 'trader.(lease_released|takeover)'"` and `ssh ... "grep trader.lease_released /tmp/old-trader.log"` (saved by `roll`, Task 8.4) meet every condition; 10 rows marked PASS.

### Task 10.2 — Second-copy tests (D17: any time)
- **Steps:** `dc up -d --no-deps --no-recreate --scale trader=2 trader`; wait 10 min; stop and remove the new container by id. Same for `worker` (5 min). Before and after, count `db.orders` and `db.positions` documents updated by the new owner (`owner` is in the lease only; use the time window and `trader.standby` logs).
- **Verify:** new trader logs contain `trader.standby` and 0 `exness.order_submitted|order_submitted|backtest_orphan`; Mongo `orders`/`positions` writes in the window come only from the lease holder (counts equal to the holder's `order_submitted` log lines); new worker logs 0 `scheduler.started`.

### Task 10.3 — Fourteen days of paper
- **Daily:** trader `event_loop.lag` count = 0; `Error notifying listener` = 0; `exness.rate_limited` with `op=openPosition` = 0. **Weekly:** `exness.rate_limited_retry` ≤ 72; `strategy.entry_skipped` counts by reason recorded; `live.signal_latency` p95 `t5_ms` ≤ 1000 on 1m Exness samples; `sync_integrity` p50 < 10 s, `sync_repair` p50 < 120 s.
- **Verify:** 14 daily rows and 2 weekly rows in the log, each meeting its numbers.

**Rollback:** none needed; a failed check stops the phase (Failure Protocol).

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## Phase 11 — Re-arm live gate

**Entry gate:** Phase 10 complete with every row PASS; the owner has a strategy to take live (go-live Phase 11 was called off for lack of one).

### Task 11.1 — Re-run the go-live phases, do not copy them
- **Steps:** re-run `plans/261019-1957-exness-go-live/phase-11-go-live-one-strategy.md` and then `phase-12-observation-and-go-live.md` as written (`--from 11 --to 11`, then daily Phase 12), adapting only container names to the label lookup (§2). Those phases own arming, pausing and the zero-money proof.
- **Verify:** go-live plan rows 11-12 report their own completion states.

### Task 11.2 — D12 canary
- **Steps:** the first live strategy runs at the minimum lot with a tight SL. Collect `live.signal_latency` for its first 20 entries.
- **Success criteria:** p95 of `t6_ms` over those 20 entries ≤ 2000. Otherwise pause entries and STOP.
- **Verify:** `ssh ... "docker logs --since <arm time> <trader> 2>&1 | grep live.signal_latency | grep <subscription_id> | head -20"` → compute p95 of `t6_ms`; it is ≤ 2000.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

---

## 4. Test matrix

| Level | What | Where |
|---|---|---|
| Unit | skip listener, loop-lag probe, settings roles, pacer lanes, bar timer/gap/seed, entry guards, warm-up, paper restore, lease repo | Phases 02, 04-07 test files above |
| Integration (testcontainers Mongo/Redis) | pause route → adapter refusal, lease race, worker single scheduler, standby trader sends nothing, heartbeat sweep | `test_safeguards_api.py`, `test_lease_repository.py`, `test_roles.py`, `test_stale_recovery.py` |
| Regression | backtests unchanged by the live-only paths | `tests/backtest_test` |
| Prod | spike, 10 handover deploys, second-copy tests, 14-day paper, D12 canary | Phases 01, 10, 11 |

## 5. Backwards compatibility and rollback

- Data: new collection `leases`; new field `backtest_runs.heartbeat_at` (old rows fall back to `created_at`); paper mirror rows are now kept across restarts. All additive; old code ignores them.
- Config: `ENABLE_JOBS` disappears; `APP_ROLES` defaults to all three roles, so a local `just be` behaves as today. `remote-db.env` moves to `APP_ROLES=api` in the same phase that deletes `ENABLE_JOBS`.
- Each phase rolls back by `git revert` + redeploy; Phase 08 has its own reverse sequence. TV data deletion is not reversible (accepted, D4).

## 6. Risks

| # | Risk | L × I | Mitigation |
|---|---|---|---|
| 1 | Exness disturbs prod ticks when a second ticks session runs during every deploy | M × H | Phase 01 spike gates Phase 07; a disturbed bar is gap-flagged, so the failure is a skipped entry, not a wrong one |
| 2 | Two traders send orders (lease bug, clock jump) | L × H | lease + 5 s order margin; standby never connects brokers; Phase 10.2 second-copy test |
| 3 | Old trader drain exceeds `stop_grace_period` and is SIGKILLed mid-order | L × M | 180 s grace vs 150 s worst-case drain; inflight orders resolve through the new trader's snapshot and `_close_missing` [V `exness_broker_adapter.py:472-486`] |
| 4 | Timer close fires early on clock skew | L × M | NTP check before D-3; 0.5 s grace; late ticks dropped |
| 5 | Order pacer at fraction 0.6 spaces N opens 0.5 s apart; the third open on one boundary leaves at +1.0 s | M × M | D12 canary measures p95 `t6_ms`; raise the trader fraction if more than 3 live 1m subscriptions share a symbol boundary |
| 6 | Rate fractions sum above 1.0 during the cutover (old `app` at 1.0) or when a script uses 0.2 | M × L | cutover overlap is ≤ 3 min; scripts keep `model_copy(... 0.2)` only outside bursts; 429 gate tracked weekly |
| 7 | Loss-cap synchronous fallback adds ~2 s to the first entry after a close | M × M | stated (verifier 5); refresh at second 30; refuse on failure |
| 8 | Warm-up seam: the last stored bar can lag the first live bar by one 1m bar | M × L | the successor check gap-flags that first bar, so no entry runs on an incomplete history |
| 9 | `web` recreate gives a short cloudflared → web gap each deploy | H × L | recorded in Phase 08/10 probe; out of D8 scope (no bar or order is missed) |
| 10 | TV test fixture rewrite is larger than expected (26 files) | M × L | Phase 03 effort 1d; failing tests stop the phase |

## 7. Unresolved

1. The acceptance row "All 8 import-linter contracts pass" cannot hold after D1: two contracts exist only for the removed packages (`pyproject.toml:142` `pandas_market_calendars confined…`, `:160` `tvDatafeed confined…`). This candidate expects `6 kept, 0 broken`. Owner confirms.
2. The TV grep over `docs` hits `docs/journals/2026-09-21-asset-class-trading-calendar.md`, a dated record. This candidate excludes `docs/journals/**`. Owner confirms or asks for the journal to be edited.
3. D10 gives budgets for 1m, 15m and 1h only. 5m, 4h, 1d and 1w entries get no stale guard here. Should they?
4. `web` keeps `container_name` and is recreated on every deploy (researcher Unresolved 4). Is a sub-second `web` gap acceptable under D7, or should `web` also roll?
5. The acceptance probe names `/api/health`, which does not exist: `/health` is registered without the prefix [V `main_extensions.py:372`] and nginx proxies only `/api/` [V `web/nginx.conf:25`]. This candidate probes `/api/v1/market-data/symbols`.
6. The spike FAIL path needs an owner choice (D24 second account, or another fallback) before Phase 07.
7. Compose and Engine versions on the VPS are unknown until Phase 08's entry check.
8. `trading_minutes` interval semantics (`[start, end)` or not) are [UNVERIFIED]; Phase 05 and 06 tests pin them before the gap rules rely on them.
