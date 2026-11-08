# Open questions after the 1d cascade fold release, and prod state on 2026-11-07

Advisory report. Read-only: no push, commit, deploy, Mongo/Redis write, job trigger or restart was made. Every command ran from `D:/w/_me/algotrading/pocketquant` (Git Bash) or over SSH to the prod VPS between 2026-11-07T05:29Z and 05:45Z. Mongo reads ran through the plan's PRODPY recipe inside the `api` container. "Fact" means I ran the command and read the output. "Inference" is labelled.

## Outcome

- Prod is healthy and live trading is disarmed. The running release is `1e47ca94` (containers `-18`, started 2026-11-07T05:14-05:16Z), not the 2026-11-06T14:48Z deploy the peer session reported. That deploy did happen, but three more followed.
- Q1: three manual job runs on 2026-11-04 (06:04-06:15Z) are visible in `job_history`; they completed, stayed under the R1 limit, and left no visible harm.
- Q2 (R4): a read-only re-run of the integrity check today reports zero missing or misaligned 5m-1d bars for all six symbols. The old container logs, where the 11-05/06/07 `integrity.issues_found` lines would be, were deleted with the containers on each redeploy. R4 is not a problem today.
- Q3 (D16): the BTCUSD 2026-10-24 volume mismatch is a vendor-side value that moves between reads (113120 on 11-01, 113100 on 11-04, 113120 again today) on a day the system no longer refreshes by design. Amend the D16 rule for pre-window days; it is not a defect.
- Q4: commit the untracked reports (eleven of fourteen are already cited by tracked plan files); do not commit the misplaced `.claude/agent-memory/planner/` directory; no secrets found.
- Q5: run the D16 script once more, on or after 2026-11-11, with the amended rule, then retire it.

## Health since the latest deploy

