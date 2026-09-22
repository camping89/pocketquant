---
title: "Asset-class index futures (ES/NQ/YM) via TradingView"
description: "Generalize the 24/7-crypto pipeline into an asset-class + trading-calendar model, add provider routing and a TradingView adapter pair, and bring ES1!/NQ1!/YM1! into charts, paper trading and backtests."
status: in-progress
priority: P1
effort: 11d
branch: develop
tags: [market-data, futures, timezone, provider-routing, tradingview, calendar, backtest]
created: 2026-09-21
blockedBy: []
blocks: []
---

## Overview

PocketQuant is hardwired to one 24/7 crypto venue: DI binds exactly one REST provider
(`BinanceAdapter`) and one WS provider (`BinanceWebSocketAdapter`), and the sync,
cascade, integrity, freshness, annualization and paper-broker math all assume
continuous trading and price x quantity units. This plan makes the trading calendar
and the contract spec explicit parameters of the existing pipeline, makes provider
resolution a function of asset class plus provider id, and then adds CME/CBOT
continuous front-month index futures (`ES1!:CME_MINI`, `NQ1!:CME_MINI`,
`YM1!:CBOT_MINI`) through TradingView. No parallel futures pipeline is built.

**Phase numbering note.** The confirmed advice in
`plans/reports/advise-260921-2001-index-futures-data-provider.md` numbers its route
Phase 0 through Phase 6. This plan numbers the same seven steps 1 through 7:
advice Phase 0 = plan Phase 1, advice Phase 1 = plan Phase 2, and so on through
advice Phase 6 = plan Phase 7.

The order retires risk before it can hide: the UTC invariant and the calendar
refactor are both proven on the crypto path with the 24/7 calendar before a single
futures symbol exists, and provider routing ships with Binance as its only
registered provider before TradingView enters.

## Phases

| # | Phase | File | Effort | Depends on |
|---|-------|------|--------|-----------|
| 1 | UTC Invariant and Live Crypto Bug Fixes | [phase-01-utc-invariant-and-crypto-bugs.md](./phase-01-utc-invariant-and-crypto-bugs.md) | 1.5d | — |
| 2 | Trading Calendar Port and Asset-Class Domain Model | [phase-02-calendar-port-and-asset-class-model.md](./phase-02-calendar-port-and-asset-class-model.md) | 2d | 1 |
| 3 | Calendar-Threaded Pipeline on the 24/7 Calendar | [phase-03-calendar-threaded-pipeline.md](./phase-03-calendar-threaded-pipeline.md) | 2.5d | 2 |
| 4 | Provider Routing Adapters and Settings | [phase-04-provider-routing-adapters.md](./phase-04-provider-routing-adapters.md) | 1d | 2 |
| 5 | TradingView History Adapter, Seeding and Backfill | [phase-05-tradingview-history-and-backfill.md](./phase-05-tradingview-history-and-backfill.md) | 1.5d | 3, 4 |
| 6 | Polling Quote Adapter and Contract-Aware Trading Math | [phase-06-quote-adapter-and-contract-math.md](./phase-06-quote-adapter-and-contract-math.md) | 1.5d | 5 |
| 7 | UI, Docs and Success-Metric Run-Through | [phase-07-ui-docs-and-metrics.md](./phase-07-ui-docs-and-metrics.md) | 1d | 6 |

## Goals

- **G1** Fresh futures bars land within one cron cycle during CME session hours.
- **G2** A paper ES strategy runs a full session and reports USD PnL that matches
  points x multiplier x contracts.
- **G3** A 1h ES backtest reports dollar PnL and a Sharpe annualized on the CME
  session calendar, not on 365 x 24.
- **G4** Adding a provider is one adapter plus one config entry, with zero edits in
  `engine/` or `app/`.
- **G5** BTC/ETH/SOL behaviour, bar values, cascade output and metrics are unchanged.
- **G6** The app refuses to start on a non-UTC host, and the DST-boundary suite passes.

## Success criteria

