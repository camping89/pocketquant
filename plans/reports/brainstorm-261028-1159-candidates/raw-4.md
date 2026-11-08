# Brainstorm contract: parallel runtime, Exness-only data, TradingView removal

Labels: **[V]** means I checked it in code at the cited line or it comes from the cited report. **[I]** is my inference. **[U]** is unknown.

## 1. Outcome
- One 8 vCPU host runs three services from one image:
  - `api`: HTTP, SSE and backtests.
  - `worker`: APScheduler and all batch jobs.
  - `trader`: feeds, bar building, strategies, paper and Exness brokers, reconcile.
- `worker` and `trader` each hold a Mongo lease, so each is a singleton. `api` is stateless.
- TradingView and the CME calendar are gone, and so are ES/NQ/YM:TRADINGVIEW, their bars, backtests and subscription `01a178ef`.
- Exness is the only live venue. Binance stays data and paper only.
- The live path refuses stale or gapped entries and always runs exits.
- A 1m Exness entry reaches the venue in about 2 s or less.
- A deploy hands the trader over at a 1m boundary, with no missed bar and no missed order.
- `US500/USTEC/US30:EXNESS` are added only after the account returns candles for them.

## 2. Constraints
- Owner decisions D1–D10 and the `CLAUDE.md` limits:
  - a flow reads in three files at most, with at most two hops to I/O;
  - a new key or helper needs two real callers today;
  - dead code is deleted in the same change;
  - repositories live in core.
- No free-threaded Python. No multiple uvicorn workers.
- Never more than one process sending orders for the account.
- The rule "Single uvicorn worker only" in `CLAUDE.md` is rewritten as "one process per role; leases enforce worker and trader".
- **Flagged risk:** phases 2–4 add more code than they remove. Only the TV removal is a net deletion. `CLAUDE.md` says "stop and ask", so each phase's plan states its line delta and gets owner sign-off.

## 3. Non-goals
- No change streams or replica set. No Redis Streams. No shared Redis pacer.
- No process pool and no symbol sharding.
- No CME calendar bisect: the code is deleted with TV (kongming-1020 §1).
- No 429 retry on order calls until Exness confirms how its idempotency key works.
- No new state store (D9).
- No ES-to-CFD history mapping (D4).

## 4. Acceptance criteria

**Stalls**
- `/health.event_loop_lag_max_s` stays under 0.5 s every day in `trader` and under 1 s in `api` and `worker`. This includes 00:00, 03:00, 04:00 and 12:00Z and the time a backtest runs.
- In `job_history` after the TV removal: `sync_integrity` p95 under 10 s, `sync_repair` p95 under 120 s, and every UTC minute has one `sync_1m` row.
- "Error notifying listener" appears 0 times in 7 days. Today it appears 72 times [V packet].

**Parallelism**
- `docker ps` shows `api`, `worker` and `trader`.
- A forced second `worker` or `trader` start logs `lease.held_by_other` and never runs the scheduler or sends an order.
- The remote-DB dev profile runs with roles = {api}.

**TradingView removal**
- `git grep -i -e tradingview -e cme_globex -e pandas_market_calendars -- src web/src tests pyproject.toml uv.lock` returns nothing.
- In Mongo: `tracked_symbols`, `bars` and `backtests` have 0 rows matching `/:TRADINGVIEW$/`, and `01a178ef` is absent.

**Exness indices onboarding**
- Pre-flight check: `getCandleHistory US500 M1` returns 200 on the prod account. Only then are the instrument entries added.
- Calendar tests for `EXNESS_US_INDEX` cover both sides of 2026-11-01 and 2027-03-14.
- 7 days after onboarding: no integrity gaps outside calendar-closed minutes, and 0 ticks-WS strike or rejected-subscribe frames.

