---
title: "Reanalysis: true parallelism on a stronger machine, Exness as the only data source"
date: 2026-10-28
status: advisory, no code changed
inputs: plans/reports/kongming-261028-0848-event-loop-concurrency-review.md, debug-261023-0045-daily-0400-integrity-event-loop-stall.md, brainstormer-261028-0915-parallel-process-topology.md, explore-261028-0915-tradingview-removal-impact.md, code-reviewer-261028-0915-live-path-parallel-safety.md, researcher-261028-0920-exness-index-cfd-equivalents.md; code on develop @ 453e8e90; prod read-only (job_history, logs, docker stats) on 2026-10-28
---

# Reanalysis: parallel processes, Exness-only data

Labels: **[F]** verified in code at the cited line, in a cited report, or measured on prod today. **[I]** my inference. **[U]** unknown, needs a check or an owner answer.

## TL;DR

1. **The root cause does not survive TradingView removal, and neither should its fix.** Every stall source measured on prod is the CME calendar; the Exness and 24/7 calendars are arithmetic [F]. Drop the calendar bisect rewrite. Do the two cheap permanent items from the earlier report (loop-lag probe, skip-listener fix) and let the process split isolate trading from the stall until the CME code is deleted.
2. **Topology: agree with the brainstormer's shape, disagree with its order.** Land `worker` (APScheduler + batch jobs) as a separate process first, keep `api` and `trader` together as `app`, and split `api` from `trader` only when the lag probe shows backtests hurting the trading loop. One worker, no process pool, no symbol sharding: after TV removal no batch job is CPU-bound; they are all paced by one Exness account's REST budget, and more workers would only divide that budget. Free-threaded Python: reject again, on different grounds (see 2.4).
3. **Exness-only data makes the REST budget and the WS strike budget the scarce resources, not CPU.** The in-process pacer already gives orders priority and its queue is shallow [F]; the danger is a second process (or a second human) on the same account. Prod logs show it: the researcher's read-only probe on 2026-10-28 02:20-03:20Z coincides with 47 of the week's 72 Exness 429 retries and all 4 WS circuit-breaker opens of the week [F, correlation only].
4. **Before any Exness live subscription:** H1a, H2, H3, M3 and C1 from the code-reviewer report, in one process. Before the split: role gate, lease, per-process rate fraction. With TV removal: delete the whole TV and CME surface, including the `ES1!:TRADINGVIEW` symbol and its paper subscription. Blocking owner item: Exness returns 404 for all Indices candles and ticks on this account [F, researcher]; `US500/USTEC/US30` cannot be onboarded until that changes.

## 0. New facts measured today (prod, read-only) [F]

| Fact | Value |
|---|---|
| Host | 2 vCPU, 3,905 MB RAM; `app` 3.55% CPU, 338 MB RSS; Mongo 886 MB |
| Tracked symbols | BTCUSDT/ETHUSDT/SOLUSDT:BINANCE, ES1!/NQ1!/YM1!:TRADINGVIEW, XAUUSD/EURUSD/BTCUSD:EXNESS |
| 1m bar depth | ES/NQ/YM about 19k bars each since 2026-10-08 (three weeks); XAUUSD 360k since 2025-10-21; EURUSD 140k since 2026-06-12; BTCUSD:EXNESS 143k since 2026-07-21; Binance 1.2-1.3M since 2024 |
| Job durations, 7 days | `sync_1m` n=9,683 p50 9.3 s p95 11.9 s max 1,483 s; `sync_backfill` p50 167 s max 980 s; `sync_integrity` p50 419 s; `sync_repair` n=14 p50 1,609 s max 2,947 s; `sync_verify_cascade` p50 4.6 s max 284 s; `data_lag_check` p50 0.1 s max 256 s |
| Subscriptions | two BTCUSDT 1m paper running; `01a178ef` ES1! 15m paper running; XAUUSD 1m and EURUSD 1h stopped |
| Exness 429s, 7 days | 72 `exness.rate_limited_retry`, zero terminal `exness.rate_limited` (the count of the shorter string equals the count of the longer one); 47 of the 72 in the 03:00Z hour of 2026-10-28 |
| Exness WS, 7 days | 56 `exness_ws.reconnecting`, by UTC hour: 00h 11, 02h 25, 03h 11, 12h 6, others 1 each; 4 `exness_ws.circuit_breaker_open`, all at 2026-10-28 02:42, 02:51, 03:01, 03:10Z |
| Binance WS, 7 days | 15 `binance_ws.reconnect`: 00h 7, 06h 1, 12h 7; 9 `stale_detected` |
| Skip listener | 72 "Error notifying listener" lines in 7 days (the `scheduled_run_time` bug from the earlier report fires on every dropped run) |
| Repair | 22 `integrity.repair.still_missing` |