- `uv run pytest` exits 0 with no test skipped that was not skipped before, and the
  existing crypto test count is unchanged or higher.
- `uv run ruff check src tests scripts` exits 0 with the `DTZ` rules enabled.
- `uv run lint-imports` exits 0 — 8 contracts today, 9 from Phase 2 onward (the new
  contract confines `pandas_market_calendars` to `core/infra`).
- Every cron job reports the same `next_run_time` under `TZ=UTC`, `TZ=Asia/Ho_Chi_Minh`
  and `TZ=America/Chicago`.
- Golden-file comparison: crypto bars, cascade output and performance metrics are
  byte-identical before and after the calendar refactor.
- Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
  `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across
  one full week including a weekend.
- `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0`.

## Non-goals

A real futures broker; multi-year 1m futures history (accepted trade-off — the cron
accumulates forward); Databento/IBKR adapters; tick-level fidelity beyond the
scraper; contract-roll modelling inside paper positions; redoing the margin
accounting shipped in plan `260628-2013`; any branching on the TradingView plan tier.

## Dependencies and risks

- **Hard ordering constraint (Phase 1).** `AsyncMongoClient(tz_aware=True)` and the
  `integrity_jobs.py:50` naive-`now` fix must land in the SAME commit. Flipping
  `tz_aware` alone makes the integrity check report every bar missing and triggers a
  full resync of every symbol.
- **New dependencies.** `pandas_market_calendars` (Phase 2, `core/infra` only) and
  the `tvDatafeed` scraper installed from git (Phase 5). Both sit behind interfaces
  so they are replaceable.
- **Credentials.** TradingView username/password/auth token live only in
  `../pocketquant-config/`. This repo carries field names and defaults, never values.


## Ultra verifier receipt

```
ultra: picked=A/5 margin=low unanimous=no rejected_all=no
```

Five independent candidates each produced a complete seven-phase plan from one
immutable evidence packet; a Fable-tier verifier scored them 1-20 on faithfulness,
evidence grounding, handover quality, sequencing and actionability, then selected one
winner. Scores: A 85, B 78, D 72, C 71, E 64. No candidate was disqualified. Full
scoring and rationale: `.ultra/verdict.md`. Candidate drafts and the evidence packet
are retained under `.ultra/` for audit.

The winner led on total score by 7 points but by only 3 on the deciding criterion, so
the margin is recorded as **low**: a single-pass plan would plausibly have been
comparable in overall shape. What the fan-out did buy was one decisive
single-candidate catch, recorded below.

## Controller corrections applied to the winning plan

The verifier named three defects in the winner that would have stopped an executor.
Each was independently re-verified against the repository before the edit, and each
is a factual fix to a broken command or a missing caller, not a blend of another
candidate's design.

1. **Ruff gate scope.** Every phase gate ran `uv run ruff check .`, which exits
   non-zero today: `ruff check .` reports 301 pre-existing errors (it walks
   `.venv/`, `web/`, and cache directories), while `ruff check src tests scripts`
   reports `All checks passed!`. All 10 occurrences across `plan.md` and six phase
   files were rescoped, so Phase 1's gate is now passable.
2. **Timezone database missing in the container.** The winner pinned `TZ=UTC`
   everywhere but never installed zone data. Verified: the pip `tzdata` package is
   locked with marker `sys_platform == 'emscripten' or sys_platform == 'win32'`, so
   it is absent on Linux, and the `runtime` stage of `deploy/Dockerfile` installs
   only `curl`. Without the OS `tzdata` package, `ZoneInfo("America/Chicago")` raises
   `ZoneInfoNotFoundError` and all of Phase 2 fails in the container. Phase 1 Task 1
   now installs it and verifies it with a `docker run` zone resolution check.
   (This also corrects an error in the datetime audit, which claimed the locked
   `tzdata` covered Linux.)
3. **Integrity HTTP routes were not updated.** Phase 3 Task 4 changes the signatures
   of `check_integrity` and `repair_integrity` but listed only the `sync_jobs.py`
   callers. Verified two more at `src/pocketquant/app/routes/integrity.py:33` and
   `:45`; leaving them would be a runtime `TypeError` on the first request to
   `/integrity/check` or `/integrity/repair`. Both routes are now named targets with
   a `FromDishka` calendar-factory step, and the gate greps for any call site left
   without a calendar argument.

### Why this plan won

It is the only one of the five that caught that `SyncService._persist_bars` calls
`SymbolRepository.upsert` with a full-document `$set`, which would reset every seeded
futures symbol's `asset_class`, `calendar_id` and `contract_spec` back to crypto
defaults on the first sync cycle after seeding. The other four plans would have
appeared to work through Phase 5 and then silently broken. Phase 2 adds a `touch`
method to avoid it.

## Verifier open items — all resolved

Every item the verifier carried over from a non-winning candidate was folded into the
phase files during validation, on the user's instruction.

| # | Item | Resolution | Where |
|---|------|-----------|-------|
| 1 | Polling quote adapter emitted a cumulative bar total as `volume`, which `add_tick` treats as a per-tick increment and would inflate accumulated volume on every poll inside one minute. | Folded in — the adapter now tracks the previous `(datetime, volume)` per symbol and emits a delta within the same bar, the full volume on a bar roll, clamping negatives to `0.0`. | Phase 6, Task 5 step 4 |
| 2 | The Phase 1 same-commit constraint was verified by inspection. | Folded in — `git show --stat HEAD --name-only` must list all three files, with a `git reset --soft HEAD~1` recovery instruction and a hard stop before Task 7. | Phase 1, Task 6 |
| 3 | `_can_afford` design fork under futures multipliers. | **Resolved by user decision: keep the unmultiplied check.** See the validation log below — the premise was partly wrong, and the plan already says to keep it. No edit needed. | Phase 6, Task 3 step 3 |
| 4 | `pandas_market_calendars` containment was a grep inside one phase gate. | Folded in — a real ninth import-linter contract, enforced on every `lint-imports` run. | Phase 2, Task 8 |
| 5 | The `tvdatafeed` git dependency was unpinned. | Folded in — resolve the sha with `git ls-remote`, pin `@<SHA>`, record the resolution date, and STOP rather than falling back to an unpinned ref. | Phase 5, Task 1 |
| 6 | `calendar_id` and `asset_class` were seeded independently and could disagree. | Folded in — `Symbol.create` derives `calendar_id` from `asset_class` via `_DEFAULT_CALENDAR_FOR`, with an explicit argument still winning, plus a test. | Phase 2, Task 3 step 2 |

## Validation log

### Session 1 — 2026-09-21

**Verification pass (mechanical, before the interview).**

- Plan format: `ak plan validate` exits 0.
- Path sweep: 125 unique repository paths cited across the seven phase files. 86 exist
  on disk and were confirmed present; the other 39 are each introduced explicitly as
  `New file`, `New package`, `New directory` or `New fixture file`. Zero phantom
  modify-targets, zero create-targets that would overwrite an existing file.
- Claims spot-checked and CONFIRMED: `ruff check .` exits non-zero with 301 errors
  while `ruff check src tests scripts` prints `All checks passed!`; `tzdata` carries
  marker `sys_platform == 'emscripten' or sys_platform == 'win32'` in `uv.lock`;
  `deploy/Dockerfile` runtime stage installs only `curl`; `app/routes/integrity.py:33`
  and `:45` call the two integrity functions; `pyproject.toml` holds exactly 8
  import-linter contracts with `include_external_packages = true`.
- Claims spot-checked and CORRECTED: see decision 1 below.
- Failures: 0.

**Decisions.**

1. **`_can_afford` — keep the unmultiplied check (user decision).** The verifier
   framed this as a wedge risk. On inspection that premise is partly wrong:
   `paper_broker_adapter.py:487-497` already exempts a BUY that covers an existing
   SHORT, a guard added by plan `260628-2013`, so no position can wedge. The real
   question was only what affordability means for an opening long, where the check is
   `fill_price * quantity + commission <= balance` against a default balance of
   10,000. The user chose to keep it unmultiplied, which is what the winning plan
   already specifies. **Consequence, recorded deliberately:** for futures the number
   compared is neither notional nor initial margin, so affordability is not a
   meaningful constraint for contract instruments — G2's 2-contract ES scenario passes
   at 4,500 (9,000 against 10,000) by arithmetic coincidence, not because the position
   is affordable in reality. Modelling real initial margin was offered and declined;
   it remains available later as an `initial_margin_per_contract` field on
   `ContractSpec`.
2. **All six verifier open items folded in (user decision).** See the table above.
3. **Phase 1 ships alone, to production, before Phase 2 (user decision).** Added as
   Phase 1 Task 14, using the real procedure from `docs/deployment.md`: commit on
   `develop`, `git push origin develop` (which is itself the entire deploy), watch the
   Actions run with `gh run watch --exit-status`, then confirm container health and
   that `ZoneInfo('America/Chicago')` resolves inside the deployed image. Credentials
   are read from `../pocketquant-config/` at use time and never enter this repo.

**Noted deviation, not blocking.** Phase 1 Task 1 step 2 adds an `environment:` block
with `TZ: "UTC"` to `deploy/compose.prod.yml`. `docs/deployment.md` states that `app`
consumes `.env` via `env_file:` with "no `environment:` block to keep in sync", so this
is a deliberate departure from a documented convention. It is justified — `TZ` must not
be overridable by a stray key in the config repo's `.env` — and it is safe either way,
because the Dockerfile `ENV TZ=UTC` already sets the default and the startup assertion
fails fast if the process is not on UTC. The executor should keep the block but not
generalize it into a habit of adding `environment:` entries.

4. **Pyright gate rescoped (found by running the baseline, same defect class as
   correction 1).** `uv run pyright` exits non-zero today with 21 errors, all in
   `tests/` (12 in `tests/scripts/rubric/test_reconciliation.py`, the rest spread
   across five other test files); `pyright src` reports `0 errors`. The command
   appeared in Phase 7's chained gate and in the Phase 3 verify step added as
   correction 3, so both would have stopped an executor on pre-existing debt. All
   seven mentions across five phase files are now `pyright src`, which still catches
   what correction 3 needs — a caller in `src/` left on an old signature.

**Measured baseline — 2026-09-21, before any phase runs.** These are the numbers the
phase gates compare against:

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `668 passed, 1 skipped` in ~10s |
| `uv run lint-imports` | `Contracts: 8 kept, 0 broken` |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run pyright src` | `0 errors, 0 warnings` |
| `uv run ruff check .` | 301 errors (pre-existing, not gated) |
| `uv run pyright` | 21 errors, all in `tests/` (pre-existing, not gated) |

