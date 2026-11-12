---
phase: 3
title: "Triple Screen stop and target parameters"
status: pending
priority: P1
effort: "4h"
dependencies: []
---

# Phase 3: Triple Screen stop and target parameters

## Goal
- **Rename:** `stop_lookback` becomes `stoploss_lookback`, counted in bars of the next higher timeframe.
- **Add:** `takeprofit_lookback`, `entry_buffer_atr`, `stoploss_buffer_atr` and `min_stop_atr`.
- **Defaults:** the new parameters default to off.

## Facts (verified by kongming on 2026-11-12, report section 3)
- **Context timing:** the strategy reads higher-timeframe bars that closed before the start of the entry bar (`strategy_app_service.py`, `_context_at`). So a window of closed middle bars would miss up to four newer entry bars.
- **Parameter checks:**
  - An unknown parameter key is rejected on submit (`core/domain/strategy/services/__init__.py`).
  - A default typed `int` rejects a float value (`_type_matches`).
- **Web form:** it is generic and renders the `DEFAULTS` the API returns.
- **Stored data:**
  - 47 stored backtest runs carry `stop_lookback`; they stay as records.
  - At 14:32 on 2026-11-12, no paper subscription carried it.

## Definitions
`ratio` = seconds(middle) / seconds(entry), which is 4 for `15m,1h,4h`. `ATR` = Wilder ATR(14) on closed top-interval context bars. `high` and `low` are those of the entry bar that just closed.

| Step | Long | Short |
|---|---|---|
| 1. Entry, stop order | `high + entry_buffer_atr x ATR` | `low - entry_buffer_atr x ATR` |
| 2. Swing stop | lowest low of the last `stoploss_lookback x ratio` closed entry bars, minus `stoploss_buffer_atr x ATR` | highest high of those bars, plus `stoploss_buffer_atr x ATR` |
| 3. Minimum stop | `sl = min(step 2, entry - min_stop_atr x ATR)` | `sl = max(step 2, entry + min_stop_atr x ATR)` |
| 4. Risk | `entry - sl` | `sl - entry` |
| 5. TP, `exit_mode=sl_tp` only | `max(highest high of the last takeprofit_lookback x ratio entry bars, entry + risk_reward x risk)` | `min(lowest low of those bars, entry - risk_reward x risk)` |

- **Market entry:** the entry is the close. The entry offset does not apply.
- **`exit_mode=strategy`:** no TP. The tide flip exits, and `takeprofit_lookback` is ignored.
- **`takeprofit_lookback=0`:** gives today's TP exactly.
- **ATR warm-up:** while ATR is undefined and any ATR parameter is non-zero, the top interval counts as warming up.

## Files to Create / Modify
- Modify: `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`: `DEFAULTS`, validation, one deque sized to the larger window, one ATR helper with two callers, the rules above, and the snapshot readings (ATR, swing stop, final SL, TP).
- Modify or create: the Triple Screen tests (find them with `grep -rl triple_screen tests`).
- Modify: `docs/governance/strategy-assessment-rubric.md`. G2 passes on in-sample t >= 3.0; report the DSR but do not gate on it (owner decision 4).

## Tasks & Steps
1. **Rename.** Change `stop_lookback` to `stoploss_lookback` (default 2) and make it count middle-interval bars. Delete the old key; keep no alias.
2. **New parameters.** Add `takeprofit_lookback` (default 0), and `entry_buffer_atr`, `stoploss_buffer_atr` and `min_stop_atr` (defaults `0.0`). Validate each as >= 0.
3. Implement the five steps above.
4. **Stored subscriptions.** Count the subscriptions whose parameters hold `stop_lookback`, on prod and read-only. If the count is not 0:
   - back up `subscriptions` with `mongodump`;
   - rename the key and divide its value by `ratio` in one reviewed update, during phase 5.
5. **Tests**, named by the rule they prove:
   - Defaults, with `stoploss_lookback=20` on `15m,1h,4h`, give the same signals as `stop_lookback=80` did. Use a fixed bar fixture.
   - The window spans `N x ratio` entry bars and includes the signal bar.
   - The entry offset moves the stop order by `X x ATR`, on both sides.
   - The stop-loss offset moves the swing stop outward by `X x ATR`, on both sides.
   - The minimum stop widens a closer stop and keeps a farther one.
   - The TP takes the farther of the swing level and the `risk_reward` floor, and is ignored under `exit_mode=strategy`.
   - ATR uses only closed top-interval bars (no look-ahead).
   - The old key `stop_lookback` is rejected on submit, and a negative value is rejected.
   - A float value is accepted for each ATR parameter.
6. Update the rubric's G2 row and its decision text.

## Verification
- `uv run pytest <triple screen test files> -q`, and pyright on the strategy package.

## Risk and rollback
- This changes strategy logic, which the owner approved on 2026-11-12.
- The default `stoploss_lookback=2` changes running paper subscriptions from 5 to 8 entry bars of lookback (owner decision 3).
- Rollback: revert the commit. For subscriptions, restore the `subscriptions` dump if step 4 updated any.