| Check | Result | Evidence |
|---|---|---|
| `docker ps` | `api-18`, `worker-18`, `trader-18`, `web` healthy (up 13-15 min at 05:29Z); `redis` up 3 days (recreated 2026-11-04T04:20Z by the rotation deploy); `mongodb`, `cloudflared`, `portainer` up 2 weeks | `docker ps --format ...`: `pocketquant-prod-trader-18  Up 13 minutes (healthy)` |
| Running commit | `1e47ca94` via CI run `42341608519` (`workflow_dispatch`, deploy job 05:13:43-05:16:40Z). Earlier deploys: `42338601824` same sha (push, 04:32-04:35Z), `42248145704` `cbd2e920` (11-06 16:02-16:06Z), `42237199331` `b42f9f88` (11-06 14:52-14:56Z; its run was created 14:48:21Z, which is the peer's "14:48:19Z"). Container numbers `-14` (11-04) to `-18` match four redeploys | `gh run view <id> --json jobs` |
| `trader_live` | `trader_live=False` (settings read inside the `trader` container, LIVECHK recipe); `safeguards` doc `live_trading: False` | `docker compose ... exec -T trader python -c "...exness_live_trading"` |
| Log greps (current containers, 188 lines, ANSI stripped) | `binance_ws.callback_failed` 0, `cascade.symbol_failed` 0, `[error` 0, `integrity.issues_found` 0; 3 warnings, all `event_loop.lag` (lag_s 0.96-1.11) in the trader at 05:15:44-47Z, during startup | `docker compose ... logs --timestamps api worker trader | sed 's/\x1b\[[0-9;]*m//g' | grep -c ...` |
| Latest durations (R1 limit 600000) | `sync_repair` 2026-11-07T00:00:00Z `duration_ms=155994`; `sync_backfill` 03:00:00Z `305938`; `sync_integrity` 04:00:00Z `5292`; `sync_verify_cascade` 05:00:00Z `4045`. All `status=completed` | PRODPY on `job_history`, latest row per `job_id` |
| `free -m` | Mem total 3905, used 2039, free 642, buff/cache 1224, available 1592; Swap 329 used of 7899 (phase-05 recorded 2407 used / 1227 available after the 11-04 deploy) | `free -m` |
| Disk, load | `/` 22G of 75G (30%); load 0.37 0.45 0.69; host up 111 days | `df -h /`, `uptime` |
| Branches | local `develop` = `origin/develop` = `e49c0565`; `origin/master` = `1e47ca94`; `develop` is one commit ahead (`e49c0565 chore: track agent memory and keep plan journals local`, no `src/` change). `origin/master` is five commits past the briefed `b42f9f88` | `git rev-parse HEAD origin/develop origin/master`; `git log origin/master ^develop` empty |

Limitation (fact): the log driver is `json-file` (`max-size 10m`, `max-file 3`) and `docker ps -a` shows no stopped containers, so every log line before 2026-11-07T05:14Z is gone. The 11-04 to 11-07 greps the questions ask for cannot be re-run from logs. `job_history` rows survive (30-day TTL), and `sync_integrity` writes no `details` rows (`sync_jobs.py:459-493` only logs), so the integrity evidence had to be reproduced (Q2).

Leftover: the PRODPY recipe copies the script to `/tmp/f.py` inside the `api` container; `exec rm` failed with `Operation not permitted` (non-root exec). The file holds no secret and dies with the container, same as the phase-05 runs. The host-side `/tmp/f.py` was removed.

## Q1: What ran on 2026-11-04 instead of the scheduled runs

**Evidence.** PRODPY on `job_history`, rows for `sync_repair`, `sync_backfill`, `sync_integrity` with `started_at >= 2026-11-03T23:00Z`:

```
sync_repair     start=2026-11-04T00:00:00.020 end=00:01:36.426 dur=96411  status=completed
sync_backfill   start=2026-11-04T03:00:00.020 end=03:03:45.739 dur=225723 status=completed inserted=1
sync_integrity  start=2026-11-04T04:00:00.037 end=04:00:06.256 dur=6223   status=completed
sync_repair     start=2026-11-04T06:04:53.476 end=06:07:19.407 dur=145962 status=completed
sync_backfill   start=2026-11-04T06:07:56.585 end=06:12:13.065 dur=256516 status=completed inserted=0
sync_repair     start=2026-11-04T06:12:13.071 end=06:14:34.163 dur=141095 status=completed
sync_repair     start=2026-11-04T12:00:00.092 end=12:02:53.629 dur=173619 status=completed
sync_repair     start=2026-11-05T00:00:00.022 ... dur=165016   (then 03:00 backfill 325758, 04:00 integrity 6839, 12:00 repair 179872)
... every later scheduled row completed; non-completed rows since 11-03T23Z: only the sync_1m in progress at query time
```

Facts:
- The schedule is `sync_repair` at `0 */12 * * *`, `sync_backfill` 03:00, `sync_integrity` 04:00, `sync_verify_cascade` hourly (`sync_jobs.py:774-799`). Scheduled rows start at `:00:00.0xx`. The three rows at 06:04:53Z, 06:07:56Z and 06:12:13Z match no trigger, so they are the manual runs. They match the phase-05 report section "Deviation: one-off job runs instead of the scheduled waits" to the millisecond.
- `sync_verify_cascade` rows since 11-03T23Z: 81 completed, 0 running/interrupted/failed. 79 hourly slots (11-03T23Z to 11-07T05Z) plus the two one-off verifies in the report equal 81.
- Durations 145962, 256516 and 141095 ms are under the 600000 R1 limit. The scheduled repair at 12:00Z the same day (173619) and every later run completed.
- The manual backfill inserted 0 bars (`total_inserted=0`); scheduled backfills insert 1 per day (`bars` created since release with `source=rest_backfill`: 3 rows, all `BTCUSDT:BINANCE 1m`).
- Bars whose `updated_at` falls in the manual window 06:04:53-06:14:35Z: 60 `1m` rows and 22 cascade rows (14 `5m`, 2 each of `15m`, `1h`, `4h`, `1d`). A 3-minute scheduled repair window shows 12-18 `1m` rows and 4-6 rows per cascade interval. Inference: these counts are the per-minute `sync_1m` steady state scaled by window length, so the manual runs rewrote few or no bars beyond what the scheduler would have.
- Who asked for the runs: not decidable from prod. The report quotes the owner; `job_history` records no actor.
- Not re-verifiable: the report's "6 `exness.rate_limited_retry`, all retried" and "0 `[error` lines" for that window. Those lines lived in the `-14` container logs, which no longer exist.

**Recommendation.** Record this as closed: three manual runs, completed, under limit, no failed or interrupted row before or after, no excess bar writes visible. No action.

**Trade-off.** The lease bypass the report describes (a second process next to the live worker) remains a pattern to avoid; it worked here because every write is an idempotent upsert, not because it is safe in general. If the owner wants a one-off again, the lower-risk path is the admin route or a job trigger inside the lease-holding worker, not a side process.

## Q2 (R4): 5m-1d gaps the cascade cannot fill

**Evidence.**
- `sync_integrity` rows 11-05, 11-06, 11-07 at 04:00Z: `completed`, `details=0`. The warnings they may have logged are gone with the containers (see Limitation).
- Read-only reproduction of the same function the job runs (`check_integrity`, `integrity_jobs.py:51-112`, `days_back=7`, reads `find_datetimes` only), today at about 05:40Z, for all six tracked symbols and intervals 5m, 15m, 1h, 4h, 1d:

```
== check_integrity (read-only, days_back=7) for 5m-1d; gap ranges with stored-1m counts
  issues_total= 0
```

- Bars written since the release (`updated_at >= 2026-11-04T04:13:56Z`, intervals 5m-1w): only `source=cascade` (5m 5082, 15m 1702, 1h 428, 4h 112, 1d 24). `source=rest_repair` rows for 5m-1d created since release: 0. A4 holds in the data, not only in logs.
- What the old 5m-1d REST repair actually did in the two weeks before the release (`created_at` in [2026-10-21, release), `source=rest_repair`): `1d` rows every day for the three Exness symbols (the old daily 1d overwrite that Phase 03 removed), `5m ETHUSDT:BINANCE` 57 rows on 10-21/10-22, `5m EURUSD:EXNESS` 2 rows (10-22, 10-27). Nothing at 15m, 1h or 4h.
- The integrity grid comes from the symbol's calendar (`_expected_instants`, `integrity_jobs.py:32-45`), so the Exness 21:00Z rollover minutes that have no venue ticks do not appear as 5m-1d gaps today.

**Answer.** Fact: as of today there is no 5m-1d gap in the 7-day integrity window, so there is nothing the cascade is failing to fill. Inference: a 5m-1d bucket with no 1m behind it can only arise when the 1m repair itself leaves `still_missing` minutes; that case is already logged at 1m (`integrity.repair.still_missing`), and the pre-release record shows the REST path filled 5m from the vendor only twice for Exness in two weeks. R4 is not a real problem now.

**Recommendation.** Close R4 with today's reproduction as the evidence. Keep `sync_integrity` as the monitor. Optional follow-up for the owner, not required: have `sync_integrity` write each issue through the existing `record_detail` (`sync_backfill` is already a caller), so the evidence survives a redeploy for the 30-day TTL instead of dying with the container. Without it, R4 can only ever be checked by re-running the function, as done here.

**Trade-off.** Dropping 5m-1d from REST repair (E3) means a vendor-only 5m bar (venue has a bar, our 1m does not) is never fetched. The two-week record shows that case was rare for Exness (2 bars) and tied to a Binance outage otherwise (57 ETH bars on 10-21/22). Accepting that loss keeps the invariant that every 5m-1d bar equals its 1m aggregate.

## Q3 (D16): BTCUSD 2026-10-24 volume mismatch

**Evidence.**
- Stored 1d (`bars`, `BTCUSD:EXNESS`, `1d`, `2026-10-24`): OHLC `81081.34 / 81115.7 / 79118.43 / 80767.83`, `volume=113120.0`, `source=rest_repair`, `created_at=2026-10-25T00:00:18Z`, `updated_at=2026-11-01T00:00:38Z`. That row was written by the old 1d REST repair from the vendor value on 11-01.
- Stored 1m for that UTC day: 1440 rows (1437 `rest_sync_1m`, 3 `rest_repair` filled within seconds of their minute), `sum(volume)=113130.0`, OHLC aggregate identical to the stored 1d.
- Exness 1d fetched today (`ExnessAdapter.fetch_ohlcv(..., DAY_1, n_bars=20)`, one read-only REST call): `2026-10-24 81081.34 81115.7 79118.43 80767.83 113120.0`.
- Phase-05 report (D16 runs at 04:33Z and 06:15Z on 11-04): Exness returned `113100`; the same row was `equal` on 11-02.
- Self-consistency today for every stored 1d since 2026-10-22, UTC-day bucket, exact compare: XAUUSD 14 days 0 diffs, EURUSD 14 days 0 diffs, BTCUSD 17 days 1 diff (this row, volume 113120 vs 113130; relative 8.8e-5, inside the D16 1e-4 tolerance).

**Reading.** Facts: the vendor's 1d volume for that day has taken two values across four reads (113120, 113120, 113100, 113120); our OHLC matches exactly in every read; the stored 1d equals its own 1m aggregate within the script's tolerance; the day sits outside the 7-day fold window and, since E3, no job refreshes a 1d bar from the vendor. Under the D16 rule as written, this row would be `equal` today and `diff` on 11-04 with no change on our side. Inference: the 11-04 reading was a transient or revised vendor value; I cannot tell which from the evidence. Nothing points to a defect in the cascade or the fold.

**Recommendation.** Amend the D16 `ok` for days older than the 7-day fold window: pass when the stored 1d equals the dry-run aggregate of its stored 1m (self-consistency), without requiring vendor equality. Keep vendor equality for days inside the window, where the system still rebuilds the bar. Keep the OHLC tolerance at 1e-9 and the volume tolerance at 1e-4 inside the window. Record the amendment in the plan as D17 with this row as its example.

**Trade-off.** The amended rule stops catching a vendor correction older than 7 days. By design the system never applies such a correction anyway (REST 1d repair is gone, cascade window is 7 days), so the rule would otherwise accumulate permanent false failures, one per vendor revision, with no action available. A rule that fails on something nobody will fix is noise. Alternative: raise the volume tolerance to 1e-3 for all days. Weaker, because it hides real 1m-level problems inside the window too.

## Q4: Untracked files under `plans/`

**Evidence.**
- `git status --porcelain plans/`: 13 untracked report files or directories under `plans/reports/` (dated 261028, 261103, 261106; 8 KB to 165 KB each) and `plans/261028-0652-exness-only-parallel-runtime/.claude/agent-memory/planner/` (4 files, 17 KB).
- Governance: `docs/governance/documentation-rules.md` exempts `plans/` from the line test ("`plans/` is exempt") and routes "Plans, reports, journals, roadmaps" to `plans/` as "records, not authority". No rule says whether they are committed. No rule in `no-look-ahead-rules.md` applies.
- Convention: 437 files are tracked under `plans/`, 59 under `plans/reports/`, including two `*-preview.html` and several `advise-*-state.md` files of the same kind as the untracked ones.
- The owner decided today (`e49c0565`, 2026-11-07T05:21Z): `.gitignore` now ignores `plans/journals/` ("Session journals stay local") and no longer ignores `**/.claude/agent-memory/`, with the root `.claude/agent-memory/` tracked in the same commit. Journals are therefore no longer in the untracked list.
- References: `git grep -l -F <basename> -- plans docs` finds tracked files citing 11 of the 14 untracked entries (for example `phase-17-observe-compare-delete.md:30` cites `advise-261103-0025-finish-mtf-plan-now.md`; the 261028 plan cites its brainstorm, reviewer, explore, researcher and kongming reports). Not cited: the preview HTML, the advise `-state.md`, and the two 261106 debugger/handoff reports.
- Secrets scan over all untracked files: 0 hits for the VPS host string or `user@host`, 0 `KEY=value` env lines, 0 emails, 0 key blocks, 0 URL-embedded credentials; the only keyword hits are prose ("Redis token pacer", "fencing token"). Long-token regex hits are test names and report slugs.

**Recommendation.** Commit the 13 `plans/reports/` entries in one `docs(plans): add the parallel-runtime, mtf-advice and run4 reports` commit; a tracked plan that cites an untracked report is a broken reference for anyone who clones. Leave `plans/261028-0652-.../.claude/agent-memory/planner/` out: it is a subagent scratch directory in a non-standard place, nothing cites it, and the owner's commit tracks agent memory at the repo root only. Delete it or move its two useful notes under `.claude/agent-memory/planner/` (owner's call). Do not commit `.cache/` or journals.

