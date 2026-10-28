---
title: "Candidate 3: Exness-only data, api/worker/trader split, zero-downtime trader handover"
description: "Ops-first candidate plan: spike, TV removal with backed-up data deletion, single-process fixes, leases in one container, then a one-time cutover to three rolled services."
status: pending
priority: P1
effort: "about 9-11 working days of code + 14 days of paper observation"
branch: develop
tags: [exness, parallel-runtime, deploy, lease, handover, tradingview-removal]
created: 2026-10-28
lens: operations and deploy reliability
---

# Candidate 3 (planner debate): ops and deploy reliability lens

Labels: **[V]** verified in current source at the cited `file:line` (develop @ 453e8e90, read 2026-10-28). **[I]** my inference. **[UNVERIFIED]** not checked. Times are UTC. Binding inputs: the brainstorm contract and D1-D24 (`plans/reports/brainstorm-261028-1159-parallel-exness-only-runtime.md`), the evidence packet, and the compose research (`reports/researcher-261028-1400-compose-rolling-deploy.md`).

## 1. Overview

### Outcome
- One host runs `api`, `worker` and `trader` from one image, each with its own event loop. `worker` and `trader` each hold a Mongo lease. A trader without the lease stays in standby and sends no order.
- TradingView, the CME calendar, `ES1!/NQ1!/YM1!:TRADINGVIEW`, subscription `01a178ef` and their data are gone (D1, D4). Exness is the only live venue and the only FX/metals/CFD data source; Binance stays data + paper (D3). US indices are out of this delivery (D22/D23).
- A 1m entry reaches Exness within about 2 s of bar end (D2).
- Every deploy rolls all roles with no missed bar and no missed order (D7/D8); a 1-2 s handover gap between bars is allowed.

### Constraints
- D1-D24; the `CLAUDE.md` limits (flow in ≤3 files, ≤2 hops to I/O, second real caller for any new class/flag/config key, delete dead code in the same change, log frequency rule, English only). D16 removes the "more code → stop and ask" gate (Phase 02 rewrites it first so the executor is not blocked by it).
- No free-threaded Python, no `--workers N`, no Redis Streams, no shared Redis pacer, no Mongo replica set.
- Branch model: all commits on `develop`; every `develop:master` push deploys prod and needs an explicit owner yes [ASK]. Reuse the "Ops recipe" in `plans/261019-1957-exness-go-live/plan.md:34-50` [V] for SSH, token-URL pushes, `GH_TOKEN`, tests and the verify-verdict check. Never print a token.

### Non-goals
A trader per venue; a process pool or symbol sharding; deterministic order ids (H1b); retrying an order after a 429; moving backtests to the worker; keeping ES history; the CME bisect rewrite; US index onboarding (D23); offsetting crons other than `sync_1m`.

### Acceptance criteria (§4 of the contract with D19-D24 applied; indices row removed)

| Area | Criterion |
|---|---|
| Stalls | `/health` on every role reports `event_loop_lag_max_s`. The trader logs 0 `event_loop.lag` lines with `lag_s >= 0.5` per day, including 00:00, 03:00, 04:00 and 12:00Z. After TV removal, 7-day `job_history` p50 of `sync_integrity` < 10 s and `sync_repair` < 120 s. 0 "Error notifying listener" lines; `skipped_max_instances` rows appear when a run is really dropped. |
| Parallelism | `docker ps` shows exactly one running container each for `api`, `worker`, `trader`. `db.leases.find()` returns exactly two docs, `worker` and `trader`, each with one owner. A second `trader` run against prod for 10 min logs `trader.standby` and 0 of `trader.lease_acquired`, `exness.order_submitted`, `position_opened`, `position_closed`, `orphan_backtest_recovery`, `orphan_jobs_recovered`. A second `worker` logs `worker.standby` and 0 `scheduler.started`. |
| TV removal | `rg -i "tradingview\|cme_globex\|pandas_market_calendars\|seed_index_futures" src tests web/src docs pyproject.toml --glob '!docs/journals/**'` returns 0 hits (journal exclusion: see Unresolved U1). Mongo `tracked_symbols`, `symbols`, `bars` have 0 docs matching `/TRADINGVIEW$/`; subscription `01a178ef-5027-73ba-a98e-b7d6de8e2cc9` is gone. All remaining import-linter contracts pass: **6**, because the two contracts that police `pandas_market_calendars` and `tvDatafeed` (`pyproject.toml:142-176` [V]) become vacuous and are deleted with the code (correction to "8"). |
| C1 | CI: a pause through the `api` route makes the trader's next open refused; a failed store read refuses the open; `Safeguards.entries_paused` no longer exists; a failed store write makes the pause route return 503. |
| C2 | CI: of two lease contenders exactly one acquires. A lost renewal stops strategies, refuses opens and exits the process. |
| H1 | CI: a second signal for a subscription is rejected while an `_inflight` open exists for it. |
| H2 / D10 | CI with a fake clock: a 1m bar 11 s late (15m 61 s, 1h 121 s) skips the entry and logs exactly one `strategy.entry_skipped reason=stale`; paper SL/TP still runs on that bar. |
| H3 / D10 | CI: a bucket that is not the calendar successor of the last one, or a bar with > 60 s tick silence in trading time, logs `reason=gap` and skips the entry. Prod: weekly count of `strategy.entry_skipped` reported in Phase 10. |
| M1 / 1m latency | CI: with fresh caches the Exness open path makes exactly 1 REST call (`openPosition`). Prod paper: `live.signal_latency` p95 of T0→T5 ≤ 1 s on 1m Exness-symbol subscriptions. Before go-live: D12 canary, first 20 live entries T0→T6 p95 ≤ 2 s. |
| M2 / D21 | CI: two subscriptions signal on one bar; their pre-submit sections run one after the other under one account lock, and their `openPosition` calls overlap (total time with a fake 1 s call < 1.5 s). A close fill marks the loss-cap cache stale; the next open refreshes it synchronously or refuses. (D21 supersedes "opens run one after the other".) |
| M3 / D9 | CI: after a restart with a LONG mirror row the strategy's direction is LONG; an opposite entry is rejected and never becomes a close; hitnrun2 can signal on the first live bar after a restart. |
| D13 | CI: after a takeover the paper balance equals the balance a never-restarted paper broker would show for the same fills. |
| D18 | CI: the backtest sweep fails only `started` runs whose heartbeat is older than 60 s. |
| Handover (D8) | Over 10 deploys in market hours: every `trader.lease_released` has `inflight=0` and `offset_ms` in [0, 30000] from a 1m boundary; `handover_gap_ms` ≤ 2000; `takeover_ms` ≤ 5000; 0 `reason=gap` skips on bars spanning a handover; the in-deploy probe (`GET http://web:80/api/v1/market-data/symbols` every 0.5 s) records 0 non-200. (Correction: `/api/health` does not exist; `/health` is a root route, `main_extensions.py:372` [V], and nginx proxies only `/api/`, `web/nginx.conf:25-26` [V].) |
| Rate budget (D19) | 0 terminal `exness.rate_limited` on order ops; `exness.rate_limited_retry` per 7 days ≤ 72. |

### Data flows after the split
- `api`: HTTP + SSE + backtests. Writes subscriptions' `desired_state`, the stored entry pause, backtest runs (with heartbeat). Reads Redis `quote:latest`/`bar:current` for SSE. Exness only for ad-hoc sync routes (fraction 0.05).
- `worker`: APScheduler + batch jobs, only while holding lease `worker`. Writes Mongo `bars`, `sync_status`, `job_history`; Exness REST candles (fraction 0.3). No WS, no broker.
- `trader`: Exness ticks WS + Binance WS → `BarAppService` → `EventBus` → strategies → brokers. Writes Redis `quote:latest`/`bar:current`, Mongo `orders`/`positions`/`trades`. Exness events WS and orders only while holding lease `trader` (fraction 0.6). Reads the stored pause per open.
- Cross-process links stay Mongo (desired state, pause, leases) and Redis (UI streams), as today.

### Phases (file order = run order; strictly sequential, no parallel file ownership)

| # | Phase | Depends on | Deploy |
|---|---|---|---|
| 01 | Two ticks sessions on one key: spike (D15/D24) | none | none (read-only probe) |
| 02 | Observe and correct: loop lag, skip listener, C3, image, D16 KISS rule | 01 recorded | D-1 |
| 03 | TradingView/CME removal: backup, prod data delete, code delete | 02 | D-2 |
| 04 | Entry guards: C1, H1, M3 rejection, D11 | 03 | D-3 |
| 05 | Bar path: timer close, Redis seed, H2, H3, D21, `live.signal_latency` | 04, NTP gate | D-4 |
| 06 | Pre-order latency: M1 caches, M2 lock, order pacer | 05 | D-5 |
| 07 | Restart state: D9 warm-up, direction seed, paper restore, D13 | 06 | D-6 |
| 08 | Roles and leases in one container (Deploy A) + D17 probes | 07, Phase 01 PASS | D-7 |
| 09 | Compose split, nginx, rolling deploy, one-time cutover (Deploy B) | 08 | D-8 (+ D-9 cleanup) |
| 10 | Prod verification: 10 handovers, 14 days paper | 09 | owner-approved deploys |
| 11 | Re-arm live gate (pointer + D12 canary) | 10 PASS | per go-live plan |

