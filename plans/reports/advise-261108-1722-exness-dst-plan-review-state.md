# advise-state
phase: advise
input: --agent Review and advise on the open PocketQuant plan D:/w/_me/algotrading/pocketquant/plans/261023-0056-exness-us-dst-session-shift (Exness sessions after the US DST change). Repo: D:/w/_me/algotrading/pocketquant, branch develop. Is the plan still needed and correct against the current code and prod after the multi-timeframe foundation (plans/261101-0843-stf-to-mtf-foundation) and the 1d cascade fold (plans/261103-1741-1d-cascade-fold-and-small-fixes)? What should be done, cut or changed before cooking it?
flags: --agent
state file: D:/w/_me/algotrading/pocketquant/plans/reports/advise-261108-1722-exness-dst-plan-review-state.md
report path: D:/w/_me/algotrading/pocketquant/plans/reports/advise-261108-1722-exness-dst-plan-review.md
questions in Vietnamese; report/state in English

## scout-findings

Verified in code (develop HEAD 9517e8e0, 2026-11-08):
- `ExnessSessionCalendarAdapter` still holds the EDT-recorded tables in `America/New_York` (`_SESSION_TZ`, `_RECORDED_AT=2026-10-13`); `_EURUSD_SESSIONS`, `_XAUUSD_SESSIONS`, `_shifted`, `_week_offset` exist, so the plan's C5 script imports still resolve. Tests cover both sides of 2026-11-01 (`test_exness_session_calendar_adapter.py:63-116`).
- Plan mechanics are stale: (1) `docker exec pocketquant-app` — container gone since the api/worker/trader split (`17026288`, plan 261028-0652 Phase 08); prod now runs `pocketquant-prod-api-19`, `-worker-19`, `-trader-19` (seen in `docker ps` today), no `container_name`; (2) `GET /api/v1/subscriptions/` now requires `X-Admin-Token` (`routes/strategy.py:73`) so C2's `running` line would 401; (3) the two STF paper subscription ids in C2 were deleted with the STF data in MTF Phase 17 (A11); (4) C1's `SINCE` and `docker inspect pocketquant-app` are moot — the json-file log driver and per-deploy container recreation drop all older logs (kongming-261107 "Limitation"); (5) `POST /integrity/check` without a token (C2's loop) is 401; C3 already sends the token.
- `check_integrity` is read-only (`integrity_jobs.py:51-112`, reads `find_datetimes`); grid comes from the calendar (`_expected_instants`). `sync_integrity` covers 1m-1d daily at 04:00Z; `sync_repair` REST-touches 1m and 1w only (E3).
- Existing evidence already in reports: MTF Phase 17 report line 193 — XAUUSD Sunday 2026-11-01 had `n1m=59/59` vs `119/119` on 2026-10-25 (the venue moved its Sunday reopen one hour later on the US change day, not the EU change day 2026-10-25); kongming-261107 Q2 — read-only `check_integrity` 5m-1d, 7 days, all six symbols: `issues_total=0`.

Verified on prod today (read-only PRODPY in the `api` container, 2026-11-08 ~10:40Z; script `.cache/f.py`, key deleted after):
- Live `trade_sessions` (plan C5): XAUUSD first enabled `Sun, 23:01:30`, last end `Fri, 21:57:59`; EURUSD `Sun, 22:05:00` / `Fri, 21:58:59`. `live == constants shifted +3600`: True for both; `shift 0`: False for both. So C5 would print `3600 True`.
- Stored 1m edges vs `calendar.trading_minutes` (UTC): XAUUSD equal on 10-25 Sun (119, 22:01..), 10-30 Fri (1258, ..20:57), 11-01 Sun (59, 23:01..), 11-02 Mon (1378, break 21:57->23:00), 11-06 Fri (1318, ..21:57). EURUSD equal on 10-25, 10-30, 11-02 (1440), 11-06 (1319, ..21:58); NOT equal on 11-01 Sun: stored 111 from 22:09, calendar 115 from 22:05 (4 minutes 22:05-22:08 absent).
- `check_integrity` 7d: XAUUSD 1m and 1h `missing=0 misaligned=0`; EURUSD 1h `0/0`; EURUSD 1m `missing=13 misaligned=0`, ranges all inside 22:00-22:08Z (11-01 22:05-22:08, 11-03 22:00-22:01, 11-04 22:02-22:04, 11-05 22:00, 11-05 22:02-22:04). Pre-DST the same pattern sat at 21:xx (1d plan phase-05 report: "known Exness rollover window, where the venue has no ticks"). Inference, not venue-verified today: these are venue-empty minutes shifted +1h; the plan's C3 venue read would classify them.
- `sync_1m` 7d: `p95_ms=8865.5`, `by_status={'completed': 10080}` (7 x 1440, no failures). CB/RC/RL log counters not read.
- Tracked symbols carry no `calendar_id` field (`tracked_calendar_id=None`); calendars resolve elsewhere (not chased).

## qa-log
- Q1: plan end state (close on evidence / fix and cook once / twice-a-year check / delete) -> A1: "do what you need, the plan idea is still valid?" — owner delegates the end-state choice to the advisor and asks whether the idea (verify Exness sessions and bars after a US DST change) is still valid. Advisor's pick: close the plan on today's evidence (option 1). Open gap carried as assumption: the 13 EURUSD minutes at 22:00-22:08Z are venue-empty (not read from the venue today).

## reframing-draft
problem: The plan asked one question — after US DST ended on 2026-11-01, did Exness move the XAUUSD and EURUSD sessions one hour later in UTC, and does the America/New_York calendar adapter still match the stored bars? The idea was valid and the question is now answered: the live venue table equals the constants shifted +1 h, stored 1m edges match the calendar on both sides of the change, and 7-day integrity is clean except EURUSD minutes inside the known 22:00-22:08Z rollover window. The plan's commands, written on 2026-10-23, target a prod topology (pocketquant-app container, STF subscription ids, token-free routes) that the MTF foundation and runtime split removed, so cooking it as written would fail on mechanics, not on the venue. The right end state is to close the plan as a stateful record of today's evidence, not to re-run it.
requirements:
1. The plan's Results table gets one row dated 2026-11-08 with today's read-only evidence (C5 equivalent `3600 True`; XAUUSD 1m/1h `0/0`; EURUSD 1m `missing=13 misaligned=0` all in 22:00-22:08Z; sync_1m 7d p95 8865 ms, 10080 completed) and a verdict `PASS (EURUSD rollover minutes venue-unverified)`.
2. plan.md front matter `status: completed`; the phase table row says Completed; a short note names why the commands were not run as written (topology changed) and points to this advice report.
3. The plan directory moves to `plans/archive/` like `archive/261009-0858-exness-venue-lean-sync-refactor`.
4. No code, test, or docs change; no prod write.
goals: stop carrying a pending plan whose question is answered; keep the evidence findable for the next DST transition (2027-03-14) without adding code.
done means: `plans/archive/261023-0056-exness-us-dst-session-shift/plan.md` exists with `status: completed` and one Results row dated 2026-11-08; `plans/261023-0056-exness-us-dst-session-shift/` no longer exists; `git status` shows only plan files changed; committed on develop as `docs(plans): close the exness dst session check`.
non-goals: repairing the EURUSD 1m gaps; a calendar change; a recurring DST script in `scripts/`; re-running C1 log counters; any deploy.
constraints: read-only on prod; docs-only commit (no CI run expected); no plan ids in code; English in the plan files.

- Q2: preview confirmation (evidence -> verdict -> docs-only close-out; assumptions marked) -> A2: Matches (preview: inline). Reframing confirmed as drafted, both assumptions accepted.

## preview
inline (orchestrator rendered); confirmed 2026-11-08.

## next
phase: advise — report written to D:/w/_me/algotrading/pocketquant/plans/reports/advise-261108-1722-exness-dst-plan-review.md; session complete.
