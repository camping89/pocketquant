---
title: Shipping the UTC invariant, and what executing the plan found
date: 2026-09-22
summary: "Phase 1 shipped to production. Executing a heavily-validated plan still surfaced four defects in it, two of which would have passed their own gates while proving nothing"
---

# Shipping the UTC invariant, and what executing the plan found

## What happened

Phase 1 of the asset-class futures plan — pin UTC, assert it, fix two live crypto bugs —
went from `pending` to deployed and verified on the VPS in one session. Nine commits, the
suite from 668 to 678 passing, green under three host zones.

The plan had already been through a best-of-five generation, a Fable-tier verifier, three
controller corrections and a full validation pass with a measured baseline. It was a good
plan. Executing it still found four defects, and that gap is the interesting part.

## The defects, and what they have in common

**1. `Asia/Saigon` does not resolve.** The plan used it as its non-UTC test zone in 11
places, including its own success criteria. It is a deprecated alias that Debian/Ubuntu
moved into `tzdata-legacy`. The failure was silent, not loud: glibc degrades an unknown
zone to UTC, so the CI matrix and the phase gate would have run the whole suite a second
time in UTC and reported green.

**2. Task 6 broke exactly what Task 11 was scheduled to fix.** Making the Mongo client
tz-aware broke four naive fixtures — precisely the four that a task five steps later
listed for a `tzinfo=UTC` fix. The plan cured what it broke, in the wrong order.

**3. Task 7 changed a live wire format without saying so.** Routing sync-status through
`to_utc_iso` drops sub-second precision. The plan prescribed the edit and stated only
that no `.isoformat()` should remain.

**4. Production had no rollback image.** Found while reviewing the deploy, not the code.
Docker Hub's `ordering` parameter reads backwards — `-last_updated` returns *oldest*
first — so the cleanup job had been deleting the newest tags and keeping the oldest. The
running build existed only as an untagged `latest` the deploy would overwrite and prune.

The common thread: **every one of them was invisible to the check that was supposed to
catch it.** Two would have produced green gates. One was a contract change no test
asserted. One lived in a job nobody reads until they need it.

## What actually caught them

Not running the Verify steps — those passed. What caught them was asking whether a
passing test can fail.

The zone bug surfaced only because I mutated the source (stripped `timezone=UTC`) to
check that the new regression test would fail. It did not. The test the plan literally
describes passed under mutation, asserting nothing, because `tzlocal` memoizes the zone
and `time.tzset()` does not clear that cache. Defeating the cache is what raised
`ZoneInfoNotFoundError` and exposed the alias.

That is the lesson worth keeping: **a test that has never failed has not been tested.**
The same move — deliberately breaking the thing and checking the alarm sounds — also
confirmed the weekly-cutoff test (the old epoch-floor returns Thursday for every
Thursday-to-Sunday case) and the CI resolve guard (exit 1 for `Asia/Saigon`, 0 for
`Asia/Ho_Chi_Minh`).

## Fix the test or fix the code

Twice the failures looked identical — stale-looking fixtures — and the right answer
differed. Both times the deciding move was checking the *write* path before touching the
test. For Task 6 the repositories turned out to pass datetimes through unchanged and
every producer supplied aware UTC, so the fixtures were genuinely stale. For Task 7 the
project's own `docs/code-standards.md` already mandated the whole-second format, and BSON
stores only milliseconds, so the fixtures were asserting a precision nothing can produce.
Had either check gone the other way, editing the assertion would have buried a real bug.

## The bug the code fix does not fix

Task 8 stops the pipeline persisting partial weekly bars. It repairs none of the ones
already stored, because the sync is insert-only and the repair job's gap scan finds no
gap for a bar that exists. Every weekly bar in production was a mid-week snapshot: BTC's
week of 09-14 stored `close 76390.01` against Binance's `81178.00`, volume at half.

Worth stating plainly because it generalizes: **a fix to a write path is not a fix to the
data that path already wrote.** The plan's goals said "bar values unchanged", and the
repair deliberately violates that — the values changed because they were wrong.

## Deploying

The order that mattered: make rollback possible *first*. Tagging the running images took
one command and turned an unrecoverable deploy into a reversible one; everything after
that was cheap to be wrong about.

The single most informative check was an integrity query in the first minute. The feared
failure mode for `tz_aware=True` was the integrity job finding every bar missing and
resyncing every symbol against Binance rate limits. It reported `total 1440, missing 0` —
which is the atomic commit constraint working, and a far better signal than waiting to
see whether something bad happened.

## Carried forward

- Roughly twenty JSON `.isoformat()` emitters remain outside the five the plan named.
  Proposed as a Phase 7 sweep rather than folded in arbitrarily.
- `test_get_latest_by_job_ids_awaits_aggregate` flaked once: a same-millisecond tie in a
  `$sort`/`$first` with no secondary key. Real, minor, not Phase 1's business.
- `docs/deployment.md` still documents an emergency rollback that could not have worked.