**CI gates on less than the plan does.** `.github/workflows/cicd.yml` runs only
`uv run lint-imports` and `uv run pytest tests/ -q`. Neither ruff nor pyright runs in
CI, which is how 301 ruff and 21 pyright findings accumulated without breaking a
deploy. The plan's gates are therefore stricter than the pipeline's; that is
deliberate, but it means a phase can be green in CI and still fail its own gate.

**Whole-plan consistency sweep.** Re-read `plan.md` and all seven phase files after
propagation. The contract count is consistent (8 today, 9 from Phase 2, with Phase 7's
docs task updating `CLAUDE.md`). No phase still references a bare `ruff check .`. The
`volume` semantics in Phase 6 no longer contradict the `add_tick` contract. No
unresolved contradictions remain.

### Session 2 — 2026-09-21 (execution, Phase 1)

**Correction 5 — `Asia/Saigon` is an unresolvable zone alias.** Found while verifying
Phase 1 Task 3's success criterion that the tests must fail if `timezone=UTC` is
removed. `Asia/Saigon` is a deprecated backward-compatibility link, and Debian/Ubuntu
moved those links out of the main `tzdata` package into `tzdata-legacy` from tzdata
2024b onward. Probed on the dev host (`tzdata 2026c-0ubuntu0.24.04.1`,
`/usr/share/zoneinfo` present, 498 zones): `UTC`, `Etc/UTC`, `America/Chicago`,
`America/New_York` and `Asia/Ho_Chi_Minh` all resolve; `Asia/Saigon` and `US/Central`
raise `ZoneInfoNotFoundError`. The GitHub `ubuntu-24.04` runner image carries the same
`tzdata` build with no `tzdata-legacy`, so CI behaved identically.

