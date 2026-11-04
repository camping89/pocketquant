---
title: "Fold late 1m bars into cascaded bars, check 1d values, and four small fixes"
description: "Fix the three 1d cascade gaps found in the MTF foundation Phase 17 review (late 1m never folded, no 1d value check, truncating read limit), the TTLCache race behind the prod binance_ws KeyError, the unused subscription positions route, and the local dev ports that sit in the Windows dynamic port range."
status: completed
priority: P2
effort: "about 1.5d code + 1 deploy + 2 repair runs of observation"
branch: develop
tags: [market-data, cascade, integrity, binance, api, local-dev]
blockedBy: []
blocks: []
created: 2026-11-03
---

# Fold late 1m bars into cascaded bars, check 1d values, and four small fixes

## Overview

The MTF foundation plan closed with three owner-approved follow-ups for the 1d cascade (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-17-observe-compare-delete.md`, section "1d cascade review", owner answer D15). This plan fixes them, plus three items found on 2026-11-03:

1. A 1m bar written by `sync_repair` or `sync_backfill` after the 100-minute `sync_1m` lookback is never folded into 5m-1d. Prod shows 1m repairs on every repair run (kongming, 6 `integrity.repaired interval=1m` in 32 h).
2. No job checks 1d values in prod.
3. The cascade reads 1m bars newest first with `limit=expected_count + 5`, so a day with more stored 1m bars than the calendar expects loses its earliest bars and gets a wrong open.
4. Prod trader logged `binance_ws.callback_failed error="'ETHUSDT:BINANCE'"` then `binance_ws.error` and reconnected the whole Binance stream (2026-11-03T07:22:33Z). Cause: `SymbolLookupHelper.get` checks `key in _CACHE` and then reads `_CACHE[key]` on a `TTLCache`; an entry that expires between the two clock reads raises `KeyError(key)`. Reproduced locally with cachetools 7.1.4 and a fake timer; the error text matches the log exactly.
5. `GET /subscriptions/{id}/positions` and `StrategyQueryService.get_positions` have no caller (the web never calls the route).
6. Local profiles in `../pocketquant-config/local/` put Redis on 53679 and Mongo on 52017. Both sit in the Windows dynamic port range 49152-65535, where Hyper-V/WinNAT reserves blocks that move across reboots; on 2026-11-01 53679 was reserved and Redis had to move to 46379 by hand.

Live trading stays disarmed. No prod data is deleted or migrated; the only prod writes are the jobs' own bar upserts.

## Sources

- Diagnosis and fix design: `plans/reports/kongming-261103-1741-1d-cascade-and-small-fixes.md` (verified against code, installed cachetools, and prod logs).
- 1d cascade review and the D16 dry-run script: `plans/261101-0843-stf-to-mtf-foundation/reports/phase-17-observe-compare-delete.md` and `plans/261101-0843-stf-to-mtf-foundation/phase-17-observe-compare-delete.md` Task 17.2.
- Governance: `docs/governance/documentation-rules.md`, `docs/governance/no-look-ahead-rules.md`.

## Owner decisions

| # | Decision |
|---|---|
| E1 | Fix the three 1d cascade items in a new small plan (Phase 17 D15 answer, 2026-11-02). |
| E2 | Move both local ports (Redis and Mongo) below 49152 (owner, 2026-11-04). |
| E3 | Drop 5m-1d from the REST repair: `sync_repair` repairs 1m and 1w only; the cascade heals 5m-1d (owner, 2026-11-04). |
| E4 | Keep the re-raise in the Binance `_invoke_callback`: one reconnect per failure keeps logging bounded (owner, 2026-11-04). |
| E5 | Ship Phases 02-04 in one release (owner, 2026-11-04). |
| E6 | Rotate the prod Redis password, which was printed in a session transcript on 2026-11-03 (owner, 2026-11-04). Phase 05 does it before the release push. |

The release push itself stays an [ASK] that needs an explicit owner "yes" at the time.

## Conventions

- Run everything from the repo root `D:/w/_me/algotrading/pocketquant`, branch `develop`, in Git Bash.
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` exits 0. If only the ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the phase report; never pad or split code to satisfy it.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the tail line contains `4 failed` and `4 errors`, and the count prints `0`.
- **CLOSE** (end of every code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references, no plan or phase ids); push `develop` with the Ops recipe; then `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`.
- Code rules from `CLAUDE.md`: no docstrings, a WHY goes in a `#` comment above the code, a new helper needs a second real caller today, delete dead code in the same change, log levels by frequency.
- Each phase writes its report to `plans/261103-1741-1d-cascade-fold-and-small-fixes/reports/phase-NN-<slug>.md` and ends it with `Result: PASS` or `Result: FAIL`.

## Ops recipe

- SSH: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`; then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`.
- Compose on the VPS: `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`; services `api`, `worker`, `trader`, `web`.
- **PRODPY f**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py'`. Scripts start with `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]` and never print a secret.
- Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`. A release is `develop:master` in the same command and is always an [ASK] that needs an explicit owner "yes". Never print a token.
- Prod logs are console format with ANSI colours: strip with `sed 's/\x1b\[[0-9;]*m//g'` before grepping `key=value`.
- Never print an env value that holds a password or token. Print only key names, ports or a masked form.

## Phases

| # | Phase | Gate | Depends on | Status |
|---|---|---|---|---|
| 01 | [Local dev ports below the Windows dynamic range](./phase-01-local-dev-ports.md) | none (E2 decided) | none | Done |
| 02 | [Symbol lookup race, cascade read limit, unused positions route](./phase-02-small-fixes.md) | none | none | Done |
| 03 | [Repair and backfill fold late 1m bars](./phase-03-fold-late-1m-bars.md) | none (E3 decided) | 02 | Done |
| 04 | [Hourly 1d self-consistency check](./phase-04-daily-bar-check.md) | none | 02, 03 | Done |
| 05 | [Redis password rotation, release and prod checks](./phase-05-release-and-prod-checks.md) | release [ASK] | 02, 03, 04 | Done |

Phase 01 is outside this repo and can run any time; Phases 02-04 verify locally with Docker and do not need it, but `just up` on the all-local profile does.

## Acceptance

| # | Criterion | Evidence |
|---|---|---|
| A1 | `SymbolLookupHelper.get` never raises on an entry that expires between reads | Phase 02 race test red before, green after |
| A2 | A 1d cascade keeps the earliest 1m bar when stored minutes exceed the calendar's count | Phase 02 test; the limit-pinning tests are deleted |
| A3 | The positions route and `get_positions` are gone; no other caller broke | Phase 02 grep `0` and FULLSUITE |
| A4 | `sync_repair` and `sync_backfill` re-cascade 7 days for every tracked symbol; repair REST-touches only 1m and 1w | Phase 03 tests; prod repair logs show no `interval=5m`, `15m`, `1h`, `4h`, `1d` |
| A5 | An hourly job warns `cascade.daily_divergence` when a stored 1d differs from its 1m aggregate | Phase 04 tests; prod shows 0 warnings after the first post-deploy repair |
| A6 | Local `just up` and `just be` run on the all-local profile with ports below 49152 | Phase 01 report |
| A7 | No `binance_ws.callback_failed` with a `KeyError` text after deploy | Phase 05 log grep |
| A8 | Prod Redis accepts only the new password and refuses the old one | Phase 05 rotation checks |

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The 7-day re-cascade costs more than estimated (inference: about 35k indexed round trips per run) | Phase 05 records `sync_repair` and `sync_backfill` durations from job history; above 10 minutes, stop and ask |
| R2 | For a symbol tracked under 7 days, the oldest 4h/1d bucket partly covered by 1m is rebuilt from partial 1m and replaces a full REST backfill bar | Accepted (kongming): one bucket per interval per symbol, leaves the window after 7 days; recorded in Phase 03 |
| R3 | Before the first post-deploy repair, the new 1d check may warn on days the old code never folded | Phase 05 reads the warnings, then re-reads after the next repair; a warning that persists after a repair is a failure |
| R4 | Dropping 5m-1d from REST repair loses repairs that the cascade cannot make (a bucket with no stored 1m) | `sync_integrity` still reports 5m-1d gaps; Phase 05 reads its warnings |

## Failure Protocol (copied verbatim into every phase file)

```markdown
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
```
