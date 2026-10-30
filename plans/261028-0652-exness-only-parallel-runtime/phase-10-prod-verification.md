---
phase: 10
title: "Prod verification: 10 handovers, 14 days paper, machine limits"
status: pending
priority: P1
effort: "about 20-40 min per run; 14+ calendar days"
dependencies: [9]
---

# Phase 10: Prod verification

## Goal

Prove the split in prod with live off: 10 handover deploys that count under D36 (D-6 is row 1; at least 5 same-tag re-rolls), 14 consecutive clean paper days, 2 weekly rows with the 7-day job metrics, and a D25 table that shows the owner the limits of the current 2 vCPU / 3 GB machine. Measurements are record-only (D31); the only machine stop is the OOM rule in `plan.md` Conventions. Machine load is sampled only during a roll; each run day adds one light snapshot (D34).

## Re-run rule

Run this phase once per UTC day after 01:00Z, and again the same day for another re-roll at least 70 min after the previous deploy. Every run executes Tasks 10.1-10.7 in order; each task skips work its report already holds. Each run appends to three files: `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` (one row per deploy), `plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md` (one row per UTC day, one per week), `plans/261028-0652-exness-only-parallel-runtime/reports/machine-limits.md` (one D25 row per deploy, one snapshot row per run day, then the owner summary). A run that is not finished ends with the `NOT_YET` block; that is not a failure.

## Context

- Deploys: a same-tag re-roll is `cd /opt/pocketquant && IMAGE_TAG=<running web tag> bash deploy/vps/10-deploy.sh` (`deploy/vps/10-deploy.sh:7-9` documents manual runs). CI deploys `:latest` (`.github/workflows/cicd.yml:79-81`, `deploy/compose.prod.yml:5,59`), so the running tag is normally `latest`; the same tag leaves `web` untouched [I: compose recreates only on a config or image change]. Any other `master` push during this phase is an image deploy: `web` is recreated (D27) and its probe is recorded only.
<!-- Red team 2026-10-28: #7 -->
- Deploy lock and log pruning belong to the deploy script (Phase 08): `10-deploy.sh` holds `flock -n /opt/pocketquant/deploy.lock` for the whole run, so a re-roll cannot overlap a CI deploy, and it deletes saved `*.log.gz` older than 30 days. This phase only checks that the lock is free before a re-roll and never prunes logs itself.
<!-- Red team 2026-10-28: #1 #4 -->
- Log events (names and fields as in `reports/red-team-shared-contract.md`): old trader `trader.drain_retry boundary=`, `trader.drain_timeout inflight=` (ERROR), `trader.lease_released inflight= boundary= offset_s=`; new trader `trader.standby`, `lease.acquired`, `trader.takeover handover_gap_ms=` (logged right after `lease.acquired`; empty when the previous holder lost the lease), `trader.takeover_complete takeover_ms=` (after the reconcile task starts); `strategy.signal_discarded reason=lease|drain` (INFO), `strategy.entry_skipped reason=stale|gap|lease|inflight bar_start= interval=` (WARNING); `lease.lost`, `lease.takeover_failed`, `lease.released`; plus `event_loop.lag lag_s=`, `live.signal_latency t0_t5_ms= t0_t6_ms=`, `exness.rate_limited op=`, `exness.rate_limited_retry`. Task 10.1 checks these names and fields exist in `src` before any row is read.
<!-- Red team 2026-10-28: #11 #15 -->
- Prod logs are console-rendered with ANSI colours (`../pocketquant-config/vps/default/.env:27`, `core/common/logging/setup.py:62-71`); each structlog line starts with an ISO UTC timestamp (`setup.py:55`), stdlib lines carry none (`setup.py:82-86`). A role's history is its saved logs (`/opt/pocketquant/logs/<svc>-<id12>-<ts>.log.gz`, written by `roll` after `docker stop` and before `docker rm`) plus the live container's log; the commands below join them, strip colours and give an untimestamped line the time of the line before it. Container logs use the json-file driver with `max-size: "10m"`, `max-file: "3"` (the backend block at `deploy/compose.prod.yml:87-91` on 453e8e90, which Phase 08 moves into the shared backend block), so a live container keeps at most about 30 MB of log; the deploy script keeps saved logs for 30 days. Do not leave day rows unwritten for long.
<!-- Red team 2026-10-28: #11 #15 -->
- VPS helpers (Phase 08, `/opt/pocketquant/bin/`; output shapes in the shared contract): `snapshot.sh <label>` (one line `label= ts= mem_used_mb= mem_available_mb= swap_used_mb= load1= psi_some_avg10= oom= boot_id=`), `sample.sh start|stop <file>` (`docker stats --no-stream` every 2 s, only while a roll runs, D34), `probe.sh start|stop <file>` (web probe every 0.5 s), `leases.sh` (`worker=<owner> trader=<owner> unexpired=<n> owners_match=<yes|no>`), `oom-check.sh <boot_id> <count>` (`OOM_OK` or `OOM_STOP <reason>`). This phase installs no script on the VPS; capture files go to `/opt/pocketquant/logs/verify/<name>-<T>.txt` and daily latency samples to `/opt/pocketquant/logs/verify/lat-<D>.txt`.
<!-- Red team 2026-10-28: #2 -->
- OOM rule (`plan.md` Conventions): every check passes the single `oom_baseline=<boot_id> <oom_kill>` line of `reports/machine-baseline.md` to `oom-check.sh`; never compare an absolute count.
- `job_history` fields: `job_id`, `status` (`completed` on success), `started_at`, `duration_ms` (`core/infra/persistence/repositories/job_history_repository.py:35-74`, `engine/market_data/app_services/sync_jobs.py:177-182`); skip rows have `status` `skipped_max_instances` (`job_history_repository.py:76-96`).
- Session check (D36, plan.md): a handover row counts only when the `XAUUSD:EXNESS` calendar is open at the deploy start and for the 15 min after it. The check uses the code's calendar (`EXNESS_CALENDARS` in `core/infra/calendars/exness_session_calendar_adapter.py`, id `EXNESS_XAUUSD`, `is_open`), so it follows the session table and the US DST shift. It tests every minute from `S` to `S` + 15 min; the shortest XAUUSD close (the daily break) lasts about 62 min, so no close falls between two tests. `S` is a UTC time such as `2026-10-30T05:00:00Z` (a row's start, or `$(date -u +%FT%TZ)` for now):
```bash
S=<UTC time>; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T trader python -c 'import sys; from datetime import datetime, timedelta; from pocketquant.core.infra.calendars.exness_session_calendar_adapter import EXNESS_CALENDARS; c = next(x for x in EXNESS_CALENDARS if x.calendar_id == \"EXNESS_XAUUSD\"); t = datetime.fromisoformat(sys.argv[1]); print(\"in-session\" if all(c.is_open(t + timedelta(minutes=m)) for m in range(16)) else \"off-session\")' $S"
```
  It prints `in-session` or `off-session`. It is a counting rule, not a deploy permission (plan.md Conventions: no deploy window).
