# Deploy A (D-4): roles and leases

Deployed 2026-10-29. Prod `app` (container hostname `90c27c2e9ca3`) runs `APP_ROLES=api,worker,trader` on image revision e646b3b5.

## Before

- Owner approval: D-4 "Đồng ý" at 14:05 UTC (inside the Thursday 12:50-19:30 UTC window; `WINDOW_OK`).
- Pre-deploy review: kongming GO (`kongming-predeploy-roles-and-leases.md`). Two of its items were applied before the push: `on_lost` exits in a `finally` (bd5be1ed), and the rollback text keeps the config commit (edbe4bd9).
- A develop CI failure (a same-millisecond release/acquire race in `test_lease_repository.py`) was fixed with `$lte` in `LeaseRepository.acquire` (e646b3b5) after Failure Protocol counsel; develop CI run 40887817974 then succeeded in all three timezones.
- Config repo: `ENABLE_JOBS` removed and local profiles set to `APP_ROLES=api` (pocketquant-config 1e4c4f1).

free -m before (14:23 UTC):

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1771         442           1        1692        1855
Swap:           7899         107        7792
```

OOM check before: `OOM_OK`.

## Release

- Pushed `develop:master` at e646b3b5. Master run 40891079388 succeeded, and its verify step reported every check PASS.
- Container started at 2026-10-29T14:28:23Z.

## After

free -m after (14:30 UTC):

```
               total        used        free      shared  buff/cache   available
Mem:            3905        1777         470           1        1657        1849
Swap:           7899         107        7792
```

Task 7.8 Verify output:

```
OOM_OK
trader\.takeover( |$)=1
trader\.takeover_complete=1
scheduler\.started=1
lease\.acquired=2
lease\.lost=0
lease\.takeover_failed=0
trader\.standby=1
"role":"api,worker,trader"
"lease":"held"
"lease_renewed_age_s":1.1
2 trader,worker 2 90c27c2e9ca3
app_host=90c27c2e9ca3
```

Startup timings from the logs:
- `trader.standby`: `warmup_s=0.8` with 4 strategies.
- `trader.takeover`: `handover_gap_ms=None`. The previous image held no lease, so there was no release to measure.
- `strategy_engine.took_over`: `paper_brokers=3`, `paper_positions=2`, `paper_dropped=0`.
- `trader.takeover_complete`: `takeover_ms=22`.
- `scheduler.started` came 0.3 s after the worker lease was acquired.

Observation (not a Verify condition): one `binance_ws.error` (`server rejected WebSocket connection: HTTP 400`) at 14:28:34Z. `binance_ws.reconnecting delay=1.0` and `binance_ws.connected` followed at 14:28:35Z, with no further errors in the next 20 minutes. The cause is not verified.

## D17 probes (Task 7.9)

Probes ran 14:31:22-14:41:28 UTC (`pq-probe-trader`, `pq-probe-worker`; the poll printed `probes-done`).

Owners before (14:31:10 UTC):

```
2 trader,worker 2 90c27c2e9ca3
app_host=90c27c2e9ca3
```

Task 7.9 Verify output:

```
trader.standby trader=1 worker=0
lease.waiting trader=1 worker=1
lease.acquired trader=0 worker=0
trader.takeover trader=0 worker=0
exness.order_submitted trader=0 worker=0
position_opened trader=0 worker=0
position_closed trader=0 worker=0
orphan_backtest_recovery trader=0 worker=0
backtest_orphan_recovery trader=0 worker=0
orphan_jobs_recovered trader=0 worker=0
scheduler.started trader=0 worker=0
app_lost=0
probes_left=0
```

Owners after (14:41 UTC):

```
2 trader,worker 2 90c27c2e9ca3
app_host=90c27c2e9ca3
```

Both probes logged `application_stopped` on their 600 s timeout. The probe trader logged the same one `binance_ws.error` HTTP 400 at its start (14:31:35Z) as the prod `app` did, so it repeats on each start; the probe worker logged no error.

## Open items

- `binance_ws.error` HTTP 400 on the first Binance WS connect after every start; it reconnects after 1 s. The cause is not verified, and no phase of this plan covers it.

Result: PASS
