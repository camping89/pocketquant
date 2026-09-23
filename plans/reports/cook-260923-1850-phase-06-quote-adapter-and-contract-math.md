# Phase 6 completion — Polling Quote Adapter and Contract-Aware Trading Math

Plan: `plans/260921-1436-asset-class-index-futures/`
Phase file: `phase-06-quote-adapter-and-contract-math.md`
Date: 2026-09-23
Status: tasks 1-8 complete and deployed (runs `35856304174` and `35857069557`). G3 is
verified on production data. G2's live full-session round trip is open; see "What is
not done".

## Outcome

Index futures now trade in contracts and dollars. A 0.25-point ES move on 2 contracts
realizes 25.00 USD. Sizing floors to whole contracts, commission can be charged per
contract, and each symbol's `ContractSpec` reaches sizing, the fill broker, the persisted
position mirror the UI reads, and backtest dispatch. ES, NQ and YM now have a realtime
feed. `TradingViewQuoteAdapter` polls the newest 1m bar every 60 s while CME is open,
and requests nothing while it is closed. Crypto behaviour is unchanged. Every linear-spec
path was checked byte-for-byte by the pre-existing suite and by an independent review.

## Measured

| Check | Result |
|-------|--------|
| `uv run pytest tests/ -q` | `865 passed, 1 skipped` |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 10 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| CI (UTC, Asia/Ho_Chi_Minh, America/Chicago) | all green, deployed |
| Mutation runs | 43 guards, every one killed |

**G3, production data.** An `engulfing` 1h backtest on `ES1!:CME_MINI` from 2025-11-17
to 2026-09-23 (run `01a0ce20-2ce0-744b-b4a6-eec0641b861d`, 10 M capital, zero
commission and slippage) closed 132 trades. Every trade was a whole number of
contracts, and every PnL equalled `(exit - entry) x 50 x contracts` to the cent (0
mismatches). The reported Sharpe of 0.527017 matches a recomputation from the stored
equity curve at 5910 periods a year to 12 digits. At 8760 it would be 0.641627, so
annualization runs on the CME session calendar. The plan's "roughly 5796" predates
Correction 24, which pinned 5910.

**Realtime, production.** After the deploy, reconcile added 6 subscriptions (3 crypto,
3 futures). Phase 5's once-per-symbol `subscribe_failed` warnings are gone. Latest quotes
for all three futures are served, stamped about 12 minutes behind on the free feed. The
live ES 1d bar opens at 22:00 UTC and the 4h bar at 10:00 UTC, on the session grid. No
WARNING or ERROR lines were logged in the 15 minutes observed.

## Decisions and corrections

These are recorded in `plan.md`, Session 9, as Corrections 27-33:

- **Task 5 ran its Failure Protocol.** The adopted design, on kongming's counsel, puts
  the spec on `StrategyConfig` and `BacktestConfig`, resolved where configs are built.
  The live broker pool is keyed by `(broker_type, contract_spec)`. Each futures spec
  gets its own paper account, while crypto still shares one.
- **The UI's position mirror needed the multiplier.** The plan did not list it.
- **Quote adapter changes.**
  - `is_connected()` follows poll health, not `is_authenticated()`, because production
    is anonymous.
  - Volume deltas are measured against the last emission, not the last poll.
  - A new minute is always emitted.
- **Realtime futures bars now use the session grid.** Buckets come from the symbol's
  calendar, and a bar closes when a tick lands in a later bucket. A DST week is an
  hour short.
- **The review before deploy found real defects.**
  - A cancelled fetch left its scraper instance shared, a history-corruption hazard.
  - The broker pool outlived its strategies.
- **Found in production after deploy.** The latest-quote TTL (60 s) equalled the poll
  interval, so futures quotes returned 404 between polls. The TTL now spans three
  polls, which is Task 8 step 2's own rule applied to the threshold that exists.

## What is not done

- **G2 (Task 9 step 1).** A paper ES strategy has not run a full CME session.
  - With `paper_initial_balance = 10_000` and the default 10% exposure cap, sizing
    yields zero contracts: one ES contract is about 390,000 USD of notional.
  - Correctly so, because a 10,000 account cannot margin an ES contract.
  - A live G2 needs a larger paper balance, a futures risk config, or a margin-based
    cap, and that choice is a risk-policy decision.
  - The arithmetic G2 checks is covered end to end in tests: broker round trips, the
    `_process_signal` sizing path, and the position mirror.
- **Seeded specs carry no `commission_per_contract`.** Futures therefore pay
  `commission_bps` on price-unit notional (3 bps of 7800 is 2.34 USD per contract).
- **`ContractSpec.tick_size` is not applied to fills.** SL/TP exits land off-grid, for
  example `7799.00825`. This predates the phase and is visible in the G3 trades.
- **`integrity_jobs` still uses `get_bar_start` for its scan window end.**

## Unresolved questions

1. What paper balance and risk config should a live ES subscription run with, and
   should futures exposure be capped on margin rather than notional? G2 depends on it.
2. Should the seed carry a per-contract commission, for example 2.25 USD, so futures
   use the model this phase added?
