---
phase: 2
title: "Backtest request queue"
status: completed
priority: P1
effort: "8h"
dependencies: [1]
---

# Phase 2: Backtest request queue

## Overview

Thay đường backtest enqueue từ APScheduler `bt:*` one-off jobs sang **Mongo collection `backtest_requests` + poll-loop worker trên app**. bff chỉ INSERT request doc (pure DB write, không cần scheduler); app có `BacktestRequestWorker` poll `pending` → chạy backtest → ghi kết quả + set `done`. Đây là điều kiện để bff bỏ JobScheduler khỏi DI (Phase 4) và để single backtest cũng đi qua queue (Phase 5).

**KHÔNG dùng RabbitMQ/Kafka** — Mongo là queue, đúng pattern poll-loop đã có (`StrategyReconcileService`, `WsSubscriptionManager`).

## Requirements

- Functional:
  - Collection `backtest_requests` doc shape: `{_id, kind: "single"|"subscription", sub_id?, strategy_code?, config?, status: "pending"|"running"|"done"|"failed", requested_at, started_at?, finished_at?, error?}`.
  - `BacktestRequestRepository` (infrastructure): `enqueue(request) -> id`, `claim_next() -> request | None` (atomic find-one-and-update pending→running), `mark_done(id)`, `mark_failed(id, error)`, `ensure_indexes()`, `get(id)`.
  - `BacktestRequestWorker` (đặt ở đâu — xem Architecture): poll mỗi N giây, `claim_next`, dispatch theo `kind`, ghi kết quả qua `BacktestRepository` (đã có `save_for_subscription` + `save`), set status.
  - `run_all_backtests` handler: thay `scheduler.add_one_off_job` bằng `bt_request_repo.enqueue(kind="subscription", sub_id=...)` cho mỗi sub. Drop `JobScheduler` dep.
  - `RunBacktestHandler` (single): thay vì chạy đồng bộ + trả `BacktestResult`, đổi thành enqueue `kind="single"` + trả `{request_id}`. (FE poll — Phase 5.) **Giữ logic replay** nhưng di chuyển vào worker dispatch path (DRY: worker single-dispatch tái dùng cùng engine-setup code của handler cũ).
  - Gỡ `rekey_backtest_job_refs` + `recover_orphan_jobs`-cho-bt khỏi liên quan `bt:*` (APScheduler bt jobs không còn tạo mới). Stale recovery cho `backtest_requests` thay bằng worker reclaim `running` quá hạn (giống `mark_stale_running_as_failed`).
- Non-functional:
  - Worker idempotent: claim atomic (`find_one_and_update`), 2 app instance (VPS+local) không double-run cùng request.
  - Worker per-request isolation: 1 request fail không chặn request khác (try/except mỗi vòng).

## Architecture

### Worker placement (layer)

Backtest execution logic sống ở `pocketquant-backtest`. Worker điều phối nên đặt ở `pocketquant-backtest` (vd `backtest/workers/backtest_request_worker.py`) — cùng tầng với engine, dùng repo từ infrastructure. App lifespan start worker như task (giống reconcile). Worker KHÔNG được import `pocketquant.app`/`pocketquant.bff` (import-linter).

`BacktestRequestRepository` → `pocketquant-infrastructure/persistence/repositories/` (mọi repo ở infra theo CLAUDE.md).

### Queue claim (atomic, distributed-safe)

```
claim_next():
  findOneAndUpdate(
    {status: "pending"},
    {$set: {status: "running", started_at: now}},
    sort={requested_at: 1}, returnDocument: AFTER
  )
```
Mongo atomic ⇒ 2 worker không nhặt trùng. Không cần lock layer (giống MongoDBJobStore racing pattern hiện có).

### Single-backtest dispatch reuse

`RunBacktestHandler` hiện tự dựng `PaperBroker` + `inject_prepared_strategy` + `BacktestAppService.run` (`run/handler.py:67-96`). Trích phần này thành hàm dùng chung mà cả handler-cũ-đường-enqueue lẫn worker-single-dispatch gọi. Subscription-dispatch tái dùng `subscription_backtest_jobs.run_subscription_backtest` logic (`subscription_backtest_jobs.py:48`) — chuyển từ "job function đọc module-global container" sang "worker method nhận deps qua DI".

### Status doc cho FE poll

`run_all` hiện đã ghi `backtest_repo.upsert_status(sub_id, "running")` rồi `save_for_subscription`. Single-backtest cần status doc tương đương để FE poll. Quyết định khi implement: FE single poll theo `request_id` (đọc `backtest_requests.get`) hay theo `sub_id`/result doc. Single backtest không gắn subscription ⇒ **poll theo `request_id`** là sạch nhất; trả `BacktestResult` embedded trong request doc khi `done`.

## Related Code Files