Two readings of this [I]: the 00h and 12h reconnect clusters on both venues line up with the `sync_repair` stalls, which matches the code-reviewer's H3 hypothesis (a saturated loop cannot answer WS pings) — correlation verified, mechanism not. The 02-03h cluster and all four breaker opens line up with the researcher's probe window on the same Exness account; a second consumer on the account disturbed prod's tick stream. The mechanism is not known (REST 429s do not pass through the WS path), so treat it as "never run a second Exness client against the prod account" rather than as a measured limit.

## 1. Does the root cause change?

**What blocks the loop today** [F]: CME `bar_start` through pandas `iterrows()` (`cme_globex_calendar_adapter.py`), called about 91k times per futures symbol per integrity pass, twice per `sync_repair`, plus per bar in the 5000-bar resync. Everything else is milliseconds.

**What remains once the CME calendar is gone.** Every remaining calendar is arithmetic:

- `ExnessSessionCalendarAdapter.bar_start` is `exness_bar_start`, pure datetime arithmetic (`exness_session_calendar_adapter.py:92-98,253-254`) [F]. `is_open` is one subtraction and a scan over at most about 20 segments (`:183-185`) [F]. `trading_minutes` builds the week spans once per call and walks the minutes with an index (`:236-251`) [F]. The debug report measured a full `check_integrity` on Exness and 24/7 calendars at 0.02-0.03 s per interval (`debug-261023-0045` line 97) [F].
- `integrity_jobs.check_integrity` keeps its two loops (`integrity_jobs.py:47-51,77-81`) [F]; on Exness calendars that is about 10k cheap calls per (symbol, interval) [I: from the measured 0.03 s].
- Cascade: `compute_boundaries` calls `bar_start` per bucket and `trading_minutes` per bucket (`cascade_aggregator.py:142-145,197`) [F]; about 34 `_spans` builds per symbol per minute [I], single-digit milliseconds.
- Per tick: 7 `bar_start` calls under one lock (`bar_app_service.py:90-102`) [F]; microseconds on Exness and 24/7 [I].
- Backtests: pure Python, yielding every 10 bars (`backtest_app_service.py:141`) [F]. This becomes the only CPU-bound work in the system.
- Exness history and repair: `ExnessAdapter.fetch_ohlcv` pages 1000 candles per call with an `await` between pages (`exness_adapter.py:56-74`) [F]; the pacer sleeps between calls (`exness_client.py:168-187`) [F]. I/O-bound, never a loop stall.

**Re-ranked stall sources in the target world** [I unless noted]:

| # | Source | Loop impact | Where it lands after the split |
|---|---|---|---|
| 1 | Backtest runs (`POST /backtest/run`) | bounded by the 10-bar yield; seconds to minutes of shared CPU | `api` (in `app` until the api/trader split) |
| 2 | Binance tick hot path: Redis `SET` per tick, debug-log chain, one global bar lock | steady-state, scales with market activity; app at 3.6% CPU today [F] | `trader` |
| 3 | APScheduler sync Mongo round trips on the loop | milliseconds per wakeup [F, earlier report] | `worker` |
| 4 | Exness REST budget contention (429 on an order call is never retried, `exness_client.py:305-307` [F]) | not a stall; a refused entry and a closed snapshot gate | crosses processes, see section 3 |
| 5 | WS reconnect storms caused by stalls (00h/12h clusters) | disappear with the stalls | gone |

