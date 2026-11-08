---
title: "Process topology for true parallelism (api / worker / trader)"
date: 2026-10-28
status: advisory, no code changed
inputs: code on develop @ 453e8e90, plans/reports/kongming-261028-0848-event-loop-concurrency-review.md, plans/reports/debug-261023-0045-daily-0400-integrity-event-loop-stall.md, uv.lock, APScheduler 3.x FAQ
---

# Process topology for true parallelism

## TL;DR

Run the same image as **three OS processes (compose services)**, picked by a role setting:

| Service | Owns | Replicas |
|---|---|---|
| `api` | HTTP routes, SSE (Redis polling), backtests, ad-hoc sync/backfill routes | 1 now (N possible later) |
| `worker` | APScheduler + every batch market-data job | exactly 1 |
| `trader` | live quote ingest, bar builder, strategies, brokers (paper + Exness), reconcile loop, trade collector | exactly 1 per broker account |

The live trading chain stays inside one process on the in-process `EventBus`. The code already
puts it there; nothing in it needs a cross-process bus. Processes talk only through things
they already share: Mongo (desired state, subscriptions, bars, positions) and Redis (quotes,
in-progress bars). Three changes do the real work:
1. A role setting that gates the lifespan steps. It replaces `enable_jobs`.
2. The Exness entry pause is read from Mongo when an order opens, not from per-process memory.
3. The Exness REST rate budget is split across processes with the existing `exness_rate_fraction` setting.
A Mongo lease enforces the singletons.

Reject for now: free-threaded 3.14t, multiple uvicorn workers, a process pool, and splitting
ingest from strategies. The calendar fix in the kongming report is still a prerequisite: the
worker runs `sync_1m` and `sync_repair` on one loop, so a 25-49 min CPU burn would still stall
bar persistence and data-lag checks. It would no longer stall trading.

## 1. Challenge to the brief

- **"True parallelism" is not the goal; isolation is.** Prod CPU is low in steady state (app at
  3.6% in one snapshot, kongming report). The measured stalls are one wasted computation (CME
  `bar_start` via `iterrows`). More cores help only by giving trading a core that batch work
  cannot take. That is a real benefit with real money involved. Judge every split by "does it
  isolate the money path?", not by "does it use more cores?".
- **The new constraints reverse the earlier "no worker container" advice, and they bring in a new
  coupling.** Kongming rejected a worker mainly because the TradingView scraper would run in two
  processes (one-session ban risk, `tvdatafeed_client.py:6-17` per that report). With TV gone,
  that reason goes away. But with "data from the broker", candle history and live orders use
  **the same Exness account's REST rate budget** (`exness_client.py:116-120`
  `global_account_rate`). Today one in-process pacer gives order calls priority over candle
  calls (`exness_client.py:147-152`). That priority does not work across processes. See section 5.
- **The bar-close-to-order chain must not be split across processes.** It runs as in-process
  function calls today. Putting a network hop in it adds latency and a failure mode (Redis
  down = no trading) and buys no parallelism.

## 2. Who owns what today (facts)

