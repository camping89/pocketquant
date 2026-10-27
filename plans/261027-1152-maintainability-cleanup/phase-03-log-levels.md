# Phase 03 — Log levels (Deploy A point)

- Demote to DEBUG: `sync_service.py` sync started/completed; `binance_adapter.py` fetch started/completed; `tradingview_adapter.py` fetch completed; `sync_internals/bar_filters.py` filtered existing; `bar_repository.py` insert_many completed; the per-run `sync_jobs.py` sync_1m lines.
- Per-replayed-fill INFO in `order_app_service.py` and `strategy_app_service.py` floods backtests. Keep per-trade INFO for live; the backtest sandbox must not print one INFO line per fill.
- `request_logging.py`: one DEBUG line per request; buffer bodies only when DEBUG is enabled.
- `strategy_reconcile_app_service.py`: `reconcile.load_failed` logs once per subscription id.
- `integrity_jobs.py`: truncate the `still_missing` ranges.

Verify: market-data and logging tests; a local run at `LOG_LEVEL=INFO` shows no per-minute line.
