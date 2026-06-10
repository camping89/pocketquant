# Strategy Lifecycle

**Scope:** End-to-end strategy lifecycle as implemented in `pocketquant-*` packages.
**Source of truth:** code paths listed inline (no speculation).

The PocketQuant strategy model is **template-based**:

- A **template** is a Python class registered in `STRATEGY_REGISTRY` (e.g. `hitnrun2`)
  — `packages/pocketquant-core/src/pocketquant/core/concepts/strategy/services/__init__.py:5`
- A **subscription** binds a template to a `(symbol, interval)` pair and is the
  unit that lives in MongoDB. Each subscription owns its own in-memory
  `IStrategy` instance keyed by the subscription's deterministic ID
  — `packages/pocketquant-trading/.../trading/domain/subscription.py:24`

**Key terminology:**
- `strategy_code`: the template name (e.g., `"hitnrun2"`), used to identify which strategy class to instantiate
- `subscription_id`: the deterministic 16-char ID of a live subscription instance (e.g., `"a1b2c3d4e5f6g7h8"`)

That distinction drives everything below.

---

## Part A — User-facing operations

### 1. How a strategy is created

`POST /api/v1/strategies/{strategy_code}/subscriptions` with body `{symbol, interval}`.

- Route: `packages/pocketquant-trading/.../handlers/strategy/add_symbol/route.py:22`
- Handler: `.../add_symbol/handler.py:35`
- Flow:
  1. Validate symbol is tracked — `TrackedSymbolRepository.exists()`; otherwise 404
     `SYMBOL_NOT_TRACKED`.
  2. Lookup template class in `STRATEGY_REGISTRY[strategy_code]`; 404 if missing.
  3. Compute `sub_id = sha256(f"{strategy_code}|{symbol}|{interval}")[:16]`
     — deterministic, idempotent.
     `packages/pocketquant-trading/.../trading/domain/subscription.py:44`
  4. If no in-memory `IStrategy` exists for `sub_id`, instantiate one through
     `StrategyAppService.load_strategy(StrategyConfig(id=sub_id, name=strategy_code,
     symbol=symbol, interval=interval), strategy_class=...)`.
  5. Persist `Subscription` to MongoDB `subscriptions` collection (renamed from
     `strategy_subscriptions`). Mongo unique `_id=sub_id` enforces dedup
     → `SubscriptionAlreadyExistsError` (400).
  6. Returns `{id, strategy_code, symbol, interval, created_at, is_running}` with HTTP 201.
     (The new `is_running` field is computed from `StrategyAppService.get_strategy(sub.id).is_running`
     and fixes the bug where FE mistakenly used backtest status to display live state.)

FE entry point: `+ New` button in left sidebar opens `NewSubscriptionDialog`
which posts via `useCreateSubscription` mutation
— `packages/pocketquant-web/src/components/strategies/new-subscription-dialog.tsx`
and `packages/pocketquant-web/src/hooks/use-strategy-mutations.ts:71`.

### 2. How to update or change config

There is **no edit endpoint**. To change a subscription's config:

1. `DELETE /api/v1/subscriptions/{sub_id}` to remove the subscription.
   Cascade-deletes the cached backtest and unloads the in-memory instance
   — `packages/pocketquant-trading/.../handlers/strategy/remove_symbol/handler.py:29`.
2. Re-create with the new `(symbol, interval)` pair via POST
   `/api/v1/strategies/{strategy_code}/subscriptions` (§1.1).

To change strategy-level parameters (e.g. `entry_lookback_bars`):

- Currently parameters are hardcoded in the strategy class (`HitNRun2Strategy`)
  or come from `StrategyConfig.parameters` which is set to `{}` in
  `AddSymbolHandler` — handler builds `StrategyConfig(id, name, symbol, interval)`
  with no parameters override. The runtime parameters override path requires
  editing code and is not exposed via API.
- FE shows config as **read-only**:
  `packages/pocketquant-web/src/components/strategies/strategy-config-card.tsx`
  exposes only Start / Stop / Delete — no edit form.

