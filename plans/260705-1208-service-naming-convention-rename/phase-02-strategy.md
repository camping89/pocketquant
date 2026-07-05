# Phase 2 — Strategy

**Priority:** P1 · **Risk:** low-med · **Status:** completed

## Overview
Rename interface `IStrategy` → `IStrategyService` + 2 impl → `*StrategyService`. Đổi tên file interface. `FilledOrder(Protocol)` ở cùng file → giữ nguyên tên, di chuyển cùng.

## Rename mapping
| Current class | New class | Current file | New file | refs |
|---|---|---|---|---|
| `IStrategy` | `IStrategyService` | `core/domain/strategy/interfaces.py` | `strategy_service_interface.py` | 6 |
| `EngulfingStrategy` | `EngulfingStrategyService` | `core/domain/strategy/services/engulfing.py` | `engulfing_strategy_service.py` | 4 |
| `HitNRun2Strategy` | `HitNRun2StrategyService` | `core/domain/strategy/services/hitnrun2.py` | `hitnrun2_strategy_service.py` | 3 |

**KHÔNG đổi:** `FilledOrder(Protocol)` (cùng file interfaces.py — di chuyển sang file mới, giữ tên).

## Implementation steps
1. `interfaces.py` → `git mv` thành `strategy_service_interface.py`; đổi `class IStrategy` → `class IStrategyService`; giữ `FilledOrder`.
2. Rename 2 impl class + `git mv` file.
3. Cập nhật refs:
   - `engine/app_services/strategy_app_service.py` — `_DefaultStrategy(IStrategy)` + import; registry map strategy name→class.
   - `strategy/__init__.py` / `strategy/services/__init__.py` re-export.
   - Mọi nơi type-hint `IStrategy` (6 file).
4. Kiểm tra bảng đăng ký strategy (name→class) nếu có — cập nhật class mới.

## Gotchas
- `IStrategy` là ABC + `_DefaultStrategy` subclass trong `strategy_app_service.py`.
- Strategy có thể được resolve động theo tên trong DB (chuỗi `"engulfing"`) → **chỉ đổi class name, KHÔNG đổi giá trị định danh strategy trong DB/config**.

## Verify
- `just test` · `import-linter` · `pyright` → xanh.
- Commit: `refactor(naming): strategy → *StrategyService, IStrategy → IStrategyService`

## Todo
- [x] IStrategy → IStrategyService + rename file → strategy_service_interface.py (giữ FilledOrder)
- [x] EngulfingStrategy → EngulfingStrategyService
- [x] HitNRun2Strategy → HitNRun2StrategyService
- [x] Cập nhật `_DefaultStrategy` + registry + __init__ re-export
- [x] Xác nhận định danh strategy trong DB không đổi
- [x] pytest + import-linter + pyright xanh

## Success criteria
Test/lint/type xanh; strategy vẫn resolve đúng theo tên; `grep -rw IStrategy\b` = 0 (chỉ còn `IStrategyService`).