- Subscriptions: `GET /api/v1/subscriptions/` lists `id`, `strategy_code`, `symbol`, `interval`, `broker`, `actual_state`; start is `POST /api/v1/subscriptions/{id}/start` (`app/routes/strategy.py:87-92`). Prod had XAUUSD 1m stopped on 2026-10-28 (`plans/reports/kongming-261028-1020-parallel-exness-only-reanalysis.md:27`).
<!-- Red team 2026-10-28: #11 -->

## Entry gate

Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, run `rm -f .cache/ssh/vps_key`, and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 10 after <UTC time>
```
1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `git fetch origin && git show origin/master:deploy/vps/10-deploy.sh | grep -c pocketquant-app` prints `0` (D-6 is on `master`).
3. `grep -c "^| 1 |" plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` prints `1`.
4. `grep -c "^Verification verdict: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md 2>/dev/null` prints `0` or nothing (else `NOT_YET: verification already passed; run --from 11`).
<!-- Red team 2026-10-28: #2 #11 -->
5. `grep -c "^oom_baseline=" plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` prints `1`.
6. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'ls /opt/pocketquant/bin/snapshot.sh /opt/pocketquant/bin/sample.sh /opt/pocketquant/bin/probe.sh /opt/pocketquant/bin/leases.sh /opt/pocketquant/bin/oom-check.sh | wc -l'` prints `5`.

## Files to create/modify

- Create/append: `plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md`, `.../reports/paper-daily.md`, `.../reports/machine-limits.md`.
<!-- Red team 2026-10-28: #11 #15 -->
- VPS data files only (no scripts): `/opt/pocketquant/logs/verify/{start,old-trader,snap,stats,probe,oom,deploy}-<T>.txt`, `/opt/pocketquant/logs/verify/lat-<D>.txt`.
- No source, doc or test file changes.

## Tasks

<!-- Red team 2026-10-28: #1 #10 #11 #15 -->
### Task 10.1 — Setup, name check, open captures
**Goal:** every later command reads names that exist; no sampler from an interrupted run is still running.
**Target files and symbols:** `src/pocketquant` log event names and fields; `/opt/pocketquant/logs/verify/snap-*.txt`.
**Steps:**
1. Names and fields in the code on `develop` (12 contract events, 4 more events this phase reads, 11 fields):
```bash
git grep -h -o -E '"(lease\.(acquired|lost|takeover_failed|released)|trader\.(standby|takeover|takeover_complete|drain_retry|drain_timeout|lease_released)|strategy\.(signal_discarded|entry_skipped))"' -- src/pocketquant | sort -u | wc -l
git grep -h -o -E '"(event_loop\.lag|live\.signal_latency|exness\.rate_limited|exness\.rate_limited_retry)"' -- src/pocketquant | sort -u | wc -l
for t in inflight offset_s boundary handover_gap_ms takeover_ms reason bar_start interval lag_s t0_t5_ms t0_t6_ms; do printf "%s %s\n" "$t" "$(git grep -l -E "(^|[^a-z0-9_])$t=" -- src/pocketquant | wc -l)"; done
grep -c "^LOG_FORMAT=console$" ../pocketquant-config/vps/default/.env
```
2. Open captures and saved logs: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'V=/opt/pocketquant/logs/verify; for f in "$V"/snap-*.txt; do [ -e "$f" ] || continue; T=$(basename "$f" .txt | sed "s/^snap-//"); grep -q "label=after-$T" "$f" || echo "open_capture $T"; done; ls /opt/pocketquant/logs/trader-*.log.gz | wc -l'`.
3. For each `open_capture <T>` line, run the Task 10.6 step 8 capture-stop command for that `<T>` now (a run was interrupted mid-roll).
**Success criteria:** 12 contract events; 4 other events; every field token found; console logs; no open capture; at least one saved trader log.
**Verify:** run the step 1 block, then the step 2 command again. They print `12`; `4`; eleven `<token> <n>` lines, each `n` ≥ 1; `1`; then no `open_capture` line and a number ≥ 1.

