# System Architecture

PocketQuant is one Python package, `src/pocketquant/` (subpackages `core`, `engine`, `app`), plus a React SPA in `web/`. Everything runs in one FastAPI process on port 41921. For run and test steps, see the [README](../README.md). For the directory map, see [codebase-summary.md](./codebase-summary.md).

## Decisions

- **One process, one worker.** The API, the scheduler, the WebSocket feeds, the strategy engine, the reconcile loop and backtest tasks share one process. They are in-process singletons, so `--workers N` would duplicate the reconcile loop and the live broker connection.
- **Dependency direction is fixed:** `core ◁ engine ◁ app`, and `web → app` over HTTP only. import-linter contracts in `pyproject.toml` enforce it.
- **Backtest and live are two drivers on one engine.** `engine.backtest` and `engine.live` never import each other. The shared parts (`engine.strategy`, `engine.execution`, `engine.market_data`) import neither.
- **The domain does no I/O.** `core/domain/` imports no pymongo, redis or aiohttp. `tests/core_test/unit/domain/test_domain_purity.py` checks this.
- **Strategies are declarative.** The API writes the desired state; a loop converges the engine to it (see [Strategy control plane](#strategy-control-plane)).
- **A symbol's suffix names its data provider** (see [Market-data routing](#market-data-routing)). The execution broker is a separate per-strategy setting.
- **All times are UTC.** `assert_utc_runtime()` (`app/main_extensions.py`) refuses to start when the process zone is not UTC.

## Layers

| Layer | Location | Holds |
|---|---|---|
| Domain | `core/domain/` | Entities, value objects, events, domain services, strategies, ports and DTOs. No I/O. |
| Adapters | `core/infra/`, `core/common/` | MongoDB, Redis, repositories, brokers, data providers, calendars, scheduler, middleware, event bus. |
| Engine | `engine/` | Orchestration shared by live and backtest: `strategy/`, `execution/`, `market_data/`, `backtest/`, `live/`. |
| App | `app/` | FastAPI routes, DI container, lifespan, SPA serving. The only package that imports `fastapi`. |
| Web | `web/` | React 19 + Vite SPA. Talks to the app over `/api/*`. |

Ports live in the domain so the engine depends on contracts, not implementations: `IBrokerPort` and `IBrokerFactoryPort` in `core/domain/brokers/`; `IDataProviderPort`, `IRealtimeQuoteProviderPort` and `ITradingCalendarPort` in `core/domain/market_data/`.

## Request Flow

- Middleware, outermost first (`configure_middleware` in `app/main_extensions.py`): `CorrelationIDMiddleware` → `IdempotencyMiddleware` (caches POST responses for 24 h) → `RateLimitMiddleware` (token bucket per client IP in Redis: 200 tokens, 20 per second refill) → `RequestLoggingMiddleware` → CORS.
- Routes in `app/routes/` inject a command or query service with `FromDishka[...]`, call one method and return its DTO. Exceptions go to the global handlers (`core/common/exceptions.py`).
- `app/main_extensions.py` (`register_routes`) mounts every router under `/api/v1`. The live route list is the OpenAPI page at `/api/v1/docs`.

## Dependency Injection

`app/di/` holds three Dishka providers. `create_container(settings)` passes `Settings` in through `from_context` and builds with `STRICT_VALIDATION`, so a type provided twice fails at startup.

| Provider | File | Provides |
|---|---|---|
| `InfrastructureProvider` | `infrastructure.py` | Settings, EventBus, Database, Cache, repositories, calendars, JobScheduler, health. |
| `AdaptersProvider` | `adapters.py` | TradingView and Exness clients, the routed data and quote ports, `BrokerFactory`. |
| `ServicesProvider` | `services.py` | App services, the strategy engine, the command and query services routes inject. |

## Startup and Shutdown

The order lives in `lifespan()` in `app/main.py`. The parts that matter:

1. `set_sync_container(container)` runs before the first `await`. APScheduler keeps `next_run_time` in Mongo, so a persisted job can fire during an early `container.get(...)` and would otherwise hit an unset global. See "Async Suspension Points" in [code-standards.md](./code-standards.md#async-suspension-points--await-is-preemption).
2. Indexes, then recovery sweeps: a backtest left `started` by a killed process is marked `failed`; a `job_history` row stuck at `running` is marked `failed`.
3. Tracked symbols are seeded and one strategy instance per subscription is loaded (`bootstrap_live_instances`). This runs even when jobs are off.
4. Health checks, background jobs, the quote feed, the live trade collector, and last the reconcile loop.

`ENABLE_JOBS=false` skips the background jobs, the live trade collector and the reconcile loop. The quote feed still runs: it writes only ephemeral Redis keys (`quote:latest`, `bar:current`) and in-process events. The `sync_1m` job and its cascade are the only writers of Mongo `bars`, so a local process with jobs off never persists bars.

Shutdown drains in-flight backtests, stops the reconcile loop and the quote feed, then `container.close()` stops the strategy engine, the scheduler, Redis and MongoDB in reverse order.

## Strategy Control Plane

Kubernetes-style split: Mongo holds the desired state, the engine holds the running instances.

- `Subscription` has `desired_state` and `actual_state` (`"running"` or `"stopped"`).
- The start and stop routes write `desired_state` only and return at once.
- `StrategyReconcileAppService` (`engine/live/`) polls every `RECONCILE_INTERVAL_SECONDS` (default 5 s). It reads every subscription from Mongo, starts or stops instances to match `desired_state`, and writes `actual_state` back only on drift. It never enumerates RAM, so backtest strategies stay invisible to it.
- A new subscription is stored with `desired_state="stopped"` and a UUIDv7 id. The route never touches the engine; the reconcile loop loads the instance. The unique index on `(strategy_code, symbol, interval)` rejects duplicates.
- A subscription document without the state fields reads both as `"stopped"`.
- Deleting a subscription removes its document; the reconcile loop unloads the orphan instance.

### Signal flow

`StrategyAppService` (`engine/strategy/`) routes `BarCompletedEvent` and `QuoteReceivedEvent` to the strategies bound to that symbol and interval. A returned `Signal` goes through balance read, position lookup, `RiskCheckHandler`, `PositionCalculatorDomainService`, order creation and `OrderAppService.submit()`. Fills route back to the owning strategy by `subscription_id`. Subscriptions on the same broker share one broker connection.

### Live trades

A broker emits a `TradeClosedEvent` on each position reduce or close (average cost). `StrategyAppService._forward_trade_to_bus` publishes it; `LiveTradeCollector` stamps `run_id=subscription_id` and stores it in `trades`. `LiveMetricsQueryService` computes metrics from `trades` on demand (`GET /api/v1/subscriptions/{sub_id}/metrics`). `OKXBrokerAdapter.subscribe_trades()` is a no-op, so OKX trades are not collected.

## Backtest

A backtest is an ad-hoc single run, independent of subscriptions.

1. `POST /api/v1/backtest/run` allocates a `run_id`, stores a `started` `BacktestResult`, starts `BacktestExecutionService.execute_and_persist` with `asyncio.create_task` (no queue) and returns 202.
2. The run uses its own `BacktestSandboxAppService`: its own EventBus, strategy engine and trackers. Live subscriptions never see replayed bars or synthetic fills, and concurrent runs do not cross-talk.
3. The task stores orders, then trades, then the run, and sets `finished`, or `failed` with `error_message`.
4. The SPA polls `GET /api/v1/backtest/{run_id}` and reads equity, trades (keyset paged), markers, stats and orders from sub-routes.

- The `run_id` is the run document `_id` and the `run_id` of every `backtest_orders` and `backtest_trades` row.
- There is no concurrency cap. Runs share the Mongo pool.
- In-flight tasks live in `app.state.backtest_tasks` and are awaited on shutdown.
- The broker publishes the fill `OrderResult` before the `TradeClosedEvent`, so `BacktestReportAppService.on_trade` can back-link the exit order. Commission is debited per fill; `on_trade` credits pnl only.
- The stored equity curve is the per-bar mark-to-market curve. `BacktestAppService._mtm_on_bar` subscribes after the broker handler, so it reads equity already marked to the bar close.

### Paper broker accounting

`PaperBrokerAdapter` (`core/infra/brokers/paper/`) uses futures/margin accounting at 1x leverage, not spot, because the live domain is OKX perpetual SWAP.

| | Spot | Paper broker |
|---|---|---|
| Open or add | `cash -= notional` | `_balance` unchanged |
| Close or reduce | `cash += proceeds` | `_balance += realized delta` |
| `total_equity` | `cash + Σ market value` | `_balance + Σ unrealized pnl` |
| `available_balance` | `cash` | `_balance` |

- Why: an all-in spot open drops equity to about zero, which zeroes Sharpe and fakes a -100% drawdown. `_balance + unrealized` is also correct for shorts without signed market value.
- `_reduce_and_credit` credits the realized delta of each reduce, not the cumulative value, so partial closes count once.
- `_can_afford` gates only a BUY that opens or adds. A BUY that covers a short is never rejected, or a losing short could not close.
- `available_balance` stays `_balance`, so a strategy that pyramids sizes against the full balance. No current strategy pyramids.
- Spread: the backtest `spread` field (default 0) treats bars as bid prices, so ask = bid + spread. BUY fills pay the ask; a SHORT's SL and TP check the bar's ask high and ask low. The live paper broker runs without spread.

## Market Data

### Market-data routing

- A composite symbol is `{CODE}:{PROVIDER}`. The suffix, lower-cased, is the provider id: `BTCUSDT:BINANCE` → `binance`, `ES1!:TRADINGVIEW` → `tradingview`, `XAUUSD:EXNESS` → `exness`. `provider_id_for()` in `core/domain/market_data/provider_routing_domain_service.py` is the only parser.
- `RoutingDataProviderAdapter` and `RoutingRealtimeQuoteAdapter` (`core/infra/market_data/`) send a symbol to exactly that provider. There is no fallback, because another provider's bars for the same code are a different instrument. An unknown suffix raises `UnknownDataProviderError`.
- An unseeded symbol takes its provider's `asset_class` and `calendar_id` from `DATA_PROVIDER_DEFAULTS`.
- How to add a provider: "Adding a data provider" in [code-standards.md](./code-standards.md#composite-symbol-format).

### Providers

| Provider | Adapter package | Notes |
|---|---|---|
| Binance | `core/infra/binance/` | Public REST, no auth. `@aggTrade` WS for quotes. |
| TradingView | `core/infra/tradingview/` | Index futures through the unofficial `tvDatafeed` scraper, with no stability promise. `TvDatafeedClient` serialises every call with a lock, because the library shares one chart session and parallel calls return one symbol's bars for another. `TRADINGVIEW_EXCHANGE_BY_CODE` maps codes to the scraper's exchange. |
| Exness | `core/infra/exness/` | Signed REST and WS (Ed25519) for CFDs. See below. |

**Exness client.** `EXNESS_API_BASE_URL` serves only `getAccessPoint`. Every later call goes to the per-account access point, resolved once per process and held in memory. Requests are paced by the strictest published limit with 20% headroom, scaled by `EXNESS_RATE_FRACTION`. A 429 on a data call is retried at most 3 times; a 429 on an order call is never retried. Order calls are refused while `EXNESS_LIVE_TRADING` is false.

**Exness data.** `ExnessAdapter` reads bid candles, paged backwards by the published `max_candles_per_request`, and drops the in-progress candle. `ExnessSessionCalendarAdapter` serves three calendars (`EXNESS_FX`, `EXNESS_XAUUSD`, `EXNESS_CRYPTO`) from recorded `trade_sessions`, held in `America/New_York` time so US daylight saving moves them.

### Background jobs

Registered in `register_sync_jobs` (`engine/market_data/app_services/sync_jobs.py`). All triggers are UTC.

| Job | Schedule | Does |
|---|---|---|
| `sync_1m` | every minute at :02 | Fetches 1m bars per tracked symbol, then cascades in-process to higher intervals. A 100-minute lookback heals missed ticks. |
| `data_lag_check` | every minute at :30 | Stores each symbol's feed lag in Redis `data_lag:{symbol}`; logs state changes only. |
| `sync_verify_cascade` | hourly | Compares REST and cascade bars on one sampled symbol. |
| `sync_backfill` | 03:00 | Full backfill. |
| `sync_integrity` | 04:00 | The only place missing 1m bars are reported (`integrity.issues_found`). On 1m it also logs `unexpected`, stored bars at minutes the calendar marks closed, with up to five `unexpected_ranges`. |
| `sync_repair` | every 12 h | Deletes misaligned bars and re-syncs gaps. |

Each symbol is gated by its own calendar. At boot, `enqueue_missed_catchups` enqueues a `<job_id>_catchup` run when a daily or 12 h job's last success is too old.

### Data lag

A delayed feed (the free TradingView plan runs about 10 to 15 minutes behind CME) is flagged, not treated as broken. Lag is counted in trading minutes from the newest 1m bar, so weekends and halts are not lag. Thresholds are constants at the top of `engine/market_data/data_lag_service.py`.

| State | Meaning |
|---|---|
| `ok` | Current. |
| `delayed` | More than 3 minutes behind, still inserting. |
| `stuck` | Behind and one of: 10 empty 1m syncs in a row, more than 30 trading minutes behind, or no 1m sync for 5 minutes. |
| `closed` | The market is shut, whatever the lag. |
| `unknown` | No reading. Never read as healthy. |

`GET /api/v1/market-data/data-lag/{symbol}` serves the reading to the SPA badge.

## Real-Time Streaming

Inbound WebSockets:

- **Binance `@aggTrade`**, one per app. `WsSubscriptionAppService` diffs `tracked_symbols` against current subscriptions every 5 s, spacing subscribe calls 20 ms apart. Reconnect backoff 1 s to 60 s. Unsubscribe is local; the stream changes on the next reconnect.
- **Exness ticks**, one per app, driven by the same diff for `:EXNESS` symbols. Subprotocol `exness-ws-protocol`. A `subscribe` frame was observed to add instruments to earlier ones, so a reconnect re-sends all of them and `unsubscribe()` is local only. Backoff 1 s to 30 s; after 10 failures in a row the breaker pauses 5 minutes. The bid is published as `last_price`.
- **OKX private channels**, one per broker instance. HMAC login, ping every 25 s (OKX times out at 30 s), backoff 1 s to 30 s, breaker pause 5 minutes after 10 failures.
- **Exness account events**, one per process (one pooled adapter; see [Exness broker](#exness-broker)).

Ticks become quotes in Redis `quote:latest:{symbol}` (60 s TTL) and in-progress bars in `bar:current:{symbol}:{interval}`.

Outbound SSE (Redis is the hand-off; the WS writes, SSE reads):

- `GET /api/v1/market-data/bars/stream/{symbol}?interval=` polls Redis every 1 s and emits on change.
- `GET /api/v1/quotes/stream/{symbol}` polls every 0.5 s and emits on change.

The SPA loads the first quote over REST and marks a stream stale when updates stop. The SSE delay (under about 1.2 s) is acceptable for bar intervals of 1 minute and up.

## Brokers

| Broker | Location | State |
|---|---|---|
| `PaperBrokerAdapter` | `core/infra/brokers/paper/` | Simulation; the default broker of a subscription. |
| `OKXBrokerAdapter` | `core/infra/brokers/okx/` | Live, HMAC auth. |
| `ExnessBrokerAdapter` | `core/infra/brokers/exness/` | Built, live trading off by default. |

`BrokerFactory` (`core/infra/brokers/broker_factory.py`) builds them.

### Exness broker

- **Off by default.** While `EXNESS_LIVE_TRADING` is false, `BrokerFactory` refuses `exness` and `ExnessClient` refuses every order call before any network call. `POST /strategies/{code}/subscriptions` takes `broker` (`paper` default, `exness` only while live trading is on).
- **Orders:** market only. A stop loss is required; take profit is optional. A close must cover the whole position. `normalize_quantity` rounds to the lot grid and caps at the minimum lot unless `EXNESS_MAX_LOTS` is set; below the minimum lot no order is created.
- **Daily loss cap (`EXNESS_DAILY_LOSS_CAP`):** unset rejects every order. Today's result comes from real deals (`_realized_today`): profit of `close`, `swap_fee`, `admin_fee` and `dividend` deals, minus the commission of every deal except `balance` deposits and withdrawals. An API error during the check rejects the order.
- **Reconciliation gate:** orders are rejected until the trading snapshot is reconciled, and while a position on the instrument is unmapped. A 429 on an order returns rejected and marks the snapshot stale.
- **Async fills:** fills arrive on the account events WS after the order call returns. `StrategyAppService` wires order updates only for brokers with `fills_async` (Exness) in the live broker pool. The events WS also closes positions closed by the venue (SL, TP, stop-out) and reconciles open positions from `trading_state_snapshot` frames.

## Persistence

All repositories live in `core/infra/persistence/repositories/`, extend `BaseRepository` and receive `Database` by constructor. Every `_id` is a UUIDv7 except `apscheduler_jobs`, which APScheduler writes. Join keys: `subscription_id` for live records, `run_id` for backtest records, the composite `symbol` across market data and trading.

| Collection | Holds |
|---|---|
| `symbols` | Symbol metadata and contract spec. |
| `tracked_symbols` | Symbols to sync and stream. |
| `bars` | OHLCV bars. |
| `sync_status` | Sync progress per symbol and interval. |
| `subscriptions` | Strategy bindings and their control-plane state. |
| `orders`, `positions`, `trades` | Live trading records, keyed by `subscription_id`. |
| `backtest_runs`, `backtest_orders`, `backtest_trades` | Backtest records, keyed by `run_id`. |
| `job_history` | Job run history. |
| `apscheduler_jobs` | APScheduler's job store; processes sharing a database coordinate through it. |

### Symbol removal

`DELETE /api/v1/market-data/tracked-symbols/{symbol}` (`TrackedSymbolService.remove`) deletes the symbol and all data that references it: `tracked_symbols` first (so sync and the WS feed stop), then each subscription, then `symbols`, `bars`, `sync_status`, the backtest collections, live `orders`, `positions` and `trades`, the symbol's `job_history` details, and its Redis keys. Repositories with a `symbol` field extend `SymbolScopedRepository.delete_by_symbol`. The call is idempotent and returns per-collection counts.

## Deployment Shape

Compose on one VPS: `web` (nginx) reverse-proxies `/api/*` to `app` on 41921; `app` has no published port. Cloudflare proxies the public domain to `web`. Secrets live in the separate `pocketquant-config` repo. Details: [deployment.md](./deployment.md).

## Limitations

- The EventBus is in memory: events are lost on a crash, and there is no outbox.
- Rate-limit buckets live in Redis and reset when Redis restarts.
- OKX trades are not collected (`subscribe_trades` is a no-op).

## MT5 (future provider, not built)

MetaTrader 5 is a possible later provider; no code exists. It would plug into `IDataProviderPort` (`copy_rates_from`), `IRealtimeQuoteProviderPort` (`copy_ticks_from`) and optionally `IBrokerPort` (`order_send`), with the suffix `:MT5`, which the routing tests pin as unregistered. The `MetaTrader5` package needs a running MT5 terminal on Windows, so it needs a Windows host or a Wine bridge next to the Linux app. Exness API keys work only for Exness-platform accounts, so an MT5 account cannot reuse the Exness client.