To delete an entire strategy (all subscriptions + cached backtests + scheduled
jobs in one go): `DELETE /api/v1/strategies/{template_id}` — handler at
`packages/pocketquant-trading/.../handlers/strategy/delete/handler.py:36`.

### 3. How to rerun

**Backtest rerun** (the only "rerun" exposed today):

`POST /api/v1/strategies/{strategy_code}/run-all-backtests` → 202 Accepted.

- Route: `packages/pocketquant-trading/.../handlers/strategy/run_all_backtests/route.py:11`
- Handler: `.../run_all_backtests/handler.py:26`
- Behavior: fans out one `JobScheduler.add_one_off_job(...)` per subscription of
  the strategy, with `job_id = f"bt:{sub.id}"` and module reference
  `pocketquant.backtest.jobs.subscription_backtest_jobs:run_subscription_backtest`. Returns
  `{job_ids: [...]}`. `replace_existing=True` so repeat calls cancel the
  previous tick safely.
- The job persists to `apscheduler_jobs` MongoDB collection (so it survives
  restarts) and executes via `AsyncIOExecutor` immediately
  (`DateTrigger(run_date=now)`).

**Live trading start/stop** (separate from backtests):

- `POST /api/v1/subscriptions/{sub_id}/start` — route
  `packages/pocketquant-trading/.../handlers/strategy/start/route.py:11`,
  handler delegates to `StrategyAppService.start_strategy(sub_id)` which calls
  `IStrategy.on_start()` and connects the broker if needed.
- `POST /api/v1/subscriptions/{sub_id}/stop` — symmetric stop, calls `on_stop()`.
- Note: `sub_id` is the subscription's deterministic ID (e.g., `"a1b2c3d4e5f6g7h8"`).
  The handler takes whatever ID was passed to `load_strategy(config)` — see §1.1 step 4.

### 4. How to see it on the UI

Open the chart UI (`http://localhost:5173` in dev, `http://localhost/`
when the nginx serves the built bundle via bff). The strategies dashboard is a
**3-pane layout**
— `packages/pocketquant-web/src/components/strategies/strategies-page-layout.tsx`:

| Pane | Component | Purpose |
|---|---|---|
| Left (240px) | `StrategyListSidebar` | Lists all subscriptions across all templates. `+ New` button opens `NewSubscriptionDialog`. Single `GET /subscriptions/` call returns all subs with `is_running` + backtest status. |
| Center (flex) | `StrategyChart` + `StrategyConfigCard` | Chart pinned to the subscription's `(symbol, interval)`; config card shows symbol/interval/template + Start/Stop/Delete buttons. Read-only. |
| Right (360px) | `DashboardColumn` | Unrealized PnL badge, equity sparkline, tabs for Metrics / Positions / Trades. Sources data from the cached backtest doc (§5.6) plus live `GET /strategies/{sub_id}/positions` and `/trades`. |

Endpoints feeding the UI:

- `GET /api/v1/strategies/` — list of registered template IDs with metadata
  (returns `[{strategy_code, class_name, description}, ...]`)
  (`packages/pocketquant-backtest/.../handlers/router.py:10`)
- `GET /api/v1/strategies/{strategy_code}` — template metadata
  (`.../get_one/handler.py`)
- `GET /api/v1/subscriptions/?strategy_code=...` — subscriptions enriched with
  backtest status + `is_running` field (optional filter; defaults to all)
  (`packages/pocketquant-trading/.../handlers/strategy/list_symbols/handler.py:23`)
- `GET /api/v1/subscriptions/{sub_id}/backtest` — cached backtest result
  (`.../get_subscription_backtest/handler.py:25`)
- `GET /api/v1/subscriptions/{sub_id}/positions` — open positions
  (`.../get_positions/handler.py:17`)
- `GET /api/v1/subscriptions/{sub_id}/trades` — closed positions as trades
  (`.../get_trades/handler.py:17`)