### Task 10.2 — [ASK] once: start the XAUUSD 1m paper subscription
**Goal:** 1m Exness signals exist so the `t0_t5_ms` criterion has samples.
**Target files and symbols:** prod subscription for `XAUUSD:EXNESS` `1m`; `reports/paper-daily.md` line `Paper start:`.
**Steps:**
1. Skip this task when `grep -c "^Paper start:" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md` prints `1`.
2. List: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api python -c "import json,urllib.request as u;[print(x[\"id\"],x[\"strategy_code\"],x[\"symbol\"],x[\"interval\"],x[\"broker\"],x[\"actual_state\"]) for x in json.load(u.urlopen(\"http://localhost:41921/api/v1/subscriptions/\")) if x[\"symbol\"]==\"XAUUSD:EXNESS\" and x[\"interval\"]==\"1m\"]"'`.
3. Ask (only an explicit yes counts): "Recommended: có — bật lại subscription paper XAUUSD:EXNESS 1m (<id>, <strategy_code>) để tiêu chí độ trễ 1m (`t0_t5_ms` p95 ≤ 1000 ms) có mẫu đo trong 14 ngày. Live đang tắt nên không có lệnh tiền thật. Trả lời `có` hoặc `chưa`." If step 2 printed no line, ask instead: "Recommended: có — tạo subscription paper hitnrun2 XAUUSD:EXNESS 1m (không có subscription 1m Exness nào) để có mẫu độ trễ. Trả lời `có` hoặc `chưa`." A `chưa` ends with the `NOT_YET` block (`NOT_YET: owner deferred the 1m paper subscription`).
<!-- Red team 2026-10-28: #13 -->
4. On yes, admin call with the token kept inside the container and off every command line (`printf` is a shell builtin; `curl -H @-` reads the header from stdin). Create first only when step 2 printed nothing:
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api sh -s' <<'EOF'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/subscriptions/<id>/start
EOF
```
   (create: `printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- -H 'Content-Type: application/json' -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","broker":"paper"}' http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions` in the same heredoc form, note its `id`, then the start call.)
5. If `paper-daily.md` does not exist, create it with `# Paper daily rows` and the table header of Task 10.4. Append the line `Paper start: <UTC now>, subscription <id>`.
**Success criteria:** the subscription runs; the start line exists.
**Verify:** re-run the step 2 command after 30 s; it prints the id with `paper running`; `grep -c "^Paper start:" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md` prints `1`.