Nothing in rows 1-3 needs a process pool, threads, or sharding.

**Is the calendar bisect still worth doing? No.** It is a half-day rewrite plus an equivalence test of code that TV removal deletes in full (`explore-261028-0915` section 1 names the CME adapter as dead with TV; no other symbol uses `CALENDAR_CME_GLOBEX_EQUITY` [F]). What stands in for it:

- The loop-lag probe and the skip-listener fix (permanent, about 40 lines) go in now; both are needed in every topology.
- The worker split moves the stall off the trading loop. Residual damage while the CME code still exists: Mongo bars for every symbol lag 25-49 min twice a day inside the worker, which `sync_1m`'s 100-bar fetch and the 100-minute cascade lookback already heal [F: `sync_jobs.py:341,351`]. SSE charts and the Phase 12 integrity checks see that lag; strategies, which take bars from ticks, do not.
- Interim safety: live trading is disarmed (`EXNESS_LIVE_TRADING=false` since 2026-10-22, plan index) and Phase 11 was called off for lack of a profitable strategy [F: `plans/261019-1957-exness-go-live/plan.md`]. No real money is exposed to the stall today. What the stall does damage is paper validation (late bars, feed drops at 00h/12h), and that stops the moment the worker split lands.
- Flip condition: if the owner decides the worker split waits for TV removal **and** TV removal is more than about a month away, do the cheapest stall remover instead of the bisect: skip CME-calendar symbols in `sync_integrity` and `sync_repair` (a few lines, deleted with TV). The ES data it stops repairing is three weeks deep and will be deleted anyway.

## 2. Target topology

### 2.1 Agree with the shape, change the order

The brainstormer's `api` / `worker` / `trader` split is the right end state and the code already keeps the whole bar-to-order chain inside one process on the in-memory bus [F: `bar_app_service.py:162` -> `event_bus.py`, `strategy_app_service.py`]. But its step 4 (split `api` from `trader`) has a cost the brainstormer underweights: it is the step that breaks the kill switch (C1), needs the safeguards read-through, and gives the trader its own HTTP-less lifespan. Its benefit after TV removal is only "backtests off the trading loop". Do it on evidence:

- **Step B (now):** `app` = `api` + `trader`; `worker` = scheduler and jobs. Two GILs, two cores. `app` keeps the one Exness client that serves routes, ticks WS, events WS and orders [F: `di/adapters.py:82-127`]. The pause route and the broker stay in one process, so C1 is not triggered by this layout.
- **Step A (on evidence):** split `api` out when `event_loop_lag_max_s` in `app` exceeds the per-interval budget during a backtest, or when a second admin user appears. The role gate from step B makes this a compose change plus the C1 read-through.

### 2.2 Where batch work runs

One `worker`. Reasons: no CPU-bound job survives TV removal (section 1); every Exness job is paced by one account budget, so two workers sharded by symbol would run two pacers against one limit (section 3); `sync_1m` already loops over all symbols in order and finishes in about 9 s today with the TV scraper in the loop [F], which drops to a few seconds without it [I]. A `ProcessPoolExecutor` inside the worker has no caller: the job bodies resolve a module-global container (`sync_jobs.py:99-121`) [F] and would need a rewrite to be picklable, for no CPU gain.

