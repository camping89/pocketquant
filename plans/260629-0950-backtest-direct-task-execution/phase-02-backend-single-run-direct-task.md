---
phase: 2
title: "Backend single-run direct-task"
status: done
effort: ""
---

# Phase 2: Backend single-run direct-task

## Overview

`POST /backtest/run` chuyển từ enqueue-into-queue sang direct `asyncio.create_task`: tạo run doc `status=started` upfront (run_id route-allocated) → spawn task chạy engine → persist đủ → `finished`/`failed`. Đổi status vocab. Áp dụng red-team C1, C2, C5, H6, M1, M2. Engine logic GIỮ, chỉ đổi trigger + run_id threading + status literal + error handling.

## Requirements

- Functional: `POST /backtest/run` trả 202 `{run_id}` ngay; doc `started` tồn tại trước khi engine xong; FE poll `GET /backtest/{run_id}` thấy `started`→`finished`/`failed`.
- Functional (C2): run_id route-allocated truyền XUYÊN SUỐT → run doc `_id` + orders.run_id + trades.run_id đều = id đó. KHÔNG để engine tự sinh id thứ 2.
- Functional (C1): error handling KHÔNG dựa vào exception propagate — `run()` catch+return; `_execute_and_persist` phải inspect `result.status` HOẶC `run()` đổi để re-raise. Pick: inspect return (ít phá contract hơn).
- Functional (C5): đổi mọi status filter `"completed"` → `"finished"` trong repo queries.
- Non-functional (M2): task giữ reference trong `app.state.backtest_tasks`; shutdown drain-with-timeout (KHÔNG cancel-then-await-persist); guard `mark_failed` chống disconnected client.
- Non-functional (H6): SỬA premise sai — engine KHÔNG yield mỗi bar (`YIELD_INTERVAL=100`, sleep chỉ khi replay_speed>0). GIẢM `YIELD_INTERVAL` 100 → 10 (validated) để WS/reconcile/health cùng process không bị starve bởi 1.1M-bar run. <!-- Updated: Validation Session 1 - YIELD_INTERVAL 100→10 -->
- Non-functional (validated): thêm endpoint `GET /backtest/{run_id}/trades` (join `trade_repo.list_by_run`) song song `/equity` — phase 5 FE cần để hiện closed trades. Có thể làm ở phase 2 (backend) hoặc đầu phase 5. <!-- Updated: Validation Session 1 - trades endpoint bắt buộc -->
- Non-functional (C4): KHÔNG cap (user quyết). Document rõ rủi ro pool(50) dùng chung live engine — task chạy có thể starve live order persistence; user tự quản.
- Constraint: import-linter — execution service ở `backtest/`, spawn task + app.state ở `app/`.

## Architecture

### Trigger mới (single)
```
POST /backtest/run (app/routes/backtest.py)
  → cmd_svc.run(cmd):
      run_id = generate_id()
      backtest_repo.save( BacktestResult.started(run_id, config_snapshot) )   # status=started, zero metrics
      task = asyncio.create_task( execution_svc.execute_and_persist(run_id, config) )
      app.state.backtest_tasks.add(task); task.add_done_callback(app.state.backtest_tasks.discard)
      return {"run_id": run_id}                                                # 202
```

### execute_and_persist (C1 — inspect return, không dựa exception)
```
async def execute_and_persist(run_id, config):
    try:
        result = await run_single(deps, config, run_id=run_id)   # engine catch nội bộ, RETURN result
        if result.status == "failed":                            # C1: run() không raise → inspect
            log failed (đã persist failed doc bởi engine)
    except Exception as e:                                        # chỉ bắt lỗi NGOÀI engine (vd save started doc race)
        await backtest_repo.mark_failed(run_id, str(e))
```

### C2 — run_id threading
`BacktestAppService.run(config, run_id=None)`: line 72 đổi `run_id = run_id or generate_id_str()`. Truyền vào `BacktestResultCollector(run_id=run_id)` + `finalize(run_id=...)`. `run_single(deps, config, run_id=None)` nhận + forward. → started doc (route) và finished doc + orders + trades CÙNG id.

### M1 — BacktestResult.started() factory
```
@classmethod
def started(cls, run_id, config_snapshot):
    now = datetime.now(UTC)
    return cls(id=run_id, strategy_code=config_snapshot["strategy_code"],
               config_snapshot=config_snapshot, metrics=BacktestMetrics.empty(),  # full zero, 15 fields
               equity_curve=[], started_at=now, completed_at=now, status="started", ...)
```
`from_mongo` round-trip OK (metrics non-null). `BacktestMetrics.empty()` đã tồn tại (dùng ở grid optimize cũ).

### Status vocab + C5 filters
| Cũ | Mới | Điểm chạm |
|----|-----|-----------|
| running | started | route save upfront; (subscription in-progress xóa ở phase 4) |
| completed | finished | backtest_app_service.py:121; result_collector.finalize default; **backtest_repository.py:65,80** (C5 query filter) |
| failed | failed | giữ |

### M2 — graceful shutdown
`main.py` lifespan: `app.state.backtest_tasks = set()` init. Shutdown: `await asyncio.wait(tasks, timeout=N)` để in-flight persist xong (vài giây), KHÔNG cancel-then-mark_failed (CancelledError là BaseException, lọt except Exception; await-during-cancel unreliable). Drain TRƯỚC `container.close()` (Database.disconnect). Doc còn `started` sau timeout → để sweep nhẹ xử lý.

### Startup sweep nhẹ (C1/M2 mitigation, KHÔNG bỏ hẳn)
Giữ 1 sweep tối giản lúc boot: `update_many({status:"started"}, {status:"failed", error_message:"interrupted_by_restart"})`. Single-process → không run `started` hợp lệ nào sống qua restart. Thay cho `recover_stale_backtests` cũ (rename filter `running`→`started`, bỏ threshold).

