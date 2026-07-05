# Phase 01 — Rename + Gut Equity + Wire Broker

**Priority:** P2 · **Status:** done · Production code only (no tests here).

## Overview

Rename collector → `BacktestReportAppService`, xoá shadow equity ledger, inject `IBrokerPort` ref, đọc broker balance thay vì tự tính. Zero logic change về số liệu (parity-exact).

## Related code files

**Rename (git mv) + edit:**
- `src/pocketquant/engine/backtest/backtest_result_app_service.py` → `backtest_report_app_service.py`

**Edit (refs):**
- `src/pocketquant/engine/backtest/backtest_app_service.py` — import + ctor call + `await finalize` (2 site)
- `src/pocketquant/engine/backtest/collected_results.py` — docstring
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` — docstring (dòng 16)

## Implementation steps

### 1. `git mv` + rename class
```
git mv src/pocketquant/engine/backtest/backtest_result_app_service.py \
       src/pocketquant/engine/backtest/backtest_report_app_service.py
```
- Class `BacktestResultAppService` → `BacktestReportAppService`.
- Module docstring: đổi framing "Result collector" → "Report collector — subscribes broker, records Orders/Trades/equity, builds the BacktestResult report". Giữ AS-IS (mô tả hiện trạng, no change-narrative).

### 2. Constructor — inject broker, xoá shadow fields
Thêm import:
```python
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
```
Ctor:
```python
def __init__(
    self,
    config: BacktestConfig,
    initial_capital: float,
    broker: IBrokerPort,
    run_id: str | None = None,
) -> None:
    self._config = config
    self._initial_capital = initial_capital
    self._broker = broker
    self._run_id = run_id or ""
    self._equity_curve: list[EquityPoint] = []
    self._mtm_curve: list[EquityPoint] = []
    self._orders_by_id: dict[str, OrderRecord] = {}
    self._trades: list[Trade] = []
    self._equity_curve.append(
        EquityPoint(timestamp=config.start_date, equity=initial_capital, drawdown=0.0)
    )
```
**Xoá:** `self._current_equity`, `self._peak_equity`, `self._total_commission`.

### 3. `on_fill` — bỏ shadow debit, giữ audit
```python
async def on_fill(self, result: Any) -> None:
    if result.filled_quantity is None or result.filled_quantity <= 0:
        self._upsert_order_status(result)
        return
    fill_price = result.filled_price or 0.0
    fill_qty = result.filled_quantity
    if fill_price <= 0:
        return
    timestamp = get_current_time()
    commission = result.commission  # stamped on Fill doc; balance debit owned by broker
    order = self._upsert_order(result, fill_price, fill_qty, commission, timestamp)
    self._append_fill(order, result, fill_price, fill_qty, commission, timestamp)
```
Xoá 2 dòng `self._total_commission += commission` + `self._current_equity -= commission`.

### 4. `on_trade` — bỏ pnl credit, đọc broker balance cho realized point
```python
async def on_trade(self, event: TradeClosedEvent) -> None:
    exit_time = event.exit_time or get_current_time()
    trade = Trade(...)  # unchanged
    self._trades.append(trade)
    # Realized equity from broker (single source). Broker updated _balance
    # (realized pnl + commission) under lock BEFORE dispatching this event
    # (dispatch is outside the lock), so available_balance is post-close truth.
    balance = await self._broker.get_balance()
    self._record_equity_point(exit_time, balance.available_balance)
    if event.exit_order_id is not None:
        ...  # back-link unchanged
```
Xoá `self._current_equity += event.pnl`.

### 5. `_record_equity_point` — nhận equity param, bỏ peak arithmetic
```python
def _record_equity_point(self, timestamp: datetime, equity: float) -> None:
    self._equity_curve.append(
        EquityPoint(timestamp=timestamp, equity=equity, drawdown=0.0)
    )