### Task 10.3 — Complete pending handover rows
**Goal:** every captured deploy older than 65 min becomes a judged row in `handover-log.md` and a D25 row in `machine-limits.md`.
**Target files and symbols:** rows containing `| pending |` in `handover-log.md`.
**Steps:**
1. For each pending row, read its stamp `<T>` and start time. If the start is less than 65 min ago, leave it and skip Task 10.6 in this run. Rows are judged before any later deploy (Task 10.6 never deploys while a row is pending), so the running trader is the one that took over at `<T>`.
<!-- Red team 2026-10-28: #1 #4 #11 #15 -->
2. Handover facts (replace `<T>` in the first line):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
T=<T>; V=/opt/pocketquant/logs/verify; cd /opt/pocketquant/deploy
dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
strip() { sed 's/\x1b\[[0-9;]*m//g'; }
num() { grep -o "$1=[^ ]*" | head -1 | cut -d= -f2; }
START=$(cat "$V/start-$T.txt"); O=$(cat "$V/old-trader-$T.txt")
OLDL=$(zcat /opt/pocketquant/logs/trader-"$O"-*.log.gz | strip)
NEW=$(dc ps -q trader); echo "trader_containers $(echo "$NEW" | grep -c .)"
NL=$(docker logs "$NEW" 2>&1 | strip)
REL=$(echo "$OLDL" | grep 'trader\.lease_released' | tail -1); BND=$(echo "$REL" | num boundary)
echo "release_lines $(echo "$OLDL" | grep -c 'trader\.lease_released')"
echo "inflight $(echo "$REL" | num inflight) offset_s $(echo "$REL" | num offset_s) boundary $BND"
echo "drain_retry $(echo "$OLDL" | grep -c 'trader\.drain_retry') drain_timeout $(echo "$OLDL" | grep -c 'trader\.drain_timeout')"
echo "handover_gap_ms $(echo "$NL" | grep -E 'trader\.takeover( |$)' | head -1 | num handover_gap_ms)"
echo "takeover_ms $(echo "$NL" | grep 'trader\.takeover_complete' | head -1 | num takeover_ms)"
SB=$(echo "$NL" | grep -m1 'trader\.standby' | cut -d' ' -f1)
echo "warmup_s $(( $(date -u -d "$SB" +%s) - $(date -u -d "$(docker inspect -f '{{.State.StartedAt}}' "$NEW")" +%s) ))"
BOTH=$(printf '%s\n%s\n' "$OLDL" "$NL")
DIS=$(echo "$BOTH" | awk -v a="$(echo "$START" | cut -c1-19)" 'substr($0, 1, 19) >= a' | grep 'strategy\.signal_discarded')
echo "discarded lease:$(echo "$DIS" | grep -c 'reason=lease') drain:$(echo "$DIS" | grep -c 'reason=drain')"
if [ -z "$BND" ]; then echo "gap_skips n/a"; else
  B=$(date -u -d "$BND" +%s)
  echo "gap_skips $(echo "$BOTH" | grep 'strategy\.entry_skipped' | grep 'reason=gap' | while read -r l; do
    case "$(echo "$l" | num interval)" in 1m) n=60;; 5m) n=300;; 15m) n=900;; 1h) n=3600;; 4h) n=14400;; 1d) n=86400;; 1w) n=604800;; *) n=0;; esac
    d=$(( $(date -u -d "$(echo "$l" | num bar_start)" +%s) - B )); [ "${d#-}" -le "$n" ] && echo x; done | wc -l)"
fi
echo "probe $(awk '{print $NF}' "$V/probe-$T.txt" | sort | uniq -c | awk '{printf "%s:%s ", $2, $1}')"
echo "probe_non200 $(awk '$NF != "200"' "$V/probe-$T.txt" | wc -l)"
for r in api worker trader; do
  m=$(docker logs --since "$START" "$(dc ps -q "$r")" 2>&1 | strip | grep 'event_loop\.lag' | grep -o 'lag_s=[0-9.]*' | cut -d= -f2 | sort -n | tail -1)
  echo "lag_max_$r ${m:-<0.25}"
done
m=$(echo "$OLDL" | grep 'event_loop\.lag' | grep -o 'lag_s=[0-9.]*' | cut -d= -f2 | sort -n | tail -1); echo "lag_max_old_trader ${m:-<0.25}"
bash /opt/pocketquant/bin/leases.sh
cat "$V/snap-$T.txt"; echo "oom_at_capture $(cat "$V/oom-$T.txt" 2>/dev/null || echo n/a)"
awk '{n = ""; c = ""; m = ""; for (i = 1; i <= NF; i++) { if (n == "" && $i ~ /^pocketquant/) n = $i; if (c == "" && $i ~ /%$/) c = $i; if (m == "" && $(i + 1) == "/") m = $i }
  if (n == "" || m == "") next; sub(/%/, "", c); v = m + 0; if (m ~ /GiB/) v *= 1024; else if (m ~ /KiB/) v /= 1024; else if (m !~ /MiB/) v /= 1048576
  if (v > r[n]) r[n] = v; if (c + 0 > p[n]) p[n] = c + 0 }
  END { for (k in r) printf "peak %s rss_mib=%.0f cpu_pct=%.1f\n", k, r[k], p[k] }' "$V/stats-$T.txt"
