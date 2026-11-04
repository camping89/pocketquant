---
phase: 5
title: "Redis password rotation, release and prod checks"
status: pending
priority: P1
effort: "1h + two sync_repair runs (up to 24h)"
dependencies: [2, 3, 4]
---

# Phase 05: Redis password rotation, release and prod checks

## Goal

Rotate the prod Redis password, ship Phases 02-04 to prod in one release, then prove on prod that the fold, the daily check and the lookup fix behave as designed.

## Context

- Prod deploys when `master` moves (CI). A release is `develop:master` and is always an [ASK] with an explicit owner "yes".
- Live trading stays disarmed: LIVECHK must print `trader_live=False` before and after.
- Prod jobs: `sync_repair` at 00:00 and 12:00 UTC, `sync_backfill` at 03:00 UTC, `sync_verify_cascade` hourly (`register_sync_jobs` in `sync_jobs.py`).

## Task 05.1: Entry gate

1. `git status --porcelain -- src tests scripts deploy docs .github` is empty; `HEAD` equals `origin/develop`; the Phase 02, 03 and 04 reports end with `Result: PASS`.
2. SSH key (plan.md Ops recipe). LIVECHK: write `.cache/live.py` with `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, copy it into `trader` like PRODPY and run it. Pass: `trader_live=False`.
3. Record `free -m` on the VPS, `prev_master=$(git rev-parse origin/master)` and `git log --oneline origin/master..origin/develop` in the report.

## Task 05.2: Rotate the prod Redis password (E6)

**Why this order.** Every deploy writes the VPS `.env` from `../pocketquant-config/vps/default/.env` (`.github/workflows` step "Write prod .env from config"). `deploy/vps/10-deploy.sh` rolls `api`, `worker`, `trader` first and recreates `redis` only at its final `dc up -d --remove-orphans`. A new password in the config alone would start the new app copies against a Redis that still wants the old password, and the roll would fail. Redis 7.2 ACLs let the `default` user hold two passwords, so the old and new passwords both work during the roll, and the recreated Redis keeps only the new one.

**Rules.** Never print either password. Pass them only through files under `.cache/` that are deleted at the end, or through stdin.

**Steps:**
1. Generate the new password into a file: `uv run python -c "import secrets; print(secrets.token_urlsafe(32))" > .cache/redis_new` (do not cat it).
2. With a short Python script that prints only key names, set `REDIS_PASSWORD` and the password inside `REDIS_URL` to the new value in `../pocketquant-config/vps/default/.env`, and the password inside `REDIS_URL` in `../pocketquant-config/local/remote-db.env`. Save the old password to `.cache/redis_old` from the same file before the edit.
3. On the VPS, add the new password next to the old one. Send both through stdin, never on a command line: `HOST=...; cat .cache/redis_old .cache/redis_new | ssh -i .cache/ssh/vps_key "$HOST" 'read -r OLD; read -r NEW; docker exec -i pocketquant-redis redis-cli --no-auth-warning -a "$OLD" ACL SETUSER default ">$NEW"'`. Pass: it prints `OK`.
4. Check both passwords work: the same stdin pattern runs `redis-cli -a "$OLD" ping` and `redis-cli -a "$NEW" ping`. Pass: two `PONG`.
5. Commit and push `../pocketquant-config`: `chore(vps): rotate the redis password`; push with `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`.

**Verify:** steps 3 and 4 printed `OK` and two `PONG`; `git -C ../pocketquant-config status --porcelain` is empty.

## Task 05.3: [ASK] Release

Ask the owner in Vietnamese, intent first, with the commit list: push develop to master now? Recommended: yes. Only an explicit "yes" counts. On yes, push `develop:master` with the Ops recipe, record `released_at=<UTC>`, wait for the deploy run to finish with `conclusion=success`, then confirm `docker ps` shows `api`, `worker`, `trader`, `web`, `redis` healthy and record `free -m` again.

After the deploy, close the rotation:
1. With the stdin pattern of Task 05.2: `redis-cli -a "$NEW" ping` prints `PONG`, and `redis-cli -a "$OLD" ping` fails with `WRONGPASS` or `NOAUTH`.
2. `docker compose ... logs --since <released_at> api worker trader` (ANSI stripped) has no line matching `-i "redis.*(auth|wrongpass|noauth)"`.
3. `rm -f .cache/redis_old .cache/redis_new`.

If the deploy fails after step 3 of Task 05.2, the old password still works in Redis, so the running containers keep working; report the failure (Failure Protocol) and do not revert the config by hand.

## Task 05.4: Prod checks after the first sync_repair

Run after the first `sync_repair` that starts after `released_at` has finished (its job history row has `status` done). Logs come from `docker compose ... logs --since <released_at> worker trader`, ANSI stripped.

1. Repair touches only 1m and 1w: `grep "integrity.repaired" | grep -E "interval=(5m|15m|1h|4h|1d)" | wc -l` prints `0` (skip this line when E3=no).
2. Fold ran: no `cascade.symbol_failed` line; PRODPY reads the latest finished `sync_repair` and `sync_backfill` rows of the job history collection (`JobHistoryRepository`, fields `started_at`, `finished_at`, `duration_ms`) and prints `duration_ms=` for each. Pass: each under 600000 (R1).
3. Daily check: list `cascade.daily_divergence` lines since `released_at` as `(symbol, datetime, log time)`, split before and after the repair end. The hourly check can overlap a `sync_1m` or repair write, so a single line is not a failure (Phase 04 report). Pass: after the repair end, no `(symbol, datetime)` appears on two consecutive hourly runs. Lines before the repair end are recorded as drift the old code left (R3).
4. Lookup fix: `grep "binance_ws.callback_failed" | wc -l` prints `0`.
5. 5m-1d gaps the cascade cannot fill (R4): record every `integrity.issues_found` line for 5m-1d since `released_at`.
6. LIVECHK still prints `trader_live=False`.

**Verify:** items 1-4 and 6 meet their pass conditions; item 5 is recorded.

## Task 05.5: Second repair and the D16 comparison

After the second post-release `sync_repair`, re-run items 1-4 of 05.4, then run the D16 dry-run script from `plans/261101-0843-stf-to-mtf-foundation/phase-17-observe-compare-delete.md` Task 17.2 (as amended by D16) once. Pass: its last line prints `mismatches=0` and `diag_truncated=0`.

## Close

`rm -f .cache/ssh/vps_key`. Mark every phase completed in its front matter and in the plan's phase table, set `plan.md` `status: completed`, commit `docs(plans): record the cascade fold release and close the plan`, push `develop`. Report `reports/phase-05-release-and-prod-checks.md` ends with `Result: PASS`.

## Risk and rollback

- Rollback: on the owner's "yes", push the previous master sha (recorded in Task 05.1) to `master` to redeploy the old image; no data migration to undo. Bars rewritten by the fold hold the 1m aggregate, which is the intended value.

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
