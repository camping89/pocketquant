---
phase: 2
title: "Backend Job Worker & CQRS"
status: pending
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 2: Backend Job Worker & CQRS

## Overview
Wire repos vào DI, implement async job worker, 6 CQRS handlers, FastAPI routes. Đây là tầng "API contract" mà FE consume ở P3.

## Requirements

**Functional**
- Routes hoạt động đúng theo brainstorm bảng
- Run-all fan-out non-blocking, dùng deterministic `job_id = f"bt:{sub_id}"` với `replace_existing=True`
- Cascade trong DELETE strategy + DELETE subscription
- Get-subscription-backtest trả 200 nếu có cache, 404 nếu chưa run

**Non-functional**
- Handler files < 100 LOC mỗi cái (tách command/query/handler/route)
- Tuân CQRS pattern + DishkaRoute (per `CLAUDE.md`)

## Architecture

### Job worker

`packages/pocketquant-trading/src/pocketquant/trading/jobs/backtest_jobs.py`:

```python
async def run_subscription_backtest(subscription_id: str) -> None:
    # 1. Resolve subscription via DI container
    container = get_container()
    sub_repo = container.get(StrategySubscriptionRepository)
    bt_repo = container.get(BacktestRepository)
    bar_repo = container.get(BarRepository)
    bt_service = container.get(BacktestAppService)
    strategy_service = container.get(StrategyAppService)

    sub = await sub_repo.get(subscription_id)
    if not sub: return

    await bt_repo.upsert_status(subscription_id, strategy_id=sub.strategy_id, status='running')

    try:
        config = await build_config(strategy_service, sub, bar_repo)
        result = await bt_service.run(config)
        await bt_repo.save_for_subscription(subscription_id, result)
    except Exception as e:
        await bt_repo.upsert_status(
            subscription_id, strategy_id=sub.strategy_id,
            status='failed', error_msg=str(e)[:500]
        )
        raise
```

`build_config()` lấy strategy logic/params từ in-memory `StrategyAppService._configs[strategy_id]`, override `symbol/exchange/interval` từ subscription, đặt `start_date/end_date` từ `BarRepository.get_range()`.

**APScheduler note**: function phải top-level + serializable. Container access qua singleton getter (existing pattern check `pocketquant.api.di.container`).

### CQRS handlers

Theo `pocketquant-trading/handlers/strategy/` đã có (`load`, `start`, `stop`, `get_all`). Thêm:

```
handlers/strategy/
  add_symbol/        command.py, handler.py, route.py
  remove_symbol/     command.py, handler.py, route.py
  list_symbols/      query.py,   handler.py, route.py
  run_all_backtests/ command.py, handler.py, route.py
  get_subscription_backtest/ query.py, handler.py, route.py
  delete/            command.py, handler.py, route.py   # cascade unload
```

Mỗi handler ngắn (~20-40 LOC). Router gộp thêm vào `handlers/strategy/router.py`.

### Routes (Dishka)

```python
@router.post("/strategies/{strategy_id}/symbols", status_code=201)
async def add_symbol(strategy_id: str, body: AddSymbolBody, mediator: FromDishka[Mediator]):
    return await mediator.send(AddSymbolCommand(strategy_id, body.symbol, body.exchange, body.interval))

@router.get("/strategies/{strategy_id}/symbols")
async def list_symbols(strategy_id: str, mediator: FromDishka[Mediator]): ...

@router.delete("/strategies/{strategy_id}/symbols/{sub_id}", status_code=204)
async def remove_symbol(strategy_id: str, sub_id: str, mediator: FromDishka[Mediator]): ...

@router.post("/strategies/{strategy_id}/backtest/run-all", status_code=202)
async def run_all(strategy_id: str, mediator: FromDishka[Mediator]):
    return await mediator.send(RunAllBacktestsCommand(strategy_id))  # → {job_ids: [...]}

@router.get("/strategies/{strategy_id}/symbols/{sub_id}/backtest")
async def get_backtest(strategy_id: str, sub_id: str, mediator: FromDishka[Mediator]): ...

@router.delete("/strategies/{strategy_id}", status_code=204)
async def delete_strategy(strategy_id: str, mediator: FromDishka[Mediator]): ...
```

### DI

`packages/pocketquant-api/src/pocketquant/api/di/`:
- **PersistenceProvider**: thêm `StrategySubscriptionRepository` provider
- **HandlerProvider**: register 6 handlers mới
- App startup hook: `await sub_repo.ensure_indexes()` + `await bt_repo.ensure_indexes()`

### Cascade flows

- `RemoveSymbolHandler`:
  1. Cancel job nếu đang chạy: `scheduler.remove_job(f"bt:{sub_id}", jobstore='default')` (try/except — có thể không tồn tại)
  2. `bt_repo.delete_by_subscription(sub_id)`
  3. `sub_repo.delete(sub_id)`