EOF
```
<!-- Red team 2026-10-28: #2 -->
3. OOM check now: `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash /opt/pocketquant/bin/oom-check.sh $B"`. `OOM_STOP` in this output or in `oom_at_capture` -> do the Task 10.7 OOM step now.
<!-- Red team 2026-10-28: #1 #4 #15 -->
4. Verdict PASS when all hold: `release_lines 1`, `inflight 0`, `0 ≤ offset_s ≤ 30`, `drain_timeout 0`, `trader_containers 1`, `handover_gap_ms` present and ≤ 2000, `takeover_ms` present and ≤ 5000, `gap_skips 0` (only skips whose `bar_start` is within one interval of the release `boundary`), the `leases.sh` line ends with `unexpired=2 owners_match=yes`, the row's `verify` cell ≥ 1, and for `re-roll` rows `probe_non200 0` (for `image` rows the probe is recorded only, D27). Recorded, not judged: `drain_retry`, `discarded`, `warmup_s`, the lag values and every D25 value. A 4h, 1d or 1w bar that contains the boundary may close after the row is judged; its `reason=gap` skips appear in the daily `entry_skipped` counts.
5. Session (D36): run the Context session check with `S=<start>`. On `off-session` write the kind as `<kind> (off-session)`; the row is judged as usual but does not count toward the ten.
6. Replace the pending line with the full row: `| <#> | <start> | <kind> | <T> | <inflight> | <offset_s> | <drain_timeout> | <handover_gap_ms> | <takeover_ms> | <gap_skips> | lease:<a> drain:<b> | <probe> | <leases.sh line> | <verify> | PASS or FAIL |`.
<!-- Red team 2026-10-28: #2 #15 -->
7. If `machine-limits.md` does not exist, create it with `# Machine limits (2 vCPU / 3 GB VPS, D25)` and the header:
```
| row | UTC | source | snapshot before | snapshot after | peak RSS MiB / CPU% per container (during the roll) | loop lag max s api/worker/trader (old trader) | warm-up s | takeover_ms | handover_gap_ms | OOM check |
|---|---|---|---|---|---|---|---|---|---|---|
```
   A snapshot cell is `used/avail/swap MiB, load1, psi, oom=` from one `snapshot.sh` line.
8. Append the D25 row `| h<#> | <start> | handover <#> (<kind>) | ...` from the same output (every `peak` line goes into one cell as `name rss/cpu; ...`; the OOM cell holds `oom_at_capture` and the step 3 result).
**Success criteria:** no row older than 65 min stays pending; each judged row has its D25 row.
**Verify:** `grep "| pending |" plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md | cut -d"|" -f3; date -u +%FT%TZ` prints only start times less than 65 min before the last line (the current time), or only the current time; and `grep -cE "^\| [0-9]+ \|.*\| FAIL \|$" plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` prints `0`. A FAIL row stops the phase (Failure Protocol); after its fix ships, only rows after the fix count toward the 10.

### Task 10.4 — Daily rows and the day snapshot
**Goal:** one judged row per completed UTC day since `Paper start`, and one light machine snapshot per run day.
**Target files and symbols:** `paper-daily.md` daily table; `machine-limits.md` snapshot rows.
**Steps:**
1. Days to record: every UTC date after the `Paper start` date and before today that has no row.
<!-- Red team 2026-10-28: #11 #15 -->
2. Per day `<D>` (replace `<D>` in the first line):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'bash -s' <<'EOF'
D=<D>; N=$(date -u -d "$D + 1 day" +%F); V=/opt/pocketquant/logs/verify; cd /opt/pocketquant/deploy
dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
rl() { { for f in /opt/pocketquant/logs/"$1"-*.log.gz; do [ -e "$f" ] && zcat "$f"; done; docker logs "$(dc ps -q "$1")"; } 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | awk -v a="${D}T00:00:00" -v b="${N}T00:00:00" '/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T/{c = substr($0, 1, 19)} c >= a && c < b'; }
for r in api worker trader; do rl "$r" > "/tmp/pq-day-$r.log"; done
cat /tmp/pq-day-api.log /tmp/pq-day-worker.log /tmp/pq-day-trader.log > /tmp/pq-day-all.log
lag() { grep 'event_loop\.lag' | grep -o 'lag_s=[0-9.]*' | cut -d= -f2 | sort -n | tail -1; }
echo "trader_lag_ge_0_5 $(grep 'event_loop\.lag' /tmp/pq-day-trader.log | grep -o 'lag_s=[0-9.]*' | cut -d= -f2 | awk '$1 >= 0.5' | wc -l)"
for r in api worker trader; do
  m=$(lag < "/tmp/pq-day-$r.log"); line="lag_max_$r ${m:-<0.25}"
  for h in 00 03 04 12; do m=$(grep "^${D}T${h}:0[0-4]" "/tmp/pq-day-$r.log" | lag); line="$line ${h}z=${m:-<0.25}"; done
  echo "$line"
