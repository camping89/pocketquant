---
title: "Candidate 2: Exness-only data, api/worker/trader split, zero-downtime trader handover"
description: "Money-path-first plan: fail-closed pause, per-order lease fence, inflight drain at a bar boundary, stale/gap guards, close-path deletion, then the role split and rolling deploy."
status: pending
priority: P1
effort: "about 11 dev days + 14 calendar days of paper observation"
branch: develop
tags: [exness, tradingview-removal, parallel-runtime, lease, handover, money-path]
created: 2026-10-28
---

# Candidate 2 (lens: money-path safety)

Labels: **[V]** checked in source at the cited `file:line` on `develop` @ 453e8e90 today. **[I]** my inference. **[UNVERIFIED]** not checked; the executor must confirm before relying on it. All times are UTC.

## 1. Overview

### Outcome
- One host runs `api`, `worker` and `trader` from one image. `worker` and `trader` each act only while they hold a Mongo lease. A trader without the lease is in standby and never sends an order.
- TradingView, the CME calendar, `ES1!/NQ1!/YM1!:TRADINGVIEW`, subscription `01a178ef-5027-73ba-a98e-b7d6de8e2cc9` and their data are gone (D1, D4). US indices are not added in this delivery (D22, D23).
- Exness is the only live venue and the only FX/metals/CFD data source; Binance stays data + paper (D3).
- A 1m entry reaches Exness within about 2 s of the bar end (D2). Opens on one boundary do not add up to N x call latency (D21).
- A deploy restarts every role with no missed bar and no missed or duplicate order; the trader hands over at a 1m boundary after its in-flight orders drain (D7, D8).

### Constraints
- Owner decisions D1-D24 bind. `CLAUDE.md` limits bind, with D16 applied first (Phase 01): net line count is not a stop gate.
- No free-threaded Python, no `--workers N`, no Redis Streams, no shared Redis pacer, no Mongo replica set.
- Primary keys stay UUIDv7: the lease document gets a UUIDv7 `_id` and a unique index on `name` (no natural key).
- Every master push deploys prod and is an [ASK] that leads with `Recommended: <reply>`. Never deploy within 30 min of 00:00, 03:00, 04:00 or 12:00.
- Local debugging against the remote DB must keep working: `remote-db.env` moves from `ENABLE_JOBS=false` to `APP_ROLES=api`.

### Non-goals
A trader per venue; a process pool or symbol sharding; deterministic order ids (H1b, contract section 3; see Unresolved U3); retrying an order after a 429; moving backtests to the worker; keeping ES history; the CME bisect rewrite; US index onboarding (D23).

### Acceptance criteria (report section 4 with D19-D24 applied; Indices row removed)

| Area | Criterion | Proven in |
|---|---|---|
| Stalls | `/health` reports `event_loop_lag_max_s` per role; 0 `event_loop.lag` WARNINGs with `lag_s >= 0.5` from `trader` on any day, including 00:00, 03:00, 04:00, 12:00. After TV removal `sync_integrity` p50 < 10 s and `sync_repair` < 120 s (`job_history`). 0 "Error notifying listener" lines; `skipped_max_instances` rows appear when a run is dropped. | P01, P11 |
| Parallelism | `docker ps` shows `api`, `worker`, `trader`. `db.leases.find()` returns one owner each for `worker` and `trader`. A second trader against prod Mongo for 10 min logs `trader.standby`, sends 0 orders, makes 0 order/position/trade writes, runs no sweep. A second worker starts no scheduler (`scheduler.started` count 1). | P08 (CI), P10 (prod) |
| TV removal | `rg -i "tradingview\|cme_globex\|pandas_market_calendars\|seed_index_futures" src tests web/src docs pyproject.toml --glob '!docs/journals/**'` returns 0 hits. Mongo `tracked_symbols` and `bars` have 0 rows matching `/TRADINGVIEW$/`; subscription `01a178ef` is gone. `lint-imports`: 6 contracts kept, 0 broken (two TV/CME contracts are deleted with their libraries, `pyproject.toml:141-175` [V]). | P03, P04 |
| C1 | CI: a pause through the `api` route makes the trader's next open refused; a failed store read refuses the open; the pause route returns 503 when the store write fails; `Safeguards` has no `entries_paused` field. | P05 |
| C2 | CI: of two lease contenders only one acquires; a lost renewal stops strategies, refuses opens and exits the process; an order is refused when the lease has under 5 s left. | P08 |
| H1 | CI: a second signal for a subscription is rejected while an Exness `_inflight` open exists for it, and while the engine still runs that subscription's order task. | P05, P06 |
| H2 / D10 | CI with a fake clock: a 1m bar 11 s late (15m 61 s, 1h 121 s) skips the entry and logs exactly one `strategy.entry_skipped reason=stale`; at 10/60/120 s the order goes out. Paper SL/TP still runs on that bar. | P06 |
| H3 / D10 | CI: a bucket that is not the calendar successor of the last one, a trading-time tick silence over 60 s, or a mid-bucket start without a fresh Redis seed logs `reason=gap` and skips the entry. Prod: `strategy.entry_skipped` counted per week. | P06, P11 |
| M1 / 1m latency | CI: with fresh caches the open path makes exactly 1 REST call (`openPosition`). Prod paper: `live.signal_latency` p95 of `t0_t5_ms` <= 1000 on 1m Exness symbols. Before live: D12 canary, first 20 entries, `t0_t6_ms` p95 <= 2000. | P05, P11, P12 |
| M2 / D21 | CI: two subscriptions signal on one bar; their check-and-register sections run one after the other while the `openPosition` sends overlap (D21 supersedes "opens one after the other"). Three opens on one boundary all leave within 0.7 s. A close fill marks the loss cap stale; the next open re-reads it synchronously or refuses. | P05, P06 |
| M3 / D9 / D11 | CI: after a restart with a LONG mirror row the strategy direction is LONG; an opposite order is rejected and never becomes a close (`closePosition` no longer exists). hitnrun2 trades on the first live bar after a restart. | P05, P07 |
| D13 | CI: after a closed paper round trip, a restart rebuilds the paper balance to the pre-restart value; a restored open paper position keeps its SL/TP and exits on the next bar that crosses it. | P07 |
| Handover (D8) | Over 10 deploys in market hours: every `trader.lease_released` has `inflight=0` and `offset_s` in [0, 30] after a 1m boundary; `handover_gap_ms` <= 2000; `takeover_ms` <= 5000; 0 `reason=gap` skips on bars that span a handover; a probe hitting `/api/v1/market-data/symbols` through `web` every 0.5 s during the role roll sees 0 non-200. | P10 |
| Rate budget (D19) | 0 terminal `exness.rate_limited` on order operations; `exness.rate_limited_retry` <= 72 per 7 days. | P11 |

The contract row names `/api/health`; that route does not exist (health is `/health` at `app/main_extensions.py:372`, nginx proxies only `/api/` at `web/nginx.conf:25-26`) [V]. The probe therefore uses a public GET that already exists (`deploy/vps/11-verify.sh:110`) [V].

## 2. Key design decisions (money path)

1. **Pause is read from Mongo on every open and fails closed** (C1). The in-memory flag, the boot load (`app/di/adapters.py:58`) and the route's double write (`app/routes/safeguards.py:43-49`) are deleted [V].
2. **Per-order lease fence.** `StrategyAppService._process_signal` refuses to call `OrderAppService.submit` unless the trader is trading and its lease has more than 5 s left (TTL 30 s, renew every 10 s). The check uses the local copy of `expires_at`, so a frozen loop that missed renewals is refused on wake-up [I].
3. **Standby never connects a broker** (contract section 6.5): standby builds bars, warms strategies and discards their signals; brokers connect only in `begin_trading` after the lease is taken.
4. **Drain at the boundary.** On SIGTERM the old trader waits for the next 1m boundary B + 1.0 s, then for its order tasks and every venue broker to be idle (no `_inflight`, no `_pending_ack`, no pending snapshot), up to B + 30 s; it retries once at the next boundary, then releases with an ERROR `trader.handover_forced`. The fail-safe after a forced release is the existing snapshot gate plus unknown-fill instrument block (`exness_broker_adapter.py:256-257,506-511`) [V].
5. **No close path.** The opposite-side close branch (`exness_broker_adapter.py:205-214`) and `closePosition` (`exness_client.py:57,59`) are deleted (D11) [V]; any held position rejects a new order for that subscription.
6. **Two duplicate-entry layers** (H1): the engine keeps one order task per subscription (strong reference, H1 check, drain predicate); the Exness adapter refuses an open while an `_inflight` open exists for the subscription.
7. **Concurrent opens without races** (M2 + D21): bar events are published after the bar lock is released; venue-broker signals run as tasks; the Exness adapter serializes only the cheap check-and-register section under an account lock; the pacer spaces order calls by the order/global limits, not the strictest data limit (today all calls share 0.6 s / fraction, `exness_client.py:116-120,355` [V]).
8. **Guards live where the data is**: gap facts are computed in `BarAppService` (it owns the calendar and the builders) and carried on `BarCompletedEvent`; the stale budget and skip decision live in `StrategyAppService`. Backtest events carry no `bar_end`, so the guards never fire in backtests (`engine/backtest/backtest_app_service.py:125-137` publishes without it [V]).

