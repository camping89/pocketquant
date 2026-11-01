# Spike go/no-go

## Measurements

Run at 2026-11-01T13:11:46Z (UTC), read-only PRODPY script over the last 72 h of `source: cascade` bars on every `:EXNESS` tracked symbol. Lag is `updated_at - (datetime + step)` in seconds, for buckets that ended at least 5 minutes before the run.

This lag is evidence only. It sets no constant and gates nothing (synthesis D1).

```
lag BTCUSD:EXNESS 5m n=862 p50_s=17.6 p99_s=21.1 max_s=617.5 share_le_40s=0.994
lag BTCUSD:EXNESS 15m n=287 p50_s=17.7 p99_s=138.5 max_s=317.5 share_le_40s=0.990
lag BTCUSD:EXNESS 1h n=71 p50_s=18.0 p99_s=257.5 max_s=257.5 share_le_40s=0.972
lag BTCUSD:EXNESS 4h n=17 p50_s=18.3 p99_s=138.5 max_s=138.5 share_le_40s=0.941
lag EURUSD:EXNESS 5m n=378 p50_s=19.0 p99_s=21.9 max_s=23.0 share_le_40s=1.000
lag EURUSD:EXNESS 15m n=127 p50_s=19.1 p99_s=22.3 max_s=23.1 share_le_40s=1.000
lag EURUSD:EXNESS 1h n=31 p50_s=19.2 p99_s=23.1 max_s=23.1 share_le_40s=1.000
lag EURUSD:EXNESS 4h n=8 p50_s=19.5 p99_s=23.1 max_s=23.1 share_le_40s=1.000
lag XAUUSD:EXNESS 5m n=369 p50_s=19.6 p99_s=22.6 max_s=23.9 share_le_40s=1.000
lag XAUUSD:EXNESS 15m n=123 p50_s=19.6 p99_s=22.8 max_s=24.0 share_le_40s=1.000
lag XAUUSD:EXNESS 1h n=30 p50_s=19.9 p99_s=24.0 max_s=24.0 share_le_40s=1.000
lag XAUUSD:EXNESS 4h n=8 p50_s=20.1 p99_s=24.0 max_s=24.0 share_le_40s=1.000
```

## Go/no-go

| piece | go/no-go | evidence | carried to phase |
|---|---|---|---|
| S1 subscription key | go | `test_two_interval_sets_sharing_the_entry_interval_both_insert`: POST `["15m","1h"]` and `["15m","4h"]` for `probe` on `BTCUSDT:BINANCE` both return 201. `test_a_repeated_interval_set_is_a_conflict`: a second `["15m","1h"]` returns 409 from `DuplicateKeyError` on the unique index `ix_subscriptions_dedup_intervals` over `(strategy_code, symbol, intervals_key)`. Verify: `2 passed`. | 06 |
| S2 context in live, warm-up, backtest | go | Seed: 1m bars 2026-01-05 00:30-01:59, 1h bars 2026-01-04 23:00, 2026-01-05 00:00 and a partial 01:00. `test_live_first_entry_bar_of_an_hour_sees_the_previous_hour`: entry bars 00:59 and 01:00 see last 1h bars 23:00 and 00:00. `test_warm_up_contexts_match_the_live_rule`: start at 01:31:25, 61 replayed bars (00:30-01:30), each sees `floor_hour(t) - 1h`, never 01:00. `test_backtest_contexts_match_the_live_rule`: 90 bars (00:30-01:59), each sees `floor_hour(t) - 1h`. Verify: `4 passed` (with S3). | 07, 08 |
| S3 one read per rollover | go | `test_context_reads_once_per_rollover`: live entry bars 00:58-01:02 make exactly 2 `BarRepository.find` calls for `1h` (two windows). | 07 |
| S4 backtest cost | no-go | `spike_cost find_calls=900 rollovers=900 t_mtf_s=9.57 t_stf_s=1.17`. The find bound (`<= 902`) is met. The time bound (`t_mtf_s <= 2 * t_stf_s`) is missed by about 8x. | 02 (owner decision) |

### S4 diagnosis

- With the context read limit at 500, 100 and 40 bars, `t_mtf_s` was 9.53, 5.08 and 4.24 against `t_stf_s` of about 1.1 (local Docker Mongo).
- A cProfile of the 500-bar MTF run attributes 8.6 s of 9.6 s to `_context_for`, 7.6 s to `BarRepository.find`, and 4.9 s to 294,740 `Bar.from_mongo` calls. Each rollover re-reads and re-parses the whole window.
- Per rollover the overhead is about 9.3, 4.3 and 3.4 ms for the three limits. The bound allows about 1.3 ms per rollover (1.17 s / 900). Inference (kongming counsel): the floor of about 3 ms is the cost of one Mongo `find` round trip, so any design with one read per rollover misses this bound. An incremental-append variant was not measured, because it still reads once per rollover.
- The probe does no work, so the STF baseline is close to the bare replay cost. This makes the ratio as harsh as it can be.
- The remedy, for example a backtest-side prefetch and in-memory slice as warm-up already does, or a different bound, is the owner's decision at Phase 02.

## Traps found

- The red step did not fail with `KeyError: 'context'` first. It failed on `build_backtest_sandbox()` taking no arguments and on `KeyError: 'interval'` in `_config_from_dict`, because a payload with only `intervals` has no `interval`.
- `Subscription.interval` is still read by `strategy_reconcile_app_service.py:149` and `strategy_query_service.py:49`. The spike kept a property `interval = intervals[0]`. The reconcile service also builds `StrategyConfig` without `intervals`, so the real live path would hand strategies an empty context until it passes them.
- The old unique index `ix_subscriptions_dedup_triple` covers `interval`. New documents carry no `interval`, so two of them would collide on null under the old index. It must be dropped before new documents land, as the prod migration verdict says.
- `BarRepository.find(end_date=instant)` uses `$lte`, so the read returns the partial current bucket. The closed filter must remove it, and the tests seed a partial 01:00 1h bar to catch that.
- The spike cache filters the window's bars at `window_start`, not at `instant`. This is the same on the 24/7 grid the tests use. It was not checked for Exness session calendars, so the build should filter at `instant` per the verdict and use the window only as the cache key.
- The spike cache is `(window_start, bars)` with no `complete` flag. Prod BTCUSD cascade lag reaches p99 257.5 s on 1h, longer than a 1m entry bar, so the verdict's re-query on a miss will read more than once per rollover. That needs its own test; the S3 test asserts exactly 2 reads.
- The governance rule says a higher bar may be read once it closed by the close of the decided bar. The verdict uses the decided bar's start, which is stricter by one entry bar at each rollover (the 00:59 1m bar does not see the 00:00 1h bar). This is safe against look-ahead and matches the measured lag of about 18-20 s.
- All three paths ran through `build_backtest_sandbox`; the real live wiring (dishka engine and reconcile loop) was not exercised.
- cProfile counts each coroutine resumption as a call, so `ncalls` for coroutines is inflated; only `tottime` and `cumtime` were used.

## Kept vs rewritten

- Kept: this report, the numbers above, and the test scenarios as prose.
- Rewritten: all code and tests. Nothing from `spike/mtf` is cherry-picked, merged, checked out by path or copied into `develop`.
