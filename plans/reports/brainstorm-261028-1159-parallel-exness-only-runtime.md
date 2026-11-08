---
title: "Brainstorm: parallel runtime, Exness-only data, TradingView removal"
date: 2026-10-28
mode: ultra (best-of-5, kongming verifier) + advice
evidence: plans/reports/brainstorm-261028-1159-evidence-packet.md (owner decisions D1-D10)
status: accepted contract (winner materialized unchanged); plan not yet written
---

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


---

## Appendix: ultra ranking

Five independent candidates (Opus tier) received the same evidence packet. They were scored by kongming (strongest tier) on 7 criteria, 1-20 each. All five passed the hard constraints.

| Rank | Candidate | Total | Note |
|---|---|---|---|
| 1 | A (this contract) | 124 | No wrong citation found; applies the "second caller today" rule (no uncalled `reduce_only`); sharpest acceptance set |
| 2 | B | 118 | Best money-path score (18); loose 0.86 s spacing figure; `db.symbols` query unverified |
| 3 | E | 118 | Fully grounded; no per-order lease fence stated |
| 4 | C | 115 | Ambiguous exit test on the money path; a few wrong line numbers |
| 5 | D | 113 | Handover mid-bar rather than at a boundary; shortest unknown list |

Margin is low: A leads by 6 in total but by at most 3 on any one criterion, and B beats it on money-path safety.

## Appendix: verifier corrections the plan must apply

These are facts the verifier checked. They do not rewrite the contract above; the plan built from it must include them.

1. Set `stop_grace_period` (about 120 s) and state the lease TTL and renew interval (30 s / 10 s). The compose default of 10 s would SIGKILL the old trader in the middle of its drain.
2. Build and warm up strategies in standby, before takeover; that is what D8 asks for. Takeover then only connects the broker, reconciles and seeds the direction. hitnrun2 needs 481 1m bars (`hitnrun2_strategy_service.py:35-37,61`).
3. Define the Redis-seed gap case. The seed can be up to 0.2 s stale (`bar_app_service.py:225-228`) or missing after a close (`:164-170`). Gap-flag a builder that starts mid-bucket without a covering seed, using `last_update` (`:234`).
4. Record an owner decision on deleting the Exness `closePosition` branch. Once it is gone, only the venue SL/TP closes a live position.
5. The synchronous loss-cap fallback costs about 2 s on the first entry after any close. Say so in the plan; tighten the refresh if 1m entries cluster.
6. Fix the orphan backtest sweep for two `api` replicas in Phase 3, using an age or heartbeat rule (`main_extensions.py:132-141`).
7. The pause route must return an error when the store write fails (`routes/safeguards.py:46-48`).
8. Move `web`'s `depends_on` (`compose.prod.yml:12-14`) and the nginx upstream (`web/nginx.conf:26`) from `app` to `api`.
9. The 429 baseline is about 25 a week, not 72; 47 of the 72 came from the probe window. Use about 25 as the gate.
10. Run the "second trader against prod for 10 min" test as the two-WS experiment (open question 2) in an owner-approved window, not as a routine check.
11. Update the auto-memory note "ES paper subscription kept" when Phase 1 lands.
12. Correction to the evidence packet: `main.py:472-475` does not exist. The quote feed starts at `main.py:65` and the sweeps are in `main_extensions.py:132-172`.

ultra: picked=A/5 margin=low unanimous=no rejected_all=no

## Appendix: owner decisions after verification (2026-10-28)

