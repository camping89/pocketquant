---
phase: 4
title: "Unit tests"
status: completed
priority: P1
effort: "3-4h"
dependencies: [2, 3]
---

# Phase 4: Unit tests

## Overview

Two unit-test files: one for HitNRun2 strategy logic, one for PaperBroker SL/TP auto-fill. Both run without DB / event loop dependencies beyond `asyncio`.

## Requirements

- All tests deterministic — no real time, no network, no DB.
- Synthetic OHLCV fixtures small enough to debug by eye (warm bars + a few crafted entry/exit bars).
- Cover happy path + edge cases listed below.

## Architecture

```
tests/
├── pocketquant-core/tests/unit/concepts/strategy/
│   ├── __init__.py                       # NEW
│   └── test_hitnrun2.py                   # NEW
└── pocketquant-core/tests/unit/infrastructure/brokers/
    ├── __init__.py                       # NEW if missing
    └── test_paper_broker_sl_tp_fill.py   # NEW
```

Test helpers in each file (no shared conftest):

```python
def _make_bar(idx, base=100, h=None, l=None, c=None):
    """Build dict bar for strategy.on_bar feeding."""
    return {
        "high": h if h is not None else base + 1,
        "low":  l if l is not None else base - 1,
        "close": c if c is not None else base,
        "open": base,
        "volume": 1.0,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=idx),
        "symbol": "BTCUSDT:BINANCE",
        "interval": "1m",
    }

def _make_strategy(direction="both", entry=240, sl=480, tp=60, max_loss=0.01, min_profit=0.02):
    cfg = StrategyConfig(
        id="hitnrun2-test",
        name="Test",
        symbol="BTCUSDT:BINANCE",
        interval="1m",
        parameters={
            "entry_lookback_bars": entry,
            "sl_lookback_bars": sl,
            "tp_lookback_bars": tp,
            "max_loss_pct": max_loss,
            "min_profit_pct": min_profit,
            "direction": direction,
        },
    )
    s = HitNRun2Strategy(cfg)
    asyncio.run(s.on_start())
    return s
```

## Related Code Files

**Create:**
- `packages/pocketquant-core/tests/unit/concepts/__init__.py` (if missing)
- `packages/pocketquant-core/tests/unit/concepts/strategy/__init__.py`
- `packages/pocketquant-core/tests/unit/concepts/strategy/test_hitnrun2.py`
- `packages/pocketquant-core/tests/unit/infrastructure/brokers/__init__.py` (if missing — check first)
- `packages/pocketquant-core/tests/unit/infrastructure/brokers/test_paper_broker_sl_tp_fill.py`

## Implementation Steps

1. Verify `tests/unit/concepts/` and `tests/unit/infrastructure/brokers/` exist (and add `__init__.py` if missing — match repo convention).
2. Write `test_hitnrun2.py` with these tests:
   - `test_warmup_returns_none_until_sl_lookback_full` — feed 479 bars (sl_lookback=480 default), all return None.
   - `test_long_entry_on_breakdown_below_4h_low` — feed 500 bars where lows[-481:-1] all == 100, then current bar close=99 → signal LONG, entry_price=99.
   - `test_short_entry_on_breakup_above_4h_high` — mirror.
   - `test_sl_capped_at_max_loss_pct_when_8h_low_too_far` — sl_lookback lows include 50 (8h low), entry=100 → uncapped SL = 50 → expected SL = max(50, 100*0.99=99) = 99.
   - `test_sl_uses_8h_technical_when_within_cap` — sl_lookback lows include 99.5 (within 1%), entry=100 → SL = max(99.5, 99) = 99.5.
   - `test_tp_uses_min_profit_pct_when_1h_high_too_close` — tp_lookback highs include 100.5, entry=99 → TP = max(100.5, 99*1.02=100.98) = 100.98.
   - `test_tp_uses_1h_technical_when_above_min_target` — tp_lookback highs include 105, entry=99 → TP = max(105, 100.98) = 105.
   - `test_direction_long_only_skips_short_signal` — direction="long", craft breakup bar → no signal.
   - `test_direction_short_only_skips_long_signal` — direction="short", craft breakdown bar → no signal.
   - `test_position_cap_blocks_second_signal_while_open` — after long fires, next breakdown bar returns None.
   - `test_on_fill_long_close_resets_state_for_next_entry` — open long, simulate fill with `OrderSide.SELL` → `_open_direction is None`; next breakdown emits signal.
   - `test_on_fill_short_close_resets_state` — mirror, fill `OrderSide.BUY`.
   - `test_current_bar_low_excluded_from_prev_window` — feed 480 bars with lows[-1] = 50 (would dominate min), but current bar is 481st → previous-window min should NOT include the new 50; only entry condition trips when 482nd bar breaks 50.

