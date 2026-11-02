# System Architecture

This file holds the decisions, cross-process rules and limits that no single source file states. The code owns everything else. For run and test steps, see the [README](../README.md).

## Decisions

- **Roles run under Mongo leases.** `APP_ROLES` (`core/config.py`) picks the roles a process runs. The worker runs the scheduler and jobs. The trader runs the quote feed, strategies, brokers and the reconcile loop. Each acts only while it holds its lease (`app/roles.py`). A second copy waits warm in standby and takes over when the holder releases or loses the lease. The goal is a trader handover with no trading gap. Rejected: roles bound to a process with no lease, where a second copy duplicates the scheduler, the feed and the broker connection. Prod runs each role as its own service from one image (`deploy/compose.prod.yml`). A deploy rolls them one at a time: the new copy starts in standby, then the old copy stops and releases its lease (`deploy/vps/10-deploy.sh`). The old trader releases at a bar boundary with no order in flight (`app/roles.py::drain_trader`).
- **There is no deploy window.** A deploy may cut a heavy sync job. The cut run is recorded as interrupted, and the next worker resumes it, skipping the symbols the cut run finished (`sync_jobs.py::_tracked`, `enqueue_missed_catchups`). Rejected: holding deploys until heavy jobs finish, which ties every release to the job schedule.
- **Leases use wall-clock time.** Every role must run on one host clock.
- **Strategies are declarative.** Routes write a subscription's `desired_state` to Mongo and return. The trader's reconcile loop (`StrategyReconcileAppService`) converges its engine to Mongo. The api process never calls `StrategyAppService`.
- **Higher-timeframe context comes from stored bars.** On each closed entry bar the engine gives the strategy the higher-interval bars from Mongo that closed by the entry bar's start, through one cache per symbol and interval (`StrategyAppService._context_at`). Live, warm-up and backtest use the same rule (`docs/governance/no-look-ahead-rules.md`). Rejected: bars built from live ticks in the trader, which a backtest cannot replay. Limit: if `sync_1m` stores a bucket's final value only after the first entry bar of the next bucket has closed (a worker handover or a slow vendor call), the engine serves that partial bucket until the next rollover; the data-lag monitor is the only signal.
- **A symbol's suffix names its data provider.** The execution broker is a separate setting on each subscription. There is no fallback provider, because the same code on another provider is a different instrument.
- **A position exits at its SL or TP, or on a strategy EXIT.** EXIT means go flat: the engine cancels the subscription's pending stop, then closes the whole position through `IBrokerPort.close_position`, even when the cancel fails. A close of a position that is already closed does nothing; it never opens or reverses one. An EXIT is never skipped as stale or gapped. The risk check accepts EXIT only with an open position and rejects FLAT, any opposite entry and any stop entry against an open position. An Exness position also closes at a broker stop-out. Unloading a subscription leaves a venue position open under its own SL/TP. Rejected: an opposite market order as the close, which opens a position when an SL fill lands first.
- **Real money is opt-in.** While `EXNESS_LIVE_TRADING` is false, `BrokerFactory` refuses to build the Exness broker and `ExnessClient` refuses every call that opens exposure (`openPosition`, `placePendingOrder`). A close and a pending cancel are never fenced: they only reduce exposure. Each check stands on its own.
- **Only the trader's live flag counts.** Compose pins `EXNESS_LIVE_TRADING` off for api and worker, so the trader writes its own flag to the safeguards store at takeover. The Exness strip and the exness subscription create read it there. No order path reads the stored flag. Rejected: passing the flag to the api under a second env var, which reports the env file instead of the running trader.
- **The paper broker uses margin accounting, not spot.** An open does not debit the notional. Equity is the balance plus unrealized pnl. Rejected: spot cash accounting. An all-in spot open drops equity to about zero, which zeroes Sharpe and fakes a -100% drawdown. Margin equity is also correct for shorts without a signed market value.

## Cross-Process Rules