Backtests stay in `api` (the KISS answer to the brainstormer's open question 7). Moving them to the worker would add a queue and a result channel for one admin user.

### 2.3 Mandatory single-owner guarantees (angle C, agreed)

| Guarantee | Mechanism | When |
|---|---|---|
| One scheduler | `worker` role is the only lifespan that starts APScheduler; fixed `container_name`; Mongo lease `worker` | step B |
| One trader per account | `trader` role is the only one that runs `bootstrap_live_instances`, `start_quote_feed`, reconcile, broker connect, the paper-row delete and the backtest orphan sweep; Mongo lease `trader` | step B |
| No second Exness client on the account | the worker never constructs `ExnessQuoteAdapter` or a broker (role-gated lifespan; the DI client is lazy, `exness_client.py:199`) [F]; the remote-DB dev profile runs role `api` only, which closes the C2 hole where a local session loads prod subscriptions (`main_extensions.py:161-172` runs regardless of `enable_jobs`) [F] | step B |
| Pause flag crosses processes | read from Mongo per open, fail closed; delete the in-memory copy and the route's dual write (net code removal) | step 1, because it also removes a stale-copy failure mode in one process |
| One scheduler docstring that tells the truth | correct `scheduler.py:3-5,54-56` (C3) | step 0 |

Lease: one helper, two callers (`worker`, `trader`), `find_one_and_update` on `{_id, $or: [{expires_at: {$lt: now}}, {owner: me}]}` with a 30 s TTL and a 10 s renew, fail-stop on a lost renewal. No fencing token; on one compose host that is acceptable [I, agreed with the brainstormer]. The lease is what turns a wrong `APP_ROLES` value into a refused start instead of duplicate orders.

### 2.4 Free-threaded Python 3.14t: reject again

- `uv.lock` carries `cp314t` wheels for numpy, pandas, pymongo, pydantic-core and uvloop, and none for `httptools` [F: grep today]. Uvicorn would fall back to h11 [I].
- Whether each extension declares `Py_mod_gil` is unverified [U]; one that does not re-enables the GIL silently.
- Decisive: after TV removal there is no CPU-bound job left to spread over threads; the only CPU consumer (backtests) is already isolated by process in step A. Every money-path structure is loop-confined (`_bars`, strategy dicts, broker `_inflight`, Dishka container) [F]; threads would add races to the order path for a gain that processes already deliver. A stronger machine changes the core count, not this argument.
- Accept condition: none foreseeable for this app. Revisit only if a single-process CPU-bound requirement appears that cannot be a separate process.

Also reject (unchanged): multiple uvicorn workers (duplicate scheduler, feeds, brokers; CLAUDE.md), `asyncio.to_thread` for the loops (GIL build, nothing left to move), Redis Streams between processes (adds a hop and a hard dependency to the order path for no parallelism), a Redis-backed shared pacer (new infrastructure on the order path; the static split suffices at this scale).

## 3. Exness as the only data source

### 3.1 The REST budget, by the numbers

- Limits [F: spike journal `docs/journals/2026-10-13-exness-api-spike.md:35-38`, researcher section 5]: 2 per second for `getCandleHistory`, `getDealsHistory`, `getTradingStateSnapshot`, `getLimits`, `getAvailableInstrumentList`; 10 per second account-wide; `max_candles_per_request` 1000; 429s arrive below the published rate because limits are counted for the whole access-point cluster [F: `exness_client.py:304`, Exness guide fetched today: "REST limits apply to the complete AP cluster"].
- Pacer [F: `exness_client.py:116-120,355`]: strictest method rate x 1.2 = 0.6 s between calls at `exness_rate_fraction` 1.0, so at most 100 calls per minute per process.
- Consumers after TV removal, with 6 Exness symbols (3 today + US500/USTEC/US30) [I from code]:

| Consumer | Calls | Share of a 100/min budget |
|---|---|---|
| `sync_1m` | 1 per symbol per minute (100 bars, one page) | 6% steady |
| `sync_verify_cascade` hourly | `n_bars=12` per interval (`sync_jobs.py:478`) | about 30 per hour |
| `sync_backfill` 03:00Z | 5 pages x 7 intervals x 6 symbols = 210 | about 2 min of continuous pacing |
| `sync_repair` 00:00/12:00Z | 5 pages per (symbol, interval) with a gap; EURUSD has a venue gap most nights [F: memory `exness-venue-no-tick-gaps`] | typically a handful, worst case 210 |
| one entry | `getTradingStateSnapshot`, `getAccountDetails`, `getDealsHistory`, `conditions` (cached 1 h), `openPosition`, up to 4 `getOperationStatus` polls [F: broker adapter `:299,332,379,657-659`] | 5-9 calls |
| one exit | `closePosition` plus polls | 1-5 calls |

Steady state uses under 10%; the bursts are two to four minutes a day. The budget is not scarce; **coordination** is.

### 3.2 Order priority

- In one process the pacer is a heap keyed `(0 if priority else 1, seq)` [F: `exness_client.py:171`]. Only `openPosition`, `closePosition` and `getOperationStatus` have priority (`:59-60`) [F]. The code-reviewer's M1 says the pre-order reads "wait in the same queue as candle backfills"; true, but the queue depth is bounded by the number of concurrent callers, and jobs run one call at a time (`max_instances=1`, sequential loops) [F]. So inside one process a non-priority pre-order read waits for at most about one in-flight job call plus one slot: about 1.2 s each, under 5 s per entry in the worst burst [I]. M1 is real but smaller than written, in one process.
- **Across processes there is no priority at all**: the worker's pacer and the trader's pacer do not see each other, and a burst from the worker can push the trader's `openPosition` into a 429, which is never retried and closes the snapshot gate until the next reconcile [F: `exness_client.py:305-307`, reviewer C/M1]. The fix that exists is `exness_rate_fraction` per process [F: `config.py:116-118`]. Sizing [I]: trader 0.7 (0.86 s spacing: an entry's 5-9 calls take 4-8 s), worker 0.25 (2.4 s spacing: the 210-call backfill takes about 8 min, fine at 03:00Z). The sum stays at 0.95 because 429s already arrive at fraction 1.0 in one process (72 retries in 7 days) [F].
- Latency floor: with 4 sequential pre-order REST calls, entry latency is set by the pacer spacing, not by CPU. A 1m live strategy cannot meet the reviewer's 2 s target this way [I]. Before any 1m live strategy, cache the balance snapshot for a few seconds and refresh the loss cap on fills rather than per order (reviewer M1 fix). Not needed for 15m/1h.
- Optional, after an owner check with Exness [U]: a 429 means the request was not processed, so one retry of `openPosition` with the same idempotency key after `Retry-After` would be safe. The client refuses that today by design (`exness_client.py:6-7`); keep it until the key semantics are confirmed.