The failure mode was silent, not loud. With `TZ=Asia/Saigon`, glibc falls back to UTC
(`time.timezone == 0`), so Task 12's matrix and Task 13's gate would have run the
entire suite a second time in UTC and reported green while proving nothing. Only code
paths reaching `zoneinfo`/`tzlocal` raise.

All 11 sites now read `Asia/Ho_Chi_Minh` (`plan.md` success criteria; phase-01 Tasks
3, 4, 5, 12, 13; phase-02 Task 8 Verify; phase-07 Tasks 5 and 7). `America/Chicago`
stays as the third zone — fixed +07 ahead of UTC plus a DST zone behind UTC covers
offset sign, magnitude and DST-ness, which is the whole space a cron-zone leak can
occupy. This is a factual fix to a broken command, the same class as corrections 1, 2
and 4; the accepted criterion was host-zone invariance, and the zone name was only its
instrument.

Two loud-failure guards were added so this cannot recur silently:
- Task 3's helper asserts `time.timezone != 0` for each non-UTC zone before building
  the trigger, so an unresolvable zone fails the test instead of vacuously passing it.
- Task 12's `test-tz` recipe and CI matrix gain the same resolve check per non-UTC leg.

Note this is a different defect from correction 2. That one is the `python:slim` base
image shipping no zone data at all; the Task 1 apt `tzdata` install remains necessary
and unchanged, and `America/Chicago` — the zone Phase 2 actually depends on — was never
at risk.

