---
phase: 3
title: "Control-plane instance lifecycle"
status: completed
priority: P1
effort: "6h"
dependencies: [1, 2]
---

# Phase 3: Control-plane instance lifecycle

## Overview

Đóng nốt 3 write-path còn dính RAM để bff = 100% Mongo write. Hiện `add_symbol` `load_strategy()` vào RAM, `remove_symbol`/`delete` `unload_strategy()`. Sau Phase 3:
- `add_symbol`/`remove_symbol`/`delete` handler chỉ ghi Mongo (persist/delete sub doc). Drop `StrategyAppService` dep.
- **App control-plane sở hữu instance lifecycle**: reconcile loop (hoặc loop song hành) load instance còn thiếu cho sub tồn tại, unload orphan instance cho sub đã xóa.

Sau Phase 2, `remove_symbol`/`delete` đã mất coupling `scheduler.remove_job` (bt:* hết tồn tại). Phase 3 chỉ còn gỡ `unload_strategy` + `load_strategy`.

## Requirements

- Functional:
  - `add_symbol`: giữ tracked-symbol check + registry validate (vẫn cần — fail sớm cho user) + persist `Subscription(desired_state="stopped")`. **Bỏ** `load_strategy`. Drop `StrategyAppService` dep.
  - `remove_symbol`: chỉ `bt_repo.delete_by_subscription` + `sub_repo.delete`. **Bỏ** `unload_strategy`. Drop `StrategyAppService` + `JobScheduler` dep (scheduler.remove_job đã vô nghĩa sau Phase 2).
  - `delete`: chỉ `bt_repo.delete_by_strategy_code` + `sub_repo.delete_by_strategy_code`. **Bỏ** `unload_strategy` + scheduler. Drop deps.
  - App control-plane **load** instance: với mỗi sub `list_all()` mà `get_strategy(sub.id) is None` và template tồn tại trong registry → `load_strategy`. (Hiện chỉ `rehydrate` lúc boot làm; cần làm liên tục để add_symbol-trên-bff được app nhặt.)
  - App control-plane **unload** orphan: instance trong RAM keyed bằng sub.id mà không còn sub doc → `unload_strategy`. **KHÔNG** đụng synthetic backtest instances (id không phải sub.id).
- Non-functional:
  - Load/unload idempotent, lock-safe (StrategyAppService `_lock` đã có).
  - KHÔNG clobber synthetic-id backtest instances (worker Phase 2 tạo/hủy synthetic id riêng).

## Architecture

### Ai làm load/unload — mở rộng reconcile hay loop riêng?

Hiện `StrategyReconcileService._converge_one` **cố ý KHÔNG load** (`strategy_reconcile_service.py:100-117` — "reconcile never loads"). SP1 tách "instance creation" (rehydrate/add_symbol) khỏi "run-state convergence" (reconcile) có chủ đích.

Sau Phase 3, add_symbol không còn load ⇒ phải có chỗ khác load. 2 lựa chọn (chốt khi implement, mặc định A):

- **(A) Mở rộng reconcile**: thêm bước "ensure instance" trước converge. Reconcile giờ sở hữu cả lifecycle lẫn run-state. Đơn giản hơn (1 loop), nhưng đảo quyết định SP1 "reconcile never loads" — cập nhật docstring + lý do.
- **(B) Loop lifecycle riêng**: `StrategyLifecycleService` load missing + unload orphan; reconcile giữ nguyên chỉ converge run-state. Tách concern sạch hơn, thêm 1 loop.

**Mặc định (A)** theo KISS — 1 loop, ít task. Reconcile mỗi tick: (1) load instance thiếu cho sub có template hợp lệ, (2) unload orphan (instance keyed sub.id không có sub doc), (3) converge run-state như cũ. Docstring/test SP1 "never loads" phải sửa — đây là thay đổi có chủ đích do SP3, không phải regression.

### Orphan-unload không đụng synthetic backtest id

Backtest worker (Phase 2) load strategy dưới `synthetic_id` (vd `sub_id + suffix` hoặc `strategy_code` cho single). Reconcile orphan-unload chỉ được unload instance mà id **khớp 1 sub.id đã-từng-tồn-tại nhưng giờ mất doc**. An toàn nhất: chỉ unload khi `instance_id in {known sub.ids trước đó}` HOẶC id match Subscription.deterministic_id shape. Synthetic id (suffix khác) bỏ qua. Verify `load_strategy_for_backtest` tạo synthetic_id shape gì để exclude chính xác.

→ Đơn giản & an toàn: reconcile chỉ iterate `sub_repo.list_all()` (như hiện tại) để LOAD; phần UNLOAD orphan so RAM-keys vs sub-ids, nhưng **chỉ unload key trông giống sub.id** (deterministic_id format), không phải mọi key lạ. Tránh giết synthetic backtest đang chạy.

### add_symbol validation giữ lại

`add_symbol` bỏ load nhưng GIỮ: tracked-symbol exists check + registry template check. Lý do: fail sớm cho user (400/404) thay vì persist sub rác rồi reconcile mới phát hiện. Đây là pure DB read (`tracked_repo.exists`) + in-memory registry lookup — bff-safe (không đụng StrategyAppService RAM).

## Related Code Files