- `GET /api/v1/system/jobs` — APScheduler job listing for ops visibility
  (`packages/pocketquant-app/.../main_extensions.py:280`)

---

## Part B — What happens behind the hood

### 5. Runtime architecture

#### 5.1 Composition root + DI lifecycle

`packages/pocketquant-app/src/pocketquant/app/main.py:34` defines the FastAPI
`lifespan` context manager. At startup, in order:

1. `set_sync_container(container)` and `set_backtest_container(container)`
   are called **synchronously before any `await`** so persisted MongoDB jobs
   that fire during early Dishka resolves can find their container
   (`main.py:47-48` — explicit comment on the publish-before-subscribe pattern).
2. Resolve `Database` and `Cache` and stash on `app.state`.
3. `register_handlers(container)` — wires CQRS handlers into the `Mediator`.
4. `migrate_strategy_id_fields(container)` — idempotent Mongo boot migration:
   renames collection `strategy_subscriptions` → `subscriptions`,
   renames legacy fields `strategy_id` → `strategy_code` and `strategy_id` → `subscription_id`
   per the field semantics table below, drops legacy indexes. Aborts if both
   old and new collections coexist.
5. `migrate_subscription_desired_state(container)` — idempotent migration:
   backfills `desired_state` and `actual_state` on legacy docs lacking them.
   Sets `desired_state="running"` (auto-resume) and `actual_state="stopped"` on
   docs without `desired_state`. Runs after field-rename migration so it sees
   the final shape. Enables the control plane.
6. `ensure_all_indexes(container)` — creates all Mongo indexes (including new
   `ix_subscriptions_strategy_code`, `ix_orders_subscription_id`, `ix_positions_subscription_id`, etc.).
7. `recover_stale_backtests(container)` — marks any doc stuck in
   `status=running` older than 10 min as `failed`.
8. `recover_orphan_jobs(container)` — same idea for `job_history`.
9. `seed_tracked_symbols(container)`.
10. `rehydrate_strategies_from_subscriptions(container)` — replays §1.1 step 4
   for every persisted `Subscription`: loads one `IStrategy` instance
   per subscription, keyed by `sub.id`. Subscriptions whose strategy_code is no
   longer in `STRATEGY_REGISTRY` are skipped with a warning. Instances are
   loaded stopped (no engine start here).
11. `start_background_jobs(container)` — starts `JobScheduler.start()` and
    registers the cron sync jobs.
12. `start_quote_feed(container, app)` — boots WebSocket aggregator.
13. `start_reconcile_loop(container, app)` — starts the background reconciliation
    service LAST (after rehydrate, so instances exist). Runs as an `asyncio.Task`
    and reconciles every 5s. First tick converges all subscriptions to their
    `desired_state` stored in Mongo (from step 5 migration).

On shutdown, `container.close()` runs `AsyncIterator` factories' cleanup in
reverse order: StrategyAppService.stop → JobScheduler.shutdown →
Cache/Database.disconnect (`main.py:73-74`).

#### 5.2 Reconciliation loop — declaring intent

`StrategyReconcileService` — `packages/pocketquant-execution/.../app_services/strategy_reconcile_service.py`

Runs as a background `asyncio.Task` started at boot step 13 (after rehydrate).
Polls every `Settings.reconcile_interval_seconds` (default 5.0s):

1. Fetch all subscriptions: `SubscriptionRepository.list_all()` (from Mongo).
2. For each subscription:
   - Fetch live instance from RAM: `StrategyAppService.get_strategy(sub.id)`.
   - Compare `sub.desired_state` (Mongo) vs live `instance.is_running` (RAM).
   - If mismatch:
     - Call `start_strategy(sub.id)` or `stop_strategy(sub.id)` to converge.
     - Mirror observed outcome back to Mongo: `update_actual_state(sub.id, observed)`.
3. Log convergence summary: `{started: N, stopped: M}`.

