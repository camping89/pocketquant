# Phase 1 — Domain Services + Helper

**Priority:** P1 · **Risk:** low (không qua DI, khởi tạo trực tiếp) · **Status:** completed

## Overview
Rename 4 domain service → `*DomainService` + 1 helper → `*Helper`. Đây là nhóm rủi ro thấp nhất: không nằm trong DI provider, refs ít.

## Rename mapping
| Current class | New class | Current file | New file | refs |
|---|---|---|---|---|
| `PositionSizer` | `PositionSizerDomainService` | `core/domain/risk/services/position_sizer.py` | `position_sizer_domain_service.py` | 5 |
| `BarBuilder` | `BarBuilderDomainService` | `core/domain/bar/services/bar_builder.py` | `bar_builder_domain_service.py` | 5 |
| `PerformanceCalculator` | `PerformanceCalculatorDomainService` | `backtest/domain/services/performance_calculator.py` | `performance_calculator_domain_service.py` | 5 |
| `SyncProgressTracker` | `SyncProgressTrackerDomainService` | `core/domain/sync_status/services/sync_progress_tracker.py` | `sync_progress_tracker_domain_service.py` | 4 |
| `LotTracker` | `LotTrackingHelper` | `backtest/engine/lot_tracker.py` | `lot_tracking_helper.py` | 3 |

**KHÔNG đổi:** `SyncProgressDecision` (enum cùng file), VO trong `trade_stats_calculator.py` (`HistogramBin`/`StreakStats`/…). `TradeStatsCalculator` không tồn tại.

## Implementation steps (mỗi class)
1. `grep -rlw <OldClass> src/ tests/` → liệt kê refs.
2. Đổi tên class trong file định nghĩa + cập nhật docstring nếu name-echo.
3. `git mv <old_file.py> <new_file.py>`.
4. Cập nhật mọi import (kể cả `__init__.py` re-export — vd `core/domain/risk/__init__.py` export `PositionSizer`, `core/domain/risk/services/__init__.py`).
5. Cập nhật call-site (vd `strategy_app_service.py` gọi `PositionSizer.calculate_size`).
6. Cập nhật test refs.

## Gotchas
- `PositionSizer` re-export 2 tầng: `risk/__init__.py` + `risk/services/__init__.py` + `__all__`.
- `LotTracker` dùng bởi `result_collector.py` (Phase 3 sẽ rename file đó — chỉ cập nhật symbol ở đây).

## Verify
- `just test` · `import-linter` · `pyright` → xanh.
- Commit: `refactor(naming): domain services → *DomainService, LotTracker → LotTrackingHelper`

## Todo
- [x] PositionSizer → PositionSizerDomainService (+ 2 __init__ re-export)
- [x] BarBuilder → BarBuilderDomainService
- [x] PerformanceCalculator → PerformanceCalculatorDomainService
- [x] SyncProgressTracker → SyncProgressTrackerDomainService
- [x] LotTracker → LotTrackingHelper
- [x] `git mv` 5 file
- [x] pytest + import-linter + pyright xanh

## Success criteria
Tất cả test/lint/type xanh; không còn refs tên cũ (`grep -rw` = 0).