| State / loop | Where | Notes |
|---|---|---|
| One process, one loop | `deploy/compose.prod.yml` `app` service; Dockerfile `CMD uvicorn` single worker | Comments forbid `--workers N` |
| `EventBus` (in-memory pub/sub, sequential await) | `core/common/messaging/event_bus.py`; APP singleton `di/infrastructure.py:57-59` | Backtests use their own bus (`backtest_sandbox_app_service.py:134`) |
| Tick -> bar builder `_bars` dict, publishes `BarCompletedEvent` | `bar_app_service.py:76,151-162` | Writes `bar:current` to Redis; not Mongo |
| Strategies, brokers, broker pool | `strategy_app_service.py:58-66`, subscribes to bus `:81-83` | RAM only; rebuilt from Mongo subscriptions |
| Paper broker SL/TP on `BarCompletedEvent` | `paper_broker_adapter.py:145` | Needs the same bus as the bar builder |
| Exness broker: positions, in-flight orders, events WS | `exness_broker_adapter.py:105-122,133-145` | One events WS per adapter |
| Exness ticks WS | `exness_quote_adapter.py:74-80` | Via `RoutingRealtimeQuoteAdapter` (`di/adapters.py:110-127`) |
| One `ExnessClient` for history, quotes and orders | `di/adapters.py:82-87` | Per-process pacer, order priority (`exness_client.py:147-152`), `exness_rate_fraction` (`config.py:116-118`) |
| Order/position managers load from Mongo at build | `di/services.py:114-133` | |
| Reconcile loop: Mongo `desired_state` -> RAM, every 5 s | `strategy_reconcile_app_service.py:1-20,90-104`; `config.py:141` | Already declarative |
| Route writes: start/stop/add/remove subscription | `strategy_command_service.py:21-25` | "pure Mongo writes, no engine dependency" |
| SSE quotes / bars | `routes/market_data_quotes.py:58-85`, `routes/market_data.py:216-233` | Poll Redis (+ Mongo fallback); already cross-process safe |
| Safeguards (`entries_paused`) | `exness_safeguards.py:10-17` "One object per process"; route flips memory then Mongo `routes/safeguards.py:43-49` | **Breaks after a split** (section 4) |
| APScheduler, Mongo jobstore, AsyncIOExecutor | `scheduling/scheduler.py:52-77` | Its comment claims multi-process coordination; the APScheduler 3.x FAQ says sharing a jobstore across processes is unsupported ("duplicate execution or ... missing jobs") |
| Batch jobs use a module-global container | `sync_jobs.py:97-121` | Cannot run as-is in a `ProcessPoolExecutor` |
| Backtests: `asyncio.create_task` in the API | `routes/backtest.py:67-68`; orphan sweep on boot `main_extensions.py:132-141` | Sweep assumes a single process |
| Gating: one `enable_jobs` flag for scheduler + collector + reconcile | `main_extensions.py:211-238`; bootstrap ignores it `:161-172` | |
| Redis usage | `persistence/redis.py`: get/set/mget/delete/scan only | No pub/sub or streams anywhere (grep) |
| Mongo | `mongo:7.0.45`, no `--replSet` in compose | Inference: standalone, so **no change streams** without converting to a single-node replica set |

## 3. Options

### A. Three role-gated processes from one image (recommended)

```
             nginx(web) --> api  (uvicorn, routes, SSE, backtests)
                              |  writes desired_state, safeguards --> Mongo
                              |  reads quote:latest / bar:current <-- Redis
 worker (APScheduler, sync_1m, cascade, integrity, repair, backfill, verify, data_lag)
                              |  sole scheduled writer of bars --> Mongo, data_lag --> Redis
 trader (Exness ticks WS + events WS, Binance WS, BarAppService, EventBus,
         StrategyAppService, paper + Exness brokers, reconcile loop, LiveTradeCollector)
                              |  reads subscriptions/safeguards <-- Mongo, writes orders/positions/trades
                              |  writes quote:latest / bar:current --> Redis
```

- Parallelism: 3 GILs, 3 loops, each on its own core.
- Cross-process traffic: none new. API -> trader already goes through Mongo `desired_state`,
  picked up within 5 s. Trader -> API already goes through Redis.
- Code delta (estimate): a role setting replacing `enable_jobs` (~30 lines across `config.py`,
  `main.py`, `main_extensions.py`), safeguards read-through (~10 lines), a Mongo lease (~40
  lines, two callers: worker and trader), compose: two more services.
- Second-order effects:
  - A deploy still restarts all three, which is no worse than today.
  - Memory: about 3 x 150-300 MB Python processes (assumption from the kongming estimate).
  - Each process holds its own Mongo and Redis pools.
  - Logs come from three containers, so the correlation ID matters more.

### B. Two processes: `app` (api + trader) + `worker`

- The smallest step that isolates batch jobs: only the scheduler moves.
- HTTP, SSE polling and backtests stay on the trading loop. Backtests yield every 10 bars, but
  their CPU still competes with order handling (kongming, row 7).