**Idempotent:** `start_strategy` and `stop_strategy` are guarded by locks and early-return if already in the desired state. No per-tick write churn — actual_state updated only on drift.

**Per-subscription error isolation:** A single failing subscription does not crash the loop; the loop logs and continues to the next tick.

**Missing instance handling:** If a subscription has `desired_state="running"` but no RAM instance, the loop records `actual_state="stopped"` and warns once. The subscription is visible to the FE with drift (`desired=running, actual=stopped`).

**Backtest strategies invisible:** Synthetic strategies injected for backtests (via `load_strategy_for_backtest`) have ids not in the subscriptions table; the loop ignores them.

#### 5.3 In-memory state held by `StrategyAppService`

`packages/pocketquant-trading/.../app_services/strategy_app_service.py:24`.

Per-process dicts (NOT shared across replicas):

```python
self._strategies: dict[str, IStrategy]   # sub_id → strategy instance
self._brokers:    dict[str, IBroker]     # sub_id → broker (may be reused by name)
self._configs:    dict[str, StrategyConfig]  # sub_id → config
```

Key invariants:

- Loading the same `sub_id` twice raises `ValueError("Strategy already loaded")`.
- `_brokers` reuses a broker if its `.name` matches `broker_type` or
  `"{broker_type}-demo"` — so multiple strategies on the same broker share one
  connection (`_get_or_create_broker`, line 356).
- `StrategyAppService.start()` registers decorated event handlers via
  `get_event_registry().register_instance(self, self._event_bus)` — auto-binds
  `_on_bar_completed` to `BarCompletedEvent` and `_on_quote_received` to
  `QuoteReceivedEvent`.

#### 5.4 Event-driven signal flow

```
@BarCompletedEvent ──┐
                     ├─▶ StrategyAppService._find_strategies(symbol, interval, trigger)
@QuoteReceivedEvent ─┘                       │
                                             ▼
                              strategy.on_bar(bar) / strategy.on_tick(tick)
                                             │
                                  Signal? ───┴─── None → no-op
                                             ▼
                              StrategyAppService._process_signal(...)
                                  1. broker.get_balance()
                                  2. position_app_service.get(sub_id)
                                  3. RiskCheckHandler.validate(signal, balance, pos, risk)
                                  4. PositionSizer.calculate_size(...)
                                  5. _create_order(...) → OrderAggregate
                                  6. order_app_service.submit(order, broker)
```

Strategies are only triggered if `is_running=True` AND
`config.symbol == event.symbol` AND (`config.interval == event.interval`
when triggered by bar) AND `config.trigger == "bar" | "tick"`
— `_find_strategies` at line 247.

#### 5.5 Backtest job execution

When `POST .../run-all-backtests` fires:

1. `RunAllBacktestsHandler` calls `JobScheduler.add_one_off_job("pocketquant
   .backtest.jobs.subscription_backtest_jobs:run_subscription_backtest", job_id="bt:{sub.id}",
   subscription_id=sub.id)`. APScheduler serializes this as a `DateTrigger`
   row in `apscheduler_jobs` Mongo collection.
2. The AsyncIOExecutor picks it up; `run_subscription_backtest(subscription_id)`
   — `packages/pocketquant-trading/.../jobs/backtest_jobs.py:52` — runs:
   a. Resolve deps via module-level `_container` (`_get_container()`).
   b. Load `Subscription` from Mongo; bail silently if deleted mid-flight.
   c. `BacktestRepository.upsert_status(sub_id, status_code='running', strategy_code=sub.strategy_code)`.
   d. Read base `StrategyConfig` from `strategy_app_service._configs[sub_id]`.
      Raises a clear error if not in memory (e.g. after restart, before
      rehydration completes for that template).
   e. `resolve_date_range(bar_repo, symbol, interval)` — derives backtest range
      from available bar data.
   f. `load_strategy_for_backtest(...)` — loads a **synthetic** strategy
      instance under a job-scoped id so concurrent jobs cannot clobber each
      other (the comment in code labels this "C2 concurrency fix").
   g. `BacktestAppService.run(config)` executes against historical bars
      (PaperBroker, `persist_results=False`).
   h. **TOCTOU re-check**: re-fetch the subscription; if deleted while running,
      do NOT write the result (labeled "M1 TOCTOU" in the code).
   i. `BacktestRepository.save_for_subscription(sub_id, result)` — upserts the
      full `BacktestResult` doc with `_id = sub_id`. Status mapped:
      `'failed' → 'failed' + error_msg`; anything else → `'completed'`.
