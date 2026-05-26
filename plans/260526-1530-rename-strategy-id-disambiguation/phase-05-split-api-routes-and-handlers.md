# Phase 05 — Split API routes + update handlers

**Priority:** Public surface change. Blocks phase 6 (FE).
**Status:** ⏳ pending, blocked by 3

## Scope

Split today's mixed `/strategies/{strategy_id}/...` into two clearly-scoped routers:

- `/strategies/{strategy_code}` → template-scoped operations
- `/subscriptions/{sub_id}` → instance-scoped operations

Update every handler's command/query/handler.py to use the right field name. Rename path params in route decorators.

## New route map

```
/api/v1/strategies                         ── template-scoped ──
  GET    /                                 list registered templates (from STRATEGY_REGISTRY)
  GET    /{strategy_code}                  template metadata (description, default params)
  POST   /{strategy_code}/subscriptions    create a subscription for this template
                                           body: {symbol, interval}    (was: POST /strategies/{id}/symbols)
  POST   /{strategy_code}/run-all-backtests  trigger backtest fan-out for all subs of this template
  DELETE /{strategy_code}                  remove ALL subs (+ backtests + runtime) for this template

/api/v1/subscriptions                      ── instance-scoped ── (NEW prefix)
  GET    /                                 list ALL subscriptions (optionally ?strategy_code=)
  GET    /{sub_id}                         subscription details (incl. is_running, backtest status)
  DELETE /{sub_id}                         remove this single subscription
  POST   /{sub_id}/start                   start the runtime strategy instance
  POST   /{sub_id}/stop                    stop it
  GET    /{sub_id}/positions               open positions for this sub
  GET    /{sub_id}/trades                  trades for this sub
  GET    /{sub_id}/backtest                latest backtest result for this sub
```

## Routes to remove

- `GET /strategies/{strategy_id}` (use `GET /subscriptions/{sub_id}` instead — old route mixed meanings)
- `POST /strategies/load` — kept (admin loader). Document explicitly as admin-only.
- `POST /strategies/{strategy_id}/start` → moved to `/subscriptions/{sub_id}/start`
- `POST /strategies/{strategy_id}/stop` → moved to `/subscriptions/{sub_id}/stop`
- `GET /strategies/{strategy_id}/symbols` → replaced by `GET /subscriptions/?strategy_code=X`
- `POST /strategies/{strategy_id}/symbols` → moved to `POST /strategies/{strategy_code}/subscriptions`
- `DELETE /strategies/{strategy_id}/symbols/{sub_id}` → moved to `DELETE /subscriptions/{sub_id}`
- `GET /strategies/{strategy_id}/positions` → `GET /subscriptions/{sub_id}/positions`
- `GET /strategies/{strategy_id}/trades` → `GET /subscriptions/{sub_id}/trades`
- `GET /strategies/{strategy_id}/symbols/{sub_id}/backtest` → `GET /subscriptions/{sub_id}/backtest`
- `POST /strategies/{strategy_id}/backtest/run-all` → `POST /strategies/{strategy_code}/run-all-backtests`

## Handler file restructure

Create new tree:
```
trading/handlers/
├── strategy/                      # template-scoped (keep prefix /strategies)
│   ├── list_templates/            # NEW — wraps STRATEGY_REGISTRY
│   ├── get_template/              # NEW
│   ├── create_subscription/       # renamed from add_symbol/
│   ├── run_all_backtests/         # rename path
│   ├── delete_by_code/            # renamed from delete/
│   └── router.py
└── subscription/                  # NEW prefix /subscriptions
    ├── list_subscriptions/        # was list_symbols
    ├── get_subscription/          # was get_one (the runtime variant)
    ├── delete_subscription/       # was remove_symbol
    ├── start/                     # was strategy/start
    ├── stop/                      # was strategy/stop
    ├── get_positions/             # was strategy/get_positions
    ├── get_trades/                # was strategy/get_trades
    ├── get_backtest/              # was strategy/get_subscription_backtest
    └── router.py
```

Per CLAUDE.md naming: each handler dir contains `command.py`/`query.py`, `handler.py`, `route.py`, `__init__.py`.

## Field rename in commands/queries

- `StartStrategyCommand.strategy_id` → `StartSubscriptionCommand.subscription_id`
- `StopStrategyCommand.strategy_id` → `StopSubscriptionCommand.subscription_id`
- `AddSymbolCommand.strategy_id` → `CreateSubscriptionCommand.strategy_code`
- `ListSymbolsQuery.strategy_id` → `ListSubscriptionsQuery.strategy_code` (optional filter)
- `DeleteStrategyCommand.strategy_id` → `DeleteByStrategyCodeCommand.strategy_code`
- `GetStrategyQuery.strategy_id` → `GetSubscriptionQuery.subscription_id`
- ... (same pattern for positions/trades/backtest)

## Wiring in api/main.py

Update DI / route registration:
- `app.include_router(strategy_router, prefix="/api/v1")` (existing)
- `app.include_router(subscription_router, prefix="/api/v1")` (NEW)

## Edge cases

- `rehydrate_strategies_from_subscriptions` (in `main_extensions.py`) reads `sub.strategy_code` to look up template in `STRATEGY_REGISTRY` — already covered by phase 2.
- Backtest jobs (`backtest_jobs.py`) read `sub.strategy_code` instead of `sub.strategy_id` — phase 2.

## Implementation steps

1. Move files / create new directory structure.
2. Update every `command.py`/`query.py` field name.
3. Update `handler.py` body where it reads `request.strategy_id` → `request.strategy_code` or `.subscription_id`.
4. Update `route.py` path decorator + arg name + mediator command construction.
5. Update `router.py` includes.
6. Wire new subscription_router in `api/main.py`.
7. `just types && just lint && just test` (unit + integration).

## Acceptance criteria

- All routes reachable per the new map (verified via OpenAPI docs page at `/api/v1/docs`)
- Old route paths return 404
- `just types && just lint` pass
- Integration tests (after phase 7) pass

## Out of scope

- FE updates (phase 6)
- Test updates (phase 7)
- Versioned URL deprecation shims (single-deploy strategy per plan.md)
