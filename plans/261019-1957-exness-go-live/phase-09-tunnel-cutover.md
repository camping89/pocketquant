---
phase: 9
title: "Tunnel cutover: deploy B (B10, B13)"
status: pending
priority: P1
effort: 1.5h + CI + ~20 min user
dependencies: [8]
---

# Phase 09: Tunnel cutover: deploy B (B10, B13)

## Context
- Round 3 of the tunnel rollout. Phase 08 proved `https://tunnel-test.pocketquant.xyz` through `cloudflared`. The old path is a proxied `A @ → <vps-ip>` and `CNAME www → pocketquant.xyz` (`docs/deployment.md`, the "Traffic enters via" line) to `web` on the host port (`deploy/compose.prod.yml:8-9`).
- Verified (research report): the dashboard rejects a route whose hostname already has an A/AAAA/CNAME record, so the user deletes the record first, then adds the route; the name is unreachable for the seconds between. A CNAME at the apex works (flattening). Removing a route does not delete its CNAME. Docker-published ports bypass ufw, so once `ports:` is gone a connect is refused (curl exit 7) or dropped (exit 28).
- Once the host port is gone, two `deploy/vps/11-verify.sh` checks would fail: the SPA probe on the host port (`:118-127`) and the port-listening section (`:171-185`). `WEB_PORT` is read only by `compose.prod.yml:9` and `11-verify.sh:119,177`, and documented in `docs/deployment.md` (env row and port map). The only `source .env` before the Redis check (`:140`, `redis-cli -a "${REDIS_PASSWORD:-}"`) is at `:118`; the other (`:176`) is inside section 8. The script runs in a fresh ssh shell (`.github/workflows/cicd.yml:245`).
- The app image has `curl`; `11-verify.sh` already runs it inside `pocketquant-app` (`:92,109`). `app` and `web` share the `backend` network (Phase 07).
- Ingress routes live in the Cloudflare dashboard, so anyone with the account can add one; Task 9.2 confirms exactly two routes.
- The token may have crossed plain HTTP if someone typed it between deploys A and B. Deploy B rotates it (user decision 2026-10-20 20:20), so any earlier copy is void; the SPA prompts again on the first 401.
- After cutover the tunnel is the only public path to Pause; Pause over SSH reads `$ADMIN_TOKEN` inside the container (`app` has `env_file: .env`, `compose.prod.yml:43-44`). The rate limiter exempts `/api/v1/admin/safeguards*` and keys on the real client IP (Phase 07).
- No `exness` subscription exists yet, so no live position is exposed during the cutover.

## Gates in this phase
[ASK] = stop and ask; state the listed facts; only an explicit yes counts; "no" or "wait" ends the phase with the NOT_YET block. [USER] = the user acts and replies with the stated token. No earlier approval counts.
- [USER] Task 9.2 `DNS cut over, 2 routes`. [USER] Task 9.3 `2fa on, rate rule on`. [ASK] Task 9.8 config. [ASK] Task 9.9 `master` push. [USER] Task 9.13 `pause ok`.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pq-develop/plans/261019-1957-exness-go-live --from 09 after <UTC time>
```
- `grep -c "^Deploy A:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1`.
- `curl -s -o /dev/null -w "%{http_code}" https://tunnel-test.pocketquant.xyz/` prints `200`.
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing; after `git fetch origin`, `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo same` prints `same`.
- `docker ps` exits 0.

## Tasks
Code blocks below are indented for Markdown. Before running one, remove only the common leading indentation of the block (keep the Python indentation inside it), so each closing `EOF` starts at column 0. The shell keeps no variables between commands: every command sets `HOST` (and `RUN_ID`) itself. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Never print a token.