## 3. Phases (file order = run order)

| # | Phase | Effort | Entry gate |
|---|---|---|---|
| 01 | Truth and observability: loop-lag probe, skip listener, C3 docstrings, `python:3.14-slim`, D16 rule | 0.5d | none |
| 02 | Two ticks WS sessions spike on one key/account (D15, D24, D17) | 2h + 20 min run | P01 deployed |
| 03 | Prod data removal: stop `01a178ef`, delete the 3 TV symbols via the API | 0.5h | P01; [ASK] |
| 04 | TradingView/CME code removal and deploy | 1d | P03 |
| 05 | Exness adapter money path: C1, D11/M3 rejection, H1, M1 caches, M2 lock, order pacing | 1.5d | P04 |
| 06 | Bar pipeline: timer close, H2 stale, H3 gap + Redis seed, publish outside lock, concurrent opens, `live.signal_latency` | 1.5d | P05 |
| 07 | State rebuild (D9 warm-up, direction seed, D13 paper restore) and single-process deploy | 1d | P06; NTP synced |
| 08 | Roles and leases: `APP_ROLES`, worker/trader lease, fence, standby, takeover, drain, heartbeat sweep, `sync_1m` second 12 | 2d | P07 in prod; P02 decision `F1: A` |
| 09 | Topology and cutover: compose, nginx, rolling deploy, `app` -> `api/worker/trader`, docs, `CLAUDE.md` | 1d | P08 CI green; [ASK] |
| 10 | Prod handover verification: 10 deploys, second trader/worker probes | 1d over 2-3 days | P09 in prod |
| 11 | 14 days of paper observation (re-runnable daily) | 15 min/day | P10 PASS |
| 12 | Re-arm live gate: re-run go-live phases 11-12 plus the D12 canary | per go-live plan | P11 PASS x 14 days |

Phases are strictly sequential; no two run in parallel, so file ownership never overlaps.

### Shared commands (used by every phase)
- Tests need Docker: run `docker ps`; if it fails start Docker Desktop and retry after 10 s. Full suite: `just test` (fallback `uv run python -m pytest tests/ -q`). **Expected local Windows red is exactly `4 failed, 4 errors`, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.** Any other red is a failure.
- Gates: `uv run ruff check src tests` -> `All checks passed!`; `uv run ruff format --check src tests` -> `... files already formatted`; `uv run pyright` -> `0 errors`; `uv run lint-imports` -> `Contracts: 8 kept, 0 broken.` (6 from Phase 04 on); `uv run python scripts/code_metrics.py --ratchet` -> exit 0 (if a ceiling trips, raise it in its own commit, never pad code).
- Push and deploy: the "Ops recipe" in `plans/261019-1957-exness-go-live/plan.md:34-50` (token URL push, `git fetch origin`, `GH_TOKEN` on every `gh` call, `sleep 15` before a run-id lookup, verify verdict grep). SSH key copy and `rm -f .cache/ssh/vps_key` at phase end. Until Phase 09 lands, admin calls use `docker exec -i pocketquant-app`; from Phase 09 on, `docker compose -f compose.prod.yml --env-file .env exec -T api`.

---

## Phase 01 - Truth and observability

Entry gate: none. Rollback: revert the commit and redeploy the previous tag; no data change.

**T1.1 Loop-lag probe.** Goal: every role reports loop stalls.
- Targets: `src/pocketquant/app/main_extensions.py` (new `start_loop_lag_probe(app)`, `stop_loop_lag_probe(app)`), `src/pocketquant/app/main.py` lifespan, `/health` handler (`main_extensions.py:372-380`).
- Steps: (1) task loop: `t0 = loop.time(); await asyncio.sleep(1.0); lag = loop.time() - t0 - 1.0`; keep `(monotonic, lag)` samples for the last 60 s on `app.state.loop_lag`. (2) When `lag >= 0.25` log one `logger.warning("event_loop.lag", lag_s=round(lag, 3))`. (3) `/health` adds top-level `event_loop_lag_max_s` = max of the 60 s window (0.0 if empty). (4) Start first thing after `assert_utc_runtime()`, stop first in `finally`.
- Test: `tests/app_test/unit/test_loop_lag_probe.py`: block the loop with `time.sleep(0.6)` once; assert window max >= 0.5 and exactly one `event_loop.lag` record.
- Success: `/health` JSON has `event_loop_lag_max_s`.
- Verify: `uv run python -m pytest tests/app_test/unit/test_loop_lag_probe.py -q` -> `1 passed`.

**T1.2 Skip listener.** Goal: dropped runs become `job_history` rows; a failed write is logged.
- Targets: `src/pocketquant/core/infra/scheduling/scheduler.py:95-99` (`_on_skip`), `:117-135` (`_dispatch_skip`).
- Steps: (1) `run_time = event.scheduled_run_times[-1] if event.code == EVENT_JOB_MAX_INSTANCES else event.scheduled_run_time`. (2) Keep the future from `run_coroutine_threadsafe`; add a done-callback that logs `scheduler.record_skip_failed` (WARNING, `job_id`, error type) when the future raised.
- Test: `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py`: build `JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "sync_1m", "default", [t])` and a `JobExecutionEvent(EVENT_JOB_MISSED, ...)`, a fake history repo, a running loop; assert `record_skip` got `t` and status `skipped_max_instances` / `missed`; a raising repo produces one `scheduler.record_skip_failed`.
- Verify: `uv run python -m pytest tests/core_test/infra/scheduling/test_scheduler_skip_listener.py -q` -> `3 passed`.

**T1.3 C3: stop claiming a shared job store is safe.** Goal: no file says two schedulers may share `apscheduler_jobs`.
- Targets: `scheduler.py:3-5` and `:53-55`; `engine/market_data/app_services/sync_jobs.py:641-643`; `docs/system-architecture.md:229`; `docs/deployment.md:221`; `docs/project-overview-pdr.md:110`.
- Steps: replace each claim with: "Exactly one process runs the scheduler. APScheduler 3 does not support two schedulers on one job store."
- Verify: `rg -n "distributed coordination|first to update|Multi-instance safe|coordinate through it|coordinate via the shared" src docs` -> no output.

**T1.4 Release base image.** Targets: `deploy/Dockerfile:4,28`. Steps: `python:3.14-rc-slim` -> `python:3.14-slim`. Verify: `rg -n "rc-slim" deploy` -> no output.

**T1.5 D16 rule rewrite.** Targets: `CLAUDE.md:26`. Steps: replace the line with `  - Keep it simple: write the smallest code that meets the requirement; a change may be longer than the code it replaces when the requirement needs it.` Verify: `rg -n "more code than the code it replaces" CLAUDE.md` -> no output.

**T1.6 Gates and push develop.** Verify: Shared commands; `just test` -> exactly `4 failed, 4 errors` in the two tz files; CI run on `develop` green (`gh run view <id> --json conclusion -q .conclusion` -> `success`).

**T1.7 Deploy [ASK] `Recommended: yes`.** Goal: probe and fix live in prod. Steps: push `develop:master` outside the forbidden windows; wait for CI. Success and Verify (each over SSH):
- `docker exec pocketquant-app python -c "import sys; print(sys.version.split()[0])"` -> starts with `3.14.` and contains no `rc`.
- `docker exec pocketquant-app curl -s http://localhost:41921/health | grep -c event_loop_lag_max_s` -> `1`.
- verify verdict grep (Ops recipe) -> a number >= 1.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 02 - Two ticks WS sessions spike (D15, D24, D17)

Entry gate: Phase 01 in prod (lag and reconnect logs visible). This phase runs before any handover code. `EXNESS_LIVE_TRADING` is off, so no real trade is at risk (D17). Rollback: stop the script; nothing is stored.

