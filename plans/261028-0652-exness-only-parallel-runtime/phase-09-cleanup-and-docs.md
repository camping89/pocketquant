---
phase: 9
title: "Cleanup and docs"
status: pending
priority: P1
effort: "about 3h + one image deploy (D-6, handover 1 of 10)"
dependencies: [8]
---

# Phase 09: Cleanup and docs

## Goal

Delete the one-time `app` -> `api`/`worker`/`trader` cutover branch, describe the role split, the leases, the trader handover and the rolling deploy in the docs as they are, and ship both as D-6. D-6 is an image deploy and counts as handover deploy 1 of 10; this phase captures its raw measurements, and Phase 10 turns them into row 1.

## Context

- The cutover branch in `deploy/vps/10-deploy.sh` runs only while a container named `pocketquant-app` exists. After Phase 08 none exists, so the branch is dead code (`CLAUDE.md`: delete dead code in the same change).
- Old-topology text found on `develop` @ 453e8e90 (Phases 02-08 may have moved lines; locate by text, not by line):
  - `docs/system-architecture.md:7` ("One process, one worker"), `:43-54` (Startup and Shutdown, `ENABLE_JOBS`), `:235-237` (Deployment Shape).
  - `docs/deployment.md:51,54,58,64,78,122` (fixed name, "6 containers", `app`), `:138-157` (pause over SSH, Restart while live), `:159-178` (Rollback), `:184-186` (Troubleshooting), `:221-224` (`ENABLE_JOBS`), `:250-269` (data runbooks with `docker exec pocketquant-app`).
  - `README.md:19,21,39,54,75`; `justfile:35-36`; `docs/project-overview-pdr.md:14,109-110`; `docs/codebase-summary.md` (package map); `scripts/audit_bar_quality.py:15,24`; `scripts/backfill/binance_bars.py:32`; `scripts/backfill/provider_bars.py:13`; `deploy/vps/one-time/README.md:8,14`.
- `CLAUDE.md:15` ("Single uvicorn worker only") is rewritten in Phase 07; this phase only checks it.
<!-- Red team 2026-10-28: #10 -->
- Doc gate wording. The gate below bans only old-topology phrases: `pocketquant-app`, `ENABLE_JOBS=` (any value), "single uvicorn", "single worker", "single process", "single backend", "app container", "6 containers", "one process," (the comma form used by "One process, one worker" and "one process, few layers") and "one uvicorn worker". It does not ban the sentences Phase 02 Task 2.4 writes about the scheduler ("Only one scheduler runs at a time; APScheduler 3 does not support two on one job store.", "APScheduler 3 does not support two schedulers on one job store.", "only one of them runs the scheduler"), and it lets a doc say that startup fails when `ENABLE_JOBS` is set. Phase 02 rewrote `docs/project-overview-pdr.md:110`; Task 9.4 step 3 replaces that line again, located by text.
- CI ignores `**/*.md`, `docs/**` and `plans/**` (`.github/workflows/cicd.yml:6-10`). The `10-deploy.sh` change in the same push triggers CI, so the docs ship with a real deploy.
- CI deploys `:latest` (`cicd.yml:79-81` tags `latest` and `sha-<short>`; `deploy/compose.prod.yml:5,59` read `${IMAGE_TAG:-latest}`). The VPS files live in `/opt/pocketquant/deploy/` (`cicd.yml:195,229-240`; `10-deploy.sh:12-14` `cd`s there), so every compose call runs `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env ...`.
- Prod logs use structlog's console renderer with colours (`LOG_FORMAT=console` at `../pocketquant-config/vps/default/.env:27`; `core/common/logging/setup.py:62-71`), so every log parse strips ANSI codes first. Each structlog line starts with an ISO UTC timestamp (`setup.py:55`). Stdlib lines (APScheduler) carry no timestamp (`setup.py:82-86`).
<!-- Red team 2026-10-28: #11 -->
- Measurement helpers: Phase 08 installs `/opt/pocketquant/bin/{snapshot,sample,probe,leases,oom-check}.sh` (names and output in `reports/red-team-shared-contract.md`). This phase reuses them and installs nothing on the VPS. Capture files for one deploy go to `/opt/pocketquant/logs/verify/<name>-<T>.txt`.
- The old trader's log needs no follow: Phase 08's `roll` saves it after `docker stop` and before `docker rm` to `/opt/pocketquant/logs/trader-<id12>-<ts>.log.gz` (`<id12>` = the first 12 characters of the container id), so the drain and release lines are in that file. The deploy script also prunes saved logs older than 30 days.
- OOM rule and deploy window: `plan.md` Conventions. The baseline is the single `oom_baseline=<boot_id> <oom_kill>` line in `reports/machine-baseline.md`.
- The memory note "ES paper subscription" is deleted by Phase 03; this phase only checks it is gone.

