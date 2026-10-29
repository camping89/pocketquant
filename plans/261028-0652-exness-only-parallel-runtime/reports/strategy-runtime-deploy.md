# Strategy runtime deploy (D-3)

Phases 04-06 released to prod in the single `pocketquant-app` container, live trading off.

## Before

Read 2026-10-29 09:35 UTC, inside the deploy window (`WINDOW_OK`).

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1790         417           1        1697        1834
Swap:           7899         107        7792
camping89/pocketquant:latest
```

- Running image: `camping89/pocketquant:latest`, label `org.opencontainers.image.revision=f90991b9a2b0528011069d5c7237d74ac94baf87` (= `origin/master` before the release), started 2026-10-29T07:48:21Z.
- Rollback tag: `sha-f90991b` (present on Docker Hub for `pocketquant` and `pocketquant-web`).
- `EXNESS_LIVE_TRADING` inside the container: `false`.
- VPS NTP synchronized: `yes`.
- Code metrics ceiling: `max_tiny_share` 0.4750 -> 0.4790 (`tiny_share` 0.478 = 358/749).

## Release

- Owner answered yes to the D-3 [ASK]; `develop:master` pushed at 10:54 UTC (`WINDOW_OK`), HEAD `3905ff6b`.
- Develop CI run 40850678379: `success`. Master pipeline run 40861234348: `success`, verify verdict with 0 failures.

## After

Read 2026-10-29 10:58 UTC; container started 2026-10-29T10:57:13Z from image revision `3905ff6bf84f6b0f9128eb317180e8d6c29a18d8`.

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1768         479           1        1657        1857
Swap:           7899         107        7792
```

Boot counts (last 15 min):

```
loaded_open_positions=2
strategy_engine.took_over=1
paper_position_dropped_no_exits=0
strategy.warmup_incomplete=0
bar_app_service.seeded_from_redis=0
strategy.entry_skipped=0
```

- `strategy_engine.took_over`: strategies=4, paper_brokers=3, paper_positions=0, paper_dropped=0.
- Two started strategies replayed `warmup_bars=500` each.
- Verify: `take_over` and `close_due_bars` present (`True`), `/health` 200, 0 error lines.

## Pause

- Stored pause before the round trip: `{"live_trading":false,"daily_loss_cap":25.0,"max_lots":0.01,"leverage":1000.0,"risk_per_trade":0.1,"entries_paused":true}`.
- Pause left as set by the owner; the round trip was skipped.

## Two-hour watch

Read 2026-10-29 12:58 UTC, 2 h after the container start.

- Error lines (`application_start_failed|bar.close_timer_failed|strategy_on_bar_error|Traceback`): 0.
- `live.signal_latency` lines: 3, below the 5 needed for a p95. All three were 1m tick closes: T2-T0 172, 136 and 122 ms; `t0_t5_ms` 181, 144 and 124; `t0_t6_ms` 241, 206 and 182.

p95(T2-T0) ms: n/a
p95 t0_t5_ms: n/a

Counts (last 2 h):

```
strategy.entry_skipped=0
strategy.warmup_incomplete=0
exness.rate_limited=5
event_loop.lag=0
```

- The 5 `exness.rate_limited` lines are `exness.rate_limited_retry` WARNINGs, the only warnings besides 2 `integrity.repair.still_missing`.
