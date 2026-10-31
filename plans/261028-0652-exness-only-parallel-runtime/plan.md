---
title: "Exness-only data, api/worker/trader split, zero-downtime trader handover"
description: "Delete TradingView and the CME calendar, fix the single-process money path (pause, in-flight, stale/gap guards, caches, warm-up, restart state), then split the app into lease-holding api, worker and trader containers with a hot-standby trader handover at a bar boundary, verified over 10 handover deploys and 14 days of paper before live is re-armed."
status: completed
priority: P1
effort: "about 6-8d code + 6 deploys + 14 days paper"
branch: develop
tags: [exness, tradingview-removal, process-split, leases, zero-downtime, latency]
blockedBy: []
blocks: []
created: 2026-10-28
---

# Exness-only data, `api`/`worker`/`trader` split, zero-downtime trader handover

## Overview

Today one `app` container runs the API, the scheduler, the tick feed, the strategies and the brokers on one event loop. This plan removes TradingView and the CME calendar (Exness becomes the only source of FX, metals and CFD data; Binance stays data + paper), fixes the money-path defects that a split would turn into real bugs, and then runs three containers from one image: `api`, `worker` and `trader`. The `worker` and the `trader` each hold a Mongo lease. A new trader warms up in standby, takes the lease at a 1m bar boundary, and only then connects a broker. Live trading stays off (`EXNESS_LIVE_TRADING=false`) for the whole plan; Phase 11 points to re-arming it.

The plan runs on the current prod VPS (2 vCPU, 3 GB RAM, D25) and measures its limits; the owner upgrades the host later.

## Sources (read when a phase cites them)

- Accepted contract and owner decisions D1-D24: `plans/reports/brainstorm-261028-1159-parallel-exness-only-runtime.md`.
- Evidence packet with D25-D32: `plans/261028-0652-exness-only-parallel-runtime/reports/debate-evidence-packet.md`.
- Synthesis that fixed this plan's structure: `plans/261028-0652-exness-only-parallel-runtime/reports/kongming-261028-1445-debate-synthesis.md`.
- Candidates it drew from: `reports/planner-debate-candidate-1.md` (KISS), `-2.md` (money path), `-3.md` (ops).
- Compose rolling deploy and nginx facts: `reports/researcher-261028-1400-compose-rolling-deploy.md`.

## Owner decisions added during planning