## Entry gate

Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, run `rm -f .cache/ssh/vps_key`, and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 09 after <UTC time>
```
1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `git fetch origin && git show origin/master:deploy/compose.prod.yml | grep -c "container_name: pocketquant-app"` prints `0` (Deploy B is on `master`; else `NOT_YET: Deploy B is not on master`).
3. `test -s plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md && echo ok` prints `ok` (Phase 08 recorded the cutover).
<!-- Red team 2026-10-28: #2 #11 -->
4. `grep -c "^oom_baseline=" plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` prints `1` (else `NOT_YET: the OOM baseline line is missing`).
5. Prod topology and helpers:
```bash
mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps -a --format '{{.Names}}' | grep -cx pocketquant-app; docker ps --filter label=com.docker.compose.project=pocketquant-prod --format '{{.Label \"com.docker.compose.service\"}}' | grep -cxE 'api|worker|trader'; ls /opt/pocketquant/bin/snapshot.sh /opt/pocketquant/bin/sample.sh /opt/pocketquant/bin/probe.sh /opt/pocketquant/bin/leases.sh /opt/pocketquant/bin/oom-check.sh | wc -l"
```
prints `0`, `3`, `5` (else `NOT_YET: the cutover or the Phase 08 helpers are not complete in prod`).

## Files to create/modify

- Modify: `deploy/vps/10-deploy.sh`, `docs/system-architecture.md`, `docs/deployment.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, `README.md`, `justfile` (comments), `scripts/audit_bar_quality.py`, `scripts/backfill/binance_bars.py`, `scripts/backfill/provider_bars.py` (docstrings), `deploy/vps/one-time/README.md`.
- Modify only if the Task 9.4 gate still hits them: comments in `deploy/compose.prod.yml`, `deploy/Dockerfile`, `web/nginx.conf`.
- Create/append: `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` (row 1, pending).
<!-- Red team 2026-10-28: #11 -->
- VPS capture files only (not in the repo, no scripts): `/opt/pocketquant/logs/verify/{start,old-trader,snap,stats,probe,oom}-<T>.txt`.

## Tasks

### Task 9.1 — Delete the one-time cutover branch
**Goal:** `10-deploy.sh` has only the rolling path.
**Target files and symbols:** `deploy/vps/10-deploy.sh` (the block guarded by a `pocketquant-app` container check, and any function only that block calls).
**Steps:**
1. `grep -n "pocketquant-app" deploy/vps/10-deploy.sh` and read the block around each hit.
2. Delete the whole conditional block. For each function it calls, run `grep -n "<function>" deploy/vps/10-deploy.sh`; if the only other hit is its definition, delete the function too.
3. Keep `dc`, `roll`, the deploy lock, the image guard, the log capture and pruning, and the main roll sequence unchanged. Delete comments that describe the cutover.
**Success criteria:** no `pocketquant-app` in either VPS script; the script parses; the three role rolls remain.
**Verify:** `grep -c "pocketquant-app" deploy/vps/10-deploy.sh deploy/vps/11-verify.sh; bash -n deploy/vps/10-deploy.sh && echo syntax-ok; grep -oE "roll (api|worker|trader) [0-9]+" deploy/vps/10-deploy.sh | wc -l` prints `deploy/vps/10-deploy.sh:0`, `deploy/vps/11-verify.sh:0`, `syntax-ok`, `3`.

