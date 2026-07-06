# Phase 03 — Move `BacktestConfig` → `core.domain.backtest`

**Priority:** P1 · **Status:** pending · **Depends:** P1
**Context:** [plan](plan.md) · nguồn `backtest/models/backtest_config.py`

## Mục tiêu
`BacktestConfig` là VO đặc thù backtest-run nhưng đang kẹt ở tầng `backtest` → move xuống `core.domain.backtest` để cùng nhà `BacktestResult`/`OpenLot`. Thuần di chuyển, class + properties (`slippage_percent`, `commission_percent`) không đổi.

## Files
**Create**
- `core/domain/backtest/config.py` — move nguyên `BacktestConfig` (dataclass + 2 property). Không đổi field/default (`initial_capital=10_000.0`, `slippage_bps=10.0`, `commission_bps=10.0`).

**Modify**
- `core/domain/backtest/__init__.py` — thêm export `BacktestConfig`.

**Update importers** (`backtest.models.backtest_config` → `core.domain.backtest`):
| File | Ghi chú |
|---|---|
| `backtest/workers/backtest_dispatch.py` | `_config_from_dict` build BacktestConfig |
| `backtest/engine/historical_replay_app_service.py` | param type |
| `backtest/engine/backtest_result_app_service.py` | param type (dòng 29 + 63) |
| `backtest/jobs/backtest_strategy_loader.py` | build BacktestConfig |
| `backtest/engine/backtest_app_service.py` | param type (run/_load_bars) |

**Delete**
- `backtest/models/backtest_config.py` + `backtest/models/__init__.py` (rỗng) → xoá cả thư mục `backtest/models/`.

**Tests**
- Grep `backtest.models.backtest_config` trong `tests/` → update path sang `core.domain.backtest`. (`test_backtest_app_service_persistence`, `test_engulfing_backtest`, `test_hitnrun2_backtest` khả năng dùng.)

## Steps
1. Move file → `core/domain/backtest/config.py`; export ở `__init__`.
2. Update 5 importer src + tests (đổi dòng import).
3. Xoá `backtest/models/`.
4. Gates: `ruff && pyright && lint-imports && just test`.

## Success
- `grep -rn "backtest.models" src/ tests/` → rỗng; `backtest/models/` không còn.
- `from pocketquant.core.domain.backtest import BacktestConfig` hoạt động; 7 contracts + test xanh.

## Rủi ro
- Thấp: `BacktestConfig` không có dep ngược lên engine/app. `entities.py` chỉ tham chiếu `config_snapshot: dict` (không import class) → không đổi.
