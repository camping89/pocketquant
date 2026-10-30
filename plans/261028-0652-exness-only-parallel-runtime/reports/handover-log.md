# Handover log

## Row 0 machine measurements (cutover D-5; D25, record only per D31)

Deploy: `develop:master` at 659120ef, pushed 2026-10-30 03:02 UTC after the owner approved. The CI run succeeded (tests, build-app, build-web, deploy, cleanup-tags).

Before (03:02:44 UTC):

```text
               total        used        free      shared  buff/cache   available
Mem:            3905        1837         392           1        1676        1789
Swap:           7899         107        7792
label=cutover-before ts=2026-10-30T03:02:44Z mem_used_mb=1840 mem_available_mb=1786 swap_used_mb=107 load1=1.04 psi_some_avg10=0.00 oom=0
```

After (03:09:04 UTC):

```text
               total        used        free      shared  buff/cache   available
Mem:            3905        1985         459           1        1460        1640
Swap:           7899         119        7780
label=cutover-after ts=2026-10-30T03:09:04Z mem_used_mb=1985 mem_available_mb=1640 swap_used_mb=119 load1=3.86 psi_some_avg10=0.00 oom=0
```

Peaks from the 2 s sampler:

```text
peak pocketquant-mongodb rss_mib=1589 cpu_pct=130.8
peak pocketquant-prod-trader-1 rss_mib=132 cpu_pct=86.1
peak pocketquant-app rss_mib=123 cpu_pct=41.8
peak pocketquant-prod-worker-1 rss_mib=97 cpu_pct=94.5
peak pocketquant-prod-api-1 rss_mib=95 cpu_pct=56.5
peak pocketquant-cloudflared rss_mib=55 cpu_pct=26.1
peak pocketquant-portainer rss_mib=28 cpu_pct=0.8
peak pocketquant-web rss_mib=8 cpu_pct=16.9
peak pocketquant-redis rss_mib=8 cpu_pct=14.2
peak vigorous_bassi rss_mib=58 cpu_pct=100.8
host_used_max_mb=2261 min_available_mb=1363 max_swap_used_mb=119
```

`vigorous_bassi` is the image guard's `docker run --rm` in `10-deploy.sh`. It appears in two samples only.

OOM: the baseline is `oom_baseline=<boot_id> 0`. Both readings were `oom=0` on the same boot id, and `oom-check.sh` printed `OOM_OK` after the cutover.

New trader: `trader.standby warmup_s=2.6`. Old app drain: no `trader.drain_retry` and no `trader.drain_timeout`. It logged `trader.lease_released inflight=0 offset_s=0.61` at the 03:08:00 boundary.

`11-verify.sh` FAIL rows: `[x] Boot integrity: FAIL - 1 fatal startup signature(s) in logs`.
- Cause (verified from the worker log): the three role containers start at once on the cutover. At startup, `JobHistoryRepository.ensure_indexes` always dropped and recreated `idx_skip_idempotency`, so one container's drop aborted the worker's build of that index (`OperationFailure: Index build failed ... caused by :: dropIndexes command`).
- The worker failed startup and restarted once (`RestartCount=1`). Its second start took the `worker` lease at 03:07:06. api and trader had 0 restarts, and every index exists.
- Fix: commit 6142249f drops the index only when its spec drifted. It ships with the next image deploy.

Heavy jobs: none was running at the push. The precondition read 0 running rows after the 03:00 `sync_backfill` completed in 116 s. The new worker logged no `orphan_jobs_interrupted` and no catch-up.

## Row 1 notes (D-6)

Deploy: `develop:master` at ee298e78, pushed after the owner approved. Capture stamp `20261030T064424Z`, start `2026-10-30T06:44:27Z`. CI run 41015889660 succeeded with one `0 failures` verdict.

Worker stop and catch-up lines (old and new worker):

```text
2026-10-30T06:49:20.021265Z [info     ] worker.lease_released          [pocketquant.app.roles] running=0
```

No `job_row` line: no job was running at the deploy start. `interrupted_heavy_now 0`. No heavy job was cut, so this deploy did not exercise the heavy-job resume.

Task 9.9 Verify: 0 `pocketquant-app`, 3 role containers, 1 `trader.takeover`, 1 `trader.takeover_complete`, `worker=cb95de09e0a8:1 trader=e28052cfc510:1 unexpired=2 owners_match=yes`, `RestartCount` 0 for `pocketquant-prod-api-2`, `-worker-2` and `-trader-2`, 0 `job_history.idempotency_drop_failed`. The capture stop printed `oom=0` on the same boot id and `OOM_OK`.

| # | UTC start | kind | stamp | inflight | offset_s | drain_timeout | handover_gap_ms | takeover_ms | gap_skips | discarded | probe | leases | verify | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2026-10-30T03:02:46Z | cutover D-5 (image deploy, web recreated) | 20261030T030247Z | 0 | 0.61 | 0 | 421 | 45 | 0 | lease:0 drain:0 | 2/546 recorded (D27) | 2/2 owners_match=yes | Boot integrity FAIL | PASS |
| 1 | 2026-10-30T06:44:27Z | image | 20261030T064424Z | 0 | 0.831 | 0 | 499 | 58 | 0 | lease:0 drain:0 | 000:1 200:583 (image, recorded only, D27) | worker=cb95de09e0a8:1 trader=e28052cfc510:1 unexpired=2 owners_match=yes | 1 | PASS |
| 2 | 2026-10-30T08:11:16Z | re-roll | 20261030T081114Z | pending | | | | | | | | | 1 | pending |