### Task 9.1 — SSH setup and tunnel health
- Goal: ssh works and `cloudflared` is healthy before DNS changes.
- Target files and symbols: `.cache/ssh/vps_key` (deleted in Task 9.14).
- Steps: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`; then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker ps --format '{{.Names}} {{.Status}}' | grep pocketquant-cloudflared"`.
- Success criteria: healthy.
- Verify: the output contains `(healthy)`.

### Task 9.2 — [USER] Move `www` and `@` to the tunnel
- Goal: both names are tunnel routes; `tunnel-test` is gone; the tunnel has exactly two routes.
- Target files and symbols: Cloudflare DNS and Networking > Tunnels > `pocketquant-prod` > Routes.
- Steps: ask exactly: "Cutover, one name at a time (each is down for the seconds between delete and save): (1) DNS > Records: delete `CNAME www`; then Networking > Tunnels > pocketquant-prod > Routes > Add route > Published application: subdomain `www`, domain `pocketquant.xyz`, service URL `http://web:80`, Save. (2) DNS > Records: delete `A @`; then Add route > Published application with the subdomain empty, domain `pocketquant.xyz`, `http://web:80`, Save. (3) Delete the `tunnel-test` route, then delete its `tunnel-test` CNAME in DNS > Records (removing a route leaves it). (4) Check the Routes list: exactly two routes, `pocketquant.xyz` and `www.pocketquant.xyz`, both `http://web:80`; delete any other. Rollback for any step: delete the new route and re-add the old proxied record. Reply `DNS cut over, 2 routes`."
- Success criteria: the reply.
- Verify: the reply equals `DNS cut over, 2 routes`.