## Related Code Files

- Create: `src/pocketquant/backtest/backtest_execution_service.py` — `execute_and_persist(run_id, config)` (C1 inspect return); dùng `BacktestDispatchDeps` + `run_single`.
- Modify: `src/pocketquant/backtest/backtest_command_service.py` — `run()` save-started + spawn task (xóa enqueue). Xóa optimize/run_all (phase 3).
- Modify: `src/pocketquant/backtest/workers/backtest_dispatch.py` — `run_single(deps, config, run_id=None)` forward id.
- Modify: `src/pocketquant/backtest/engine/backtest_app_service.py` — `run(config, run_id=None)`: line 72 `run_id or generate`; line 84/117/148 dùng id; status `completed`→`finished` (line 121).
- Modify: `src/pocketquant/backtest/engine/result_collector.py` — `finalize(status="finished")` default.
- Modify: `src/pocketquant/core/domain/backtest/entities.py` — `BacktestResult.started()` factory; comment status `started/finished/failed`.
- Modify: `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py` — `mark_failed(run_id, msg)`; **filter `:65` + `:80` `completed`→`finished` (C5)**; sweep rename `started` (M2).
- Modify: `src/pocketquant/backtest/backtest_query_service.py` — `get_result` poll (đã có); DTO status literal. (request-status method xóa ở phase 3.)
- Modify: `src/pocketquant/app/routes/backtest.py` — `/run` trả 202 `{run_id}` (giữ shape).
- Modify: `src/pocketquant/app/main.py` + `main_extensions.py` — `app.state.backtest_tasks` init; shutdown drain-with-timeout; sweep rename; (xóa worker start/stop ở phase 3).
- Modify (tests): cập nhật characterization status `completed`→`finished`.

## Implementation Steps

1. **TDD red**: cập nhật characterization status mới → đỏ.
2. `BacktestMetrics.empty()` verify tồn tại + đủ 15 field zero. `BacktestResult.started()` factory.
3. C2: `run(config, run_id=None)` line 72 conditional; thread vào collector + finalize. `run_single(..., run_id=None)`.
4. Status `completed→finished`: engine + result_collector + **repo filter :65/:80 (C5)**.
5. `backtest_repository.mark_failed(run_id, msg)`; sweep rename `started` + bỏ threshold.
6. `backtest_execution_service.execute_and_persist` (C1: inspect `result.status`, except chỉ cho lỗi ngoài engine).
7. `command_service.run()`: save-started → spawn task (execution svc) → return run_id.
8. `main.py`: `app.state.backtest_tasks` set; shutdown `asyncio.wait(timeout)` drain trước container.close; sweep call lúc boot.
9. Route `/run` giữ 202 `{run_id}`.
10. **TDD green**: characterization + route smoke → xanh. Verify run_id invariant (C2) + list filter (C5).
11. `ruff`+`pyright`+`lint-imports` → xanh (execution service KHÔNG import fastapi).

## Success Criteria

- [x] `POST /backtest/run` → 202 `{run_id}` (key `request_id` giữ nguyên cho FE); doc `started` tức thì; xong → `finished` + metrics + equity + orders + trades.
- [x] C2: route run_id == run doc `_id` == orders.run_id == trades.run_id (characterization + direct-task test assert).
- [x] C1: engine lỗi → doc `failed` + error_message (execute_and_persist inspect `result.status` + outer guard mark_failed; test `test_engine_failure_marks_failed_via_inspect_not_exception`).
- [x] C5: `list_by_strategy_code`/`get_best_by_metric` filter `finished`.
- [x] M1: `BacktestResult.started()` zero metrics; round-trip `from_mongo` OK (test assert).
- [x] M2: shutdown `drain_backtest_tasks` (await, không cancel); `mark_orphaned_started_as_failed` boot sweep (test assert).
- [x] H6: `YIELD_INTERVAL` 100→10.
- [x] Endpoint `GET /backtest/{run_id}/trades` (BacktestQueryService.list_trades) — làm ở phase 2.
- [x] `ruff`/`pyright`/`lint-imports`(7) xanh; DI scope KHÔNG đổi (mọi provider Scope.APP).

## Notes — deferred test breakage (intentional)

`cmd_svc.run` đổi signature (queue enqueue → save-started + return tuple) làm 2 test queue ĐỎ tạm thời:
`test_backtest_request_queue.py`, `test_backtest_request_service.py`. Cả 2 nằm trong danh sách XÓA ở phase 3 (queue machinery). Full `pytest` xanh verify sau phase 4 khi queue/optimize/run-all đã gỡ.

## Risk Assessment

- **Risk (C1)**: nếu impl vẫn dựa exception → mark_failed dead code. Mitigation: inspect `result.status`; test engine-error path.
- **Risk (C2)**: quên thread run_id vào collector/finalize → 2 doc. Mitigation: characterization assert invariant; line 72 conditional.
- **Risk (C4)**: no cap → cạn pool(50) starve live trading. Mitigation: user chấp nhận; document knob `MONGODB_MAX_POOL_SIZE`; nêu rõ rủi ro trong code comment chỗ spawn.
- **Risk (H6)**: event loop starve bởi 1.1M-bar run (yield mỗi 100 bar). Mitigation: document; cân nhắc giảm `YIELD_INTERVAL` xuống ~10; theo dõi WS/reconcile/health latency.
- **Risk (M1)**: `started` doc metrics rỗng sai shape → poll 500. Mitigation: `BacktestMetrics.empty()` full zero; characterization round-trip assert.
- **Risk (M2)**: cancel mid-write corrupt. Mitigation: drain-with-timeout thay cancel; guard mark_failed chống disconnected; sweep boot dọn orphan.