done
echo "listener_errors $(grep -c 'Error notifying listener' /tmp/pq-day-all.log)"
echo "scheduler_skip_lines $(grep -c 'maximum number of running instances reached' /tmp/pq-day-worker.log)"
echo "rate_limited_retry $(grep -c 'exness\.rate_limited_retry' /tmp/pq-day-all.log)"
echo "terminal_429_order_ops $(grep -E 'exness\.rate_limited( |$)' /tmp/pq-day-all.log | grep -cE 'openPosition|getOperationStatus')"
echo "lease_lost $(grep -cE 'lease\.(lost|takeover_failed)' /tmp/pq-day-all.log)"
echo "entry_skipped $(grep 'strategy\.entry_skipped' /tmp/pq-day-trader.log | grep -o 'reason=[a-z_]*' | sort | uniq -c | awk '{printf "%s:%s ", $2, $1}')"
grep 'live\.signal_latency' /tmp/pq-day-trader.log | grep 'interval=1m' | grep ':EXNESS' | grep -o 't0_t5_ms=[0-9.]*' | cut -d= -f2 > "$V/lat-$D.txt"
echo "t0_t5_1m_exness $(sort -n "$V/lat-$D.txt" | awk '{a[NR] = $1} END {if (NR < 5) print "n/a n=" NR; else {i = int(0.95 * NR); if (i < 0.95 * NR) i++; print "p95=" a[i] " n=" NR}}')"
bash /opt/pocketquant/bin/leases.sh
rm -f /tmp/pq-day-*.log
EOF
```
3. Rolling 7-day retries = this day's `rate_limited_retry` plus the previous 6 rows' counts.
4. Verdict PASS when: `listener_errors 0`, `terminal_429_order_ops 0`, `lease_lost 0`, the `leases.sh` line ends with `unexpired=2 owners_match=yes`, rolling 7-day retries ≤ 72, and the latency cell is `n/a` or `p95` ≤ 1000. Recorded, not judged (D31): `trader_lag_ge_0_5`, the lag cells, `entry_skipped`.
5. Table (header created by Task 10.2):
```
| UTC day | trader lag ≥ 0.5 s (count) | lag max api / worker / trader (00z 03z 04z 12z) | listener errors | scheduler skip lines | 429 retry day / 7d | terminal 429 order ops | lease.lost | leases | entry_skipped by reason | 1m Exness t0_t5 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
```
<!-- Red team 2026-10-28: #2 #15 -->
6. Day snapshot (D34; once per run day, skipped when `machine-limits.md` already has a row starting `| s<today> |`): `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash /opt/pocketquant/bin/snapshot.sh day; bash /opt/pocketquant/bin/oom-check.sh $B"`. Append `| s<today> | <ts> | day snapshot | <snapshot cell> | n/a | n/a | n/a | n/a | n/a | n/a | <OOM_OK or OOM_STOP line> |` to `machine-limits.md` (create it with the Task 10.3 step 7 header if absent).
7. OOM stop: `OOM_STOP` -> do the Task 10.7 OOM step now.
**Success criteria:** every completed day has one row; this run day has one snapshot row.
**Verify:** `grep -cE "^\| 20[0-9]{2}-[0-9]{2}-[0-9]{2} \|.*\| FAIL \|$" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md; grep -c "^| s$(date -u +%F) |" plans/261028-0652-exness-only-parallel-runtime/reports/machine-limits.md` prints `0` then `1`. A FAIL day stops the phase (Failure Protocol) and resets the 14-day count to 0 after the fix ships.

### Task 10.5 — Weekly rows and 7-day job metrics
**Goal:** a weekly row after the 7th and the 14th consecutive PASS day.
**Target files and symbols:** `paper-daily.md` section `## Weekly`; prod `job_history`.
**Steps:**
1. Run only when the count of consecutive PASS daily rows is 7 or 14 and that week has no weekly row.
2. Job metrics (window = the last 7 days, all after the TradingView removal):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api python -' <<'EOF'
from datetime import UTC, datetime, timedelta
from statistics import median
from pymongo import MongoClient
from pocketquant.core.config import get_settings
s = get_settings(); db = MongoClient(str(s.mongodb_url))[s.mongodb_database]; since = datetime.now(UTC) - timedelta(days=7)
for j in ("sync_integrity", "sync_repair"):
    d = [x["duration_ms"] for x in db.job_history.find({"job_id": j, "status": "completed", "started_at": {"$gte": since}}, {"duration_ms": 1}) if x.get("duration_ms") is not None]
    print(j, "n", len(d), "p50_s", round(median(d) / 1000, 1) if d else None)
print("skipped_max_instances", db.job_history.count_documents({"status": "skipped_max_instances", "started_at": {"$gte": since}}))
EOF
```
3. Pooled latency for the same 7 days (`<END>` = the last day of the week): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/logs/verify && for i in 0 1 2 3 4 5 6; do cat lat-$(date -u -d "<END> - $i day" +%F).txt 2>/dev/null; done | sort -n | awk "{a[NR]=\$1} END {if (NR < 5) print \"n/a n=\" NR; else {i=int(0.95*NR); if (i < 0.95*NR) i++; print \"p95=\" a[i] \" n=\" NR}}"'`.
4. Sum the week's `rate_limited_retry`, `scheduler skip lines` and `entry_skipped` counts from the 7 daily rows.
5. Append under `## Weekly` (create the section with this header if absent):
```
| week | UTC days | 429 retry 7d | entry_skipped by reason 7d | pooled 1m t0_t5 | sync_integrity p50 s | sync_repair p50 s | skipped_max_instances rows / scheduler skip lines | verdict |
|---|---|---|---|---|---|---|---|---|
```
6. Verdict PASS when: 429 retries ≤ 72; `sync_integrity` p50 < 10; `sync_repair` p50 < 120; `skipped_max_instances` rows equal the summed scheduler skip lines; pooled latency `n/a` or p95 ≤ 1000.
**Success criteria:** weekly rows at day 7 and day 14.
**Verify:** `grep -cE "^\| [0-9]+ \|.*\| FAIL \|$" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md` prints `0` (only weekly rows start with a plain number).