### Task 9.2 — `docs/system-architecture.md`
**Goal:** the architecture doc states the three roles as they are.
**Target files and symbols:** `docs/system-architecture.md` sections Decisions, Startup and Shutdown, Background jobs, Brokers / Exness broker, Persistence (collections table), Deployment Shape; one new section "Roles, leases and handover".
**Steps:**
<!-- Red team 2026-10-28: #10 -->
1. Before writing any number, read it from the code that owns it (for example `git grep -n -i -E "ttl|renew|margin|poll" -- src/pocketquant/core/infra/persistence/repositories/lease_repository.py src/pocketquant/app` and `grep -n -E "stop_grace_period|EXNESS_RATE_FRACTION|APP_ROLES|EXNESS_LIVE_TRADING|start_period" deploy/compose.prod.yml`). Write the code's value; if it differs from this list, the code wins.
2. Decisions: replace "One process, one worker" with one bullet: one image runs as three services; `APP_ROLES` picks a process's roles (`api`, `worker`, `trader`; default `api`); the worker and the trader act only while holding their Mongo lease, so a second copy waits in standby; never `--workers N`.
<!-- Red team 2026-10-28: #1 #4 #5 -->
3. New section "Roles, leases and handover", one idea per sentence:
   - What each role runs: `api` (routes, `/health`, the pause write), `worker` (scheduler, sync jobs, the orphan-backtest sweep job), `trader` (quote feed, bar building, strategies, brokers, reconcile loop, live collector).
   - The `leases` collection: UUIDv7 `_id`, unique `name`, TTL 30 s, renew 10 s, standby poll 0.5 s, `owner` = `hostname:pid`. A lease counts as held only after the takeover work returns. A takeover exception logs ERROR `lease.takeover_failed`, releases the lease and the process sends itself SIGTERM. A lost renewal stops work, logs ERROR `lease.lost` and the process sends itself SIGTERM. `lease.acquired` and `lease.released` mark the normal path.
   - The order fence: `trading_until` = lease expiry minus 5 s; it is re-checked after the open lock and after the pacer wait, right before the send; after it an order is refused with `reason=lease` and never resent; on lease loss, signal tasks that have not reached the send are cancelled.
   - Standby: warm-up before `/health` answers; no broker, no sweep, no reconcile loop, no collector, no write to `bar:current`. Only the trader lease holder writes or deletes `bar:current`; the stored seed carries `gap` and `coverage_start`.
   - Takeover: `trader.takeover handover_gap_ms=` is logged right after `lease.acquired`, before any takeover I/O; the value is the time from the previous holder's release to this acquire, and it is empty when the previous holder lost the lease instead. Then the trader reloads positions and pending orders, restores paper brokers and directions, connects brokers, starts the collector and the reconcile loop, and logs `trader.takeover_complete takeover_ms=` after the reconcile task starts.
   - Drain on SIGTERM: the deadline counts from the start of lifespan shutdown. The trader picks the next 1m boundary B and releases only when every bar of B is published and `inflight_count` is 0. `inflight_count` counts Exness opens in flight and pending acks, running signal tasks and running bar handlers; a pending snapshot is not counted, it re-triggers a snapshot. The trader waits up to B + 30 s, logs `trader.drain_retry boundary=` and retries once at the next boundary; the hard deadline is shutdown start + 150 s with ERROR `trader.drain_timeout inflight=`; then `trader.lease_released inflight= boundary= offset_s=`. Lease renewal keeps running until the engine has stopped and the lease is released; the engine's wait for signal tasks is bounded by the remaining grace (trader grace 180 s).
   - Signals dropped by the lease fence or the drain log INFO `strategy.signal_discarded reason=lease|drain`; standby drops stay DEBUG.
   - Worker stop: pause the scheduler, wait for running jobs within the grace, shut the scheduler down, release the lease.
   - `/health` fields: `role`, `lease`, `lease_renewed_age_s`, `event_loop_lag_max_s`. Rate fractions: `api` 0.05, `worker` 0.3, `trader` 0.6.
