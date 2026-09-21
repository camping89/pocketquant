# Phase 1 completion — UTC Invariant and Live Crypto Bug Fixes

Plan: `plans/260921-1436-asset-class-index-futures/`
Phase file: `phase-01-utc-invariant-and-crypto-bugs.md`
Date: 2026-09-22
Status: complete. All 14 tasks done; shipped to production and verified on the VPS.

## Outcome

The pipeline's UTC assumption is now enforced by construction rather than held by
convention. The process timezone is pinned in every runtime surface and asserted at
startup; cron triggers carry an explicit UTC timezone instead of inheriting the host's;
Mongo decodes aware UTC; bar alignment rejects naive input; and the suite runs under
three host zones in CI. Two live crypto bugs are fixed: cron jobs no longer fire at
host-dependent instants, and the Binance weekly cutoff no longer persists a partial
week-to-date bar from Thursday through Sunday.

## Verification

Task 13 phase gate, chained, exit 0:

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `678 passed, 1 skipped` (baseline 668) |
| `uv run ruff check src tests scripts` | `All checks passed!` (DTZ enabled) |
| `uv run lint-imports` | `Contracts: 8 kept, 0 broken` |
| `TZ=Asia/Ho_Chi_Minh uv run pytest tests/ -q` | `678 passed, 1 skipped` |
| `TZ=America/Chicago uv run pytest tests/ -q` | `678 passed, 1 skipped` |
| `uv run pyright src` | `0 errors, 0 warnings` |
| `just test-tz` | three zones green, exit 0 |

Checks run beyond the phase's own Verify steps, because a passing test proves less
than a failing one:

- Stripping `timezone=UTC` from both `CronTrigger` call sites fails all three cron
  tests. The version the plan literally describes did not have this property — its
  third test passed under mutation, asserting nothing.
- The old epoch-floor cutoff returns Thursday 2026-06-04 for every Thursday-to-Sunday
  `now` in the test week, inside the current week, which is the bug Task 9 pins.
- The resolve guard exits 1 for `Asia/Saigon` and 0 for `Asia/Ho_Chi_Minh`.
- Task 6 atomicity re-verified on committed history: `git show --stat a0f663e
  --name-only` lists `mongodb.py`, `integrity_jobs.py` and
  `bar_builder_domain_service.py` together.

## Commits

```
3d1fbbc ci: run the suite under three host timezones
69c0f87 style(lint): enable ruff DTZ and make every datetime zone-explicit
925ba7e fix(binance): derive the weekly in-progress cutoff from bar alignment
29793f3 refactor(serialization): emit every JSON datetime as UTC ISO
a0f663e fix(persistence): decode Mongo datetimes as aware UTC
ed13a10 feat(app): refuse to start on a non-UTC process timezone
d22f8dd fix(scheduling): pin cron triggers to UTC instead of the host timezone
c5f77dc build(deploy): pin the process timezone to UTC and install tzdata
```

Plus `e5ab3bb fix(ci): keep the newest Docker Hub tags and pin the timezone matrix runner`,
added before the push — see Deployment below. All nine are on `origin/develop`.

## Deviations from the plan, and why

Three defects in the plan were found by executing it. Each is recorded in full in
`plan.md`'s Session 2 validation log as Corrections 5, 6 and 7.

1. **`Asia/Saigon` does not resolve.** It is a deprecated alias that Debian/Ubuntu
   moved into `tzdata-legacy`. glibc degrades an unknown zone to UTC rather than
   raising, so Task 12's matrix and Task 13's gate would have re-run the UTC suite and
   reported green while proving nothing. All 11 plan sites now use the canonical
   `Asia/Ho_Chi_Minh`, and both the test helper and the CI matrix now assert the zone
   actually resolved.
2. **Task 6 broke what Task 11 was scheduled to cure.** Making the Mongo client
   tz-aware broke exactly the four naive fixtures Task 11 step 4 lists. The fixes were
   pulled into Task 6's commit so no red revision exists. The write path was checked
   first to confirm these were stale fixtures rather than a repository persisting
   naive datetimes.
