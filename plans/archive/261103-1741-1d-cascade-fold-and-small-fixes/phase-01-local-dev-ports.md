---
phase: 1
title: "Local dev ports below the Windows dynamic range"
status: completed
priority: P3
effort: 30m
dependencies: []
---

# Phase 01: Local dev ports below the Windows dynamic range

## Goal

Local Mongo and Redis bind to host ports that Windows never reserves, so `just up` works after any reboot.

## Context

- Files are in the sibling repo `../pocketquant-config` (its own git history; push with the `camping89` gh account). This repo does not change.
- `deploy/compose.local.yml` publishes `${MONGO_PORT}:27017` and `${REDIS_PORT}:6379`; `justfile` runs compose with `--env-file .env`, where `.env` is a copy of one profile from `../pocketquant-config/local/`.
- Today every profile has `MONGO_PORT=52017` and `REDIS_PORT=53679`. `netsh int ipv4 show dynamicport tcp` shows the dynamic range 49152-65535. Hyper-V/WinNAT reserves blocks inside it (`netsh interface ipv4 show excludedportrange protocol=tcp`), and the blocks move across reboots. On 2026-11-01 53679 was reserved (`plans/261019-1957-exness-go-live/phase-06-spa-mode-pause-and-hints.md:167`).
- `just tunnel` reads prod ports from `../pocketquant-config/vps/default/.env`, never from a local profile, so prod is unaffected.
- `remote-db.env` uses prod Mongo and prod Redis through the tunnel; its PORT vars are unused (its own comment near line 20).

## Task 01.1: E2 (decided)

E2 is decided in plan.md Owner decisions: move both ports. Record `E2=both` in the report. Do not ask again.

## Task 01.2: Change the profiles

**Target files:** `../pocketquant-config/local/all-local.env`, `../pocketquant-config/local/remote-db-local-redis.env`, `../pocketquant-config/local/remote-db.env`.

**Steps:**
1. Check the new ports are free: `netstat -ano | grep -E ':(46379|47017) '` prints nothing, and neither is inside a range of `netsh interface ipv4 show excludedportrange protocol=tcp`.
2. `all-local.env`: `REDIS_PORT=46379`, `REDIS_URL=redis://localhost:46379/0`, `MONGO_PORT=47017` and the port inside `MONGODB_URL`. Edit with a script that never prints the URL values.
3. `remote-db-local-redis.env`: `REDIS_PORT=46379`, `REDIS_URL=redis://localhost:46379/0`, `MONGO_PORT=47017`. `MONGODB_URL` stays (it points at the tunnel).
4. `remote-db.env`: `MONGO_PORT=47017`, `REDIS_PORT=46379`. Leave `REDIS_URL` and `MONGODB_URL` (tunnel); Phase 05 changes the password inside `REDIS_URL`.
5. Above the PORT lines in each file add one comment: `# Below 49152: Windows reserves moving blocks inside its dynamic port range 49152-65535.`
6. Commit in `../pocketquant-config`: `chore(local): move local ports below the windows dynamic range`; push with `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant-config.git" HEAD`.

**Verify:**
- `grep -hE '^(REDIS_PORT|MONGO_PORT)=' ../pocketquant-config/local/*.env | sort -u` prints only ports below 49152.
- Copy `all-local.env` to `.env`, `just down`, `just up`, then `docker ps --format '{{.Names}} {{.Ports}}' | grep pocketquant-` shows `46379->6379` and `47017->27017`, and `just be` logs `startup` with no Redis or Mongo connection error within 30 s. Stop the backend afterwards.

## Risk and rollback

- Local data stays in the named volumes; only host ports change.
- Rollback: `git revert` the config commit and `just down && just up`.

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
