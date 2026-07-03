# Phase 01 — Backend: stats calculator + cursor/markers repo + stats app service + routes

## Context

- Trade entity: `core/domain/backtest/value_objects.py:226-296` (fields: trade_id, entry_time, pnl, quantity, duration_seconds, direction, exit_time...).
- Repo: `core/infra/persistence/repositories/backtest_trade_repository.py` — `list_by_run` sort entry_time asc, no paging. Indexes incl. `ix_bttrades_run_entry [(run_id,1),(entry_time,1)]`, `ix_bttrades_pnl`.
- Query service: `backtest/backtest_query_service.py` — `list_trades` shape (keys: trade_id, direction, entry_price, entry_time, exit_price, exit_time, quantity, sl_price, tp_price, pnl, commission, duration_seconds).
- Existing pure calculator to sit beside: `backtest/domain/services/performance_calculator.py` (static, numpy, has `drawdown_series`).
- DI services provider: `app/di/services.py`. Repos auto-provided in `app/di/persistence.py`.
- Routes: `app/routes/backtest.py` (`/{run_id}/trades` at line 100). Registered `main_extensions.py` `register_routes`.
- FE stats logic to port (oracle): `web/src/components/backtest/stats-utils.ts` — `histogram(values, binCount=20)`, `computeStreaks`, `profitFactorByDirection`, `topDrawdowns(curve, topN=5)`.

## Files to create

1. `src/pocketquant/backtest/domain/services/trade_stats_calculator.py`
   - Pure functions (no I/O), numpy where useful. Port FE 1-1:
     - `histogram(values: list[float], bin_count: int = 20) -> list[HistogramBin]` — same semantics: []→[], degenerate range→1 bin, clamp top edge into last bin.
     - `win_loss_streaks(trades) -> StreakStats` — closed only; pnl>0 win, <0 loss, ==0 resets.
     - `profit_factor_by_direction(trades) -> {long: float|None, short: float|None}` — gross profit/loss per side; None if no loss.
     - `drawdown_periods(equity_curve, top_n=5) -> list[DrawdownPeriod]` — same scan as FE `topDrawdowns` (open on dd<0, track trough, close on recovery, tail unrecovered = recovery None), sort by depth, slice top_n.
   - Dataclasses: `HistogramBin(lo,hi,count)`, `StreakStats(max_win_streak,max_loss_streak)`, `DrawdownPeriod(depth,start_time,trough_time,recovery_time,duration_seconds)`.
   - Input: closed `Trade` list + `EquityPoint` list (domain types). Duration for histogram = `duration_seconds/3600` (hours), matching FE.

2. `src/pocketquant/backtest/backtest_stats_service.py`
   - `BacktestStatsService` app-service, inject `BacktestTradeRepository` + `BacktestRepository`.
   - Pydantic DTOs co-located (matches convention):
     - `TradeSortKey` enum (entry_time, pnl, quantity, duration_seconds, entry_price, exit_price, commission, direction, status).
     - `TradeFilter` enum (all, wins, losses).
     - `ListTradesQuery(run_id, limit=50, cursor: str|None, sort_key=entry_time, sort_dir=desc, filter=all)`.
     - `TradeDto` (same keys as current list_trades shape — includes `trade_id`).
     - `PagedTradesResponse(items: list[TradeDto], next_cursor: str|None, has_more: bool, total: int)` (total = count for current filter, for footer).
     - `TradeMarkerDto(trade_id, entry_time, exit_time, direction)`.
     - `HistogramBinDto`, `StreakStatsDto`, `DirectionProfitFactorDto`, `DrawdownPeriodDto`.
     - `BacktestStatsResponse(pnl_histogram, duration_histogram, streaks, profit_factor_by_direction, drawdowns, profit_factor_all)` — profit_factor_all lifted from run metrics (FE reads it from BE metrics already).
   - Methods:
     - `list_trades_paged(query) -> PagedTradesResponse` — delegate repo keyset query + shape DTO + encode next_cursor.
     - `list_markers(run_id) -> list[TradeMarkerDto]` — repo markers-lite.
     - `get_stats(run_id) -> BacktestStatsResponse` — pull closed trades (lite fields) + equity curve, run calculator.
   - Cursor codec: base64(json) `{k, id}`. Private helpers `_encode_cursor`/`_decode_cursor`. No bson.

