# Sync Resilience & Observability — Shipped

**Date**: 2026-05-05 22:50
**Severity**: Medium (tactical fix, not architectural)
**Component**: Market data sync pipeline (handler, scheduler, UI)
**Status**: Resolved & deployed

## What Happened

15m bar sync was getting stuck — three consecutive empty-or-misaligned fetches at bar close would wedge the job indefinitely. Blamed race: provider lags behind exchange close tick, handler's bar-fetch validation rejects young bars. Applied layered defense: +2s cron offset (eliminates ~80% timing races) + bounded exponential retry (0, 3, 8s slots within 15s budget) for residual provider lag. Refactored handler to meet LOC budget and exposed three new structured logs (`fetch_recovered`, `no_progress`, `stuck_threshold_crossed`).

## The Brutal Truth

This was a death by a thousand paper cuts. Sync-one/handler.py bloated to 373 LOC chewing through my brain. I underestimated the retry orchestration complexity — the attempt counter, time-budget math, and no-progress-bump semantics needed five separate modules to stay sane. Friction point: `JobScheduler.add_cron_job` didn't accept a `second` kwarg initially; I had to thread it through both the cron-expression and explicit-parameter branches. Felt stupid backtracking on that.

The UI precedence flip (error → warn → ok → neutral) seemed trivial until I traced all six status-path permutations. Got it right, but the cognitive load was real.

## Technical Details

- **Retry knobs**: `(0, 3, 8)` seconds, 15s total budget. Aggressive but safe — combined with +2s cron offset, residual misaligned bars decay fast.
- **No-progress semantics**: `consecutive_empty_fetches` bumps on any `inserted==0` (empty + all-misaligned + all-already-existing). Single field, broader scope; docstring updated.
- **Observability**: `fetch_recovered` (INFO), `no_progress` (WARN), `stuck_threshold_crossed` (ERROR, fires once at streak==3 with age > 3× cadence).
- **Refactor**: extracted `bar_alignment.py`, `bar_filters.py`, `provider_fetch.py`, `anomaly_log.py`, `responses.py`. handler.py: 373 → 195 LOC.
- **Test coverage**: 13 new unit tests; all 104 backend tests pass; web build clean.
- **Code review**: 9/10. One minor concern: `_fetch_attempts` stored as instance state (thread-safe per Dishka scoping, but smells like coupling).

## What We Tried

- Conservative retry (0, 10, 30s) initially — too slow for 15m cadence, stuck jobs lingered 30s+.
- Switched to aggressive (0, 3, 8s) — hit 15s budget properly, pairs well with +2s offset.
- No auto-repair on stuck threshold — too many unknowns about provider recovery patterns. Defer if frequency > 1/week.

## Root Cause Analysis

Handler validation was correct; the problem was timing. Cron job fired 2s before bar close, provider lag hit us. Sync'd-bars validation (OHLCV age < 5s) rejected everything. Three strikes = stuck. We were solving the wrong problem: instead of retrying fetch, we needed to sync later.

## Lessons Learned

1. **Cron offsets are cheap, retries are expensive.** Add offset first, retry second.
2. **Bounded retries with monotonic budgets beat indefinite loops.** The `time.monotonic() + delay > deadline` check avoids overshooting and keeps ops predicable.
3. **No-progress semantics demand explicit naming.** Broadening the bump condition required a docstring, not just code. Field name survived; semantics grew.
4. **Module extraction overhead is real.** Five new files to save 178 LOC felt excessive until I realized each module owns one concern cleanly. Would extract again.

## Next Steps

1. **Monitor stuck frequency over two weeks** — if > 1/week, implement auto-repair logic (force sync, emit alert).
2. **Optional refactor**: replace `_fetch_attempts` instance state with explicit tuple return to remove coupling.
3. **Observability debt**: add Prometheus counters for `fetch_recovered` and `stuck_threshold_crossed` events.