| # | Decision |
|---|---|
| D25 | Run on the current 2 vCPU / 3 GB VPS (Compose v5.1.1, Engine 29.3.0, NTP synchronized, checked 2026-10-28). Measure CPU, memory, swap, OOM, load, loop lag and warm-up time; no per-container memory limits. |
| D26 | Stale-bar budgets: 1m 10 s, 5m 30 s, 15m 60 s, 1h 120 s, 4h 300 s, 1d 600 s, 1w 600 s. |
| D27 | `web` is recreated on image deploys with a few seconds of SPA gap; accepted. `web` is not rolled. |
| D28 | The TradingView `rg` gate excludes `docs/journals/**` and `plans/**`; those dated records are not edited. |
| D29 | Same-tag re-rolls count as handover deploys; at least 5 of the 10 are re-rolls. |
| D30 | Opposite-side entries are rejected on paper as well as on Exness; exits are SL/TP only. |
| D31 | D25 measurements are record-only; the only machine stop is an OOM line. |
| D32 | No Mongo backup before the TradingView cascade delete (explicit owner decision for this one delete). |
| D33 | Before go-live is declared, 3 same-tag re-rolls run during the D12 canary while an Exness subscription is running; each logs `trader.lease_released inflight=0` (after any `trader.drain_retry`) and 0 `trader.drain_timeout`. |
| D34 | No all-day sampler. The `docker stats` sampler runs only during a roll; each Phase 10 day records one light snapshot (`free -m`, load, OOM counter). |
| D35 | Every interval closes on a timer at its end (+0.5 s); 4h/1d/1w end at the bucket end, so long bars after a market close are not stale and their entries are not skipped. |
| D36 | A handover row counts toward the ten only when the `XAUUSD:EXNESS` calendar (the Phase 10 paper symbol) is open at the deploy start and for the 15 min after it (owner, 2026-10-30). A row outside this gets `(off-session)` appended to its `kind` and does not count. It is a counting rule, not a deploy permission: deploys run at any time (Conventions, "No deploy window"). The check is the session check in Phase 10 Context. |
| D37 | Phase 10 closed early on the evidence at 2026-10-31T02:33Z (owner, 2026-10-31): 7 counted handover rows PASS (6 re-rolls), about 19 h of paper since 2026-10-30T07:10Z with 0 errors, 0 listener errors, 0 lost leases, 2 rate-limit retries and 1m Exness `t0_t5_ms` p95 699 ms over 26 samples. The 10-handover, 14-day and weekly-row criteria are waived, not met. Not observed: memory over several days, a Monday open, the 7-day limits. |
| D38 | Plan closed after Phase 11 Task 11.3 (owner, 2026-10-31): the owner will reset the strategies, so no strategy goes live under this plan. Phase 11 Tasks 11.4-11.7 (go-live run, D12 canary, D33 live re-rolls, go-live declaration) did not run. Live was re-armed at 05:12Z and disarmed again the same day (`pocketquant-config` 76acb5e); entries stay paused. A future go-live re-runs the go-live phases on the split runtime with the Phase 11 Substitutions table. |

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order; file order is execution order.
- **Entry gate** runs first in every phase. A miss is not a failed verification: edit nothing, spawn no `kongming`, leave the phase pending, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from NN after <UTC time>`. The coordinator stops the run on any worker summary that contains `NOT_YET` or `Status: BLOCKED`.
- Every entry gate checks that `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
- **[ASK]** = stop and ask the owner. The question is in Vietnamese (owner preference), leads with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts; a "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward to a later gate.
- **[USER]** = the owner acts and replies with a stated token.
- **Resume** after a `NOT_YET` exit: re-run the phase from its entry gate. Each entry gate also accepts the state this phase's own finished tasks left (it says so where that differs). Skip every task whose Verify already passes, and never repeat a prod data step whose recorded result already exists (for example the TradingView counts in `reports/tv-removal-counts.md`).
- Every `develop:master` push deploys prod and is an [ASK].
- **Failure Protocol**: each phase file carries the literal block. A failed Verify stops the phase and goes to `kongming`; a `NOT_YET` exit does not.
- Report paths are written from the repo root as `plans/261028-0652-exness-only-parallel-runtime/reports/<file>`. Every Verify is one self-contained command run from `D:/w/_me/algotrading/pocketquant`.
- No plan ids, phase numbers or finding codes in code, comments, test names, log events or commit messages. Commits use conventional format, English, no AI references.
- Code follows `CLAUDE.md`: a flow reads in ≤ 3 files, ≤ 2 hops to I/O, a new class/flag/config key needs a second real caller today, dead code is deleted in the same change, log level = frequency.
- Any phase that deploys records `free -m` on the VPS before and after the deploy in its report.
- **No deploy window** (owner decision 2026-10-30): a deploy or re-roll runs at any time after its [ASK]. A heavy job cut by a worker handover resumes from its last finished symbol (Phase 08 Task 8.6). A step that still names the window has no time check. The Phase 01 spike had its own window (it is not a deploy).
- **Search** uses `git grep`, because `rg` is not installed in the local Git Bash: `git grep -n -i -E "<pattern>" -- <paths> ':!docs/journals' ':!plans'`; counts pipe to `wc -l`.
- **Prod logs** are `LOG_FORMAT=console` with ANSI colours. Strip them with `sed 's/\x1b\[[0-9;]*m//g'` and parse `key=value`; never parse JSON.
- **OOM rule** (the only machine stop, D31): Phase 02 writes exactly one line `oom_baseline=<boot_id> <oom_kill>` to `reports/machine-baseline.md`, read on the VPS with `echo "$(cat /proc/sys/kernel/random/boot_id) $(awk '/^oom_kill /{print $2}' /proc/vmstat)"`. A later reading stops the plan when the boot id differs or the counter is higher, or when `docker inspect -f '{{.State.OOMKilled}}'` is `true` for any backend container.
- **VPS helpers**: Phase 08 installs one helper set in `/opt/pocketquant/bin/` (`snapshot.sh`, `sample.sh`, `probe.sh`, `leases.sh`, `oom-check.sh`); Phases 08-11 reuse it and create no other copies. Before Phase 08, phases run the same snapshot and OOM commands inline.
- **Secrets** never go on a command line: Mongo reads use a Python one-liner with `get_settings()` inside the backend container; admin calls pass the token with `curl -H @-`.