### 3.3 Tick stream and strikes

- Limits [F: spike `:38`]: up to 10 active WS connections per account, 50 inbound messages per second, 25 tick-subscription operations per second, strike threshold 10 refilling 1 per 600 s. The Exness guide adds that WS limits are enforced per server node [F, fetched today]; no numbers on the page.
- The trader holds two WS (ticks, events) [F: `exness_quote_adapter.py:78-86`, broker adapter `:138`]. The worker needs none. The split adds no connection.
- Strike hazard [F: researcher section 8]: `ExnessQuoteAdapter.subscribe` checks only the instrument list, and `US500` is in it; every reconnect would send a rejected subscribe and take a strike. With reconnects clustering at 11-25 per hour during stalls [F], mapping the indices before the account returns data would exhaust the strike budget within an hour of a bad night [I]. Rule: add `US500/USTEC/US30` to `EXNESS_INSTRUMENTS` only after `getCandleHistory` returns 200 for them on the prod account.
- Two consumers on one account disturb each other (section 0). The lease and the `api`-only dev profile are the code side; the human side is a rule: no scripts against the prod account while the trader runs.

### 3.4 Bars from ticks vs fetched candles

Keep both paths as they are: the trader builds live bars from ticks (latency, no REST cost), the worker stores REST candles (source of truth for cascade, backtests, charts) [F: `bar_app_service.py:137-141` "No MongoDB write here"]. Both are bid-based [F: `exness_adapter.py:63`, researcher section 6], so they agree in price. They disagree on completeness after a feed drop (H3): a tick-built bar can be short and the next buckets missing, while the REST candle is whole. The guard belongs on the consumer: H3's successor check in `StrategyAppService` (skip entries on a non-consecutive bar). Do not add a "trader reads Mongo bars" fallback; it couples the order path to the worker's lag.

### 3.5 What this means for the split