**Live-path safety (each item has a CI test)**
- **C1:** a pause through `api` blocks the next open in `trader`. If the Mongo read fails, the open is refused. `Safeguards.entries_paused` no longer exists.
- **C2:** the lease test above. Boot sweeps run only in their own role. Paper rows are no longer deleted at boot.
- **H1:** a second signal while an open is still in flight is rejected with `reason=open_in_flight`.
- **H2 and D10:**
  - An entry is refused when `occurred_at − (bar_start + interval)` is over 10 s / 60 s / 120 s. One `strategy.entry_skipped` WARNING is logged with `reason`, `age_s`.
  - The exit on the same bar still runs.
  - Backtests are unaffected, because backtest events set `occurred_at = bar.datetime` [V `backtest_app_service.py:136`].
- **H3:** a feed reconnect marks open bars `gapped`, and so does a bar after missing buckets. The test for missing buckets is `calendar.trading_minutes(prev_end, new_start)` non-empty [V port `trading_calendar_port.py:66`]. Entries on a gapped bar are refused and exits run.
- **M1:** with a fake client, the steady-state entry makes exactly one Exness call, `openPosition`.
- **M2:** the global bar lock stays [V `bar_app_service.py:90`]. Two simultaneous signals check the loss cap one after the other.
- **M3:** after a restart with an open mirror row, the strategy direction is seeded from it. An opposite-side entry that is not marked as an exit is rejected instead of closing the position.

**Latency**
- One `live.signal_latency` line per signal, with T0–T6 as in the reviewer's §5.
- Before go-live: a dry run of an Exness-broker subscription with live trading off gives T0→T5 p95 under 1.0 s. The `LIVE_TRADING_DISABLED` raise happens before the pacer [V `exness_client.py:265`].
- After go-live: T0→T6 p95 at or under 2 s over the first 20 1m entries.

**Zero-downtime deploy**
- 5 deploy drills during market hours.
- Each logs one `trader.handover_completed` with old `last_bar_end` and new `first_bar_end` per (symbol, interval). The new value must be the calendar successor of the old one.
- Pre-handover orders are terminal: 0 `exness.unknown_request_fill`.
- 0 nginx 5xx outside SSE.
- No `sync_1m` minute is missing.

## 5. Trade-offs (worst plausible case)

**Fork A: trader handover**

| Option | Load-bearing assumption | Fails first when |
|---|---|---|
| **A1 (recommended).** Standby trader holds the ticks feed and runs strategies with orders suppressed. On SIGTERM the old trader finishes bar T_b, waits until nothing is in flight, then releases. The new trader acquires, connects the events WS, reconciles the snapshot, hydrates paper positions and seeds directions before T_b+60 s. | Exness tolerates a second ticks WS for about 2 min. Published limit: 10 per account [V spike via kongming §3.3]. | A second session triggers breaker opens like the probe window did [V correlation, kongming §0]. Worst case: the handover is aborted and the old trader keeps running. |
| A2. Stop, then cold start. | Startup is under 1–2 s. | Always, for 1m: the first bar misses its opening ticks, so it is gapped and its entry is refused. That breaks D8. |
| A3. A long-lived ingest process feeds bars to the trader over Redis. | A Redis hop on the order path is acceptable. | Redis goes down and trading stops. It also breaks in-bus ordering I5/M4 [V reviewer]. |

Two A1 details:
- The standby must **not** connect the events WS. If it did, it would see the old trader's fill as an unknown request and block that instrument [V `exness_broker_adapter.py:506-511`].
- The seam: the standby starts its bar builders at the first full minute m0. Once Mongo has the 1m bars up to m0 (sync p95 11.9 s [V packet]), it replays stored closed bars into the strategies and seeds the in-progress higher-interval bar from 1m bars in [bucket_start, m0).
  - This replaces `_seed_builder_from_mongo` [V `bar_app_service.py:114,180`], which seeds from the lagging in-progress cascade bar.
  - The same path serves a crash restart (D9, DRY).

**Fork B: meeting the 1m pre-order budget**

