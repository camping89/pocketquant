# Brainstorm — Backtest Direct-Task Execution (bỏ queue/worker + xóa /optimize)

Metadata: mode=brainstorm · date=2026-06-29 · branch=develop · flags=none

## Problem statement

Pain gốc (từ session trước): "bấm backtest mà data không persist đủ để review, cách chạy rối + dính cờ `ENABLE_JOBS` đụng prod."

User đề xuất 3 giải pháp (solution-jumping):
1. Bỏ hẳn `/optimize`, chỉ dùng `/run`.
2. `/run` trigger 1 luồng chạy, không phụ thuộc jobs.
3. Check DI/scope tránh tranh chấp Mongo client/pool.

## Scout findings

- **2 entry backtest**: `/backtest/run` (async, enqueue → `BacktestRequestWorker` drain, persist đủ) + `/backtest/optimize` (sync inline, grid search, `persist_results=False`). Cộng `/strategies/{code}/run-all-backtests` (fan-out subscription, async).
- **FE thực gọi**: `run-all-backtests` + `/subscriptions/{id}/backtest`. **KHÔNG gọi `/backtest/run` lẫn `/optimize`** → cả 2 entry chưa có UI tiêu thụ.
- **DI scope**: tất cả `Scope.APP` (singleton) — `Database`, mọi repo, worker, dispatch deps. Không có `Scope.REQUEST`.
- **Mongo**: 1 `AsyncMongoClient`, pool `min=5/max=50`. pymongo async pool tự quản, concurrency-safe.
- **Engine**: replay loop `await publish()` mỗi bar + `asyncio.sleep(0)` khi `replay_speed=0` → yield event loop mỗi bar (async, KHÔNG CPU-block thuần → không dùng OS thread).
- **`ENABLE_JOBS` coupling**: 1 cờ gate cả scheduler + reconcile loop + WS feed (chạm live) + backtest worker (sandbox-isolated, vô hại) tại `main_extensions.py`.

## Phản biện 3 đề xuất

| Đề xuất | Verdict | Lý do |
|---|---|---|
| #1 Xóa `/optimize` | ✅ Đúng (theo nhu cầu) | `/optimize` = grid tuning, KHÁC `/run`. User xác nhận **không bao giờ tuning** → dead feature (FE không gọi) → xóa hợp YAGNI. |
| #2 Bỏ job, chạy task riêng | ✅ Đúng (sau khi chốt manual-only) | Ban đầu phản đối (queue cần cho scheduled). User xác nhận **never scheduled** → lý do tồn tại của persistent queue sụp → direct `asyncio.create_task` hợp lý. Lưu ý: async task, KHÔNG phải OS thread. |
| #3 Đổi scope tránh pool conflict | ❌ Non-issue | 1 singleton client + pool là best practice (pymongo doc). Repo `Scope.APP` stateless → không tranh chấp. KHÔNG cần `Scope.REQUEST`. |

## Quyết định (chốt với user)

- **Execution**: Option Z — direct background task. Bỏ hẳn `backtest_requests` queue + `BacktestRequestWorker` + coupling `ENABLE_JOBS` cho backtest.
- **Single run UX**: luôn async + poll (timeout-safe cho multi-year ~ phút).
- **Concurrency**: KHÔNG cap (user tự quản traffic/amount).
- **`/optimize`**: xóa toàn bộ.
- **Persist**: đủ (runs + orders + trades + equity).
- **Subscription**: fix `persist_results=True` + save orders/trades để review thấy trades.
- **DI/scope**: giữ nguyên singleton client/pool(5/50)/repo `Scope.APP`.

## Kiến trúc mới

Status model (fire-and-forget, KHÔNG sweep/reclaim/recovery):
```
trigger → backtest_runs { status:"started",  started_at }
done    → update         { status:"finished", completed_at, metrics, equity } + orders/trades
error   → update         { status:"failed",   error_message }   (log only, no retry)
```

```
POST /backtest/run
  → tạo backtest_runs {status:"started", run_id} (FE poll được ngay)
  → asyncio.create_task( run_single → persist đủ → update status finished/failed )
  → trả {run_id} (202)
FE: poll GET /backtest/{run_id} (đã có) → started → finished/failed

POST /strategies/{code}/run-all-backtests
  → fan-out N task trực tiếp (KHÔNG cap — user tự quản traffic), mỗi task tự persist
```