- Recommended as **step 1 of the migration** toward A, not as the end state.

### C. Fine-grained services (ingest per venue -> Redis Streams -> strategy runners -> execution service)

- Most parallel. The bar-to-order chain picks up 2-3 network hops, consumer-group acks, and
  idempotency on every hop. Bar events are already at-least-once with idempotent subscribers by
  contract (`bar_app_service.py:149`), but orders are not idempotent across processes.
- Redis becomes a hard dependency of trading. The single-owner rules multiply: per stream, per
  consumer, per account.
- Reject unless a profile shows ingest CPU saturating a core. One-account Exness tick rates make
  that unlikely (inference).

### D. In-process parallelism (rejected as the main mechanism)

**Free-threaded 3.14t: reject.**
- Verified: `uv.lock` has `cp314t` manylinux x86_64 wheels for numpy 2.4.1, pandas 3.0.0,
  pydantic-core 2.41.5, pymongo 4.16.0, uvloop 0.22.1, cryptography 46.0.4, pyyaml 6.0.3,
  websockets 16.0 and watchfiles 1.1.1. There is none for httptools 0.7.1. Inference: uvicorn then
  falls back to h11.
- Not verified: whether each extension declares `Py_mod_gil`. If one does not, the GIL silently
  turns back on at import. pandas thread-safety is described as "partial" by third-party 2026
  sources, not by pandas itself. Python-level deps (pandas-market-calendars, exchange-calendars,
  APScheduler, dishka, structlog) need no wheel, but nobody audits their shared-state safety.
- Decisive reason: the app is single-loop asyncio, and every money-path structure is loop-only
  (`_bars`, strategy dicts, broker state, the Dishka container). Threads would add data races to
  the order path. Processes give the same parallelism with isolation built in.

**`ProcessPoolExecutor` inside the worker: defer.**
- Job bodies resolve dependencies from a module-global container (`sync_jobs.py:97-121`), so they
  must be rewritten as pure (docs, calendar) functions before they can be pickled.
- The calendar fix removes the need (inference, kongming estimate: minutes to seconds).
- Revisit only if the worker's own lag probe shows a job holding its loop for more than about 30 s.

**Multiple uvicorn workers: defer, even for `api`.**
- After A, `api` is close to stateless, but the backtest orphan sweep at boot would fail another
  worker's running backtest (`main_extensions.py:132-141`).
- `RateLimitMiddleware` is per process, so limits multiply by N (inference from its in-process
  registration, `main_extensions.py:321`).
- One admin user does not need it.

**`asyncio.to_thread` for CPU loops: reject.** This is a GIL build; the kongming report covers it.

## 4. State that must move out of process memory (for A)

1. **Exness entry pause (`Safeguards.entries_paused`): blocking item.**
   - Today the API route flips the in-memory object, then Mongo (`routes/safeguards.py:43-49`).
   - In `trader` that object is a different instance, loaded once at boot (`di/adapters.py:49-59`).
     After the split, **the kill switch would silently stop working.**
   - Fix: the Exness broker reads `entries_paused` from Mongo on every open. Opens are rare, and
     the read costs about 1 ms. If the read fails, reject the open (fail closed).
   - Closes stay ungated, as today. Env caps stay env (the same in every process).
2. **Lifespan steps per role.**
   - `api`: indexes, health, routes, backtest tasks, orphan-backtest sweep.
   - `worker`: indexes, orphan-job sweep, scheduler + sync jobs + catch-ups.
   - `trader`: indexes, `bootstrap_live_instances`, quote feed, live trade collector, reconcile loop.
   - `ensure_indexes` is idempotent in Mongo, so every role may run it.
3. **Orphan sweeps follow their owner.**
   - `recover_orphan_jobs` must run only in `worker`. Otherwise an API restart marks the worker's
     running job as failed (`main_extensions.py:144-158`; it sweeps `running` rows older than 600 s).
   - `recover_orphan_backtests` runs in the role that runs backtests.