Provenance: the alias entered from the datetime audit
(`plans/reports/kongming-260921-2106-datetime-timezone-audit.md`, lines 121, 163, 167)
and the plan inherited it.

**Open decision carried to the user.** `.github/workflows/cicd.yml` runs on
`ubuntu-latest`, which migrates to Ubuntu 26.04 between 2026-10-19 and 2026-11-19 —
an image whose `tzdata` packaging nobody has probed. Pinning `runs-on: ubuntu-24.04`
would freeze the matrix on a known-good image. Left unpinned for now because it is
outside the accepted scope of Task 12, and the resolve-check guard makes the migration
fail loudly rather than silently.

**Correction 6 — Task 6 breaks what Task 11 cures.** Task 6's Verify step passed
(29 passed), but its success criterion "the full suite still passes" was red: making
the Mongo client `tz_aware=True` broke four repository roundtrip tests whose expected
fixtures were naive. Stashing Task 6 returned the suite to 674 passing and clean, so
the change caused exactly those four and nothing else.

Each failing file held one naive `datetime(2026, 1, 5, 10, 0, 0)` module constant, and
each was a 1:1 match with a DTZ001 finding that **Task 11 step 4** schedules for a
`tzinfo=UTC` fix. The plan therefore cured in Task 11 what it broke in Task 6, five
tasks earlier. The four fixture fixes were pulled forward into Task 6's commit rather
than deferred: the single-commit constraint exists so no revision has `tz_aware=True`
without its companion fix, and a revision whose suite fails four tests is red in
exactly the way Task 14 step 1 forbids. Their stale `# Mongo strips tz info on
roundtrip` comments were replaced, since that sentence is what Task 6 falsifies.

The write path was checked before the tests were touched, to be sure `tz_aware=True`
was not exposing a repository that genuinely persists naive datetimes. `Trade`,
`OrderRecord`, `BacktestResult` and `OpenLot` all pass datetimes through unchanged in
both directions, and every production producer supplies aware UTC — the backtest
report service derives from broker events, which derive from `Bar.datetime`, aware on
both the Mongo path (`coerce_utc` in `from_mongo`) and the Binance path
(`fromtimestamp(..., tz=UTC)`). These were stale fixtures, not a defect.

