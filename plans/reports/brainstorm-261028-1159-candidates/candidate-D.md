# Candidate D

# Brainstorm contract: parallel runtime, Exness as the only data source, TradingView removed

Labels: **[F]** means I checked it in code at the cited line or it comes from a cited report. **[I]** means it is my inference. **[U]** means it is unknown.

## 1. Outcome
- One 8 vCPU host runs three services from one image: `api`, `worker` and `trader` (D5, D6).
- Exness is the only live venue. Binance stays data and paper only (D3).
- TradingView, the CME calendar, `ES1!/NQ1!/YM1!` and subscription `01a178ef` are gone (D1, D4).
- `US500/USTEC/US30` are onboarded once Exness returns data for them.
- A deploy does not miss any bar or order. The trader hands over between bar closes (D8).
- After a restart, strategies rebuild from stored bars and the venue or paper position (D9).
- Stale or gapped bars do not get new entries, but exits always run (D10).
- A 1m entry reaches the venue in about 2 s or less (D2).

## 2. Constraints
- D1-D10 and `CLAUDE.md`: KISS, at most 3 files per flow and 2 hops, a second real caller for anything new, delete dead code, all repos in core.
- Never two schedulers [F: APScheduler FAQ, reviewer C3].
- Never two order senders on one account.
- Python with the GIL. One uvicorn worker per service.
- Mongo has no replica set and Redis has no pub/sub [F: brainstormer §2].
- One Exness account budget. Orders are never retried on a 429 [F: `exness_client.py:305-307`].

## 3. Non-goals
- Free-threaded Python, a process pool, sharded workers, Redis Streams, a shared Redis pacer.
- More than one trader.
- A CME bisect rewrite (it is deleted with TV).
- H1b deterministic ids until Exness confirms the idempotency window.
- Live crypto.
- Back-adjusting the ES history.

## 4. Acceptance criteria

| Area | Check (pass condition) |
|---|---|
| Stalls | Trader `loop.lag_max_s` stays under 1 s every day for 7 days, including 00/03/04/12Z. In `job_history` over 7 days: `sync_1m` has 60 rows per hour, `sync_repair` p95 under 120 s, `sync_integrity` p95 under 10 s. Zero "Error notifying listener" lines. Zero `exness_ws.reconnecting` in the 00h and 12h hours. |
| Parallelism | `docker ps` shows `api`, `worker` and `trader`. `db.leases` has exactly one `owner` for `worker` and one for `trader`. A forced second `worker` logs `lease.held_elsewhere` and starts no scheduler. A second `trader` stays standby and logs no `exness.broker_connected`. A CI lease test covers acquire, renew, expiry and transfer. |
| TV removal | `rg -i "tradingview\|cme_globex"` over `src web/src tests docs` returns 0 hits. `pandas_market_calendars` is not in `uv.lock`. `db.tracked_symbols.countDocuments({symbol:/TRADINGVIEW$/})==0`, with bars, backtests and `01a178ef` also 0. import-linter (8 contracts) and the full suite are green. |
| Indices (gated) | `getCandleHistory` returns 200 for all 3 symbols on the prod account before they are mapped. The `EXNESS_US_INDEX` calendar has unit tests on both sides of the 2026-11-01 DST shift. Zero `code 4000` subscribe frames. Integrity finds 0 missing over 7 days. |
| C1 | CI: a pause through the route on `api` blocks the next Exness open in `trader`. A failed Mongo read rejects the open. The in-memory flag is deleted. |
| C2 | A remote-DB dev session (role `api`) deletes no positions and fails no backtests. Only the lease owner logs `strategy_started` or `exness.broker_connected`. |
| H1 | CI: a second signal for a subscription with a pending order is refused, and `strategy.entry_refused reason=inflight` is logged once. |
| H2, D10 | CI: a 1m bar 11 s old (15m: 61 s, 1h: 121 s) skips the entry and logs exactly one WARNING `strategy.bar_stale_skipped age_s=`. The paper SL/TP and close orders on that bar still run. |
| H3 | CI: a feed reconnect inside a bucket sets `gap=True` on the bar and the entry is skipped. A bar that is not the next one after the previous bar logs `strategy.bar_gap_skipped`. |
| M1 | CI: with warm caches the open path makes exactly one REST call, `openPosition`, counted on a client fake. |
| M2 | The global bar lock is kept. A test shows that two opens on one bar run the loss-cap check-then-send one after the other. |
| M3 | CI: after a restart with an open position, the strategy's open direction is seeded. An opposite entry is rejected, not turned into a close. Closes need `reduce_only`. |
| Latency | `live.signal_latency` p95 from T0 to T6 is 2.0 s or less for 1m over at least 50 signals. On paper, T0 to T5 p95 is 0.5 s or less. T5 to T6 is measured on the owner-approved canary or demo account. |
| Handover | 10 deploy drills in market hours with 1m paper subscriptions running. Each drill: zero `strategy.bar_gap_skipped`, `trader.handover_done gap_ms` of 2000 or less, the lease changes owner exactly once, the old and new `trader.active` windows never overlap, the open paper position count is the same before and after, and no `exness.unknown_request_fill`. |