- Create: `packages/pocketquant-infrastructure/.../repositories/backtest_request_repository.py`
- Create: `packages/pocketquant-backtest/src/pocketquant/backtest/workers/backtest_request_worker.py`
- Create: `packages/pocketquant-backtest/src/pocketquant/backtest/workers/backtest_dispatch.py` (shared single+subscription dispatch, DRY)
- Modify: `packages/pocketquant-backtest/.../handlers/run_all_backtests/handler.py` — enqueue thay add_one_off_job; drop JobScheduler dep
- Modify: `packages/pocketquant-backtest/.../handlers/run/handler.py` — enqueue single + trả request_id; di chuyển replay vào dispatch
- Modify: `packages/pocketquant-app/.../main_extensions.py` — add `start_backtest_worker`/`stop_backtest_worker`; gỡ `rekey_backtest_job_refs` (bt jobs hết tạo); cập nhật `recover_orphan_jobs` nếu chỉ phục vụ bt
- Modify: `packages/pocketquant-app/.../main.py` — gọi start/stop worker trong lifespan
- Modify: `packages/pocketquant-app/.../di/` — provider cho `BacktestRequestRepository` + worker
- Modify: `main_extensions.py:_REPO_TYPES` — thêm `BacktestRequestRepository` vào ensure_indexes
- Read context: `subscription_backtest_jobs.py`, `run/handler.py`, `run_all_backtests/handler.py`, `backtest_repository.py`, `strategy_reconcile_service.py` (poll-loop pattern)

## Implementation Steps

1. **TEST FIRST** — `tests/backtest_test/test_backtest_request_queue.py`:
   - `enqueue` → doc `pending`; `claim_next` atomic flip→`running`, 2 lần claim liên tiếp lần 2 trả None (đã claimed).
   - worker dispatch subscription → `backtest_runs` có result + status `completed`; request → `done`.
   - worker dispatch single → request doc chứa `BacktestResult` + `done`.
   - request fail → status `failed` + error; request kế vẫn chạy (isolation).
   - stale `running` quá hạn → reclaim.
2. Tạo `BacktestRequestRepository` + `ensure_indexes` (index `status`, `requested_at`).
3. Trích `backtest_dispatch.py`: `run_single(deps, config)` + `run_subscription(deps, sub_id)` từ logic hiện có (handler single + subscription_backtest_jobs). Giữ C1/C2/M1 fixes (synthetic_id, TOCTOU re-check) trong subscription path.
4. Tạo `BacktestRequestWorker.run()` poll-loop (mirror `StrategyReconcileService.run`): claim→dispatch→mark. Per-vòng try/except. Reclaim stale running đầu mỗi tick.
5. Sửa `run_all_backtests/handler.py`: loop subs → `enqueue(kind="subscription", sub_id)`; drop `JobScheduler`. Trả `{request_ids}` (giữ key `job_ids` cho FE back-compat? — xác nhận FE `strategy-api.ts:54` đọc `job_ids`; giữ tên `job_ids` để 0 FE change phần run_all).
6. Sửa `run/handler.py`: enqueue `kind="single"` + config → trả `{request_id}`.
7. Wire worker vào app lifespan: `start_backtest_worker` sau `start_reconcile_loop`, gated `enable_jobs`; `stop` trước container.close.
8. Gỡ `rekey_backtest_job_refs` call + hàm (bt:* jobs không còn tạo). Migration 1 lần: drain `apscheduler_jobs` bt:* tồn dư → re-enqueue sang `backtest_requests` HOẶC để worker bỏ qua (xác nhận: có job bt:* in-flight lúc deploy không? nếu prod sạch thì chỉ xóa code).
9. `ensure_indexes` thêm `BacktestRequestRepository`.
10. `just test-pkg backtest` + `just test-pkg app` xanh; lint + types.

## Success Criteria

- [ ] `backtest_requests` collection + repo + atomic claim hoạt động; test xanh.
- [ ] Worker chạy trong app lifespan, gated `enable_jobs`; poll→dispatch→status.
- [ ] `run_all_backtests` enqueue (không gọi scheduler); `run` single enqueue + trả request_id.
- [ ] Không còn tạo APScheduler `bt:*` job mới; `rekey_backtest_job_refs` gỡ.
- [ ] Distributed-safe: 2 worker không double-run (atomic claim test).
- [ ] backtest + app suite xanh; lint + types clean.

## Risk Assessment

- **In-flight `bt:*` jobs lúc deploy**: nếu prod có job bt:* đang chờ, gỡ rekey làm chúng drop. Mitigation: trước deploy đếm `db.apscheduler_jobs.countDocuments({_id:/^bt:/})`; nếu >0, drain script re-enqueue sang backtest_requests. Hỏi user nếu prod có job treo.
- **Single backtest đổi từ sync→async**: breaking cho bất kỳ caller curl nào dựa vào response synchronous. FE sửa ở Phase 5; Bruno/curl docs (`tests/http`, README) cập nhật.
- **Worker + scheduler cùng `enable_jobs` gate**: app test (`enable_jobs=False`) không chạy worker — OK. Nhưng integration test backtest cần worker → bật flag hoặc gọi dispatch trực tiếp (không qua loop).
- **CPU-heavy replay trên app**: app giờ gánh mọi backtest compute cạnh live trading. Nếu replay nặng block event-loop, ảnh hưởng reconcile/WS tick. Mitigation: worker chạy 1 request/lần (max_instances=1 semantics); nếu cần, để worker `await asyncio.sleep(0)` giữa bước nặng. Theo dõi ở Phase 7.
- **DRY dispatch trích sai**: di chuyển replay dễ rớt C1/C2/M1 fix. Mitigation: characterization test giữ behavior trước khi trích.
