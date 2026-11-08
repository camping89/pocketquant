# Brainstorm contract: Exness-only data, `api`/`worker`/`trader` split, zero-downtime trader handover

Labels: **[V]** I checked it in code at the cited line or in a cited report. **[I]** my inference. **[U]** unknown. I worked read-only on `develop` at 453e8e90.

## 1. Outcome
- One host (8 vCPU / 16 GB) runs three containers from one image: `api`, `worker` and `trader`.
  - Each has its own event loop.
  - The worker and the trader each hold a Mongo lease.
  - A trader that does not hold the lease stays in **standby** and never sends an order.
- TradingView, the CME calendar, `ES1!/NQ1!/YM1!:TRADINGVIEW` and subscription `01a178ef` are deleted, with their data (D1, D4).
- Exness is the only live venue and the only source of FX, metals and CFD data. Binance stays data + paper (D3). `US500/USTEC/US30` are added once Exness serves their data.
- A 1m entry reaches Exness within about 2 s of the bar end.
- A deploy restarts every role with no missed bar and no missed order.

## 2. Constraints
- D1-D10 and the `CLAUDE.md` limits, as given in the packet:
  - a flow reads in at most 3 files, with at most 2 hops to I/O;
  - a new class or config key needs a second real caller;
  - dead code is deleted in the same change;
  - "more code than it replaces → ask".
- The `CLAUDE.md` rule "Single uvicorn worker only" must be rewritten to "one lease-holding trader and one lease-holding worker". It must not be silently broken.
- No free-threaded Python, no `--workers N`, no Redis Streams, no shared pacer, no Mongo replica set.

## 3. Non-goals
- A trader per venue.
- A process pool or symbol sharding.
- Deterministic order ids (H1b), until Exness confirms how `EXN-IDEMPOTENCY-KEY` dedups.
- Retrying an order after a 429.
- Moving backtests to the worker.
- Keeping ES history.
- The CME bisect rewrite.

## 4. Acceptance criteria

| Area | Criterion |
|---|---|
| Stalls | `/health` reports `event_loop_lag_max_s` per role. Trader max is under 0.5 s every day, including 00:00, 03:00, 04:00 and 12:00Z. After TV removal, `sync_integrity` p50 is under 10 s and `sync_repair` under 2 min (`job_history`). 0 "Error notifying listener" lines; `skipped_max_instances` rows appear when a run is really dropped. |
| Parallelism | `docker ps` shows `api`, `worker` and `trader`. `db.leases.find()` returns exactly one owner each for `worker` and `trader`. A second `trader` run against prod Mongo for 10 min logs `trader.standby` and sends 0 orders. It makes 0 position or order writes and does not run the paper-row delete or the backtest sweep. A second `worker` starts no scheduler (`scheduler.started` count is 1). |
| TV removal | `rg -i "tradingview\|cme_globex\|pandas_market_calendars\|seed_index_futures"` over `src tests web/src docs pyproject.toml` returns 0 hits. Mongo `tracked_symbols` and `bars` have 0 rows matching `/TRADINGVIEW$/`, and subscription `01a178ef` is gone. All 8 import-linter contracts pass. |
| Indices | First, `getCandleHistory US500 M1` returns 200 on the prod account. Only then: 3 entries in `EXNESS_INSTRUMENTS`, an `EXNESS_US_INDEX` calendar, a backfill, and `sync_integrity` reporting 0 missing bars over 7 days, across the 2026-11-01 DST shift. 0 `MARKET_INSTRUMENT_NOT_FOUND` WS frames. |
| C1 | CI: a pause through the `api` route makes the trader's next open refused. A failed store read also refuses the open (fail closed). The in-memory flag no longer exists. |
| C2 | CI: of two lease contenders only one acquires. A lost renewal stops strategies, refuses opens and exits the process. |
| H1 | CI: a second signal for a subscription is rejected while an `_inflight` open exists for it. |
| H2 / D10 | CI with a fake clock: a 1m bar 11 s late (15m 61 s, 1h 121 s) skips the entry and logs exactly one `strategy.entry_skipped reason=stale`. The paper SL/TP and venue SL paths still run on that bar. |
| H3 / D10 | CI: a bucket that is not the calendar successor of the last one, or a bar with tick silence over the threshold in trading time, logs `reason=gap` and skips the entry. Prod: `strategy.entry_skipped` count reported per week. |
| M1 / 1m latency | CI: with fresh caches the open path makes exactly 1 REST call (`openPosition`). Prod paper: `live.signal_latency` p95 for T0→T5 is 1 s or less on 1m Exness symbols. Before go-live, one live minimum-lot test shows T0→T6 at 2 s or less. |
| M2 | CI: two subscriptions signal on one bar; the opens run one after the other. A close fill marks the loss-cap cache stale, and the next open refreshes it synchronously or refuses. |
| M3 / D9 | CI: after a restart with a LONG mirror row, the strategy's direction is LONG. An opposite entry is **rejected** and does not become a close. hitnrun2 trades on the first live bar after a restart, not 8 h later. |
| Handover (D8) | Over 10 deploys in market hours, every `trader.lease_released` has `inflight=0` and is logged inside [B+0 s, B+30 s] of a 1m boundary B. `handover_gap_ms` (release to the new owner publishing bars) is 2,000 or less. `takeover_ms` is 5,000 or less. 0 `reason=gap` skips on bars that span a handover. A probe hitting `/api/health` every 0.5 s during the deploy sees 0 failures. |
| Rate budget | 0 terminal `exness.rate_limited` on order operations. `exness.rate_limited_retry` per 7 days stays at or below today's 72. |