### Task 10.6 — [ASK] One same-tag re-roll (while fewer than 10 PASS handover rows)
**Goal:** add one handover deploy per run until 10 PASS rows exist, at least 5 of them re-rolls.
**Target files and symbols:** VPS `deploy/vps/10-deploy.sh`, `deploy/vps/11-verify.sh`; capture files; `handover-log.md`.
**Steps:**
1. Skip when: 10 PASS rows without `(off-session)` with ≥ 5 `re-roll` rows among them exist, or a row is pending, or the last deploy started less than 70 min ago, or the Context session check with `S=$(date -u +%FT%TZ)` prints `off-session` (D36: the row would not count).
<!-- Red team 2026-10-28: #7 #11 -->
2. Lock (no time check; plan.md Conventions): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'flock -n /opt/pocketquant/deploy.lock true && echo lock-free'`. No `lock-free` (a CI deploy is running) -> skip this task in this run.
3. Tag: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker inspect -f '{{.Config.Image}}' pocketquant-web | sed 's/.*://'"`; write it down as `<tag>`.
4. Ask (only an explicit yes counts): "Recommended: có — chạy 1 lần re-roll cùng tag (`IMAGE_TAG=<tag>`) ngay bây giờ để đo handover thứ <n>/10 (đã có <k> re-roll PASS, cần ≥ 5). Live đang tắt, chỉ paper; web không bị tạo lại nên probe phải 0 lỗi. Trả lời `có` hoặc `chưa`." A `chưa` skips to Task 10.7, which ends the run with the `NOT_YET` block.
<!-- Red team 2026-10-28: #11 #15 -->
5. Stamp `date -u +%Y%m%dT%H%M%SZ` -> `<T>`. Capture start (the `docker stats` sampler runs only from here to step 8, D34):
```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'T=<T>; V=/opt/pocketquant/logs/verify; mkdir -p "$V"; cd /opt/pocketquant/deploy; O=$(docker compose -f compose.prod.yml --env-file .env ps -q trader); [ "$(echo "$O" | grep -c .)" = 1 ] || { echo "capture_error trader_containers=$(echo "$O" | grep -c .)"; exit 1; }; echo "$O" | cut -c1-12 > "$V/old-trader-$T.txt"; date -u +%FT%TZ > "$V/start-$T.txt"; bash /opt/pocketquant/bin/snapshot.sh "before-$T" | tee "$V/snap-$T.txt"; bash /opt/pocketquant/bin/sample.sh start "$V/stats-$T.txt"; bash /opt/pocketquant/bin/probe.sh start "$V/probe-$T.txt"; echo capture_started'
```
6. Re-roll (use the harness background-run facility when it has one; up to about 12 min; the script takes the deploy lock itself): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant && IMAGE_TAG=<tag> bash deploy/vps/10-deploy.sh > /opt/pocketquant/logs/verify/deploy-<T>.txt 2>&1; echo "deploy_exit $?"; bash deploy/vps/11-verify.sh 2>&1 | grep "=== Verdict:" | grep -c ", 0 failures)"'`.
7. Append `| <n> | <content of start-<T>.txt> | re-roll | <T> | pending | | | | | | | | | <verdict count> | pending |`. Task 10.3 judges it in a run at least 65 min later.
<!-- Red team 2026-10-28: #2 #11 #15 -->
8. Capture stop, right after step 6 (also used by Task 10.1 step 3 and by Phase 09 D-6):
```bash
B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "bash -s $B" <<'EOF'
T=<T>; V=/opt/pocketquant/logs/verify
bash /opt/pocketquant/bin/sample.sh stop "$V/stats-$T.txt"
bash /opt/pocketquant/bin/probe.sh stop "$V/probe-$T.txt"
bash /opt/pocketquant/bin/snapshot.sh "after-$T" | tee -a "$V/snap-$T.txt"
bash /opt/pocketquant/bin/oom-check.sh "$1" "$2" | tee "$V/oom-$T.txt"
EOF
```
   `OOM_STOP` -> do the Task 10.7 OOM step now.
9. Any `master` push during this phase (a fix) runs only when no row is pending, after an [ASK] and the step 2 lock check, uses steps 5, 7 and 8 around it with kind `image`, and takes the CI verdict count from `gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"`.
**Success criteria:** the deploy exits 0; the verify verdict has 0 failures; a pending row exists; the capture is stopped.
**Verify:** the step 6 output is `deploy_exit 0` then `1`; the step 8 output ends with `OOM_OK`; `grep -c "| <T> | pending |" plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md` prints `1`.

