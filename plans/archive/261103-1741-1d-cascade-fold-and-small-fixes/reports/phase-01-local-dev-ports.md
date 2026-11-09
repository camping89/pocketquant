# Phase 01 report: Local dev ports below the Windows dynamic range

Date: 2026-11-04 (Asia/Bangkok). Run in Git Bash on the owner's Windows 11 host.

## Outcome

Local Mongo now binds to host port 47017 and local Redis binds to host port 46379 in every local profile. Both ports are below the Windows dynamic range (49152-65535), so Hyper-V/WinNAT reservations can no longer take them. The config change is committed and pushed in `../pocketquant-config` as `7191764 chore(local): move local ports below the windows dynamic range`. The remote `master` is at `7191764`, confirmed with `git ls-remote`. This repo has no code change.

## Decision

E2=both. Both ports moved, as recorded in plan.md Owner decisions.

## Changes (`../pocketquant-config/local/`)

| File | Change |
|---|---|
| `all-local.env` | `MONGO_PORT=47017`, port 47017 inside `MONGODB_URL`, `REDIS_PORT=46379`, `REDIS_URL=redis://localhost:46379/0` |
| `remote-db-local-redis.env` | `MONGO_PORT=47017`, `REDIS_PORT=46379`, `REDIS_URL=redis://localhost:46379/0`. `MONGODB_URL` unchanged (tunnel). |
| `remote-db.env` | `MONGO_PORT=47017`, `REDIS_PORT=46379`. `MONGODB_URL` and `REDIS_URL` unchanged (tunnel). |

Each file has the comment `# Below 49152: Windows reserves moving blocks inside its dynamic port range 49152-65535.` directly above `MONGO_PORT`. The staged diff was 3 files, 12 insertions, 9 deletions. The untracked `.claude/` directory in pocketquant-config was not committed.

## Evidence

- Pre-check: `netstat -ano | grep -E ':(46379|47017) '` printed nothing. Neither port falls inside a range from `netsh interface ipv4 show excludedportrange protocol=tcp`. The excluded ranges were 5357, 50000-50760 in blocks, and 65035-65134. The dynamic range is 49152 with 16384 ports.
- Verify 1: `grep -hE '^(REDIS_PORT|MONGO_PORT)=' ../pocketquant-config/local/*.env | sort -u` printed only `MONGO_PORT=47017` and `REDIS_PORT=46379`.
- Verify 2, compose: I copied `all-local.env` to `.env` (no `.env` existed before; `.env` is git-ignored), then ran `just down` and `just up`. `docker ps` showed `pocketquant-redis 0.0.0.0:46379->6379/tcp` and `pocketquant-mongodb 0.0.0.0:47017->27017/tcp`.
- Verify 2, backend: `TZ=UTC .venv/Scripts/python.exe -m uvicorn pocketquant.app.main:app --host 127.0.0.1 --port 41921` logged `runtime.timezone tz=UTC`, `mongodb.connected`, `redis.connected` and `Application startup complete.` about 5 s after launch. The log had 0 matches for connection errors or tracebacks. `GET /api/v1/docs` returned 200. I stopped the backend afterwards and confirmed port 41921 was free.

## Deviation: `just be` was not used for Verify 2

`just be` failed before reaching the app. The output was `TZ=UTC : The term 'TZ=UTC' is not recognized as the name of a cmdlet...` and `error: recipe 'be' failed on line 39 with exit code 1`. The justfile sets `windows-shell` to PowerShell (`justfile:4`), and PowerShell does not support the `VAR=value cmd` prefix that the `be` recipe uses (`justfile:39`). The port change did not cause this. The same failure and the same workaround were already recorded at `plans/261019-1957-exness-go-live/phase-06-spa-mode-pause-and-hints.md:167`.

Under the Failure Protocol, I asked kongming for counsel. It advised running the recipe's own command directly from Git Bash with `TZ=UTC` and leaving this repo unchanged, because the phase is scoped to pocketquant-config. I followed that advice. I left out `--reload` so there was only one PID to stop; the flag does not affect connections.

## Carried finding

`just be` and the TZ lines of the test recipe (`justfile:71-75`) cannot run on Windows: they combine the PowerShell `windows-shell` with `TZ=` prefixes. This is not fixed here because Phase 01 changes only pocketquant-config. Acceptance A6 in plan.md names `just be` literally. This report meets A6's intent by running the recipe's command. A follow-up could turn those recipes into bash shebang recipes, as `tunnel` already is. That is the owner's or coordinator's call.

## Local state left behind

- `.env` in this repo is a copy of `all-local.env`.
- Docker Desktop is running. The local compose containers were stopped with `just down`, and their data stays in the named volumes.

## Notes for Phase 02 (kongming go/no-go: GO)

- `.env` now exists in this repo for the first time, and `Settings` reads it. The FULLSUITE baseline was established without a `.env`. Run FULLSUITE once before any Phase 02 code change. If the result deviates from the baseline, that is environment drift, not a code regression.
- The plan-file edits for this phase (phase-01 frontmatter, the plan.md table row, this report) are uncommitted in this repo. Commit them with the Phase 02 CLOSE commit.
- `../pocketquant-config/.claude/` is untracked there. Stage by path; never run `git add -A` in that repo.

Result: PASS