3. Write `test_paper_broker_sl_tp_fill.py` with these tests:
   - `test_no_event_bus_no_auto_fill` — instantiate `PaperBroker(event_bus=None)`, open a position via `submit_order`, no exit fires.
   - `test_long_sl_fills_when_bar_low_below_sl` — instantiate with FakeEventBus; open LONG @100 SL=98 TP=104 qty=1; publish `BarCompletedEvent(low=97, high=99)` → exit fill at ~98 (after slippage = 98 * 0.999 = 97.902), position closed, callback fired.
   - `test_long_tp_fills_when_bar_high_above_tp` — open LONG @100 SL=98 TP=104; bar(low=99, high=105) → exit at ~104.
   - `test_long_both_hit_in_same_bar_sl_wins` — open LONG @100 SL=98 TP=104; bar(low=97, high=105) → exit at ~98, only one fill emitted.
   - `test_short_sl_fills_when_bar_high_above_sl` — open SHORT @100 SL=102 TP=96; bar(high=103, low=99) → exit at ~102 (BUY side, +slippage).
   - `test_short_tp_fills_when_bar_low_below_tp` — open SHORT @100 SL=102 TP=96; bar(high=101, low=95) → exit at ~96.
   - `test_fill_clears_sl_tp_state_on_position` — after exit fill, position closed; subsequent bars don't double-fire.
   - `test_order_with_no_sl_tp_skipped` — open LONG @100 without SL/TP; any bar → no exit.

   Helper FakeEventBus: subscribe/publish in-memory; bypass real EventRegistry. Or use real `EventBus()` from `pocketquant.core.common.messaging`.

4. Run: `uv run pytest packages/pocketquant-core/tests/unit/concepts/strategy/ packages/pocketquant-core/tests/unit/infrastructure/brokers/test_paper_broker_sl_tp_fill.py -v` — all green.

## Success Criteria

- [ ] 14 strategy tests + 8 broker tests pass.
- [ ] No flaky timing (asyncio.sleep ≤ 1ms total per test).
- [ ] Files <200 lines each — split into multiple files if exceeded (e.g. `test_hitnrun2_entry.py`, `test_hitnrun2_exit.py`).
- [ ] Coverage: `uv run pytest --cov=pocketquant.core.concepts.strategy.services.hitnrun2 --cov=pocketquant.core.infrastructure.brokers.paper.paper_broker` reports ≥85% on the two modules.

## Risk Assessment

- **Risk:** Slippage math drift between test expectation and runtime. **Mitigation:** instantiate broker with `slippage_percent=0.0` for SL/TP tests; assert exact prices.
- **Risk:** Async/event-bus coupling makes tests bulky. **Mitigation:** call `broker._on_bar_completed(event)` directly when possible — skip pub/sub plumbing.
- **Risk:** PositionAggregate sl/tp field add (phase 2) breaks fields elsewhere. **Mitigation:** check `test_position_repository.py` / other position tests — Phase 2 step 9 covers reset.