4. **Health.** Each service keeps `/health` (same app, routers trimmed by role), so the compose
   healthchecks stay `curl`. Live feed freshness is already visible through `data_lag` in Redis.
   No new heartbeat is needed for the first cut.
5. **Nothing else needs a bus.**
   - Strategy commands are Mongo-declarative. SSE reads Redis.
   - `sync_1m` writes Mongo, and strategies take bars from ticks, not from Mongo (kongming 3.5).
   - If push is ever needed, Redis Streams is cheaper than Mongo change streams, which need a
     replica set (inference).

## 5. Exness REST budget across processes (new coupling from constraint 2)

- Fact: limits are per account (`global_account_rate`, `exness_client.py:116-120`). 429s can
  arrive under the limit because limits are cluster-wide (`:304`). A 429 on an order call is
  never retried (`:6-7`).
- Fact: `exness_rate_fraction` exists for exactly this case: "Share of the published request rate
  one process may use" (`config.py:116-118`).
- Recommendation: a static split through env per service, for example `trader` 0.5, `worker`
  0.35, `api` 0.15. These numbers are assumed; size them from the real limit and the symbol count.
- The ad-hoc sync/backfill routes in `api` (`routes/market_data.py:66-130,319`) also call the
  provider. Either give them the small share or have them enqueue a worker one-off job. The static
  share is the KISS choice.
- Rejected for now: a Redis-backed shared pacer with priority. It is correct, but it is new
  infrastructure on the order path.

## 6. Exactly-once and single-owner guarantees

**One scheduler.**
- Mechanism: a compose service with a fixed `container_name`, plus a Mongo lease `scheduler`.
  Compose refuses to scale a service with a fixed `container_name` (from the Compose spec, not
  re-fetched today).
- Why the lease too: `scheduler.py:52-55` invites "VPS + local" sharing of the jobstore, which
  the APScheduler 3.x FAQ calls unsupported. Today only `ENABLE_JOBS=false` in `remote-db.env`
  (README:54) prevents it.

**One trader per broker account.**
- Mechanism: a lease `trader:<venue>:<account>` (one lease while there is one trader).
- The trader is also the only holder of the Exness ticks and events WebSockets, and the only
  builder of brokers.

**One live subscription owner.**
- Follows from the trader lease: only the lease holder runs `bootstrap` and the reconcile loop.
- Today `bootstrap_live_instances` runs even with `enable_jobs=false` (`main_extensions.py:161-172`).
  Inference, not verified: a remote-DB dev session loads prod subscriptions into local RAM. The
  role gate closes this.

**Batch jobs.** Unchanged: `coalesce` and `max_instances=1` (`scheduler.py:64-69`). Bar upserts
are idempotent.

**Lease design** (about 40 lines, two callers):
- Acquire with `find_one_and_update` on `{_id, $or: [{expires_at < now}, {owner: me}]}`, setting
  `owner` and `expires_at = now + 30 s`, with upsert. A duplicate-key error means another process
  holds it.
- Renew every 10 s.
- Release on clean shutdown, so a deploy hands over at once.
- Fail-stop: if a renewal fails or is lost, the process exits, and compose restarts it.
- There is no fencing token. On one host with compose this is acceptable (inference). Exness order
  requests already carry an idempotency key (`exness_client.py`, `sign_headers(...,
  idempotency_key=...)`). That protects retries, not split-brain.

## 7. Recommended migration order

0. **Prerequisite (independent):** kongming steps 1-3 (CME session table + bisect, loop-lag
   probe, skip-listener fix). Also move the Dockerfile from `python:3.14-rc-slim` to
   `python:3.14-slim`. Reason: the worker still co-hosts `sync_1m` and `sync_repair`.
1. **Role setting** `APP_ROLES`, a set of `api`, `worker` and `trader`.
   - The default (all three) is today's behavior. Delete `enable_jobs` in the same change.
   - Local and remote-DB dev profiles map to explicit role sets.