**T2.1 Spike script.** Goal: measure whether a second ticks session on the same key and account drops or delays the first.
- Targets: new uncommitted `.cache/spike/two_tick_sessions.py` (`.cache` is git-ignored; check `git check-ignore -q .cache/spike/two_tick_sessions.py && echo ignored` -> `ignored`).
- Steps: (1) Build one `ExnessClient(get_settings())` and two `ExnessQuoteAdapter` instances A and B (`core/infra/exness/exness_quote_adapter.py:54-108` [V]); subscribe only `XAUUSD:EXNESS`, `EURUSD:EXNESS`, `BTCUSD:EXNESS` (in `EXNESS_INSTRUMENTS`, so no strike). (2) Record every tick per session as `(instrument, venue timestamp, bid, ask, monotonic receive time)`; capture `exness_ws.*` log events per session. (3) Timeline: A alone 5 min, A+B 10 min, A alone 5 min. With prod's own session that is 3 concurrent sessions, a superset of the 2-session handover [I]. (4) Write JSON: per phase tick counts per instrument, A-vs-B symmetric difference during overlap, receive-time delta p50/p99 for ticks seen by both, reconnect/circuit events per session.
- Verify: `uv run python -m py_compile .cache/spike/two_tick_sessions.py && echo ok` -> `ok`.

**T2.2 Run on the VPS.** Steps: in a liquid window (13:00-16:00, Monday-Thursday): `docker cp` the script into `pocketquant-app`, run it with `docker exec -d pocketquant-app python /tmp/two_tick_sessions.py --out /tmp/spike.json`, wait 21 min, `docker cp` the JSON back to `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.json`. Count prod reconnects in the window: `docker logs pocketquant-app --since <start> --until <end> 2>&1 | grep -cE "exness_ws\.(reconnecting|circuit_breaker_open|connection_failed)"`.
- Pass condition (all): symmetric difference <= 1% of the union; receive delta p99 <= 250 ms; 0 reconnect/circuit/connection-failed events in A, B and prod; A's ticks/min during overlap >= 90% of the mean of its two solo phases.
- Verify: `test -s plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.json && echo ok` -> `ok`.

**T2.3 Decision record.** Goal: pick F1-A or the fallback from evidence. Steps: write `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` with the numbers, the pass table and one line `F1: A` (all pass) or `F1: fallback` (any fail). On `F1: fallback`, Phases 03-07 still run; Phase 08 does not start until the owner provides a second Exness account for the standby feed (D24) or chooses another fallback.
- Verify: `grep -cE "^F1: (A|fallback)$" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` -> `1`.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 03 - Prod data removal (D1, D4)

Entry gate: Phase 01 in prod. [ASK] before T3.2: "Delete subscription 01a178ef and ES1!/NQ1!/YM1!:TRADINGVIEW with all their bars and backtests now? This cannot be undone. `Recommended: yes`." Rollback: none (accepted by D4).

**T3.1 Baseline counts.** Steps: over SSH run `docker exec -i pocketquant-mongodb sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin pocketquant --quiet --eval "printjson([db.tracked_symbols.countDocuments({symbol:/TRADINGVIEW\$/}), db.bars.countDocuments({symbol:/TRADINGVIEW\$/}), db.subscriptions.countDocuments({symbol:/TRADINGVIEW\$/})])"'`. The field name `symbol` in `tracked_symbols` and `subscriptions` is [UNVERIFIED]; confirm with `findOne()` first. Verify: first and second numbers > 0 (record them).

**T3.2 Stop, then delete through the API.** Steps: (1) `POST /api/v1/subscriptions/01a178ef-5027-73ba-a98e-b7d6de8e2cc9/stop` (`app/routes/strategy.py:96` [V]). (2) `DELETE /api/v1/market-data/tracked-symbols/{ES1%21%3ATRADINGVIEW|NQ1%21%3ATRADINGVIEW|YM1%21%3ATRADINGVIEW}` (`app/routes/market_data.py:296-310`, cascades subscriptions, bars, backtests, orders, positions, trades [V]). Use the Ops-recipe admin call with `X-Admin-Token`.
- Verify: re-run the T3.1 command -> `[ 0, 0, 0 ]`.

**T3.3 Memory note.** Steps: delete `C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md` and its line in that folder's `MEMORY.md` (the note says to delete it after this phase). Verify: `grep -c "es-paper-subscription-kept" C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/MEMORY.md` -> `0`.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 04 - TradingView and CME code removal

Entry gate: Phase 03 verified (no tracked TV symbol is left, so the deploy cannot hit a missing provider). Rollback: revert and redeploy; TV data stays deleted.

**T4.1 Delete files.** Targets: `src/pocketquant/core/infra/tradingview/` (6 modules), `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`, `scripts/seed_index_futures.py`, `tests/core_test/infra/tradingview/`, `tests/app_test/unit/test_tradingview_credentialed.py`, `tests/core_test/infra/calendars/test_cme_globex_calendar.py`. Verify: `ls src/pocketquant/core/infra/tradingview 2>&1 | grep -c "No such file"` -> `1`.

**T4.2 Edit source.** Targets (each verified to mention TV/CME today): `app/di/adapters.py:43-45,76-80,94,100-104,114,120-124`; `app/main_extensions.py:66,275-305` (`_tradingview_credentialed`, the `tradingview` health entries); `core/config.py:73-107`; `core/domain/shared/enums.py` (`TradingViewPlan`, capabilities); `core/domain/market_data/provider_routing_domain_service.py` (`"tradingview"` default); `core/domain/symbol/value_objects.py:21` (`CALENDAR_CME_GLOBEX_EQUITY`) and `core/domain/symbol/__init__.py`; `core/infra/calendars/__init__.py`, `trading_calendar_factory.py`; `core/infra/market_data/provider_health_check.py`; `engine/market_data/app_services/quote_app_service.py` (TV TTL); `engine/market_data/data_lag_service.py`; docstrings in `core/domain/market_data/data_provider_port.py` and `realtime_quote_provider_port.py`; `scripts/backfill/binance_bars.py`, `scripts/README.md`. Steps: delete the TV/CME branch, keep Binance and Exness behaviour unchanged. Verify: `rg -il "tradingview|cme_globex|tvdatafeed" src scripts` -> no output.

**T4.3 Dependencies and contracts.** Targets: `pyproject.toml:13` (`pandas-market-calendars`), `:29-30` (`tvdatafeed`), `:54` (hatch direct-reference note, delete if only for tvdatafeed), `:141-175` (two import-linter contracts); `uv.lock`. Steps: delete, then `uv lock`. Verify: `uv run lint-imports` -> `Contracts: 6 kept, 0 broken.`

**T4.4 Tests.** Targets: the remaining test files that name TV/CME (`rg -il "tradingview|cme_globex" tests` lists them, 31 files today). Steps: where CME is only an example of a session calendar, switch to `CALENDAR_EXNESS_FX` or `CALENDAR_EXNESS_XAUUSD` (`core/domain/symbol/value_objects.py:24-25` [V]) and recompute the expected instants; delete cases that assert CME-only rules (holidays, early closes). Never weaken an assertion to pass. Verify: `rg -il "tradingview|cme_globex" tests` -> no output; `just test` -> exactly the expected local red.

**T4.5 Web.** Targets: `web/src/lib/symbol-format.ts`, `components/chart/trading-chart.tsx`, `components/backtest/backtest-form.tsx`, `components/ticker-widget/ticker-widget.tsx`, `components/data-lag-badge.tsx`, `components/controls/symbol-selector.tsx`, `types/quote.ts`, `types/market-data.ts`, `lib/datetime.test.ts`. Verify: `cd web && npm run lint && npm test && npm run build` -> exit 0 (scripts at `web/package.json:6-12` [V]); `rg -il tradingview web/src` -> no output.

**T4.6 Docs.** Targets: `docs/system-architecture.md`, `docs/deployment.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, `docs/code-standards.md`, `README.md`, `CLAUDE.md:14` ("8 contracts" -> "6 contracts"). Journals are dated records and stay untouched (Unresolved U5). Verify: the TV-removal `rg` command from the acceptance table -> no output.

**T4.7 Gates, push develop, deploy [ASK] `Recommended: yes`.** Verify: Shared commands; CI green; after deploy, `docker logs pocketquant-app --since 10m 2>&1 | grep -cE "ModuleNotFoundError|ImportError"` -> `0`; `docker exec pocketquant-app curl -s http://localhost:41921/health | grep -ci tradingview` -> `0`.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 05 - Exness adapter money path (one process)

Entry gate: Phase 04 merged. All work stays in one process; no role code yet. Rollback: revert the phase commits (no schema change; the safeguards document keeps its shape).