## Ops recipe (each phase inlines what it needs)

- Working dir `D:/w/_me/algotrading/pocketquant`, branch `develop`. The shell keeps no variables between commands, so every command sets `HOST` itself.
- SSH: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`; then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit.
- Push (the active gh account cannot push): `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; a release is `develop:master` in the same command. Check: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. Never print a token.
- Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Wait `sleep 15` before looking up a run id. Commits that touch only `**/*.md` do not trigger CI (`.github/workflows/cicd.yml:6-10`).
- `pocketquant-config` push: `git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`.
- Tests: run `docker ps` first; if it fails, start Docker Desktop (`"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background) and retry after 10 s. Full suite: `just test` (fallback `uv run python -m pytest tests/ -q`). The expected local red on Windows is exactly `4 failed, 4 errors`, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`. Any other red is a failure. About 109 setup errors mean Docker is down.
- Import contracts: `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.` through Phase 02 and `Contracts: 6 kept, 0 broken.` from Phase 03 on (two contracts exist only for the deleted TradingView and CME libraries).
- CI runs `lint-imports`, the code-metrics ratchet and pytest. The ratchet ceiling is flexible: raise it in its own commit instead of padding code, and say so in the phase report.
- Before Phase 08 the backend container is `pocketquant-app`; from Phase 08 on use `dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }` in `/opt/pocketquant/deploy` (where CI copies the compose file and `.env`, `.github/workflows/cicd.yml:229-240`, `deploy/vps/10-deploy.sh:12-14`) and `dc exec -T api|worker|trader ...`.

## Phases

| # | Phase | Deploy | Depends on | Status |
|---|---|---|---|---|
| 01 | [Spike: two ticks sessions on one key](./phase-01-spike-two-tick-sessions.md) | none | — | Done |
| 02 | [Observe and correct: KISS rule, loop-lag probe, skip listener, docstrings, machine baseline](./phase-02-observe-and-correct.md) | D-1 | — | Done |
| 03 | [Delete TradingView and the CME calendar (prod data first, then code)](./phase-03-delete-tradingview-and-cme.md) | D-2 | 02 | Done |
| 04 | [Exness order path: stored pause, opposite rejection, in-flight guard, caches, order pacer lane](./phase-04-exness-order-path.md) | none (CI) | 03 | Done |
| 05 | [Bar path: publish outside the lock, timer close, gap facts, Redis seed](./phase-05-bar-path.md) | none (CI) | 04 | Done |
| 06 | [Strategy runtime and restart state: guards, signal tasks, latency, warm-up, paper restore](./phase-06-strategy-runtime-and-restart-state.md) | D-3 | 05 | Done |
| 07 | [Roles and leases inside one process (Deploy A)](./phase-07-roles-and-leases-deploy-a.md) | D-4 | 01 (spike PASS), 06 | Done |
| 08 | [Topology and cutover to api/worker/trader (Deploy B)](./phase-08-topology-and-cutover-deploy-b.md) | D-5 | 07 | Done |
| 09 | [Cleanup and docs](./phase-09-cleanup-and-docs.md) | D-6 (handover 1/10) | 08 | Done |
| 10 | [Prod verification: 10 handovers, 14 days paper, machine limits](./phase-10-prod-verification.md) | re-rolls | 09 | Done (D37) |
| 11 | [Re-arm live gate](./phase-11-re-arm-live-gate.md) | per go-live plan | 10 | Closed (D38) |

## Acceptance criteria

| Area | Criterion |
|---|---|
| Stalls | `/health` on every role reports `role`, `lease` and `event_loop_lag_max_s`. Trader `event_loop.lag` lines with `lag_s >= 0.5` are counted per day, including 00:00, 03:00, 04:00 and 12:00Z; on the 2 vCPU / 3 GB host the count is recorded, not judged (D31), and the 0-per-day target is judged after the host upgrade. After TV removal, 7-day `job_history` p50 `sync_integrity` < 10 s and `sync_repair` < 120 s. 0 "Error notifying listener" lines; `skipped_max_instances` rows appear when a run is dropped. |
| Machine limits (D25, D31, D34) | The baseline, the cutover and every handover row carry the D25 measurements (per-container peak RSS and CPU, host used/available/swap, PSI if present, load, OOM counter, per-role loop lag, warm-up seconds); each Phase 10 day adds one light snapshot. Record only; the only stop is the OOM rule in Conventions (against the single Phase 02 `oom_baseline=<boot_id> <oom_kill>` line: a changed boot id, a higher `/proc/vmstat` `oom_kill` counter, or `State.OOMKilled=true` on a backend container; `oom-check.sh` from Phase 08 on). Prod logs use `LOG_FORMAT=console` with ANSI colours; strip them (`sed 's/\x1b\[[0-9;]*m//g'`) before any grep. |
| Parallelism | `docker ps` shows one running `api`, `worker` and `trader`. `db.leases` has exactly two docs, `worker` and `trader`, each with one unexpired owner. A second trader run for 10 min logs `trader.standby` and 0 of `lease.acquired`, `exness.order_submitted`, `position_opened`, `position_closed`, `orphan_backtest_recovery`, `orphan_jobs_recovered`; a second worker logs 0 `scheduler.started`. |
| TV removal | The D28 gate (the Phase 03 Task 3.8 Verify: `git grep -n -i -E` for `tradingview`, `cme_globex`, `pandas_market_calendars`, `seed_index_futures` over `src tests web/src docs pyproject.toml`, excluding `docs/journals` and `plans`) finds nothing. Mongo `tracked_symbols` and `bars` have 0 docs matching `/TRADINGVIEW$/`; subscription `01a178ef-5027-73ba-a98e-b7d6de8e2cc9` is gone. `lint-imports` prints `Contracts: 6 kept, 0 broken.` |
| Stored pause | CI: a pause through the `api` route makes the trader's next open refused; a failed store read refuses the open; the pause route returns 503 when the store write fails; `Safeguards` has no `entries_paused`. |
| Lease | CI: of two lease contenders one acquires; a lost renewal sets `trading_until=None`, stops strategies and exits; an order is refused with under 5 s of lease left (`reason=lease`). |
| In-flight | CI: a second signal for a subscription is rejected while an Exness in-flight open exists for it and while its signal task still runs (`reason=inflight`). |
| Stale (D10, D26) | CI with a fake clock: a bar 1 s past its budget (1m 11 s, 5m 31 s, 15m 61 s, 1h 121 s, 4h 301 s, 1d/1w 601 s) skips with exactly one `strategy.entry_skipped reason=stale`; at the budget the order goes out; paper SL/TP still fills on that bar; an event without `bar_end` (backtest) never skips. |
| Gap (D10) | CI: a non-successor bucket, > 60 s trading-time silence, or a mid-bucket start without a covering seed logs `reason=gap` and skips. Prod: weekly `strategy.entry_skipped` counts by reason. |
| 1m latency | CI: with fresh caches the open path makes exactly 1 REST call (`openPosition`). Prod paper: `live.signal_latency` p95 `t0_t5_ms` ≤ 1000 on 1m Exness symbols. Before live: the D12 canary p95 `t0_t6_ms` ≤ 2000 over the first 20 entries, and 3 live-armed same-tag re-rolls with `inflight=0` and 0 `trader.drain_timeout` (D33). CI: a lifespan test with a fake slow async-fill broker drains an open in flight across SIGTERM, releases, and the next trader takes over. |
| Concurrent opens (D21) | CI: with two subscriptions on one bar the check-and-register sections do not overlap, but `openPosition` sends do (three opens with a 0.5 s fake call all start within 0.7 s); `add_tick` for symbol B is not blocked by a 0.3 s handler on symbol A; a close fill marks the loss cap stale and the next open re-reads or refuses. |
| Direction and exits (D9, D11, D30) | CI: a LONG mirror row gives direction LONG after start; an opposite entry is rejected on paper and Exness and never becomes a close; `closePosition` is absent from `src`; hitnrun2 with 481 stored bars signals on the first qualifying live bar. |
| Paper restore (D13) | CI: after a closed paper round trip a rebuilt broker shows the pre-restart balance; a restored open paper position keeps SL/TP and exits on the next crossing bar. |
| Orphan sweep (D18) | CI: the sweep fails only `started` runs whose heartbeat is older than 60 s. |
| Handover (D8, D29) | Over 10 deploys that count under D36 (the `XAUUSD:EXNESS` calendar is open from the deploy start until 15 min after it; at least 5 same-tag re-rolls): every `trader.lease_released` has `inflight=0` and an offset of 0-30 s after a 1m boundary; 0 `trader.drain_timeout`; `handover_gap_ms` ≤ 2000; `takeover_ms` ≤ 5000; 0 `reason=gap` on bars within one interval of the boundary; the web probe shows 0 non-200 on the same-tag re-rolls (image deploys: recorded only, D27). |
| Rate budget (D19) | 0 terminal `exness.rate_limited` on order operations; `exness.rate_limited_retry` ≤ 72 per rolling 7 days. |

## Risks

| # | Risk | Likelihood × impact | Mitigation |
|---|---|---|---|
| R1 | A second ticks session disturbs prod (a past probe coincided with 4 breaker opens; correlation only) | M × H | Phase 01 gates Phase 07; a disturbed bar is gap-flagged, so the failure mode is a skipped entry |
| R2 | Memory on 3 GB during the two-trader overlap | M × H | D25 measurements at baseline, cutover and every handover; OOM is the stop (D31); levers for the owner: bigger host, WiredTiger cache cap, measured `mem_limit` |
| R3 | Two traders send orders | L × H | Lease plus `trading_until` fence per order; standby never connects a broker; second-trader probe in Phase 07 |
| R4 | Drain exceeds the grace period and SIGKILL lands mid-release | L × M | Hard drain deadline lifespan-shutdown start + 150 s, bounded engine stop by + 160 s, plus up to 10 s uvicorn graceful < 180 s grace; the new trader's snapshot reconcile recovers missed fills |
| R5 | An emergency `IMAGE_TAG` pin of a pre-lease image under the split compose | L × H | Image guard in the roll script; rollback reverts compose and scripts together |
| R6 | The k-th concurrent open waits (k-1) × 0.3 s in the order lane | M × M | The D12 canary measures `t0_t6_ms`; raise the trader fraction if more than 3 live 1m subscriptions share a boundary |
| R7 | The synchronous loss-cap read after a close costs about 2 s on the next entry | M × L | Stated; background refresh at second 30 |
| R8 | A seam between the last stored bar and the first live bar after warm-up | M × L | Wait until second ≥ 20; the successor check gap-flags a hole; `strategy.warmup_incomplete` WARNING |
| R9 | 26-31 CME-fixture tests to rewrite | M × L | Move fixtures to the Exness calendars; never weaken an assertion |
| R10 | The one-time cutover path runs once in prod | M × M | Docker Desktop rehearsal, `bash -n`, recorded rollback sequence |

## Unresolved

1. If Phase 01 returns `Result: FAIL`, the owner chooses the fallback (a second Exness account for the standby feed per D24, or another option) before Phase 07.
2. Settled while planning: `job_history` uses `duration_ms`, `status`, `started_at`; Mongo symbol fields are `symbol`, `asset_class`, `calendar_id`; `Trade.pnl` is gross and commission is stored separately; prod logs are console format.

## Red Team Review

### Session — 2026-10-28
**Findings:** 15 after deduplicating 33 raw findings from four reviewers plus one orchestrator finding (15 accepted, 0 rejected).
**Severity breakdown:** 3 Critical, 8 High, 4 Medium.
Details and evidence: `reports/red-team-adjudication.md`; raw reviews `reports/red-team-{security,failure-mode,assumptions,scope-critic}.md`; names and shapes every phase applies: `reports/red-team-shared-contract.md`.

| # | Finding | Severity | Disposition | Applied to |
|---|---|---|---|---|
| 1 | `trader.takeover_complete` never emitted; gap includes takeover time | Critical | Accept | 07, 09, 10 |
| 2 | OOM gate unpassable and ring-buffer based; cutover checks too late | Critical | Accept | 02, 03, 07, 08, 10, plan.md |
| 3 | Handover checks cannot fail while live is off | Critical | Accept (CI lifespan test, rehearsal with fake async broker, D33) | 07, 08, 11 |
| 4 | Drain releases too early, wrong deadline origin, renewal stops too soon, worker jobs cancelled | High | Accept | 06, 07, 08 |
| 5 | Lease safety: failed takeover, fence not at send, roles fail open, live flag in api/worker | High | Accept | 04, 06, 07, 08 |
| 6 | Probe containers outlive SSH and can win the lease | High | Accept | 07, 08 |
| 7 | Deploy lock, one-copy assert, re-roll probe timing, public log tails, pruning | High | Accept | 07, 08, 10 |
| 8 | Public safeguards GET becomes an unthrottled Mongo read | High | Accept | 04 |
| 9 | Console logs parsed as JSON | High | Accept | 06, 08, plan.md |
| 10 | `rg` missing locally; Task 7.1 Verify; doc wording conflict; test helper; missed callers | High | Accept | 02-11, plan.md |
| 11 | Duplicated VPS scripts, lease checks and deploy windows | High | Accept | 02, 03, 08, 09, 10, plan.md |
| 12 | Redis seed drops gap; non-holders write `bar:current`; process-local bar cache | Medium | Accept | 05, 07 |
| 13 | Secrets on command lines | Medium | Accept | 03, 06, 10, 11 |
| 14 | One-caller optional parameters | Medium | Accept | 04, 06, 07 |
| 15 | Phase 10 gap window, all-day sampler (D34), wrong log-rotation fact | Medium | Accept | 01, 10 |

### Whole-Plan Consistency Sweep — 2026-10-28

**Checks run:** (1) duplicate work, (2) seam names between Phases 04-06 and 07/08/10, (3) log events and fields read in Phases 08-11 against their emitters in Phases 02-07 and the shared contract, (4) OOM rule, (5) search commands, (6) deploy windows, (7) secrets on command lines, (8) entry gates against the Resume rule and cross-phase task numbers, (9) acceptance table against Phases 06-11 and the phase list, (10) superseded terms, (11) Failure Protocol blocks and frontmatter `dependencies`.

**Verified without change:** every seam name exists where it is defined (`submit_order(..., deadline=)` in Phase 04 Task 4.6; `last_closed_boundary` and `publishes_current` in Phase 05 Tasks 5.2-5.3; `trading_until`, `_running_bar_handlers`, `cancel_pending_signals`, `stop(timeout_s)` and `take_over` in Phase 06; `inflight_count` and `on_renewed` in Phase 07). Phase 05 already advances `last_closed_boundary` on every timer pass with no running publish, idle or not, and tests it (`test_an_idle_service_still_advances_the_boundary`). `QuoteAppService.start` has no early return (checked in `src`), so the trader always runs the close timer. No `oom_lines`, `/api/health`, "5 MB", `mongosh -p` or inline `X-Admin-Token: $ADMIN_TOKEN` remains; the Phase 11 Substitutions table only quotes the go-live text it replaces. `waiting_since` in Phase 07 is a local of the trader closure, not the parameter finding 14 removed. `entries_paused` after Phase 04 is the GET body key and the `reason=entries_paused` log value, both kept on purpose. Every `git grep` absence check runs after its task's commit or over paths with no new files; Phase 07 Task 7.1 already uses `--untracked`. Cross-phase task references (Phase 09 and Phase 11 to Phase 10 Task 10.6 steps 5, 6 and 8; Phase 08 to the Task 7.8 lease one-liner; Phase 06 to Phase 04 Task 4.2) point at existing steps. Every phase file ends with exactly one identical `## Failure Protocol` block.

**Changes made:**
- `phase-07-roles-and-leases-deploy-a.md`: Task 7.6 no longer edits `setup.py:71` (Phase 02 Task 2.6 owns that change); its Verify still asserts the formatter is present; `setup.py` left the Modify list; Context no longer says tracebacks print locals.
- `phase-07-roles-and-leases-deploy-a.md`: `LeaseRepository.release` logs INFO `lease.released name= owner=` when it released a lease, asserted in two repository tests. The shared contract, the Phase 09 docs and the Phase 10 Task 10.1 count of 12 contract events need this event, and no phase emitted it.
- `phase-07-roles-and-leases-deploy-a.md`: entry gate line 2 reads Phase 01's `Owner fallback:` line (`pending` asks the owner; `second-account` exits `NOT_YET` for a plan revision without asking again).
- `phase-07-roles-and-leases-deploy-a.md`: the Task 7.8 window check and the after-D-4 rollback name the plan.md Conventions deploy window.
- `phase-06-strategy-runtime-and-restart-state.md`: Task 6.8 step 1 was a blackout-only check; it now runs the Conventions deploy window command. The after-D-3 emergency pin names the [ASK] and the window.
- `phase-06-strategy-runtime-and-restart-state.md`: Task 6.8 step 7 and Task 6.9 steps 3-5 set `HOST` in the same command (Ops recipe: no shell state carries between commands).
- `phase-04-exness-order-path.md`, `phase-05-bar-path.md`, `phase-06-strategy-runtime-and-restart-state.md`: the entry gates accept this phase's own unpushed commits on a resume (`synced=no` with nothing behind `origin/develop`; Phases 05 and 06 then check CI on `origin/develop`), as the Resume rule states.
- `phase-08-topology-and-cutover-deploy-b.md`: the Resume rule says Task 8.5 is done when `Rehearsal: PASS` is recorded, and that every `NOT_YET` exit comes before the cutover push. The Task 8.7 window and the rollback pushes name the Conventions window. Rollback step 5 sets `HOST`.
- `phase-02-observe-and-correct.md`, `phase-03-delete-tradingview-and-cme.md`, `phase-09-cleanup-and-docs.md`, `phase-10-prod-verification.md`, `phase-11-re-arm-live-gate.md`: rollback deploys, emergency pins, Phase 10 fix pushes and the Phase 11 disarm dispatch name the Conventions deploy window.
- `phase-02-observe-and-correct.md`, `phase-03-delete-tradingview-and-cme.md`, `phase-06-strategy-runtime-and-restart-state.md`: window end bounds are exclusive (`-lt 680`, `-lt 1170`), like Phases 08-11.
- `phase-02-observe-and-correct.md` Task 2.4 and `phase-09-cleanup-and-docs.md` Context: the doc-gate text quotes the phrases Phase 09 actually bans and the sentences Phase 02 actually writes.
- `plan.md`: the Machine limits criterion uses the `oom_baseline=` rule instead of a `dmesg` count. The TV removal criterion uses the Phase 03 Task 3.8 `git grep` gate instead of `rg`. R4 states the drain deadline from lifespan-shutdown start. The Phase 07 row depends on `01 (spike PASS), 06`.
- All 11 phase files: frontmatter `phase` and `dependencies` use plain integers, like the sibling go-live plan (`[]`, `[]`, `[2]`, `[3]`, `[4]`, `[5]`, `[1, 6]`, `[7]`, `[8]`, `[9]`, `[10]`), matching the plan.md phase table.

**Not changed:** D28 keeps the words "`rg` gate" because owner decisions are not edited; the gate itself runs as `git grep`. Phase 06 D-3 takes no OOM reading. Phase 07 Task 7.8 step 4 compares the cumulative `oom_kill` counter and the boot id before D-4, so an OOM during D-3 still stops the plan there (inference from how the counter is defined). `Unresolved` item 2 holds settled facts and makes no JSON claim.

**Unresolved:** none.

## Validation Log

### Session 1 — 2026-10-28
Questions asked during intake, synthesis, red team and validation: 16 (all answered in Vietnamese; recorded here in English as D25-D35).

- **Verification:** the red-team reviewers fact-checked file paths, symbols and behaviour in every phase (`reports/red-team-*.md`); the consistency sweep re-checked seams and events. `[UNVERIFIED]` tags remaining: 0.
- **Decisions confirmed in validation:** D35 (every interval closes on a timer at its end; long bars after a market close are no longer stale) and the D33 live re-rolls without an entry pause during the minimum-lot canary (accepted by the owner; each re-roll stays a separate [ASK]).
- **Propagation:** D35 applied to Phase 05 (rule, Task 5.3 goal, test, constants, `close_due_bars` scope, commit message), Phase 06 Context and Phase 09 docs text; D33 confirmed as already written in Phase 11.

### Whole-Plan Consistency Sweep (validation)
- Searched all phase files for "1h or less", "tick close", "up to 1h" and "keep tick"; the remaining hits describe only the session cut for bars up to 1h, which D35 keeps.
- No contradiction remains.
