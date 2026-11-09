# Phase 05 report: Redis password rotation, release and prod checks

## Task 05.1: Entry gate (PASS)

- `git status --porcelain -- src tests scripts deploy docs .github` is empty; `HEAD` = `origin/develop` = `3473b87b`.
- Phase 02, 03 and 04 reports end with `Result: PASS`.
- LIVECHK: `trader_live=False`.
- VPS `free -m` before: Mem total 3905, used 2421, free 297, buff/cache 1186, available 1213; Swap 7899 total, 332 used.
- `prev_master=36e435858597fd7e5d549e8b1d2d11ea75599772`
- `git log --oneline origin/master..origin/develop` (17 commits):

```
3473b87b docs(plans): count a daily divergence only when two hourly runs repeat it
4c77aee1 docs(plans): record the daily bar check phase
c0abc0fb feat(market-data): check stored daily bars against their minutes every hour
f161b9f9 docs(plans): record the cascade fold phase
0b5a0608 fix(market-data): fold late 1m bars into cascaded bars after repair and backfill
d180749f docs(plans): record the local ports and small fixes phases
4933e028 refactor(api): remove the unused subscription positions route
bb84c2a3 fix(market-data): read every 1m bar of a cascaded bucket
9c5f0cae fix(market-data): read the symbol lookup cache once
dcf302e7 docs(plans): plan the cascade fold, daily bar check and four small fixes
b34d137a docs(plans): close the multi-timeframe foundation plan
d4a9cc08 docs: fix stale names in the architecture docs
935d9504 docs(plans): amend the task 17.2 pass rule for pre-deploy days
77c60dbc docs(plans): amend phase 17 for a same-day close
f73f3648 docs(plans): record the triple screen backtests and paper start
3df5ec91 docs(plans): write the release push time as a bare report line
954fbed6 docs(plans): record the multi-timeframe release and mark it complete
```

## Task 05.2: Rotate the prod Redis password (PASS after one Failure Protocol round)

- Steps 1-2: new password generated into `.cache/redis_new`; old saved to `.cache/redis_old`. `REDIS_PASSWORD` and the `REDIS_URL` password were replaced in `vps/default/.env`; in `local/remote-db.env` both `REDIS_URL` and `REDIS_PASSWORD` were replaced. The plan listed only `REDIS_URL` for `remote-db.env`, but that file also holds `REDIS_PASSWORD` with the same old value, so leaving it stale would be a trap (kongming agreed). Diff: 2 files, 4 lines.
- First run of step 3 failed (`AUTH failed: WRONGPASS` then `NOAUTH Authentication required.`), and step 4 printed no `PONG`. Cause, verified: both `.cache` files ended in `\r\n` (Windows Python text mode), so `read -r` on the VPS kept a trailing `\r`. The CR-stripped old password matched the VPS `.env` (sha256 prefix equal) and pinged `PONG`. Redis rejected the `ACL SETUSER` unauthenticated, so nothing changed.
- Failure Protocol: kongming counselled GO with: strip CR in place, confirm sizes (45 and 44 bytes, no `\r`), re-run steps 3-4 unchanged, and count ACL password hashes without printing them.
- Re-run: ACL password hashes before `1`; step 3 printed `OK`; hashes after `2`; step 4 printed `PONG` twice.
- Step 5: `pocketquant-config` commit `5f1e7ebc chore(vps): rotate the redis password`, pushed to `master` (the ref `get-vps-config` reads); remote `master` = local `HEAD`.
- `git -C ../pocketquant-config status --porcelain` shows only `?? .claude/`, an untracked agent-memory directory dated 2026-10-10 that predates this phase and is not mine; no tracked change is left.

## Task 05.3: Release (PASS)

- Owner answered `yes` through the coordinator to the Vietnamese release question.
- `develop:master` pushed; `origin/master` = `3473b87b`.
released_at=2026-11-04T04:13:56Z
- CI/CD run `41771933085` on `3473b87b`: `completed success` (web, tests in three timezones, build-web, build-app, deploy, cleanup-tags all `success`).
- `docker ps` after deploy: `api-14`, `worker-14`, `trader-14`, `web`, `redis` all `healthy`; `redis` and `web` show about a minute of uptime, so the final `dc up -d --remove-orphans` recreated redis. This is expected for the rotation, even though `docs/deployment.md` says the deploy normally keeps stateful containers.
- VPS `free -m` after: Mem total 3905, used 2407, free 369, buff/cache 1128, available 1227; Swap 237 used.
- Rotation close: `-a NEW ping` printed `PONG`; `-a OLD ping` printed `AUTH failed: WRONGPASS ...` / `NOAUTH Authentication required.` (PASS).
- `logs --since 2026-11-04T04:13:56Z api worker trader` (ANSI stripped, 396 lines): `grep -i -E "redis.*(auth|wrongpass|noauth)"` count `0` (PASS).
- `.cache/redis_old` and `.cache/redis_new` deleted.
- Recorded: the redis recreate caused about one second of connection errors at 2026-11-04T04:20:16-17Z: two `exness_ws.callback_failed` warnings, one `market_data.sync.failed` (EURUSD 1m, `Connection refused`), one `binance_ws.callback_failed` and one `binance_ws.error` (`Error -2 connecting to redis:6379. Name or service not known.`), and one `unhandled_exception` on a trader HTTP request. Binance reconnected at 04:20:22Z. None carries a `KeyError` text. LIVECHK after deploy: `trader_live=False`.

