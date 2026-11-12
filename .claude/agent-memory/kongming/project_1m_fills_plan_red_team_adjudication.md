---
name: 1m-fills-plan-red-team-adjudication
description: 2026-11-12 advice on plan 261112-1445 (backtest 1m fills, Triple Screen stop/target) - clock rule, backfill route, G2 sample gap for candidate C
metadata:
  type: project
---

Advice given 2026-11-12 on plan `261112-1445-backtest-1m-stop-fills-and-min-stop` (report `plans/reports/kongming-261112-1724-red-team-adjudication.md`). Not yet known whether the owner accepted it.

- **Clock rule advised:** `clock = bar start + own interval - finest interval`; single-stream runs keep today's timestamps; cross-mode trade key = `(side, floor(entry_time, entry interval))`. Do not set `bar_end` on backtest events.
- **Backfill route advised:** 1m into local Mongo, then `mongorestore` without `--drop` of only the range older than prod's first 1m bar; rollback = `deleteMany` below that cutoff.
- **Golden check advised:** replay `01a1c980` (starts 2023-01-01, so the run-level gate keeps it coarse), not `01a1c41f`.
- **G2 sample gap:** `.cache/km3/candidate_trades.csv` = 745 trades, pessimistic, t 3.32 full window; from 2024-05-01 552 trades, +77.7 R, t 2.58; before, 193 trades, t 2.11. Owner made t >= 3.0 binding, so the sample choice decides C.
- **Counts settled:** `01a1c41f` stored 489 trades; in `01a1c980`, 490 closed and 491 opened in 2025-11-09..2026-11-08.

**Why:** these numbers and rules were re-derived from code and scratch data and are easy to get wrong again.

**How to apply:** when reviewing phase 2-4 work of this plan, check against these rules first; verify the plan text adopted them before citing. A privacy hook blocks reads of `../pocketquant-config/*.env` for a subagent with no user turn; see [[project_triple_screen_oos_diagnosis_and_rubric]] for the rubric context.
