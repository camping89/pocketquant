# Phase 5 completion — TradingView History Adapter, Seeding and Backfill

Plan: `plans/260921-1436-asset-class-index-futures/`
Phase file: `phase-05-tradingview-history-and-backfill.md`
Date: 2026-09-22/23
Status: tasks 1-11 complete and deployed. Task 9 (`--apply` in production), Task 10's
backfill run and Task 12's live week are open and deliberately deferred to a separate
window — see "What is not done".

## Outcome

TradingView is registered as a second real provider, so every fallback path Phase 4
could only mutation-test now has a live sibling. Adding it was one entry in the DI
`providers` dict plus configuration that already existed, with no edit in `engine/` or
`app/`, which is G4 demonstrated rather than asserted.

The phase's genuinely new risk is not the adapter. It is that the library underneath it
behaves differently from what the plan described in three separate places, each of which
the phase text depended on, and that a second provider makes Phase 4's empty-result
fallback reachable for the first time.

## What the library actually does

Every claim below was read off the installed package at the pinned sha, not reasoned
about. All three contradict the phase text.

- **`tradingview_auth_token` is not a constructor argument.** `TvDatafeed.__init__` takes
  `username` and `password` only. The setting is kept and the token is assigned to
  `tv.token` after construction, where `get_hist` reads it. That also makes it the way
  past a broken login, which this phase's own risk table rates the highest-likelihood
  failure.
- **Login never raises.** `__auth` catches every exception and returns `None`;
  `__init__` then substitutes the literal `"unauthorized_user_token"` and continues. So
  Task 3 step 2's "on any exception fall back to `TvDatafeed()`" is unreachable, and
  `is_authenticated()` compares the token value instead.
- **One instance cannot serve two callers.** `get_hist` calls `__create_connection`,
  which assigns `self.ws`, then reads `self.ws.recv()`; `chart_session` is fixed at
  construction and shared. Two concurrent calls overwrite each other's socket and share
  one chart session, so the loser reads the winner's series and ES bars are stored under
  NQ. Every such bar is individually well-formed, so alignment, deduplication and the
  integrity scan all pass it. `sync_verify_cascade` fires at `:00:00` and `sync_1m` at
  `:00:02`, and `max_instances=1` is per job, so the overlap was guaranteed rather than
  hypothetical.

Both `[UNVERIFIED]` items check out: all seven `tvDatafeed.Interval` member names the
phase assumed exist, and `get_calendar("CME Globex Equity")` resolves with 259 sessions
in 2025, reproducing Correction 12's number independently.

## Verification

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `823 passed, 1 skipped` (baseline 792) |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 10 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| `uv run pyright` (src + tests) | `27 errors`, all pre-existing, 0 in new files |
| `just test-tz` | `823 passed` under UTC, Asia/Ho_Chi_Minh, America/Chicago |
| `cd web && npx tsc --noEmit` | exit 0 |
| `docker build -f deploy/Dockerfile` | exit 0; the runtime image imports `tvDatafeed`, the adapter and `ZoneInfo("America/Chicago")` |

The first commit was verified green in isolation (`812 passed`, 10 contracts, pyright 0),
so no revision on the branch is red.

## Verified against the live venue, which no gate in the phase does

A single anonymous fetch of `ES` / `CME_MINI` / `fut_contract=1` returned five real 1h
bars. This is the only check capable of catching a wrong exchange alias or a wrong
contract argument, and the phase has no step for it.

The result also proved the in-progress filter on real data rather than on a stub. The
newest bar was the one still forming — 2,754 contracts against 100k-190k on the closed
ones — and the adapter dropped exactly that one, logging
`tradingview.in_progress_bar_filtered count=1` and returning four. The free plan works
unauthenticated, which is what the entitlement decision requires.

`bar_start` was also walked across every hour of a full weekend for all seven intervals
with zero failures, because the adapter calls it on every fetch whether the market is
open or not. Session 6's fix holds for this new caller.