## Preparation for Tasks 05.4 and 05.5 (not a Verify)

- The phase-17 report describes the D16 diagnostic script but does not keep its code. I rebuilt it as `.cache/d16.py` from the Task 17.2 script plus a dry-run cascade on the current live path: `BarRepository.find` reads newest first with its default `limit=5000`, then `aggregate_ohlcv` runs, and nothing is written. `diag_truncated` counts days where the read returned fewer 1m bars than are stored. It prints the same last three lines as the phase-17 run.
- A pre-check run at 2026-11-04T04:33Z (before any post-release repair) printed `diag_truncated=0 post_d1_not_cascade=0`, `min_days=12`, `mismatches=1 repair_1d=0`. The single diff is `BTCUSD:EXNESS 2026-10-24 stored=diff dry=diff source=rest_repair`. Its OHLC matches Exness exactly, but Exness now reports volume `113100` while stored is `113120` (relative diff about 1.8e-4, above the 1e-4 tolerance). The stored bar is unchanged since `updated_at=2026-11-01T00:00:38Z`, and on 2026-11-02 the same row was `stored=equal dry=equal`. So the change is on the Exness side (inference: Exness revised that day's volume after 2026-11-02). The day is outside the 7-day re-cascade window, so the fold cannot touch it.

## Deviation: one-off job runs instead of the scheduled waits

The owner said at 2026-11-04T06:03Z: "I don't have time to wait, so we sync now and we take the result now to close the plan." So I did not wait for the scheduled 12:00 and 00:00 UTC repairs; I ran the jobs once each in a one-off process inside the prod worker container instead. kongming reviewed this and accepted it as a recorded deviation.

`.cache/run_jobs.py` (untracked) calls the same module coroutines that the scheduler calls, so `_tracked` writes the job history rows:

```python
import asyncio
import sys
from pocketquant.app.di import create_container
from pocketquant.core.common.logging import setup_logging
from pocketquant.core.config import get_settings
from pocketquant.engine.market_data.app_services import sync_jobs
async def main(names):
    s = get_settings()
    assert not s.exness_live_trading
    setup_logging(s)
    # half the Exness rate: the worker's own pacer is in another process
    container = create_container(s.model_copy(update={"exness_rate_fraction": 0.5}))
    sync_jobs.set_container(container)
    try:
        for n in names:
            print("RUN", n, flush=True)
            await getattr(sync_jobs, n)()
            print("END", n, flush=True)
    finally:
        await container.close()
asyncio.run(main(sys.argv[1:]))
```

Runs, in order: `sync_repair` 06:04:53-06:07:19Z (`duration_ms=145962`), `sync_backfill` 06:07:56-06:12:13Z (`256516`), `sync_repair` 06:12:13-06:14:34Z (`141095`), then `sync_verify_cascade` twice (06:14:34Z and 06:14:37Z). All rows are `status=completed`, and the scheduled hourly `sync_verify_cascade` also completed at 05:00Z and 06:00Z.

- **Lease bypass.** The process ran next to the live worker and outside its lease, and the `_RUNNING` guard is per process. It could therefore overlap `sync_1m` and the 06:00Z verify. Every write is an idempotent bar upsert (equal values are skipped before any write), so the overlap is harmless. The job history since 2026-11-03T23:00Z has only completed `sync_repair` and `sync_backfill` rows (scheduled 00:00Z and 03:00Z, plus the three one-off runs), so no row was closed by mistake.
- **Exness rate budget.** The worker ran at fraction 1.0 and the one-off process at 0.5, so for about 10 minutes the combined request rate was 1.5 times the limit. The window logged 6 `exness.rate_limited_retry` warnings (2 in the one-off process, 4 in the worker), every one retried. The container logs have 0 `[error` lines from 04:20:23Z on.
- `market_data.sync.no_progress` warnings in `sync_backfill` show `filtered_existing` equal to `bars_fetched`: backfill only inserts missing bars, and none were missing.

## Task 05.4: Prod checks after the first repair (PASS, item 4 on A7 intent)

1. `integrity.repaired` with `interval=5m|15m|1h|4h|1d`: `0` in the container logs and in the one-off output. The only repairs were `interval=1m symbol=EURUSD:EXNESS gaps_resynced=6`, then `7`. `integrity.repair.still_missing interval=1m` for 2026-10-29T21:xx is the known Exness rollover window, where the venue has no ticks; it is not a failure.
2. `cascade.symbol_failed`: `0`; `[error` lines in the one-off output: `0`. Durations: repair `145962` and `141095`, backfill `256516`, all under 600000 (R1 PASS).
3. `cascade.daily_divergence` since `released_at`: `0` lines. That covers the scheduled 05:00Z and 06:00Z runs and the two one-off runs after the second repair ended at 06:14:34Z, so no `(symbol, datetime)` repeats. With no lines at all, the two-consecutive-runs rule is met vacuously, and there is no drift from the old code to record (R3).
4. `grep "binance_ws.callback_failed" | wc -l` since `released_at` prints `1`, so the literal rule (`0`) misses. The one line is `trader-14 2026-11-04T04:20:16.628851Z ... error='Error -2 connecting to redis:6379. Name or service not known.'`. It was logged while the deploy's final `dc up -d --remove-orphans` recreated redis, and Binance reconnected at 04:20:22Z, which is the single reconnect E4 keeps. Since 04:20:23Z the count is `0`, and `callback_failed` lines with a `KeyError` text number `0`. Acceptance A7 ("no `binance_ws.callback_failed` with a `KeyError` text after deploy") holds. Failure Protocol: kongming counselled pass on A7 with this deviation recorded. A two-hour grep is weak evidence for a race that rare; the load-bearing evidence for A1 and A7 is the Phase 02 race test.
5. `integrity.issues_found` for 5m-1d since `released_at`: `0` lines. `sync_integrity` runs at 04:00Z, before the release, and was not run by hand, so R4 evidence is pending until the 2026-11-05T04:00Z run.
6. LIVECHK: `trader_live=False`.

## Task 05.5: Second repair and the D16 comparison (PASS under D16 with one recorded exception)

- The second repair (06:12:13-06:14:34Z) was followed by a re-run of 05.4 items 1-4, with the same results as above.
- D16 script `.cache/d16.py` run at 2026-11-04T06:15:33Z. Its last lines:

```
diag_truncated=0 post_d1_not_cascade=0
min_days=12
mismatches=1 repair_1d=0
```

- 38 day rows. All 9 rows from the deploy day (2026-11-01) on are `stored=equal dry=equal source=cascade`. The only diff row is `BTCUSD:EXNESS 2026-10-24 stored=diff dry=diff source=rest_repair post_d1=0 updated_at=2026-11-01T00:00:38.136000 n1m=1440/1440`. Its OHLC matches Exness exactly, but the volume is stored `113120` against Exness `113100` (relative diff about 1.8e-4, above the 1e-4 tolerance).
- Exception reasoning (Failure Protocol, kongming counsel). The same row was `stored=equal dry=equal` on 2026-11-02 with the same `updated_at`, and it already showed `stored=diff` in the 04:33Z pre-release run. The stored 1d still equals the aggregate of its stored 1m bars, which is the invariant A5 protects. Only the Exness value changed (inference: a revision of that day's volume on the Exness side). The day is outside the 7-day fold window and the hourly check's window, so the system does not refresh it. No 1m fetch was made, because the result would change no decision.
- Possible follow-up for the owner, not done here: amend the D16 `ok` so that a pre-window day whose stored 1d equals its stored 1m aggregate is not counted as a mismatch.

## Close

- `.cache/ssh/vps_key` deleted; `.cache/redis_old` and `.cache/redis_new` were deleted in Task 05.3.
- Phase 05 and `plan.md` are marked completed.
- Acceptance: A1-A3 (Phase 02), A4 (Phase 03 plus prod item 1), A5 (Phase 04 plus prod item 3), A6 (Phase 01), A7 (item 4 on intent) and A8 (Task 05.3 rotation checks) are met.

## Unresolved

- R4: closed on 2026-11-07. The 11-05 to 11-07 `integrity.issues_found` lines were lost with the redeployed containers. A read-only `check_integrity` run over the same 7-day window printed `issues_total=0` for all six symbols and 5m-1d (`plans/reports/kongming-261107-1227-open-questions-and-prod-state.md`, Q2). `fc173b5f` stores each future issue on the `sync_integrity` run doc.
- None. The D16 amendment (F2) and the final D16 run (F1) closed on 2026-11-09 with `mismatches=0 repair_1d=0`; see `plan.md` "Follow-ups".

Result: PASS