3. `finally:` unload the synthetic strategy id only — the user's live strategy
   instance is untouched.

Failures: writes `status='failed', error_msg=str(exc)[:500]` and re-raises so
the scheduler's `EVENT_JOB_ERROR` listener also records to `job_history`.

#### 5.6 Risk + sizing pipeline

`_process_signal` calls `RiskCheckHandler.validate(signal, balance, position,
risk_config)`. If it returns `(False, reason)`, the signal is logged as rejected
and dropped. Otherwise `PositionSizer.calculate_size(available_balance,
current_price, stop_loss, risk_config)` returns size; if `≤ 0` the trade is
skipped. The resulting `OrderAggregate` is created with deterministic side
mapping (`LONG → BUY`, `SHORT → SELL`), `order_type` from
`config.orders.entry_type`, and `sl_price`/`tp_price` from the signal.

---

### 6. MongoDB collections (the durable state)

Control-plane truth lives in the `subscriptions` collection (§2).

Sources: `packages/pocketquant-core/src/pocketquant/core/common/constants.py`
(collection names) and each repository's `_collection_name` plus `to_mongo()`
serializers.

| Collection | Owner repo | `_id` | Purpose | Indexes |
|---|---|---|---|---|
| `subscriptions` | `SubscriptionRepository` | `deterministic_id(strategy_code, symbol, interval)` | One row per subscription. Source of truth for what runs after restart (rehydration). | `_id`, `strategy_code` (`ix_subscriptions_strategy_code`) |
| `backtest_runs` | `BacktestRepository` | `sub_id` (subscription-scoped) OR backtest `result.id` (ad-hoc) | One cached backtest result per subscription. Holds `metrics`, `equity_curve`, `open_positions`, `config_snapshot`, `status`, `last_run_at`, `error_msg`. Also holds non-subscription runs from `/backtest/run`. | `strategy_code`, `started_at`, `status`, `(strategy_code, started_at desc)`, `(strategy_code, metrics.sharpe_ratio desc)`, `(strategy_code, metrics.sortino_ratio desc)`, `(strategy_code, metrics.win_rate desc)`, `subscription_id unique sparse` |
| `backtest_orders` | `BacktestOrderRepository` | order id | Per-run order fills array. Indexes: `(strategy_code, status)` |  |
| `backtest_trades` | `BacktestTradeRepository` | trade id | Round-trip trade outcomes from backtests. Indexes: `(strategy_code, direction)` |  |
| `backtest_optimization_runs` | `OptimizationRepository` | run id | Optimizer grid results. Indexes: `strategy_code` |  |
| `orders` | `OrderRepository` | order id | Live orders. Doc keys: `_id, subscription_id, symbol, side, order_type, quantity, price, stop_price, status, filled_quantity, filled_price, broker_order_id, created_at, updated_at`. | `subscription_id` (`ix_orders_subscription_id`) |
| `positions` | `PositionRepository` | position id | Live positions. Doc keys: `_id, subscription_id, symbol, side, entry_price, quantity, current_price, realized_pnl, is_closed, opened_at, closed_at, sl_price, tp_price`. Queries: `find_open_by_subscription(subscription_id)` filters `is_closed=False`; `find_closed_by_subscription` sorts `closed_at desc`. | `subscription_id` (`ix_positions_subscription_id`) |
| `bars` | `BarRepository` | bar id | Historical OHLCV. Consumed by `BacktestAppService` and strategies via `BarCompletedEvent`. |  |
| `sync_status` | `SyncStatusRepository` | symbol+interval | Per-symbol sync progress for the market-data sync jobs. |  |
| `symbols` | `SymbolRepository` | symbol | Symbol metadata. |  |
| `tracked_symbols` | `TrackedSymbolRepository` | symbol | Symbols the platform tracks. `AddSymbolHandler` gates on `exists()`. |  |
| `job_history` | `JobHistoryRepository` | row id | Per-tick scheduler history — `started`, `completed`, `failed`, `missed`, `skipped_max_instances`. Surfaces silent skips. |  |
| `apscheduler_jobs` | APScheduler `MongoDBJobStore` | `job_id` | Serialized scheduled jobs (interval/cron/one-off). Drives cross-process coordination via `next_run_time` updates. |  |