**T5.1 C1: pause read from the store, fail closed.**
- Targets: `core/infra/brokers/exness/exness_safeguards.py:10-31` (drop `entries_paused`, `set_entries_paused`); `app/di/adapters.py:49-59` (drop the boot load); `core/infra/brokers/broker_factory.py:79-84` and `app/di/adapters.py:61-74` (pass `SafeguardsRepository` to the adapter); `exness_broker_adapter.py:98-108,245-253` (`_presubmit_reason`); `app/routes/safeguards.py:24-49`.
- Steps: (1) Adapter gets `safeguards_repository`; inside the open path (T5.5 lock) call `await repo.load_entries_paused()`; any exception -> reject `"entries pause unreadable"` with WARNING `exness.order_rejected_presubmit reason=pause_unreadable`; `True` -> existing `reason=entries_paused` rejection. (2) Route GET returns `asdict(safeguards) | {"entries_paused": await repo.load_entries_paused()}`. (3) POST pause/resume: `await repo.save_entries_paused(p)`; on exception log WARNING `exness.safeguards.pause_store_failed` and raise `HTTPException(503, "pause not stored")`; on success log the existing `exness.safeguards.entries_paused` / `entries_resumed` WARNING and return the GET body. (4) Update the module docstring (`exness_broker_adapter.py:13-14`).
- Tests: update `tests/app_test/integration/test_safeguards_api.py`; new `tests/core_test/infra/brokers/exness/test_exness_pause_store.py`: pause via the route, then a separately built adapter on the same Mongo rejects the open with 0 client calls; a raising repo rejects with `entries pause unreadable`; a raising save makes POST return 503; `"entries_paused" not in Safeguards.__dataclass_fields__`.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_pause_store.py tests/app_test/integration/test_safeguards_api.py -q` -> `0 failed`; `rg -n "entries_paused" src/pocketquant/core/infra/brokers/exness/exness_safeguards.py src/pocketquant/app/di/adapters.py` -> no output.

**T5.2 D11 / M3: delete the close path, reject opposite orders.**
- Targets: `exness_broker_adapter.py:199-214` (`submit_order`), `:80-88` (`_Inflight.kind`), `:397-404`, `:493-499` (match on `kind`), `:534-566` (`_apply_success` close branch), `:568-584` (`_finish`/`_complete` trade hand-off), `:1-10` docstring; `core/infra/exness/exness_client.py:57,59`.
- Steps: (1) `held = self._held_for(sub)`; if held -> `_rejected(order, "position already open for subscription")` whatever the side. (2) Delete `kind` (always open), the close pop in `_apply_success`, the `trade` element of `_early` and the `trade` parameter of `_finish`/`_complete` (broker closes keep `_emit_trade` in `_on_broker_close`, `:516-532`). (3) Delete `closePosition` from `_ENDPOINTS` and `_ORDER_OPS`. (4) Delete or convert close tests in `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py` and `tests/core_test/infra/exness/test_exness_client.py`.
- Tests: a LONG position mapped from a snapshot + repo row, then a SELL with equal quantity -> `REJECTED`, 0 client calls, position kept.
- Verify: `rg -n "closePosition" src` -> no output; `uv run python -m pytest tests/core_test/infra/brokers/exness -q` -> `0 failed`.

**T5.3 H1 (adapter layer).** Targets: `_presubmit_reason` (`exness_broker_adapter.py:245-263`). Steps: reject `"entry already in flight for subscription"` when any `_inflight` entry has `order.subscription_id == order.subscription_id`. Test: first open ACKed without fill, second open for the same subscription -> `REJECTED`, exactly 1 `openPosition` call. Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py -q -k inflight` -> `1 passed`.

