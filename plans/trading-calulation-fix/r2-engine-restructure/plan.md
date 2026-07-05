---
initiative: trading-calculation-fix
sub: R2
track: structure
status: done
depends: [R1]
blocks: [R3, R8, 260630-0031-backtest-mae-mfe-excursion]  # cross-initiative: R2 rebase backtest paths
---

# R2 — Engine Restructure (gộp `backtest/` → `engine/`, 4→3 tầng)

> STRUCTURE-ONLY. Thuần di chuyển + đổi path import, **không đổi logic**. Mỗi phase
> kết thúc với `just test` + `ruff` + `pyright` + `lint-imports` **xanh**. Nguồn:
> [roadmap](../roadmap.md) (hàng R2) + [design](../design-execution-metrics-separation.md).

## Mục tiêu

Chuẩn hoá kiến trúc đích: *backtest & live là hai **driver** trên một **engine** chung*.
Gộp package top-level `backtest/` vào `engine/backtest/`; regroup engine thành 5 feature
area `{strategy, execution, market_data, backtest, live}`; hạ import-linter từ **4 tầng
→ 3 tầng** (`app ◁ engine ◁ core`) + thêm **2 contract intra-engine** khoá `backtest ⟂ live`
và *máy chung ⊄ driver*.

## Phát hiện nền (đã verify)

- **Đồ thị import sạch cho contract mới** (không cần đổi logic):
  - Live driver `strategy_reconcile` chỉ import `strategy_app_service` (máy chung).
  - Backtest driver `backtest_sandbox` chỉ import máy chung (order/position/strategy/risk_check).
  - Máy chung (`strategy_app_service` → order/position/risk_check) không chạm backtest/live.
- **Blast radius**: 12 file `src` move; ~13 file `src` update import (app/di×4, app/routes×3, app/main_extensions, engine internal×4); ~17 file `test` update import; `pyproject.toml` (6 chỗ contract); `test_domain_purity.py:14`.
- **`__init__.py`**: `engine/market_data/` là PEP 420 (không `__init__`) → subpackage mới theo cùng pattern (verify grimp/pytest discover được).
- **Không đụng**: `engine/market_data/` (đã là feature area); `web/` SPA (route URL không đổi); `packages = ["src/pocketquant"]` (glob đơn, không cần sửa).
- **Giữ tên file** `backtest_result_app_service.py` (rename → report là **R5**, không phải R2).

## Quyết định đã chốt (user)

1. **Intra-engine = 2 contract tách**: `independence` [backtest, live] + `forbidden` máy chung → driver. Tổng **8 contract**.
2. **backtest/ phẳng hoàn toàn**: 12 file vào flat `engine/backtest/`; bỏ subfolder `engine/`, `jobs/`, `workers/`.
3. Không re-export shim — update importer trực tiếp (AS-IS, khớp R1).

## Phases

| # | Phase | Trạng thái | Depends |
|---|-------|-----------|---------|
| 1 | [Engine internal regroup → {strategy, execution, live}](phase-01-engine-internal-regroup.md) | ✅ done | R1 |
| 2 | [Fold `backtest/` → `engine/backtest/` + import-linter 4→3 + 2 intra-engine contract](phase-02-fold-backtest-and-contracts.md) | ✅ done | P1 |
| 3 | [Docs sync + roadmap R2 done + final gate sweep](phase-03-docs-roadmap-verify.md) | ✅ done | P1, P2 |

## Target layout (đích)

```
engine/
  strategy/     strategy_app_service, strategy_command_service, strategy_query_service
  execution/    order_app_service, position_app_service, orders_positions_service, risk_check
  market_data/  (giữ nguyên — feature area)
  backtest/     backtest_app_service, backtest_sandbox_app_service, historical_replay_app_service,
                backtest_result_app_service, collected_results, lot_tracking_helper,
                backtest_command_service, backtest_query_service, backtest_stats_service,
                backtest_execution_service, backtest_dispatch, backtest_strategy_loader
  live/         strategy_reconcile_app_service
```

## Invariants

- **Parity**: backtest & paper-live cùng logic khớp lệnh (`PaperBrokerAdapter` chung) — R2 không tách engine khớp lệnh.
- Không đổi logic: math/`to_mongo`/`from_mongo`/thứ tự await giữ nguyên → số backtest + DB compat không đổi.
- Contract cuối = **8**: `app◁engine◁core` (layers), core⊄infra, core⊄inner, engine⊄app, fastapi-only-app, no-bson, `backtest⟂live` (independence), máy-chung⊄driver (forbidden).
- Gates xanh **sau mỗi phase**; phase đỏ vì logic → dừng, tách ra (không thuộc R2).

## Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Import-linter fail vì source_module không tồn tại giữa move | Move file + update contract **cùng 1 phase** (P2 atomic) |
| Namespace package mới không discover được | Verify `lint-imports` + `pytest --collect-only` ngay sau tạo dir; fallback thêm `__init__.py` |
| Sót path string trong test/docs | `grep -rn "pocketquant.backtest"` toàn repo cuối P2 + P3 = 0 hit |
| Circular import sau regroup | Đồ thị đã verify DAG (máy chung ⊄ driver); giữ nguyên chiều import khi move |