Document shape for the most relevant collection (`subscriptions`):

```jsonc
{
  "_id":            "<16-hex deterministic id>",
  "strategy_code":  "hitnrun2",        // template name in STRATEGY_REGISTRY
  "symbol":         "BTCUSDT:BINANCE", // composite "{code}:{exchange}"
  "interval":       "1h",
  "created_at":     ISODate("..."),
  "desired_state":  "running" | "stopped",  // control plane: what user/API intends
  "actual_state":   "running" | "stopped"   // data plane: what reconcile loop observed
}
```

Backtest cache doc shape (`backtest_runs` keyed by `sub_id`):

```jsonc
{
  "_id":             "<sub_id>",
  "subscription_id": "<sub_id>",
  "strategy_code":   "hitnrun2",        // renamed from "strategy_id"
  "status":          "completed" | "running" | "failed",
  "last_run_at":     ISODate("..."),
  "error_msg":       null | "<truncated 500 chars>",
  // when status='completed' the full BacktestResult fields are present:
  "config_snapshot": { ... },
  "metrics":         { "sharpe_ratio": ..., "win_rate": ..., ... },
  "equity_curve":    [ { "ts": ..., "equity": ... }, ... ],
  "open_positions":  [ ... ],
  "started_at":      ISODate("..."),
  "completed_at":    ISODate("..."),
  "parameters":      { ... }   // optimizer-only
}
```

Live order and position docs (collections `orders` and `positions`) now use
`subscription_id` (the 16-char deterministic ID) instead of `strategy_id`
(which held the subscription ID in v1, causing confusion).

---

### 7. Redis cache contents

`Cache` wraps `redis.asyncio.Redis` and is DI-scoped APP. See
`packages/pocketquant-core/src/pocketquant/core/persistence/redis.py` and
the constants at
`packages/pocketquant-core/src/pocketquant/core/common/constants.py:27-41`.

**Strategy code itself touches no Redis keys directly.** The cache is used
upstream of strategies by market-data and middleware layers:

| Key pattern | Set by | Read by | TTL |
|---|---|---|---|
| `quote:latest:{symbol}` | `QuoteAppService` on `QuoteReceivedEvent` (`packages/pocketquant-app/.../quote_app_service.py:65`) | `GetLatestQuoteHandler`, `GetAllQuotesHandler`, `/quotes/stream` SSE route | 60s (`TTL_QUOTE_LATEST`) |
| `bar:current:{symbol}:{interval}` | `BarAppService` (`packages/pocketquant-app/.../bar_app_service.py:216`) | `BarAppService.get_current_bar` | 300s (`TTL_BAR_CURRENT`) |
| `ohlcv:{symbol}:{interval}:{limit}[:from:...][:to:...]` | `GetOHLCVHandler` (`packages/pocketquant-app/.../ohlcv/get_ohlcv/handler.py:46`) | same handler — query-result cache | 300s (`TTL_OHLCV_QUERY`) |
| `ohlcv:{SYMBOL}:{interval}:*` (delete-pattern) | `SyncOneHandler` after sync completion (`.../sync/sync_one/handler.py:176`) | Cache invalidation — drops every limit variant for that symbol/interval. | n/a (delete) |
| Idempotency keys | `IdempotencyMiddleware` (`packages/pocketquant-core/.../middleware.py`) | same | request-scoped |
| Rate-limit tokens | `RateLimitMiddleware` | same | window-scoped |
| Health-check liveness | `checks.py` | health endpoint | short |