**T5.4 M1 caches (F2-A).**
- Targets: `exness_broker_adapter.py:137-159` (`connect`/`disconnect`), `:265-288` (`_loss_cap_reason`, `_realized_today`), `:472-486`, `:516-532` (close events), `:656-669` (`get_balance`).
- Steps: (1) `_balance_state` cache from `getTradingStateSnapshot.account_state`, fresh for 60 s. (2) `_realized` cache with `_realized_at`, `_realized_day`, `_realized_stale=True` at start; set stale on every close (`_on_broker_close`, `_close_missing`) and when the UTC date changes. (3) `_refresh_loop` task started in `connect`, cancelled in `disconnect`: at second 30 of each minute refresh both (2 REST calls per minute, inside the D19 budget [I]). (4) `_loss_cap_reason`: use the cache when not stale and younger than 90 s; otherwise read synchronously; a read failure refuses (existing `daily loss check failed`). The synchronous read costs about one paced call (~1-2 s) on the first entry after a close (verifier item 5).
- Tests: fake client counting calls: fresh caches -> the open path makes exactly 1 call (`openPosition`); a broker close event -> next open calls `getDealsHistory` once then `openPosition`; deals read raises -> `REJECTED daily loss check failed`.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness/test_exness_open_path_calls.py -q` -> `3 passed`.

**T5.5 M2 account lock and D21 order pacing.**
- Targets: `exness_broker_adapter.py:216-243,317-370` (`_submit_open`, `_send_tracked`); `exness_client.py:147-196` (`_RequestPacer`), `:116-120` (`min_request_interval`), `:348-356` (`_pacer_for`).
- Steps: (1) `self._open_lock = asyncio.Lock()`; under it: pause read, presubmit, H1 check, loss cap, conditions, lot check, then register `_inflight[rid]` and `_pending_ack`; release the lock; then send `openPosition`. (2) Pacer keeps one priority heap and two clocks: every grant sets `_last_any`; a non-priority grant also sets `_last_data`. A priority waiter may leave at `_last_any + priority_interval`; a non-priority waiter at `max(_last_data + data_interval, _last_any + priority_interval)`. `data_interval` = today's strictest x 1.2 / fraction; `priority_interval` = max(global_account_rate x 1.2 / fraction, the slowest own limit among `_PRIORITY_OPS` x 1.2). Order ops are not scaled by the fraction because only the trader sends them [I]. With the fixture (`tests/core_test/infra/exness/fixtures/limits.json`: global 10/s, `openPosition` 4/s, `getOperationStatus` 10/s [V]) and fraction 0.6: priority 0.3 s, data 1.0 s.
- Tests: `test_exness_pacer.py` (fake clock): three priority waits leave at 0.0/0.3/0.6 s; two data waits are 1.0 s apart; a priority wait right after a data call leaves after 0.3 s, not 1.0 s. `test_exness_open_lock.py`: two subscriptions open concurrently with an instrumented slow loss-cap read; the check sections never overlap; three opens with a 0.5 s fake `openPosition` all start sending within 0.7 s.
- Verify: `uv run python -m pytest tests/core_test/infra/exness/test_exness_pacer.py tests/core_test/infra/brokers/exness/test_exness_open_lock.py -q` -> `0 failed`.

**T5.6 Gates and push develop (no deploy yet; Phase 07 deploys 05-07 together).** Verify: Shared commands; CI green.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 06 - Bar pipeline: timer close, stale/gap guards, concurrent opens

Entry gate: Phase 05 merged. Rollback: revert the phase commits.

**T6.1 Event fields.** Targets: `core/domain/bar/events.py:7-22`; `core/domain/bar/services/bar_builder_domain_service.py:60-113`. Steps: `BarCompletedEvent` gains `bar_end: datetime | None = None`, `gap: bool = False`, `closed_at: datetime | None = None`, `closing_tick_at: datetime | None = None`, `closed_by: str = "tick"`. The builder gains `last_tick_at: datetime | None = None` (set in `add_tick`) and `gap: bool = False`. Verify: `uv run python -m pytest tests/core_test/unit/domain/bar -q` -> `0 failed`.

**T6.2 Publish outside the bar lock (D21).** Targets: `engine/market_data/app_services/bar_app_service.py:81-178`. Steps: `_process_tick_for_interval` returns the `BarCompletedEvent` it closes instead of publishing; `add_tick` collects them under `_lock`, then after release publishes each and deletes its `bar:current` key, in order. Test: a slow `BarCompletedEvent` handler (0.3 s) on symbol A does not block `add_tick` for symbol B. Verify: `uv run python -m pytest tests/app_test/market_data/test_bar_app_service_unit.py -q` -> `0 failed`.

**T6.3 Timer close (F2b, D20).** Targets: `bar_app_service.py` (new `run_close_timer()`, constants `_TIMER_CLOSE_GRACE_S = 0.5`); start/stop next to the quote feed (`main_extensions.py:185-208`).
- Steps: (1) Every 0.25 s, under `_lock`, close each non-empty builder with `bar_end + 0.5 s <= now`; mark `closed_by="timer"`; remove it from `_bars` and record `_last_end[(symbol, interval)] = bar_end`. (2) A tick whose bucket start is earlier than `_last_end` for its key is late: drop it (DEBUG `bar.late_tick_dropped`). (3) A tick creating a builder when `_last_end` is known starts coverage at the bucket start (`last_tick_at = bar_start`).
- Tests: `tests/app_test/market_data/test_bar_timer_close.py` with a fake clock: no close at bucket end + 0.4 s, close at + 0.6 s with `closed_by == "timer"`; a late tick for the closed bucket produces no second event.
- Verify: `uv run python -m pytest tests/app_test/market_data/test_bar_timer_close.py -q` -> `0 failed`.

**T6.4 H3 gap facts and the Redis seed.** Targets: `bar_app_service.py:101-135`; delete `_seed_builder_from_mongo` (`:180-208`) and `flush_all_bars` (`:270-289`) with their tests; fix the "at-least-once" docstring (`:54,149`) to "at most once; gaps are flagged".
- Steps: (1) Trading seconds between instants a < b: `(b - a) - 60 * (minute opens in [a, b) - len(calendar.trading_minutes(a, b)))`. (2) G1: when a tick (or the close at `bar_end`) follows `last_tick_at` by more than 60 trading seconds, set `gap`. (3) G2: a builder created with no `_last_end` for its key reads `bar:current`; if its `bar_start` equals the bucket and `time.time() - last_update <= 2.0`, copy OHLCV and `tick_count` and set `last_tick_at` from `last_update`; else, when the first tick is more than 1 s after the bucket start, set `gap` (verifier item 3; `last_update` is written at `:234` [V]). (4) G3: at close, if `_last_end` is known and `calendar.trading_minutes(_last_end, bar_start)` is non-empty, set `gap`. (5) Copy `gap`, `bar_end`, `closed_at`, `closing_tick_at` onto the event.
- Tests: `tests/app_test/market_data/test_bar_gap_flags.py`: 15m bar with a 61 s trading silence -> gap, 59 s -> no gap; mid-bucket start without seed -> gap; fresh seed -> no gap and OHLC from the seed; seed 3 s old -> gap; skipped 1m bucket -> gap; `EXNESS_FX` Friday close to Monday open -> no gap.
- Verify: `uv run python -m pytest tests/app_test/market_data/test_bar_gap_flags.py -q` -> `0 failed`; `rg -n "flush_all_bars|_seed_builder_from_mongo" src tests` -> no output.

**T6.5 H2 stale guard, gap skip, dedup, H1 engine layer, concurrent opens.**
- Targets: `engine/strategy/strategy_app_service.py:241-270` (`_on_bar_completed`), `:323-390` (`_process_signal`), constructor `:42-66`; `core/domain/brokers/broker_port.py:23` (`fills_async` [V]).
- Steps: (1) `_last_bar_start: dict[str, datetime]`; ignore an event whose `bar_start` is not later than the strategy's last. (2) After `strategy.on_bar_completed`, when a signal exists and `event.bar_end` is set: `age = now - bar_end`; budgets `_STALE_AFTER_S = {"1m": 10, "15m": 60, "1h": 120}`, other intervals 120 [I]; over budget -> WARNING `strategy.entry_skipped reason=stale age_s=...`; `event.gap` -> WARNING `reason=gap`; both call `_notify_rejected` (resets hitnrun2's optimistic direction, `hitnrun2_strategy_service.py:105,130-132` [V]). (3) `_order_tasks: dict[str, asyncio.Task]`: a signal for a subscription with a live task -> WARNING `reason=inflight` and reject. (4) Brokers with `fills_async` run `_process_signal` as a task stored in `_order_tasks` (removed in a done-callback); paper stays inline (its docstring forbids concurrent calls, `paper_broker_adapter.py:81-83` [V]).
- Tests: `tests/engine_test/test_strategy_entry_guards.py` (fake clock): 1m at 11 s skipped with exactly one `reason=stale`, at 10 s submitted; 15m 61/60; 1h 121/120; `gap=True` skipped; on the stale bar the paper SL/TP handler still exits a held paper position whose SL is crossed; an event without `bar_end` (backtest shape) is never skipped. `tests/engine_test/test_concurrent_opens.py`: three async-fill subscriptions signal on one bar; `_on_bar_completed` returns before any submit finishes; a second signal while the task runs is rejected. Venue SL closes do not pass through bar handling (`exness_broker_adapter.py:516-532`), so they need no bar test.
- Verify: `uv run python -m pytest tests/engine_test/test_strategy_entry_guards.py tests/engine_test/test_concurrent_opens.py tests/backtest_test -q` -> `0 failed`.

**T6.6 `live.signal_latency`.** Targets: `_process_signal`. Steps: after `submit` returns, one INFO `live.signal_latency` per signal with `subscription_id, symbol, interval, bar_start, closed_by`, ISO times `t0_bar_end, t1_closing_tick, t2_closed, t3_published (event.occurred_at), t4_signal, t5_submit, t6_returned` and `t0_t5_ms`, `t0_t6_ms`. T5 is the call to `submit` (adapter checks are cached, so T5->T6 is the venue ACK for Exness and the fill for paper). Per signal, so bounded (CLAUDE.md log rule). Test: one signal -> one record with both ms fields. Verify: `uv run python -m pytest tests/engine_test/test_strategy_entry_guards.py -q -k latency` -> `1 passed`.

**T6.7 Gates and push develop.** Verify: Shared commands; CI green.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 07 - State rebuild and single-process deploy

Entry gate: Phase 06 merged. Rollback: revert phases 05-07 and redeploy the Phase 04 tag; paper mirror rows written meanwhile stay valid for the old code, which deletes them at boot.

**T7.1 Direction and warm-up contract.** Targets: `core/domain/strategy/strategy_service_interface.py:21-77`; `engulfing_strategy_service.py:72,74-79`; `hitnrun2_strategy_service.py:59-73`. Steps: move `_open_direction` to `IStrategyService`; add `restore_open_direction(direction: Direction | None)`; add `warmup_bars` (base 0; engulfing `key_level_lookback_bars + 1`; hitnrun2 `_buffer_size`, 481 at defaults, `:60-62` [V]). Verify: `uv run python -m pytest tests -q -k "engulfing or hitnrun2"` -> `0 failed`.

**T7.2 D9 warm-up and M3 direction seed.** Targets: `strategy_app_service.py:139-154` (`start_strategy`), constructor; `app/di/services.py:135-160`.
- Steps: (1) Inject optional `BarRepository` and `TradingCalendarFactory` (live DI only; backtest passes none and keeps its own replay). (2) In `start_strategy`, before `on_start`: wait until `now >= current 1m bucket start + 20 s` (after `sync_1m` stores the bar, T8.9), then `BarRepository.find(symbol, interval, end_date=now, limit=warmup_bars + 5)` (`bar_repository.py:146-174` [V]), keep bars with `datetime + interval <= now`, oldest first. (3) Then, with no I/O await in between: `on_start()`, feed each bar to `on_bar_completed`, call `on_order_rejected("warmup")` for any signal, set `_last_bar_start`. (4) If `calendar.trading_minutes(last_end, current_bucket_start)` is non-empty, log WARNING `strategy.warmup_incomplete` once. (5) Restore direction from `PositionAppService.get(id)` (LONG/SHORT/None).
- Tests: `tests/engine_test/test_strategy_warm_up.py`: hitnrun2 with 481 stored 1m bars, then one live bar that breaks the 4h low -> an order is submitted on that bar; a replayed signal sends nothing and leaves the direction None; a LONG mirror row -> direction LONG after start and no opposite signal on an engulfing bear bar.
- Verify: `uv run python -m pytest tests/engine_test/test_strategy_warm_up.py -q` -> `0 failed`.

**T7.3 D13 paper rebuild.** Targets: `core/domain/order/events.py:22-30` (add `sl_price`, `tp_price`); `engine/execution/order_app_service.py:87-96,160-169`; `engine/execution/position_app_service.py:31-53,73-80`; `core/infra/brokers/paper/paper_broker_adapter.py` (new `restore`); `core/infra/persistence/repositories/trade_repository.py` (new `realized_net`); `strategy_app_service.py` (new `restore_paper_brokers`); `app/di/services.py:122-133`.
- Steps: (1) Carry `sl_price`/`tp_price` from the order into `OrderFilledEvent` and into the mirror `PositionAggregate.open` (today the mirror gets none). (2) Delete the boot paper-row delete: `load_open_positions()` loads every open row and clears `_positions` first; `start()` drops its argument. (3) `TradeRepository.realized_net(run_ids) -> float`: sum of `pnl` minus commission if `pnl` is gross; check `TradeClosedEvent` construction in `core/domain/position/entities.py` first [UNVERIFIED]. (4) `PaperBrokerAdapter.restore(positions, realized)`: `_balance = _initial_balance + realized`; `_positions[f"{sub}:{symbol}"] = pos`. (5) `StrategyAppService.restore_paper_brokers(trade_repo)`: per paper broker in the pool, its subscriptions, their mirror rows, then `restore`. Call it at boot after `bootstrap_live_instances` (this phase) and at takeover (Phase 08).
- Tests: `tests/engine_test/test_paper_restore.py`: round trip closed, trade persisted, new broker restored -> balance equals the pre-restart balance; an open position restored with SL; the next bar crossing SL emits the exit fill.
- Verify: `uv run python -m pytest tests/engine_test/test_paper_restore.py tests/engine_test/test_paper_position_lifecycle.py -q` -> `0 failed`; `rg -n "delete_open_by_subscription" src/pocketquant/engine/execution/position_app_service.py` -> only the `drop` method line.

**T7.4 NTP gate (D20).** Steps: over SSH `timedatectl show -p NTPSynchronized --value`. Verify: -> `yes` (if not, `sudo timedatectl set-ntp true`, wait 5 min, re-check; still not `yes` -> Failure Protocol).

**T7.5 Deploy 05-07 [ASK] `Recommended: yes`.** Steps: gates, push develop, CI green, push `develop:master` outside forbidden windows. Verify over SSH:
- `docker logs pocketquant-app --since 15m 2>&1 | grep -cE '"level":"error"|Traceback'` -> `0`.
- `curl` GET `/api/v1/admin/safeguards` inside the container -> JSON with `entries_paused`.
- POST pause then GET -> `"entries_paused": true`; POST resume -> `false` (live trading is off, so no order is affected).
- `docker logs pocketquant-app --since 15m 2>&1 | grep -c strategy.warmup_incomplete` -> `0`.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 08 - Roles, leases, standby and handover (code + CI)

Entry gate: Phase 07 in prod (C1 lands before the split); `grep -c "^F1: A$" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` -> `1`. Rollback: revert; the `leases` collection is ignored by old code.

**T8.1 `APP_ROLES` replaces `enable_jobs`.** Targets: `core/config.py:64`; `app/di/infrastructure.py:95-105`; `app/main_extensions.py:211-238`; `app/main.py:36-86`; test conftests `tests/app_test/conftest.py:37`, `tests/backtest_test/conftest.py:40`, `tests/core_test/conftest.py:94`, `tests/core_test/infra/market_data/conftest.py:26`, `tests/engine_test/conftest.py:38`, `tests/app_test/integration/app_factory.py`. Steps: `app_roles: str = "api,worker,trader"` with a validator that splits on commas and rejects names outside the three; property `roles -> frozenset[str]`. The DI scheduler provider no longer starts the scheduler (`shutdown` is already a no-op when not initialized, `scheduler.py:137-141` [V]). Feature routes register only with `api`; `/health` always. Tests use `app_roles="api"` where they had `enable_jobs=False`. Verify: `rg -n "enable_jobs|ENABLE_JOBS" src tests` -> no output; `uv run python -m pytest tests/core_test -q -k app_roles` -> `0 failed`.

**T8.2 Lease repository.** Targets: new `core/infra/persistence/repositories/lease_repository.py`; `app/main_extensions.py:109-122` (`_REPO_TYPES`). Steps: collection `leases`, unique index `ux_leases_name`; `acquire(name, owner, ttl_s) -> datetime | None` = `find_one_and_update({"name": name, "$or": [{"expires_at": {"$lt": now}}, {"owner": owner}]}, {"$set": {"owner", "expires_at": now + ttl, "renewed_at": now}, "$setOnInsert": {"_id": generate_id_str()}}, upsert=True, return AFTER)`; `DuplicateKeyError` -> `None`. `release(name, owner)` sets `expires_at = now`, `released_at = now`. `last_released_at(name)`. Tests (Mongo): two owners race -> one acquires; owner renews; expiry lets the other in; release lets the other in at once; never two documents for one name. Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_lease_repository.py -q` -> `0 failed`.