## Files to modify

3. `src/pocketquant/core/infra/persistence/repositories/backtest_trade_repository.py`
   - `list_by_run_paged(run_id, *, limit, cursor_value, cursor_id, sort_key, sort_dir, pnl_filter) -> tuple[list[Trade], bool]`
     - Build filter `{run_id}` (+ `pnl` gt/lt for wins/losses).
     - Keyset: for desc, `(key < cursor_value) OR (key == cursor_value AND _id < cursor_id)`; asc mirrored. Map `status`→`exit_time` presence (all closed here so status sort trivial; keep for parity), `direction` string sort.
     - `.sort([(mongo_key, dir), ("_id", dir)]).limit(limit+1)`; return (first `limit`, has_more).
   - `count_by_run(run_id, pnl_filter) -> int` for footer total.
   - `list_markers_by_run(run_id) -> list[dict]` — projection `{entry_time, exit_time, direction, _id}` sort entry_time asc (lite; avoid full doc).
   - `list_closed_for_stats(run_id) -> list[Trade]` (or reuse `list_by_run`) — full closed set for stats calc (one pass).
   - Add compound index for pnl keyset if needed: `[(run_id,1),(pnl,1)]` name `ix_bttrades_run_pnl` (pnl sort is a listed option). Update `ensure_indexes` + its test.

4. `src/pocketquant/backtest/backtest_query_service.py`
   - VERIFIED: `list_trades` has exactly one caller (`app/routes/backtest.py:106`); `/{run_id}/trades` has exactly one FE consumer (`backtest-api.ts:128`). Safe to migrate the route to the stats service and remove `list_trades` (or leave it unused). Remove to avoid dead code; keep the shared trade-DTO shaping in the stats service.

5. `src/pocketquant/app/routes/backtest.py`
   - Change `GET /{run_id}/trades` to accept `limit, cursor, sort_key, sort_dir, filter` query params → `stats_svc.list_trades_paged(...)` → `PagedTradesResponse`.
   - Add `GET /{run_id}/trade-markers` → `list_markers`.
   - Add `GET /{run_id}/stats` → `get_stats`.
   - Inject `FromDishka[BacktestStatsService]`.

6. `src/pocketquant/app/di/services.py`
   - `backtest_stats_service = provide(BacktestStatsService, scope=Scope.APP)`.

## Tests (create/modify)

- `tests/backtest_test/domain/test_trade_stats_calculator.py` — parity vs FE oracle cases: histogram empty/degenerate/clamp, streaks reset on breakeven/open, PF None when no loss, drawdown open/recover/tail.
- `tests/core_test/infra/persistence/backtest/test_trade_repository.py` — add: paged first/next page, has_more flag, keyset stable on equal entry_time (tie-break _id), wins/losses filter, markers projection, count. Update `test_ensure_indexes_creates_all_five` → six if index added.
- `tests/backtest_test/` — stats service: list_trades_paged happy path + cursor roundtrip; get_stats shape.

## Implementation steps

1. Grep callers of `BacktestQueryService.list_trades` to decide keep/replace.
2. Write calculator + dataclasses. Unit test against FE oracle values.
3. Extend repo (paged/count/markers/stats-source) + index + repo tests.
4. Write stats service + DTOs + cursor codec + tests.
5. Wire routes + DI. Run `just lint`, `just types`, targeted `just test-pkg`.

## Validation

- `just test` backtest + core persistence green.
- `just lint`, `just types` clean.
- import-linter contracts pass (no new cross-layer imports).

## Risks / rollback

- Keyset correctness on duplicate sort values → tie-break `_id`, explicit test.
- If `list_trades` has other callers, do NOT remove — only the route migrates.
- Rollback = revert route to old `list_trades`; new service/endpoints are additive.