3. **Task 7 carries unstated wire-format changes.** `to_utc_iso` formats to whole
   seconds, so step 7 drops sub-second precision from `last_sync_at` and `last_bar_at`.
   Accepted, because `docs/code-standards.md:777-783` already mandates this contract,
   BSON stores only milliseconds, and every reader renders at minute granularity.

Two smaller deviations, both inside the spirit of their task:

- The zone-switching fixture was extracted to `tests/core_test/conftest.py` rather than
  duplicated across the two timezone test modules.
- Three DTZ001 findings in `scripts/backfill/test_binance_bars.py` are passthrough
  lambdas (`lambda *a, **kw: datetime(*a, **kw)`), not literal constructors. The plan
  said to add `tzinfo=UTC`; doing so would override whatever tzinfo the code under test
  supplies. They carry a `noqa` with that reason instead.

## Follow-ups, not done and not in Phase 1 scope

- **Serialization sweep.** Roughly twenty further JSON `.isoformat()` emitters remain
  outside Task 7's five named sites. Proposed as a Phase 7 task.
  `backtest_stats_service._encode_cursor` must stay on `isoformat()` — it is a
  pagination round-trip, not a display field.
- **`backtest_stats_service` wire format.** Its four `.isoformat()` calls gained a
  `+00:00` offset as a side effect of Task 6. Strictly more correct, but Phase 7's UI
  work should know.
- **Job-history flake.** `test_get_latest_by_job_ids_awaits_aggregate` failed once in a
  full-suite run and passed in isolation and on re-run. Root cause is most likely a
  same-millisecond tie in a `$sort`/`$first` pipeline with no secondary key
  (`job_history_repository.py:193-197`). A production `_id` tiebreak would close it.
- **CI runner pin.** `runs-on: ubuntu-latest` migrates to Ubuntu 26.04 between
  2026-10-19 and 2026-11-19, an image whose `tzdata` packaging nobody has probed.
  Pinning `ubuntu-24.04` would freeze the new matrix on a known-good image. Left to
  the user; the resolve-check guard makes a bad migration fail loudly rather than
  silently.

## Deployment (Task 14)

Actions run `35633903668` green on every job, including all three timezone legs on the
newly pinned `ubuntu-24.04` runner — the first real execution of the matrix.

Verified on the VPS after deploy:

| Check | Result |
|-------|--------|
| Startup assertion | `runtime.timezone tz=UTC tzlocal=UTC tzname=('UTC','UTC')`, logged once |
| Containers | `pocketquant-app` and `-web` healthy on a fresh image |
| Health endpoint | `HTTP 200` |
| UTC invariant in container | `TZ=UTC`, `time.timezone=0`, `daylight=0` |
| `ZoneInfo('America/Chicago')` | resolves — the Task 1 `tzdata` install works |
| Integrity check, BTC 1m, 1 day | `total 1440, misaligned 0, missing 0, gaps []` |
| Sync heartbeat | cascade/insert events within 3 minutes |
| Errors since start | zero `Traceback`, `TypeError`, `offset-naive` |
| Rollback image | `pre-utc-20260922` survived `docker image prune` |

The integrity result is the one that mattered most: the failure mode the plan's risk
table fears would have reported roughly 1440 missing bars. It reported zero, which is
the atomic Task 6 commit working as designed.

Two pre-deploy findings are recorded as Correction 8 in `plan.md`: production had no
rollback image because `cleanup-tags` deleted the newest tags rather than the oldest,
and every stored weekly bar was a stale mid-week snapshot that Task 8 prevents but does
not repair. Both were fixed — the first in `e5ab3bb`, the second by resyncing `1w` for
all three symbols after backing up 1269 documents. Weekly values now match Binance
exactly (BTC `81178.00`, ETH `2645.21`, SOL `111.17` for the week of 2026-09-14).

## Unresolved questions

None blocking. Remaining follow-ups are listed above: the serialization sweep proposed
for Phase 7, the job-history tiebreak flake, a docs note covering the `TZ` pin and the
refuse-to-start assertion, and a test for the `register_sync_jobs` trigger guard.
