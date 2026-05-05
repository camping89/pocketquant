---
phase: 4
title: "Tests & Stale Recovery"
status: completed
priority: P2
effort: "0.5d"
dependencies: [3]
---

# Phase 4: Tests & Stale Recovery

## Overview
Đảm bảo cascade đúng, concurrent run an toàn, status không stuck. Thêm startup hook recovery cho jobs `running` quá threshold.

## Requirements

**Functional**
- Stale recovery: app khởi động → scan `backtest_runs` với `status='running' AND last_run_at < now - 10min` → mark `failed` với `error_msg='stale_recovery'`
- Integration tests cho cascade flows
- Unit test cho `deterministic_id` stability

**Non-functional**
- Tests dùng test DB (mongo testcontainer hoặc fixture sẵn có)
- Recovery hook idempotent + không block startup nếu mongo lag

## Architecture

### Stale recovery hook

`packages/pocketquant-trading/src/pocketquant/trading/persistence/backtest_repository.py` (extend):
```python
async def mark_stale_running_as_failed(self, threshold_minutes: int = 10) -> int:
    cutoff = utcnow() - timedelta(minutes=threshold_minutes)
    result = await self._coll.update_many(
        {'status': 'running', 'last_run_at': {'$lt': cutoff}},
        {'$set': {'status': 'failed', 'error_msg': 'stale_recovery'}}
    )
    return result.modified_count
```

`packages/pocketquant-api/src/pocketquant/api/main.py` startup hook:
```python
@app.on_event('startup')  # hoặc lifespan context
async def recover_stale_backtests():
    repo = container.get(BacktestRepository)
    n = await repo.mark_stale_running_as_failed()
    if n: logger.info(f"stale_recovery: marked {n} backtest(s) as failed")
```

### Tests

**Unit** (`packages/pocketquant-trading/tests/`)
- `test_subscription_deterministic_id.py`:
  - Cùng input → cùng id (5 cases)
  - Khác bất kỳ field → khác id
  - id length = 16 chars hex
- `test_strategy_subscription_repository.py`:
  - add → get → delete (round-trip)
  - add duplicate → raises
  - list_by_strategy filter đúng
  - delete_by_strategy bulk

**Integration** (`packages/pocketquant-api/tests/integration/`)
- `test_strategy_subscriptions_api.py`:
  - POST /symbols 2 lần khác sub → 201, 201
  - POST /symbols duplicate → 409
  - GET /symbols → 2 items, backtest=null
  - DELETE /symbols/{id} → 204, GET → 1 item
  - DELETE /strategies/{id} → 204, GET /symbols → 404 hoặc 200 + []
- `test_run_all_backtest_cascade.py`:
  - Setup: load strategy, add 2 subs (dùng symbols có bars sẵn trong test fixtures)
  - POST /run-all → 202 với 2 job_ids
  - Wait until all `done` (poll, max 30s)
  - GET /symbols/{sub_id}/backtest → 200 với positions[]
  - DELETE /strategies/{id} → backtest_runs collection: 0 docs với strategy_id

**Concurrency test** (`packages/pocketquant-api/tests/integration/test_concurrent_run_all.py`):
- POST /run-all x2 trong 100ms → kiểm tra scheduler chỉ có N jobs (không 2N)
- Sau khi xong: chỉ 1 BacktestResult per sub_id

**Stale recovery test** (`packages/pocketquant-trading/tests/test_stale_recovery.py`):
- Insert doc với `status='running', last_run_at=now-30min`
- Call `mark_stale_running_as_failed(threshold=10)` → 1 modified
- Re-call → 0 modified (idempotent)

## Related Code Files

**Create**
- `packages/pocketquant-trading/tests/test_subscription_deterministic_id.py`
- `packages/pocketquant-trading/tests/test_strategy_subscription_repository.py`
- `packages/pocketquant-trading/tests/test_stale_recovery.py`
- `packages/pocketquant-api/tests/integration/test_strategy_subscriptions_api.py`
- `packages/pocketquant-api/tests/integration/test_run_all_backtest_cascade.py`
- `packages/pocketquant-api/tests/integration/test_concurrent_run_all.py`

**Modify**
- `packages/pocketquant-backtest/src/pocketquant/backtest/persistence/backtest_repository.py` (add `mark_stale_running_as_failed`)
- `packages/pocketquant-api/src/pocketquant/api/main.py` (startup hook)

**Read for context**
- Existing test fixtures dưới `tests/conftest.py` mỗi package

## Implementation Steps

1. Add `mark_stale_running_as_failed` to BacktestRepository.
2. Wire startup hook (lifespan event) trong `main.py`.
3. Unit test: `deterministic_id` stability + repo CRUD.
4. Integration test: subscription API + cascade.
5. Integration test: run-all → poll → done → cascade delete kiểm tra DB sạch.
6. Concurrency test: 2 calls / job count assertion.
7. Stale recovery test.
8. Chạy `uv run pytest` cho từng package; fix flaky nếu có.

## Success Criteria

- [x] All unit tests pass
- [x] Integration test cascade: sau DELETE strategy, cả 2 collections không còn docs với `strategy_id` đó
- [x] Concurrency test: scheduler.get_jobs() count đúng, không double
- [x] Stale recovery test: 1 modified lần đầu, 0 lần sau
- [x] App startup log dòng `stale_recovery: ...` khi có docs cần recover
- [x] CI green

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Test flaky vì timing (run-all polling) | Polling với timeout đủ rộng (30s); skip nếu env var `SKIP_SLOW_TESTS` |
| Test cần real strategy YAML để load | Dùng fixture YAML đơn giản (e.g. buy-and-hold) trong `tests/fixtures/strategies/` |
| Stale threshold 10min quá ngắn cho backtest dài | Configurable via Settings (default 30min); doc trong code |
| Mongo testcontainer chậm khởi động CI | Reuse fixture session-scope; cache image |
