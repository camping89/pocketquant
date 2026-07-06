---
initiative: trading-calculation-fix
sub: R1
track: structure
status: done
depends: []
blocks: [R2, R3, R5, R6]
---

# R1 — Domain Consolidation (`core.domain.trading`)

> STRUCTURE-ONLY. Không đổi logic. Mỗi phase kết thúc với `just test` + `ruff` +
> `pyright` + `lint-imports` (7 contracts) **xanh**. Nguồn:
> [roadmap](../roadmap.md) (hàng R1) + [design](../design-execution-metrics-separation.md) (Model E, §4 Placement).

## Mục tiêu

Gom contract phổ quát + metrics vào **`core.domain.trading`** để backtest & (tương lai)
live/forward dùng chung một tầng duy nhất; tách các VO đặc thù backtest-run đúng chỗ;
tất cả **thuần di chuyển + đổi tên**, không đụng thuật toán.

## Phát hiện nền (đã verify)

- Trade/Fill/EquityPoint/Order/OpenLot/BacktestMetrics **đã ở** `core.domain.backtest.value_objects` → R1 là **tách file trong `core.domain`**, không kéo từ package `backtest` lên.
- "build facade" = `metrics_builder.build_metrics` (`backtest/engine/metrics_builder.py`); consumer **duy nhất** `backtest_result_app_service.py:424`.
- Engine DTO audit: engine chỉ có `sync_dtos` + `BackfillTrackedSymbolCommand` — app/command DTO đúng tầng, **không có domain VO đặt nhầm** → không move gì (deliverable ở P5).
- Blast radius: 13 file `src` + 17 file `test`. Web TS `BacktestMetrics` độc lập (không đổi JSON keys).

## Quyết định đã chốt (user)

1. **Order → OrderRecord**, move `core.domain.order` (P4). 2. **Fold** `build_metrics` → `PerformanceCalculatorDomainService.build()`, xoá `metrics_builder.py` trong R1 (P2). 3. **1 file** `core/domain/trading/value_objects.py` (khớp convention hiện tại). Không dùng re-export shim — update importer trực tiếp (AS-IS).

## Phases

| # | Phase | Trạng thái | Depends |
|---|-------|-----------|---------|
| 1 | [Scaffold `core.domain.trading` + move Trade/Fill/EquityPoint + rename PerformanceMetrics](phase-01-trading-package-and-value-objects.md) | ✅ done | — |
| 2 | [Move calculator + fold `build` + move trade_stats + xoá metrics_builder](phase-02-calculator-build-facade-trade-stats.md) | ✅ done | P1 |
| 3 | [Move `BacktestConfig` → `core.domain.backtest`](phase-03-backtest-config-move.md) | ✅ done | P1 |
| 4 | [`Order` → `OrderRecord` → `core.domain.order`](phase-04-order-record-move.md) | ✅ done | P1 |
| 5 | [Engine DTO audit deliverable + docstrings + docs + roadmap status](phase-05-audit-docs-roadmap.md) | ✅ done | P1–P4 |

## Move map (tổng)

| Symbol | Từ | Đến |
|---|---|---|
| `Trade`, `Fill`, `EquityPoint` | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` |
| `BacktestMetrics` → **`PerformanceMetrics`** | `core.domain.backtest.value_objects` | `core.domain.trading.value_objects` |
| `PerformanceCalculatorDomainService` (+ static `build`) | `backtest.domain.services.performance_calculator_domain_service` | `core.domain.trading.performance_calculator_domain_service` |
| `trade_stats` (histogram/streaks/…) | `backtest.domain.services.trade_stats_calculator` | `core.domain.trading.trade_stats` |
| `BacktestConfig` | `backtest.models.backtest_config` | `core.domain.backtest.config` |
| `Order` → **`OrderRecord`** | `core.domain.backtest.value_objects` | `core.domain.order.records` |

**Ở lại `core.domain.backtest`:** `BacktestResult` (entities), `OpenLot` (value_objects), `BacktestConfig` (mới về).
**Xoá:** `backtest/engine/metrics_builder.py`, `backtest/domain/` (cả cây), `backtest/models/` (cả cây).

## Invariants

- Không đổi logic: `to_mongo`/`from_mongo` + math giữ nguyên byte-for-byte → DB compat + số backtest không đổi.
- Cross-import trong `core.domain` (trading↔backtest↔order) hợp lệ — 7 contracts không ràng buộc nội bộ `core.domain`.
- numpy vào `core.domain.trading` hợp lệ (không nằm trong forbidden `bson`/`fastapi`).
- Gates xanh **sau mỗi phase**; phase đỏ vì logic → dừng, tách ra (không thuộc R1).