## 2. Conventions used by every phase

- **SSH and admin calls:** the go-live Ops recipe (`plans/261019-1957-exness-go-live/plan.md:37-44` [V]). Before Phase 09 the backend container is `pocketquant-app`. From Phase 09 on, resolve it on the VPS with `C=$(cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env ps -q <api|worker|trader>)`.
- **Local gates (G):** `docker ps` (start Docker Desktop if it fails); `uv run ruff check src tests`; `uv run pyright`; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet`; `just test`. Expected local red is exactly `4 failed, 4 errors`, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`. Any other red is a failure. If the ratchet fails only because of new small functions, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit rather than pad code.
- **Release procedure (R):** (1) G green; (2) commit on `develop` with a conventional message (no plan ids); (3) push via the token URL, `git fetch origin`, wait for the `develop` CI run green (`gh run watch <id> --exit-status`); (4) [ASK] "Deploy <phase> to prod now? Recommended: yes"; (5) push `develop:master` outside 00:00-00:59, 03:00-04:59, 12:00-12:59; (6) `gh run watch` the master run; then `gh run view <id> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints ≥ 1. A docs-only or `*.md`-only commit does not trigger CI (`.github/workflows/cicd.yml:6-10` [V]).
- **Log checks** always carry `--since`, e.g. `docker logs "$C" --since 30m 2>&1 | grep -c '"event": "trader.standby"'` [UNVERIFIED exact JSON spacing: check one line with `| head -1` first and adjust the pattern].
- **New log events** (INFO unless noted, all low-frequency): `event_loop.lag` (WARNING, one per stall > 0.25 s), `lease.acquired`, `lease.lost` (ERROR), `worker.standby`, `worker.lease_acquired`, `trader.standby`, `trader.warm_done`, `trader.lease_acquired` (`handover_gap_ms`), `trader.trading` (`takeover_ms`), `trader.drain_started`, `trader.drain_retry` (WARNING), `trader.drain_timeout` (ERROR), `trader.lease_released` (`inflight`, `boundary`, `offset_ms`), `strategy.entry_skipped` (WARNING, `reason=stale|gap`), `live.signal_latency` (one per signal).

## 3. Phases

### Phase 01 — Two ticks sessions on one key: spike (D15/D24, D17)

Entry gate: none. Runs before any handover code. `EXNESS_LIVE_TRADING` is false, so no real trade is at risk (D17). Run Mon-Fri inside 13:00-16:00Z (liquid FX/metals, no cron hour). No commit: the script lives in `.cache/spike/`.

**Task 1.1 — Write the spike script**
- Goal: open one extra Exness ticks session beside prod's own session for 30 min and measure whether prod's session drops or lags.
- Target: `.cache/spike/two_ticks_sessions.py` (not committed). Uses `pocketquant.core.config.get_settings`, `ExnessClient` (`core/infra/exness/exness_client.py`), `ExnessStream` (`core/infra/exness/exness_stream.py`), the ticks path `/v1/server-events/accounts/{account_id}/ws/ticks` (`exness_quote_adapter.py:28` [V]) and Redis keys `quote:latest:{symbol}` (`core/common/constants.py:25` [V]).
- Steps: (1) build `ExnessClient(get_settings().model_copy(update={"exness_rate_fraction": 0.05}))`; (2) open one `ExnessStream` on the ticks path, on connect send `{"id":"sub-all","subscribe":{"event":"ticks","instruments":["XAUUSD","EURUSD","BTCUSD"]}}` (only mapped instruments: an unknown one is a strike); (3) per tick record instrument, venue timestamp, local receive time; count reconnects and error frames; (4) every 0.25 s read Redis `quote:latest:XAUUSD:EXNESS`, `EURUSD:EXNESS`, `BTCUSD:EXNESS` (written by prod per tick, `quote_app_service.py:70-71` [V]) and record `lag = spike_latest_venue_ts - prod_latest_venue_ts` per instrument; (5) after 1800 s print one JSON object: per instrument tick count, max inter-tick gap, lag p50/p99/max, reconnects, error frames.
- Success: the script runs 1800 s and prints the JSON.
- Verify: `uv run python -c "import ast,sys; ast.parse(open('.cache/spike/two_ticks_sessions.py').read()); print('ok')"` prints `ok`.

**Task 1.2 — Run it inside the prod container and read prod's logs**
- Goal: measure interference in the real topology (prod session + one more = the handover overlap).
- Target: VPS container `pocketquant-app`.
- Steps: (1) note `T0=$(date -u +%FT%TZ)`; (2) `ssh ... 'docker exec -i pocketquant-app python -' < .cache/spike/two_ticks_sessions.py > .cache/spike/result.json`; (3) `ssh ... "docker logs pocketquant-app --since $T0 2>&1 | grep -cE 'exness_ws.reconnecting|exness_ws.circuit_breaker_open|exness_ws.error_frame'"`.
- Success: result JSON saved; prod log count captured.
- Verify: `test -s .cache/spike/result.json && echo saved` prints `saved`.

**Task 1.3 — Decide and record**
- Goal: pick F1-A or stop (D15/D24).
- Target: `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-ticks-sessions.md` (result table + verdict).
- Steps: PASS when all hold: prod log count from 1.2 is 0; spike reconnects 0 and error frames 0; per instrument lag p99 ≤ 1.0 s and max ≤ 5.0 s [I: thresholds sized from the 4.30 s EURUSD max tick gap]. Write PASS → "F1-A hot standby with tick overlap". On FAIL write FAIL and stop: the D24 fallback is a second Exness account, which is an owner action and changes Phase 08 (the standby would need its own quote credentials).
- Success: the report exists with a PASS or FAIL line.
- Verify: `grep -cE "^Verdict: (PASS|FAIL)$" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-ticks-sessions.md` prints `1`. A FAIL verdict triggers the Failure Protocol (owner decision needed before Phase 08).

Rollback: none needed; the script holds no state. Stop it with Ctrl+C; its session closes.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 02 — Observe and correct (loop lag, skip listener, C3, image, D16)

Entry gate: Phase 01 report exists (PASS or FAIL; this phase does not depend on the verdict).

**Task 2.1 — Rewrite the CLAUDE.md "more code" rule (D16)**
- Goal: the executor must not stop on net line counts.
- Target: `CLAUDE.md:26` [V].
- Steps: replace the line with `  - Prefer the simplest design that meets the requirement; a larger diff is fine when it removes complexity or is required by the scope.`
- Success: the old sentence is gone.
- Verify: `grep -c "stop and ask" CLAUDE.md` prints `0`.

**Task 2.2 — Event-loop lag probe on every process**
- Goal: `event_loop_lag_max_s` on `/health`, one WARNING per stall.
- Target: `app/main_extensions.py` new `start_loop_lag_probe(app)` / stop in `_cancel`; `main.py:58-66` (start before `ensure_all_indexes`), `main.py:80-85` (stop); `/health` route `main_extensions.py:372-380`.
- Steps: a task loops `t = loop.time(); await asyncio.sleep(0.5); lag = loop.time() - t - 0.5`; keeps the max of the last 120 samples (60 s) on `app.state.loop_lag_max_s`; logs `event_loop.lag` WARNING with `lag_s` when `lag > 0.25`; `/health` adds top-level `event_loop_lag_max_s` (rounded to 3 decimals).
- Tests: `tests/app_test/unit/test_loop_lag_probe.py`: block the loop with `time.sleep(0.6)` once; assert the recorded max ≥ 0.5 and exactly one WARNING captured.
- Success: test green; `/health` JSON carries the field.
- Verify: `uv run python -m pytest tests/app_test/unit/test_loop_lag_probe.py -q` ends with `1 passed` (or the count of tests written, 0 failed).

**Task 2.3 — Fix the skip listener and its silent failure**
- Goal: dropped runs become `job_history` rows; 0 "Error notifying listener".
- Target: `core/infra/scheduling/scheduler.py:95-99` (`_on_skip`), `:117-135` (`_dispatch_skip`).
- Steps: for `EVENT_JOB_MAX_INSTANCES` read `event.scheduled_run_times[-1]`; for `EVENT_JOB_MISSED` keep `event.scheduled_run_time`; add a done-callback on the `run_coroutine_threadsafe` future that logs `scheduler.record_skip_failed` WARNING with `exc_info` when it raised.
- Tests: `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py`: start a real `AsyncIOScheduler` with a `max_instances=1` job that sleeps, force a second submission, assert `record_skip` got `status="skipped_max_instances"` and the run time.
- Verify: `uv run python -m pytest tests/core_test/infra/scheduling/test_scheduler_skip_listener.py -q` shows 0 failed, ≥ 1 passed.

**Task 2.4 — Correct the scheduler docstring and the docs (C3)**
- Goal: no text claims a shared jobstore coordinates processes.
- Target: `scheduler.py:1-10`, `:52-55` [V]; `docs/deployment.md:221` [V]; `docs/project-overview-pdr.md:110` [V].
- Steps: state "Exactly one process runs the scheduler. The APScheduler 3.x FAQ says a shared jobstore across processes runs jobs twice or skips them."
- Verify: `grep -rc "distributed coordination\|first to update next_run_time" src/pocketquant/core/infra/scheduling/scheduler.py docs/deployment.md` prints `0` for each file.

**Task 2.5 — Pin the release Python image**
- Target: `deploy/Dockerfile:4,28` [V].
- Steps: `python:3.14-rc-slim` → `python:3.14-slim` in both stages.
- Verify: `grep -c "3.14-rc-slim" deploy/Dockerfile` prints `0` and `grep -c "python:3.14-slim" deploy/Dockerfile` prints `2`.

**Task 2.6 — Deploy D-1 and verify**
- Steps: release procedure R. Then on the VPS: `docker exec pocketquant-app python -c "import sys; print(sys.version.split()[0])"`; `docker exec pocketquant-app curl -s http://localhost:41921/health`.
- Success: Python is a 3.14 final release; `/health` carries `event_loop_lag_max_s`.
- Verify: the version string contains no `rc` (`... | grep -c rc` prints `0`); `... /health | grep -c event_loop_lag_max_s` prints `1`. After 24 h: `docker logs pocketquant-app --since 24h 2>&1 | grep -c "Error notifying listener"` prints `0`.