- `worker`: `ExnessAdapter` (history) only; `exness_rate_fraction` 0.25; no WS, no broker, no bootstrap, no paper-row delete.
- `app` (`api` + `trader`): quote adapter, broker, routes; `exness_rate_fraction` 0.7. The ad-hoc sync/backfill/integrity routes (`routes/market_data.py:66-130`) [F] keep calling the provider from `app`; one admin user clicking them is inside the 0.7 share. Do not move them.
- Binance: stays data + paper; its own limits (1200 weight/min, `binance_adapter.py:3`) [F] are far from use and unaffected by the split.

## 4. Sequencing (smallest set)

Each step is one deploy and stays inside CLAUDE.md limits (a flow in one to three files; no new helper without two callers; dead code deleted in the same change).

**Step 0 — observe and stop lying (now, independent of everything).**
- Loop-lag probe task in the lifespan, `event_loop_lag_max_s` on `/health`.
- Skip listener: read `scheduled_run_times[-1]` on submission events; log a failed `record_skip` (72 silent failures in 7 days [F]).
- Correct the `scheduler.py` docstring (C3) to "exactly one process runs the scheduler".
- Dockerfile `python:3.14-rc-slim` -> `python:3.14-slim` (`deploy/Dockerfile:4,28`) [F].
- Files: `main_extensions.py`, `scheduler.py`, `Dockerfile`. Deploy outside 00:00, 03:00, 04:00, 12:00Z.

**Step 1 — live-path guards (before Phase 11 is re-run; one process).**
- H2 stale-entry guard and H3 gap guard in `StrategyAppService._on_bar_completed`, with one `live.signal_latency` log line per signal. Budgets: refuse entries older than 10 s (1m), 60 s (15m), 120 s (1h); exits always run.
- H1a: refuse an open while an `_inflight` open exists for the subscription; M3: seed the strategy's open direction from the position mirror on start, and accept a venue close only for an order marked as an exit.
- C1: the broker reads `entries_paused` from Mongo per open and fails closed; delete the in-memory flag and the route's dual write.
- Files: `strategy_app_service.py`, `exness_broker_adapter.py`, `exness_safeguards.py` + `routes/safeguards.py`. Tests: a pause through the route blocks the next open; a stale bar skips the entry and still runs the exit; a second signal while an open is in flight is refused.

