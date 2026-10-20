---
phase: 8
title: "Ship with live off: deploy A (B7, B12)"
status: pending
priority: P1
effort: 2.5h + CI
dependencies: [1, 2, 3, 4, 5, 6, 7]
---

# Phase 08: Ship with live off: deploy A (B7, B12)

## Context
- Outcome: prod runs Phases 01-07 with `ADMIN_TOKEN`, `EXNESS_DAILY_LOSS_CAP=25`, `EXNESS_MAX_LOTS=0.01`, `EXNESS_LEVERAGE=1000`, `EXNESS_RISK_PER_TRADE=0.10`; `EXNESS_LIVE_TRADING` stays absent; Mongo, Redis and Portainer answer only on 127.0.0.1 (local debugging goes through `just tunnel`, user decision 2026-10-20 21:32); Mongo runs a pinned 7.0 patch; `tunnel-test.pocketquant.xyz` serves through `cloudflared` while the old path keeps serving.
- Prod config is `../pocketquant-config/vps/default/.env`, written onto the VPS by each deploy (`docs/deployment.md:72-76`); remote `camping89/pocketquant-config`, branch `master`. A release is a fast-forward `develop:master` (`docs/deployment.md:10`); every `master` push deploys.
- Prod has `ENVIRONMENT=production` and none of the keys above (counted 2026-10-20, values not read). On 2026-10-20 `git -C ../pocketquant-config status` showed `M vps/default/.env` with an empty `git diff` [I: line endings or file mode].
- E2 (paper validation) keeps running; this deploy restarts every container: paper warmup resets (hitnrun2 about 8 open-market hours, engulfing about 21), in-memory paper positions are lost, and the next E2 row's C1 log window is shorter. E2 schedule (Bangkok = UTC+7): row 2 Sat 2026-10-24 03:00Z, row 3 Mon 2026-10-26 03:00Z, row 4 Mon 2026-11-02 03:00Z (`plans/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md:260-264`). Paper validation subscriptions: hitnrun2 XAUUSD 1m `01a15754-39ed-73e3-921e-df085eb4a786`, engulfing EURUSD 1h `01a15754-3ab5-7258-b46b-ad98e1f3471f`.
- The user's SPA check here is read-only: the token is first typed into the SPA after cutover (Phase 09, which also rotates it). Never stop or start a paper validation subscription (a stop loses strategy state).
- Pushing to a token URL does not move `origin/*`; every push below is followed by `git fetch origin`.

## Gates in this phase
[ASK] = stop and ask; state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [ASK] Task 8.3 config edit. [ASK] Task 8.4 `master` push. [USER] Task 8.8 `spa ok`.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 08 after <UTC time>
```
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing; after `git fetch origin`, `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo same` prints `same`.
- Each prints ≥ 1: `git show origin/develop:src/pocketquant/app/main_extensions.py | grep -c verify_admin_token`; `git show origin/develop:src/pocketquant/core/infra/exness/exness_client.py | grep -c access_point_reset`; `git show origin/develop:src/pocketquant/engine/market_data/app_services/integrity_jobs.py | grep -c unexpected_count`; `git show origin/develop:src/pocketquant/core/infra/persistence/repositories/safeguards_repository.py | grep -c save_entries_paused`; `git show origin/develop:web/src/components/strategies/strategies-page-layout.tsx | grep -c ExnessStrip`; `git show origin/develop:deploy/compose.prod.yml | grep -c "127.0.0.1:"`; `git show origin/develop:web/nginx.conf | grep -c "limit_conn sse"`; `git show origin/develop:justfile | grep -c "^tunnel:"`.
- `grep -c "^TUNNEL_TOKEN=." ../pocketquant-config/vps/default/.env` prints `1`.
- `docker ps` exits 0.

## Tasks
Code blocks below are indented for Markdown. Before running one, remove only the common leading indentation of the block (keep the Python indentation inside it), so each closing `EOF` starts at column 0. The shell keeps no variables between commands: every command sets `HOST` (and `RUN_ID`) itself. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Never print a token.

### Task 8.1 — SSH setup
- Goal: a working key copy and host.
- Target files and symbols: `.cache/ssh/vps_key` (gitignored; deleted in Task 8.10).
- Steps: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
- Success criteria: ssh works.
- Verify: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps --format '{{.Names}}' | grep -c pocketquant-app"` prints `1`.

