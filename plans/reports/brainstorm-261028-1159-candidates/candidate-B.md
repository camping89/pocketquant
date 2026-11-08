# Candidate B

# Brainstorm contract: api / worker / trader split, Exness-only data, zero-downtime trader handover

Labels: **[V]** means I checked it at the cited file:line or in a cited report. **[I]** means it is my inference. Report names are shortened (kongming-1020, reviewer, brainstormer-0915, researcher).

## 1. Outcome
- One host (8 vCPU / 16 GB) runs three services from one image, chosen by `APP_ROLES`:
  - `api`: routes, SSE, backtests.
  - `worker`: APScheduler and all batch jobs. Exactly one owns the scheduler, enforced by a lease.
  - `trader`: feeds, bars, strategies, brokers and reconcile. Exactly one owns the account, enforced by a lease.
- TradingView, the CME calendar, `pandas_market_calendars`, `ES1!/NQ1!/YM1!:TRADINGVIEW` and the `01a178ef` subscription are deleted.
- `US500/USTEC/US30:EXNESS` are added only after Exness serves their data.
- A deploy restarts `api` and `worker` rolling. A new `trader` warms up next to the old one, takes the lease at a 1m boundary, and the old one exits. No bar evaluation and no order is lost or duplicated.
- A 1m entry reaches the venue within about 2 s of bar end. Entries on stale or gapped bars are refused; exits always run.

## 2. Constraints
- D1-D10 and the `CLAUDE.md` limits: a flow reads in ≤3 files, ≤2 hops to I/O, a new helper needs a second caller today, dead code is deleted in the same change, and a change that grows the code needs an owner OK.
- The "single uvicorn worker" rule in `CLAUDE.md` is rewritten to "one lease holder per role". Comments at `compose.prod.yml:62-63` and `Dockerfile:62` are updated to match.
- No free-threaded Python, no `--workers N`, no Redis Streams, no shared Redis pacer, no new state store (D9).
- Mongo migrations must be expand-only. During a rolling deploy, old and new code read the same schema [I].
- Live trading stays disarmed until phase P5 below.

## 3. Non-goals
- Live crypto, a Binance broker, symbol-sharded workers, a process pool.
- Deterministic order ids (H1b) until Exness confirms the idempotency window.
- Multi-host deployment. Keeping ES history (D4).
- Making in-flight backtests survive an `api` restart; they fail today too [V `main_extensions.py:132-141`].

## 4. Acceptance criteria
| Area | Observable check |
|---|---|
| Stalls | `/health` `event_loop_lag_max_s` < 1 s in every role every day, including 00:00/03:00/04:00/12:00Z and during a backtest. `sync_repair` < 120 s and `sync_integrity` < 10 s in `job_history`. Zero `exness_ws.reconnecting` / `binance_ws.reconnect` in the 00h and 12h hours over 7 days. |
| Scheduler | Exactly 1,440 `sync_1m` rows per day with no gap over 90 s, including across deploys. Zero "Error notifying listener" lines. `skipped_max_instances` rows appear only for real drops. |
| Parallelism | `docker stats` shows three backend containers. A forced second start of `worker` or `trader` logs `lease.refused` and never starts the scheduler, feeds or broker. A CI test covers two lease contenders. |
| TradingView removal | `grep -ri tradingview src web tests` returns nothing. `pandas_market_calendars` is gone from `uv.lock`. `db.symbols.find({code:/1!$/})` returns 0 documents. The 8 import contracts and the metric ratchet pass. |
| Index onboarding | Gate: `getCandleHistory US500 M1` returns 200 on the prod account. After onboarding: zero `MARKET_INSTRUMENT_NOT_FOUND` frames, zero WS strikes, `data_lag` < 120 s in-session. A CI test covers `EXNESS_US_INDEX` sessions on both sides of a DST change. |
| C1 | CI and prod: `POST /admin/safeguards/pause` on `api` blocks the next open in `trader` and logs `exness.order_rejected_presubmit reason=entries_paused`. If the Mongo read fails, the open is refused. |
| C2 | Only the `trader` lease holder runs bootstrap, feeds, reconcile and broker connect. The remote-DB dev profile runs `api` only. |
| H1 | CI: a second signal for a subscription while its open is in flight is refused. |
| H2 / D10 | CI: a 1m bar evaluated 11 s late, a 15m bar 61 s late, a 1h bar 121 s late, or any bar with a feed gap inside it skips the entry and logs exactly one `strategy.entry_skipped` WARNING with `reason=stale|gap`. Paper SL/TP still fire on that bar. |
| H3 | CI: a non-successor `bar_start` logs `strategy.bar_gap` and the entry is skipped. Prod: the count of these lines equals the feed disconnects. |
| M1 / latency | A `live.signal_latency` line per signal carries T0..T6. p95(T6−T0) ≤ 2 s for 1m. The count of non-priority Exness calls between signal and `openPosition` is 0. |
| M2 / M3 | The global bar lock stays, so no concurrent opens pass the loss cap. CI: after a restart, an opposite entry while a position is held does not close it, and the strategy direction is seeded from the position mirror. |
| Handover | Every trader deploy logs one `trader.handover` line with `processed_through` and `gap_ms` ≤ 2,000. Per subscription, the `bar_start`s evaluated live by old and new together are contiguous with no duplicates (CI test with two trader instances on a fake feed). `orders` has no two orders per subscription inside one bar interval. Zero `unknown_request_fill` after a handover. |
| api / worker | An external 1 req/s probe through Cloudflare sees 0 non-2xx responses during a deploy. SSE reconnects within 5 s. |