**Consequences for Task 11.** Its step 4 list loses these four files, so the
tests/scripts count falls from 31 to 27, and step 3's "3 findings in `src/`" is already
2 (`backtest_strategy_loader.py:37` and `cascade_aggregator.py:81`) because Task 6
removed the `bar_builder_domain_service.py` one.

**Correction 7 — Task 7 carries unstated wire-format changes.** Task 7's Verify was
red on four assertions. Two were cosmetic (`+00:00` → `Z`), but two were a precision
loss the plan never states: `to_utc_iso` formats `"%Y-%m-%dT%H:%M:%SZ"`, whole seconds,
whereas the `_iso_z` it replaces preserved microseconds. Step 7 therefore drops
sub-second precision from `last_sync_at` and `last_bar_at` on the sync-status endpoint.

Verified before accepting it. `docs/code-standards.md:777-783` already mandates
`to_utc_iso()` for frontend JSON and shows the whole-second `Z` output, so Task 7
aligns the code with the documented contract rather than inventing one. BSON stores
milliseconds — encoding `…54.190179Z` and decoding it returns `…54.190000Z` — so the
fixtures asserted a precision Mongo cannot store; `last_bar_at` is a bar boundary and
always whole minutes. Every SPA reader renders at minute granularity or compares ages
against interval multiples, and nothing sorts or compares these strings. The four
assertions were updated to call `to_utc_iso` directly, and the sync-status `NOW`
fixture now truncates to whole seconds so it stops asserting fabricated precision.

Rejected alternatives: adding a `timespec` parameter, or widening `_UTC_FMT` globally.
Both trade a documented contract for a fixture, and the global change would alter
`scheduler.py`'s `next_run`, the job-history timestamps, OHLCV and `Bar.to_dict`.

**Other contract changes Task 7 carries, recorded for Phase 7.** Persisted
`config_snapshot.start_date`/`end_date` change shape from naive to trailing-`Z`; old
documents keep the old shape, so the collection is mixed, and every reader tolerates
both. `RunBacktestCommand` now anchors naive input to UTC. The OHLCV cache key text
changes, costing one cold miss per window after deploy, and naive and `Z` spellings of
the same instant now share a key. `Bar.datetime` stays `dt | None` despite the task
title — the plan's own validator keeps `None` legal.

**Deferred, proposed as a Phase 7 task.** Roughly twenty further JSON `.isoformat()`
emitters remain (`backtest_stats_service`, `strategy_query_service`, `routes/backtest`,
`tracked_symbols_service`, `quote_dto`, `quotes_service`, `bar_app_service`,
`main_extensions` among them). Task 7 scopes itself to five named sites, so folding in
an arbitrary four was declined. `backtest_stats_service._encode_cursor` must stay on
`isoformat()` — it is a pagination round-trip, not a display field.

**Correction 8 — production had no rollback image, and the weekly data needed repair.**
Two findings from the pre-deploy review of Task 14, neither anticipated by the plan.

*No rollback was possible.* Docker Hub held only March `sha-` tags plus a July `latest`,
and the VPS held the running build solely as an untagged `latest` that the deploy
overwrites and then prunes. Root cause verified against the live API: Docker Hub's
`ordering` parameter reads backwards — `ordering=-last_updated` returns OLDEST first, so
pairing it with `tail -n +8` in `cleanup-tags` kept the seven oldest tags and deleted
every newer one. Before pushing, both running images were tagged `pre-utc-20260922` on
the VPS (a tagged image is not dangling, so `docker image prune -f` leaves it), and the
ordering was fixed in commit `e5ab3bb`. That commit also pins the `tests` job to
`ubuntu-24.04`, since the timezone matrix depends on which zones the runner image ships
and `ubuntu-latest` moves to 26.04 during October and November — which resolves the open
runner-pin question recorded under Correction 5.