**T8.3 `RoleLease`.** Targets: new `core/infra/persistence/role_lease.py`. Steps: owner `f"{hostname}:{pid}:{uuid7}"`; TTL 30 s, renew 10 s, poll 0.5 s; `wait_acquire()` logs INFO `lease.acquired name waited_ms`; `run_renewal(on_lost)`: a failed renewal logs WARNING and retries; when local `expires_at - now <= 5 s` without success, mark lost and await `on_lost()` once; `valid_for(margin_s)`; `release()`. One host means one clock for all roles [I]. Tests: renew failures until the margin -> `on_lost` once and `valid_for(5)` false. Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_role_lease.py -q` -> `0 failed`.

**T8.4 Worker role.** Targets: `main_extensions.py` (`start_worker`), `main.py`. Steps: background task: `wait_acquire("worker")` -> `recover_orphan_jobs` -> `scheduler.initialize/start` -> `register_sync_jobs` -> renewal. `on_lost`: `scheduler.shutdown(wait=False)`, ERROR `lease.lost`, `os.kill(os.getpid(), SIGTERM)`. Shutdown: `scheduler.shutdown(wait=True)`, then release. Test: two worker runtimes on one Mongo -> `scheduler.started` logged once. Verify: `uv run python -m pytest tests/app_test/integration/test_second_worker.py -q` -> `1 passed`.

**T8.5 Trader standby, fence, takeover, drain.** Targets: new `app/trader_role.py` (`start_trader`, `take_over`, `hand_over`); `strategy_app_service.py` (`trading` state, `begin_trading`, `end_trading`, `is_idle`, fence); `core/domain/brokers/broker_port.py` (`is_idle` property, default `True`); `exness_broker_adapter.py` (`is_idle`: no `_inflight`, no `_pending_ack`, not `_needs_snapshot`).
- Startup (before `yield`, so health means a warm standby): start the quote feed and close timer; `bootstrap_live_instances`; `start_strategy` for every subscription whose `desired_state` is running (no broker connect while not trading; warm-up from T7.2); log INFO `trader.standby`.
- Takeover task: `wait_acquire("trader")`, then: reload `load_open_positions()` and `load_pending_orders()`; `restore_paper_brokers`; restore directions; `begin_trading()` sets trading and connects the broker of every running strategy (Exness snapshot gate keeps opens shut until reconciled, `:256-257` [V]); log INFO `trader.takeover handover_gap_ms` (now minus the lease's `released_at`, null on a cold start); start `LiveTradeCollector`, the reconcile loop and renewal; log INFO `trader.takeover_complete takeover_ms` (acquire to reconcile loop started).
- Fence: in `_process_signal`, right before `submit`, refuse unless `trading` and (`lease is None` or `lease.valid_for(5.0)`): WARNING `strategy.entry_skipped reason=lease`. While not trading a signal is discarded (DEBUG `strategy.signal_discarded`) and `on_order_rejected("standby")` is called.
- `on_lost`: `end_trading()` without drain, ERROR `lease.lost`, SIGTERM self.
- `hand_over()` (first in lifespan `finally`): if the lease is not held, skip. Else wait for the next 1m boundary B + 1.0 s; poll every 0.2 s until `is_idle()` (no `_order_tasks` and every broker idle) or B + 30 s; on timeout retry once at the next boundary; still busy -> ERROR `trader.handover_forced inflight=N`. Then `end_trading()` (disconnect brokers), stop the reconcile loop, `release()`, INFO `trader.lease_released inflight=N boundary=B offset_s=x`.
- Tests: `tests/app_test/unit/test_trader_handover.py` (fake clock, fake adapter): an in-flight open delays release until it resolves, then release logs `inflight=0` inside the window; never idle -> retries once then `handover_forced`. `tests/engine_test/test_trader_fence.py`: `valid_for(5)` false -> 0 submits and `reason=lease`; not trading -> broker `connect` never called, 0 order/position repo writes. `tests/app_test/integration/test_second_trader_standby.py` (Mongo): second trader holds no lease, logs `trader.standby`, makes 0 writes to `orders`, `positions`, `trades`, never runs a sweep.
- Verify: `uv run python -m pytest tests/app_test/unit/test_trader_handover.py tests/engine_test/test_trader_fence.py tests/app_test/integration/test_second_trader_standby.py -q` -> `0 failed`.

**T8.6 D18 heartbeat sweep.** Targets: `core/infra/persistence/repositories/backtest_repository.py:92-107`; `engine/backtest/backtest_app_service.py:139-141`; `main_extensions.py:132-141`. Steps: `touch_heartbeat(run_id)` every 30 s from the yield point (wiring of the repo and run id into the service [UNVERIFIED]); sweep marks failed only `started` rows whose `heartbeat_at` (or start time when absent; field name [UNVERIFIED]) is older than 120 s; runs only in `api`. Test: fresh and stale runs -> only stale fails. Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_backtest_heartbeat_sweep.py -q` -> `1 passed`.