### Task 8.2 — Release gate on `develop`
- Goal: the commit to release is green locally.
- Target files and symbols: whole repo at `origin/develop`.
- Steps: `just test 2>&1 | tail -n 15`; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet`; `npm --prefix web test`; `npm --prefix web run build`.
- Success criteria: only the expected Windows red.
- Verify: pytest shows exactly `4 failed` and `4 errors`, all in `test_utc_runtime_guard.py` or `test_cron_trigger_timezone.py`; lint-imports `Contracts: 8 kept, 0 broken.`; the ratchet, web test and web build exit 0.

### Task 8.3 — [ASK] Prod config: token, caps and sizing keys; local remote-DB URLs through the tunnel
- Goal: the five keys are in `pocketquant-config`, pushed; the flag stays absent; the local remote-DB env files point at `just tunnel` (Mongo `localhost:27017`, Redis `localhost:6379`), because deploy A binds the data ports to 127.0.0.1.
- Target files and symbols: `../pocketquant-config/vps/default/.env`; `../pocketquant-config/local/remote-db.env` (`MONGODB_URL`, `REDIS_URL`); `../pocketquant-config/local/remote-db-local-redis.env` (`MONGODB_URL`; its `REDIS_URL` is already local). Both have CRLF in the working tree and LF in the index (`git ls-files --eol`, `core.autocrlf=true`). Git Bash `sed -i` rewrites them with LF (checked 2026-10-20 on a scratch file), so the commit still shows only the URL lines.
- Steps:
  1. Facts for the question: the keys to add (`ADMIN_TOKEN` generated, `EXNESS_DAILY_LOSS_CAP=25`, `EXNESS_MAX_LOTS=0.01`, `EXNESS_LEVERAGE=1000`, `EXNESS_RISK_PER_TRADE=0.10`); `grep -c "^EXNESS_LIVE_TRADING=" ...` (must be `0`); `grep -c "^TUNNEL_TOKEN=." ...` (`1`); the three local URL changes (VPS IP → `localhost:27017` / `localhost:6379`; `just tunnel` already works before deploy A, because a port published on all interfaces also answers on the VPS loopback); the output of `git -C ../pocketquant-config status --short`. Ask: "Add these keys to pocketquant-config, point the local remote-DB URLs at just tunnel, and push it?"
  2. On yes: `F=../pocketquant-config/vps/default/.env; [ -n "$(tail -c1 $F)" ] && echo >> $F; printf 'ADMIN_TOKEN=%s\n' "$(uv run python -c 'import secrets;print(secrets.token_urlsafe(32))')" >> $F; printf 'EXNESS_DAILY_LOSS_CAP=25\nEXNESS_MAX_LOTS=0.01\nEXNESS_LEVERAGE=1000\nEXNESS_RISK_PER_TRADE=0.10\n' >> $F`. Never print the token.
  3. `C=../pocketquant-config; IP=$(head -1 $C/vps/default/host | tr -d '\r' | sed 's/.*@//'); MP=$(grep '^MONGO_PORT=' $C/vps/default/.env | cut -d= -f2 | tr -d '\r '); RP=$(grep '^REDIS_PORT=' $C/vps/default/.env | cut -d= -f2 | tr -d '\r '); sed -i "s|@$IP:$MP/|@localhost:27017/|; s|@$IP:$RP/|@localhost:6379/|" $C/local/remote-db.env $C/local/remote-db-local-redis.env`. Never print the URLs (they carry passwords).
  4. `git -C ../pocketquant-config add vps/default/.env local/remote-db.env local/remote-db-local-redis.env && git -C ../pocketquant-config commit -m "feat(env): add admin token, exness safeguard keys and tunnel urls" && git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`.
- Success criteria: each key appears once; the local URLs use localhost; only the URL lines changed; the push succeeds.
- Verify: `for k in ADMIN_TOKEN EXNESS_DAILY_LOSS_CAP EXNESS_MAX_LOTS EXNESS_LEVERAGE EXNESS_RISK_PER_TRADE; do grep -c "^$k=." ../pocketquant-config/vps/default/.env; done` prints `1` five times; `grep -c "^EXNESS_LIVE_TRADING=" ../pocketquant-config/vps/default/.env` prints `0`; `grep -c "^MONGODB_URL=.*@localhost:27017/" ../pocketquant-config/local/remote-db.env ../pocketquant-config/local/remote-db-local-redis.env` prints `1` for each file; `grep -c "^REDIS_URL=.*@localhost:6379/" ../pocketquant-config/local/remote-db.env` prints `1`; `git -C ../pocketquant-config show --numstat --format= HEAD -- local` prints `2	2	local/remote-db.env` and `1	1	local/remote-db-local-redis.env` (no line-ending churn); `test "$(git -C ../pocketquant-config rev-parse HEAD)" = "$(git -C ../pocketquant-config ls-remote "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" master | cut -f1)" && echo pushed` prints `pushed`.

### Task 8.4 — [ASK] Push `master` (deploy A)
- Goal: prod runs the new code.
- Target files and symbols: `master` on `camping89/pocketquant`.
- Steps:
  1. Facts for the question: `git fetch origin && git log --oneline origin/master..origin/develop | wc -l` commits; open paper positions per validation subscription (`HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app curl -s http://localhost:41921/api/v1/subscriptions/<id>/positions"` for both ids; count the items); the next E2 row time from Context; warmup cost (about 8 h hitnrun2, 21 h engulfing); "every container restarts once (new networks; Mongo moves to a pinned 7.0 patch); data ports become loopback only (local debugging through `just tunnel`); live trading stays off". Ask: "Push develop to master now (deploys prod)?"
  2. On yes: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`. Record the push UTC time.
- Success criteria: the run succeeds.
- Verify (one command): `sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 5 --json databaseId,headSha -q "[.[] | select(.headSha==\"$(git rev-parse develop)\")][0].databaseId"); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null && GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.