## 5. Trade-offs

**Fork A: how the trader hands over** (D8)

| Option | Assumption it depends on most | What fails first | Worst plausible case |
|---|---|---|---|
| A1. Shadow then transfer. The new trader opens its own ticks WS but writes nothing to Redis, runs no strategies and has no broker. It builds bars in a buffer. The old trader processes the bars closing at T, drains `_inflight`, stops strategies and the events WS, then compare-and-sets the lease (owner, `processed_through=T`). The new trader replays stored and buffered bars with signals discarded, then connects the broker. | Exness accepts a third WS session on the account (published limit 10 [V spike via kongming-1020 §3.3]) without disturbing the old sessions | Old trader's ticks WS drops while the new one shadows | Old trader's bars are marked gapped, so entries are refused for one bar (safe). The 2026-10-28 probe correlated with breaker opens [V kongming-1020 §0]. |
| A2. Cold transfer. The new trader warms up from Mongo only and opens its WS after taking the lease. | WS connect and subscribe finish within about 2 s | A slow access-point lookup or backoff | The first post-handover 1m bar misses its opening ticks. D10 then refuses its entry, which is a missed bar and breaks D8. |
| A3. The old trader writes its builder state to a handoff record. | — | — | This is a new state store, which D9 forbids. Rejected. |

**Fork B: how the 1m entry meets ≤ 2 s**

| Option | Assumption | What fails first |
|---|---|---|
| B1. Cache balance and realized-today in the adapter. Refresh every 15 s, after every fill or close on the events stream, and keep conditions warm before their 1 h TTL. Fail closed if the cache is older than 60 s. Close bars by timer at bar_end + 0.5 s, or on the first next-bucket tick if earlier. | `openPosition` round trip ≤ about 1 s [unknown] and host vs venue clock skew < 0.5 s | Three 1m entries at the same boundary. The pacer spaces even priority calls [V `exness_client.py:147-195`], so the third order waits about 2 × 0.86 s plus RTT and goes over 2 s [I]. A venue-side SL close that the stream missed can let one open through a cap breached in the last 15 s [I]. |
| B2. Per-method pacing, so orders go at the 10/s global rate | Order ops are not in the 2/s list | 429s already arrive below the published rate (72 in 7 days [V]), so this is rejected |

Today the pre-order path pays for `getTradingStateSnapshot` + `getAccountDetails` once + `getDealsHistory` + an hourly `conditions` call [V `exness_broker_adapter.py:216-243,277-305,656-669`]. Bars also close only on the next tick [V `bar_app_service.py:117-132`].

**Fork C: how the processes share the Exness rate budget**
- C-1 (recommended). Static fractions: trader 0.6, worker 0.25, api 0.1 [V the setting exists, `config.py:118`]. Move `sync_1m` from second 2 to second 15.
  - Reason: today it fires exactly when 1m entries leave [V `sync_jobs.py:703-709`].
  - What fails first: the standby trader's warm-up calls push the total past 1.0 during an overlap. That is about 10 calls [I].
- C-2. A separate API key for the worker. Its assumption (limits counted per key) is unverified, and a second consumer disturbed prod regardless of key [V kongming-1020 §0]. Rejected.

**Fork D: keeping bars complete across a feed drop or handover**
- D-1 (recommended). At takeover, seed in-progress higher-interval bars from the Mongo 1m and cascade bars before the shadow start, plus the trader's own 1m bars after it.
  - This extends the existing `_seed_builder_from_mongo` [V `bar_app_service.py:180-208`].
  - A feed drop marks the symbol's open bars as gapped. After the gap, the strategy re-warms from Mongo, which is the same function as cold start and handover. Entries stay refused until then.
  - Assumption: the worker's `sync_1m` is current. Failure: worker lag, so the takeover is postponed. Bounded; the deploy aborts and the old trader keeps running.
