---
phase: 11
title: "Re-arm live gate"
status: pending
priority: P1
effort: "per go-live plan (about 1h attention plus calendar days)"
dependencies: [10]
---

# Phase 11: Re-arm live gate

## Goal

<!-- Red team 2026-10-28: #3 -->
Take live trading back on, on the split runtime, by re-running go-live Phases 11 and 12 (`plans/261019-1957-exness-go-live/phase-11-go-live-one-strategy.md`, `phase-12-observation-and-go-live.md`) as written, with the substitutions below, plus the D12 canary and the D33 live re-rolls. The first 20 live entries must reach Exness with p95 `t0_t6_ms` ≤ 2000 and 0 terminal `exness.rate_limited`. During the canary, 3 same-tag re-rolls run while an `exness` subscription is running; each must log `trader.lease_released inflight=0` (after any `trader.drain_retry`) and 0 `trader.drain_timeout`. Go-live is declared only after both pass. This file does not copy the go-live phases; it says how to run them here.

## Context

- Live is disarmed: `Disarm: 2026-10-22T02:02:17Z ... live trading off (config efb6c90)` (`plans/261019-1957-exness-go-live/reports/ship-log.md:13`). Go-live Phase 11's entry gate only checks the `Deploy C (armed):` line (`ship-log.md:12`), and its Task 11.1 Verify needs `"live_trading":true`. Arming was go-live Phase 10 Task 10.5; Task 11.3 here repeats only its flag step, records it in this plan's reports, and never adds a second `Deploy C` line (go-live Phase 11's gate expects exactly one).
- Go-live run state lives in `plans/261019-1957-exness-go-live/reports/round-trip.md`. Its `## Live run 1` section (engulfing EURUSD:EXNESS 1h) has `baseline` and a `called off` note and no `round_trip: DONE` line (`round-trip.md:3-8`), so a re-run would resume that run at Task 11.5 with a 2026-10-22 baseline. Task 11.2 asks the owner to close it first.
- Go-live 11.7 reads the pause rejection as `exness.order_rejected_presubmit ... reason=entries_paused` (go-live `phase-11-go-live-one-strategy.md:18,185`); on 453e8e90 that reason is set at `core/infra/brokers/exness/exness_broker_adapter.py:246-249`. Phase 04 moved the pause into the store; Task 11.1 checks the reason and the `GET /api/v1/admin/safeguards` fields still exist (`app/routes/safeguards.py:24-48` on 453e8e90).
- Exits are venue SL/TP only (D11, D30); there is no close route. A rolling deploy hands the trader over at a 1m boundary (Phase 08), so the trader container id and `StartedAt` change on every deploy. Go-live 11.1 step 5 and go-live 12.5 step 3 stop on a restart while an `exness` position is open (`phase-11-go-live-one-strategy.md:67`, `phase-12-observation-and-go-live.md:125`); the Substitutions table marks D33 re-rolls and the re-arm dispatch as planned restarts.
<!-- Red team 2026-10-28: #10 #11 -->
- Prod logs are console-rendered with ANSI colours (`../pocketquant-config/vps/default/.env:27`); each structlog line starts with an ISO UTC timestamp (`core/common/logging/setup.py:55`). The trader's history is its saved logs (`/opt/pocketquant/logs/trader-<id12>-<ts>.log.gz`, written by the Phase 08 `roll`) plus the live container's log. Read it with this function, defined in the remote script after `cd /opt/pocketquant/deploy` (it prints lines at or after `FROM`; lines from different containers are not in time order, so sort timestamped lines when order matters):
```bash
tl() { { for f in /opt/pocketquant/logs/trader-*.log.gz; do [ -e "$f" ] && zcat "$f"; done; docker logs "$(docker compose -f compose.prod.yml --env-file .env ps -q trader)"; } 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | awk -v a="$(echo "$1" | cut -c1-19)" '/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T/{c = substr($0, 1, 19)} c >= a'; }
```
<!-- Red team 2026-10-28: #2 #7 #11 -->
- VPS helpers (Phase 08, `/opt/pocketquant/bin/`; shapes in `reports/red-team-shared-contract.md`): `snapshot.sh`, `sample.sh`, `probe.sh`, `leases.sh`, `oom-check.sh`. This phase installs no script. The deploy script holds `flock -n /opt/pocketquant/deploy.lock`, so a re-roll cannot overlap a CI deploy. The OOM rule and the deploy window are in `plan.md` Conventions; the OOM baseline is the `oom_baseline=` line of `reports/machine-baseline.md`.
<!-- Red team 2026-10-28: #13 -->
- Secrets stay off command lines: admin calls run inside the `api` container as `printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -H @- ...` (`printf` is a shell builtin; `curl -H @-` reads the header from stdin).

## Substitutions (apply to every command and text in go-live Phases 11 and 12)

| Go-live text | Use here |
|---|---|
| `ssh ... 'docker exec -i pocketquant-app sh -s'` / `'docker exec -i pocketquant-app python -'` | `ssh ... 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api sh -s'` / `... exec -T api python -'` |
| `docker exec pocketquant-app curl ...` / `docker exec pocketquant-app python -c ...` (inside an ssh command or a `bash -s` heredoc) | first line of the remote script `cd /opt/pocketquant/deploy; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }`, then `dc exec -T api curl ...` / `dc exec -T api python -c ...` |
| `docker inspect -f '{{.State.StartedAt}}' pocketquant-app` | `docker inspect -f '{{.State.StartedAt}}' $(dc ps -q trader)` (the trader's start; record it wherever go-live records "app StartedAt") |
| `docker logs --since "$X" pocketquant-app 2>&1` (order, broker, signal and safeguard lines) <!-- Red team 2026-10-28: #10 #11 --> | `tl "$X"` (the Context function, defined after `cd /opt/pocketquant/deploy` in the remote script) |
| `curl ... -H "X-Admin-Token: $ADMIN_TOKEN" ...` (admin calls) <!-- Red team 2026-10-28: #13 --> | `printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" \| curl ... -H @- ...` (same method, URL and other headers) |
| `ENABLE_JOBS=false` (local backend against prod) | `APP_ROLES=api` |
| "closes by the strategy's SL/TP ... or its exit rule" | "closes by its venue SL/TP" (D11; no close route, opposite entries are rejected) |
| "Restart while live" runbook | the runbook as rewritten in Phase 09 (`docs/deployment.md`); a D33 re-roll (Task 11.7) is the one stated exception: entries are not paused for it |
| "unplanned restart" stop in go-live 11.1 step 5 and 12.5 step 3 <!-- Red team 2026-10-28: #3 --> | a trader `StartedAt` that matches a `Live re-roll` line in `plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` or the `Re-armed:` line in `re-arm-log.md` is a planned restart: record it in the row and do not stop; any other new `StartedAt` while positioned stops as written |
| Every `[ASK]` question | asked in Vietnamese, starting with `Recommended: <reply>` and a one-line reason, then the go-live facts |
| `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from NN ...` | `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 11 after <UTC time>` |
| go-live 12.6 "Declare go-live?" <!-- Red team 2026-10-28: #3 --> | ask it only when `grep -c "^Canary: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` prints `1` and `grep -c "^Live re-roll [1-3]/3: .* -> PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` prints `3`; else end with `NOT_YET: D12 canary <n>/20 entries, D33 re-rolls <k>/3` |

Everything else in those files runs as written, including their state records, `NOT_YET` exits, report paths under `plans/261019-1957-exness-go-live/reports/`, commits and Failure Protocol.

## Entry gate

Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, run `rm -f .cache/ssh/vps_key`, and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 11 after <UTC time>
```
1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `grep -c "^Verification verdict: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md` prints `1` (else `NOT_YET: prod verification not complete; run --from 10`).
3. `ls docs/journals/*-exness-go-live.md 2>/dev/null | wc -l` prints `0` (else `NOT_YET: go-live already declared`).

## Files to create/modify

- Create/append: `plans/261028-0652-exness-only-parallel-runtime/reports/re-arm-log.md`, `plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` (canary progress and the D33 `Live re-roll` lines).
- Modify: `../pocketquant-config/vps/default/.env` (key `EXNESS_LIVE_TRADING` only).
- Written by the go-live tasks as they define: `plans/261019-1957-exness-go-live/reports/round-trip.md`, `live-observation.md`, `docs/journals/<date>-exness-go-live.md`.
<!-- Red team 2026-10-28: #3 #11 -->
- VPS data files only (no scripts): `/opt/pocketquant/logs/verify/{start,old-trader,snap,stats,probe,oom,deploy}-<T>.txt` for each D33 re-roll.

## Tasks

Each run starts at Task 11.1 and skips any task whose record already exists.

### Task 11.1 — SSH setup and preflight on the split runtime
**Goal:** the go-live commands will find what they read.
**Target files and symbols:** `.cache/ssh/vps_key`; `src/pocketquant` (pause reason, latency fields, drain events); prod `GET /api/v1/admin/safeguards`; the Phase 08 helpers.
**Steps:**
1. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
2. Run the Verify command.
**Success criteria:** the pause reason, the latency field, the drain events, the safeguards fields and the helpers exist.
<!-- Red team 2026-10-28: #3 #10 #11 -->
**Verify:** `git grep -l 'reason="entries_paused"' -- src/pocketquant/core/infra/brokers/exness/ | wc -l; git grep -l -E "(^|[^a-z0-9_])t0_t6_ms=" -- src/pocketquant | wc -l; git grep -h -o -E '"trader\.(lease_released|drain_retry|drain_timeout)"' -- src/pocketquant | sort -u | wc -l; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api curl -s http://localhost:41921/api/v1/admin/safeguards; echo; ls /opt/pocketquant/bin/snapshot.sh /opt/pocketquant/bin/sample.sh /opt/pocketquant/bin/probe.sh /opt/pocketquant/bin/leases.sh /opt/pocketquant/bin/oom-check.sh | wc -l'` prints a number ≥ 1, a number ≥ 1, `3`, a JSON body containing `"entries_paused":` and `"live_trading":`, then `5`.

### Task 11.2 — [ASK] Close the stale go-live run 1
**Goal:** go-live Phase 11 starts a fresh run with a fresh baseline.
**Target files and symbols:** `plans/261019-1957-exness-go-live/reports/round-trip.md` (`## Live run 1`).
**Steps:**
1. Skip when the last `## Live run` section already has a `round_trip: DONE` line.
2. Ask: "Recommended: đóng — đóng Live run 1 (engulfing EURUSD:EXNESS 1h, đã huỷ ngày 2026-10-22 ở bước 11.5, không có lệnh nào) để go-live Phase 11 bắt đầu một lượt mới với số dư gốc mới; số dư gốc cũ (211.47, 2026-10-22) đã quá cũ cho kiểm tra AC6. Trả lời `đóng` hoặc `tiếp tục run 1`."
3. `đóng` -> append `- round_trip: DONE <UTC> (called off 2026-10-22 at 11.5; no order sent; closed so a new run can start)` to that section. `tiếp tục run 1` -> append nothing; go-live Phase 11 resumes run 1 at Task 11.5.
**Success criteria:** the owner's answer is applied.
**Verify:** `awk '/^## Live run/{n++; d=0} /round_trip: DONE/{d=1} END{print n, d}' plans/261019-1957-exness-go-live/reports/round-trip.md` prints `1 1` after `đóng`, or `1 0` after `tiếp tục run 1`.

### Task 11.3 — [ASK] Re-arm with entries paused
**Goal:** prod runs with `EXNESS_LIVE_TRADING=true`, entries paused, every subscription still paper.
**Target files and symbols:** `../pocketquant-config/vps/default/.env` key `EXNESS_LIVE_TRADING`; `cicd.yml` dispatch; `plans/261028-0652-exness-only-parallel-runtime/reports/re-arm-log.md`.
**Steps:**
1. Skip when `grep -c "^Re-armed:" plans/261028-0652-exness-only-parallel-runtime/reports/re-arm-log.md 2>/dev/null` prints `1`.
<!-- Red team 2026-10-28: #11 -->
2. No time check (plan.md Conventions: no deploy window).
<!-- Red team 2026-10-28: #13 -->
3. Pause (no gate; the token stays inside the container and off every command line):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api sh -s' <<'EOF'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/admin/safeguards/pause
EOF
```
4. Facts: the safeguards body; the count of `"broker":"exness"` subscriptions (expected 0) from `GET /api/v1/subscriptions/` through `exec -T api curl -s`. Ask: "Recommended: có — bật lại EXNESS_LIVE_TRADING=true trong khi entries đang pause (đã lưu, giữ qua restart); hiện có <n> subscription exness nên chưa thể có lệnh nào. Việc này đẩy pocketquant-config và chạy lại CI deploy (handover trader như mọi deploy). Trả lời `có` hoặc `chưa`." A `chưa` ends with the `NOT_YET` block (`NOT_YET: owner deferred re-arming`).
<!-- Red team 2026-10-28: #11 -->
5. On yes: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash /opt/pocketquant/bin/snapshot.sh before-rearm'` (record as before).
6. `sed -i 's/^EXNESS_LIVE_TRADING=.*/EXNESS_LIVE_TRADING=true/' ../pocketquant-config/vps/default/.env && git -C ../pocketquant-config add vps/default/.env && git -C ../pocketquant-config commit -m "feat(env): arm exness live trading" && git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD` (never print a token).
7. Dispatch and watch (use the harness background-run facility when it has one): `GH_TOKEN=$(gh auth token --user camping89) gh workflow run cicd.yml --ref master; sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --event workflow_dispatch --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null && GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"`.
<!-- Red team 2026-10-28: #2 #11 -->
8. `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash /opt/pocketquant/bin/snapshot.sh after-rearm; bash /opt/pocketquant/bin/oom-check.sh $B; cd /opt/pocketquant/deploy && docker inspect -f '{{.State.StartedAt}}' \$(docker compose -f compose.prod.yml --env-file .env ps -q trader)"` (record as after, the OOM check and the trader StartedAt).
9. Create `re-arm-log.md` if absent (`# Live re-arm`), append `Re-armed: <UTC>, run <RUN_ID>, trader StartedAt <value>, entries paused, exness subscriptions 0`, `snapshot before: <snapshot line>`, `snapshot after: <snapshot line>`, `oom: <OOM_OK or OOM_STOP line>`. Commit `docs(plans): record the live re-arm` and push `develop` with the token URL, then `git fetch origin`.
**Success criteria:** armed, paused, recorded; no OOM.
**Verify:** `grep -c "^EXNESS_LIVE_TRADING=true$" ../pocketquant-config/vps/default/.env; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api curl -s http://localhost:41921/api/v1/admin/safeguards'; echo; grep -c "^Re-armed:" plans/261028-0652-exness-only-parallel-runtime/reports/re-arm-log.md` prints `1`, a body containing `"live_trading":true` and `"entries_paused":true`, then `1`; the step 7 count is ≥ 1; the step 8 output contains `OOM_OK`.

### Task 11.4 — Run go-live Phase 11 (one strategy live)
**Goal:** one owner-chosen strategy completes a live round trip under the go-live rules.
**Target files and symbols:** `plans/261019-1957-exness-go-live/phase-11-go-live-one-strategy.md` (Tasks 11.1-11.12); its state record `round-trip.md`.
**Steps:**
1. Skip when the last `## Live run` section has both a `resumed_at:` line and a `round_trip: DONE` line (the Verify command prints `run-done`).
2. Read that file fully. Execute its Tasks 11.1 to 11.12 in order in this session, applying the Substitutions table to every command and question. Skip its entry gate's `Deploy C (armed)` check (Task 11.3 here armed it; the line stays at count 1).
3. A go-live `NOT_YET` exit is this phase's `NOT_YET` exit (with this plan's Resume line). A go-live Verify failure is this phase's Verify failure.
4. Note for Task 11.6 here: record the UTC `resumed_at` of the new run; the canary counts from it.
**Success criteria:** a new `## Live run` section ends with `round_trip: DONE`.
**Verify:** `awk '/^## Live run/{r=0; d=0} /resumed_at:/{r=1} /round_trip: DONE/{d=1} END{print (r && d) ? "run-done" : "open"}' plans/261019-1957-exness-go-live/reports/round-trip.md` prints `run-done`.

### Task 11.5 — Run go-live Phase 12 (daily observation) with the canary and the D33 re-rolls
**Goal:** five clean observation days, a passed canary and 3 passed live re-rolls before go-live is declared.
**Target files and symbols:** `plans/261019-1957-exness-go-live/phase-12-observation-and-go-live.md` (Tasks 12.1-12.6); `live-observation.md`.
**Steps:**
<!-- Red team 2026-10-28: #3 -->
1. Once per UTC day after 03:00Z, execute go-live Tasks 12.1-12.5 with the Substitutions, then Task 11.6 here, then Task 11.7 here, then go-live 12.6 only under the go-live rule in the Substitutions table.
2. Go-live `NOT_YET` exits (fewer than 5 rows, today's row exists, user deferred) are this phase's `NOT_YET` exits; run Tasks 11.6 and 11.7 before exiting. A second run on the same day (for a D33 re-roll inside the deploy window) therefore reaches Task 11.7 through the "today's row exists" exit.
**Success criteria:** go-live 12.6 has run on a day with `Canary: PASS` and 3 `Live re-roll` PASS lines.
**Verify:** `ls docs/journals/*-exness-go-live.md | wc -l; grep -c "^go-live:" plans/261019-1957-exness-go-live/reports/live-observation.md; grep -c "^Canary: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md; grep -c "^Live re-roll [1-3]/3: .* -> PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` prints `1`, `1`, `1`, `3`.

### Task 11.6 — D12 canary (each Phase 12 run)
**Goal:** the first 20 live Exness entries reach the venue fast enough: p95 `t0_t6_ms` ≤ 2000 and 0 terminal `exness.rate_limited`.
**Target files and symbols:** trader `live.signal_latency` lines for the live subscription ids; `plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md`.
**Steps:**
1. Skip when `grep -c "^Canary: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md 2>/dev/null` prints `1`.
2. `<R>` = the `resumed_at` value of the run Task 11.4 completed (the last `## Live run` section with a `resumed_at:` line in `round-trip.md`).
<!-- Red team 2026-10-28: #10 #11 -->
3. Collect (the latency lines are sorted by their timestamp, so "first 20" holds across saved and live logs):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
cd /opt/pocketquant/deploy; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
tl() { { for f in /opt/pocketquant/logs/trader-*.log.gz; do [ -e "$f" ] && zcat "$f"; done; docker logs "$(dc ps -q trader)"; } 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | awk -v a="$(echo "$1" | cut -c1-19)" '/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T/{c = substr($0, 1, 19)} c >= a'; }
R=<R>
IDS=$(dc exec -T api python -c "import json,urllib.request as u;[print(x['id']) for x in json.load(u.urlopen('http://localhost:41921/api/v1/subscriptions/')) if x['broker']=='exness']")
L=$(tl "$R")
echo "$L" | grep 'live\.signal_latency' | grep -F "$IDS" | sort | grep -o 't0_t6_ms=[0-9.]*' | cut -d= -f2 | head -20 > /tmp/pq-canary.txt
echo "entries $(wc -l < /tmp/pq-canary.txt) max $(sort -n /tmp/pq-canary.txt | tail -1)"
echo "p95 $(sort -n /tmp/pq-canary.txt | awk '{a[NR] = $1} END {if (NR < 20) print "n/a"; else {i = int(0.95 * NR); if (i < 0.95 * NR) i++; print a[i]}}')"
echo "terminal_rate_limited $(echo "$L" | grep -cE 'exness\.rate_limited( |$)')"
rm -f /tmp/pq-canary.txt
EOF
```
4. Create `d12-canary.md` if absent (`# D12 canary`). Append `- <UTC>: entries <n>/20, max <ms>, terminal_rate_limited <k>`.
5. `terminal_rate_limited` > 0, or `entries` = 20 and `p95` > 2000 -> pause entries now with the Task 11.3 step 3 admin call, append `Canary: FAIL <UTC> p95 <ms> terminal_rate_limited <k>`, and go to the Failure Protocol.
6. `entries` = 20 and `p95` ≤ 2000 and `terminal_rate_limited 0` -> append `Canary: PASS <UTC> p95 <ms> over 20 entries`.
7. Commit `docs(plans): record the live canary` and push `develop` with the token URL, then `git fetch origin`. Before any exit of this phase run `rm -f .cache/ssh/vps_key`.
**Success criteria:** one progress line per run; a PASS line once 20 entries exist.
**Verify:** `grep -c "^Canary: FAIL" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` prints `0`, and the step 3 output has `terminal_rate_limited 0` and either `entries` < 20 or `p95` ≤ 2000.

<!-- Red team 2026-10-28: #3 -->
### Task 11.7 — [ASK] D33 live re-roll (one per run, until 3 PASS)
**Goal:** prove the drain with a live Exness broker: 3 same-tag re-rolls while an `exness` subscription runs, each with `trader.lease_released inflight=0` (after any `trader.drain_retry`) and 0 `trader.drain_timeout` (D33).
**Target files and symbols:** VPS `deploy/vps/10-deploy.sh`, `deploy/vps/11-verify.sh`; the Phase 08 helpers; `plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` lines `Live re-roll <k>/3: ...`.
**Steps:**
1. Skip when `grep -c "^Live re-roll [1-3]/3: .* -> PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md 2>/dev/null` prints `3`, or when Task 11.4's Verify does not print `run-done` (no live run has resumed yet).
2. Preconditions, all in one call: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }; dc exec -T api python -c "import json,urllib.request as u;[print(\"sub\",x[\"id\"],x[\"symbol\"],x[\"interval\"],x[\"actual_state\"]) for x in json.load(u.urlopen(\"http://localhost:41921/api/v1/subscriptions/\")) if x[\"broker\"]==\"exness\"]"; dc exec -T api curl -s http://localhost:41921/api/v1/admin/safeguards; echo; echo "trader_started $(docker inspect -f "{{.State.StartedAt}}" $(dc ps -q trader))"; flock -n /opt/pocketquant/deploy.lock true && echo lock-free'`. Skip this task in this run when no `sub` line shows `running`, when `trader_started` is less than 70 min ago, when `lock-free` is missing, or when the window check (the **Deploy window** rule in `plan.md` Conventions: `D=$(date -u +%u); H=$(date -u +%H%M); [ "$D" -le 5 ] && { { [ "$H" -ge 0600 ] && [ "$H" -lt 1120 ]; } || { [ "$H" -ge 1250 ] && [ "$H" -lt 1930 ]; }; } && echo in-window`) prints nothing.
3. Facts: the open positions of the running `exness` subscription (`dc exec -T api curl -s http://localhost:41921/api/v1/subscriptions/<id>/positions` in the same remote form); the tag (`docker inspect -f '{{.Config.Image}}' pocketquant-web | sed 's/.*://'`) as `<tag>`; `<k>` = PASS lines so far + 1.
4. Ask (only an explicit yes counts): "Recommended: có — chạy re-roll cùng tag (`IMAGE_TAG=<tag>`) lần <k>/3 ngay bây giờ trong lúc subscription exness <id> (<symbol> <interval>) đang chạy live, để chứng minh trader cũ xả hết lệnh đang bay (`inflight=0`, 0 `drain_timeout`) trước khi tuyên bố go-live (D33). Entries giữ nguyên trạng thái hiện tại (entries_paused=<x>), không pause cho lần re-roll này (ngoại lệ D33 của runbook Restart while live). Vị thế đang mở: <n> (SL/TP nằm trên sàn; trader mới nạp lại vị thế khi tiếp quản). Trader cũ chờ mốc nến 1m, xả lệnh rồi mới nhả lease. Trả lời `có` hoặc `chưa`." A `chưa` ends with the `NOT_YET` block (`NOT_YET: owner deferred D33 re-roll <k>/3`).
5. Stamp `date -u +%Y%m%dT%H%M%SZ` -> `<T>`. Capture start, the re-roll and capture stop: run Phase 10 Task 10.6 steps 5, 6 and 8 as written with this `<T>` and `<tag>` (snapshot, roll-only `docker stats` sampler, probe, old trader id; the deploy script takes the deploy lock itself).
6. Facts from the old trader's saved log and the new trader (replace `<T>`):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
T=<T>; V=/opt/pocketquant/logs/verify; cd /opt/pocketquant/deploy
strip() { sed 's/\x1b\[[0-9;]*m//g'; }
num() { grep -o "$1=[^ ]*" | head -1 | cut -d= -f2; }
OLDL=$(zcat /opt/pocketquant/logs/trader-"$(cat "$V/old-trader-$T.txt")"-*.log.gz | strip)
NL=$(docker logs "$(docker compose -f compose.prod.yml --env-file .env ps -q trader)" 2>&1 | strip)
REL=$(echo "$OLDL" | grep 'trader\.lease_released' | tail -1)
echo "release_lines $(echo "$OLDL" | grep -c 'trader\.lease_released') inflight $(echo "$REL" | num inflight) offset_s $(echo "$REL" | num offset_s)"
echo "drain_retry $(echo "$OLDL" | grep -c 'trader\.drain_retry') drain_timeout $(echo "$OLDL" | grep -c 'trader\.drain_timeout')"
echo "handover_gap_ms $(echo "$NL" | grep -E 'trader\.takeover( |$)' | head -1 | num handover_gap_ms) takeover_ms $(echo "$NL" | grep 'trader\.takeover_complete' | head -1 | num takeover_ms)"
DIS=$(printf '%s\n%s\n' "$OLDL" "$NL" | awk -v a="$(cut -c1-19 "$V/start-$T.txt")" 'substr($0, 1, 19) >= a' | grep 'strategy\.signal_discarded')
echo "discarded lease:$(echo "$DIS" | grep -c 'reason=lease') drain:$(echo "$DIS" | grep -c 'reason=drain')"
echo "trader_started $(docker inspect -f '{{.State.StartedAt}}' "$(docker compose -f compose.prod.yml --env-file .env ps -q trader)")"
bash /opt/pocketquant/bin/leases.sh
EOF
```
7. PASS when: the step 5 re-roll printed `deploy_exit 0` then `1`; the capture stop ended with `OOM_OK`; `release_lines 1`; `inflight 0`; `drain_timeout 0`; `takeover_ms` present; the `leases.sh` line ends with `unexpired=2 owners_match=yes`. Recorded, not judged: `drain_retry`, `offset_s`, `handover_gap_ms`, `discarded`, the probe.
8. Append to `d12-canary.md`: `Live re-roll <k>/3: <T> sub <id> trader StartedAt <trader_started> inflight=<n> drain_retry=<r> drain_timeout=<d> offset_s=<o> handover_gap_ms=<g> takeover_ms=<t> discarded lease:<a> drain:<b> -> PASS` (or `-> FAIL`). Also append `- planned re-roll: <T>, trader StartedAt <trader_started>` to the last `## Live run` section of `round-trip.md` (after its `round_trip: DONE` line; the Task 11.4 Verify still prints `run-done`), so the go-live restart checks see a planned restart.
9. FAIL -> pause entries now with the Task 11.3 step 3 admin call, then go to the Failure Protocol.
10. Commit `docs(plans): record a live re-roll` with `d12-canary.md` and `round-trip.md`, push `develop` with the token URL, then `git fetch origin`.
**Success criteria:** one `Live re-roll` line for `<T>`; no FAIL line.
**Verify:** `grep -c "^Live re-roll [1-3]/3: <T> .* -> PASS$" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md; grep -c "^Live re-roll .* -> FAIL$" plans/261028-0652-exness-only-parallel-runtime/reports/d12-canary.md` prints `1` then `0`.

## Rollback

<!-- Red team 2026-10-28: #3 #13 -->
Softest first, as in the go-live plan: Pause (SPA strip, or the Task 11.3 step 3 admin call); stop the `exness` subscription (`printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/subscriptions/<id>/stop` through `exec -T api sh -s`); close in the Exness app. Disarm only with a flat account and after deleting every `exness` subscription: `sed -i 's/^EXNESS_LIVE_TRADING=.*/EXNESS_LIVE_TRADING=false/' ../pocketquant-config/vps/default/.env`, commit `feat(env): disarm exness live trading`, push `pocketquant-config`, and dispatch `cicd.yml` [ASK] inside the **Deploy window** of plan.md Conventions (pause and stop above need no deploy and need no window), recording `snapshot.sh` lines before and after in `re-arm-log.md`. A D33 re-roll that fails mid-way is recovered by the roll script, or by the same re-roll once the deploy lock is free and the time is inside the deploy window; a run interrupted between capture start and stop runs Phase 10 Task 10.6 step 8 for that `<T>`. Re-opening go-live run 1 is not supported once it is closed. Always `rm -f .cache/ssh/vps_key`.

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
