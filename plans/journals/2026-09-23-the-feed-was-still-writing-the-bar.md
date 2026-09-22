---
title: The feed was still writing the bar
date: 2026-09-23
summary: "Phase 5 registered the first real second provider. The library contradicted the plan in three places, but the finding that mattered came from one thing no gate in the phase does: asking the live venue a question twice"
---

# The feed was still writing the bar

## What happened

Phase 5 of the futures plan put TradingView behind `IDataProviderPort` and registered it,
so everything Phase 4 could only mutation-test now has a live sibling. Eight commits, the
suite from 792 to 826, green under three host zones, deployed, and with zero
`tradingview` lines in production — because the code is deliberately dormant until a
futures symbol is seeded.

The interesting part is not the adapter. It is that the phase file described a library
that does not exist.

## Three claims, three contradictions

The plan said `tradingview_auth_token` was a constructor argument. `__init__` takes
`username` and `password`. It said a login failure could be caught and degraded to
anonymous mode. `__auth` catches everything itself, returns `None`, and the constructor
substitutes the string `"unauthorized_user_token"` — so login never raises and there is
nothing to catch. It implied one client instance could serve concurrent callers.
`get_hist` assigns `self.ws` and then reads from it, with one chart session shared across
calls, so two overlapping calls swap each other's series and ES bars land under NQ.

None of these took cleverness to find. They took `inspect.getsource`. Each was a claim
the phase text depended on, written by someone reasoning about a library they had not
installed, which is exactly what the two `[UNVERIFIED]` tags in the phase were warning
about — and the tags were on the two items that turned out to be *fine*. The interval
names were right. The calendar alias was right. The unmarked confident prose was wrong.

That inverts how I had been reading these plans. An explicit "I could not check this" is a
signal the author knew where their knowledge ended. Fluent specificity about an
unavailable dependency is the thing to distrust.

## A test that asserts something true about nothing

Task 5's host-zone test builds `datetime.fromtimestamp(epoch)` and asserts
`naive.timestamp() == epoch`. That is true of every non-ambiguous instant regardless of
what our code does. It is a test of CPython. And Task 3's own Verify pointed at that same
module, so the phase's entire coverage of the client was a test that could not fail.

The replacement drives the real client against a naive-indexed DataFrame. Mutating the
recovery to read the index as UTC leaves the suite **green under `TZ=UTC`** and red only
under `America/Chicago`. I have been running `just test-tz` for four phases as a chore.
This is the first time I watched it earn its place: the bug is invisible on the host the
tests normally run on, and a developer would have shipped it with a clean local suite.

The same shape bit me twice more in my own work. My adapter test asserted bars came back
ascending, against a fixture that was already ascending — deleting the sort kept it green.
And the plan's own ascending-order claim had the same hole. Sorted input cannot test a
sort. Feed it backwards or you have written a comment.

## The bisect I did not expect

My new end-to-end test passed, and two unrelated unit tests three directories away began
failing with `logs == []`. In isolation they passed. Together with my file they passed.
Only the full tree failed, which is the worst possible signature.

structlog runs here with `cache_logger_on_first_use=True`. A module-level logger first
used inside `capture_logs()` stays bound to that configuration, and after any later
`setup_logging()` — which `make_test_app` calls on every integration test — it stops being
capturable forever. My test was simply the first thing ever to log through
`anomaly_log.logger`. The suite had been passing because of an accident of which test got
there first.

I spent a while theorising and got it backwards twice before writing a six-line script
that just tried the sequences. The script took a minute. My reasoning took longer and was
wrong. That ratio keeps recurring and I keep not learning it fast enough.

## The question no gate asks

Every check in the phase runs against fakes. Nothing in twelve tasks fetches a real bar.
So before deploying I asked the venue directly, and got five real ES bars — which also
retired the risk that `CME_MINI` or the `1!` contract split was wrong, a mistake that
would have fetched nothing forever while every test stayed green.

Then I noticed the newest bar had 2,754 contracts against 100k-190k on the others. It was
still being written. So I asked the same question again 75 seconds later and diffed:

```
frontier bar 17:20  close 7828.25 vol  775   ->   close 7828.5 vol 1229
feed lag behind wall clock: 633s
```

The free plan is ten and a half minutes behind, and its newest bar is live. Our
in-progress filter compares against `bar_start(now)` — our clock — so a bar ten minutes in
the past sails through it. `sync_1m` never rewrites a bar it already has, and the cascade
builds 5m, 15m, 1h and 4h on top. Seeding today would have written a partial bar every
minute and compounded it upward.

The advisory review had predicted this at medium confidence from TradingView's published
delay policy. I could have implemented the fix on that basis and been right. Measuring it
cost two minutes and changed it from a plausible concern into a number I could put in a
commit message — and it also told me the thing the policy could not: that the delayed
series includes a *forming* bar rather than only complete ones, which is the whole
difference between "slightly stale data" and "corruption".

The fix drops the newest bar by position rather than timestamp, and only while the market
is open. That condition is the part worth remembering: once trading stops, the newest bar
is the session's real last bar and stays newest for as long as the market is shut, so
dropping unconditionally would silently lose the closing bar of every session forever. The
obvious version of this fix is wrong in a way that looks fine on a Tuesday afternoon.

It also gave `capabilities.realtime` its first consumer. The field had existed since Task
1 recording a fact nothing acted on — which, in hindsight, was the tell.

## Deploying the dormant thing first

I split the deploy from the seeding, which felt over-cautious until it wasn't. Pushing the
adapter changes nothing: the client is lazy, so DI does no network I/O, and no tracked
symbol carries a non-24/7 calendar. Production confirms it with the cleanest metric
available — zero log lines matching `tradingview`. Registered, wired, typechecked, and
never executed.

That gave me a window where the code was live and the scraper was not, which is when I ran
the delay measurement. Had I seeded in the same window, the first corrupt bars and the
discovery would have arrived together, and I would have been debugging under pressure
instead of reading a diff.

## Carried forward

- The stuck threshold probably fires at each session open, because a ten-minute-late feed
  means the first bar after 17:00 CT arrives around 17:11 and the no-progress streak
  builds in between. Probably — I have not measured it, and this entry is mostly about the
  difference between those two words.
- `_direct` upserts whatever the provider returns with no alignment filter, so the
  backfill wants a staged `n=3` pass before 21 fetches of 5000 bars.
- Five phases in, every one has produced Verify steps that cannot measure what they claim.
  I no longer treat that as a surprise, and I now read a gate by asking what it would
  catch if it ran, rather than whether it passes.