- Modify: `packages/pocketquant-trading/.../handlers/strategy/add_symbol/handler.py` — bỏ load + StrategyAppService dep; giữ checks + persist
- Modify: `packages/pocketquant-trading/.../handlers/strategy/remove_symbol/handler.py` — bỏ unload + scheduler; chỉ delete bt + sub
- Modify: `packages/pocketquant-trading/.../handlers/strategy/delete/handler.py` — bỏ unload + scheduler; chỉ cascade delete docs
- Modify: `packages/pocketquant-execution/.../app_services/strategy_reconcile_service.py` — thêm ensure-instance (load missing) + unload-orphan; sửa docstring "never loads"
- Modify: DI `pocketquant-app/.../di/handlers.py` — cập nhật constructor deps (drop StrategyAppService khỏi add/remove/delete)
- Read context: `add_symbol/handler.py`, `remove_symbol/handler.py`, `delete/handler.py`, `strategy_reconcile_service.py`, `strategy_app_service.py` (get_strategy/load/unload), `backtest_strategy_loader.py` (synthetic_id shape), `subscription/entities.py` (deterministic_id)

## Implementation Steps

1. **TEST FIRST** — `tests/trading_test/test_handlers_pure_declarative.py`:
   - `add_symbol` → sub persisted `desired_state="stopped"`; `StrategyAppService` KHÔNG được gọi (handler không có dep / mock không invoked); instance NOT loaded bởi handler.
   - `remove_symbol` → sub doc + bt doc xóa; KHÔNG gọi unload/scheduler.
   - `delete` → mọi sub + bt theo template xóa; KHÔNG gọi unload/scheduler.
2. **TEST FIRST** — `tests/execution_test/test_reconcile_instance_lifecycle.py`:
   - sub tồn tại + no RAM instance + template hợp lệ → reconcile load instance (`get_strategy(sub.id)` not None sau 1 tick).
   - sub tồn tại + template unknown → KHÔNG load, warn (như rehydrate skip).
   - sub bị xóa + RAM còn instance keyed sub.id → reconcile unload.
   - synthetic backtest instance (id khác sub.id shape) đang trong RAM → reconcile KHÔNG unload nó (anti-clobber).
   - converge run-state vẫn hoạt động sau khi thêm load/unload (regression SP1).
3. Sửa reconcile `_reconcile`: thêm ensure-instance trước converge (load missing cho sub có template); thêm unload-orphan (so RAM keys giống-sub-id vs sub-ids hiện tại). Cập nhật docstring (bỏ "never loads", giải thích lý do SP3).
4. Sửa `add_symbol`: drop StrategyAppService import + dep; chỉ giữ checks + `sub_repo.add`.
5. Sửa `remove_symbol`: drop StrategyAppService + JobScheduler; chỉ `bt_repo.delete_by_subscription` + `sub_repo.delete`.
6. Sửa `delete`: drop StrategyAppService + JobScheduler; chỉ cascade delete docs.
7. Cập nhật DI `handlers.py` constructor wiring (Phase 4 verify resolve, nhưng deps đổi ở đây).
8. `rehydrate_strategies_from_subscriptions` (boot): giữ — nó load lúc boot; reconcile load tiếp sau đó. Hoặc xác nhận reconcile-tick-1 đủ thay rehydrate (KISS: giữ cả 2, rehydrate cho cold-start nhanh, reconcile cho liên tục).
9. `just test-pkg trading` + `just test-pkg execution` + `just test-pkg app` xanh; lint + types.

## Success Criteria

- [ ] add/remove/delete handler 0 đụng StrategyAppService/JobScheduler — pure Mongo. Test xác nhận.
- [ ] Reconcile load instance còn thiếu cho sub hợp lệ trong ≤1 tick.
- [ ] Reconcile unload orphan (sub đã xóa) nhưng KHÔNG đụng synthetic backtest instance.
- [ ] Run-state convergence SP1 vẫn pass (regression).
- [ ] trading + execution + app suite xanh; lint + types clean.

## Risk Assessment

- **Đảo quyết định SP1 "reconcile never loads"**: có chủ đích — SP3 cần load liên tục vì add_symbol không còn load. Đây là new context (split process), không phải audit-flip. Cập nhật docstring + ghi lý do. (Tuân review-audit rule: context đã đổi → revise hợp lệ.)
- **Clobber synthetic backtest instance khi unload orphan** (CAO): reconcile unload nhầm instance backtest đang chạy → backtest fail. Mitigation: chỉ unload key match sub.id-shape (deterministic_id); verify synthetic_id shape ở `backtest_strategy_loader.py` để exclude. Test anti-clobber bắt buộc.
- **add_symbol persist sub nhưng reconcile chưa kịp load → run ngay fail**: user add rồi start ngay, reconcile tick chưa load. Nhưng start chỉ set desired=running; reconcile tick sau load + converge. Độ trễ ≤1 tick (5s) — đúng declarative model. Document.
- **Race rehydrate (boot) vs reconcile (tick-1) cùng load**: `load_strategy` có `_lock` + early-return nếu `config.id in self._strategies` (`strategy_app_service.py:95`). Idempotent — an toàn.
- **add_symbol mất registry/tracked check nếu lỡ tay bỏ**: giữ lại 2 check này (chỉ bỏ load). Test verify 400/404 vẫn raise.