Rollback: `git revert` the phase commits and run R; the probe and listener hold no state.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 03 — TradingView/CME removal (D1, D4)

Entry gate: Phase 02 deployed. Order matters: delete prod data through the running app first (its cascade route exists today), then ship the code deletion. Shipping code first would leave three tracked symbols whose provider no longer exists.

**Task 3.1 — Back up prod Mongo and record counts**
- Goal: a restorable copy before any prod deletion (owner rule: backup before delete).
- Target: VPS `/opt/pocketquant/backups/`.
- Steps: (1) `ssh ... "mkdir -p /opt/pocketquant/backups && docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --archive --gzip' > /opt/pocketquant/backups/pre-tv-removal-$(date -u +%Y%m%dT%H%M).archive.gz"` (pattern from `docs/deployment.md:253` [V], plus `--gzip`); (2) list size; (3) record counts with mongosh: `db.tracked_symbols.countDocuments({symbol:/TRADINGVIEW$/})`, the same for `symbols` and `bars` [UNVERIFIED field name `symbol` in each collection: inspect one doc first], and `db.subscriptions.countDocuments({_id:"01a178ef-5027-73ba-a98e-b7d6de8e2cc9"})`.
- Success: archive > 1 MB; counts saved to `plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`.
- Verify: `ssh ... "ls -l /opt/pocketquant/backups/pre-tv-removal-*.archive.gz | awk '{print \$5}'"` prints a number > 1000000; `ssh ... "docker exec -i pocketquant-mongodb sh -c 'mongorestore --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin\" --dryRun --archive --gzip' < /opt/pocketquant/backups/<archive file>; echo rc=\$?"` ends with `rc=0` [UNVERIFIED that the image's mongorestore has `--dryRun`: check `docker exec pocketquant-mongodb mongorestore --help | grep -c dryRun` prints ≥ 1 first].

**Task 3.2 — Stop subscription 01a178ef, then delete the three symbols via the API**
- Goal: cascade-delete all TV data (D4); stop the ES paper run first.
- Target: `POST /api/v1/subscriptions/{id}/stop` (`routes/strategy.py:96` [V]); `DELETE /api/v1/market-data/tracked-symbols/{symbol}` (`routes/market_data.py:296-309` [V], cascades subscriptions, bars, backtests, orders/positions/trades).
- Steps: admin calls inside the container as in the Ops recipe: stop `01a178ef-5027-73ba-a98e-b7d6de8e2cc9`; wait 10 s; `GET /api/v1/subscriptions/` and confirm its `actual_state` is `stopped`; then `DELETE .../tracked-symbols/ES1%21%3ATRADINGVIEW`, `NQ1%21%3ATRADINGVIEW`, `YM1%21%3ATRADINGVIEW`; save each response's `deleted` counts to the counts report.
- Success: three 200 responses; counts recorded.
- Verify: re-run the 3.1 count queries: every count prints `0`.

**Task 3.3 — Delete the TV/CME code surface**
- Goal: no TV/CME code, dependency, config, test, web branch or doc line remains.
- Target (checklist, `explore-261028-0915-tradingview-removal-impact.md` §1, re-verified by the `rg` run above): `src/pocketquant/core/infra/tradingview/` (6 modules); `core/infra/calendars/cme_globex_calendar_adapter.py` + `calendars/__init__.py` + `trading_calendar_factory.py` CME entries; `app/di/adapters.py:43-45,76-80,100-104,120-124` [V]; `core/domain/market_data/provider_routing_domain_service.py:23,46` [V]; `core/config.py:10-14,66-107` [V]; `core/domain/shared/enums.py:62-107`; `app/main_extensions.py:66,275-305` [V] (health check keeps binance + exness); `engine/market_data/app_services/quote_app_service.py:32-34` [V] (TTL becomes `TTL_QUOTE_LATEST`); `core/infra/market_data/provider_health_check.py`; `engine/market_data/data_lag_service.py` CME text; `scripts/seed_index_futures.py`, `scripts/README.md`; `pyproject.toml:13,29-30,54` deps and the two contracts at `:142-176` [V]; `uv.lock` (`uv lock`); web files listed in the scout report; tests under `tests/core_test/infra/tradingview/`, `tests/app_test/unit/test_tradingview_credentialed.py`, `tests/core_test/infra/calendars/test_cme_globex_calendar.py`, and every test the `rg` lists (rewrite fixtures to Exness/Binance symbols, do not delete behaviour coverage); docs `system-architecture.md`, `deployment.md`, `codebase-summary.md`, `project-overview-pdr.md`, `code-standards.md`, `README.md`.
- Steps: delete, then `uv lock`; fix every import and fixture until G is green; delete the Vietnamese comments at `deploy/compose.prod.yml:113-114` [V] (English rule).
- Success: G green with the expected red; web lint/tests green.
- Verify: (a) the TV-removal `rg` from the acceptance table prints nothing (exit 1); (b) `uv run lint-imports` reports `Contracts: 6 kept, 0 broken.`; (c) `cd web && npm run lint && npm run test && npm run build` exits 0.

**Task 3.4 — Deploy D-2, verify, and close the memory note**
- Steps: R. Then on the VPS: `docker logs pocketquant-app --since 15m 2>&1 | grep -ciE "tradingview|cme"` and `/health` providers block. Next morning read `job_history` for the 00:00/04:00/12:00 runs. Then delete the auto-memory note `pocketquant-es-paper-subscription-kept.md` and its line in that memory dir's `MEMORY.md` (verifier item 11; the note says to delete itself after this phase).
- Success: no TV log lines; first post-removal `sync_integrity` < 30 s and `sync_repair` < 300 s (7-day p50 targets are checked in Phase 10).
- Verify: log count prints `0`; mongosh `db.job_history.find({job_id:{$in:["sync_integrity","sync_repair"]},started_at:{$gt:ISODate("<deploy time>")}},{job_id:1,duration_s:1})` [UNVERIFIED field names: check one doc] shows durations under those bounds.

Rollback: code: `git revert` + R (the old code tolerates absent TV symbols [I]). Data: restore only the affected collections from the archive with `mongorestore --archive --gzip --nsInclude=pocketquant.<coll>` after an owner [ASK]; a full `--drop` restore would also roll back every other collection to the backup time.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 04 — Entry guards: C1, H1, M3 rejection, D11

Entry gate: Phase 03 deployed. One process; must land before any split (C1 before split).

**Task 4.1 — C1: read the pause from the store on every open, fail closed**
- Target: `core/infra/brokers/exness/exness_safeguards.py:10-31` [V] (delete `entries_paused` and `set_entries_paused`); `app/di/adapters.py:49-74` [V] (no load at boot; pass `SafeguardsRepository` into `BrokerFactory`); `core/infra/brokers/broker_factory.py` (forward it to `ExnessBrokerAdapter`); `exness_broker_adapter.py:216-263` [V]; `app/routes/safeguards.py:24-49` [V]; `app/di/services.py:169-171` comment.
- Steps: (1) in `_submit_open`, before other checks, `paused = await self._safeguards_repo.load_entries_paused()`; on any exception log `exness.order_rejected_presubmit reason=pause_unreadable` and refuse; on `True` refuse "entries paused" with the existing log line; remove the pause branch from `_presubmit_reason`; (2) the route writes the store only; on a store exception it returns 503 `{"detail":"pause not stored"}`; GET returns `asdict(safeguards) | {"entries_paused": await repo.load_entries_paused()}` (same response shape for the SPA).
- Tests: extend `tests/app_test/integration/test_safeguards_api.py`: pause via route → a broker built from the same container refuses the next open; repo read raising → open refused; repo write raising → 503. Remove tests of the in-memory flag.
- Verify: `uv run python -m pytest tests/app_test/integration/test_safeguards_api.py tests/core_test/infra/brokers/exness -q` shows 0 failed; `grep -rc "set_entries_paused" src` prints `0` per file.

**Task 4.2 — H1: one open in flight per subscription**
- Target: `exness_broker_adapter.py:245-263` [V].
- Steps: refuse with "open in flight for subscription" when any `_inflight` value has `kind == "open"` and `order.subscription_id` equal to the new order's.
- Tests: in `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`, hold the first `openPosition` ACK, submit a second for the same subscription → rejected; a different subscription → allowed.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q -k inflight` shows ≥ 2 passed, 0 failed.

**Task 4.3 — M3 + D11: reject opposite entries, delete the close branch**
- Target: `exness_broker_adapter.py:199-214` [V] and the close-only paths `kind: str  # "open" | "close"` (`:86` [V]) and `inflight.kind == "close"` (`:543` [V]); `engine/execution/risk_check.py:32-33` [V].
- Steps: (1) adapter: when a position is held for the subscription, reject every order ("position already open for subscription"); delete the `closePosition` send and any code only it reached (`kind="close"` paths); live positions close only by venue SL/TP (D11); (2) `RiskCheckHandler.validate`: reject when an open position exists with the opposite side ("opposite position open"), so paper behaves the same.
- Tests: adapter: held LONG + SELL of equal units → rejected, no `closePosition` call; risk check: LONG position + SHORT signal → `(False, "opposite position open")`.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness tests/engine_test/test_risk_check.py -q` 0 failed; `grep -c '"closePosition"' src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py` prints `0`.

**Task 4.4 — Deploy D-3 and verify**
- Steps: R; then GET `/api/v1/admin/safeguards` inside the container.
- Verify: the response contains `"entries_paused":` (any value), and `docker logs pocketquant-app --since 10m 2>&1 | grep -c application_start_failed` prints `0`.

Rollback: `git revert` + R. The stored pause document is unchanged by this phase.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 05 — Bar path: timer close, Redis seed, H2, H3, D21, latency line

Entry gate: Phase 04 deployed, and the VPS clock is NTP-synced (D20).

**Task 5.1 — NTP gate**
- Verify: `ssh ... "timedatectl show -p NTPSynchronized --value"` prints `yes`. If not: `ssh ... "sudo timedatectl set-ntp true"`, wait 5 min, re-check; still `no` → Failure Protocol.

**Task 5.2 — Timer close and publish outside the bar lock (D20, D21)**
- Target: `engine/market_data/app_services/bar_app_service.py:79-135,137-178` [V]; `core/domain/bar/events.py` (`BarCompletedEvent`).
- Steps: (1) `_process_tick_for_interval` returns completed bars instead of publishing; `add_tick` publishes them after releasing `_lock` (D21: no bar lock across handlers or `openPosition`); (2) one background task (started by `QuoteAppService.start`, stopped with the feed) wakes every 0.1 s and, under `_lock`, closes every builder whose `bar_end + 0.5 s <= now`, where `bar_end = min(bar_start + interval, calendar.session_close(calendar.session_date(bar_start)))` (port methods at `trading_calendar_port.py:37-52` [V]); publish after release; (3) a tick older than its builder's bucket after a timer close stays dropped (existing late-tick rule); (4) `BarCompletedEvent` gains `closed_at` (wall time of close) and `has_gap: bool`; (5) delete `flush_all_bars` (`:270-289` [V], dead) and fix the "at-least-once" text at `:54,149` [V] to "at most once: a restart or a feed gap loses bars; consumers must check `has_gap` and bar succession".
- Tests: `tests/app_test/market_data/test_bar_app_service_unit.py`: fake clock, no next tick → bar published at end + 0.5 s with `closed_at`; a handler that awaits 1 s does not delay a tick for another symbol.
- Verify: `uv run python -m pytest tests/app_test/market_data/test_bar_app_service_unit.py -q` 0 failed; `grep -c "def flush_all_bars" src/pocketquant/engine/market_data/app_services/bar_app_service.py` prints `0`.

**Task 5.3 — Redis seed replaces the Mongo seed; gap flag**
- Target: `bar_app_service.py:104-115,180-208,210-236` [V].
- Steps: replace `_seed_builder_from_mongo` with `_seed_builder_from_redis`: only for the first builder of a key in this process (not after a close), read `bar:current:{symbol}:{interval}`; use it when its `bar_start` equals the bucket and `first_tick_ts - last_update <= 60 s` (verifier item 3, D20 threshold). Otherwise, if the first tick is more than 60 s after the bucket start, mark the builder `has_gap`. Inside a bar, a tick gap > 60 s (wall time equals trading time inside one bucket, because buckets never cross a session break [I]) or a tail gap (`bar_end - last_tick > 60 s`) also sets `has_gap`.
- Tests: seed present and fresh → OHLC merged, `has_gap=False`; seed missing mid-bucket → `has_gap=True`; 61 s silence → `has_gap=True`.
- Verify: `uv run python -m pytest tests/app_test/market_data/test_bar_app_service_unit.py -q -k "seed or gap"` ≥ 3 passed, 0 failed; `grep -c "_seed_builder_from_mongo" src -r` prints `0`.

**Task 5.4 — H2/H3 entry skip in the strategy service; concurrent order sends (D10, D21)**
- Target: `engine/strategy/strategy_app_service.py:241-270,323-390` [V].
- Steps: (1) per strategy keep `last_bar_start`; on each bar compute `age = now - bar_end`; reason `stale` when age > 10 s (1m), 60 s (15m), 120 s (1h), 120 s for other intervals (see U4); reason `gap` when `event.has_gap` or `bar_start` is not the successor of `last_bar_start` (successor = previous `bar_end`, or the next `session_open` when it equals `session_close`); (2) always call `strategy.on_bar_completed` (state continuity); on a skip discard the signal, log one `strategy.entry_skipped` WARNING with `reason`, `subscription_id`, `bar_start`, `age_s`, and call `_notify_rejected(strategy, reason)` so the strategy re-arms; (3) process each accepted signal in its own task held in `self._order_tasks` (strong refs, errors logged), so N opens on one boundary do not wait for each other (D21); exits are untouched (paper SL/TP is a separate bus handler; venue SL lives at Exness).
- Tests: `tests/engine_test/test_strategy_entry_skip.py` with a fake clock: 1m bar 11 s late → one `reason=stale`, no order; 15m 61 s, 1h 121 s likewise; non-successor → `reason=gap`; paper SL/TP still fills on the skipped bar.
- Verify: `uv run python -m pytest tests/engine_test/test_strategy_entry_skip.py -q` ≥ 5 passed, 0 failed.

**Task 5.5 — `live.signal_latency`**
- Target: `strategy_app_service.py:323-390`; `exness_broker_adapter.py:352-360` [V] (`exness.order_submitted`).
- Steps: one INFO line per signal keyed by `subscription_id` + `bar_start` with `t0_bar_end`, `t2_closed_at`, `t3_published` (`event.occurred_at`), `t4_signal`, `t5_presubmit` (just before `order_app_service.submit`), `t6_submitted` (submit returned), `closed_by_timer`; add `send_ms` (HTTP duration) to `exness.order_submitted`.
- Verify: a unit test asserts one `live.signal_latency` line per signal with all fields: `uv run python -m pytest tests/engine_test/test_strategy_entry_skip.py -q -k latency` 1 passed.

**Task 5.6 — Deploy D-4 and verify**
- Steps: R. After 2 h: count timer closes and skips.
- Verify: `docker logs pocketquant-app --since 2h 2>&1 | grep -c live.signal_latency` ≥ 0 (record); `... | grep -c '"reason": "gap"'` recorded; `... | grep -c application_start_failed` prints `0`. Report the T2−T0 p95 from the latency lines; it must be ≤ 1.0 s (timer grace 0.5 s + loop) or the NTP/grace assumption failed.

Rollback: `git revert` + R. No stored state.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 06 — Pre-order latency: M1 caches, M2 lock, order pacer

Entry gate: Phase 05 deployed.

**Task 6.1 — Cached balance and loss cap (F2-A)**
- Target: `exness_broker_adapter.py:265-305` (loss cap), `:656-669` (`get_balance`, snapshot) [V].
- Steps: a task started in `connect()` refreshes the realized-today sum and the balance at second 30 of every minute; `_on_event` marks the loss cap stale on every close/deal event; `_submit_open` uses the cache when fresh (< 75 s and not stale), else reads synchronously (about 2 s on the first entry after a close: verifier item 5), and refuses on a read error; `get_balance` returns the cached snapshot when < 75 s old.
- Tests: fresh caches → exactly 1 client call (`openPosition`) per open; close event → next open calls `getDealsHistory` once; deals read raising → open refused.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q -k "cache or loss_cap"` ≥ 3 passed, 0 failed.

**Task 6.2 — M2: account-level open lock**
- Target: `exness_broker_adapter.py:216-243,317-330` [V].
- Steps: one `asyncio.Lock` covers pause read, presubmit, loss-cap check and `_inflight[rid]` registration; release before the HTTP call.
- Tests: two concurrent opens: presubmit sections serialize (ordering asserted); with a fake 1 s `openPosition`, total wall time < 1.5 s (D21).
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q -k account_lock` ≥ 1 passed, 0 failed.

**Task 6.3 — Pace order ops by their own limit**
- Goal: N opens on one boundary are spaced by `openPosition`'s 4/s limit, not by the strictest 2/s data limit (D21). Today one pacer spaces every call by the strictest rate ×1.2 / fraction (`exness_client.py:116-120,346-355` [V]): 1.0 s at fraction 0.6, so a third open would leave 2 s after the first. The spike journal records `openPosition`/`closePosition` at 4 per 1 s (`docs/journals/2026-10-13-exness-api-spike.md:36` [V]).
- Target: `core/infra/exness/exness_client.py:147-195,300,346-355` [V].
- Steps: keep the existing pacer for non-priority ops; add a second `_RequestPacer` for `_PRIORITY_OPS` (`:60` [V]) with interval `max(global_account_rate, own method rate) window/limit × 1.2 / fraction` (0.5 s at 0.6). Worst-case process rate becomes 1/1.0 + 1/0.5 = 3/s, under the 10/s account limit with the worker at 0.5/s [I].
- Tests: `tests/core_test/infra/exness/test_request_pacer.py`: two priority waits are spaced by the priority interval and not delayed by a waiting candle call.
- Verify: `uv run python -m pytest tests/core_test/infra/exness/test_request_pacer.py -q` 0 failed.

**Task 6.4 — Deploy D-5 and verify**
- Steps: R. After 24 h: rate counts.
- Verify: `docker logs pocketquant-app --since 24h 2>&1 | grep -c exness.rate_limited_retry` ≤ 11 (72/7 days); terminal `"event": "exness.rate_limited"` lines with an order op: `0`.

Rollback: `git revert` + R.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 07 — Restart state: D9 warm-up, direction seed, paper restore, D13

Entry gate: Phase 06 deployed. This phase also removes the boot paper-row delete, which would otherwise delete the live trader's paper rows when a standby trader starts in Phase 08 (`app/di/services.py:122-133` runs `PositionAppService.start` → `load_open_positions` → `delete_open_by_subscription`, `position_app_service.py:36-53` [V]).

**Task 7.1 — Store SL/TP on the paper mirror row**
- Goal: a restored paper position keeps its exits. Today the mirror row is opened without SL/TP (`position_app_service.py:73-80` [V]) because `OrderFilledEvent` carries none (`core/domain/order/events.py:22-30` [V]).
- Target: `OrderFilledEvent`; its producers in `engine/execution/order_app_service.py:88,161` [V]; `position_app_service.py:61-92`.
- Steps: add `sl_price`/`tp_price` to the event from the order; pass them into `PositionAggregate.open(...)` (fields exist, `core/domain/position/entities.py:40-41,57-58` [V]).
- Verify: `uv run python -m pytest tests/engine_test/test_order_filled_event_routing.py tests/engine_test/test_paper_position_lifecycle.py -q` 0 failed, with a new assertion that the saved row has the order's SL/TP.

**Task 7.2 — Restore paper positions and rebuild the paper balance (D9, D13)**
- Target: `position_app_service.py:31-53` [V]; `app/di/services.py:122-133` [V]; `core/infra/brokers/paper/paper_broker_adapter.py:97-98,282-287` [V]; `TradeRepository` (`core/infra/persistence/repositories/trade_repository.py`).
- Steps: (1) `load_open_positions` keeps every open row (delete the paper delete and its parameter); paper rows without SL and TP (written before 7.1) are deleted with one WARNING `paper_position_dropped_no_exits`; (2) `PositionAppService` loading moves out of the DI factory into an explicit `reload()` called by the trader start path (Phase 08 calls it at takeover); (3) `PaperBrokerAdapter.restore(positions, realized_pnl)` sets `_positions` and `_balance = _initial_balance + realized_pnl - entry commission of the restored positions`; realized P&L = sum of `Trade.pnl` over the pool's subscriptions (`run_id` = subscription id, `live_trade_collector.py:57-73` [V]), the same base + Σpnl formula as `live_metrics_query_service.py:69` [V]; (4) `StrategyAppService` calls `restore` when it creates a paper broker pool.
- Tests: `tests/engine_test/test_paper_restore.py`: run open/close/open on a paper broker, record its balance and position; rebuild a fresh broker from the saved rows and trades → equal balance and position (D13), SL/TP fire on the next bar.
- Verify: `uv run python -m pytest tests/engine_test/test_paper_restore.py -q` 0 failed; `grep -c "delete_open_by_subscription" src/pocketquant/engine/execution/position_app_service.py` prints `1` (only `drop()` keeps it).

**Task 7.3 — Strategy warm-up and direction seed (D9, M3)**
- Target: `core/domain/strategy/strategy_service_interface.py:35-77` [V]; `engulfing_strategy_service.py:74-79` and `hitnrun2_strategy_service.py:66-73` [V] (`on_start` clears buffers and `_open_direction`); `engulfing_pullback30_touch_strategy_service.py`; `strategy_app_service.py:139-154` [V]; `BarRepository`.
- Steps: (1) move `_open_direction` into `IStrategyService`; add `async def warm_up(self, bars, open_direction)`: `on_start()`, feed each bar to `on_bar_completed` discarding signals, then set `_open_direction`; (2) `StrategyAppService.warm_strategy(sid)` loads the last 1000 bars of the subscription's symbol/interval from Mongo (hitnrun2 needs 481: `hitnrun2_strategy_service.py:35-37,60-62` [V]) and the mirror side from `PositionAppService.get(sid)`; (3) `start_strategy` calls it instead of a bare `on_start` (callers: boot bootstrap and user start).
- Tests: `tests/engine_test/test_strategy_warm_up.py`: LONG mirror row → direction LONG after start, opposite signal rejected (4.3); hitnrun2 with 481 stored bars signals on the first live breakout bar.
- Verify: `uv run python -m pytest tests/engine_test/test_strategy_warm_up.py -q` ≥ 2 passed, 0 failed.

**Task 7.4 — Deploy D-6 and verify**
- Steps: R; inspect the boot lines.
- Verify: `docker logs pocketquant-app --since 10m 2>&1 | grep -c loaded_open_positions` prints `1` and no line shows `paper_dropped` > 0 except `paper_position_dropped_no_exits` for pre-7.1 rows (record them).

Rollback: `git revert` + R. The mirror rows gain two optional fields; the old code ignores them [I].

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 08 — Roles and leases in one container (Deploy A)

Entry gate: Phase 07 deployed; Phase 01 verdict PASS (else stop for the D24 decision). Deploy A ships every role mechanism while compose still runs one `app` container with all roles, so the role code is proven in prod before the topology changes, and the old container already releases leases when the cutover in Phase 09 stops it.

**Task 8.1 — `APP_ROLES` replaces `enable_jobs`**
- Target: `core/config.py:64` [V]; `app/di/infrastructure.py:95-105` [V]; `app/main_extensions.py:161-172,211-238` [V]; `app/main.py:58-66` [V]; tests setting `enable_jobs=False` (`tests/app_test/conftest.py:37`, `tests/backtest_test/conftest.py:40`, `tests/app_test/integration/app_factory.py`, `test_declarative_subscription_state_api.py`, `test_app_standalone_runtime.py` [V]); `justfile:36`, `README.md:39,54,75`, `docs/system-architecture.md:43-54`, `docs/deployment.md:221-224` [V].
- Steps: `app_roles: str = "api,worker,trader"` parsed into a frozenset; any unknown or empty value fails startup; delete `enable_jobs`. The scheduler provider never starts the scheduler (the worker runtime does). Lifespan: every role runs indexes, health and the lag probe; `api` runs backtests and the backtest sweep loop (8.4); `worker` and `trader` start their runtimes (8.3) as background tasks so uvicorn binds `/health` at once. Tests use `app_roles="api"`.
- Verify: `grep -rc "enable_jobs\|ENABLE_JOBS" src tests justfile README.md docs/system-architecture.md docs/deployment.md` prints `0` per file; G green.

**Task 8.2 — Lease repository and lease object (C2)**
- Target: new `core/infra/persistence/repositories/lease_repository.py` (repos live in core per `CLAUDE.md`); new `core/infra/persistence/lease.py` (`Lease` with `TraderLease`, `WorkerLease` subclasses for DI); `app/di/infrastructure.py`.
- Steps: doc `{_id: name, owner, expires_at, released_at}`; `try_acquire` = `find_one_and_update({_id, $or:[{expires_at:{$lt:now}},{owner:me}]}, {$set:{owner:me, expires_at:now+30s}}, upsert=True)`, a `DuplicateKeyError` means held; renew every 10 s; `valid_for(margin_s)` is true while `now + margin < expires_at` of the last successful renew; no successful renew by `expires_at - 5 s` → `lease.lost` ERROR, the owner callback stops work, then the process sends itself SIGTERM (compose restarts it); `release()` sets `expires_at = now` and `released_at = now` only when `owner == me`. Owner = `"{hostname}-{uuid7}"`. TTL 30 s, renew 10 s, standby poll 0.5 s.
- Tests: `tests/core_test/infra/persistence/test_lease_repository.py` (real Mongo): two contenders → exactly one acquires; expiry → the other acquires; release by a non-owner is a no-op; a renew failing past the margin fires the lost callback.
- Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_lease_repository.py -q` ≥ 4 passed, 0 failed.

**Task 8.3 — Worker and trader runtimes (standby, takeover, drain)**
- Target: new `app/role_runtime.py` (`run_worker`, `run_trader`, `drain_trader`, `drain_worker`); `main.py` lifespan `finally`; `strategy_app_service.py` (a `trading` switch, default `True`; the live provider in `app/di/services.py:135-160` [V] builds it with `False`); `exness_broker_adapter.py` (refuse an open when `not lease.valid_for(5.0)`); `engine/live/strategy_reconcile_app_service.py:75-88` [V].
- Steps worker: poll the worker lease (`role_state=standby`, log `worker.standby` once); on acquire: `recover_orphan_jobs` (moved here from boot: otherwise a starting worker fails the running worker's job rows), initialize + start the scheduler, `register_sync_jobs` (catch-ups included), log `worker.lease_acquired`. On SIGTERM: stop the scheduler from taking new runs, wait up to 60 s for the running job, release.
- Steps trader standby: start the quote feed; resolve `StrategyAppService` with `trading=False` (bars reach strategies, signals are discarded); bootstrap instances; warm every subscription desired `running` (7.3) without connecting a broker; buffer live completed bars per key while warming and replay those after the Mongo bars, so no bar between them is lost; `role_state=standby`, log `trader.standby` and `trader.warm_done`. No broker connect, no events WS, no reconcile loop, no collector, no sweeps (an events stream in standby would see the owner's fills as unknown and block instruments, `exness_broker_adapter.py:506-511`).
- Steps trader takeover (lease acquired): log `trader.lease_acquired` with `handover_gap_ms = acquired_at - previous released_at`; `PositionAppService.reload()`; `OrderAppService.load_pending_orders()`; restore paper pools (7.2); seed directions from the mirror; connect brokers of running strategies; start the collector and the reconcile loop; `trading=True`; log `trader.trading` with `takeover_ms`. Opens stay refused until the Exness snapshot reconciles (existing gate).
- Steps trader drain (SIGTERM while holding): log `trader.drain_started`; next 1m boundary B; wait until B + 0.6 s (timer close) and until `_order_tasks`, Exness `_inflight` and any pending snapshot are empty, by B + 30 s; else `trader.drain_retry` and try the next boundary; hard deadline SIGTERM + 150 s → `trader.drain_timeout` ERROR and release anyway; then `trading=False`, stop reconcile, stop strategies, disconnect brokers, release, log `trader.lease_released` with `inflight`, `boundary`, `offset_ms`. A lost lease skips the wait.
- Tests: `tests/app_test/integration/test_trader_handover.py` (real Mongo, fake broker): trader A holds; B starts in standby and sends no order on a signal; A drains at a boundary with `inflight=0`; B takes over and its first post-takeover signal submits; A's renew loss → strategies stopped and opens refused.
- Verify: `uv run python -m pytest tests/app_test/integration/test_trader_handover.py -q` ≥ 4 passed, 0 failed.

**Task 8.4 — Heartbeat backtest sweep (D18)**
- Target: `app/main_extensions.py:132-141` [V]; `backtest_repository.py:92-107` [V]; `engine/backtest/backtest_execution_service.py:71-90` [V].
- Steps: the execution task refreshes `heartbeat_at` every 15 s; `mark_orphaned_started_as_failed(stale_after_s=60)` fails only `started` runs whose `heartbeat_at` (or `created_at` when absent) is older than 60 s; `api` runs it at boot and every 60 s, so a run left by a stopped replica fails within 2 min.
- Tests: `tests/core_test/infra/persistence/test_backtest_orphan_heartbeat.py`: fresh heartbeat kept, stale failed.
- Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_backtest_orphan_heartbeat.py -q` 0 failed.

**Task 8.5 — Health semantics per role**
- Target: `main_extensions.py:372-380` [V]; `deploy/compose.prod.yml:81-86` [V]; `deploy/vps/10-deploy.sh:72` [V].
- Steps: `/health` adds `roles`, `role_state` (`worker: standby|running`; `trader: warming|standby|trading|draining`); HTTP 503 when `status` is `unhealthy` or the trader is `warming` (trader healthy = standby ready). Compose `app`: `stop_grace_period: 180s` (> 150 s drain + disconnect; verifier item 1), healthcheck `interval: 5s`, `start_period: 180s`; `wait_health pocketquant-app 41921 240` (warm-up can take about 90 s).
- Verify: a unit test asserts 503 while warming and 200 in standby: `uv run python -m pytest tests/app_test/unit -q -k health_role` ≥ 2 passed; `grep -c "stop_grace_period: 180s" deploy/compose.prod.yml` prints `1`.

**Task 8.6 — Rewrite the single-worker rule and the config files**
- Target: `CLAUDE.md:15` [V]; `deploy/Dockerfile:61-62`, `deploy/compose.prod.yml:53-57,62-63` [V] comments; `../pocketquant-config/vps/default/.env:31`, `local/remote-db.env:42`, `local/remote-db-local-redis.env:3,47`, `local/all-local.env:34` [V].
- Steps: CLAUDE.md line becomes "**One lease-holding trader and one lease-holding worker** — never `--workers N`; a second trader or worker waits in standby until it holds the Mongo lease." Config: `ENABLE_JOBS=true` deleted from prod `.env` (roles come from compose); local files `ENABLE_JOBS=false` → `APP_ROLES=api` (a local backend never opens a second Exness session; local debugging against prod keeps working through `just tunnel`). Commit and push `pocketquant-config` per the recipe before the master push.
- Verify: `grep -c "Single uvicorn worker" CLAUDE.md` prints `0`; `git -C ../pocketquant-config grep -c ENABLE_JOBS` prints nothing (exit 1).

**Task 8.7 — Deploy A (D-7) and verify**
- Steps: R (this deploy still recreates the fixed-name `app`: the last deploy with a restart gap; paper only). Then mongosh `db.leases.find()`.
- Verify: two docs `worker`, `trader` with the same owner; `docker logs pocketquant-app --since 10m 2>&1 | grep -cE "trader.trading|worker.lease_acquired"` prints `2`; `/health` shows `"role_state"` `trading`.

**Task 8.8 — D17 probes: a second trader and a second worker for 10 min**
- Goal: the Parallelism acceptance row, and a real F1-A overlap on prod.
- Steps: `IMG=$(docker inspect -f '{{.Config.Image}}' pocketquant-app)`; `docker network ls | grep backend` to get the network name; `docker run -d --rm --name pq-probe-trader --network <backend> --env-file /opt/pocketquant/deploy/.env -e TZ=UTC -e APP_ROLES=trader "$IMG" uvicorn pocketquant.app.main:app --host 0.0.0.0 --port 41921`; after 10 min save its logs and `docker stop` it (it never held the lease, so it exits without drain). Repeat with `APP_ROLES=worker` as `pq-probe-worker`.
- Verify: trader probe log: `trader.standby` ≥ 1 and `0` for each of `trader.lease_acquired`, `exness.order_submitted`, `position_opened`, `position_closed`, `orphan_backtest_recovery`, `orphan_jobs_recovered`; worker probe: `worker.standby` ≥ 1, `scheduler.started` `0`; prod `app` in the window: 0 `exness_ws.reconnecting`; `db.leases` owners unchanged.

Rollback: `git revert` + R (the old image ignores `db.leases`; delete the collection afterwards with an [ASK]). Config: revert the `pocketquant-config` commit first.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 09 — Compose split, nginx, rolling deploy, one-time cutover (Deploy B)

Entry gate: Phase 08 verified, including 8.8. Read-only check first: `ssh ... "docker compose version && docker version -f '{{.Server.Version}}' && nproc && free -g | awk '/Mem:/{print \$2}'"` — record; Compose must be v2 (researcher unresolved 1); record whether the host is the 8 vCPU / 16 GB target (U3).

**Task 9.1 — Three services from one image**
- Target: `deploy/compose.prod.yml:4-14,53-91` [V].
- Steps: replace `app` with `api`, `worker`, `trader` sharing one YAML anchor (image, `env_file`, `TZ`, networks, mongodb/redis `depends_on`, logging); no `container_name` on any of them or on `web`; per service `environment`: `APP_ROLES` and `EXNESS_RATE_FRACTION` = `api` 0.05, `worker` 0.3, `trader` 0.6 (F3-A); `api` command adds `--timeout-graceful-shutdown 10`, `stop_grace_period: 30s`; `worker` `stop_grace_period: 90s`; `trader` `stop_grace_period: 180s`, healthcheck `start_period: 180s`; all healthchecks `interval: 5s`; `web.depends_on` → `api` (verifier item 8).
- Verify: `uv run python -c "import yaml;d=yaml.safe_load(open('deploy/compose.prod.yml'))['services'];assert 'app' not in d;assert all('container_name' not in d[s] for s in ('api','worker','trader','web'));assert 'api' in d['web']['depends_on'];print('ok')"` prints `ok`.

**Task 9.2 — `sync_1m` at second 12**
- Target: `engine/market_data/app_services/sync_jobs.py:703-708` [V].
- Steps: `second=2` → `second=12` (worker's minute burst leaves the 1m entry window); the job is re-registered with `replace_existing=True` on worker start (`scheduler.py:194-202` [V]).
- Verify: `grep -A4 'job_id="sync_1m"' src/pocketquant/engine/market_data/app_services/sync_jobs.py | grep -c "second=12"` prints `1`.

**Task 9.3 — nginx re-resolves `api`**
- Target: `web/nginx.conf:24-41` [V].
- Steps: in `server`: `resolver 127.0.0.11 valid=5s ipv6=off;`; in `location /api/`: `set $api_upstream http://api:41921;` and `proxy_pass $api_upstream;` (no URI part), `proxy_connect_timeout 2s;`, `proxy_next_upstream error timeout;`; no static `proxy_pass` to `api` anywhere (it would pin the IP).
- Verify: `MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd)/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t` ends with `test is successful`; `grep -c "proxy_pass http://" web/nginx.conf` prints `0`.

**Task 9.4 — Rolling deploy script with image guard, probe and log capture**
- Target: `deploy/vps/10-deploy.sh:45-78` [V].
- Steps: (1) `PROJECT=${COMPOSE_PROJECT_NAME:-pocketquant-prod}`, `dc()` wrapper with `-p "$PROJECT"`; (2) image guard: `docker run --rm "$IMG" python -c "import pocketquant.core.infra.persistence.lease"` must succeed, else exit 1 with "image predates leases: roll back by reverting compose too" (an old image under this compose would run three unleased full runtimes); (3) the researcher's `roll <svc> <timeout>` (remove exited/created containers first; capture old id; `up -d --no-deps --no-recreate --scale svc=2`; wait for `healthy`; on timeout print logs, stop and remove the new one, exit 1; else save `docker logs "$old"` gzipped to `deploy/reports/containers/<svc>-<id12>-<ts>.log.gz`, then `docker stop "$old"` (honours `stop_grace_period`) and `docker rm`); never scale down with `--no-recreate`; (4) order `roll api 120; roll worker 120; roll trader 240; roll web 60; dc up -d --remove-orphans`; (5) a probe container (`curlimages/curl` pinned by digest [UNVERIFIED digest: resolve at write time]) on the backend network requests `http://web:80/api/v1/market-data/symbols` every 0.5 s from before the first roll to after the last, writing status codes to `deploy/reports/probe-<ts>.txt`; (6) after the trader roll, wait up to 60 s for the new trader's `/health` `role_state=trading`, else exit 1.
- Verify: `bash -n deploy/vps/10-deploy.sh` prints nothing and exits 0; `grep -c "pocketquant-app" deploy/vps/10-deploy.sh` prints `1` (the cutover branch only, 9.5).

**Task 9.5 — One-time cutover branch (app → api/worker/trader)**
- Goal: switch topology with no gap, using Deploy A's leases.
- Target: `deploy/vps/10-deploy.sh`.
- Steps, run only when a container named `pocketquant-app` exists: (1) `dc up -d --no-deps api worker trader`; wait `api` healthy, `worker` healthy (`standby`), `trader` healthy (`standby`: warm, no lease); (2) `dc up -d --no-deps web` (new nginx → `api`; the old web keeps its fixed name, so this is one recreate gap of a few seconds, see R6); (3) `docker logs pocketquant-app > deploy/reports/containers/app-final-<ts>.log` then `docker stop pocketquant-app` (its `StopTimeout` is 180 s from Deploy A, so it drains the trader at a boundary and releases both leases); (4) `docker rm pocketquant-app`; (5) wait for `trader.trading` and `worker.lease_acquired` in the new containers (≤ 60 s); (6) `dc up -d --remove-orphans`. The branch is deleted in 9.9.
- Verify: `bash -n deploy/vps/10-deploy.sh` exits 0.

**Task 9.6 — Verify script follows the services**
- Target: `deploy/vps/11-verify.sh:67,79,93,110,120,172,177,188,228,240` [V] (the researcher's line numbers `145...318` do not match this file).
- Steps: resolve ids with `dc ps -q api|worker|trader`; check each is running and healthy; exactly one container per role (`dc ps -q <svc> | wc -l` = 1); `/health` of each role: `trader` `role_state=trading`, `worker` `running`; mongosh `db.leases.countDocuments({expires_at:{$gt:new Date()}})` = 2; the latest `probe-*.txt` has 0 non-200 lines; logs checks per container.
- Verify: `bash -n deploy/vps/11-verify.sh` exits 0; `grep -c "pocketquant-app" deploy/vps/11-verify.sh` prints `0`.

**Task 9.7 — Local rehearsal on Docker Desktop**
- Goal: prove roll + cutover before prod (the research ran on a simulated backend).
- Steps: build `docker build -f deploy/Dockerfile -t pq:rehearsal .` and the web image; in `.cache/rehearsal/` copy the Phase 08 compose (`git show <phase-08 commit>:deploy/compose.prod.yml`) and the new compose, an `.env` from `pocketquant-config/local/all-local.env` with Mongo/Redis pointed at the project's own `mongodb`/`redis` services and no Exness keys; `COMPOSE_PROJECT_NAME=pqrehearsal`; start the old compose (`app`, `web`, `mongodb`, `redis`; not `cloudflared`), add one Binance paper subscription, then run the new script with pulls skipped by editing the copy only; then run it a second time (a normal roll).
- Success: both runs exit 0; probe files show 0 non-200; app/trader logs show `trader.lease_released inflight=0` and the new `trader.trading`.
- Verify: `grep -vc "^200$" .cache/rehearsal/reports/probe-*.txt` prints `0` for each file; then `docker compose -p pqrehearsal down -v` (stop what you started).

**Task 9.8 — Docs for the new topology**
- Target: `docs/deployment.md:13-55,138-180` [V] (deploy flow, verify commands, "Restart while live": a deploy no longer needs stopping `exness` subscriptions, but the pause step stays; rollback across the cutover); `docs/system-architecture.md:43-54,235-237` [V]; `README.md:52-56`; `docs/codebase-summary.md`; script docstrings using `docker exec pocketquant-app` (`scripts/audit_bar_quality.py:15,24`, `scripts/backfill/binance_bars.py:32`, `scripts/backfill/provider_bars.py:13` [V]) → `docker exec $(dc ps -q api)`; backfill scripts run with `--rate-fraction 0.05` while the worker runs (fractions must sum ≤ 1).
- Verify: `grep -rc "pocketquant-app" docs README.md scripts | grep -v ":0"` prints nothing; every doc stays under 800 lines (`wc -l docs/*.md`).

**Task 9.9 — Deploy B (D-8, the cutover), then delete the cutover branch (D-9)**
- Steps: [ASK] "Cut over prod from `app` to `api`/`worker`/`trader` now (Mon-Fri 06:00-11:00Z or 14:00-20:00Z)? Recommended: yes". R. Verify. Then delete the 9.5 branch (dead code) and ship it with R as D-9, which is the first fully rolled deploy.
- Verify: after D-8 and D-9: verdict `0 failures`; `ssh ... "docker ps --format '{{.Names}}' | grep -cE 'pocketquant-prod-(api|worker|trader)-'"` prints `3`; `grep -c "pocketquant-app" deploy/vps/10-deploy.sh` prints `0`.

Rollback: before D-8 lands: revert. After D-8: `git revert` the Phase 09 commits (restores the `app` service and the old scripts) + R; the old script's `up --remove-orphans` removes the three services with their grace periods (they drain and release), and the `app` container (Deploy A image, lease-aware) takes both leases. Never pin `IMAGE_TAG` alone across this boundary: the guard in 9.4 refuses a pre-lease image, and a lease-aware image under the wrong compose is still single-owner but untested.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 10 — Prod verification: 10 handovers, 14 days of paper

Entry gate: D-9 verified. Deploys counted here are real releases or owner-approved `gh workflow run cicd.yml --ref master` dispatches, each [ASK] (every run deploys; never test-dispatch). Market hours = Mon-Fri 06:00-20:00Z outside the cron hours.

**Task 10.1 — Per-deploy handover record (repeat until 10 qualifying deploys)**
- Steps: after each deploy, from the saved old-trader log and the new trader: `trader.lease_released` (`inflight`, `offset_ms`), `trader.lease_acquired` (`handover_gap_ms`), `trader.trading` (`takeover_ms`), `strategy.entry_skipped reason=gap` on bars whose `bar_start` falls within 5 min of the handover, probe non-200 count. Append one row to `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`. For two of the ten, also probe the public SPA domain every 0.5 s from the workstation (cloudflared → web path, R6).
- Verify per row: `inflight=0`; `0 <= offset_ms <= 30000`; `handover_gap_ms <= 2000`; `takeover_ms <= 5000`; gap skips `0`; probe non-200 `0`. Any row failing → Failure Protocol.

**Task 10.2 — Daily paper checks for 14 days**
- Steps: each day after 13:00Z, collect from live and saved container logs (`deploy/reports/containers/`, since rolls remove containers and their logs): trader `event_loop.lag` lines with `lag_s >= 0.5`; "Error notifying listener"; `exness.rate_limited_retry`; terminal `exness.rate_limited` on order ops; `strategy.entry_skipped` by reason; `live.signal_latency` T0→T5 p95 on 1m Exness-symbol subscriptions; `trader.drain_timeout`; `lease.lost`; mongosh `db.leases.find()`. Append a row to `reports/paper-daily.md`.
- Verify per day: lag lines `0`; listener errors `0`; terminal 429 on order ops `0`; T0→T5 p95 ≤ 1.0 s; `drain_timeout` `0`; `lease.lost` `0`; exactly two lease docs. Rolling 7-day `exness.rate_limited_retry` sum ≤ 72.

**Task 10.3 — 7-day job metrics after TV removal**
- Verify: mongosh p50 of `sync_integrity` duration over the last 7 days < 10 s and `sync_repair` < 120 s; `skipped_max_instances` rows exist for every really dropped run (cross-check with `job_history` gaps).

Rollback: none (observation). A failing day stops the clock; the 14 days restart after the fix ships.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

### Phase 11 — Re-arm live gate (pointer only)

Entry gate: Phase 10 PASS (10 handover rows, 14 paper days); owner [ASK] to start.

**Task 11.1 — Re-run the go-live phases**
- Steps: re-run `plans/261019-1957-exness-go-live/phase-11-go-live-one-strategy.md` and `phase-12-observation-and-go-live.md` as written (`--from 11 --to 12`); do not copy them here. Replace every `pocketquant-app` in their commands with the role container (`api` for admin calls, `trader` for broker logs) at run time.
- Verify: as defined in those phases.

**Task 11.2 — D12 live minimum-lot canary**
- Steps: within the go-live run, with the smallest lot and a tight SL, collect `live.signal_latency` for the first 20 live entries.
- Verify: T0→T6 p95 ≤ 2.0 s over those 20 entries; 0 terminal `exness.rate_limited`. Failing → pause entries (stored pause) and Failure Protocol.

Rollback: the go-live plan's own rollback and the stored pause.

#### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry with a variation, do not start the next task, do not push.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same five items to the user.

## 4. Test matrix

| Level | What | Where |
|---|---|---|
| Unit | loop probe, skip listener, pacer, health per role, bar timer/seed/gap, entry skip, latency line, warm-up, paper restore, risk opposite | Phases 02, 05-08 test files named above |
| Integration (real Mongo/Redis via Docker) | safeguards route ↔ broker, lease contention, trader handover, heartbeat sweep, existing reconcile/standalone runtime tests | Phases 04, 08 |
| Rehearsal | roll + cutover on Docker Desktop | Task 9.7 |
| Prod E2E | D17 probes, cutover, 10 handovers, 14 paper days, D12 canary | Tasks 8.8, 9.9, 10.x, 11.2 |

## 5. Risks

| # | Risk | L × I | Mitigation | Phase |
|---|---|---|---|---|
| R1 | A second ticks session disturbs prod's (researcher probe coincided with all 4 breaker opens) | M × H | Spike first (01); real overlap again in 8.8; FAIL stops for the D24 account decision | 01, 08 |
| R2 | Standby trader runs a boot side effect against the live trader (paper-row delete, orphan sweeps) | H × H if missed | Paper delete removed in 07 before standby exists; sweeps run only after the lease (8.3, 8.4); 8.8 probe proves 0 such lines | 07, 08 |
| R3 | `stop_grace_period` shorter than the drain → SIGKILL mid-order | M × H | Drain hard deadline 150 s < grace 180 s; Deploy A sets 180 s on `app` so the cutover stop also drains | 08, 09 |
| R4 | Emergency `IMAGE_TAG` pin of a pre-lease image under the split compose → three unleased runtimes | L × H | Image guard in 9.4; rollback = revert compose and scripts together | 09 |
| R5 | nginx pins the old `api` IP | M × M | Variable `proxy_pass` + `resolver valid=5s`, connect timeout 2 s; probe per deploy | 09 |
| R6 | `web` and `cloudflared` gap: web was fixed-name; cloudflared DNS caching of `web` is [UNVERIFIED] | M × M | Roll `web` too; measure the public path in 10.1; if cloudflared keeps the old IP, ask the owner whether a short web gap is acceptable or cloudflared needs a restart step | 09, 10 |
| R7 | Pacer bound: k-th concurrent open waits (k−1) × 0.5 s | M × M | 6.3; D12 canary measures real T0→T6 | 06, 11 |
| R8 | Cluster-wide 429s from worker crons at second 0 (hourly, 00/03/04/12Z) overlapping 15m/1h entries | M × M | Fractions sum 0.95; `sync_1m` moved; if the D19 gate fails, offset the other crons to second 12 (owner decision, not in scope by default) | 09, 10 |
| R9 | Timer close with clock skew > 0.5 s | L × M | NTP gate 5.1; T2−T0 check in 5.6 | 05 |
| R10 | Synchronous loss-cap read after a close costs ~2 s on the next entry | M × L | Accepted (verifier item 5); refresh tightening if 1m entries cluster | 06 |
| R11 | Prod data deletion is irreversible | L × H | Full gzip archive + dry-run restore check + counts before delete | 03 |
| R12 | Logs of removed containers are lost, so 7-day counts undercount | H × M | `roll` saves each old container's log; daily rows | 09, 10 |
| R13 | Migrations run in the new `api` while the old one serves | L × M | Expand-then-contract only; the new fields here are optional | 07-09 |
| R14 | Lease owner clock: `expires_at` from container clocks | L × M | One host, one kernel clock [I]; NTP gate | 08 |

## 6. Unresolved

1. **U1 Journals and the TV `rg`:** `docs/journals/2026-09-21-asset-class-trading-calendar.md` matches the TV pattern [V]. Journals are dated records; this plan excludes `docs/journals/**` from the criterion. Owner: confirm, or ask to edit the journal.
2. **U2 Import-linter count:** the criterion said 8 contracts; two police the deleted dependencies (`pyproject.toml:142-176` [V]) and are deleted, leaving 6. Owner: confirm.
3. **U3 Host size:** prod measured 2 vCPU / 3.9 GB on 2026-10-28 (kongming §0). Is the 8 vCPU / 16 GB host (D5) already in place, or is a VPS migration part of this delivery? The plan does not move hosts.
4. **U4 Stale budgets for 5m/4h/1d/1w:** D10 names only 1m/15m/1h; the plan uses 120 s for the others.
5. **U5 Pacer change (6.3):** pacing order ops by `openPosition`'s 4/s limit is my answer to D21 with more than 2 live 1m subscriptions; it raises the trader's peak request rate. Confirm, or accept (k−1) × 1.0 s spacing.
6. **U6 Public web gap (R6):** if cloudflared does not follow a rolled `web`, is a few seconds of public downtime per deploy acceptable?
7. **U7 Phase 01 FAIL path:** a second Exness account (D24) means separate quote credentials for the standby; that design is not in this plan.
8. **U8 Exness questions that stay open:** `EXN-IDEMPOTENCY-KEY` retention and close-only candles stay unknown and non-blocking (no order retries; indices out).