- D-2. Gap-flag only, no re-warm. Strategy windows then keep holes for N bars and diverge from backtests [I].

## 6. Better approaches
None. The recommended direction is the requested one: D6, D8 and D9 map directly onto existing seams.
- Mongo desired-state plus a 5 s reconcile [V brainstormer-0915 §2].
- The existing Mongo seed [V `bar_app_service.py:180`].
- Position mirror rows carry SL/TP [V `position/entities.py:40-41`].
- Strategy state is only bar deques plus the open direction, so replaying with signals discarded is safe [V `engulfing_strategy_service.py:67-133`].

Risks in the decisions, flagged and not overridden:
- **D1**: US index data may be absent indefinitely. The block is vendor-side [V researcher §0].
- **D8 vs fixed `container_name`**: an overlap needs two containers per service, so the lease becomes the only singleton guarantee. Today's `container_name` and `docker compose up -d` deploy do stop-then-start [V `compose.prod.yml:60`, `10-deploy.sh`]. nginx resolves `app` once at startup [V `web/nginx.conf:26`] and needs a Docker resolver with re-resolve [I].
- **D9**: the paper broker balance is in memory only [V `paper_broker_adapter.py:98`]. Positions can be rebuilt; the balance resets as it does today.

## 7. Recommended direction
A1 + B1 + C-1 + D-1, with one shared deploy routine for all three services: scale to 2, wait for health or standby-ready, stop the old one. The lease decides ownership.

| Phase | Content | Gate |
|---|---|---|
| P0 | Loop-lag probe; skip-listener fix (`scheduled_run_times`); `scheduler.py` docstring; `python:3.14-slim` | none |
| P1 | Delete TradingView and CME (checklist: explore report §1), the three symbols and `01a178ef`; docs updates | owner already decided (D1, D4) |
| P2 | Live-path guards in one process: C1 Mongo read per open, fail closed; H1a; H2/H3 with D10 thresholds and bar timer; M3 seed plus explicit exit flag; B1 caches; `live.signal_latency` | CI tests in §4 |
| P3 | `APP_ROLES` replaces `enable_jobs`; lease (`find_one_and_update`, 30 s TTL, 10 s renew, fail-stop; also checked per open). Lifespan per role: orphan-job sweep in `worker`; orphan-backtest sweep only on runs older than the longest backtest. Fractions; `sync_1m` at second 15; `remote-db.env` = `api` | forced double start refused |
| P4 | Zero-downtime: compose without `container_name` for the three roles; nginx resolver; deploy script overlap; trader shadow/transfer; warm-up from stored bars; paper positions loaded from mirror rows | 10 consecutive paper deploys meet the handover criteria |
| P5 | Re-arm `EXNESS_LIVE_TRADING` | P2-P4 green plus 7 days of §4 metrics; go-live Phase 11 |
| P6 | `EXNESS_US_INDEX` calendar (US DST, close-only minutes treated as closed for entries), `EXNESS_INSTRUMENTS`, `ContractSpec`s, backfill | `getCandleHistory US500` = 200 on the prod account |

**Deleted code**:
- `core/infra/tradingview/*`, `cme_globex_calendar_adapter.py` and its tests, the `tradingview_*` config and enums, `seed_index_futures.py`, the web TradingView branches.
- `enable_jobs`; the in-memory `entries_paused` and the route's dual write.
- The paper-row delete in `load_open_positions` [V `position_app_service.py:36-53`]; the unconditional orphan-backtest sweep; the dead `flush_all_bars` [V `bar_app_service.py:270`].

**Possible simplification [I]**: with one lease-held scheduler, `MemoryJobStore` could replace the Mongo jobstore. The `enqueue_missed_catchups` sweep already covers missed runs [V `sync_jobs.py:760-761`]. Needs a check of misfire behaviour first.

## 8. Unknowns
| # | Question | Blocking? |
|---|---|---|
| 1 | Exness: why are Indices candles and ticks 404 on this account? | Blocks P6 |
| 2 | Exness: are concurrent ticks WS sessions allowed during the shadow phase, and is the per-node limit hit? | Blocks P4; fall back to A2 and accept one refused 1m entry per deploy |
| 3 | `openPosition` RTT from the VPS (no live order measured) | Blocks the P5 latency criterion |
| 4 | Are REST limits counted per key or per account? | No; static split assumed |
| 5 | `EXN-IDEMPOTENCY-KEY` dedup window | No; no order retry, no H1b |
| 6 | Host vs venue clock skew for the timer grace | No; measure in P2 |
| 7 | Paper balance after a handover: reset (today's behaviour) or rebuild from `trades`? | No; default is reset |
| 8 | Do candles print in the close-only minutes? | Blocks the P6 table only |
