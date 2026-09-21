---
title: Planning ES/NQ/YM futures as an asset-class generalization
date: 2026-09-21
summary: "Advise interview, datetime audit and a best-of-5 plan run turned 'add three futures symbols' into a calendar-parameterized pipeline, and surfaced two live crypto bugs"
---

# Planning ES/NQ/YM futures as an asset-class generalization

## What happened

The request was "get ES1!, NQ1!, YM1! — these are not crypto so we need to research".
The data-provider adapter turned out to be the smallest part of the job.

**Reframing (ak:advise, 6 interview rounds).** The outcome grew from "backtest
research" to "charts + paper trading + backtests", and then the user rejected the
futures-shaped framing entirely in favour of a general one: group symbols by asset
class in an enum, store each class's trading schedule alongside it, and drive the
existing pipeline from that rather than branching on futures. The source decision went
against the recommendation — TradingView via the `tvdatafeed` scraper rather than a
licensed feed — which caps history at 5,000-20,000 bars per timeframe and defers
multi-year 1m backtests by years. That was recorded as an accepted trade-off with an
explicit switch condition and a bounded switch cost, not argued twice.

**Datetime audit (kongming).** The pipeline is UTC by convention, not by construction.
Binance's conventions happen to match every hardcoded assumption — UTC-midnight days,
Monday-midnight weeks, a dense 1m grid, continuous trading — so nothing has broken yet.
Five assumptions fire on day one of any session-scheduled asset: the alignment filter
drops every session-based 1d/1w bar, the cascade buckets on a fixed UTC epoch grid,
the integrity check assumes a dense grid and makes repair thrash, freshness logic calls
a closed market stuck, and annualization is 365x24.

**Two live bugs, unrelated to futures.** `scheduler.py:79` sets `timezone="UTC"` on the
scheduler, but `:219-233` builds `CronTrigger(...)` with no `timezone=`, so APScheduler
falls back to `tzlocal` and pickles the host zone into the Mongo jobstore; production is
UTC only because the container sets no TZ. And `binance_adapter.py:80-83` floors the
weekly cutoff to a Thursday-aligned epoch week, so from Thursday to Sunday the
in-progress Monday kline is persisted partial.

**Best-of-5 plan run (ak:plan --ultra --advice).** Five Opus candidates each wrote a
complete seven-phase plan from one immutable evidence packet; a Fable verifier scored
them against a five-criterion rubric. Winner 85, runner-up 78, margin recorded as low
because the lead on the deciding criterion was only 3 points. The fan-out still earned
itself: the winner was the only candidate to notice that `SyncService._persist_bars`
calls `SymbolRepository.upsert` with a full-document `$set`, which would reset every
seeded futures symbol's `asset_class`, `calendar_id` and `contract_spec` to crypto
defaults on the first sync after seeding. The other four would have looked correct
through Phase 5 and then broken silently.

## Decision

Generalize rather than special-case: an `AssetClass` enum with a persisted trading
schedule, a `ITradingCalendarPort` whose 24/7 implementation keeps crypto
byte-identical, and provider resolution keyed by asset class plus provider id. The
seven phases are ordered so the UTC invariant and the calendar refactor are both proven
on the crypto path before a single futures symbol exists.

Three verifier-named defects in the winning plan were corrected only after independently
re-verifying each against the repo, because a plan that fails its own gate hands the
executor a guaranteed stop:
- Every phase gate ran `uv run ruff check .`, which exits non-zero today with 301
  pre-existing errors; `ruff check src tests scripts` passes clean.
- `TZ=UTC` was pinned everywhere but no zone data was installed. The pip `tzdata` is
  locked `sys_platform == 'emscripten' or sys_platform == 'win32'` and the Dockerfile
  runtime stage installs only `curl`, so `ZoneInfo("America/Chicago")` would raise
  inside the container and all of Phase 2 would fail. This also corrected an error in
  the audit, which had claimed the locked `tzdata` covered Linux.
- Phase 3 changes the `check_integrity`/`repair_integrity` signatures but listed only
  the `sync_jobs.py` callers; `app/routes/integrity.py:33` and `:45` call them too, and
  would have been a runtime `TypeError` on the first request.

One verifier claim was rejected on evidence rather than applied: the `_can_afford`
"wedge risk" does not exist, because `paper_broker_adapter.py:487-497` already exempts
a BUY that covers a short, a guard added by plan `260628-2013`. The genuine question
was narrower and went to the user, who chose to keep the unmultiplied affordability
check with the consequence recorded explicitly.

## Next steps

Phase 1 ships alone to production before Phase 2 starts, because it fixes the two live
bugs and touches no futures code. `git push origin develop` is the entire deploy per
`docs/deployment.md`; the phase ends by confirming on the live container that
`time.timezone` is 0 and that `ZoneInfo('America/Chicago')` resolves, which is the
first real proof the TZ pin and tzdata install work in the deployed image.

Carried unresolved: the TradingView plan tier and whether the non-professional CME
add-on is held. Both are config, so no code depends on the answer, but until the add-on
exists CME quotes are 10-minute delayed and paper fills faster than 15m bars are
fiction.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
