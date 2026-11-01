# No Look-Ahead Rules

A strategy decision may use only data that existed when the decision was made. These rules apply to live trading, warm-up and backtests alike. A result that breaks them is not evidence.

## Higher-Timeframe Bars

- A multi-timeframe strategy decides on a lower-timeframe bar and reads higher-timeframe bars for context. It may read only higher-timeframe bars that had fully closed by the close of the bar it decides on.
- A bar is stamped with its start time (`Bar.datetime`). It closes at the end of its bucket, not at its stamp. Never join a higher-timeframe bar to the lower-timeframe bars that fall inside its own bucket.
- An open higher-timeframe bar is never read from storage or from the live in-progress feed. A partial higher-timeframe value is allowed only when the strategy builds it itself from lower-timeframe bars that have closed.
- A backtest must give the strategy the same view live trading gives it. It must not hand the strategy a bar or value that the live path could not have had at that moment.

## Why

- The common failure is a backtest in which a 5m bar at 10:00 sees that day's final daily close. The result looks better than any live run can be.
- Trading sources consistently describe this leak as real (checked on 2026-11-01 in public trading and backtesting articles). Claims about how much it inflates profit come from vendor blogs and are not evidence.

## Checks Before Trusting a Multi-Timeframe Backtest

1. For the first lower-timeframe bar of each higher-timeframe bucket, the strategy's higher-timeframe value must equal the previous bucket's close, not this bucket's close.
2. Check bars across the whole history, not only the end. Some leaks appear only at gaps and bucket boundaries.
3. Compare indicator values, not only entry flags.
4. Warm up long enough that every higher-timeframe indicator is defined before the first decision.
