# Phase 03 report: 1d cascade for session calendars

Every calendar now cascades its 1d bar from stored 1m bars. The change is on `develop` and `master`, and the D-1 deploy ran green on prod.

## Commits and CI

- `5f6b8dc1` `style(scripts): wrap two long usage lines`. This fixes two E501 lines that existed before this phase (from commit `7695ccee`) in the epilogs of `scripts/audit_bar_quality.py` and `scripts/backfill/provider_bars.py`. The GATES rule `ruff check src tests scripts` failed on them. CI runs no ruff, so CI never caught them. Kongming advised fixing them in their own commit ahead of the feature commit.
- `ba6cba9a` `feat(market-data): cascade the daily bar for session calendars`.
- CI run on develop: `41315575975`, `completed success`, headSha `ba6cba9a2d6b45eb12a2f577d6344464c3a90de0`.
- GATES: `Contracts: 6 kept, 0 broken.`; ratchet exited 0 with no ceiling raise; `ruff check src tests scripts` printed `All checks passed!`.
- FULLSUITE: `4 failed, 1255 passed, 1 skipped, 50 warnings, 4 errors`. The non-timezone FAILED/ERROR count was `0`.

## Deviations

- `tests/engine_test/market_data/test_backfill_calendar_stamp.py` was missing from the Files list. Its test `test_direct_backfill_stamps_the_session_calendar` sent a 1d `auto` backfill and relied on the deleted override to route it to the direct path, so the first FULLSUITE run failed with `5 failed`. Following kongming's counsel, the test now passes `mode="direct"`, which keeps its intent.
- `test_backfill_daily_mode.py` lost its autouse `_fresh_logger` fixture together with its `structlog` and module imports. That fixture existed only for the deleted log-capture tests, so it became dead code. `test_cascade_aggregator.py` now unpacks `_, XAUUSD, _`, because `EURUSD` lost its last use.
- The order test runs once per calendar through `pytest.mark.parametrize` (`24x7`, `xauusd`). The expected red count was still `4 failed`.
- Runtime note, inferred from code and not measured: a 1d `auto` backfill of an Exness symbol through the backfill endpoint now cascades. That path fetches at most 5000 1m bars, which is about 3 daily bars. Deep Exness 1d history needs `mode=direct`, as crypto 1d already did. REST 1d stays in `SYNC_INTERVALS`.

## Deploy D-1

[ASK] sent to the coordinator in Vietnamese. The English intent: "Recommended: yes, because the change is independent of the rest and starts the one-week 1d comparison. Deploy D-1 now by pushing develop to master. It ships ba6cba9a feat(market-data): cascade the daily bar for session calendars; 5f6b8dc1 style(scripts): wrap two long usage lines; 8b07f292, c28809f1, f7bd6b53, 53553f8c, 1430946b and e4a998b8 (docs only). The only runtime change is the 1d cascade for Exness symbols. Nothing changes in strategies, schema or indexes. The style commit changes only help strings. Today is Sunday UTC, so the smoke check may have to wait for the session open."

Owner's answer: `yes`.

- Pushed `develop:master` at 2026-11-01T14:44:27Z; `origin/master` = `ba6cba9a2d6b45eb12a2f577d6344464c3a90de0`.
- Master run `41317673724`: `completed success`, headSha `ba6cba9a2d6b45eb12a2f577d6344464c3a90de0`.

d1_deployed_at=2026-11-01T14:50:40Z

### `free -m` before (2026-11-01T14:19:27Z)

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1693         349           1        1863        1927
Swap:           7899         364        7535
```

### `free -m` after (2026-11-01T14:51:11Z)

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1648         444           1        1812        1973
Swap:           7899         366        7533
```

### Smoke (run 2026-11-01T14:56:09Z, five minutes after the run completed)

XAUUSD and EURUSD had no 1m bars yet because it was Sunday UTC. `BTCUSD:EXNESS` runs on the `EXNESS_CRYPTO` session calendar. Its stored 1d bar for today now comes from the cascade, and it was written after the deploy.

```
XAUUSD:EXNESS m1_today=0 skipped
EURUSD:EXNESS m1_today=0 skipped
BTCUSD:EXNESS m1_today=896 d1_source=cascade d1_updated_at=2026-11-01 14:55:17.543000+00:00
checked=1 bad=0
```

## Unresolved questions

- None.

Result: PASS