*Task 8 stops new partial weekly bars but repairs none of the existing ones.* Every
stored `1w` bar was a mid-week 03:00 UTC snapshot, never updated, because the regular
sync is insert-only and the repair job's gap scan finds no gap for a bar that exists.
Measured before repair, week of 2026-09-14: BTC stored `close 76390.01 / vol 53593`
against Binance's `81178.00 / 108474`; ETH `2430` against `2645.21`; SOL `99.42` against
`111.17`. Prior closed weeks were wrong too. After the deploy verified, all three symbols
were resynced with `skip_filter=true` (1269 documents backed up first via `mongodump`),
and every value now matches Binance.

**G5 is deliberately violated by this repair.** The goal says BTC/ETH/SOL bar values are
unchanged; the weekly values changed because they were wrong. This is the correction
landing, not a regression. Intraday intervals are untouched.

### Session 3 — 2026-09-22 (execution, Phase 2)

**Correction 9 — the promised ninth import contract had no owning task.** `plan.md`'s
success criteria state "9 from Phase 2 onward (the new contract confines
`pandas_market_calendars` to `core/infra`)", and the verifier open-items table records
item 4 as folded into "Phase 2, Task 8". Task 8 creates the `TradingCalendarFactory` and
contains no contract step, so no task would have created it and the plan's own criterion
could not have been met. Added alongside Task 6, where the library first enters.

It needed `allow_indirect_imports = true`. Written as a plain forbidden contract it
broke immediately on `app.di.infrastructure -> trading_calendar_factory ->
cme_globex_calendar_adapter -> pandas_market_calendars`, which is DI wiring doing its
job, not a violation. Restricting it to direct imports expresses the real rule — nothing
outside `core.infra.calendars` may import the library to compute a schedule itself — and
will not fight Phase 3 when engine services start receiving calendars. Verified by
mutation: a direct `import pandas_market_calendars` in `core.domain` breaks it.

**Correction 10 — Task 7's expected count is arithmetically impossible.** Its Verify
expects `14 passed`, while its own steps prescribe 6 + 8 test functions with two of them
parametrized over all 7 intervals. That yields 14 functions and 28 cases. Delivered as
specified: 14 functions, 28 cases, green under a non-UTC host.

**Environment note, no action needed.** `pandas-market-calendars` pulls in the pip
`tzdata` package, so `Asia/Saigon` now resolves inside the venv where it previously
raised. This does not weaken Correction 5's guards: both the test helper and the CI
matrix key on `time.timezone`, which is glibc's view, and glibc still cannot resolve the
alias (`time.timezone == 0`, `tzname == ('Asia','Asia')`). The canonical zone remains
the right choice because it works with or without the pip package.

**Flake observed once.** One unidentified test failed in a single full-suite run and did
not reproduce across four subsequent runs, including the chained gate. Same class as the
job-history tie recorded in the Phase 1 report; noted rather than chased.

### Session 4 — 2026-09-22 (execution, Phase 3)

**Correction 11 — two Verify greps count definitions as call sites.** Task 2's
`grep ... | grep -vc "calendar"` prints `4` and Task 4's prints `4` on fully correct
code. Both matches are `def`/`async def` lines and wrapped call sites: ruff's
`line-length = 100` forces `filter_aligned_bars` (124 chars on one line) and
`drop_misaligned_bars` (110) onto two lines, and a line-based grep cannot see an
argument on the continuation. Satisfying the grep literally would mean violating the
project's own line length.

Both Verify steps now read `uv run pyright src` instead, which is what actually
enforces the stated criterion — every caller passes a calendar — across all of `src/`,
and which Task 4's own Verify already used for exactly this purpose. Same defect class
as corrections 1 and 4: a gate command that cannot pass on correct code.

