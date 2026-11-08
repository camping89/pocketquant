# Advice: close the Exness US-DST session check plan on today's evidence

Date: 2026-11-08. Plan reviewed: `plans/261023-0056-exness-us-dst-session-shift`. Branch `develop` at `9517e8e0`. Advisory only: nothing in the repo or on prod was changed; one read-only inspection ran in the prod `api` container (Mongo reads, two `getInstrumentCondition` calls, `check_integrity`, the `sync_1m` stats route). The SSH key copy was deleted afterwards.

## Verdict

The plan's idea was valid and is now answered, so the plan should be closed, not cooked. What it set out to prove is proven: Exness moved the XAUUSD and EURUSD sessions one hour later in UTC on the US change day (not on the EU change day a week earlier), the live venue table equals the calendar constants shifted +1 h, stored 1m bars match the `America/New_York` calendar adapter on both sides of 2026-11-01, and the post-DST integrity window is clean apart from a few EURUSD minutes in the venue's 22:00-22:08Z rollover window. Cooking the plan as written would not fail on the venue; it would fail on its own commands, which target a prod topology that no longer exists. Re-running it buys nothing the evidence below does not already give.

## Is the idea still valid? (verified vs inferred)

Verified today on prod (read-only, about 10:40Z):

- Live `trade_sessions` from `getInstrumentCondition`: XAUUSD first enabled segment `Sun, 23:01:30`, last end `Fri, 21:57:59`; EURUSD `Sun, 22:05:00` and `Fri, 21:58:59`. Merged UTC spans equal the constants in `exness_session_calendar_adapter.py` shifted +3600 s for both symbols, and do not equal the unshifted constants. The plan's C5 would print `3600 True`.
- Stored 1m session edges versus `calendar.trading_minutes` (UTC): XAUUSD equal on Sun 10-25 (119 bars from 22:01), Fri 10-30 (1258, to 20:57), Sun 11-01 (59 from 23:01), Mon 11-02 (1378, daily break 21:57 to 23:00), Fri 11-06 (1318, to 21:57). EURUSD equal on 10-25 (175 from 21:05), 10-30 (1259, to 20:58), 11-02 (1440), 11-06 (1319, to 21:58). The only unequal day is EURUSD Sun 11-01: 111 bars from 22:09 against 115 expected from 22:05.
- `check_integrity`, 7 days back: XAUUSD 1m and 1h `missing=0 misaligned=0`; EURUSD 1h `0/0`; EURUSD 1m `missing=13 misaligned=0`, every range inside 22:00-22:08Z (11-01 22:05-22:08, 11-03 22:00-22:01, 11-04 22:02-22:04, 11-05 22:00, 11-05 22:02-22:04).
- `sync_1m` stats, 7-day window: `p95_ms=8865.5`, `by_status={'completed': 10080}` (7 x 1440, no failed runs). Within the plan's `p95_ms < 60000` bound.
- Earlier evidence in the repo agrees: MTF Phase 17 report (line 193) recorded XAUUSD `n1m=59/59` on Sun 11-01 against `119/119` on Sun 10-25, and the 1d cascade of that day equalled the fresh Exness 1d bar; kongming report of 2026-11-07 (Q2) reproduced `check_integrity` for 5m-1d over 7 days with `issues_total=0` for all six symbols.

Inferred, not verified:

- The 13 EURUSD minutes at 22:00-22:08Z are venue-empty, like the 21:xx gap before DST that the 1d-cascade plan recorded as "the known Exness rollover window, where the venue has no ticks". I did not run the plan's C3 venue read for those ranges. The circuit-breaker, reconnect and rate-limit log counters (C1) were not read; the json-file log driver and per-deploy container recreation make the plan's `SINCE` window unrecoverable anyway.

So: yes, the idea was sound, the venue follows US DST, and the adapter's `America/New_York` design handled the change without any code. The next transition is 2027-03-14 (US DST starts); the adapter needs no change for it either, and the tests already assert both offsets.

## What you should do

1. Add one row to the plan's Results table dated 2026-11-08 with the values above and the verdict `PASS (EURUSD rollover minutes not venue-read)`. Fill C1 as `not read (logs recreated per deploy)` and Running as `n/a (STF subscriptions deleted 2026-11-02)`.
2. Set `plan.md` `status: completed`, mark the phase row Completed, and add one short note: the commands were not run as written because the prod topology changed after the plan was written; evidence came from a read-only inspection recorded in this report.
3. Move the directory to `plans/archive/261023-0056-exness-us-dst-session-shift/`, as the lean-sync plan it was extracted from already is.
4. Commit the plan files only, on `develop`: `docs(plans): close the exness dst session check`. A docs-only push triggers no CI run.

## What you shouldn't do

- Do not repair the plan's commands and cook it. The fixes are real (replace `docker exec pocketquant-app` with `docker compose ... exec -T api`, send `X-Admin-Token` on `GET /subscriptions/` and `POST /integrity/check`, drop the two deleted STF subscription ids, replace `SINCE` with the container `StartedAt`), but they would only reproduce numbers already in hand.
- Do not call `POST /api/v1/market-data/integrity/repair` for the EURUSD 22:00-22:08Z ranges. `sync_repair` already retries 1m every 12 hours and logs `still_missing` for venue-empty minutes; a manual repair adds a prod write and changes nothing.
- Do not touch `exness_session_calendar_adapter.py` to carve out the rollover minutes. The calendar is correct at every edge the venue publishes; the missing minutes are the venue not printing candles, which the integrity check is meant to surface, not hide.
- Do not add a recurring DST script under `scripts/`. One function in a report, re-runnable by hand twice a year, costs nothing to keep; a script needs a second caller today, which it does not have.