**T8.7 `sync_1m` at second 12 (F3-A).** Targets: `sync_jobs.py:693-708`; `docs/system-architecture.md:141`. Verify: `rg -n "second=12" src/pocketquant/engine/market_data/app_services/sync_jobs.py` -> 1 line.

**T8.8 Local dev profile.** Targets: `../pocketquant-config/local/remote-db.env`, `remote-db-local-redis.env`. Steps: `ENABLE_JOBS=false` -> `APP_ROLES=api`; commit and push per the Ops recipe. Verify: `grep -c "^APP_ROLES=api$" ../pocketquant-config/local/remote-db.env` -> `1`.

**T8.9 Gates and push develop.** Verify: Shared commands; CI green.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 09 - Topology, rolling deploy, one-time cutover, docs

Entry gate: Phase 08 CI green. [ASK] before T9.8. Rollback: revert the phase commit and push; the old `10-deploy.sh` runs `up -d --remove-orphans`, which removes `api/worker/trader` and starts `app` (a short gap; live is off).

**T9.1 Compose.** Targets: `deploy/compose.prod.yml:4-14,53-91,113-114`. Steps: replace `app` with `api`, `worker`, `trader`: same image, no `container_name`, `env_file: .env`, `environment: {TZ: UTC, APP_ROLES: <role>, EXNESS_RATE_FRACTION: 0.05 | 0.3 | 0.6}`, same healthcheck; `stop_grace_period`: api 30s, worker 120s, trader 180s (boundary wait <= 60 s + two 30 s windows + teardown); api command adds `--timeout-graceful-shutdown 10`. `web.depends_on` -> `api`. Replace the Vietnamese comment (`:113-114`) with English. Verify: `docker compose -f deploy/compose.prod.yml --env-file /dev/null config -q` with dummy vars -> exit 0; `grep -c "container_name: pocketquant-app" deploy/compose.prod.yml` -> `0`.

**T9.2 nginx.** Targets: `web/nginx.conf:24-26`. Steps: `resolver 127.0.0.11 valid=5s ipv6=off;`, `set $api_upstream http://api:41921;`, `proxy_pass $api_upstream;`, `proxy_connect_timeout 2s;`, `proxy_next_upstream error timeout;`; no static `proxy_pass` to `api` anywhere. Verify: `docker run --rm -v "$PWD/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro" --add-host api:127.0.0.1 nginx:1.27.5 nginx -t` -> `test is successful`.

**T9.3 Rolling deploy.** Targets: `deploy/vps/10-deploy.sh:49-72`. Steps: add `dc()` and `roll()` from the researcher recipe; order: `dc up -d --no-deps web` and wait healthy, then `roll api 120`, `roll worker 120`, `roll trader 240`, then `dc up -d --remove-orphans`, `docker image prune -f`. Add `cutover_from_app()` that runs only when a container named `pocketquant-app` exists: `dc up -d --no-deps api` and wait healthy; `dc up -d --no-deps web` (new nginx points at `api`); `docker stop pocketquant-app && docker rm pocketquant-app`; `dc up -d --no-deps worker trader`. Starting `worker`/`trader` only after the old `app` is gone prevents a lease-less old trader beside a new one. Verify: `bash -n deploy/vps/10-deploy.sh && echo ok` -> `ok`.

**T9.4 Scripts and verify.** Targets: `deploy/vps/11-verify.sh:67,79,93,110,120,172,177,188,228,240` [V]; `scripts/audit_bar_quality.py:15,24`; `scripts/backfill/binance_bars.py`, `scripts/backfill/provider_bars.py`. Steps: replace `pocketquant-app` with `$(dc ps -q api)` (logs checks cover all three roles); docstrings use `docker compose ... exec api`. Verify: `rg -n "pocketquant-app" deploy scripts docs README.md` -> no output.

**T9.5 Docs and `CLAUDE.md` (D16).** Targets: `CLAUDE.md:15`; `docs/system-architecture.md:7,52,54` and new sections; `docs/deployment.md:51,64,142,184-186,221-224,256-269`; `README.md:39,54,75`; `justfile:34-36`; `docs/codebase-summary.md`. Steps: `CLAUDE.md:15` -> `- **One lease-holding trader and one lease-holding worker** - APP_ROLES picks a process's roles; worker and trader act only while holding their Mongo lease, so a second copy waits in standby. Never run --workers N.` Docs state as-is: roles, leases (TTL 30 s, renew 10 s, fence 5 s), standby/handover, pause read per open, timer close, stale/gap guards, `live.signal_latency`, rate fractions, rolling deploy, `APP_ROLES=api` for remote-DB dev. Each doc stays under 800 lines. Verify: `wc -l docs/*.md | awk '$1>800 && $2!="total"' | wc -l` -> `0`; `rg -n "Single uvicorn worker|ENABLE_JOBS" CLAUDE.md README.md docs/*.md justfile` -> no output.

**T9.6 VPS precheck.** Steps: `docker compose version`. Verify: prints `v2.` or later (record it; `--scale` and `--no-recreate` are needed).

**T9.7 Gates and push develop.** Verify: Shared commands; CI green.

**T9.8 Cutover deploy [ASK] `Recommended: yes, now (market hours are fine; live is off)`.** Steps: push `develop:master` outside forbidden windows; CI runs `10-deploy.sh`, which performs the cutover. Paper strategies miss bars during this one-time gap (about trader warm-up, <= 2 min) [I]; D8 applies from the next deploy. Verify over SSH:
- `docker ps --format '{{.Names}}' | grep -cE "pocketquant-prod-(api|worker|trader)-[0-9]+"` -> `3`; `docker ps -a --format '{{.Names}}' | grep -cx pocketquant-app` -> `0`.
- mongosh `db.leases.find({}, {name:1, owner:1}).toArray().length` -> `2`, names `worker` and `trader`.
- `docker logs $(dc ps -q trader) 2>&1 | grep -c trader.takeover_complete` -> `1`.
- `docker exec pocketquant-web curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/market-data/symbols` -> `200`.
- verify verdict grep -> a number >= 1.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 10 - Prod handover verification

Entry gate: Phase 09 in prod. Deploys run Monday-Friday 07:00-20:00, never near 12:00. Rollback: as Phase 09.

**T10.1 Delete the cutover function (deploy 1 of 10).** Targets: `deploy/vps/10-deploy.sh` (`cutover_from_app`). Steps: verify `pocketquant-app` is absent, delete the function and its call, gates, push develop, [ASK] `Recommended: yes` master push. Verify: `grep -c cutover_from_app deploy/vps/10-deploy.sh` -> `0`; the T10.3 checks pass for this deploy.

**T10.2 Redeploys 2-10.** Steps: per deploy, start the probe on the VPS: `docker exec -d pocketquant-web sh -c 'for i in $(seq 1 600); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/v1/market-data/symbols; sleep 0.5; done > /tmp/probe.log'`, then `cd /opt/pocketquant/deploy && IMAGE_TAG=<current tag> bash vps/10-deploy.sh` (documented manual invocation, `10-deploy.sh:7-9` [V]; `web` is not recreated for an unchanged tag [I]).

**T10.3 Per-deploy checks.** Verify (each deploy):
- `docker exec pocketquant-web grep -cv "^200$" /tmp/probe.log` -> `0`.
- old trader log: one `trader.lease_released` with `inflight=0` and `offset_s` between 0 and 30; 0 `trader.handover_forced`.
- new trader log: `trader.takeover` with `handover_gap_ms` <= 2000 and `trader.takeover_complete` with `takeover_ms` <= 5000.
- new trader log: 0 `strategy.entry_skipped reason=gap` for bars whose `bar_start` is within one interval of the boundary B.
- `db.leases.find()` still shows one owner per name.
Record each deploy in `plans/261028-0652-exness-only-parallel-runtime/reports/handover-deploys.md` (a row per deploy); after 10 rows, `grep -c "| PASS |" .../handover-deploys.md` -> `10`.