4. Same section, money-path facts that run in the trader: the entry pause is read from the store on every open (a failed read refuses the open; the pause route returns 503 when the store write fails); opposite-side entries are rejected on paper and Exness, exits are SL/TP only; bars of every interval close on a timer 0.5 s after their end (bars up to 1h end at the session close when it comes first; 4h/1d/1w end at the bucket end); an entry is skipped with one WARNING `strategy.entry_skipped` when the bar is stale (budgets 1m 10 s, 5m 30 s, 15m 60 s, 1h 120 s, 4h 300 s, 1d and 1w 600 s) or gapped (non-successor bucket, more than 60 s trading-time silence, uncovered mid-bucket start), SL/TP always run; Exness opens run as tasks, paper fills inline; order calls use their own pacer lane; `live.signal_latency` logs `t0_t5_ms` and `t0_t6_ms` per signal.
<!-- Red team 2026-10-28: #5 -->
5. Startup and Shutdown: rewrite the numbered list per role (the role list in step 3 decides what starts); replace the `ENABLE_JOBS=false` paragraph with `APP_ROLES=api` (the default: routes only, no scheduler, no feed, no strategies, no broker, so a local process against prod data writes no bars and sends no order). State that startup fails when `ENABLE_JOBS` is set in the environment, so an old `.env` cannot start jobs by accident. Keep step 1 (`set_sync_container`) if the code still does it.
6. Background jobs: `sync_1m` runs at second 12; the orphan-backtest sweep is a worker job every 5 min that fails only `started` runs whose heartbeat (refreshed every 15 s) is older than 60 s.
7. Persistence table: add `leases` (one document per role lease). If the `apscheduler_jobs` row does not already name the worker, make it `APScheduler's job store, used by the worker (the scheduler process).` Deployment Shape: `web` proxies `/api/*` to the `api` service (nginx re-resolves the service name every 5 s); `api`, `worker`, `trader` have no published port and no fixed container name.
8. Delete every sentence the steps above contradict. No history, no "now", no "previously".
**Success criteria:** no old-topology wording; the new section exists; the file stays under 800 lines.
<!-- Red team 2026-10-28: #10 -->
**Verify:** `grep -c -i -E "pocketquant-app|enable_jobs=|single uvicorn|single worker|single process|single backend|app container|one process,|one uvicorn worker" docs/system-architecture.md; grep -c -E "APP_ROLES|trader\.lease_released|trader\.takeover_complete|strategy\.signal_discarded|leases" docs/system-architecture.md; wc -l < docs/system-architecture.md` prints `0`, then a number ≥ 4, then a number ≤ 800.

