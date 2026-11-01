# Phase 01 report: Spike A, data path

S1-S3 are `go`; S4 backtest cost is `no-go` and goes to the owner at Phase 02. Every Task Verify passed.

## Facts

- Task 01.1 commit: `1430946b` (`docs(plans): plan the move to multi-timeframe strategies`), pushed to `origin/develop`.
- Spike worktree: `../pocketquant-spike` on local branch `spike/mtf`, started from `1430946b`. It stays for Phase 02.
- Measurement run: 2026-11-01T13:11:46Z UTC. Results are in `spike-go-no-go.md` under `## Measurements`. The SSH key file was removed after the run.

## Verify outputs (Tasks 01.4-01.6)

```
01.4: 2 passed, 4 warnings in 5.35s
01.5: 4 passed, 2 warnings in 6.17s
01.6: spike_cost find_calls=900 rollovers=900 t_mtf_s=9.57 t_stf_s=1.17  (grep count 1)
```

## Decisions

| piece | result |
|---|---|
| S1 subscription key | go |
| S2 context in live, warm-up, backtest | go |
| S3 one read per rollover | go |
| S4 backtest cost | no-go: find bound met (900 <= 902); time bound missed (9.57 s against a 2.34 s limit) |

## Advisory counsel

- `kongming` reviewed S4 and the phase. Its advice was to record S4 as `no-go` exactly as measured, without building a variant, because an incremental read still makes one Mongo round trip per rollover (about 3 ms) against the 1.3 ms per rollover the bound allows. That figure is kongming's inference from the measured window series.
- It found no test that would pass with a look-ahead bug. It flagged two points for the build: filter at `instant` rather than `window_start`, and test the re-query-on-miss path that the `complete` flag needs.

## Traps found

See `spike-go-no-go.md` `## Traps found`. The main ones: the reconcile service builds `StrategyConfig` without `intervals`; the old triple index collides on documents without `interval`; `find` returns the partial current bucket; the BTCUSD cascade lag p99 reaches 257.5 s on 1h.

## Deviations

- The red step failed first on the sandbox signature and on `KeyError: 'interval'`, not on `KeyError: 'context'`.
- The spike tests use their own `tests/spike_test/conftest.py` (settings, `app_client`, `database`), because those fixtures live in per-suite conftests.
- Extra S4 evidence was collected: read-limit runs at 100 and 40 bars, and one cProfile run. The recorded row uses the plan's run at the 500-bar limit.

## Unresolved questions

- S4: does the owner accept the cost, change the bound, or ask the build to prefetch and slice the context in the backtest, as warm-up already does?

Result: PASS