**Correction 12 — the CME annualization band assumed the wrong exchange.** Task 10
asserts `periods_per_year(DAY_1)` between 245 and 255, citing "23h x 252 sessions".
Measured: the adapter returns `259.0`. Verified against `pandas_market_calendars`
directly — `CME Globex Equity` has 259 sessions in 2025, which is 261 weekdays less
the only two full closures, 2025-01-01 and 2025-12-25. Globex equity futures do not
skip US holidays; they close early, which shows up as 11 sessions shorter than 20h
(seven at 19:00, three at 19:15, Good Friday at 15:15) rather than as absent days. For
comparison `NYSE` has 250 sessions in the same year, which is where 245-255 comes from.
The band is an equity-cash assumption applied to a near-24x5 electronic calendar.

The adapter is correct and unchanged; the assertion was rewritten. Both CME assertions
are now exact equalities (`259.0` and `5910.0`) rather than ranges. The adapter
measures over a fixed 2025 reference window specifically so a re-run reports the same
Sharpe, and 2025 is a closed year whose holiday set cannot change, so an exact value is
the honest assertion. The original bands asserted almost nothing: 5000-6200 accepts
5957 (early closes ignored) and 5796 (a 252-session basis) as readily as the true 5910.
Confirmed by mutation — drifting the reference window to 2024, and falling back to the
24/7 interval table, each fail both assertions.

**Correction 13 — Task 9 step 2 routes a session count into CAGR, which is wrong.**
The step prescribes giving `cagr` a `days_per_year` argument fed from
`calendar.periods_per_year(Interval.DAY_1)`. But `build` computes `days` as
`(end_date - start_date).days` — wall-clock calendar days. Dividing those by 259
stretches one real year into 1.41 years, so a CME strategy that doubles its capital
over a calendar year reports CAGR `0.635` instead of `1.0`, understating it by 36.5%.
CAGR is compound *annual* growth: the numerator is calendar time, so the denominator
must be too, for every instrument.

Sharpe and Sortino are the opposite case and keep the calendar's `periods_per_year`;
they count return observations, not elapsed time. `cagr` was left reading the 365-day
module constant and the parameter was not added at all, rather than added with a 365
default: a knob that must always hold one value to stay correct is an invitation to
set it. A regression test pins that a doubling over 365 calendar days is CAGR 1.0.

Crypto cannot detect this — 365/365 is the identity — so the golden files and Task 11's
byte-identical gate would both have passed over a wrong futures CAGR indefinitely.
Found by advisory review of the Correction 12 failure, not by a test.

**Every Phase 3 behaviour was mutation-tested, and most were initially unguarded.**
Running the phase's own Verify steps passed while proving little: with only the 24/7
calendar registered, `is_bar_aligned` could ignore its calendar argument entirely and
all 712 tests still passed. The same was true of the cascade's non-advancing-step
guard, its calendar-derived expected-bar count, the `calendar_id`/`session_date`
stamping on both the cascade and sync write paths, the integrity grid and its weekly
short-circuit, session-aware staleness, the closed-market no-progress silence, the
`is_market_open` DTO field, the closed-market sync skip and its grace window,
`cascade_tfs`, and the report service's annualization source — fourteen behaviours, all
of which passed their prescribed Verify while being undetectable under mutation.

Each now has a test that fails when the behaviour is removed, verified by actually
removing it. The suite went from 709 to 751 passing. The pattern is the same one
Phase 1 recorded: on a refactor whose acceptance is "nothing changed", the tests that
prove the new thing works cannot be the tests that proved the old thing worked.

One guard needed care beyond an assertion. `compute_boundaries`' non-advancing fallback,
when removed, makes the loop spin forever, so a naive test hangs CI instead of failing
it. The test drives the call on a daemon thread with a five-second deadline, which turns
that into a red test in 13 seconds and lets the rest of the suite finish.

**Job-history flake seen again.** `test_get_latest_by_job_ids_awaits_aggregate` failed
once more in a full-suite run and passed on re-run, the third sighting. Still the
same-millisecond `$sort`/`$first` tie with no secondary key at
`job_history_repository.py:193-197`. Still not this phase's business, but it is now a
recurring rather than an isolated observation.
