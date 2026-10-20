---
phase: 6
title: "Live observation, DST check 2026-11-02, go-live"
status: pending
priority: P1
effort: ~1h attention, to >= 2026-11-02
dependencies: [5]
---

# Phase 06: Live observation, DST check, go-live

## Context
- The Exness session calendar is modelled in `America/New_York` (`core/infra/calendars/exness_session_calendar_adapter.py:7-10,34`; the UTC constants `_EURUSD_SESSIONS` `:51` and `_XAUUSD_SESSIONS` `:62` were recorded under EDT). US DST ends on Sun 2026-11-01, so every UTC session edge moves one hour later. For XAUUSD, the Sunday reopen moves from 22:01:30Z to 23:01:30Z (kongming §3).
- Defect in the previous plan (kongming §3): Phase-08 T8.6 step 2 compares the live `trade_sessions` with the EDT constants `_XAUUSD_SESSIONS`/`_EURUSD_SESSIONS`, and fails exactly when the code is right. This phase compares against those constants shifted by +1 h.
- Asia/Bangkok is UTC+7.

## Files
- Create: `plans/261019-1957-exness-go-live/reports/live-observation.md`; at go-live, a journal entry `docs/journals/2026-11-02-exness-go-live.md` (or the actual date).

## Steps
1. Observation, from the end of Phase 05 to Fri 2026-10-30 ~20:30Z, with the `exness` subscriptions running (gated restart under D4-A). Once a day, one row in `reports/live-observation.md`:
   - container `StartedAt`;
   - counts of `exness_ws.circuit_breaker_open`, `exness.order_rejected_async`, `exness.daily_loss_cap_reached` and the stop events listed in Phase 05;
   - the number of `close` deals since the last row compared with the new `trades` rows for the `exness` subscriptions (must be equal);
   - realized today compared with the cap.
   
   A restart resets the counts and is not a failure.
2. **[Stop-and-ask]** Before Fri 2026-10-30 20:30Z, ask whether `exness` subscriptions and any open position stay on over the weekend that holds the DST change. If not, stop them; an open position keeps its SL at the venue.
3. Mon 2026-11-02 ~10:00 Bangkok, the DST check:
   - re-read `trade_sessions` for XAUUSD and EURUSD (inline snippet, as in the previous plan's T8.6) and compare with the constants shifted +1 h. Pass: equal;
   - the previous plan's phase-08 C3 (add the token header) with `CHECKS='XAUUSD:EXNESS/1m/2 EURUSD:EXNESS/1m/2'`. Pass: `PASS` on both lines (misaligned 0, every gap venue-empty). On a `FAIL`, run `integrity/repair` once and re-run; still `FAIL` fails;
   - at least one XAUUSD quote frame or 1m bar exists after Sun 2026-11-01 23:01:30Z, and none exists in 22:00–23:00Z of that Sunday;
   - if subscriptions ran: no order rejected for a closed market.
4. **[Stop-and-ask]** Go-live: the user confirms. The `exness` subscriptions run unattended (`desired_state=running`), and the flag stays true. Write the journal entry: the date, the D1–D5 answers, the AC6 numbers and the link to `reports/`.

## Validation
- Every observation row: `CB == 0`, no stop event, and close deals equal trades rows.
- Every check in step 3 passes.
- The user's go-live confirmation is recorded in the journal.

## Risk
- The session model is wrong after DST (M/M). Orders could be sent in a closed hour (the venue rejects them, so CANCELLED) or bars could be skipped. Step 3 catches it; stop the subscriptions and ask.
- Weekend gap through the SL (M/M). Step 2 decides whether positions are held.

## Rollback
Use `plan.md` "Rollback". Declaring go-live changes no code or config.
