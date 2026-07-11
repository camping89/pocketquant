---
phase: 1
title: "Foundation & data access"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Foundation & data access

## Overview

Dựng skeleton `scripts/rubric/` + lớp truy cập dữ liệu read-only (runs, trades, bars) + domain types dùng chung. Mọi phase sau phụ thuộc phase này.

## Requirements

- Functional: load một run (config_snapshot + metrics + equity_curve), tất cả trades của run, và bars theo (symbol, interval, [start,end]) — read-only, env-driven Mongo URL.
- Functional: dedup runs có metrics + trade-set identical (double-persist artifact) → 1 canonical run + danh sách alias id.
- Non-functional: `uv run` (venv project, pymongo 4.16); không hardcode credential; không import trading path để mutate.

## Architecture

```
scripts/rubric/
  __init__.py
  data_access.py        # Mongo read: load_run, load_trades, load_bars, list_finished_runs, dedup
  types.py              # dataclasses: RunData, TradeRow, ScorecardResult (shared, no logic)
```

- `data_access.py`: `MongoClient(os.environ["MONGODB_URL"])`; DB name từ `MONGODB_DATABASE` (default `pocketquant`). **[Validation S2] Connection LAZY** — tạo client BÊN TRONG loader function (hoặc cached getter gọi khi cần), KHÔNG ở module import time. Lý do: unit test dưới `tests/scripts/rubric/` import module này; direnv nạp prod `MONGODB_URL` → module-level connect vướng conftest prod-guard (`207.148.79.60`). Prod read-only; ghi chỉ khi `--persist` (Phase 8).
  - `list_finished_runs() -> list[str]` — status=finished.
  - `load_run(run_id) -> RunData` — config_snapshot (slippage/commission/parameters/dates/initial_capital), metrics dict, equity_curve (list of {timestamp,equity,drawdown}), strategy_code, symbol, interval, name.
  - `load_trades(run_id) -> list[TradeRow]` — Decimal→float: entry_price, exit_price, sl_price, tp_price, quantity, pnl, commission, duration_seconds, direction, entry_time, exit_time.
  - `load_bars(symbol, interval, start, end) -> np.ndarray struct` — fields open/high/low/close/datetime (bar doc: composite symbol `BTCUSDT:BINANCE`, field `datetime` ISO string per bar_repository).
  - `dedup_runs(run_ids) -> list[(canonical_id, [alias_ids])]` — group by (strategy_code, total_trades, round(total_return,10)) then confirm identical trade entry_time set; collapse.
- `types.py`: dataclasses thuần, không logic (tránh circular import).

## Related Code Files

- Create: `scripts/rubric/__init__.py`, `scripts/rubric/data_access.py`, `scripts/rubric/types.py`
- Reference (read shape, DO NOT import for mutation): `src/pocketquant/core/domain/backtest/entities.py` (run doc shape), `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` (bars field names)

## Implementation Steps

1. `types.py`: `@dataclass RunData`, `TradeRow`, `ScorecardResult` (placeholder: run_id, strategy_code, axes scores dict, grade, metrics dict, audit dict, rubric_version).
2. `data_access.py`: connection helper (env-only), 5 loader functions above. Decimal→float ngay tại boundary.
3. `dedup_runs`: group + confirm identical entry_time set → canonical (giữ id nhỏ nhất theo thời gian) + aliases.
4. Smoke: `uv run python -c "from scripts.rubric.data_access import list_finished_runs; print(list_finished_runs())"` → 6 ids; dedup → 5.

## Success Criteria

- [ ] `list_finished_runs()` trả 6 run; `dedup_runs` gộp `hitnrun2` 546f/6b52 → 5 canonical.
- [ ] `load_trades('019f36d2…')` trả 8629 TradeRow, mọi field float (không Decimal/str).
- [ ] `load_bars('BTCUSDT:BINANCE','1m',start,end)` trả struct array sorted theo datetime, khớp range run.
- [ ] Không credential hardcode; chạy được qua `uv run`.

## Risk Assessment

- **Bars volume lớn** (1m, 1 năm ≈ 500k bars/run) → load_bars phải project chỉ o/h/l/c/datetime + filter range, không kéo cả collection. Mitigation: query có index (symbol,interval,datetime); chỉ load window của run.
- **Decimal vs float**: Mongo lưu Decimal128/string → convert tại boundary, tránh lỗi arithmetic downstream.
- **Dedup sai gộp nhầm**: 2 run KHÁC nhau tình cờ cùng total_trades → confirm bằng entry_time SET, không chỉ count.
