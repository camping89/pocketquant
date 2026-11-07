---
name: phase08-checkpoint-open-items
description: Exness-only parallel plan, after D-5 cutover 2026-10-30 - index race on simultaneous role start (fix 6142249f, ships with D-6), stale deploy-window clauses left in phase-10/11 (phase-11:177 executable), Phase 09 missing the Binance WS 400 task, "market hours" undefined (D36 option A proposed)
metadata:
  type: project
---

After the D-5 cutover (2026-10-30 03:02Z, master 659120ef) the checkpoint report
`plans/261028-0652-exness-only-parallel-runtime/reports/kongming-phase-08-checkpoint.md` said GO for Phase 09 with these open items:

- Role containers starting together race on `JobHistoryRepository.ensure_indexes` (one container's `drop_index` aborts another's build). Fix 6142249f drops only on spec drift; not deployed until D-6. Only `job_history_repository.py` ever calls `drop_index` (verified by `git grep`). Trigger needs a simultaneous start (cutover, host reboot); a rolling deploy starts one container at a time.
- `plan.md:60` removed the deploy window, but `phase-11:177` still has an executable weekday/hour check and `phase-10:280,291`, `phase-11:29,138,209`, `phase-09:221` still name the window in prose.
- Phase 09 has no task for the Binance WS first-connect HTTP 400 even though `phase-08:74` and the Phase 07 checkpoint say "scheduled for Phase 09".
- "10 deploys in market hours" (`plan.md:113`) is undefined; proposed D36 = a row counts when the XAUUSD:EXNESS calendar (`exness_session_calendar_adapter.py:44-76`: open Sun 22:01:30Z-Fri 20:58Z, daily break 20:58-22:00:29Z) is open at deploy start and 15 min after. Owner had not decided as of 2026-10-30.

**Why:** these are the places a Phase 09/10/11 checkpoint will be asked about again; the plan text and the code disagree until the docs commit lands.
**How to apply:** at the next checkpoint, first check whether the docs-only plan commit (Q3 of the report) landed and whether D36 was recorded; if yes, delete this memory.