**Step 2 — role gate, lease, worker service (the parallelism step).**
- `APP_ROLES` (set of `api`, `worker`, `trader`; default all three = today's behaviour) replaces and deletes `enable_jobs`. Lifespan branches: `worker` = indexes, orphan-job sweep, scheduler, jobs, catch-ups; `trader` = bootstrap, quote feed, collector, reconcile, paper-row delete; `api` = routes, backtests, orphan-backtest sweep. `remote-db.env` = `api`.
- Mongo lease, two callers (`worker`, `trader`).
- Compose: `worker` service from the same image, fixed `container_name`, no published port, `curl /health` healthcheck; `EXNESS_RATE_FRACTION` 0.25 for `worker`, 0.7 for `app`.
- Files: `config.py`, `main.py`/`main_extensions.py`, one lease module, `compose.prod.yml`, `remote-db.env` in `pocketquant-config`. Verify: `app` lag max under 1 s across 00:00/04:00/12:00Z; 15 `sync_1m` runs per 15 min; zero Exness WS reconnects at 00h/12h; a forced double start of `worker` is refused.
- Timing against TV: this can land before TV removal. The only TV exposure it adds is two scraper sockets from two processes (worker `sync_1m`, app ES quote polling). The corruption the client docstring describes is about two concurrent calls on **one instance** sharing `self.ws` (`tvdatafeed_client.py:6-15`) [F]; two processes each have their own instance. What remains is "two sockets on an unofficial endpoint that can ban us" (`:16-17`) [F]. TV is deprecated; a ban would only bring the removal forward. Accept it.

**Step 3 — TradingView removal (when the owner decides; see section 6).**
- Delete: `core/infra/tradingview/*`, `cme_globex_calendar_adapter.py` and its test, the `pandas_market_calendars` dependency, `tradingview_*` settings and `TradingViewPlan` enums, the DI and routing entries, the credential and health checks, the TV TTL in `quote_app_service.py`, `scripts/seed_index_futures.py`, the web TV branches, the docs lines (explore report section 1 is the checklist) [F].
- Delete the tracked symbols `ES1!/NQ1!/YM1!:TRADINGVIEW`. This cascades their bars, backtests and the `01a178ef` ES 15m paper subscription [F: memory `symbol-delete-cascades-all-data`]. The owner confirms this explicitly; the earlier "never stop/delete" note on that subscription predates the TV deprecation.
- After this step the CME stall no longer exists anywhere, and the worker's residual lag from section 1 is gone.

**Step 3b — Exness index onboarding (only when the account returns candles for `US500`).**
- One new calendar id `EXNESS_US_INDEX` in `exness_session_calendar_adapter.py`, table taken from the live `trade_sessions` once enabled (the docs table in the researcher's section 3 is the fallback); three entries in `EXNESS_INSTRUMENTS`; `ContractSpec`s from `getInstrumentCondition` (contract size 1, lot step 0.01, min 0.14/0.05/0.05) [F: researcher section 2]; a decision on whether the one-minute close-only windows count as open [U].
- Backfill: M1 depth is about 2.5 years on XAUUSD [F]; assume the same for indices [U].

**Drop:** the CME bisect rewrite; `ProcessPoolExecutor`; symbol-sharded workers; free-threaded Python; multiple uvicorn workers; Redis Streams and a shared Redis pacer; the api/trader split until the probe shows a need; H1b deterministic request ids until Exness confirms the idempotency-key window [U]; M2's account-level open lock until the bar lock stops covering HTTP (not planned).

## 5. Conflicts between the inputs, resolved

| # | Conflict | Side taken | Reason |
|---|---|---|---|
| 1 | kongming-0848 "no worker container" vs brainstormer "three services" | brainstormer's shape, in two steps (B then A on evidence) | the scraper-socket argument weakens to a ban-exposure risk on a deprecated source [F: docstring]; the owner wants multi-core; the api/trader split alone carries the C1 cost |
| 2 | brainstormer "calendar fix is a prerequisite for the split" vs this report | drop the bisect | it is a throwaway on code TV removal deletes; the split isolates trading; the residual worker lag is healed by existing lookbacks [F] and no money is exposed while live is disarmed [F] |
| 3 | brainstormer "process pool in the worker, defer" vs code-reviewer "one or more worker processes" | exactly one worker, no pool | no CPU-bound job survives TV removal; the REST budget is per account |
| 4 | code-reviewer M1 "pre-order reads queue behind backfill backlog" vs the pacer code | reviewer is right across processes, overstated within one | queue depth is bounded by concurrent callers and jobs are sequential [F: `exness_client.py:168-195`, `max_instances=1`] |
| 5 | kongming-0848 "stale-bar guard is a product decision" vs code-reviewer "mandatory" | mandatory before live, with the reviewer's budgets | feed drops at 00h/12h are now measured [F]; paper fills at the stale close hide the cost [F: reviewer H2] |
| 6 | explore "CME calendar becomes dead" vs researcher "indices need a new session table" | both; the new table is an Exness arithmetic calendar, not CME | `ExnessSessionCalendarAdapter` is generic over `week_sessions` [F: `:139`] |
| 7 | brainstormer "separate API key for the worker" (reviewer M1 option) vs static fraction split | static split | the Exness guide says limits vary by key and must not be assumed [F]; the probe evidence shows a second consumer on the account disturbs prod regardless of key [F, correlation] |
| 8 | brainstormer open Q7 "backtests in api or worker" | api | one admin user; a queue has no second caller |
| 9 | explore "ES/NQ/YM have no broker path" vs owner "Exness has equivalents" | both: names exist, data is blocked on this account [F: researcher] | owner action with Exness is the gate |
| 10 | earlier memory "never stop/delete the ES 15m paper subscription" vs TV deprecation | the deprecation wins, after an explicit owner confirmation | symbol delete cascades the subscription [F] |
| 11 | reviewer "trader lease must gate every boot sweep" vs brainstormer "sweeps follow their owner" | both, expressed as role-gated lifespan plus lease | the lifespan branch is where the sweeps start today [F: `main_extensions.py:132-172`] |

## 6. Prerequisites and owner questions

| # | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| 1 | Enable Indices (and Stocks) market data on the Exness account, or switch to an account type that has it. Today every Indices candle and tick call returns 404 `MARKET_INSTRUMENT_NOT_FOUND` [F: researcher]. Ask Exness why the category is blocked (account type "pro"?, jurisdiction, API product scope) | **Blocking** for ES/NQ/YM on Exness and for step 3b | nothing to do in code until it changes |
| 2 | Does TV removal wait for question 1, or are ES/NQ/YM dropped first (ending the `01a178ef` ES 15m paper run) and re-added as `US500/USTEC/US30` later? | **Blocking** for step 3's date; not for steps 0-2 | recommend: remove TV as soon as steps 0-2 are in, do not wait; the ES paper results do not transfer to a CFD anyway (price basis, sessions, lot units differ [F: researcher section 6]) |
| 3 | Keep `ES1!/NQ1!/YM1!` history for backtests, or let the symbol delete drop it? | not blocking | drop it: three weeks of 1m bars [F], unadjusted roll series, futures prices that the CFD will not match |
| 4 | New machine: cores, RAM, still one host with compose? | not blocking; sizes memory only | assume 4 vCPU, 8 GB, one host: `app` about 0.4-0.5 GB, `worker` 0.3 GB, Mongo 1-2 GB [I from today's 338 MB RSS] |
| 5 | Crypto: does Binance stay data + paper with `BTCUSD:EXNESS` as the live crypto path, or will Binance get a real broker? | not blocking; decides whether a second trader ever exists | assume Exness is the only live venue |
| 6 | Ask Exness: are REST limits counted per API key or per account, and what is the `EXN-IDEMPOTENCY-KEY` dedup window? | not blocking | per account; no order retry on 429 and no H1b until answered |
| 7 | After question 1: do the one-minute close-only windows print candles, and do `trade_sessions` mark them enabled? | blocking for the `EXNESS_US_INDEX` table only | treat close-only as closed for entries |
| 8 | Accept the two-scraper-socket exposure if step 2 lands before TV removal? | not blocking | accept (section 4, step 2) |

## 7. Success metrics

- `event_loop_lag_max_s` in `app` under 1 s every day, including 00:00, 03:00, 04:00 and 12:00Z and during a backtest.
- 15 `sync_1m` runs per 15 min around every cron; `data_lag_check` p95 under 0.3 s; `skipped_max_instances` rows appear when a run is really dropped.
- Zero `exness_ws.reconnecting` and `binance_ws.reconnect` in the 00h and 12h hours over 7 days.
- `exness.rate_limited_retry` per 7 days not above today's 72 after the split; zero terminal `exness.rate_limited` on `openPosition`/`closePosition`.
- A forced double start of `worker` or `trader` is refused by the lease; a pause through the API blocks the next open.
- After TV removal: `sync_integrity` under 10 s and `sync_repair` under 2 min (I/O only), with the CME adapter and `pandas_market_calendars` gone from the tree.

## 8. Assumptions

- The owner's "stronger machine" is one host with compose, at least 4 cores (high; the brainstormer assumed the same and nothing here needs more).
- Exness remains the only live venue in the near term; Binance is data and paper (medium; question 5).
- The 00h/12h WS reconnect clusters are caused by the loop stall (medium; correlation measured, mechanism not; the reviewer's ping-timeout explanation fits).
- The researcher's probe caused the four breaker opens on 2026-10-28 (medium; same account, same window; no other change known).
- Exness limits are counted per account, so a second API key would not add budget (medium; the guide says limits vary by key but must not be assumed; question 6).
- Index CFD history depth matches XAUUSD (low; untestable until question 1).
- Entry latency for 15m and 1h strategies is acceptable at 4-8 s given the pacer spacing (medium; the reviewer's targets are recommendations, not measurements).
- The ES paper results on TradingView data have no carry-over value once ES moves to a CFD (medium; based on the researcher's basis/session/unit differences).
