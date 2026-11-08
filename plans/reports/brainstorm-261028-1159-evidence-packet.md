---
title: "Evidence packet: parallel runtime, Exness-only data, TradingView removal"
date: 2026-10-28
purpose: immutable input for the ultra brainstorm candidates and verifier
---

# Evidence packet

## Request (owner, verbatim intent)
"Brainstorm this, fix it as well as you can, for a standard implementation." Scope: the event-loop stalls, true parallelism on a stronger machine, and moving all market data to the broker that executes orders (TradingView deprecated, index futures move to Exness CFDs).

## Owner decisions (2026-10-28, binding)
| # | Topic | Decision |
|---|---|---|
| D1 | Index move | **Delete TradingView first.** Remove TradingView, `ES1!/NQ1!/YM1!:TRADINGVIEW` and paper subscription `01a178ef` now; add Exness `US500/USTEC/US30` later once their data works. No US index data in between is accepted. The owner says the Exness app shows the index symbols on the same account, so treat Exness indices as doable. |
| D2 | Live timeframes | **Include 1m.** A 1m entry must reach the venue within about 2 s, so pre-order reads (balance, daily loss cap) must not cost 4-8 s. |
| D3 | Crypto | **Binance stays data + paper only.** Live crypto, if ever, is `BTCUSD` on Exness with Exness data. Exness is the only live venue. |
| D4 | ES history | **Drop it** (symbol delete cascades bars, subscriptions, backtests). |
| D5 | Machine | **8 vCPU / 16 GB, one host**, Docker compose. |
| D6 | Split depth | **Full `api` / `worker` / `trader`** from one image in this delivery. |
| D7 | Deploys | **Zero-downtime.** |
| D8 | Zero-downtime meaning | **No missed bar or order.** `api` and `worker` restart rolling with no gap. A new `trader` starts, warms up from stored bars, takes over the lease at a bar boundary, then the old one exits; a 1-2 s handover gap between bars is allowed. |
| D9 | Strategy state after restart | **Rebuild from stored bars + venue position** (Exness or paper store). No new state store. |
| D10 | Stale bars | **Refuse entries, allow exits.** Skip new entries when a bar is late (1m >10 s, 15m >60 s, 1h >120 s) or has a feed gap inside it; exits and stop-losses always run; one WARNING per skip. |

## Repo rules that bind the design (`CLAUDE.md`)
- KISS; a flow reads in one file, three at most; at most two hops route/job → I/O.
- A new class, port, helper, parameter, flag or config key needs a second real caller today.
- Delete dead code in the same change; never deprecate and keep.
- When a change needs more code than the code it replaces, stop and ask.
- All repositories in `core.infra.persistence.repositories`; fastapi only in `app`; UUIDv7 keys; English only; docs AS-IS, under 800 lines.
- "Single uvicorn worker only — scheduler/WS feed/broker are in-process singletons" (this rule changes with D6 and must be rewritten, not silently broken).
- Every `await` is a preemption point; no `await` inside atomic blocks.
- Branch model: work on `develop`; `master` = prod, every master push deploys (fast-forward `develop:master`).

