# Red Team Adjudication — Backtest direct-task execution plan

3 hostile reviewers (Failure Mode Analyst, Assumption Destroyer, Security/Data-Integrity). 18 raw findings → dedupe → 15. Tất cả có `file:line` evidence (pass evidence filter). Severity: 6 Critical, 6 High, 3 Medium.

## Verified-TRUE plan assumptions (survived)
- `/optimize` không có FE consumer (zero `web/src` refs; chỉ tests/bruno) → xóa an toàn.
- dispatch deps `Scope.APP` singleton → task sống ngoài request KHÔNG hit closed session.
- `backtest_repo.save()` upsert-by-`_id` (replace_one upsert).
- `ContextVar` simulation-time copy per task → concurrent backtests không corrupt nhau/live time.

## Findings & dispositions

| # | Severity | Finding | Disposition | Evidence |
|---|----------|---------|-------------|----------|
| C1 | Critical | `BacktestAppService.run()` catch `Exception` → finalize failed → **return** (không re-raise). Plan's `try/except → mark_failed` là dead code | **Accept** | backtest_app_service.py:144-167 |
| C2 | Critical | `run()` sinh `run_id` nội bộ unconditional (`:72`) + thread vào collector/finalize. Plan chỉ thread vào `run_single` → mismatch: started doc (id A) vs finished doc + orders/trades (id B) | **Accept** | backtest_app_service.py:72,84,117,148; backtest_dispatch.py:92 |
| C3 | Critical | `StrategyCommandService` (engine layer) **hard-deps** `BacktestRequestRepository` (constructor + cascade-delete). Xóa repo → DI fail → **app không boot**. Plan không list file này | **Accept** | strategy_command_service.py:70,75,143,155; di/trading_services.py:15 |
| C4 | Critical | No cap + shared `AsyncMongoClient` pool(50) với LIVE engine. Bar cursor giữ connection suốt replay → N backtest nặng starve live order persistence (`serverSelectionTimeoutMS=5000` → throw) | **User decision** (new evidence) | mongodb.py:44-49; bar_repository.py:191-197; order_app_service.py:47-114 |
| C5 | Critical | `list_by_strategy_code:65` + `get_best_by_metric:80` hardcode filter `status=="completed"`. Đổi sang "finished" → 2 query trả rỗng (history list + best-by-metric chết im) | **Accept** | backtest_repository.py:65,80 |
| C6 | Critical | FE poll-START gate keyed `status==='running'` (`use-subscriptions.ts:23,36`). Vocab mới → poll không bao giờ start. + blanket grep-replace `'running'/'completed'` sẽ phá domain khác (job-history, sync, forward-status) | **Accept** | use-subscriptions.ts:23,36; strategy-card.tsx:18; forward-status-badge.tsx:17; job-history.ts:2 |
| H1 | High | `BacktestConfig` nằm TRONG `optimization/models/backtest_config.py` — dir bị đánh dấu xóa. "Keep BacktestConfig, delete optimization/" tự mâu thuẫn | **Accept** | optimization/models/backtest_config.py:9; dispatch.py:25; backtest_app_service.py:8 |
| H2 | High | `run_subscription` build `BacktestAppService(persist_results=False)` KHÔNG truyền order/trade repo. Chỉ flip `True` → save_many vẫn skip (None-guard) NHƯNG `save(run)` fire → double doc, đụng `save_for_subscription` cache model | **Accept** | backtest_dispatch.py:202-219; backtest_app_service.py:52-53,134-140 |
| H3 | High | Vocab rename KHÔNG migrate existing prod docs. Docs cũ `running/completed` → FE render "none". Cần `update_many` migration, plan chỉ drop 2 collection | **Accept** | backtest_repository.py:171,176; phase-05 (no backfill) |
| H4 | High | Phase 5 drop prod collection trong khi VPS OLD app vẫn write `backtest_requests` (auto-deploy on develop push). Race: drop giữa lúc worker drain → lost request / index lệch | **Accept** | cicd.yml:5,168; backtest_command_service.py:114,166 |
| H5 | High | FE KHÔNG consume single-run path (`/backtest/run`, poll `/backtest/{run_id}`) — grep rỗng. FE chỉ dùng run-all + `/subscriptions/{id}/backtest`. Single-run async machinery (started factory, run_id threading, positions assembly) phục vụ chỉ manual/.http | **User decision** (scope) | web/src grep empty; strategy-api.ts:52-60; backtest_request_worker.py:121-167 |
| H6 | High | Plan claim "yield event loop mỗi bar" SAI. `YIELD_INTERVAL=100` + sleep chỉ khi `replay_speed>0` (backtest default=0). 100 bars CPU giữa mỗi yield → 1.1M bars starve WS feed/reconcile/health | **Accept** (correct premise) | historical_replay_app_service.py:36,96-97; backtest_app_service.py:90-103 |
| M1 | Medium | `BacktestResult.started()` cần full zero `BacktestMetrics` (15 required fields) + non-null `completed_at` placeholder, nếu không `from_mongo` 500 mọi poll. `BacktestMetrics.empty()` đã tồn tại | **Accept** | entities.py:32-33,60-71; backtest_repository.py uses BacktestMetrics.empty |
| M2 | Medium | Shutdown cancel+mark_failed unreliable: `CancelledError` là `BaseException` (lọt `except Exception`); await mark_failed trong lúc cancel + `Database.disconnect` ordering → doc kẹt started + leaked sandbox subs | **Accept** | backtest_app_service.py:144,169-173; mongodb.py:69-72; main.py:80-85 |
| M3 | Medium | Phase 5 re-smoke: memory note nói dùng `/optimize` (sync) cho re-smoke, nhưng plan xóa `/optimize`. Re-smoke mới phải chạy NEW local build (direct-task `/run`, không cần ENABLE_JOBS) + drop dùng explicit conn string (không qua `.env`). `.env.allsafe.bak` vs memory `.env.remote-db.bak` naming | **Accept** | memory prod-resmoke; main_extensions.py:266; phase-05:26-36 |

## Two user-decision items (reverse explicit choices → present, không auto-apply)

**C4 — pool cap.** User trước chọn "no cap, I handle traffic myself". NEW evidence: pool dùng CHUNG với live trading engine cùng process; bar cursor giữ connection suốt replay. "No cap" không chỉ là backtest chậm — mà có thể starve live order persistence (real-money risk). → cần user quyết lại với evidence mới.

**H5 — single-run scope.** FE không dùng single-run. Quyết định: descope single-run FE / coi `/run` là API-only, hay vẫn build full? Ảnh hưởng độ lớn phase 2 + 4.