### Task 9.3 — `docs/deployment.md`
**Goal:** the deploy and runbook doc matches the three services and the rolling deploy.
**Target files and symbols:** `docs/deployment.md` sections Deploy (flow diagram), Verify, Platform & URLs, Environment & Credentials, Stop real-money entries, Restart while live, Rollback, Troubleshooting, Local access, Data Runbooks.
**Steps:**
1. Container lookup used everywhere in this doc: `ssh <VPS> "cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api <cmd>"` (use `trader` for broker and strategy logs, `worker` for job logs). Replace every `docker exec pocketquant-app` and `docker logs pocketquant-app` with it.
<!-- Red team 2026-10-28: #7 -->
2. Deploy flow: `10-deploy.sh` holds `flock -n /opt/pocketquant/deploy.lock` for the whole run, so a second deploy exits at once; CI does not cancel a running `master` deploy. Then: pull, image guard (the image must contain the lease repository, else exit 1), roll `api`, `worker`, `trader` one at a time. `roll` refuses unless exactly one copy of the service runs; it starts a second copy and waits until healthy; for `api` it disconnects the old copy from the backend network and waits 6 s so nginx stops sending to it; it stops the old copy with its grace period, saves its log to `/opt/pocketquant/logs/<svc>-<id12>-<ts>.log.gz` and removes it. A failed health wait writes the log tail to `/opt/pocketquant/logs/failed-<svc>-<ts>.log` and prints only that path. Then `web`/`cloudflared`, `--remove-orphans`, image prune, and deletion of saved `*.log.gz` older than 30 days. State the grace periods (`api` 30 s, `worker` 120 s, `trader` 180 s) from the compose file. State that `web` is recreated on an image deploy with a few seconds of SPA gap, and is not recreated on a same-tag re-roll.
<!-- Red team 2026-10-28: #5 -->
3. Platform: "8 containers: api, worker, trader (one image, internal :41921), web, cloudflared, MongoDB, Redis, Portainer"; networks: `backend` lists `api`, `worker`, `trader`; port map and the health row use the lookup from step 1. `env_file: .env` is shared by the three roles; each sets `APP_ROLES` and `EXNESS_RATE_FRACTION` in compose, and `api` and `worker` set `EXNESS_LIVE_TRADING: "false"`, so only the trader can send a live order.
<!-- Red team 2026-10-28: #13 -->
4. Restart while live: a rolling deploy hands the trader over at a 1m bar boundary and the new trader rebuilds strategy state, so `exness` subscriptions are not stopped for a deploy. Keep: pause entries before a deploy, rollback or config dispatch; check `"entries_paused":true` after; resume only with a fresh approval. The pause command uses the step 1 lookup with `exec -T api sh -s` and keeps the token off every command line: `printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -H @- -X POST http://localhost:41921/api/v1/admin/safeguards/pause`.
5. Rollback: standard revert stays. Emergency `IMAGE_TAG=sha-<last-good-short>` works only for an image that has the lease repository (the guard refuses older ones); rolling back across the topology change means reverting compose and scripts together and pushing.
<!-- Red team 2026-10-28: #7 -->
6. Troubleshooting: logs, health and restart per role (`docker compose ... logs --tail 50 trader`, `... exec -T trader curl -s localhost:41921/health`, `... restart trader` drains and hands over only when a standby exists, so prefer a same-tag re-roll: `cd /opt/pocketquant && IMAGE_TAG=<running tag> bash deploy/vps/10-deploy.sh`). Logs of removed containers are in `/opt/pocketquant/logs/<svc>-*.log.gz`; failed health waits are in `/opt/pocketquant/logs/failed-<svc>-<ts>.log`.
<!-- Red team 2026-10-28: #5 -->
7. Local access: replace the three `ENABLE_JOBS` bullets with `APP_ROLES=api` (the code default and the `remote-db.env` value): routes only, no scheduler, no feed, no strategy, no broker; mutation routes need no token and write prod Mongo; startup fails when `ENABLE_JOBS` is set, so delete it from old local `.env` files; for bar building go fully local with all roles (`all-local.env` default).
8. Data runbooks: scripts run in `api` (`exec -T api python scripts/...`); the backfill uses `--rate-fraction 0.05` while the worker and the trader run (fractions sum ≤ 1).
**Success criteria:** no fixed backend name and no `ENABLE_JOBS=` setting; the file stays under 800 lines.
<!-- Red team 2026-10-28: #10 -->
**Verify:** `grep -c -i -E "pocketquant-app|enable_jobs=|single uvicorn|single worker|single process|single backend|app container|6 containers|one process,|one uvicorn worker" docs/deployment.md; grep -c -E "exec -T (api|trader|worker)" docs/deployment.md; grep -c "deploy.lock" docs/deployment.md; wc -l < docs/deployment.md` prints `0`, then a number ≥ 5, then a number ≥ 1, then a number ≤ 800.

