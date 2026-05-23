---
phase: 5
title: "Integration backtest tests"
status: completed
priority: P2
effort: "2-3h"
dependencies: [2, 3]
---

# Phase 5: Integration backtest tests

## Overview

End-to-end test: `BacktestAppService.run()` over synthetic OHLCV → assert hitnrun2 opens position, broker fills SL or TP, equity curve + metrics computed. Validates phase 2 + 3 + existing backtest engine together without MongoDB.

## Requirements

- **No MongoDB.** Use an in-memory `BarRepository` stub that yields a controlled `AsyncIterator[Bar]`.
- **No persistence.** Pass `persist_results=False` to `BacktestAppService` OR mock `BacktestRepository`.
- **Deterministic.** Same synthetic bars → same metrics across runs. Disable slippage (0) for exact equity assertions.
- **Two scenarios:** trending-down fires long signals, trending-up fires short signals. Each completes ≥1 round-trip.

## Architecture

```
fake_bar_repo (AsyncIterator) ──► HistoricalReplayAppService.replay()
                                       │
                                       ▼
                                 BarCompletedEvent
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                                                  ▼
      StrategyAppService                                   PaperBroker
       (hitnrun2 signal)                                  (SL/TP auto-fill)
              │                                                  │
              └────────► OrderAppService.submit ──► broker ──────┘
                                       │
                                       ▼
                              BacktestResultCollector.on_fill
                                       │
                                       ▼
                              metrics + equity_curve
```

Reuse the **real** `BacktestAppService` + `HistoricalReplayAppService` + `PaperBroker` + `StrategyAppService` wiring. Substitute only:
- `BarRepository` → fake.
- `BacktestRepository` → in-memory mock (just stores result).
- `EventBus` → fresh real instance.
- `PositionRepository` → in-memory mock.

## Related Code Files

**Create:**
- `packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py`

**Read for context:**
- `packages/pocketquant-backtest/tests/conftest.py` (existing fixtures)
- `packages/pocketquant-backtest/src/pocketquant/backtest/engine/backtest_app_service.py`
- `packages/pocketquant-backtest/src/pocketquant/backtest/handlers/run/handler.py` (composition reference)

## Implementation Steps

1. Inspect `tests/conftest.py` for reusable fixtures (event_bus, fake bar repo). Reuse if exists.
2. Build fake `BarRepository`:
   ```python
   class FakeBarRepository:
       def __init__(self, bars): self._bars = bars
       async def stream(self, symbol, interval, start_dt, end_dt):
           for b in self._bars: yield b
       async def find_datetimes(self, *a, **kw): return []
   ```
3. Build synthetic OHLCV generators:
   - `_downtrend_bars(n=600, start_price=100, slope=-0.05)` — 480 warmup bars at 100 ± 0.5, then 120 bars stepping down 0.05/bar with low<entry triggering breakdown. Each `Bar(symbol="BTCUSDT:BINANCE", interval="1m", open, high, low, close, volume, datetime=...)`.
   - `_uptrend_bars(...)` — mirror.
4. Write test class `TestHitNRun2Backtest`:
   - `test_backtest_long_round_trip_on_downtrend`:
     - Wire `EventBus`, `PaperBroker(event_bus=bus, slippage_percent=0)`, `StrategyAppService(...)`, hitnrun2 strategy injected.
     - Build `BacktestConfig(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1m", start_date, end_date, slippage_bps=0, commission_bps=0, parameters={"entry_lookback_bars":120, "sl_lookback_bars":240, "tp_lookback_bars":30, "max_loss_pct":0.01, "min_profit_pct":0.02, "direction":"long"})` — smaller lookbacks so synthetic bar count is manageable.
     - Call `BacktestAppService.run(config)` with `persist_results=False`.
     - Assert: `result.status == "completed"`, `result.metrics.total_trades >= 1`, `len(result.equity_curve) > 1`, no orphan open positions.
   - `test_backtest_short_round_trip_on_uptrend`: mirror.
   - `test_backtest_no_trades_on_choppy_market`: feed flat-ranged OHLCV (no breakdown/breakup) → `total_trades == 0`, `status == "completed"`.
5. Run: `uv run pytest packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py -v` — green.

## Success Criteria

- [ ] 3 integration tests pass.
- [ ] No real MongoDB / Redis touched (verified with `MONGO_URL=invalid uv run pytest ...` still passes).
- [ ] Each test runs <2s.
- [ ] `result.metrics.total_trades >= 1` in the two trend scenarios.
- [ ] `result.metrics.total_return` is a finite number (not NaN).

## Risk Assessment

- **Risk:** Wiring StrategyAppService manually is verbose. **Mitigation:** mimic `RunBacktestHandler._load_strategy_for_backtest` directly (already does the dishka-bypass injection). Test cleanup via `unload_strategy`.
- **Risk:** PositionRepository required by PositionAppService — even in tests. **Mitigation:** trivial in-memory mock with `save`/`find_open`/`get_by_strategy` returning empties.
- **Risk:** EventBus ordering: strategy must register handler before broker, so when bar fires, strategy submits entry first, then broker can check exit. **Mitigation:** assert order in test via subscriber counts, or rely on registration order in setUp.
- **Risk:** Synthetic bars trigger SL the same bar as entry → strategy emits LONG, broker checks SL on same bar's high/low. Need to ensure entry happens at `bar.close` (after high/low considered). PaperBroker.set_current_price uses bar.close before event — so entry fill price = bar.close. Then `_on_bar_completed` checks high/low. If `bar.low < sl` and `sl < close < tp`, SL triggers immediately. Could exit on entry bar — that's actually realistic. Document as expected behavior; tests assert "round-trip" without caring about same-bar vs cross-bar.