Implications for strategies:

- Backtest jobs read bars directly from `BarRepository` (Mongo), not from
  Redis. The OHLCV cache only short-circuits the `/market-data/ohlcv` REST
  endpoint.
- Live strategy `on_bar` / `on_tick` is fed by **events** (`BarCompletedEvent`,
  `QuoteReceivedEvent`) over the in-process `EventBus`, not via Redis pub/sub.
- The `quote:latest` cache key is what the `/quotes` SSE stream returns to
  the FE chart — it does NOT gate strategy execution.

---

### 8. How storage and operation tie together

The lifecycle is best read as: **subscription is the source of truth (control plane) →
reconcile loop converges engine state (data plane) → everything else is derived**.

Control-plane truth: `subscriptions` collection holds `desired_state` and `actual_state`.
Data-plane truth: `StrategyAppService` instances' `is_running` flag, converged by reconcile loop every 5s.

```
                       ┌─────────────────────────────────────────────────┐
                       │ MongoDB: subscriptions (durable)                │
                       │  _id = sha256(strategy_code|symbol|interval)    │
                       └─────────┬───────────────────────────────────────┘
                                 │
       ┌─────────────────────────┼──────────────────────────┐
       │                         │                          │
       │ on startup              │ on add_symbol            │ on delete
       ▼                         ▼                          ▼
 rehydrate_from_           AddSymbolHandler          DeleteStrategy /
 _subscriptions           (load + insert)           RemoveSymbol cascade
       │                         │                          │
       ▼                         ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│ StrategyAppService (in-memory, per process)                       │
│   _strategies[sub_id] = IStrategy instance                        │
│   _brokers[sub_id]    = IBroker                                   │
│   _configs[sub_id]    = StrategyConfig                            │
└──────────┬──────────────────────────────────────────────┬─────────┘
           │                                              │
           │ EventBus subscription                        │ start_strategy
           ▼                                              ▼
   BarCompletedEvent / QuoteReceivedEvent          broker.connect()
           │                                              │
           ▼                                              │
   _on_bar_completed / _on_quote_received                 │
           │                                              │
           ▼                                              │
   strategy.on_bar() → Signal                             │
           │                                              │
           ▼                                              │
   _process_signal: risk → size → OrderAggregate          │
           │                                              │
           ▼                                              │
   OrderAppService.submit(order, broker)  ───────────────▶│
                                                          ▼
                                          MongoDB: orders, positions
                                          (live state)


Backtest path is parallel and isolated:
  POST run-all-backtests → JobScheduler.add_one_off_job → apscheduler_jobs (Mongo)
                       → AsyncIOExecutor picks up DateTrigger
                       → run_subscription_backtest(sub_id):
                           resolve_date_range → bars (Mongo)
                           load synthetic strategy id → PaperBroker
                           BacktestAppService.run(config) → BacktestResult
                           save_for_subscription(sub_id, result) → backtest_runs (Mongo)
```

**State machine for a subscription's cached backtest** (collection
`backtest_runs`, `_id = sub_id`):

```
   (no doc)
      │ first run-all
      ▼
   running ────error────▶ failed (error_msg set)
      │                     │
      │ run completes       │ next run-all (replace_existing=True)
      ▼                     ▼
   completed ◀───────── running
```

**Restart semantics:**