## 5. Trade-offs

**F1: how the trader hands over.**

| Approach | Load-bearing assumption | First failure | Worst case |
|---|---|---|---|
| **(a) Standby with overlapping feed** (recommended). The new trader opens a ticks WS but starts no strategies and no broker. It sets `handover_to` on the lease. The old trader waits for a safe point: second 20-50 of a minute with no pending orders. It then stops, transfers the lease with a compare-and-set, and exits 0. The new trader connects the events WS (the existing snapshot gate blocks opens until reconciled [F: `exness_broker_adapter.py:256-262`]), replays history and seeds the in-progress bars. | Exness accepts a second ticks WS for about 2 min. The spike says up to 10 WS per account [F: kongming-1020 §3.3]. | Exness drops one of the two sessions, or strikes it. | The old trader keeps the lease and the deploy aborts. No order is lost. |
| (b) Stop, then start at second :15 of a minute (cold restart) | Boot plus warm-up takes under 40 s | Slow boot | The first bar after the restart is partial. It is flagged as a gap and its entry is refused, which breaks D8. |
| (c) Pass the in-progress bars through Redis `bar:current` | That snapshot is current. It is written every 0.2 s [F: `bar_app_service.py:25`]. | Ticks between the last flush and the takeover are lost | A silently incomplete bar, the case D10 forbids |

**F2: how 1m reaches the venue in about 2 s.**

| Approach | Assumption | Fails first | Worst case |
|---|---|---|---|
| **(a) Cache balance and today's realized P&L.** Refresh them after each fill or close event, every 30 s, and at UTC midnight. Do a blocking fetch if the cache is older than 120 s. Close the bar on a timer at bar end + 0.5 s. | The loss cap counts realized P&L only. Verified: it sums deals [F: `:277-288`]. | The events WS is down. The cache then goes past its age limit and the path falls back to today's slow fetch. | 4-8 s in rare cases, but still fail-safe. |
| (b) Give the pre-order reads priority | The pacer serializes calls | Always | 4 calls at about 1 s spacing is 4 s or more [F: `exness_client.py:171`]. |
| (c) Run the pre-order reads with `gather` | Same | Always | Same |

**F3: how the three services share the Exness budget.**

| Approach | Assumption | Fails first | Worst case |
|---|---|---|---|
| **(a) Static `EXNESS_RATE_FRACTION`**: trader 0.6, worker 0.25, api 0.1 (the setting exists [F: `config.py:118`]) | The cluster throttles at about 95% of the published rate | 429s below the published rate [F: kongming-1020 §3.1] | An `openPosition` 429 rejects one entry. The venue SL is unaffected. |
| (b) A separate API key for the worker | Limits are counted per key [U] | They are per account | Same as (a), plus key handling |
| (c) A Redis token bucket with priority | Redis is up | Redis goes down | No trading at all |

**F4: how bars stay complete across a feed drop.**
- **(a) Recommended:** a gap flag, a check that each bar follows the previous one, and seeding from Mongo 1m bars.
- (b) Fetch the REST candle at each bar close. It fails on budget: `getCandleHistory` is limited to 2 per second [F]. Six symbols closing on one boundary take about 6 s or more.
- (c) The trader reads bars from Mongo. That couples it to the worker's lag [F: kongming-1020 §3.4].

## 6. Better approaches
None. The recommended direction is the one requested.
- The cheaper handover (F1b) breaks D8.
- REST-built bars (F4b) break D2 on the per-method rate limit.
- A second key (F3b) depends on [U].

Risks I see in the owner decisions (flagged, not overridden):
- **D1:** index data may never be enabled. It returns 404 today [F: researcher §0].
- **D8:** the overlapping WS is unverified.
- **D9:** paper balance resets to 10,000 today [F: `paper_broker_adapter.py:88-98`]. "Rebuild from store" needs a rule for that.

## 7. Recommended direction

