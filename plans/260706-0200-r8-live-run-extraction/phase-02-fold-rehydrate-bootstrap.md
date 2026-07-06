# Phase 2 — Fold rehydrate → StrategyReconcileAppService.bootstrap()

**Context:** [plan.md](./plan.md) · [phase-01](./phase-01-relocations.md)
**Priority:** P2 · **Status:** Done · **Track:** structure (dedup DRY, thin driver)

## Overview

`rehydrate_strategies_from_subscriptions` (`main_extensions.py:121-167`) là bản sao gần-nguyên của `StrategyReconcileAppService._ensure_instances`. Fold thành method `bootstrap()` trên reconcile service (DRY). App gọi `svc.bootstrap()` (unconditional) trước `create_task(svc.run())` (gated `enable_jobs`).

## Key insights

- **Nuance behavior phải giữ:** rehydrate chạy **luôn** (lifespan:64, không gate); reconcile loop gate `enable_jobs` (`start_reconcile_loop:232`). → `bootstrap()` gọi unconditional; `create_task(run())` giữ gate.
- `bootstrap()` = chạy `_ensure_instances(await sub_repo.list_all())` một lần (đúng logic rehydrate). Tránh nhân đôi code load-per-sub.
- App resolve `StrategyReconcileAppService` từ container (đã có ở `start_reconcile_loop`) — nhưng bootstrap cần chạy KỂ CẢ khi `enable_jobs=false`. → resolve svc ở bước riêng, gọi bootstrap luôn.

## Related code files

- `src/pocketquant/engine/live/strategy_reconcile_app_service.py` — thêm `async def bootstrap()`.
- `src/pocketquant/app/main_extensions.py` — xoá `rehydrate_strategies_from_subscriptions` (121-167); thêm `bootstrap_live_instances(container)` mỏng gọi `svc.bootstrap()`; `start_reconcile_loop` giữ gate + create_task.
- `src/pocketquant/app/main.py:19,64` — đổi call `rehydrate_strategies_from_subscriptions` → `bootstrap_live_instances`.

## Implementation steps

1. Thêm `async def bootstrap(self) -> None` vào `StrategyReconcileAppService`: `subs = await self._sub_repo.list_all(); await self._ensure_instances(subs)`. Log `live_instances_bootstrapped` (giữ semantics `strategies_rehydrated`).
2. `main_extensions.py`: xoá hàm `rehydrate_strategies_from_subscriptions` + import không dùng (`STRATEGY_REGISTRY`/`StrategyConfig` nếu chỉ hàm đó dùng). Thêm:
   ```python
   async def bootstrap_live_instances(container: AsyncContainer) -> None:
       svc = await container.get(StrategyReconcileAppService)
       await svc.bootstrap()
   ```
3. `main.py`: import + gọi `bootstrap_live_instances(container)` thay `rehydrate_...` (giữ NGUYÊN vị trí — sau `seed_tracked_symbols`, trước `start_background_jobs`; đảm bảo trước `start_reconcile_loop`).
4. `pytest` — cập nhật test nào ref `rehydrate_strategies_from_subscriptions` (nếu có) → gọi qua svc.bootstrap()/bootstrap_live_instances.
5. Gate xanh (test/ruff/pyright/lint-imports).

## Todo

- [x] `bootstrap()` trên reconcile service (reuse `_ensure_instances`)
- [x] Xoá `rehydrate_...` + thêm `bootstrap_live_instances` wrapper
- [x] Rewire `main.py` call site (giữ thứ tự lifespan)
- [x] Cập nhật test ref rehydrate (nếu có)
- [x] Gate xanh

## Success criteria

- `grep -rn "rehydrate_strategies_from_subscriptions"` = 0.
- Startup: instances load per subscription y như cũ (kể cả `enable_jobs=false`). Reconcile loop vẫn gate `enable_jobs`.
- 560 test + 8 contract + ruff + pyright xanh.

## Risk assessment

- **Bootstrap chạy khi enable_jobs=false:** đúng ý (rehydrate cũ cũng unconditional). KHÔNG gate bootstrap.
- **Thứ tự lifespan:** bootstrap PHẢI trước `start_reconcile_loop` (khỏi tick đầu warn missing_instance). Giữ vị trí call cũ.
- **Test coupling:** một số test có thể gọi `rehydrate_...` trực tiếp → chuyển sang `svc.bootstrap()`.

## Next steps

→ Phase 3 (TradeRepository). Kết thúc track structure; app driver giờ = inject + bootstrap + create_task + cancel.