### Task 10.7 — Exit check, owner summary, record
**Goal:** finish with the machine-limits summary, or end this run with `NOT_YET`.
**Target files and symbols:** the three reports; `.cache/ssh/vps_key`.
**Steps:**
<!-- Red team 2026-10-28: #2 -->
1. OOM step (D31, the only machine stop): if any check printed `OOM_STOP`, append the rows so far, commit and push them (steps 5-6), then ask: "Recommended: 1 — nâng cấp host (D5: 8 vCPU / 16 GB) vì máy 2 vCPU / 3 GB đã có OOM khi chạy thử. Số liệu: <dòng OOM_STOP>, <dòng D25 liên quan>. Lựa chọn (chỉ là thông tin, không phải cổng tự động): 1) nâng host; 2) giới hạn cache WiredTiger của MongoDB (`--wiredTigerCacheSizeGB 0.5`, một dòng compose); 3) đặt `mem_limit` cho từng container theo RSS đỉnh đã đo. Trả lời 1, 2, 3 hoặc `tiếp tục`." Record the answer in `machine-limits.md`, `rm -f .cache/ssh/vps_key`, and end with the `NOT_YET` block (`NOT_YET: OOM seen; owner chose <answer>`); the chosen lever is a new change outside this phase.
2. Done when all hold: ≥ 10 PASS handover rows after the last fix whose kind has no `(off-session)` (D36), ≥ 5 of them `re-roll`; 14 consecutive PASS daily rows; weekly rows 1 and 2 PASS; pooled 14-day latency has ≥ 5 samples (sum of `n` over the two weekly rows). If pooled samples are fewer than 5 at day 14, ask: "Recommended: tiếp tục — chạy thêm ngày cho tới khi có ≥ 5 mẫu `t0_t5_ms` 1m Exness (hiện có <n>). Trả lời `tiếp tục` hoặc `bỏ qua tiêu chí độ trễ`." and record the answer.
3. Not done: commit and push (steps 5-6), `rm -f .cache/ssh/vps_key`, end with the `NOT_YET` block (`NOT_YET: <k>/10 handover rows, <d>/14 days`, resume after the next UTC day 01:00Z, or 70 min from now when a re-roll is still owed).
<!-- Red team 2026-10-28: #4 #15 -->
4. Done: append to `machine-limits.md` a section `## Machine limits summary for the owner` with: `nproc` and total RAM (`free -m` total, one SSH call); per container the max peak RSS and CPU% over all handover rows (sampled only during rolls); host used max, available min and swap max over all snapshots (point samples before and after each roll and once per run day, not continuous peaks); PSI max; load1 max against `nproc`; loop lag max per role; warm-up s min/median/max; `takeover_ms` and `handover_gap_ms` max; the summed `strategy.signal_discarded` counts by reason; every OOM check `OOM_OK`; then one paragraph labelled "Inference" on where the machine runs short first (memory headroom at the overlap or CPU), and the three levers as information: a bigger host (D5), a WiredTiger cache cap (`--wiredTigerCacheSizeGB 0.5`; MongoDB's default is about half of RAM minus 1 GB, about 1 GB here [I]), measured `mem_limit` values. Append `Verification verdict: PASS <UTC>` as the last line of `paper-daily.md`. Record in the summary that trader lag ≥ 0.5 s days (the Stalls criterion) are reported, not judged, per D31.
5. `git add plans/261028-0652-exness-only-parallel-runtime/reports/handover-log.md plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md plans/261028-0652-exness-only-parallel-runtime/reports/machine-limits.md && git commit -m "docs(plans): record prod verification rows"`.
6. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; `rm -f .cache/ssh/vps_key`.
**Success criteria:** reports pushed; key removed; on completion the summary and the verdict line exist.
**Verify:** `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test -f .cache/ssh/vps_key; echo $?` prints `pushed` then `1`; on completion also `grep -c "^Verification verdict: PASS" plans/261028-0652-exness-only-parallel-runtime/reports/paper-daily.md; grep -c "^## Machine limits summary for the owner" plans/261028-0652-exness-only-parallel-runtime/reports/machine-limits.md` prints `1` then `1`.

## Rollback

<!-- Red team 2026-10-28: #11 #13 #15 -->
Observation only; nothing in the repo changes. A re-roll that fails mid-way is recovered by the roll script (it stops and removes the new copy on a health timeout) or by `cd /opt/pocketquant && IMAGE_TAG=<tag> bash deploy/vps/10-deploy.sh` again once the deploy lock is free (no time check; plan.md Conventions). A run interrupted between Task 10.6 steps 5 and 8 is closed by Task 10.1 step 3 (the capture-stop command for that `<T>`). To undo Task 10.2, stop the subscription with the same heredoc admin call and `/stop`. There is no long-running sampler to stop. Always `rm -f .cache/ssh/vps_key`.

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
