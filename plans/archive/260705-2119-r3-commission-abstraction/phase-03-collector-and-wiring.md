# Phase 03 — Collector single-source + wiring (config/Settings → broker)

**Priority:** P2 · **Status:** completed · **Depends:** P02 · **Blocks:** P05

## Overview

Nối commission thật vào broker (bỏ formula post-hoc ở collector) + đưa `commission_bps` (backtest) và `Settings.paper_commission_percent` (live paper) tới broker. Sau phase này broker mới thực sự nhận commission > 0.

## Requirements

- `BacktestResultAppService.on_fill`: `commission = result.commission` (bỏ `fill_price*fill_qty*self._config.commission_percent`). Số **không đổi** (cùng giá trị) — chỉ đổi nguồn.
- `sandbox.create_broker(commission_bps=…)` → `PercentageCommissionModel(bps=commission_bps)`.
- `dispatch.run_single`: truyền `config.commission_bps` vào `create_broker`.
- `Settings.paper_commission_percent: float = 0.0004`.
- `execution.py` `default_broker_config` + `broker_factory` paper branch → dựng `PercentageCommissionModel` cho live paper.

## Related code files

- **MODIFY** `src/pocketquant/engine/backtest/backtest_result_app_service.py` (on_fill: đọc `result.commission`)
- **MODIFY** `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` (`create_broker` +`commission_bps`)
- **MODIFY** `src/pocketquant/engine/backtest/backtest_dispatch.py` (truyền `config.commission_bps`)
- **MODIFY** `src/pocketquant/core/config.py` (`Settings.paper_commission_percent`)
- **MODIFY** `src/pocketquant/app/di/execution.py` (`default_broker_config` +`commission_percent`)
- **MODIFY** `src/pocketquant/app/di/broker_factory.py` (paper branch dựng model)

## Implementation steps

1. **Collector** (`backtest_result_app_service.py` ~dòng 103):
   ```python
   commission = result.commission        # broker single-source (was: fill_price*fill_qty*config.commission_percent)
   self._total_commission += commission
   self._current_equity -= commission
   ```
   - `_config.commission_percent`/`commission_bps` còn dùng chỗ khác? Grep: dòng ~442 persist `"commission_bps": self._config.commission_bps` (metadata) — GIỮ. Chỉ bỏ chỗ TÍNH.

2. **sandbox.create_broker** (~dòng 110): thêm param + dựng model:
   ```python
   def create_broker(self, *, initial_balance, slippage_percent=0.0, commission_bps=0.0, currency="USDT"):
       broker = PaperBrokerAdapter(
           initial_balance=initial_balance,
           slippage_percent=slippage_percent,
           currency=currency,
           commission_model=PercentageCommissionModel(bps=commission_bps),
           ...
       )
   ```
   Import `PercentageCommissionModel` từ `core.domain.trading`.

3. **dispatch.run_single** (~dòng 91): `commission_bps=config.commission_bps` vào `create_broker(...)`.

4. **Settings** (`config.py`, cạnh `paper_slippage_percent` dòng ~72):
   ```python
   paper_commission_percent: float = 0.0004   # 4 bps; R7 tune value + currency
   ```

5. **execution.py** `default_broker_config` (~dòng 66): thêm
   ```python
   "commission_percent": settings.paper_commission_percent,
   ```

6. **broker_factory** paper branch (~dòng 31): dựng model từ config (đổi percent→bps tại boundary — comment rõ để tránh unit bug):
   ```python
   commission_bps = config.get("commission_percent", 0.0) * 10_000  # Settings dùng fraction; model dùng bps
   return PaperBrokerAdapter(
       initial_balance=config.get("initial_balance", 100_000.0),
       slippage_percent=config.get("slippage_percent", 0.001),
       fill_delay_ms=config.get("fill_delay_ms", 50),
       currency=config.get("currency", "USDT"),
       commission_model=PercentageCommissionModel(bps=commission_bps),
       event_bus=self._event_bus,
   )
   ```

## Todo

- [x] Collector đọc `result.commission` (giữ metadata persist `commission_bps`)
- [x] `create_broker` +`commission_bps` → model
- [x] `dispatch` truyền `config.commission_bps`
- [x] `Settings.paper_commission_percent=0.0004`
- [x] `execution.py` config +`commission_percent`
- [x] `broker_factory` dựng `PercentageCommissionModel` (percent→bps, comment)
- [x] compile + `pyright`

## Success criteria

- Backtest: broker `_balance` cuối run = collector `_current_equity` (cùng trừ commission, cùng value) — 2 ledger hội tụ (fix đầy đủ ở R5).
- Live paper: broker nhận commission 4bps từ Settings.
- Metadata persist `commission_bps` không đổi.
- `commission_bps` không còn được collector dùng để TÍNH.

## Risks

- **Unit bug** percent↔bps ở factory (0.0004 × 10000 = 4 bps). Comment + P05 test khẳng định factory-built broker tính đúng.
- Test backtest cũ assert metrics: value commission giống trước (formula tương đương) → metrics KHÔNG đổi; chỉ broker balance test đổi (P05).