### Task 9.4 — README, justfile, PDR, codebase summary, script docstrings
**Goal:** no other surface describes the single-process topology.
**Target files and symbols:** `README.md` (lines 19, 21, 39, 54, 75 on 453e8e90), `justfile` comments above `be:`, `docs/project-overview-pdr.md` (NF6 Scale and line 14), `docs/codebase-summary.md` (package map entries for the new role and lease modules), `scripts/audit_bar_quality.py` and `scripts/backfill/*.py` module docstrings, `deploy/vps/one-time/README.md:8,14`.
**Steps:**
1. `README.md`: backend = one image run as `api`, `worker`, `trader` (`APP_ROLES`); `just be` runs all three roles in one process; the "Single worker only" note becomes "Never run `--workers N`: the worker and the trader hold leases"; `ENABLE_JOBS=false just be` becomes `APP_ROLES=api just be`; `remote-db.env` ships with `APP_ROLES=api`; the all-local note drops "set ENABLE_JOBS=true".
2. `justfile`: the two comments above `be:` say the same as step 1 (comments only; no recipe change).
<!-- Red team 2026-10-28: #10 -->
3. `docs/project-overview-pdr.md`: line 14 "one process" -> "one image"; NF6: replace the line that says "One process, one uvicorn worker" with "One image, three roles; one lease-holding worker and one lease-holding trader. Scale vertically."; replace the sharing-rule line (the line Phase 02 Task 2.4 step 6 rewrote, found with `grep -n "scheduler" docs/project-overview-pdr.md`) with "Several processes may share one database; only lease holders run jobs or trade (`APP_ROLES=api` for extra processes)."
4. `docs/codebase-summary.md`: list each module Phase 07-08 added (`git log --name-status --diff-filter=A origin/master -- src/pocketquant | grep -E "^A" | grep -E "role|lease"` shows them) with one line each.
5. Script docstrings: `docker exec pocketquant-app python <script>` -> `docker compose -f compose.prod.yml --env-file .env exec -T api python <script>` (run in `/opt/pocketquant/deploy`).
6. `deploy/vps/one-time/README.md:8,14`: "after the app container becomes healthy" and "after app container becomes healthy" -> "after the `api` service becomes healthy".
7. Run the gate below. For any remaining hit in `deploy/compose.prod.yml`, `deploy/Dockerfile` or `web/nginx.conf`, rewrite only that comment in plain English.
**Success criteria:** the repo-wide gate is empty.
<!-- Red team 2026-10-28: #10 -->
**Verify:** `git grep -n -i -E "pocketquant-app|enable_jobs=|single uvicorn|single worker|single process|single backend|app container|6 containers|one process,|one uvicorn worker" -- README.md CLAUDE.md justfile docs scripts deploy web/nginx.conf ':!docs/journals' ':!plans'` prints nothing.

### Task 9.5 — Gates, commits, push `develop`
**Goal:** both changes on `develop` with CI green.
**Target files and symbols:** the files of Tasks 9.1-9.4.
**Steps:**
<!-- Red team 2026-10-28: #10 -->
1. TV gate (D28): `git grep -n -i -E "tradingview|cme_globex|pandas_market_calendars|seed_index_futures" -- src tests web/src docs pyproject.toml ':!docs/journals' ':!plans'` prints nothing.
2. Doc sizes: `wc -l docs/*.md README.md | awk '$1>800 && $2!="total"' | wc -l` prints `0`.
3. `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`
4. `git add deploy/vps/10-deploy.sh && git commit -m "chore(deploy): remove the one-time cutover branch"`.
5. `git add README.md justfile docs scripts deploy web/nginx.conf && git commit -m "docs: describe the api, worker and trader roles and rolling deploys"`.
6. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
**Success criteria:** pushed; the `develop` CI run is green.
**Verify:** `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && sleep 15 && RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json databaseId -q '.[0].databaseId') && GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null && echo ci-green` prints `ci-green`.

### Task 9.6 — Memory note is gone
**Goal:** the stale "ES paper subscription" note no longer exists (Phase 03 deleted it).
**Target files and symbols:** `C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md`, `.../memory/MEMORY.md`.
**Steps:** run the Verify; edit nothing.
**Success criteria:** file absent and no index line.
**Verify:** `test -e "C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md"; echo $?; grep -c "pocketquant-es-paper-subscription-kept" "C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/MEMORY.md"` prints `1` then `0`.