**T10.4 Second trader and second worker in prod (D17).** Steps: `dc run -d --no-deps -e APP_ROLES=trader --name pq-probe-trader trader` for 10 min, then stop and remove it; same with `APP_ROLES=worker` for 2 min. Verify: `docker logs pq-probe-trader 2>&1 | grep -c trader.standby` -> `1`; `docker logs pq-probe-trader 2>&1 | grep -cE "lease.acquired|exness.broker_connected|exness.order_submitted|order_filled|position_opened|orphan_backtest_recovery"` -> `0` (writes to `orders`/`positions`/`trades` happen only behind these events; writes carry no process owner, so a collection count cannot separate the two traders); probe worker: `grep -c scheduler.started` on its logs -> `0`.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 11 - 14 days of paper observation (re-runnable daily)

Entry gate: Phase 10 PASS. [ASK] once: "Start the stopped XAUUSD:EXNESS 1m paper subscription (and EURUSD 1h) so the 1m latency gate has data? `Recommended: yes`" (ids from `GET /api/v1/subscriptions`). Rollback: stop the subscriptions.

**T11.1 Daily row.** Goal: one row per day in `plans/261028-0652-exness-only-parallel-runtime/reports/paper-observation.md`. Verify (for the previous UTC day, logs with `--since/--until`):
- trader `event_loop.lag` WARNINGs with `lag_s >= 0.5` -> `0`.
- all roles: "Error notifying listener" -> `0`.
- `job_history`: `sync_integrity` duration < 10 s; `sync_repair` < 120 s.
- `live.signal_latency` on 1m Exness paper: p95 `t0_t5_ms` <= 1000 (compute with `jq` over the day's lines; fewer than 5 signals -> record `n/a`, not pass).
- order ops: `exness.rate_limited` with `op=openPosition` -> `0` (live off means 0 by construction; record).
- `strategy.entry_skipped` counts by reason.
**T11.2 Weekly row.** `exness.rate_limited_retry` over 7 days <= 72 (D19).
- Exit: 14 consecutive PASS rows. Verify: `grep -c "| PASS |" .../paper-observation.md` -> `14` or more.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## Phase 12 - Re-arm live gate

Entry gate: Phase 11 exit met; the owner names one strategy. Do not copy the go-live phases; re-run them.

**T12.1 Re-run go-live phases.** Steps: run `plans/261019-1957-exness-go-live/phase-11-go-live-one-strategy.md`, then `phase-12-observation-and-go-live.md`, with three substitutions: `docker exec -i pocketquant-app` -> `docker compose -f compose.prod.yml --env-file .env exec -T api` (admin calls) or `trader` (logs); `ENABLE_JOBS` text -> `APP_ROLES`; exits are venue SL/TP only (D11, no close route). Verify: as written in those phases.
**T12.2 D12 canary.** Steps: minimum lot, tight SL; collect `live.signal_latency` for the first 20 Exness entries. Verify: p95 of `t0_t6_ms` over those 20 lines <= 2000; any entry over 2000 is recorded with its T-deltas. Fail -> Failure Protocol, pause entries first.

### Failure Protocol
If any Verify result differs from its expected result, or a step cannot be done as written:
1. Stop. Do not retry, do not continue to the next task or phase, and do not change tests or expected values.
2. Spawn the `kongming` agent and give it: the task id, the steps you ran, the exact command, its full output, and the pass condition that failed.
3. If `kongming` cannot be spawned, stop and report the same items to the user.

---

## 4. Test matrix

| Layer | What | Where |
|---|---|---|
| Unit | probe, skip listener, pacer, gap math, timer close, stale budgets, fence, lease margin, handover drain, warm-up, paper restore | P01, P05-P08 test files above |
| Integration (Mongo) | pause across instances, lease race, second trader/worker, heartbeat sweep, safeguards API | P05, P08 |
| Regression | backtest suite unchanged (events without `bar_end`), Exness adapter suite, paper lifecycle | P05-P07 |
| Prod | 10 handover deploys with probe, second trader/worker, 14-day paper rows, D12 canary | P10-P12 |

## 5. Data flow (trader, after the split)

Exness/Binance tick -> adapter callback (awaited inline, `exness_quote_adapter.py:124-135`) -> `QuoteAppService` -> `BarAppService.add_tick` (under lock: build, gap facts, close) -> publish after the lock -> `StrategyAppService._on_bar_completed` (dedup, signal, stale/gap/inflight checks, fence) -> paper inline / Exness task -> `OrderAppService.submit` -> Exness adapter (account lock: pause read from Mongo, presubmit, cached loss cap, register inflight) -> paced `openPosition` -> ACK -> fill on the events stream -> `OrderFilledEvent` (with SL/TP) -> mirror row. `api` writes desired state and the pause to Mongo; `trader` reads them (reconcile every 5 s, pause per open). `worker` writes bars to Mongo; `trader` reads them only for warm-up.

## 6. Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | Two traders send orders (split brain) | Low x High | Lease with UUIDv7 doc and unique name; fence with 5 s margin on every order; standby never connects a broker; worker/trader start after the old `app` is removed at cutover; residual: an HTTP send already in flight when the loop froze past the TTL, caught by the snapshot gate and unknown-fill block |
| R2 | Duplicate order across handover | Low x High | Drain to `inflight=0` before release; new trader reloads pending orders and reconciles the snapshot before opens; forced release logs ERROR and stays fail-safe |
| R3 | Pause lost or ignored | Low x High | Read per open, refuse on read failure, route 503 on write failure; CI test across two instances |
| R4 | Two Exness tick sessions disturb each other (kongming saw 4 breaker opens during a probe, correlation only) | Medium x High | Phase 02 spike before any handover code; fallback is a second account (D24), owner gate |
| R5 | Order pacing change causes a terminal 429 on `openPosition` | Low x Medium | Order spacing honours the venue's `openPosition` limit with 20% headroom; fewer pre-order calls than today; P11 weekly 429 gate (D19) |
| R6 | Timer close on a skewed host clock | Low x Medium | NTP gate (D20); late ticks dropped, never re-published; T2-T1 visible in `live.signal_latency` |
| R7 | Stale-cap: realized loss lags until the next refresh after a manual app-side close | Medium x Low | Close events mark stale; 60 s refresh at second 30; synchronous fallback costs ~2 s on the first entry after a close |
| R8 | Warm-up starts before `sync_1m` stored the last bar | Medium x Low | Wait to bucket + 20 s with `sync_1m` at second 12; `strategy.warmup_incomplete` WARNING; first bar gap rules |
| R9 | Cutover gap (one-time missed paper bars; `web` recreated every real deploy) | High x Low | Live is off; D8 counted from deploy 2; web gap is Unresolved U2 |
| R10 | Paper balance rebuild differs by open-position entry commissions | Medium x Low | Documented approximation; exact after the position closes |
| R11 | `api` orphan sweep fails a backtest still running on the old `app` at cutover | Low x Low | One-time; the heartbeat rule applies afterwards |

## 7. Unresolved

1. **U1 Spike result.** If `F1: fallback`, Phase 08 waits for the owner: second Exness account (D24) or another choice. Not answerable from code.
2. **U2 `web` recreation gap.** Every image deploy recreates `web` (fixed `container_name`, `compose.prod.yml:6` [V]); the cloudflared -> web gap is outside the handover criteria (researcher unresolved 4). Accept, or roll `web` too?
3. **U3 Deterministic idempotency keys.** The public spec now documents dedup semantics (same key + same payload returns the original operation; different payload is rejected), which meets the stated exit condition of non-goal H1b, but the retention window is unpublished. A `uuid5(subscription, bar_start, side)` key in a separate field would make a split-brain duplicate impossible at the venue. Kept out of scope; owner to decide.
4. **U4 Acceptance M2 wording.** D21 forces concurrent sends; this plan serializes only the check-and-register section. Confirm this reading.
5. **U5 Journals.** The TV `rg` gate excludes `docs/journals/**` (dated history). Confirm, or rewrite the one journal hit (`docs/journals/2026-09-21-asset-class-trading-calendar.md`).
6. **U6 Stale budget for 5m/4h/1d.** D10 gives only 1m/15m/1h; the plan uses 120 s for others [I].
7. **U7 Pacer assumption.** Order ops use the venue per-method limit unscaled by the fraction because only the trader sends them [I]; `getLimits` on the prod account must list `openPosition` (the fixture does).
8. **U8 Field names** marked [UNVERIFIED] (Mongo `symbol` fields, backtest start-time field, `Trade.pnl` net or gross) must be checked by the executor before use.
