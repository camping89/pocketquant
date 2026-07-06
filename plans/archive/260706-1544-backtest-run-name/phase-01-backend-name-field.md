# Phase 01 — Backend: name field

## Files sửa

### 1. `src/pocketquant/core/domain/backtest/config.py`
`BacktestConfig`: thêm field `name: str | None = None` (sau `parameters` hoặc trước cũng được, dataclass field có default). Cập nhật docstring 1 dòng.

### 2. `src/pocketquant/core/domain/backtest/entities.py` — `BacktestResult`
- Thêm field `name: str | None = None` (đặt cạnh `verdict`).
- `.started()`: `name=config_snapshot.get("name")`.
- `to_mongo()`: thêm `"name": self.name`.
- `from_mongo()`: `name=data.get("name")`.

### 3. `src/pocketquant/engine/backtest/backtest_command_service.py`
- `RunBacktestCommand`: thêm `name: str | None = Field(default=None, max_length=200, description="Optional run label")`.
- `run()` config dict: thêm `"name": cmd.name`.
- Thêm `SetNameCommand(BaseModel)`: `run_id: str`, `name: str | None = Field(default=None, max_length=200)`.
- Thêm method `set_name(cmd)` → `repo.set_name(...)`, raise `NotFoundError` nếu không match (mirror `set_verdict`).

### 4. `src/pocketquant/core/infra/persistence/repositories/backtest_repository.py`
Thêm `set_name(run_id, name) -> bool` mirror `set_verdict` (`update_one $set name`, return `matched_count > 0`).

### 5. `src/pocketquant/engine/backtest/backtest_dispatch.py`
`_config_from_dict`: thêm `name=payload.get("name")`.

### 6. `src/pocketquant/engine/backtest/backtest_report_app_service.py` — `finalize()`
- `config_snapshot`: thêm `"name": self._config.name`.
- `BacktestResult(...)`: thêm `name=self._config.name`.

### 7. `src/pocketquant/app/routes/backtest.py`
- Import `SetNameCommand`.
- `list_backtests` dict: thêm `"name": r.name`.
- Thêm `SetNameBody(BaseModel)`: `name: str | None = Field(default=None, max_length=200)`.
- Thêm route `PATCH /{run_id}/name` (mirror `set_backtest_verdict`) → `cmd_svc.set_name(...)`, return `{"run_id", "name"}`.
- `get_backtest` không đổi (đã trả `to_dict()` = `to_mongo()` → có `name`).

## Validation
- `uv run ruff check .`
- `uv run pyright`
- `uv run lint-imports`
- `just test` (hoặc `pytest` scoped backtest) — **không** chạy trên `.env` trỏ prod.

## Risks
Không đổi index/schema bắt buộc; `name` là field optional, doc cũ thiếu `name` → `from_mongo` trả `None` (tolerant). Không cần migration.