## What the phase's own Verify steps did not catch

This is the fifth phase in a row to produce gates that cannot measure what they claim.
Full detail is in `plan.md` under Corrections 17-22.

1. **Task 3's Verify does not test Task 3's code.** It points at the mapper test module,
   which never constructs the client.
2. **Task 5's host-zone test asserts a property of the standard library.**
   `naive.timestamp() == epoch` holds for every non-ambiguous instant whatever the
   adapter does, so it cannot fail if the epoch recovery is wrong. The replacement drives
   the real client against a naive-indexed DataFrame; mutating the recovery to read that
   index as UTC stays **green under `TZ=UTC`** and fails only under
   `America/Chicago`. That pair is the clearest evidence in this plan for why the
   timezone matrix exists — the bug is invisible on the host the tests usually run on.
3. **Task 1 step 3's STOP condition is broader than the failure it guards.** `uv sync`
   failed because hatchling rejects any direct reference without
   `tool.hatch.metadata.allow-direct-references`, which is our own build metadata and
   independent of the dependency. Resolution was never attempted; the pin then resolved
   unchanged. A literal executor would have stopped here for no reason.
4. **Task 10's stated reason is wrong and the real failure is worse.** Phase 3's
   `cascade_tfs` already omits `DAY_1` for a session calendar, so cascading cannot
   produce a misaligned daily bar. It produces no daily bar at all, while persisting 1m
   bars and reporting success.
5. **Task 11 step 6 cannot be followed as written.** `emit_no_progress` takes no instant;
   it reads the clock. It also prescribes `caplog`, which captures nothing here because
   structlog renders outside stdlib logging.

## Two defects in my own new tests

Both are the class this plan keeps rediscovering, and both were found by mutation rather
than by review.

- The adapter's ascending-order assertion was vacuous: the fixture is already sorted, so
  deleting the sort left it green. The fake now replays the bars reversed.
- The end-to-end test broke two unrelated unit tests in the same run without touching
  them. structlog runs with `cache_logger_on_first_use=True`, so a module logger first
  used inside `capture_logs()` stays bound to that configuration and stops being
  capturable after any later reconfigure — and `make_test_app` reconfigures on every
  integration test. The two victims received an empty list. The suite passed before only
  because those two tests happened to be that logger's first users.

## Mutation results

Every new behaviour was confirmed to turn a test red by actually being changed:

| Behaviour removed or inverted | Result |
|---|---|
| Remove the `asyncio.Lock` | re-entrancy test fails |
| Read the naive index as UTC | green under `TZ=UTC`, fails under `America/Chicago` |
| Drop the `n_bars` entitlement clamp | 2 failed |
| Raise the cap above the plan (drop `min()`) | 1 failed |
| Keep the in-progress bar | 1 failed |
| Drop the ascending sort | 1 failed (only after the fake was made to return descending) |
| Return `[]` instead of raising on no series | 1 failed |
| Keep the instance after a fetch timeout | 1 failed |
| Remove the Task 10 override / apply it to crypto / apply it silently | 1-2 failed each |
| Plant a direct `tvDatafeed` import in `engine/` | contract BROKEN |
| Remove the closed-market silence | 1 failed |
| Drop the `calendar_id` stamp | 1 failed |
| Derive `session_date` from the UTC date | 1 failed |
| Replace the integrity grid with a flat UTC one | 1 failed |

## Guards added from the pre-deploy review

Two findings, both deviations from Task 3, recorded as Correction 22.

**An empty answer from this provider is never a quiet market.** `get_hist` returns `None`
only when the response carries no series — a bad symbol, an entitlement refusal, a rate
limit — and TradingView serves the last N bars whatever the session state. Returning `[]`
made a refusal indistinguishable from emptiness to `fetch_with_retry`, which retries on
empty: three sockets per symbol per minute against a venue that had just refused us. That
is exactly the cost Correction 15 was written to avoid, arriving through the other branch.
It now raises, so Correction 15's path gives one call, one `market_data.sync.failed` ERROR
and `status=error`.