### Task 8.5 — Prod settings and auth checks
- Goal: the values are live and the guard holds.
- Target files and symbols: prod app container.
- Steps: run this one command (the token stays inside the container):
  ```bash
  HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
  python -c "from pocketquant.core.config import get_settings as g;s=g();print(s.exness_live_trading, s.exness_daily_loss_cap, s.exness_max_lots, s.exness_leverage, s.exness_risk_per_trade, s.admin_token is not None)"
  curl -s http://localhost:41921/api/v1/admin/safeguards; echo
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:41921/api/v1/subscriptions/x/stop
  python -c "import json,urllib.request as u;d=json.load(u.urlopen('http://localhost:41921/api/v1/subscriptions/'));print(len(d), sum(s['broker']=='paper' for s in d))"
  curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","days_back":1}' http://localhost:41921/api/v1/market-data/integrity/check; echo
  EOF
  ```
- Success criteria: all five output lines match.
- Verify: line 1 is `False 25.0 0.01 1000.0 0.1 True`; line 2 contains `"live_trading":false`, `"daily_loss_cap":25.0`, `"max_lots":0.01`, `"leverage":1000.0`, `"risk_per_trade":0.1` and `"entries_paused":false`; line 3 is `401`; line 4 is two equal numbers; line 5 contains `"unexpected_count"`.

### Task 8.6 — Tunnel round 2 checks
- Goal: `cloudflared` is up and `tunnel-test` serves; the old path still serves.
- Target files and symbols: prod `pocketquant-cloudflared`; workstation curl.
- Steps:
  1. `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps --format '{{.Names}} {{.Status}}' | grep pocketquant-cloudflared; docker logs pocketquant-cloudflared 2>&1 | grep -c 'Registered tunnel connection'"`.
  2. From the workstation: `for u in https://tunnel-test.pocketquant.xyz/ https://tunnel-test.pocketquant.xyz/strategies https://tunnel-test.pocketquant.xyz/api/v1/admin/safeguards https://pocketquant.xyz/; do curl -s -o /dev/null -w "%{http_code}\n" "$u"; done`.
- Success criteria: four 200s.
- Verify: (1) the status contains `(healthy)` and the count is ≥ 1; (2) prints `200` four times.

### Task 8.7 — Data ports closed from outside; `just tunnel` works
- Goal: Mongo, Redis and Portainer are not reachable by the VPS IP; Mongo runs the pinned patch (AC10, first part); local debugging works through `just tunnel` with the edited `remote-db.env`.
- Target files and symbols: workstation curl; prod `pocketquant-mongodb`; `justfile` recipe `tunnel`; `../pocketquant-config/local/remote-db.env`.
- Steps:
  1. `IP=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r' | sed 's/.*@//'); for k in MONGO_PORT REDIS_PORT PORTAINER_PORT; do P=$(grep "^$k=" ../pocketquant-config/vps/default/.env | cut -d= -f2 | tr -d '\r '); curl -s --max-time 5 -o /dev/null "http://$IP:$P/"; echo "$k exit=$?"; done`.
  2. `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps --format '{{.Names}} {{.Ports}}' | grep -E 'mongodb|redis|portainer'; docker exec pocketquant-mongodb mongod --version | head -1"`.
  3. Start `just tunnel` with the harness's background-run facility and record its PID. After 10 s run the probe below (it reads the URLs without printing them). Then stop the background process, and run `rm -f .cache/ssh/tunnel_key` in case its exit trap did not run.
     ```bash
     M=$(grep '^MONGODB_URL=' ../pocketquant-config/local/remote-db.env | cut -d= -f2- | tr -d '\r') R=$(grep '^REDIS_URL=' ../pocketquant-config/local/remote-db.env | cut -d= -f2- | tr -d '\r') uv run python -c "import os,redis;from pymongo import MongoClient;print('mongo', MongoClient(os.environ['M'],serverSelectionTimeoutMS=5000).admin.command('ping')['ok']);print('redis', redis.from_url(os.environ['R']).ping())"
     ```