Today an entry makes these paced calls in order: snapshot (`get_balance`) [V `:656-660`], `getDealsHistory` (loss cap) [V `:265-305`], `conditions` (cached for 1 h) [V `exness_client.py:373`], and `openPosition`. The spacing at trader fraction 0.6 is 0.6/0.6 = 1.0 s [V `exness_client.py:120,355`].

| Option | Assumption | Fails first when |
|---|---|---|
| **B1 (recommended).** Cache account state. A refresh loop at second :30 of each minute reads the snapshot and realized-today, and warms conditions. Any close deal triggers an immediate recompute, and the entry awaits a pending recompute. The entry is refused if the last good refresh is more than 90 s old. | The events stream delivers close deals. A missed one is bounded by the 60 s refresh. | Several 1m entries close in the same second. The global lock serializes them: the second waits about 1 s and the third goes over 2 s [I]. |
| B2. Give pre-order reads priority. | Three sequential calls fit in 2 s. | At any fraction ≤ 1: 2 × 1.0 s + 3 round trips is over 2 s [I]. |
| B3. Fetch the snapshot just before each bar close. | Loss state does not change in the last few seconds. | A close lands just before the fetch, so the cap is checked on an old number. |

**Fork C: sharing the Exness rate budget across processes**

| Option | Assumption | Fails first when |
|---|---|---|
| **C1 (recommended).** Static `exness_rate_fraction` per process: trader 0.6, worker 0.25, api 0.1. The first 3 s after each minute are kept for order calls: `sync_1m` moves from `second=2` [V `sync_jobs.py:707`] to 5, and the trader refresh runs at :30. | 429s come from window counting. They are not exact coincidences. | A repair or backfill burst is not aligned to the minute. Exness counts limits for the whole cluster [V `exness_client.py:304`], so an `openPosition` 429 can still happen. It is not retried and closes the snapshot gate [V `:305`, `:337-339`]. |
| C2. A separate API key for the worker. | Limits are counted per key. | Limits are counted per account [U]. A second consumer already disturbed prod [V correlation]. |
| C3. A Redis token pacer. | Redis is always up. | It adds new infrastructure on the order path. |

**Fork D: keeping bars complete**

| Option | Assumption | Fails first when |
|---|---|---|
| **D1 (recommended).** Tick-built bars, a `gapped` flag, entries refused on gapped bars, and the seam seed. | Exness and Binance reconnect hooks exist. The Exness one does [V `exness_quote_adapter.py:82`]. The Binance one has to be added in its reconnect loop [V `binance_websocket_adapter.py:225`]. | A silent tick drop without a reconnect. The 5 s watchdog reconnects in that case [V explore §3]. |
| D2. Repair a gapped bar from REST before publishing it. | Exness candles arrive within seconds. | 1m stale budget, plus REST calls on the hot path. |
| D3. The trader reads bars from Mongo. | — | Always: entries would be at least 10 s late, which breaks D2 [V kongming §3.4]. |

## 6. Better approaches
Better approaches: none. The recommended direction is the one requested. Evidence:
- With TV removed, no batch job is CPU-bound [V kongming-1020 §1].
- B1 is the packet's own M1 remedy [V kongming §3.2].
- The minute-window and seam choices refine the packet's plan; they do not reverse any decision D1–D10.

## 7. Recommended direction, in delivery order

**P0: observe (now)**
- Loop-lag probe and the skip-listener fix (`scheduled_run_times[-1]`).
- Correct the `scheduler.py` docstring.
- `python:3.14-slim`.

**P1: TV removal (D1/D4)**
- Delete the explore §1 checklist: `core/infra/tradingview/*`, `cme_globex_calendar_adapter.py`, `pandas_market_calendars`, the TV settings and enums, the DI and routing entries, the health and credential checks, the TV TTL, `seed_index_futures.py`, the web branches and the docs.
- Delete the three symbols. This cascades their bars, backtests and `01a178ef`.
- Your auto-memory still says never to stop or delete `01a178ef`. D1 replaces that note, so it needs updating.

