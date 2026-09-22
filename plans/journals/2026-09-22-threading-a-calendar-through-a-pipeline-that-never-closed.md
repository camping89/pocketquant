---
title: Threading a calendar through a pipeline that never closed
date: 2026-09-22
summary: "Phase 3 shipped. Fourteen of its behaviours passed their own Verify steps while being provably untested, and the one defect no gate could ever have caught came from the plan being confidently wrong about arithmetic"
---

# Threading a calendar through a pipeline that never closed

## What happened

Phase 3 of the asset-class futures plan — put a trading calendar behind alignment,
cascade, integrity, freshness and annualization — went from `pending` to deployed and
verified in one session. Ten commits, the suite from 709 to 751 passing, green under
three host zones, and the golden snapshot captured before the first production edit
still byte-identical at the end.

The phase's own acceptance was "crypto comes out unchanged". It did. That turned out to
be the easy half.

## A refactor whose acceptance is "nothing changed" cannot be tested by its own gates

The shape of this phase is: take a hardcoded assumption, make it a parameter, pass the
old value, prove nothing moved. The trap is that passing the old value is exactly what
makes the new parameter invisible.

`Continuous24x7Calendar.bar_start` delegates to the very helper it replaces. So when I
mutated `is_bar_aligned` to ignore its calendar argument entirely and call the old
helper directly, all 712 tests passed. The parameter could have been decorative.

That was not one oversight. It was true of fourteen behaviours: the cascade's
non-advancing-step guard, its calendar-derived bucket size, the `calendar_id` and
`session_date` stamping on both write paths, the integrity grid, the weekly
short-circuit, session-aware staleness, the closed-market silence, the `is_market_open`
field, the closed-market sync skip and its grace window, `cascade_tfs`, and the report
service's annualization source. Every one passed the Verify step the plan prescribed
for it. Every one survived deletion.

The fix is not more assertions, it is a second calendar. Almost all of these became
testable the moment the real `CmeGlobexCalendarAdapter` was the other party: its
sessions open at 22:00 UTC the evening before, so a daily bar stamped at UTC midnight
is aligned on one calendar and misaligned on the other, and the hour 21:00–22:00 UTC
holds sixty trading minutes on one and zero on the other. Two real calendars
disagreeing is a better test than any stub, because the disagreement is the feature.

## The guard that hangs instead of failing

One of them needed more than an assertion. `compute_boundaries` now walks buckets by
asking the calendar for the next one, which means a calendar that maps the next instant
back onto the current bucket spins a cron job forever. The plan added a fallback for
that. Deleting the fallback to check the alarm sounds did not produce a red test — it
produced a test run that never ended.

A hung CI job and a failing one look nothing alike to the person reading the dashboard,
and the hung one is worse: it costs a timeout, reports nothing, and gets retried.
Running the call on a daemon thread with a five-second deadline turns the same mutation
into a red test in thirteen seconds and lets the rest of the suite finish. Daemon
specifically, because a pooled worker would block interpreter exit and the process would
hang at the end instead of the middle.

## Being confidently wrong about arithmetic

The plan asserted that a CME year holds between 245 and 255 sessions, citing "23h x 252
sessions". The adapter returned 259, so the test failed.

The instinct is to widen the band. The band was the defect: 252 is the NYSE cash
session. CME Globex equity futures do not skip US holidays, they close early — 2025 has
261 weekdays and exactly two full closures, New Year's Day and Christmas, which is 259.
The eleven short sessions are early closes, and they still produce a daily bar and a
daily return, so they count.

So the assertion was rewritten to exact equality rather than a wider range. That sounds
brittle and is the opposite: the adapter measures over a fixed 2025 reference window
precisely so a re-run reports the same Sharpe, and 2025 is a closed year whose holiday
set cannot change. The original band was the brittle one — 5000–6200 for hourly accepts
5957 (early closes ignored) and 5796 (a 252-session basis) as readily as the true 5910,
which is every wrong answer worth catching.

## The defect no gate would ever have caught

Reviewing that failure turned up a worse one, in a task that had already passed.

Task 9 said to give `cagr` a `days_per_year` argument fed from the calendar. That reads
as obviously right — annualization comes from the calendar, this phase's whole thesis.
But `cagr` divides *calendar* days. Feeding it 259 stretches one real year into 1.41, so
a CME strategy that doubles its capital over a year reports 63.5% growth instead of
100%.

Sharpe and CAGR sound like the same kind of quantity and are not. Sharpe counts return
observations, so it wants sessions. CAGR measures elapsed wall-clock time, so it wants
365, always, for every instrument. The plan generalised the right idea one step too far.

What makes this the interesting one: crypto cannot detect it. 365/365 is the identity.
The golden files are crypto. This phase's byte-identical gate is crypto. The entire
verification apparatus built to protect this refactor would have waved a 36%-wrong
futures CAGR through indefinitely, and nobody would have looked until someone compared
a backtest against a broker statement months later.

The lesson generalises past this bug: **a regression suite whose fixture is the old
behaviour cannot see a defect that only exists in the new one.** The safety net and the
change were pointed in different directions.

I also removed the parameter rather than defaulting it to 365. A knob that must always
hold one value to remain correct is not a safety feature, it is the next person's bug.

## What production said

The single most informative check was an integrity query in the first minute, same as
last time. The check now builds its expected-bar grid from the calendar's trading
minutes instead of `start + N*interval`; for BTC 1m over one day it returned `total
1440, missing 0, gaps []` — bit for bit what the arithmetic grid returned. Five cron
cycles then matched the pre-deploy baseline exactly.

And 57 `partial_aggregate` warnings in four minutes, which looked like a regression for
about a minute. They are in-progress buckets: at 01:51 the hourly bucket opened at 01:00
holds 51 of its 60 minutes. The useful part is the `expected` values — 60, 240, 1440 —
which are precisely the constants this phase deleted, arriving now from
`calendar.trading_minutes`. The alarming number was the proof.

## Carried forward

- `calendar_id` and `session_date` are effectively write-once on cascaded bars: the
  repository's diff-aware upsert only writes OHLCV on update, and returns early when
  OHLCV is unchanged. Buckets that predate the deploy will never be stamped. Phase 1's
  line applies unchanged — a fix to a write path is not a fix to the data that path
  already wrote.
- `cascade.partial_aggregate` is a WARNING firing once per symbol per timeframe per
  minute. Three symbols make fourteen a minute; futures will multiply it.
- The job-history `$sort` tie flaked for a third time. Still real, still minor, still
  nobody's phase.