- Each process has its own in-memory EventBus. No event crosses processes. Processes share state only through Mongo and Redis.
- Live quotes and in-progress bars pass through Redis. The trader writes them. The api's SSE routes poll Redis. The poll delay is acceptable because the shortest bar interval is one minute.
- A backtest runs as a plain asyncio task in the api process. There is no queue and no concurrency cap. Runs share the Mongo pool. The worker marks a run `failed` when its heartbeat stops, so a killed api process leaves no run stuck at `started`.
- Paper positions live in broker memory. The trader that takes the lease rebuilds them from the open `positions` rows and the realized pnl in `trades`. A pending stop never outlives its strategy: stop, unload, edit and handover cancel it, the takeover cancels the stored pending stop of every loaded subscription, and the strategy re-places it on its next bar.
- The startup and shutdown order lives in `app/main.py::lifespan` and `app/roles.py`. Each ordering rule is a comment at its line.

## Symbol Removal

- Removing a tracked symbol deletes every document and cache key that references it. That includes its subscriptions, market data, backtests, and live orders, positions and trades. Nothing is archived. `TrackedSymbolService.remove` owns the cascade.
- A new collection that stores a symbol must be added to the cascade map in `TrackedSymbolService`. Extending `SymbolScopedRepository` alone does not add it.

## Limitations

- The EventBus is in memory. Events are lost on a crash, and there is no outbox.
- Rate-limit buckets live in Redis and reset when Redis restarts.
- A strategy that adds to a position sizes each add against the full paper balance.
- MetaTrader 5 is not built. No code exists, and `:MT5` is not a registered provider suffix. The `MetaTrader5` Python package ships only Windows wheels and works through a running MT5 terminal (checked on PyPI). Exness API keys work only for Exness-platform accounts, not MT5 accounts (checked in the Exness help center). An MT5 account cannot reuse the Exness client.
- An Exness pending stop is tracked only from the events stream. A trader that stops or hands over cancels its pending stops, except one whose placement the stream has not confirmed yet; after a crash the next trader does not re-adopt one, and the snapshot marks its instrument unmapped, which blocks new orders there until the owner cancels the order in the Exness app. Re-adoption must exist before live trading is armed.
- A pause or the daily loss cap does not cancel an Exness pending stop: the venue fills it without asking the trader. Cancel venue pending stops before a pause.
- An accepted Exness close means the venue took the request. It can still fail later with `MARKET_SESSION_CLOSED` or `MARKET_NO_QUOTES`; the position then stays open and the owner retries.
- An Exness pending-stop fill is linked to its order by the deal field `order_id` (from the venue spec).
- The Exness broker reports a resting stop as cancelled when a snapshot no longer lists it. A stop that filled while the stream was disconnected, or while its fill event was still in transit, is reported cancelled too; its position then blocks its instrument. Recovering that fill from the deals history must exist before live trading is armed.
- After a trader restart, an Exness position is matched to a subscription by instrument and side only. Do not hold a manual Exness position on an instrument and side a live subscription trades: an EXIT can close the manual one.

### One position and one pending stop per subscription

A subscription holds at most one position and one pending stop. A new signal cancels the pending stop before it places anything; an unchanged stop (same side and price) is kept. There is no scale-out, no multi-TP and no partial close; a close is always the whole position. These layers each hold one, and all must change together, plus the position box in `web/`:

| Layer | Holds one | Owner |
|---|---|---|
| Signal | `take_profit_price`; `entry_type`; or `Direction.EXIT` | `Signal` (`core/domain/strategy/value_objects.py`) |
| Strategy hook | `Signal \| None` per bar | `IStrategyService.on_bar_completed` |
| Pending stop | one SUBMITTED `STOP_MARKET` order | `OrderAppService.pending_stop` |
| Paper exit | the whole `pos.quantity` | `PaperBrokerAdapter._check_sl_tp`, `close_position`, `_fire_synthetic_exit` |
| Position store | one position per `{subscription_id}:{symbol}`; a second market fill merges into it | `PaperBrokerAdapter._execute_fill` |

The Exness broker also sends one take-profit per order. The engine runs `PaperBrokerAdapter.fill_resting_stops` before strategies decide on a bar: resting stops fill first, then SL/TP exits. A paper stop fills on the first later finest bar whose range reaches it, at the stop or at an open beyond it; in a fast market this is optimistic. On that bar only its SL is checked; it exits at the SL, or at the fill when the SL is already past it.