**Trade-off.** 165 KB of brainstorm candidates and a 76 KB HTML preview add repository weight with little future reading. Dropping the preview and `-state.md` files is defensible; the cost of keeping them is small and it matches what is already tracked.

## Q5: Re-run the D16 script in the week of 2026-11-09?

**Evidence.**
- Nothing in prod compares a stored 1d bar with the vendor any more: the hourly `cascade.daily_divergence` check was removed in `ac8ebbc6` (2026-11-05, plan.md A5); `sync_verify_cascade` fetches 5m with `n_bars=12` only (`sync_jobs.py` `_verify_one_symbol`); `check_integrity` checks presence and alignment, not values; `sync_repair` REST-touches 1m and 1w only.
- The post-release evidence for 1d values so far: the D16 runs on 11-04 (every day from 11-01 on `equal`) and today's offline self-consistency (44 of 45 day rows exact, the exception being the pre-window row of Q3). Days 11-04 to 11-07 were built by the new code inside the 7-day window. A run on or after 2026-11-11 is the first in which every day of the window was built and folded only by the released code.
- Cost: about one minute, read-only, three Exness REST calls of 20 bars.

**Recommendation.** Yes, once, on or after 2026-11-11 (any day that week works), with the Q3 amendment applied, as the steady-state proof of A6. If it passes, retire the script and do not schedule more runs. If it fails inside the window, that is a real finding and goes through the plan's Failure Protocol.