**A stalled login could have stopped crypto.** Upstream `__auth` posts with no timeout,
under this client's lock. A stall would hold the lock indefinitely, `sync_1m` would never
finish, `max_instances=1` would skip every later tick, and BTC/ETH/SOL would stop syncing
— a crypto outage reachable purely from futures configuration. No TradingView credentials
exist anywhere in `../pocketquant-config/`, which is precisely why this was worth closing
before any are added. Both threaded calls are now bounded, and the instance is discarded
on timeout: cancelling a `to_thread` does not stop the thread (confirmed directly —
`wait_for` returned in 0.10s while its thread slept 2.0s), so the orphan keeps writing to
that instance's socket, and reusing it would restore the corruption the lock removes.

## A tenth import contract

The seam is only real if nothing outside `core.infra.tradingview` can import the library,
and Task 8's grep checks the string `"tradingview"` rather than the import. The new
contract mirrors the `pandas_market_calendars` one, including `allow_indirect_imports`
for DI wiring. `plan.md`'s success criteria and `CLAUDE.md` were corrected; the latter
still claimed 8 and had been stale since Phase 2.

## Commits

```
9332bf1 feat(market-data): add the TradingView scraper behind a client seam
1c2bd20 fix(market-data): fetch a session-calendar daily bar directly
955bc47 feat(market-data): register TradingView and seed the index futures
7490328 test(market-data): drive a futures symbol through the real pipeline
21a15c3 docs: record the TradingView provider and its settings
0fd2139 docs(plans): record what executing phase 5 found
c4f4290 fix(market-data): make a refused scrape loud and a stalled login survivable
```

## What is not done, and why

- **Task 9 in production, Task 10's backfill, Task 12's live week.** Deliberately a
  separate window. Deploying the code is inert: the scraper client is built lazily so DI
  performs no network I/O, and no tracked symbol carries a non-24/7 calendar, so every
  new path is dormant and crypto routing is unchanged (`crypto_spot` and `crypto_perp`
  resolve to `binance`; only `index_future` resolves to `tradingview`). Seeding is the
  step that turns a live unofficial scraper on, and it wants a weekday CME session and
  someone watching.
- **Delay-awareness.** The free plan's CME feed is delayed roughly ten minutes.
  `capabilities.realtime` records this and nothing yet acts on it. Three consumers assume
  the newest vendor bar is current, and each needs verifying against the live feed before
  being treated as fact. Phase 6 already owns the poll floor and is the natural home.

## Unresolved questions

- **Does the free plan's delayed series include a still-forming newest bar?** If it does,
  the in-progress filter drops nothing, a partial bar can be persisted once and never
  refreshed because `sync_1m` filters existing bars, and the cascade builds on it.
  `sync_verify_cascade`'s `divergent_fraction` would catch it, but as a gate rather than
  a fix. Cheapest check: fetch the same 1m bar twice a minute apart and diff it.
- **Will the stuck threshold fire at every session open and halt resume?** On a delayed
  feed the first bar after the 17:00 CT open arrives around 17:11, which is past the
  180-second threshold. If so that is six ERRORs per day across three symbols and fails
  Task 12's own criterion by design, so the threshold needs the feed delay added or the
  gate needs to know about it.
- **Should `_direct` filter misaligned bars before persisting?** It currently upserts
  whatever the provider returns with no alignment check, so a misaligned vendor stamp at
  `n=5000` is 5000 documents the nightly scan flags and `sync_repair` re-fetches. Staging
  the backfill at `n=3` per interval first would answer it cheaply.
- **Whether the routing adapter should fall through on an empty result at all**, carried
  from Phase 4 and now sharper: with this provider raising rather than returning `[]`, the
  remaining empty-fallthrough case is a genuinely quiet venue, which TradingView never
  reports.