**P2: live-path guards, still one process**
- C1:
  - **Change:** the broker reads `entries_paused` from Mongo on every open and fails closed.
  - **Delete:** the in-memory flag (`exness_safeguards.py:23,25-31`) and the in-memory flip in the route (`routes/safeguards.py:44-49`; the store write stays).
- H1: the in-flight open check.
- H2, H3 and D10: the stale and gap guards in `StrategyAppService._on_bar_completed`. A single "is this an exit" test (an opposite side to the mirror position) drives both the guard and the M3 exit marking.
- B1 cached account state, and `live.signal_latency`.
- D9 rebuild: replay stored bars and seed directions from the position mirror.
  - **Change:** the paper broker reloads its open positions from the mirror rows.
  - **Delete:** the paper-row delete at boot (`position_app_service.py:44-47`).
- **Delete** also: `flush_all_bars` (`bar_app_service.py:270`) and the wrong "at-least-once" docstring.

**P3: roles and leases (D6)**
- **Change:** `APP_ROLES` replaces `enable_jobs`. **Delete** `enable_jobs`, including its scheduler gate (`di/infrastructure.py:100-105`). The scheduler starts when it is resolved, so the worker lease must be acquired before that resolve [V].
- One lease repository in `core.infra.persistence.repositories`, with two callers (worker and trader).
  - 30 s TTL, 10 s renew.
  - Before every order send, a memory check that the lease is still valid for more than 5 s.
  - Fail-stop on a lost renew.
- Compose: `api`, `worker`, `trader`. Exness fractions 0.6 / 0.25 / 0.1, and the `sync_1m` second moves to 5.

**P4: zero-downtime deploy (D7/D8)**
- Remove `container_name` from `api`, `worker` and `trader`; the lease guarantees one active owner.
- The deploy script runs each service in turn (worker, then api, then trader): scale to 2, wait for health (for the trader, `standby_ready`), stop the old container by ID with a 120 s grace period.
- nginx (`web/nginx.conf:26`) must re-resolve the `api` name.
- `/health` reports `lease` and `seam_ready`.

**P5: Exness indices (gated on a 200)**
- `EXNESS_US_INDEX` table in `America/New_York`, three `EXNESS_INSTRUMENTS` entries, `ContractSpec`s from `getInstrumentCondition`, backfill.

**Before `EXNESS_LIVE_TRADING=true`:** P2–P4 run in prod on paper for 7 days, and the 5 handover drills plus the latency dry run pass.

## 8. Open questions

| # | Question | Blocking? |
|---|---|---|
| 1 | Exness returns 404 for Indices data on this account [V researcher]. Who enables it? | Blocks P5 |
| 2 | Does a second ticks WS session for about 2 min disturb the account (breaker opens, strikes)? Test it during a paper drill. | Blocks P4 sign-off |
| 3 | Are REST limits counted per API key or per account? | No |
| 4 | How long does Exness deduplicate `EXN-IDEMPOTENCY-KEY`? Should a 429 on `closePosition` be retried, given D10 says exits always run? Today the exit is rejected and only the venue stop-loss protects the position. | No, but owner decision |
| 5 | Do index close-only minutes print candles or count as open? | Blocks the index calendar |
| 6 | Paper balance after a restart: initial balance plus realized trades, or reset as today? | No. Default: rebuild |
| 7 | What is the most simultaneous 1m Exness entries per minute? The 2 s budget holds for about 2 [I]. | No |
| 8 | Stale budgets for live intervals other than 1m, 15m and 1h? | No |
| 9 | When the scale-to-2 deploy removes the old container, does compose then keep the right one? | No, check in P4 |
| 10 | Does the nginx version in use support re-resolving `api` (upstream `resolve`), or is it resolver + variable? | No, check in P4 |
| 11 | When Mongo is unreachable the trader fail-stops, including strategy exits, and only the venue stop-loss protects open positions. Do you accept that? | No |
