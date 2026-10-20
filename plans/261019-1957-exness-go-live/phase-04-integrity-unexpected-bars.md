---
phase: 4
title: "Count unexpected 1m bars on the integrity WARNING"
status: pending
priority: P2
effort: 1h
dependencies: []
---

# Phase 04: Count unexpected 1m bars on the integrity WARNING

## Context
- User decision (light log): `unexpected_count` and `unexpected_ranges` ride on the 1m `integrity.issues_found` WARNING. Phases 08 and 12 do not read the WARNING: they call `POST /api/v1/market-data/integrity/check`, which returns the same report dict (`app/routes/market_data.py:112-118`). Phase 12 records the count only; it never fails a row (user decision 2026-10-20 20:20).
- `check_integrity` (`src/pocketquant/engine/market_data/app_services/integrity_jobs.py`) reports only `expected − present`: it builds `in_progress`, `expected`, `missing` and `gap_ranges` (`:101-107`) and returns them (`:109-113`). The weekly branch returns early with no grid (`:91-99`).
- The daily job logs `integrity.issues_found` only when bars are misaligned or missing (`engine/market_data/app_services/sync_jobs.py:368-376`). `SYNC_INTERVALS` includes `WEEK_1` (`sync_jobs.py:72-80`).
- 1m is the only interval with no false positives (`D:/w/_me/algotrading/plans/reports/kongming-261020-1630-exness-trading-time-check.md` Q3): a 1m bar is expected exactly when its minute trades.
- `tests/app_test/market_data/test_integrity_calendar.py` already imports `EXNESS_CALENDARS` (`:21`).

## Gates in this phase
None. The `develop` push (Task 4.5) is authorized by the plan.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 04 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s; still failing → `NOT_YET: Docker Desktop is not running`).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing (else `NOT_YET: uncommitted code changes`).

## Tasks

### Task 4.1 — Compute unexpected 1m bars
- Goal: the 1m report lists stored bars at minutes the calendar says are closed.
- Target files and symbols: `integrity_jobs.py` → `check_integrity` (the block after `gap_ranges = _group_gaps(missing, step)` and the final `return`).
- Steps:
  1. After `gap_ranges`, add `unexpected = sorted(t for t in aligned_times if t < in_progress and t not in expected) if interval == Interval.MINUTE_1 else []`.
  2. One comment line: only 1m, because a 1m bar is expected exactly when its minute trades.
  3. Add `"unexpected_count": len(unexpected)` and `"unexpected_ranges": [(s.isoformat(), e.isoformat()) for s, e in _group_gaps(unexpected, step)]` to the returned dict.
- Success criteria: two new keys on non-weekly reports.
- Verify: `grep -c "unexpected_count" src/pocketquant/engine/market_data/app_services/integrity_jobs.py` prints a number ≥ 1.

### Task 4.2 — Log them, bounded
- Goal: the daily WARNING fires on unexpected bars and carries at most five ranges.
- Target files and symbols: `sync_jobs.py:368-376` (the `integrity.issues_found` block).
- Steps:
  1. The condition becomes `if report["misaligned_count"] or report["missing_count"] or report.get("unexpected_count"):`.
  2. Add `unexpected=report.get("unexpected_count", 0)` and `unexpected_ranges=report.get("unexpected_ranges", [])[:5]` to the WARNING. `.get` covers the weekly report; `[:5]` keeps the line bounded (CLAUDE.md log rule).
- Success criteria: two new log fields.
- Verify: `grep -c "unexpected_ranges" src/pocketquant/engine/market_data/app_services/sync_jobs.py` prints `1`.

### Task 4.3 — Tests
- Goal: the count is pinned on an Exness calendar.
- Target files and symbols: `tests/app_test/market_data/test_integrity_calendar.py`.
- Steps — two cases with the Exness XAUUSD calendar from `EXNESS_CALENDARS`:
  1. A stored 1m bar at a closed minute gives `unexpected_count == 1`.
  2. A stored 1m bar at an open minute gives `unexpected_count == 0`.
- Success criteria: two cases with behaviour names.
- Verify: `uv run python -m pytest tests/app_test/market_data -q` exits 0.

### Task 4.4 — Docs
- Goal: the light log is described where integrity is documented.
- Target files and symbols: `docs/system-architecture.md:138` (the `sync_integrity` row of the job table).
- Steps: change the row's "Does" cell to: "The only place missing 1m bars are reported (`integrity.issues_found`). On 1m it also logs `unexpected`, stored bars at minutes the calendar marks closed, with up to five `unexpected_ranges`."
- Success criteria: one table cell changed.
- Verify: `grep -rc "unexpected_ranges" docs/system-architecture.md` prints `1`.

### Task 4.5 — Gates and push
- Goal: green on `origin/develop`.
- Target files and symbols: whole repo.
- Steps: ruff and pyright on `src` and the touched test; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet`; commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: gates pass, push succeeds.
- Verify: ruff `All checks passed!`; pyright `0 errors`; lint-imports `Contracts: 8 kept, 0 broken.`; ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- A venue bar in a minute the session model marks closed shows as unexpected (M/L). That is the purpose: it flags a wrong session model, for example after a DST change. Phase 12 records it in the row (record only) and names it in the go-live question.
- The ratchet moves (L/L). No new function is added; stop and ask if it moves.

## Rollback
Revert the commit. No stored state changes.

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