## 5. Trade-offs (main forks)

**F1. Keeping bars complete across a trader handover**

| Approach | Depends most on | Fails first when | Worst plausible case |
|---|---|---|---|
| **A. Hot standby with tick overlap.** The new trader opens its tick feeds, seeds each in-progress builder once from Redis `bar:current` (the old trader refreshes it every 0.2 s [V `bar_app_service.py:210-236`]), then builds bars from its own ticks. | Exness accepting a second ticks WS session on the account for a few minutes [U]. The limit is 10 connections [V spike `:38`]. | Exness throttles or drops one session. The researcher's probe coincided with all 4 breaker opens of the week [V kongming §0, correlation only]. | Old trader reconnects mid-bar, so the bar is gap-flagged and its entry skipped. That is safe. |
| B. Cold cut. The old trader force-flushes to Redis and exits; the new one seeds from Redis and then subscribes. | Every bar tolerating a 0.5-2 s tick hole. | A fast move during the cut produces a wrong high/low. | Every bar that spans a deploy is gap-flagged, so a 1h strategy loses a whole bar of entries. That conflicts with D8. |
| C. Build higher timeframes from 1m bars and seed from Mongo REST candles. | `sync_1m` staying fresh. | The worker lags or gets 429s, which couples trading to the worker. Kongming §3.4 rejected this coupling. | Takeover stalls, or warms up on stale bars. |

**F2. Meeting the 1m pre-order budget**

Today one entry makes about 3 paced calls with caches warm: snapshot, deals, open [V `exness_broker_adapter.py:222,656-669`, `strategy_app_service.py:332`].

| Approach | Depends most on | Fails first when |
|---|---|---|
| **A. Cache balance and loss cap.** Refresh both off the minute boundary (second 30); mark the loss cap stale on every close event; fall back to a synchronous read when stale; refuse if that read fails. | Every realized loss arriving on the events stream or within one refresh [I]. | A manual close in the Exness app between refreshes. The cap then lags by at most one refresh. |
| B. Give the reads pacer priority. | The pacer spacing. | 3 × 0.6 s or more (fraction 1.0) already exceeds 2 s [V `exness_client.py:116-120`]. |
| C. Prefetch at the bar boundary minus 5 s. | Bar timing. | Session-edge bars, and extra calls on bars with no signal. |

**F2b. When a bar closes**

A bar closes only on the next tick [V `bar_app_service.py:117-132`]. The spike measured a max tick gap of **4.30 s on EURUSD** and 1.90 s on XAUUSD [V spike journal]. Tick-driven close alone can therefore miss 2 s. **A timer close** (bucket end + 0.5 s grace, under the same lock) depends on the host clock agreeing with the venue clock. It fails first if clock skew exceeds the grace; late ticks are already dropped [V reviewer]. Measure it as T2−T1 in `live.signal_latency`.

**F3. Sharing the Exness rate budget**
- **A. Static fractions:** trader 0.6, worker 0.3, api 0.05 [I]. Move `sync_1m` from `second=2` [V `sync_jobs.py:703-708`] to `second=12`, so the worker's minute burst never overlaps the 1m entry window. It depends on 429s being per account, and fails first during the 00:00/03:00/12:00Z bursts.
- B. A per-process API key: depends on per-key limits [U], and fails if limits are per account.
- C. A shared Redis pacer: new infrastructure on the order path (rejected in the packet).

## 6. Better approaches
Each of these beats a packet proposal on evidence. None changes an owner decision.
1. **Timer bar close.** The packet has none. Evidence: EURUSD tick gap of 4.3 s. It also fixes H2's "Friday bar closes on Monday". Cost: about 25 lines in `bar_app_service.py`.
2. **M3: reject opposite-side orders instead of adding `reduce_only`.** No code sends an exit: EXIT/FLAT are rejected [V `risk_check.py:24`], and no caller reaches `closePosition` except the accidental branch [V `exness_broker_adapter.py:205-214`]. A `reduce_only` flag would have no caller. Deleting the branch (plus the close-only paths in `_apply_success`) is net code removal. Exits stay the venue SL/TP. This needs owner confirmation; it is not blocking.
3. **The lease loser waits instead of exiting.** The same code path gives both the C2 guard and the D8 handover, with one lease helper for two callers.
4. **Seed from Redis instead of Mongo.** `_seed_builder_from_mongo` [V `:180-208`] is replaced, not added to. It also serves crash restarts while the Redis TTL is live; a stale seed is gap-flagged.
5. **Do not open the broker in standby.** A second events stream would see the old trader's fills as `unknown_request_fill` and block instruments [V `:506-511`]. The broker connects only after the lease is taken. Fills missed during the gap are recovered by the existing `_close_missing` [V `:464-486`].