| State | Persisted? | Recovered on restart |
|---|---|---|
| Subscription template + (symbol, interval) | Yes (`subscriptions` collection) | Re-loaded via `rehydrate_strategies_from_subscriptions` |
| Running/stopped intent | Yes (`subscriptions.desired_state`) | `desired_state` restored from Mongo; reconcile loop converges to it within 1 tick |
| Running/stopped observation | Yes (`subscriptions.actual_state`) | `actual_state` restored from Mongo; reflects last observed engine state before shutdown. Reconcile loop immediately re-observes on next tick. |
| Cached backtest result | Yes (`backtest_runs`) | Available immediately after rehydration |
| In-flight backtest in `running` state | Yes (status row) | `recover_stale_backtests` flips `running` older than 10 min to `failed` |
| Scheduled jobs (cron/interval/one-off) | Yes (`apscheduler_jobs`) | Picked up automatically; missed ticks within `misfire_grace_time=300s` still fire |
| Job history (per-tick records) | Yes (`job_history`) | Orphans stuck in `running` older than 600s flipped to `failed` by `recover_orphan_jobs` |
| Redis OHLCV / quote caches | TTL'd | Auto-rebuild on first request after expiry |

---

## Quick-reference: HTTP API surface for strategies

| Method | Path | Purpose | File |
|---|---|---|---|
| GET  | `/api/v1/strategies/` | List template IDs with metadata `{strategy_code, class_name, description}` | `pocketquant-backtest/.../handlers/router.py:10` |
| GET  | `/api/v1/strategies/{strategy_code}` | Get template metadata | `strategy/get_one/route.py` |
| POST | `/api/v1/strategies/{strategy_code}/subscriptions` | Create a subscription | `strategy/add_symbol/route.py` |
| GET  | `/api/v1/subscriptions/?strategy_code=...` | List subscriptions with backtest status (optional filter; defaults to all) | `strategy/list_symbols/route.py` |
| DELETE | `/api/v1/subscriptions/{sub_id}` | Remove a subscription (cascade) | `strategy/remove_symbol/route.py` |
| POST | `/api/v1/subscriptions/{sub_id}/start` | Start a live subscription instance | `strategy/start/route.py` |
| POST | `/api/v1/subscriptions/{sub_id}/stop` | Stop a live subscription instance | `strategy/stop/route.py` |
| POST | `/api/v1/strategies/{strategy_code}/run-all-backtests` | Enqueue one-off backtest per subscription | `strategy/run_all_backtests/route.py` |
| GET  | `/api/v1/subscriptions/{sub_id}/backtest` | Read cached backtest doc | `strategy/get_subscription_backtest/route.py` |
| GET  | `/api/v1/subscriptions/{sub_id}/positions` | Open positions for a subscription | `strategy/get_positions/route.py` |
| GET  | `/api/v1/subscriptions/{sub_id}/trades` | Closed positions for a subscription | `strategy/get_trades/route.py` |
| DELETE | `/api/v1/strategies/{strategy_code}` | Cascade delete template + all subs + backtests | `strategy/delete/route.py` |

---

## Unresolved Questions

1. **Edit-config endpoint missing.** The only way to "change config" is
   delete + re-create. Is an `UpdateSubscriptionCommand` planned that would
   either update `StrategyConfig.parameters` in place (and persist them on the
   subscription row) or hot-reload the in-memory instance?
2. **`config.parameters` is `{}` for FE-created subscriptions.** `AddSymbolHandler`
   builds `StrategyConfig` without passing any `parameters` dict, so the
   strategy class falls back to whatever defaults it hard-codes. Should
   parameters be (a) persisted on the subscription, (b) part of the template
   registration, or (c) sent in the `AddSymbol` body?
3. **Redis use for strategies is currently zero.** Worth caching the
   `subscriptions` rehydration list, recent signal counts, or
   per-subscription live PnL snapshots in Redis to avoid Mongo round-trips on
   every `/subscriptions/{sub_id}/positions` poll?
4. **Backtest stale-recovery threshold = 10 min** vs **orphan job recovery =
   600s**. Inconsistent; if a real backtest legitimately runs longer than 10
   min it gets force-failed. Should the threshold be derived from
   `BacktestConfig` or made configurable per template?