<!-- Red team 2026-10-28: #2 #11 -->
### Task 9.7 — Machine and lease check before D-6
**Goal:** no OOM since the baseline and both leases held by the compose containers before the first handover deploy.
**Target files and symbols:** `/opt/pocketquant/bin/oom-check.sh`, `/opt/pocketquant/bin/leases.sh` (Phase 08); `reports/machine-baseline.md` line `oom_baseline=`.
**Steps:** run the Verify; install nothing. `OOM_STOP` is the plan's machine stop (`plan.md` OOM rule) and goes to the Failure Protocol with the printed reason.
**Success criteria:** `OOM_OK`; two unexpired leases whose owners match their containers.
**Verify:** `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash /opt/pocketquant/bin/oom-check.sh $B; bash /opt/pocketquant/bin/leases.sh"` prints `OOM_OK`, then a line that ends with `unexpired=2 owners_match=yes`.

### Task 9.8 — [ASK] Deploy D-6 (handover 1 of 10, image deploy)
**Goal:** the cleanup and docs run in prod; the first handover is captured.
**Target files and symbols:** `develop:master` push; CI run; VPS capture files `/opt/pocketquant/logs/verify/*-<T>.txt`; `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`.
**Steps:**
<!-- Red team 2026-10-28: #11 -->
1. Window (the **Deploy window** rule in `plan.md` Conventions): `D=$(date -u +%u); H=$(date -u +%H%M); [ "$D" -le 5 ] && { { [ "$H" -ge 0600 ] && [ "$H" -lt 1120 ]; } || { [ "$H" -ge 1250 ] && [ "$H" -lt 1930 ]; }; } && echo in-window`. No `in-window` -> end with the `NOT_YET` block (`NOT_YET: outside the deploy window`, resume at the next window start).
2. Ask the owner (only an explicit yes counts): "Recommended: có — đẩy develop lên master ngay bây giờ (deploy ảnh mới D-6, tính là handover 1/10). Thay đổi: xoá nhánh cutover một lần trong 10-deploy.sh và cập nhật tài liệu cho api/worker/trader. Live đang tắt (EXNESS_LIVE_TRADING=false), chỉ có paper. web sẽ được tạo lại, SPA gián đoạn vài giây (D27, chỉ ghi nhận). Trả lời `có` hoặc `chưa`." A "chưa" ends with the `NOT_YET` block (`NOT_YET: owner deferred D-6`).
3. Stamp: `date -u +%Y%m%dT%H%M%SZ`; write it down as `<T>` and use it literally below.
<!-- Red team 2026-10-28: #11 #15 -->
4. Capture start (the old trader id, a snapshot, the `docker stats` sampler and the web probe; the sampler runs only until step 7):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'T=<T>; V=/opt/pocketquant/logs/verify; mkdir -p "$V"; cd /opt/pocketquant/deploy; O=$(docker compose -f compose.prod.yml --env-file .env ps -q trader); [ "$(echo "$O" | grep -c .)" = 1 ] || { echo "capture_error trader_containers=$(echo "$O" | grep -c .)"; exit 1; }; echo "$O" | cut -c1-12 > "$V/old-trader-$T.txt"; date -u +%FT%TZ > "$V/start-$T.txt"; bash /opt/pocketquant/bin/snapshot.sh "before-$T" | tee "$V/snap-$T.txt"; bash /opt/pocketquant/bin/sample.sh start "$V/stats-$T.txt"; bash /opt/pocketquant/bin/probe.sh start "$V/probe-$T.txt"; echo capture_started'
```
   It prints the `label=before-<T>` snapshot line, then `capture_started`. A `capture_error` line ends the task with the Failure Protocol.
5. Release: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`.
6. Watch (use the harness background-run facility when it has one; the run takes about 10-15 min): `sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null; GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"`; note `RUN_ID` and the count.
<!-- Red team 2026-10-28: #2 #11 #15 -->
7. Capture stop, right after the run ends (the same command as Phase 10 Task 10.6 step 8; it stops the sampler and the probe, appends the `label=after-<T>` snapshot and runs the OOM check against the baseline):
```bash
B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash -s $B" <<'EOF'
T=<T>; V=/opt/pocketquant/logs/verify
bash /opt/pocketquant/bin/sample.sh stop "$V/stats-$T.txt"
bash /opt/pocketquant/bin/probe.sh stop "$V/probe-$T.txt"
bash /opt/pocketquant/bin/snapshot.sh "after-$T" | tee -a "$V/snap-$T.txt"
bash /opt/pocketquant/bin/oom-check.sh "$1" "$2" | tee "$V/oom-$T.txt"
EOF
```
<!-- Red team 2026-10-28: #4 -->
8. The handover table must have exactly this header and separator (the `discarded` column holds the `strategy.signal_discarded` counts):
```
| # | UTC start | kind | stamp | inflight | offset_s | drain_timeout | handover_gap_ms | takeover_ms | gap_skips | discarded | probe | leases | verify | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
```
   If `handover-log.md` has no line starting `| # | UTC start | kind | stamp |`, append `## Handover deploys`, a blank line and these two lines. If it has the header without `| discarded |`, replace the header and separator lines with these two and insert a `n/a` cell after the `gap_skips` cell of each existing row.