**Trade-off.** Skipping it is defensible: Phases 02 and 03 carry tests for the three causes and today's self-consistency is clean. The run buys a vendor comparison that no job provides and costs almost nothing; the downside is one more manual step. Do not turn it into a job: the owner removed the hourly check for the same reason a scheduled D16 would be unwanted.

## Assumptions

- The three 06:0x rows on 11-04 are the one-off runs the phase-05 report describes (high: times match the report to the millisecond and match no trigger).
- The 11-04 Exness value 113100 was read correctly by the D16 script (medium: I rely on the report; the script code is not kept in the repo). If that read was wrong, Q3's answer does not change: the stored bar still equals its 1m aggregate and the vendor equals it today.
- My self-consistency check used UTC-day buckets for all three Exness symbols (high: it reproduced 0 diffs on 28 session-calendar day rows, which it could not do if the bucket differed).
- "No harm" for Q1 rests on `job_history` and bar counts, not on the lost logs (high for job rows; medium for the rate-limit statement, which cannot be re-verified).

## Unresolved

- The `integrity.issues_found` lines of the 11-05, 11-06 and 11-07 runs are unrecoverable. Today's reproduction stands in for them; the owner decides whether the `record_detail` follow-up in Q2 is worth a small change.
- Whether the 11-04 vendor volume 113100 was a transient value or a revision later reverted is not decidable from our data.
- The disposition of `plans/261028-0652-exness-only-parallel-runtime/.claude/agent-memory/planner/` (delete, move, or track) is the owner's call.
- A copy of the last PRODPY script remains at `/tmp/f.py` inside the `api-18` container (no secret; `exec rm` is not permitted for the exec user). It disappears at the next redeploy.
