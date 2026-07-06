# Phase 6 — Closeout (OKX no-op, docs/roadmap sync)

**Context:** [plan.md](./plan.md) · [phase-05](./phase-05-live-metrics-query-route.md)
**Priority:** P3 · **Status:** Done · **Track:** docs

## Overview

Chốt R8: confirm OKX `subscribe_trades` giữ no-op (comment trỏ future R), sync docs + roadmap, chạy full gate lần cuối.

## Key insights

- OKX `subscribe_trades` (`okx_broker_adapter.py:287-292`) đã no-op với comment "wired at R8". → R8 KHÔNG wire OKX (thiếu demo payload). Cập nhật comment: defer sang R tương lai (vd R9) + lý do (cần demo fill payload để verify snapshot-delta, tránh double-count accFillSz).
- Roadmap R8 row + unresolved question (dòng 82) cần đổi trạng thái.
- `docs/system-architecture.md` live-run section: engine/live giờ có `bootstrap` + `LiveTradeCollector` + `LiveMetricsQueryService`; `BrokerFactory` ở `core.infra.brokers`; Quote/WsSubscription ở `engine.market_data.app_services`. AS-IS.

## Related code files

**Touch:**
- `src/pocketquant/core/infra/brokers/okx/okx_broker_adapter.py:287` — cập nhật comment defer (R8→future).
- `plans/trading-calulation-fix/roadmap.md` — R8 row status `✅` (nếu done) + giải unresolved dòng 82 (OKX emission defer; live-value map GIẢI: `run_id←subscription_id` qua LiveTradeCollector).
- `docs/system-architecture.md` — live-run / engine.live / broker section AS-IS.
- `docs/code-standards.md` — nếu naming section liệt kê service theo layer, thêm LiveTradeCollector/LiveMetricsQueryService (nếu áp dụng).

## Implementation steps

1. Cập nhật OKX comment: `subscribe_trades` no-op — defer OKX position→Trade emission sang R tương lai (cần demo payload; snapshot-delta vs paper per-fill khác nhau → tránh double-count). Giữ no-op.
2. Roadmap: R8 row + dependency graph note done; unresolved dòng 82 + R4 defer note (OKX emission / live-value map) → GIẢI: live-value map = `subscription_id`; OKX emission defer riêng.
3. `docs/system-architecture.md`: cập nhật vị trí BrokerFactory + Quote/Ws + engine.live thêm collector/metrics + thin app driver (app chỉ inject/bootstrap/create_task/cancel). Mermaid/ASCII nếu concept ≥2 thành phần.
4. Full gate: `just test` + `ruff` + `pyright` + `lint-imports` → xanh.
5. (option) `docs-manager` review docs sync.

## Todo

- [x] OKX comment defer (giữ no-op)
- [x] roadmap.md R8 status + unresolved resolve
- [x] docs/system-architecture.md AS-IS
- [x] Full gate xanh
- [x] (option) journal entry

## Success criteria

- OKX no-op có comment defer rõ (future R + lý do).
- Roadmap R8 done; unresolved OKX/live-value map resolved.
- docs phản ánh vị trí mới + thin driver.
- `just test` 560 + 8 contract + ruff + pyright xanh.

## Risk assessment

- **Docs drift:** giữ AS-IS (không changelog/banner theo CLAUDE.md). Chỉ mô tả hiện trạng.
- **OKX quên:** comment rõ ràng để R sau pick up; không để no-op câm.

## Next steps

R8 done → roadmap R1-R8 hoàn tất. OKX live trade emission = R tương lai (khi có demo payload). MAE/MFE (`260630-0031`) có thể rebase Trade VO sau.