## 7. Recommended direction
F1-A, F2-A plus the timer close, and F3-A.

**Handover sequence**
1. The deploy starts the new trader. It sits in standby: tick feeds open, bars built, the last 5 completed bars kept per key, conditions cache warmed. No strategies, broker, sweeps or reconcile.
2. The deploy sends SIGTERM to the old trader.
3. After the next boundary B, the old trader finishes that bar and its orders. It waits until `_inflight` is empty and no snapshot is pending. If that runs past B+30 s, it retries at the next boundary. Then it stops strategies, disconnects the broker and releases the lease.
4. The new trader polls the lease every 0.5 s and acquires it.
5. On takeover it:
   - reloads positions and pending orders;
   - restores paper positions from the mirror rows;
   - builds strategies and warms them by replaying Mongo bars plus its 5-bar tail, discarding signals;
   - seeds each strategy's direction from the mirror;
   - connects the broker and reconciles the snapshot;
   - starts publishing bars.
6. Every order send checks that the lease is still valid with a 5 s margin.

**Phases**

| # | Lands | Gate |
|---|---|---|
| 0 | Loop-lag probe; skip-listener fix (`scheduled_run_times`); C3 docstring; `python:3.14-slim` | none; deploy outside 00/03/04/12Z |
| 1 | **TV removal (D1).** Stop and delete `01a178ef`, delete the 3 symbols through the API (cascade), then deploy the code removal | owner already confirmed |
| 2 | One process: C1 store read; H1; H2 stale guard plus timer close; H3 gap guard; M1 caches; M3 rejection; D9 warm-up plus paper restore; `live.signal_latency` | CI tests from §4 |
| 3 | `APP_ROLES` replaces `enable_jobs`; lease (worker + trader); standby/handover; 3 services; rate fractions; `sync_1m` second=12; `remote-db.env` = `api`; nginx `resolver 127.0.0.11` plus a variable upstream; rolling deploy script; rewrite the `CLAUDE.md` rule and the docs | Phase 2 done (C1 must come before the split) |
| 4 | `EXNESS_US_INDEX` calendar, instruments, specs, backfill, paper subscriptions | Exness returns 200 for US500 candles |
| Live | Switch `EXNESS_LIVE_TRADING` back on | Phases 2-3 done; 14 days of paper meeting §4; live min-lot T0→T6 at 2 s or less; owner answers Q3-Q4 |

**Deleted:**
- TV/CME surface: `core/infra/tradingview/*`, `cme_globex_calendar_adapter.py` and its test, the `pandas_market_calendars` dependency, TV settings and enums, the DI and routing entries, the credential and health checks, `seed_index_futures.py`, the web branches and the doc lines (explore §1).
- Old controls: `enable_jobs`, `Safeguards.entries_paused` with the route's double write, and the boot paper-row delete [V `position_app_service.py:36-53`].
- Bar and order paths: `_seed_builder_from_mongo`, the opposite-side close branch, and `flush_all_bars` [V `:270-289`].
- Wrong docs and comments: the "at-least-once" docstring, and the Vietnamese comments in `compose.prod.yml`.

The plan should report net line counts per phase, because of the `CLAUDE.md` "more code than it replaces → ask" rule.

**Risks flagged, not overridden**
- D6: splitting `api` now carries the C1 cost (kongming would have split it only on evidence). Phase 3 is gated on C1.
- D9 without a store: the paper *balance* still resets on every deploy [V `paper_broker_adapter.py:~99`].
- The bar lock is held across `openPosition`. N live 1m subscriptions on one boundary add up to N × the call's latency [I].
- The memory note "ES paper subscription kept" contradicts D1 and must be updated.

## 8. Unknowns and open questions
1. Exness: enable Indices data on this account. Today every call returns 404 [V researcher]. **Blocking for Phase 4.**
2. Can two ticks WS sessions run at once on one account without disturbing each other? **Blocking for F1-A.** Test on paper deploys first; the fallback is F1-B.
3. Are rate limits counted per key or per account? Not blocking; the default is per account.
4. What is the `EXN-IDEMPOTENCY-KEY` dedup window? Not blocking; there are no order retries.
5. Is a demo Trader API account available, or is a live min-lot test acceptable for the latency gate? **Blocking for go-live.**
6. The `openPosition` round trip has never been measured [U]. **Blocking for go-live.**
7. Do close-only minutes on indices print candles? **Blocking for the index calendar only.**
8. The gap threshold (default 60 s of trading time) and the timer grace (0.5 s): tune from prod. Not blocking.
9. Confirm deleting the close branch (§6.2). Not blocking.
10. With two `api` instances during a rollout, the backtest orphan sweep [V `main_extensions.py:132-141`] would fail the other instance's running backtests. It needs an age or heartbeat rule. Not blocking.
11. A compose rolling start with `--scale` and no `container_name` is unverified [I]. Not blocking.