```
Drawdown recompute ở persist (`_with_drawdown`); `build().max_drawdown` tự tính cummax từ equity values → field `.drawdown` trên realized point vốn không dùng cho max_drawdown. Xoá `_peak_equity` refs.

### 6. `mark_to_market` — GIỮ NGUYÊN
Vẫn `mark_to_market(timestamp, total_equity)`; caller `_mtm_on_bar` không đổi (minimal churn). `_downsample_equity_curve`/`_with_drawdown`/`_position_to_open_lot` không đổi.

### 7. `finalize` — async, đọc broker cho current_equity + sum commission từ fills
```python
async def finalize(self, run_id, started_at, completed_at, status="finished",
                   error_message=None, positions=None) -> CollectedResults:
    ...  # late-bind run_id + open_positions unchanged
    balance = await self._broker.get_balance()
    current_equity = balance.available_balance
    total_commission = sum(
        f.commission for o in self._orders_by_id.values() for f in o.fills
    )
    metrics = PerformanceCalculatorDomainService.build(
        closed_trades=self._trades,
        equity_curve=self._equity_curve,
        initial_capital=self._initial_capital,
        current_equity=current_equity,
        total_commission=total_commission,
        start_date=self._config.start_date,
        end_date=self._config.end_date,
        periods_per_year=periods_per_year,
        returns_curve=self._mtm_curve or None,
    )
    ...  # persisted_curve + config_snapshot + BacktestResult + CollectedResults unchanged
```
`def finalize` → `async def finalize`.

### 8. `backtest_app_service.py`
- Import: `from pocketquant.engine.backtest.backtest_report_app_service import BacktestReportAppService`.
- Ctor call (dòng ~87): `collector = BacktestReportAppService(config, config.initial_capital, broker=self._broker, run_id=run_id)`.
- 2 site `collected = collector.finalize(...)` → `collected = await collector.finalize(...)` (try + except block).
- `_mtm_on_bar` không đổi.

### 9. Docstring refs
- `collected_results.py`: "output of BacktestResultAppService.finalize()" → "BacktestReportAppService.finalize()".
- `backtest_sandbox_app_service.py:16`: "built by the ``BacktestResultAppService``" → "BacktestReportAppService".

## Compile check

```
ruff check src/pocketquant/engine/backtest/
pyright src/pocketquant/engine/backtest/backtest_report_app_service.py \
        src/pocketquant/engine/backtest/backtest_app_service.py
lint-imports   # 8 contracts — collector→IBrokerPort (core.domain) hợp lệ
```

## Parity reasoning (tại sao số không đổi)

| Giá trị | Cũ (shadow) | Mới (broker) | Bằng nhau? |
|---|---|---|---|
| realized equity point | `_current_equity` (init − Σcomm + Σpnl) | `broker.available_balance` (init − Σcomm + Σrealized_pnl_delta) | ✓ `event.pnl == realized_pnl_delta`, init chung |
| current_equity (finalize) | `_current_equity` cuối | `broker.available_balance` cuối | ✓ |
| total_commission | `_total_commission` (Σ fill comm) | `sum(fill.commission)` | ✓ cùng nguồn `result.commission` |
| max_drawdown | cummax(realized values) | cummax(realized values, broker-sourced, cùng values) | ✓ |
| Sharpe/Sortino | MTM curve | MTM curve (không đổi) | ✓ |

## Todo
- [x] `git mv` + rename class `BacktestReportAppService`
- [x] Ctor: inject `IBrokerPort`, xoá `_current_equity`/`_peak_equity`/`_total_commission`
- [x] `on_fill`: bỏ shadow debit
- [x] `on_trade`: `await broker.get_balance()` → `_record_equity_point`
- [x] `_record_equity_point(timestamp, equity)`
- [x] `finalize` async + broker current_equity + sum commission
- [x] `backtest_app_service.py`: import + ctor + 2× `await finalize`
- [x] Docstring refs (collected_results, sandbox)
- [x] ruff + pyright + lint-imports xanh

## Success criteria
- Compile sạch; `git grep '_current_equity\|_peak_equity\|_total_commission'` → 0 hit trong src.
- `git grep BacktestResultAppService src/` → 0 hit.
- lint-imports 8 contract xanh.
