# System Architecture

This file holds the decisions, cross-process rules and limits that no single source file states. The code owns everything else. For run and test steps, see the [README](../README.md).

## Decisions

- **Roles run under Mongo leases.** `APP_ROLES` (`core/config.py`) picks the roles a process runs. The worker runs the scheduler and jobs. The trader runs the quote feed, strategies, brokers and the reconcile loop. Each acts only while it holds its lease (`app/roles.py`). A second copy waits warm in standby and takes over when the holder releases or loses the lease. The goal is a trader handover with no trading gap. Rejected: roles bound to a process with no lease, where a second copy duplicates the scheduler, the feed and the broker connection. Prod runs each role as its own service from one image (`deploy/compose.prod.yml`). A deploy rolls them one at a time: the new copy starts in standby, then the old copy stops and releases its lease (`deploy/vps/10-deploy.sh`). The old trader releases at a bar boundary with no order in flight (`app/roles.py::drain_trader`).
- **There is no deploy window.** A deploy may cut a heavy sync job. The cut run is recorded as interrupted, and the next worker resumes it, skipping the symbols the cut run finished (`sync_jobs.py::_tracked`, `enqueue_missed_catchups`). Rejected: holding deploys until heavy jobs finish, which ties every release to the job schedule.
- **Leases use wall-clock time.** Every role must run on one host clock.
- **Strategies are declarative.** Routes write a subscription's `desired_state` to Mongo and return. The trader's reconcile loop (`StrategyReconcileAppService`) converges its engine to Mongo. The api process never calls `StrategyAppService`.
- **A symbol's suffix names its data provider.** The execution broker is a separate setting on each subscription. There is no fallback provider, because the same code on another provider is a different instrument.
- **Exits are SL/TP only.** The risk check rejects EXIT and FLAT signals and any entry against an open position. A paper position closes at its SL or TP. An Exness position closes only at the venue's SL, TP or a stop-out. Unloading a subscription leaves a venue position open under its own SL/TP.
- **Real money is opt-in.** While `EXNESS_LIVE_TRADING` is false, `BrokerFactory` refuses to build the Exness broker and `ExnessClient` refuses every order call. Each check stands on its own.
- **Only the trader's live flag counts.** Compose pins `EXNESS_LIVE_TRADING` off for api and worker, so the trader writes its own flag to the safeguards store at takeover. The Exness strip and the exness subscription create read it there. No order path reads the stored flag. Rejected: passing the flag to the api under a second env var, which reports the env file instead of the running trader.
- **The paper broker uses margin accounting, not spot.** An open does not debit the notional. Equity is the balance plus unrealized pnl. Rejected: spot cash accounting. An all-in spot open drops equity to about zero, which zeroes Sharpe and fakes a -100% drawdown. Margin equity is also correct for shorts without a signed market value.

## Cross-Process Rules

- Each process has its own in-memory EventBus. No event crosses processes. Processes share state only through Mongo and Redis.
- Live quotes and in-progress bars pass through Redis. The trader writes them. The api's SSE routes poll Redis. The poll delay is acceptable because the shortest bar interval is one minute.
- A backtest runs as a plain asyncio task in the api process. There is no queue and no concurrency cap. Runs share the Mongo pool. The worker marks a run `failed` when its heartbeat stops, so a killed api process leaves no run stuck at `started`.
- Paper positions live in broker memory. The trader that takes the lease rebuilds them from open `positions` rows and the realized pnl in `trades`. A paper row with neither SL nor TP is deleted, not restored. It is deleted rather than closed, so it never shows as a finished position.
- The startup and shutdown order lives in `app/main.py::lifespan` and `app/roles.py`. Each ordering rule is a comment at its line.

## Symbol Removal

- Removing a tracked symbol deletes every document and cache key that references it. That includes its subscriptions, market data, backtests, and live orders, positions and trades. Nothing is archived. `TrackedSymbolService.remove` owns the cascade.
- A new collection that stores a symbol must be added to the cascade map in `TrackedSymbolService`. Extending `SymbolScopedRepository` alone does not add it.

## Limitations

- The EventBus is in memory. Events are lost on a crash, and there is no outbox.
- Rate-limit buckets live in Redis and reset when Redis restarts.
- A strategy that adds to a position sizes each add against the full paper balance. No current strategy adds; each holds at most one position.
- MetaTrader 5 is not built. No code exists, and `:MT5` is not a registered provider suffix. The `MetaTrader5` Python package ships only Windows wheels and works through a running MT5 terminal (checked on PyPI). Exness API keys work only for Exness-platform accounts, not MT5 accounts (checked in the Exness help center). An MT5 account cannot reuse the Exness client.

### One take-profit per entry, closed in full

There is no scale-out, no multi-TP and no partial close. Four layers each hold exactly one exit, and all four must change together, plus the position box in `web/`:

| Layer | Holds one | Owner |
|---|---|---|
| Signal | `take_profit_price` | `Signal` (`core/domain/strategy/value_objects.py`) |
| Strategy hook | `Signal \| None` per bar | `IStrategyService.on_bar_completed` (`core/domain/strategy/strategy_service_interface.py`) |
| Paper exit | an exit of the whole `pos.quantity` | `PaperBrokerAdapter._check_sl_tp`, `PaperBrokerAdapter._fire_synthetic_exit` |
| Position store | one position per `{subscription_id}:{symbol}`; a second fill merges into it | `PaperBrokerAdapter._execute_fill` |

The Exness broker also sends one take-profit per order.