## Current state (facts with sources)
- Stalls (prod `job_history`, 7 days): `sync_repair` at 00:00/12:00 UTC p50 1,609 s (max 2,947 s); `sync_integrity` at 04:00 p50 419 s; `sync_1m` p50 9.3 s. Root cause: `cme_globex_calendar_adapter.py` runs pandas `iterrows()` per `bar_start` call (~91k calls per CME symbol per pass), on the single event loop. Sources: `debug-261023-0045-daily-0400-integrity-event-loop-stall.md`, `kongming-261028-0848-event-loop-concurrency-review.md`, `kongming-261028-1020-parallel-exness-only-reanalysis.md`.
- The CME calendar is used only by the TradingView index symbols; the Exness and 24/7 calendars are pure arithmetic (`exness_session_calendar_adapter.py`, no pandas). After TV removal no batch job is CPU-bound (kongming-1020 §1). Source of TV surface: `explore-261028-0915-tradingview-removal-impact.md`.
- Skip-listener bug (verified): `scheduler.py:99` reads `event.scheduled_run_time`; APScheduler 3.11.2 `JobSubmissionEvent` has `scheduled_run_times`; 72 "Error notifying listener" lines in 7 days of prod logs.
- `scheduler.py` docstring claims a shared Mongo job store coordinates several processes; the APScheduler 3.x FAQ says that is unsupported (duplicate/missed runs).
- Prod image `python:3.14-rc-slim` (3.14.0rc3, GIL on). `uv.lock` has no `cp314t` wheel for `httptools`.
- Exness: one shared `ExnessClient` with a `_RequestPacer` (strictest rate × 1.2; orders jump the queue in-process; a 429 on an order is not retried). REST and WS strike budgets are per account (assumed; unconfirmed per-key vs per-account). Steady-state use under 10% of 100 calls/min. Pre-order path makes several sequential calls: 4-8 s entry latency floor (kongming-1020 §3).
- Exness indices: `US500`, `USTEC`, `US30` (+ `_x100`/`_x10`) exist in `instruments()`; on the API today every Indices/Stocks candle and tick call returns `404 MARKET_INSTRUMENT_NOT_FOUND`; `trade_mode: trading_disabled` for all 15 Indices and 102 Stocks. Sessions follow US DST; daily break 21:00-22:00Z now; none of the existing Exness session tables match; 1000 candles per call; spec says M1 ~1 year. CFD vs futures: carry basis, swaps, dividend adjustments, bid candles, tick-count volume, 1 USD/point. Source: `researcher-261028-0920-exness-index-cfd-equivalents.md`.
- Live-path safety (source `code-reviewer-261028-0915-live-path-parallel-safety.md`):
  - C1 entries-pause is an in-memory object loaded once (`di/adapters.py:58`, `exness_safeguards.py:10-17`, `routes/safeguards.py:43-49`).
  - C2 nothing prevents a second trading copy: strategy loading and quote feed start even with jobs off (`main.py:472-475`); order keys are random; startup cleanup deletes paper rows and fails running backtests.
  - C3 wrong scheduler docstring.
  - H1 second entry possible while the first fills (`_held_for` only sees filled positions).
  - H2 no stale-bar guard; a bar closes only on the next tick.
  - H3 a feed drop publishes a partial bar as complete and never sends missing bars (at-most-once).
  - M1 pre-order calls share the rate queue with candle sync; M2 removing the global bar lock lets two opens pass the daily loss cap; M3 after restart a strategy forgets its position and an opposite signal closes it.
  - Existing guards: venue stop-loss on every open, opens blocked until reconcile, unknown fills block an instrument, daily loss cap from venue deals, one position per subscription, one feed per symbol.
- Topology proposal (source `brainstormer-261028-0915-parallel-process-topology.md`): three services `api` (HTTP, SSE, backtests), `worker` (scheduler + batch jobs, exactly one), `trader` (feeds, bar building, strategies, brokers, reconcile; one per account); communication via Mongo (desired-state + 5 s reconcile loop, `strategy_command_service.py:21-25`, `config.py:141`) and Redis (UI streams); Redis has no pub/sub/streams today; Mongo has no replica set (no change streams); `APP_ROLES` replacing `enable_jobs`; Mongo lease (~40 lines) for worker and trader; `exness_rate_fraction` per process (`config.py:116-118`); free-threaded 3.14t rejected.
- Live trading state: Exness live disarmed 2026-10-22 (`EXNESS_LIVE_TRADING=false`); go-live Phase 11 called off (no profitable strategy yet). Everything is paper today. Open plans: `plans/261019-1957-exness-go-live/` (phases 11-12 pending), `plans/261023-0056-exness-us-dst-session-shift/` (check on 2026-11-02).
- US DST ends 2026-11-01; Exness sessions shift +1 h in UTC.

## Reports to read (all in `plans/reports/`)
`debug-261023-0045-daily-0400-integrity-event-loop-stall.md`, `kongming-261028-0848-event-loop-concurrency-review.md`, `brainstormer-261028-0915-parallel-process-topology.md`, `explore-261028-0915-tradingview-removal-impact.md`, `code-reviewer-261028-0915-live-path-parallel-safety.md`, `researcher-261028-0920-exness-index-cfd-equivalents.md`, `kongming-261028-1020-parallel-exness-only-reanalysis.md`.

## Rubric (verifier scores each 1-20)
1. **Faithfulness**: honours every owner decision D1-D10 and the repo rules; no silent reversal of a decision (a concern about a decision must be raised as a flagged risk, not overridden).
2. **Evidence grounding**: claims cite files/reports; feasibility checked against code, not assumed.
3. **Acceptance criteria sharpness**: observable, measurable, testable in prod and CI (numbers, log events, queries).
4. **Money-path safety**: C1, C2, H1, H2, H3, M1-M3, lease handover without double ownership or missed bar/order, 1m latency budget.
5. **Simplicity**: smallest design meeting D1-D10 within `CLAUDE.md` limits; no invented infrastructure.
6. **Honesty about unknowns**: Exness 404 on indices, per-key vs per-account limits, idempotency window, WS connection limits during trader handover, Exness behaviour on two concurrent sessions.
7. **Conditional fields**: Trade-offs with load-bearing assumption and first-failure condition per approach; Better approaches present with evidence or "none — <evidence>".
Hard constraints: must not propose free-threaded Python or multiple uvicorn workers for trading state without new evidence; must not keep TradingView (D1); must not lose the entries-pause semantics; must not allow two traders to send orders for one account at the same time.