- Success criteria: three closed ports; Mongo 7.0.N with N ≥ 28; Mongo and Redis answer through the tunnel.
- Verify: step 1 prints three lines, each ending `exit=7` or `exit=28`; step 2 shows `127.0.0.1:` on all three port lines and `db version v7.0.N` with N ≥ 28; step 3 prints `mongo 1.0` and `redis True`; afterwards `test -f .cache/ssh/tunnel_key; echo $?` prints `1` and `netstat -ano | grep -c ":27017 .*LISTENING"` prints `0` (no orphaned tunnel; if it prints more, stop the PID netstat shows, since it is the tunnel this task started).

### Task 8.8 — [USER] Read-only SPA check
- Goal: the user sees the new UI in prod without typing the token.
- Target files and symbols: none.
- Steps: ask exactly: "Open https://pocketquant.xyz/strategies. Do not press Pause, Start, Stop or Delete, and do not type the admin token. Check: every row shows PAPER and one state pill; the Exness strip shows live_trading OFF, daily loss cap 25 USD, max lots 0.01, and a Pause button. Reply `spa ok` or name what differs."
- Success criteria: the reply.
- Verify: the reply equals `spa ok`.

### Task 8.9 — Dispatch auth probe and ship-log row
- Goal: Phase 10 knows whether the agent can dispatch; the E2 runner has the restart time.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/ship-log.md` (create if absent).
- Steps:
  1. `GH_TOKEN=$(gh auth token --user camping89) gh api repos/camping89/pocketquant/actions/workflows --jq '.workflows[].name'` (read-only).
  2. `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker inspect -f '{{.State.StartedAt}}' pocketquant-app"`.
  3. Append to `plans/261019-1957-exness-go-live/reports/ship-log.md`: `Deploy A: <push UTC>, app StartedAt <value>, dispatch auth <ok|failed>, data ports loopback, just tunnel ok, live trading off`.
- Success criteria: one row.
- Verify: `grep -c "^Deploy A:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1`. A failed probe is recorded, not a failure (Phase 10 then asks the user to dispatch).

### Task 8.10 — Commit the report, remove the key
- Goal: the evidence is on `develop`; no key copy stays on disk.
- Target files and symbols: `plans/261019-1957-exness-go-live/reports/ship-log.md`; `.cache/ssh/vps_key`.
- Steps: commit the report (`docs(plans): record the live-off ship`); `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; `rm -f .cache/ssh/vps_key`.
- Success criteria: pushed; key removed.
- Verify: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`; `test -f .cache/ssh/vps_key; echo $?` prints `1`.

## Exit rule
Before any `NOT_YET` exit or a stop after Task 8.1, run `rm -f .cache/ssh/vps_key`.

## Risk
- Deploying before Task 8.3 makes mutations return 503 (L/L): 8.3 comes first.
- The tunnel fails to connect (L/M): only `tunnel-test` is affected; fix before Phase 09.
- The deploy resets paper warmup and drops paper positions (L/L): recorded; E2 is optional for live.
- Mongo is recreated on the pinned image (M/L): same volume and 7.0 line; the verdict's Mongo ping and the app health check cover it.
- Local tools that reached the data ports by IP stop working (H/L): `just tunnel` (Phase 07) and the localhost URLs from Task 8.3; Task 8.7 proves both.

## Rollback
- Code: `git revert <sha>` on `develop`, then push `master` [ASK].
- Config: remove the keys and redeploy [ASK]. Removing `ADMIN_TOKEN` while Phase 01 code runs makes mutations return 503; revert the code first or keep the key. The local remote-DB URLs keep working through `just tunnel` either way; revert them only together with the Phase 07 port change.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