**What the design does:**
- **Roles and lease.** `APP_ROLES` replaces `enable_jobs`. One Mongo lease module (`find_one_and_update`, 30 s TTL, 10 s renew, compare-and-set transfer) is used by `worker` and `trader`. Losing a renewal stops the process.
- **Fencing on opens.** Before each open, the trader checks two things together: that it still owns the lease, and the C1 pause flag from Mongo.
- **Warm-up (D9).**
  - Each strategy declares `warmup_bars`; both existing strategies have lookbacks [F].
  - `start_strategy` replays that many Mongo bars and throws away their signals.
  - It then seeds the open direction from `PositionAppService.get`.
  - Paper subscriptions reload their positions from the mirror rows, which carry `sl_price`/`tp_price` [F: `position/entities.py:40-41`]. Today those rows are deleted at boot.
- **Seeding the in-progress bars.** At takeover, each in-progress bucket is built from the Mongo 1m bars for [bucket start, current minute) plus the trader's own current 1m builder.
  - This is complete only if the Mongo bars are up to date. `sync_1m` runs at second :02 [F: `sync_jobs.py:704-708`]. The handover checks that the latest stored bar is the previous bucket and otherwise defers to the next minute.
  - The same code covers a cold start, where the partial first bars are flagged as gaps.
  - It replaces `_seed_builder_from_mongo` [F: `bar_app_service.py:180-208`].
- **Rolling deploys.**
  - `api`: run 2 instances, wait for health, remove the old one. nginx needs `resolver 127.0.0.11` because today it has a static `proxy_pass http://app` [F: `web/nginx.conf:26`].
  - The backtest orphan sweep becomes age-based. Today it fails every `started` run [F: `main_extensions.py:132-141`].
  - `worker`: the new one waits for the lease and the old one releases it on SIGTERM. Misfire grace plus the 100-bar fetch cover the gap [F: `sync_jobs.py:698`].
  - `trader`: scaled to 2 during the deploy and set to `restart: on-failure`. `10-deploy.sh` stops running a plain `up -d` for these three services [F: `10-deploy.sh` today].

**Phases:**
1. **TV removal (D1 first).** Delete the whole surface listed in explore §1 and delete the three symbols, which cascades their data. Also: the skip-listener fix, the scheduler docstring, the loop-lag probe, and the base image `python:3.14-slim`.
2. **Live-path guards, still one process.**
   - C1, H1 (pending order per subscription, checked in `StrategyAppService`), M3 with `reduce_only`, warm-up and paper reload.
   - D10: timer close, gap flag, stale and next-bar checks.
   - M1: the caches.
   - The `live.signal_latency` log line.
3. **Split into three services.** Roles, lease, rate fractions, role-aware sweeps, and the remote-DB profile set to `api` only. Rewrite the `CLAUDE.md` "single uvicorn worker" rule.
4. **Zero-downtime deploy.** The handover protocol, the deploy script and nginx changes, then the 10 drills.
5. **Indices (gated on Exness data).** The `EXNESS_US_INDEX` calendar, mappings, `ContractSpec`s and backfill.
- **Before Exness live is switched back on:** phases 2-4 green for 7 days, the latency criterion met, and the owner's canary approved.

**Deleted code:**
- The TradingView package, the CME adapter and its dependency, `scripts/seed_index_futures.py`, and the web TV branches.
- `enable_jobs`, the in-memory `entries_paused` and the route's dual write.
- `_seed_builder_from_mongo`, `flush_all_bars`, and the paper-row delete in `load_open_positions` [F: `position_app_service.py:36-53`].

**Size check:** across the whole change, deletions outweigh additions because of the TV removal [I]. Phase 4 on its own adds about 150 lines net [I]. Under the `CLAUDE.md` rule, this contract is where that is raised for approval.

## 8. Open questions
1. Exness Indices data returns 404 [F]. **Blocking** for phase 5.
2. Does Exness accept two concurrent ticks WS sessions per account? **Blocking** for the phase 4 drills. Test it while live trading is still off.
3. Are rate limits per key or per account? What is the `EXN-IDEMPOTENCY-KEY` window? Not blocking.
4. What account do we measure live T5 to T6 on: a demo account or a minimum-lot canary? **Blocking** before switching 1m live on.
5. How should paper balance be rebuilt after a restart (initial balance plus realized trades)? Not blocking.
6. Do the indices' close-only minutes count as open? Blocking only for the index calendar.
7. Does the events WS push account state without a REST call [U]? Not blocking, since F2a works without it.