### Quyết định cuối (chốt với user)
- **Status vocab**: đổi `running/completed/failed` → **`started/finished/failed`**. Blast radius: phải sửa FE (badge + poll) + subscription path.
- **Error**: ghi `failed` + `error_message` (ignore = không retry/recovery, nhưng vẫn log để audit + FE hiện).
- **KHÔNG startup sweep**: fire-and-forget, không còn khái niệm "running cần reclaim". Doc orphan (nếu restart) cứ để "started", chấp nhận.
- **KHÔNG cancel endpoint** (YAGNI).
- **KHÔNG cap concurrency** (user tự quản).
- **Drop prod collections sau deploy ổn**: `backtest_optimization_runs` + `backtest_requests`.
- **Giữ 2 cơ chế key**: single = run_id (lịch sử nhiều run), subscription = sub_id (cache 1 doc/sub).
- **Plan mode**: `/ck:plan --tdd`.

## Touchpoints

### Xóa
- Route: `run_optimization`, `get_optimization` (`app/routes/backtest.py`).
- DTO/service: `RunOptimizationCommand`, `BacktestCommandService.optimize`, `OptimizationSummaryResponse`, `GetOptimizationQuery`.
- Domain/infra: `GridOptimizationAppService`, `OptimizationConfig`, `OptimizationResult`, `OptimizationRepository` + provider, `COLLECTION_BACKTEST_OPTIMIZATION_RUNS`.
- Queue: `backtest_requests` collection, `BacktestRequestRepository`, `BacktestRequestWorker`, `start/stop_backtest_worker`, `BacktestWorkerProvider` (phần worker).
- `ENABLE_JOBS` gating cho backtest worker.
- Tests: `test_grid_optimization_isolation.py`, `test_backtest_request_service.py`, `tests/http/backtest/run-optimization.bru`; cập nhật openapi/route snapshots.

### Thêm/Sửa
- `BacktestExecutionService` (hoặc tái dùng `backtest_dispatch`): tạo run doc upfront (run_id cố định) → spawn task → return run_id. Engine upsert cùng run_id.
- `app/routes/backtest.py`: `/run` đổi sang direct-task; `run-all` fan-out task.
- `main_extensions.py`: thêm startup sweep (`running`→`failed` cho orphan) + graceful shutdown cancel task; bỏ worker start/stop.
- `run_subscription`: `persist_results=True` + save orders/trades.
- `app.state`: set giữ reference task đang chạy.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Fire-and-forget task bị GC | Giữ reference trong `app.state` set; done-callback log + discard. |
| Task lỗi im lặng | Wrap try/except, **luôn** update run doc status (kể cả exception). |
| Restart mid-run → mất in-flight | Startup sweep mark `running`→`failed` (one-shot lúc boot); graceful shutdown cancel + mark failed. Chấp nhận vì manual → bấm lại. |
| Không cap + pool(50) cạn khi chạy ồ ạt | User tự quản (đã chấp nhận). Tài liệu hóa knob `MONGODB_MAX_POOL_SIZE`. |
| Orphan data sau xóa optimize | `backtest_optimization_runs` collection mồ côi → drop (an toàn, FE không dùng). |

## Success criteria

- 1 entry rõ ràng: `/backtest/run` (single) + `run-all-backtests` (fan-out), cả 2 direct-task.
- Bấm backtest → poll `/backtest/{run_id}` → completed → có metrics + equity + orders + trades trong DB.
- Subscription backtest review được trades.
- Không còn `backtest_requests`, `BacktestRequestWorker`, `/optimize`, coupling `ENABLE_JOBS` cho backtest.
- `just test` / `ruff` / `pyright` / `lint-imports` xanh; import-linter contracts giữ nguyên.

## Unresolved questions

Không còn — toàn bộ đã chốt với user (xem "Quyết định cuối"). Các điểm cần plan giải quyết chi tiết:
- Vị trí `BacktestExecutionService` (module mới trong `backtest/` hay mở rộng `backtest_dispatch`) — quyết trong plan theo module boundary.
- Cập nhật FE: enum status + badge mapping + poll logic cho `started/finished/failed`.
- Migration drop 2 collection prod: chạy tay sau verify, hay script có cờ.