- `DeleteStrategyHandler`:
  1. `subs = sub_repo.list_by_strategy(strategy_id)` → cancel mỗi job
  2. `bt_repo.delete_by_strategy(strategy_id)`
  3. `sub_repo.delete_by_strategy(strategy_id)`
  4. `strategy_service.unload_strategy(strategy_id)` (existing method, line 158-167)

- `RunAllBacktestsHandler`:
  1. `subs = sub_repo.list_by_strategy(strategy_id)` → 404 nếu rỗng
  2. For each sub: `scheduler.add_job(run_subscription_backtest, args=[sub.id], id=f"bt:{sub.id}", replace_existing=True, trigger='date')` (run-once, immediate)
  3. Return `{job_ids: [f"bt:{sub.id}" for sub in subs]}`

### Response shapes

```python
# GET /symbols
[
  {id, strategy_id, symbol, exchange, interval, created_at,
   backtest: {status, last_run_at, error_msg} | null}
]

# GET /symbols/{sub_id}/backtest (200 if status=done)
{subscription_id, strategy_id, status, last_run_at,
 metrics: {...}, positions: [...], equity_curve: [...], trades: [...]}

# 404 nếu chưa từng run; 202 + status='running' nếu đang chạy (FE poll)
```

## Related Code Files

**Create**
- `packages/pocketquant-trading/src/pocketquant/trading/jobs/backtest_jobs.py`
- `packages/pocketquant-trading/src/pocketquant/trading/jobs/__init__.py`
- 6 handler folders dưới `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/`

**Modify**
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/router.py` (gắn 6 routes)
- `packages/pocketquant-api/src/pocketquant/api/di/persistence_provider.py` (provide SubscriptionRepo)
- `packages/pocketquant-api/src/pocketquant/api/di/handler_provider.py` (register handlers)
- `packages/pocketquant-api/src/pocketquant/api/main.py` (or startup hook) — call `ensure_indexes()`

**Read for context**
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/handler.py` (handler pattern)
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py:36-80`
- `packages/pocketquant-backtest/src/pocketquant/backtest/engine/backtest_app_service.py:57-142`
- `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py` (`get_range` method)

## Implementation Steps

1. **Job worker** (`backtest_jobs.py`): viết `run_subscription_backtest` + `build_config` helper. Dùng container singleton.
2. **DI providers**: register `StrategySubscriptionRepository` (PersistenceProvider). Verify `BacktestAppService` có thể access qua container.
3. **Add symbol**: command/handler/route. Handler tạo `StrategySubscription.deterministic_id`, validate strategy đã loaded (`strategy_service.is_loaded(strategy_id)` — add helper nếu chưa có), persist sub.
4. **List symbols**: query trả mảng subs + nested backtest status (join lookup hoặc 2 calls).
5. **Remove symbol**: cancel job + cascade delete.
6. **Run all**: enqueue jobs.
7. **Get subscription backtest**: lookup, return 404 nếu null hoặc status≠'done'? — Decision: **always return doc**, FE check `status` field. Easier polling. 404 chỉ khi document không tồn tại (chưa Run lần nào).
8. **Delete strategy**: cascade unload + xóa subs/backtests.
9. **Wire routes** vào `strategy/router.py`. Smoke test mỗi route với httpie/curl.
10. **Compile + run**: `uv run pocketquant-api` → swagger UI tại `/docs`, kiểm tra 6 endpoints xuất hiện.

## Success Criteria

- [ ] POST `/strategies/{id}/symbols` với `{BTC-USDT, okx, 1h}` → 201, doc tồn tại
- [ ] POST lần 2 cùng input → 409 Conflict
- [ ] GET `/strategies/{id}/symbols` → array với `backtest: null` cho subs chưa run
- [ ] POST `/run-all` → 202, response `{job_ids: [...]}`, scheduler có jobs
- [ ] Sau ~vài giây: GET `/symbols/{sub_id}/backtest` → 200 với positions
- [ ] DELETE `/strategies/{id}/symbols/{sub_id}` → 204, doc gone, backtest gone
- [ ] DELETE `/strategies/{id}` → 204, list_by_strategy empty cho cả 2 collections
- [ ] Concurrent `/run-all` x2 → scheduler chỉ có 1 job per sub_id (replace_existing OK)

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Container access từ APScheduler job (sync vs async context) | Kiểm tra existing pattern trong `pocketquant-core/.../sync_jobs.py`. Có thể cần `asyncio.run()` wrapper. |
| BacktestAppService.run() yêu cầu strategy đã loaded trong memory | Validate strategy loaded trước khi enqueue; nếu không → 400 |
| BarRepository.get_range() với symbol mới chưa sync bars | Job fail status='failed' với message rõ ràng |
| Race: user delete sub khi job đang run | `remove_job` swallow exception; job sau đó upsert status vào doc đã xóa → no-op nếu doc gone (upsert tạo lại); cần guard: kiểm tra sub còn tồn tại đầu mỗi job step |

## Security Considerations
Auth/authz skip per brainstorm. Input validation qua Pydantic models (symbol regex, exchange whitelist, Interval enum).