2. **Safeguards read-through** and **per-service `exness_rate_fraction`**. These must land
   before any split.
3. **Split the worker out** (option B): `app` runs `api,trader` and `worker` runs `worker`. Add
   the lease for the `worker` and `trader` roles.
   - Verify: `app` loop-lag max under 1 s across 00:00, 04:00 and 12:00 UTC.
   - Verify: 15 `sync_1m` runs per 15 min.
4. **Split `api` from `trader`** (option A). `web` depends on `api`. `trader` has no HTTP port
   beyond health.
   - Verify: a pause takes effect on the next open.
   - Verify: start/stop converges within 5 s, and SSE is unchanged.
5. **Only on evidence:**
   - A trader per venue. The shard key is the symbol suffix, which under constraint 2 is also the
     execution venue (`XAUUSD:EXNESS` goes to trader-exness). Paper subscriptions follow their
     symbol's venue.
   - A process pool in the worker.
   - More `api` workers.

**Sizing (assumption):** 4 vCPU and 8 GB are enough for A (api ~0.2 core, trader ~0.5-1 core,
worker ~1 core in bursts, Mongo 1-2 cores, Redis small). More cores than that buy nothing until
step 5 has evidence.

## 8. Risks

- **The kill switch breaks if step 2 is skipped.** This is the highest risk. Gate step 4 on a
  test: a pause through `api` blocks an open in `trader`.
- **Rate budget starvation:** worker backfill bursts (5000 bars x 7 intervals per symbol,
  `sync_jobs.py:371-377`) take budget from orders if the fractions are wrong. Watch
  `exness.rate_limited` warnings.
- **Role misconfiguration** (two processes both holding `trader`): the lease turns this into a
  refused start instead of duplicated orders.
- **Deploy handover gap:** the trader is down between the old container's stop and the new one's
  start (as today). If the old one died uncleanly, add up to the lease TTL.
- **Three log streams:** debugging crosses containers. Keep correlation IDs and add the role as a
  log field.

## 9. Success criteria

- Trader loop-lag max under 1 s every day, including during worker jobs and backtests.
- Zero duplicate orders or subscriptions after a forced double start (lease test).
- No `exness.rate_limited` on order operations over 7 days.
- `sync_1m` runs once a minute without gaps, and `data_lag_check` takes about 0.1 s.

## Assumptions

- The new host is a single machine with compose (no orchestrator). Confidence: high.
- Exness is the only live venue near-term; Binance stays data + paper. Confidence: medium.
- Steady-state CPU per process is low, and the stalls come from the calendar bug. Confidence: high
  (prod job_history, kongming report).
- Each Python process uses 150-300 MB RSS. Confidence: medium.
- Exness allows the trader's two WebSockets as today, and option A adds no WebSocket. Confidence: high.

## Unresolved questions

1. What are the core count and RAM of the new machine? Is it still one host with compose, or
   several hosts?
2. Which venues besides Exness will have real brokers? Is Binance only data and paper, or a real
   broker later? This decides whether the step 5 sharding is ever needed.
3. What are the real Exness `global_account_rate` and per-method limits, and how many `:EXNESS`
   symbols will be tracked? These set the fraction split.
4. Does Exness allow more than one ticks or events WebSocket per account? This matters only for
   per-strategy traders, which this report does not recommend.
5. Is a 5 s reconcile latency acceptable for start/stop now that the API and trader are separate
   processes? It is unchanged from today.
6. In remote-DB dev mode, should local run `api` only? Today it also runs the live feed and bootstrap.
7. Should backtests stay in `api` (the KISS choice) or move to `worker` (keeps API latency flat
   during long runs)?

## Sources

- APScheduler 3.x FAQ, job store sharing: https://apscheduler.readthedocs.io/en/3.x/faq.html
- Free-threaded 3.14 package status (third-party, 2026):
  https://reptile.haus/journal/pypi-free-threaded-wheels-audit-500-packages-2026/ and
  https://www.danilchenko.dev/posts/python-314-free-threading/