9. Append the pending row: `| 1 | <content of start-<T>.txt> | image | <T> | pending | | | | | | | | | <verdict count from step 6> | pending |`. Phase 10 completes it no earlier than 65 min after the deploy.
**Success criteria:** CI verdict 0 failures; three role containers; no `pocketquant-app`; one takeover and one completed takeover by the new trader; two held leases owned by their containers; no OOM; the pending row exists.
<!-- Red team 2026-10-28: #1 #2 #11 -->
**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; docker ps -a --format "{{.Names}}" | grep -cx pocketquant-app; docker compose -f compose.prod.yml --env-file .env ps -q api worker trader | wc -l; L=$(docker logs "$(docker compose -f compose.prod.yml --env-file .env ps -q trader)" 2>&1 | sed "s/\x1b\[[0-9;]*m//g"); echo "$L" | grep -cE "trader\.takeover( |$)"; echo "$L" | grep -c "trader\.takeover_complete"; bash /opt/pocketquant/bin/leases.sh'; grep -c "| <T> | pending |" plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` prints `0`, `3`, `1`, `1`, a line that ends with `unexpired=2 owners_match=yes`, then `1`; the step 6 count is ≥ 1; the step 7 output ends with `OOM_OK`.

### Task 9.9 — Record, push, remove the key
**Goal:** the pending row is on `develop`; no key copy remains.
**Target files and symbols:** `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`; `.cache/ssh/vps_key`.
**Steps:**
1. `git add plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md && git commit -m "docs(plans): record the first rolling deploy"`.
2. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`.
3. `rm -f .cache/ssh/vps_key`.
**Success criteria:** pushed; key removed.
**Verify:** `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test -f .cache/ssh/vps_key; echo $?` prints `pushed` then `1`.

## Rollback

- Before D-6: `git revert` the two commits on `develop` and push; nothing ran in prod.
- After D-6: the deleted branch was dead (no `pocketquant-app` exists) and the docs change no behaviour, so a revert plus a `develop:master` push [ASK] inside the **Deploy window** of plan.md Conventions restores the files only. An emergency image pin (same [ASK] and window) uses a lease-aware tag: `ssh ... "cd /opt/pocketquant && IMAGE_TAG=sha-<Deploy B short sha> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh"`.
<!-- Red team 2026-10-28: #11 -->
- A run interrupted between Task 9.8 steps 4 and 7 leaves the sampler and the probe running: run the step 7 capture-stop command for that `<T>` first. Capture files live only under `/opt/pocketquant/logs/verify/`; `rm -rf /opt/pocketquant/logs/verify` removes them. The Phase 08 helpers in `/opt/pocketquant/bin/` stay.
- Always `rm -f .cache/ssh/vps_key`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