### Task 9.3 — [USER] Cloudflare account 2FA and one rate-limit rule
- Goal: a stolen Cloudflare password cannot add a route, and one client IP cannot flood `/api/` through Cloudflare; Pause stays exempt.
- Target files and symbols: Cloudflare dashboard (account profile; zone `pocketquant.xyz` security rules).
- Facts (Cloudflare docs, read 2026-10-20): the Free plan has one rate-limiting rule, counts by IP only, with a fixed 10 s period and a fixed 10 s mitigation timeout; the rule fields are Path and Verified Bot; the `matches` regex operator needs Business, and no plan limit is documented for `wildcard` [I: available on Free].
- Steps: ask exactly: "Two Cloudflare steps. (1) My Profile > Authentication > Two-Factor Authentication: turn it on (authenticator app or security key) and store the backup codes offline. (2) Zone pocketquant.xyz > Security rules > Create rule > Rate limiting rules: name `api-flood`; Edit expression: `(http.request.uri.path wildcard "/api/*" and not http.request.uri.path wildcard "/api/v1/admin/safeguards*")`; characteristic IP; 200 requests per 10 seconds; action Block; duration 10 seconds; Deploy. If the dashboard rejects the expression, reply with its error instead. Reply `2fa on, rate rule on`."
- Success criteria: the reply. Task 9.12 then proves Pause still answers right after a burst with the rule live.
- Verify: the reply equals `2fa on, rate rule on`.

### Task 9.4 — Check with the old port still open
- Goal: both names serve through the tunnel before the port is removed.
- Target files and symbols: workstation curl; `pocketquant-cloudflared` logs.
- Steps: `for u in https://pocketquant.xyz/ https://www.pocketquant.xyz/ https://pocketquant.xyz/strategies https://pocketquant.xyz/api/v1/admin/safeguards; do curl -s -o /dev/null -w "%{http_code}\n" "$u"; done`; then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker logs --since 10m pocketquant-cloudflared 2>&1 | grep -c ' ERR '"`.
- Success criteria: four 200s, no tunnel errors. On any miss, the user restores the old record (Task 9.2 rollback) and the phase stops (Failure Protocol).
- Verify: the loop prints `200` four times; the grep prints `0`.

### Task 9.5 — Drop the `web` host port
- Goal: no public origin port.
- Target files and symbols: `deploy/compose.prod.yml` (`web` → `ports:`, `:8-9`).
- Steps: delete the two `ports:` lines; add one comment line: "No host port: Cloudflare Tunnel (cloudflared) is the only public entry."
- Success criteria: `web` publishes nothing.
- Verify: `docker compose -f deploy/compose.prod.yml config --quiet` exits 0 and `grep -c "WEB_PORT" deploy/compose.prod.yml` prints `0`.

### Task 9.6 — Verify script probes inside the network
- Goal: the verdict stays meaningful without a host port, and the Redis password leaves the process arguments.
- Target files and symbols: `deploy/vps/11-verify.sh`: the `cd` line (`:12`), section "3b. Web container: SPA routes" (`:116-127`), section "5. Redis direct check" (`:140`), section "8. Port listening" (`:171-185`).
- Steps:
  1. Move `source .env 2>/dev/null || true` from `:118` to the line after the `cd` (`:12`); keep it. Section 5 reads `REDIS_PASSWORD` from it.
  2. In 3b, delete only the `WEB_PORT_VAL` line; the probe becomes `http=$(docker exec pocketquant-app curl -s -o /dev/null -w "%{http_code}" "http://web:80${path}" || echo "000")`.
  3. Section 5 becomes `redis_ok=$(REDISCLI_AUTH="${REDIS_PASSWORD:-}" docker exec -e REDISCLI_AUTH pocketquant-redis redis-cli PING 2>/dev/null || echo "")` (the password travels in the environment, not in `ps`).
  4. Delete section 8 entirely (with its own `source` line).
- Success criteria: one `source .env` near the top; no `WEB_PORT`; no `-a` on `redis-cli`.
- Verify: `bash -n deploy/vps/11-verify.sh` exits 0; `grep -n "^source .env" deploy/vps/11-verify.sh` prints exactly one line with a number below 20; `grep -c "WEB_PORT" deploy/vps/11-verify.sh` prints `0`; `grep -c "redis-cli -a" deploy/vps/11-verify.sh` prints `0`; `grep -c "REDISCLI_AUTH" deploy/vps/11-verify.sh` prints `1`.

### Task 9.7 — Docs: traffic path, break-glass, restart while live
- Goal: the doc matches the new traffic path and says how to pause and how to restart while live.
- Target files and symbols: `docs/deployment.md`: the container list line ("containers: app"), the "Traffic enters via" line, the `WEB_PORT` env row, the "Port map:" line, and two new sections after the "**Operator Runbook — break-glass.**" line, before `## Rollback`.
- Steps:
  1. Container list: "web (nginx reverse proxy)" → "web (nginx reverse proxy, internal)".
  2. Traffic line → "Traffic enters via Cloudflare → Cloudflare Tunnel (`cloudflared`, outbound only) → `web` (nginx :80, no host port) → app (internal :41921). Cloudflare terminates browser TLS. DNS: the tunnel's routes `pocketquant.xyz` and `www`; no A record points at the VPS. The SPA is domain-agnostic (calls `window.location.origin + /api/...`), so no rebuild on domain change. SSH (22) is the only public port on the VPS; Mongo, Redis and Portainer bind 127.0.0.1 (use `just tunnel`)."
  3. Delete the `WEB_PORT` row. In the port map write "web `80` (internal, no host port)".
  4. New section:
     ````markdown
     ## Stop real-money entries when the site is down
     The tunnel is the only public path to the SPA. Pause entries over SSH; the token stays inside the container:

     ```bash
     ssh -i <key> <host> 'docker exec -i pocketquant-app sh -s' <<'EOF'
     curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/pause
     EOF
     ```

     Then close any open position in the Exness app. The pause is stored and survives a restart.
     ````
  5. New section:
     ```markdown
     ## Restart while live
     Use this for every planned restart (deploy, rollback, config dispatch) while an `exness` subscription exists. The pause survives a restart; strategy state (warmup, open direction) does not.
     1. Pause entries (Exness strip, or the SSH command above).
     2. Stop each `exness` subscription: `POST /api/v1/subscriptions/{id}/stop` with the token.
     3. Confirm the account is flat (`GET /api/v1/subscriptions/{id}/positions` is empty for each), or accept that the venue SL/TP protects the open position.
     4. Deploy.
     5. After the health check, `GET /api/v1/admin/safeguards` shows `"entries_paused":true`.
     6. Start each `exness` subscription again.
     7. Resume entries only with a fresh approval.
     ```
- Success criteria: four edits and two sections.
- Verify: `grep -rn "WEB_PORT" deploy docs/deployment.md` prints nothing; `grep -c "Stop real-money entries when the site is down" docs/deployment.md` prints `1`; `grep -c "^## Restart while live" docs/deployment.md` prints `1`; `wc -l < docs/deployment.md` prints a number < 800.

### Task 9.8 — [ASK] Push develop; drop `WEB_PORT` and rotate `ADMIN_TOKEN`
- Goal: the code is on `develop` with green CI; prod config has no dead key and a fresh token.
- Target files and symbols: `develop`; `../pocketquant-config/vps/default/.env` keys `WEB_PORT`, `ADMIN_TOKEN`.
- Steps:
  1. Commit Tasks 9.5-9.7 on `develop` (`feat(deploy): serve the site only through the cloudflare tunnel`); `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`.
  2. Wait for the `develop` CI run: `sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 5 --json databaseId,headSha -q "[.[] | select(.headSha==\"$(git rev-parse HEAD)\")][0].databaseId"); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null; echo "ci exit=$?"`.
  3. Ask: "Remove WEB_PORT from pocketquant-config and rotate ADMIN_TOKEN in the same commit, then push it? (WEB_PORT is unused after this deploy; the new token voids any copy typed before the cutover. You will paste the new token in Task 9.13.)"
  4. On yes: `F=../pocketquant-config/vps/default/.env; sed -i '/^WEB_PORT=/d' "$F"; sed -i "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=$(uv run python -c 'import secrets;print(secrets.token_urlsafe(32))')|" "$F"`; then `git -C ../pocketquant-config add vps/default/.env && git -C ../pocketquant-config commit -m "chore(env): drop the web port and rotate the admin token" && git -C ../pocketquant-config push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`. Never print the token.
- Success criteria: CI green; the key is gone; the token changed; pushed.
- Verify: step 2 prints `ci exit=0`; `grep -c "^WEB_PORT=" ../pocketquant-config/vps/default/.env` prints `0`; `git -C ../pocketquant-config show HEAD -- vps/default/.env | grep -c "^[-+]ADMIN_TOKEN="` prints `2`; `test "$(git -C ../pocketquant-config rev-parse HEAD)" = "$(git -C ../pocketquant-config ls-remote "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" master | cut -f1)" && echo pushed` prints `pushed`.

### Task 9.9 — [ASK] Push `master` (deploy B)
- Goal: prod drops the host port and runs with the new token.
- Target files and symbols: `master`.
- Steps:
  1. Facts: `git fetch origin && git log --oneline origin/master..origin/develop | wc -l` commits; the deploy A time from `plans/261019-1957-exness-go-live/reports/ship-log.md`; "this restart again resets paper warmup; live trading stays off; the admin token changes". Ask: "Push develop to master now?"
  2. On yes: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`.
- Success criteria: the run succeeds.
- Verify (one command): `sleep 15; RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 5 --json databaseId,headSha -q "[.[] | select(.headSha==\"$(git rev-parse develop)\")][0].databaseId"); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --exit-status > /dev/null && GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints ≥ 1.

### Task 9.10 — Origin closed, site up, SSE (AC10)
- Goal: no origin port answers by IP; the site serves through the tunnel; one SSE check.
- Target files and symbols: workstation curl; `plans/261019-1957-exness-go-live/reports/ship-log.md`.
- Steps:
  1. `IP=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r' | sed 's/.*@//'); curl -s --max-time 5 -o /dev/null "http://$IP:80/"; echo "WEB exit=$?"; for k in MONGO_PORT REDIS_PORT PORTAINER_PORT; do P=$(grep "^$k=" ../pocketquant-config/vps/default/.env | cut -d= -f2 | tr -d '\r '); curl -s --max-time 5 -o /dev/null "http://$IP:$P/"; echo "$k exit=$?"; done`.
  2. `for u in https://pocketquant.xyz/ https://pocketquant.xyz/api/v1/subscriptions/; do curl -s -o /dev/null -w "%{http_code}\n" "$u"; done`.
  3. SSE. Market probe (age in minutes of the newest XAUUSD 1m bar):
     ```bash
     HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
     ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     from datetime import UTC, datetime
     from pymongo import MongoClient
     from pocketquant.core.config import get_settings
     s = get_settings()
     b = MongoClient(str(s.mongodb_url))[s.mongodb_database].bars.find_one({"symbol": "XAUUSD:EXNESS", "interval": "1m"}, sort=[("datetime", -1)])
     print(int((datetime.now(UTC) - b["datetime"].replace(tzinfo=UTC)).total_seconds() // 60))
     EOF
     ```
     Age ≤ 5: `curl -s -N --max-time 150 "https://pocketquant.xyz/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m" | grep -c "^data:"` and append `SSE pocketquant.xyz: <count> data lines at <UTC>` to the ship log. Age > 5: append `SSE deferred: XAUUSD closed at <UTC>` (record only; no later phase repeats it).
- Success criteria: four closed ports, two 200s, one SSE line.
- Verify: step 1 prints four lines, each ending `exit=7` or `exit=28`; step 2 prints `200` twice; step 3: open case count ≥ 1, closed case `grep -c "^SSE deferred" plans/261019-1957-exness-go-live/reports/ship-log.md` prints ≥ 1.

### Task 9.11 — Break-glass drill over SSH
- Goal: Pause works without the tunnel, Cloudflare or the SPA.
- Target files and symbols: prod safeguards routes; the ship log.
- Steps:
  ```bash
  HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
  curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/pause; echo
  curl -s http://localhost:41921/api/v1/admin/safeguards; echo
  curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://localhost:41921/api/v1/admin/safeguards/resume; echo
  curl -s http://localhost:41921/api/v1/admin/safeguards; echo
  EOF
  ```
  Append `Break-glass drill: pause over SSH ok at <UTC>` to `plans/261019-1957-exness-go-live/reports/ship-log.md`.
- Success criteria: pause then resume took effect.
- Verify: line 2 contains `"entries_paused":true`; line 4 contains `"entries_paused":false`.

### Task 9.12 — Pause holds under a request flood
- Goal: a burst of public GETs does not block Pause over the tunnel, with the app limiter and the Cloudflare rule (Task 9.3) both live.
- Target files and symbols: workstation curl; prod limiter; the Cloudflare `api-flood` rule. Some burst lines are expected to be `429` (from the app or from Cloudflare); only Pause, the safeguards GET and Resume must answer.
- Steps (the token goes from the config file into curl's stdin config, never into arguments or output):
  ```bash
  seq 300 | xargs -P 50 -I{} curl -s -o /dev/null -w "%{http_code}\n" https://pocketquant.xyz/api/v1/subscriptions/ | sort | uniq -c
  grep '^ADMIN_TOKEN=' ../pocketquant-config/vps/default/.env | cut -d= -f2- | tr -d '\r' | sed 's/^/header = "X-Admin-Token: /; s/$/"/' | curl -s -K - -o /dev/null -w "pause %{http_code}\n" -X POST https://pocketquant.xyz/api/v1/admin/safeguards/pause
  curl -s https://pocketquant.xyz/api/v1/admin/safeguards; echo
  grep '^ADMIN_TOKEN=' ../pocketquant-config/vps/default/.env | cut -d= -f2- | tr -d '\r' | sed 's/^/header = "X-Admin-Token: /; s/$/"/' | curl -s -K - -o /dev/null -w "resume %{http_code}\n" -X POST https://pocketquant.xyz/api/v1/admin/safeguards/resume
  ```
  Append `Flood check: <uniq -c line(s)>, pause 200 at <UTC>` to the ship log.
- Success criteria: Pause and Resume answer 200 right after the burst.
- Verify: the output shows `pause 200`, a safeguards line containing `"entries_paused":true`, and `resume 200`.

### Task 9.13 — [USER] First token entry, over the tunnel
- Goal: the SPA's token prompt and Pause/Resume work in prod with the rotated token.
- Target files and symbols: none.
- Steps: ask exactly: "Open https://pocketquant.xyz/strategies. Press Pause in the Exness strip; when asked, paste ADMIN_TOKEN from pocketquant-config/vps/default/.env (it was rotated in this phase; never paste it in chat). Check that Entries paused appears; then press Resume, confirm Resume entries, and check that Pause is back. Reply `pause ok` or describe what differs."
- Success criteria: the reply, and prod unpaused.
- Verify: the reply equals `pause ok`, and `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker exec pocketquant-app curl -s http://localhost:41921/api/v1/admin/safeguards"` contains `"entries_paused":false`.

### Task 9.14 — Record, push, remove the key
- Goal: evidence on `develop`; no key copy on disk.
- Target files and symbols: the ship log; `.cache/ssh/vps_key`.
- Steps: append `Deploy B: <UTC>, app StartedAt <docker inspect -f '{{.State.StartedAt}}' pocketquant-app>, admin token rotated`; commit `docs(plans): record the tunnel cutover`; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; `rm -f .cache/ssh/vps_key`.
- Success criteria: pushed; key removed.
- Verify: `grep -c "^Deploy B:" plans/261019-1957-exness-go-live/reports/ship-log.md` prints `1`; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`; `test -f .cache/ssh/vps_key; echo $?` prints `1`.

## Exit rule
Before any `NOT_YET` exit or a stop after Task 9.1, run `rm -f .cache/ssh/vps_key`.

## Risk
- A name is down for seconds between delete and save (M/L): one name at a time; no live position exists.
- The site depends on `cloudflared` (M/M): `restart: unless-stopped`, the healthcheck and the verdict cover it; Pause over SSH (Task 9.11) works without it.
- A stray dashboard route exposes a backend (L/H): Task 9.2 confirms two routes; `cloudflared` sits only on `edge` with `web` (Phase 07), so it cannot reach `app`, Mongo or Redis directly.
- The flood check pauses prod briefly (L/L): no `exness` subscription exists; it resumes at once.
- The Cloudflare rule blocks a normal SPA user (L/L): 200 requests per 10 s per IP is far above one user's load, Pause is exempt, and a block lasts 10 s; delete the rule in the dashboard if it misfires.
- A lost 2FA device locks the user out of Cloudflare (L/H): the backup codes stored offline in Task 9.3; Pause over SSH needs no Cloudflare login.

## Rollback
Restore the port first, then DNS (an A record to an origin with no open port returns 52x). After Phase 10, deploy only through the "Restart while live" runbook (`docs/deployment.md`).
1. Agent: revert this phase's commit, re-add `WEB_PORT` and rotate `ADMIN_TOKEN` again in one `pocketquant-config` commit [ASK] (the token then crosses plain HTTP again on the old path), push `master` [ASK]. The tunnel keeps serving meanwhile.
2. [USER] Delete the `pocketquant.xyz` and `www` routes; re-add `A @ → <vps-ip>` (proxied) and `CNAME www → pocketquant.xyz` (proxied). The `api-flood` rule and 2FA stay; they also protect the old path.

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