## What could be better

- If the EURUSD rollover gap bothers you, the cheapest closure is a one-off C3-style venue read for the five ranges (about ten lines, read-only), recorded in the archived plan. Effort: minutes. Impact: turns the one inference into a fact. I did not do it because it is outside today's read-only scope decision, not because it is hard.
- For 2027-03-14, the inspection script in this session (stored edges versus `trading_minutes`, live `trade_sessions` versus constants shifted by the recorded offset) answers the question in one run. Keep it as text in the archived plan's phase file rather than as code.

## My take and how to get there

Close it today. Route: write the Results row and the note, move the directory, commit on `develop`. No cook, no deploy, no code. Total effort: under half an hour.

## Benefits

- One fewer pending plan whose question is already answered.
- The DST evidence stays findable in one place (the archived plan plus this report) for the March transition.
- Zero prod risk and zero code churn, which matches the plan's own "Out of scope: any code change".

## Trade-offs

- The EURUSD rollover minutes stay an inference. Cost if wrong: integrity keeps reporting 13 missing minutes a week that a venue read would have reclassified; no trading impact, since no subscription runs on EURUSD today.
- The plan's commands are archived stale. Anyone reusing them in March must apply the four mechanical fixes listed above; the note in `plan.md` says so.
- Stops being the right call if a later session edge disagrees with the calendar (for example a venue-side session change outside DST). Then the archived plan is the template for a new check, at the cost of re-deriving the commands for the current topology.

## Unverified

- Venue emptiness of the 13 EURUSD minutes (where I looked: `check_integrity` output and the stored 1m edges; what would confirm it: `getCandleHistory` from each range start, as in the plan's C3).
- C1 counters `CB`, `RC`, `RL` since the previous check (where I looked: the plan's own `SINCE` rule against the kongming 2026-11-07 "Limitation" on log retention; what would confirm it: `docker compose logs --since <StartedAt> trader` grep, bounded to the current container's life).

## Work checklist

- [ ] Add the 2026-11-08 Results row to `plans/261023-0056-exness-us-dst-session-shift/phase-01-post-dst-session-check.md` with the values in this report and verdict `PASS (EURUSD rollover minutes not venue-read)`.
- [ ] Set `phase-01` front matter `status: completed`.
- [ ] In `plan.md`: `status: completed`, phase row Completed, one note on why the commands were not run as written, linking `plans/reports/advise-261108-1722-exness-dst-plan-review.md`.
- [ ] `git mv plans/261023-0056-exness-us-dst-session-shift plans/archive/261023-0056-exness-us-dst-session-shift`.
- [ ] Commit `docs(plans): close the exness dst session check` on `develop`; push with the camping89 token recipe; no CI run expected.

## Success metrics

- `test -d plans/archive/261023-0056-exness-us-dst-session-shift && ! test -d plans/261023-0056-exness-us-dst-session-shift` succeeds.
- `grep -c "^status: completed" plans/archive/261023-0056-exness-us-dst-session-shift/plan.md` prints `1`.
- `grep -c "2026-11-08" plans/archive/261023-0056-exness-us-dst-session-shift/phase-01-post-dst-session-check.md` prints at least `1`.
- `git show --stat HEAD` lists only files under `plans/`.
- Next `sync_integrity` runs keep reporting XAUUSD 1m `missing=0` (visible on the job run doc since `fc173b5f`).

## Handoff brief

```text
Objective: Close plan 261023-0056-exness-us-dst-session-shift as completed on the read-only evidence of 2026-11-08 and archive it; docs only.
Done means: plans/archive/261023-0056-exness-us-dst-session-shift/plan.md exists with status: completed and the phase row Completed; its phase-01 file has one Results row dated 2026-11-08 (C5 3600 True; XAUUSD 1m/1h 7d 0/0; EURUSD 1h 0/0; EURUSD 1m missing=13 misaligned=0 all in 22:00-22:08Z; sync_1m 7d p95_ms 8865.5, completed 10080; CB/RC/RL not read; Running n/a; verdict PASS (EURUSD rollover minutes not venue-read)) and status: completed; plan.md carries a one-line note that the commands were not run as written because the prod topology changed, linking plans/reports/advise-261108-1722-exness-dst-plan-review.md; the old directory under plans/ is gone; one commit on develop "docs(plans): close the exness dst session check" touching only plans/ files, pushed.
Out of scope: repairing EURUSD 1m gaps; any calendar or code change; a recurring DST script; re-running C1 log counters or the C3 venue read; any deploy or prod write.
Constraints: English in plan files; no plan ids in commit messages beyond the conventional subject above; read-only on prod; docs-only commit (no CI run to wait for); push with the camping89 token recipe, never printing the token.
Stop and ask only if: a git operation would rewrite published history; a file outside plans/ would change; the archive move collides with an existing directory of the same name.
```