| # | Topic | Decision |
|---|---|---|
| D11 | Exness close path | Delete the unused `closePosition` branch. Live Exness positions close only by venue SL/TP (resolves verifier item 4 and open question 9). |
| D12 | 1m latency proof before re-arming live | A live minimum-lot canary on the real account: smallest lot, tight SL, first 20 entries, T0→T6 p95 ≤ 2 s. |
| D13 | Paper balance after a handover | Rebuild it at takeover from the initial balance plus realized P&L in stored trades. |
| D14 | If Exness refuses two tick sessions on one account | Ask Exness for a second API key or account for the standby feed. Open: this works only if limits are per key (unknown); if Exness refuses, the owner must choose another fallback. |
| D15 | Two tick sessions (F1-A) | Spike it first, before the handover code. The owner will provide a second Exness API key for the spike. Test two sessions on one key first, then the second key if the first is refused. The plan picks F1-A or a fallback from the spike result. |
| D16 | `CLAUDE.md` "more code than it replaces → stop and ask" | Replace it with a plain KISS rule. Net line counts per phase are no longer a stop gate. |
| D17 | Two-trader / two-WS probe window | Run it whenever needed. `EXNESS_LIVE_TRADING` is off, so no real trade is at risk (supersedes verifier item 10). |
| D18 | Orphan backtest sweep with two `api` replicas | Heartbeat: running backtests refresh a timestamp, and the sweep fails only rows with a stale heartbeat (resolves verifier item 6 and open question 10). |
| D19 | 429 gate | Keep 72 terminal-free `exness.rate_limited_retry` per 7 days as the gate (overrides verifier item 9's ~25). |
| D20 | Gap threshold and timer grace | 60 s of trading time and 0.5 s, tuned later from prod. Check VPS NTP sync before enabling the timer close. |
| D21 | Live 1m subscriptions | More than 2 are expected. The plan must not hold the bar lock across `openPosition`; opens on one boundary must not add up to N × call latency (supersedes the "lock held across `openPosition`" risk). |
| D22 | Exness-only questions (Indices data, per-key vs per-account limits, `EXN-IDEMPOTENCY-KEY` window, close-only candles) | No ticket. Answer them from public docs and web research first; whatever stays unknown is settled by the D15 spike or a direct API probe. |

## Appendix: answers to the Exness-only questions from public docs (2026-10-28, per D22)

Sources: the public OpenAPI spec `https://www.exness-api.com/exness_api.yaml` (downloaded and read), the Help Center article "Exness API" (`https://get.exness.help/hc/en-us/articles/27866287512476-Exness-API`, seen only through a search-engine summary; a direct fetch was reset by the server), and the "Instrument trading hours" article.

1. **Indices data (open question 1).** Search-summary claim [not fetched directly]: the Help Center says the current API version does not support stock and index instruments. This agrees with the researcher's verified result (`researcher-261028-0920-exness-index-cfd-equivalents.md:13-14`): all 15 Indices and 102 Stocks are `trading_disabled` and return 404 on candles and ticks. Inference: Phase 4 is blocked by Exness API scope, not by an account setting, and enabling something on the account will not unblock it. The owner must confirm this with Exness or decide how to proceed.
2. **Per key or per account (open question 3).** The spec says per account. `getLimits` "returns the effective REST and WebSocket limits for the account". REST uses `global_account_rate` (measured at 10 per 1 s) "across the AP cluster". WebSocket limits are "enforced per account, per server node", with `max_active_connections` (measured at 10). Inference: a second API key on the same account adds no REST or WebSocket budget. Two tick sessions use 2 of the 10 connections, so the D15 spike needs only one key. It tests whether a second session disturbs the first, which the spec does not address. Only a second *account* would bring its own budget.
3. **`EXN-IDEMPOTENCY-KEY` window (open question 4).** The spec says only that records "are retained for a limited time"; no number is published. A reused key with the same payload returns the original `operation_id`, and a reused key with a different payload is rejected. It stays non-blocking, because the plan does not retry orders.
4. **Close-only candles (open question 7).** Not published. The trading-hours article separates close-only, quote-only and closed modes. It is my inference that quotes, and therefore candles, continue in close-only mode. This is moot until item 1 is resolved.

## Appendix: owner decisions after the Exness research (2026-10-28)

| # | Topic | Decision |
|---|---|---|
| D23 | US indices | Keep D1: delete TradingView as planned. Drop Phase 4 from this delivery; US index data is absent until the Exness API supports indices. The `Indices` acceptance row in §4 and open questions 1 and 7 leave this plan. |
| D24 | D15 spike shape | One API key: two ticks sessions on the same key and account, measuring whether the second session drops or delays the first. If it interferes, the fallback is a second Exness account, not a second key (supersedes D14 and the second-key part of D15). |
