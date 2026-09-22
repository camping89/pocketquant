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
  contract confines `pandas_market_calendars` to `core/infra`), and 10 from Phase 5
  onward (the tenth confines `tvDatafeed` to `core/infra/tradingview`).
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
accounting shipped in plan `260628-2013`.

~~Any branching on the TradingView plan tier.~~ **Reversed by user decision,
2026-09-22** — see Session 5 below. The free plan must work untouched and a paid
plan must light up without a rewrite, which needs the tier represented somewhere.
What survives of the original non-goal is that nothing below `Settings` branches on
the plan's name.

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

### Session 5 — 2026-09-22 (execution, Phase 4)

**Correction 14 — three more gates that cannot pass on correct code, and the real
defect one of them was hiding.** Same class as corrections 1, 4 and 11, with one
difference that matters: this time the broken gate was not merely useless, it was
concealing a genuine type error.

*Task 5's Verify calls `issubclass` on a Protocol that forbids it.*
`IRealtimeQuoteProviderPort` has three non-method members (`last_tick_at`,
`subscription_count`, `subscriptions`), and CPython raises
`TypeError: Protocols with non-method members don't support issubclass()` for any
class at all. The shipped `BinanceWebSocketAdapter` fails the same call identically,
which is the proof the gate was never measuring the adapter. Task 5's own **Success
criteria** line names `isinstance`, which does pass; only the Verify command was
wrong.

*What it was hiding.* Task 5 step 9 asserts that "a read-only property satisfies
structural typing". That is true of runtime `isinstance`, which only checks that an
attribute exists, and false of static typing. With the `# type: ignore` comments
removed from `app/di/market_data.py`, pyright reports
`"last_tick_at" is invariant because it is mutable / Type "property" is not
assignable to type "datetime | None"`. The port declared `last_tick_at` as a mutable
attribute, the routing adapter derives it as a read-only property, and those are
genuinely incompatible. `uv run pyright src` was green only because Task 7 step 2
said to keep the existing `# type: ignore` style, and pyright treats any
`# type: ignore[...]` as a blanket suppression of the line — so the single place
where the adapter meets the port type was unchecked.

Fixed by declaring `last_tick_at` as a read-only property **on the port**, not by
giving the adapter a setter. Every write in the codebase is a provider assigning its
own attribute (`binance_websocket_adapter.py:55,116,197`); no consumer in `app/` or
`engine/` reads or writes it through the port at all. A port should declare the
weakest contract its consumers need, and a mutable declaration would forbid any
provider that derives the value instead of storing it. Both `# type: ignore`
comments were removed, which is a deliberate deviation from Task 7 step 2.

This is a domain-port edit outside Task 5's listed target files, recorded as a
deviation in the same spirit as Correction 6's pulled-forward fixture fixes.

*Task 7's Verify grep counts a class definition and two docstrings.* The pattern
`BinanceAdapter(` matches `class BinanceAdapter(IDataProviderPort):` at
`binance_adapter.py:34`, and the "Usage:" examples at `binance_adapter.py:38` and
`binance_websocket_adapter.py:44`. It returns 2 on fully correct code and always
would have. Replaced with a grep that excludes the DI package and the adapters' own
package, which returns 0 today and returns 1 when a construction is planted in
`engine/` — verified by planting one.

*Task 8 step 3's URL does not exist.* It gives
`/api/v1/market-data/quotes/BTCUSDT%3ABINANCE`, which returns
`{"detail":"Not Found"}`. The quotes router mounts at `/quotes` with a `/latest/`
path, so the live check is `/api/v1/quotes/latest/BTCUSDT%3ABINANCE`. A manual
verification rather than an automated gate, so it costs minutes rather than blocking.

*Two expected test counts are wrong, in the harmless direction.* Task 3 says
`4 passed` and Task 6 says `10 passed`; the delivered counts are 5 and 20. Both
numbers are now the delivered ones. Task 3's extra test pins Task 2 step 2's "return
a NEW list" requirement, which none of its four named tests covers.

**The routing layer's own gate proves nothing, exactly as Phase 3 predicted.** With
Binance as the only registered provider, every fallback branch is unreachable in
production and each one passed its Verify while being removable. The whole of Task 4
and Task 5 was therefore mutation-tested against fake children: returning the
primary's empty answer instead of falling through, ending the walk on an unregistered
id, dropping either warning, warning more than once, replacing `asyncio.gather` with
sequential awaits, and swallowing `CancelledError` were each confirmed to turn a test
red by actually making the change.

**The nested-loop risk is now pinned rather than warned about.**
`tests/app_test/unit/market_data/test_closed_market_skip_precedes_provider_loops.py` wires
the real chain — `_sync_by_intervals` to `SyncService.sync_one` to `fetch_with_retry`
to `RoutingDataProviderAdapter` to fake children — and asserts on the children rather
than on `sync_one`, which is what the existing calendar-gate suite mocks. A shut
market reaches zero providers; deleting Phase 3's skip turns that red. An open market
whose providers are all empty costs exactly `attempts x providers` calls, recorded as
an exact number so Phase 5 reads the real price of a second provider instead of
rediscovering it. The loops compose; neither short-circuits the other.

**The unseeded-symbol default is now explicit rather than implicit.** Task 4 step 2's
"use `AssetClass.CRYPTO_SPOT` when the symbol record is missing" is an ordering
invariant in disguise, and the failure is worse than it looks. `_persist_bars`
returns early when no bars arrive, so `SymbolRepository.touch` is never reached; a
futures symbol tracked before it is seeded routes to a crypto venue, gets nothing
back, never gets a document written, and repeats forever — with `SymbolLookupHelper`
caching the miss for 60s in between. The assumption now lives in one named constant,
`UNSEEDED_SYMBOL_ASSET_CLASS` in `core/infra/market_data/symbol_provider_resolver.py`,
shared by both routing adapters, and emits a one-shot WARNING naming the symbol and
the class it assumed. One-shot because this is a per-minute path, and because the
ongoing alarm is already `emit_no_progress`'s job; this line only names the cause.

**Task 1 carries an unstated footgun.** pydantic-settings does parse
`dict[AssetClass, list[str]]` from a JSON environment string with no custom parser,
as the task claims — but the assignment REPLACES the whole mapping rather than
merging into it, so `MARKET_DATA_PROVIDERS={"index_future":[...]}` leaves crypto with
no provider and the sync silently fetches nothing. Documented on the field, in
`README.md` and in `docs/system-architecture.md`, and made audible by a second
one-shot WARNING when resolution yields an empty provider list.

**Two follow-ups from Phase 3 folded in at the user's request.**

- `cascade.partial_aggregate` now logs at DEBUG for a bucket that has not closed yet
  and stays at WARNING for one that has. An open bucket is short because it is still
  filling, which is arithmetic; a closed bucket that is short has really lost bars.
  This removes roughly 14 WARNING lines a minute at three symbols. Both directions
  are mutation-tested: always-WARNING, always-DEBUG, and pinning `in_progress` to
  either constant each turn one of the two tests red.
- `JobHistoryRepository.get_latest_by_job_ids` sorts on `("started_at", "_id")`
  instead of `started_at` alone. BSON stores milliseconds, so two runs of a fast job
  can tie and `$first` was free to return either; `_id` is a UUIDv7 string, monotonic
  within a millisecond and lexicographically ordered by generation time, so
  descending on it resolves the tie to the later run. Verified that Python 3.14's
  `uuid7()` is monotonic within a millisecond before relying on it.
  `get_last_completed_start` has the same untied sort and needs no fix: it projects
  only `started_at`, so both sides of a tie return the same value.

  The first version of that test passed with the fix removed, five times out of five.
  It inserted the rows newest-first, so natural order already agreed with the right
  answer and the assertion proved nothing. Inserting oldest-first makes the mutation
  fail five out of five. Worth recording because it is the phase's own lesson in
  miniature: a test written against a fix is not automatically a test of the fix.

**Measured at Phase 4 close.**

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `782 passed, 1 skipped` (baseline 751) |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 9 kept, 0 broken` |
| `uv run pyright src` | `0 errors` — and now actually checking the port binding |
| `just test-tz` | `782 passed` under all three zones |
| `cd web && npx tsc --noEmit` | exit 0 |

**Correction 15 — Task 4 step 2 downgrades an outage to a successful sync, which
violates G5.** Found by the post-phase advisory review, after Phase 4 had already
deployed, and confirmed by running the two paths side by side.

The step prescribes catching a provider exception, logging it at DEBUG and continuing
to the next provider, returning `[]` when none is left. Before routing existed a
`BinanceAdapter` exception — it raises on 429 and on `raise_for_status` — travelled
through `fetch_with_retry`, which has no `try`, into `SyncService.sync_one`'s handler:
`market_data.sync.failed` at ERROR, the symbol's sync status set to `error`, and
`error_count` incremented on the job. After Phase 4 the same failure was invisible at
production `LOG_LEVEL=INFO` and reported `status=completed` with no progress.

Measured on the same simulated 429, before and after the fix:

| | status | log | provider calls |
|---|---|---|---|
| Pre-Phase-4 direct provider | `error` | `market_data.sync.failed` ERROR | 1 |
| Phase 4 as shipped | `completed` | none above DEBUG | 3 |
| After this correction | `error` | `market_data.sync.failed` ERROR | 1 |

The call count is the second half of the defect. `fetch_with_retry` retries on an empty
answer, and a swallowed exception is indistinguishable from one, so every provider
failure was retried three times inside a 15s budget. Against an unofficial scraper in
Phase 5 that is three fresh connections per symbol per minute for as long as the ban
lasts — the precise cost the closed-market containment test was written to bound,
arriving through the other branch.

`fetch_ohlcv` now keeps the first exception and re-raises it if no provider returned
bars. An empty answer from every provider still returns `[]`, because that is a quiet
market rather than a broken one, and a provider that answers still hides an earlier
one's failure, because that is what a fallback is for. With one registered provider the
behaviour is exactly pre-Phase-4.

`test_all_providers_exhausted_returns_empty_list` pinned the wrong behaviour and was
replaced by three tests that separate the cases. Both directions are mutation-tested:
restoring the swallow, and raising even when a provider answered, each turn two tests
red.

**Correction 16 — `Settings` declared the two routing fields twice.** Lines 71-78 and
82-87 held identical values, so Python kept the last and behaviour was unaffected, but
the surviving block was the one WITHOUT the comment recording that
`MARKET_DATA_PROVIDERS` replaces rather than merges. Two writers edited `core/config.py`
in the same session and the file was staged without being re-read. The duplicate is
removed. The example in that comment also named `binance` as an `index_future`
fallback, a venue that cannot serve one; it now shows a two-class override instead.

**Measured after corrections 15 and 16.**

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `785 passed, 1 skipped` |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 9 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| `just test-tz` | `785 passed` under all three zones |

**Carried to Phase 5 by the same review, verified against the adapter and not yet
fixed.** Both fire on the first futures symbol in production, and neither is Phase 4
code:

- `CmeGlobexCalendarAdapter.bar_start` and `session_date` raise `KeyError` from Friday
  16:00 CT until Sunday 00:00 UTC, because `_window_rows` looks only one calendar day
  either side and Saturday's window contains no session. The cascade loop in `sync_1m`
  has no closed-market gate, so once ES/NQ/YM are tracked this is a `cascade_failed`
  ERROR per symbol per minute for roughly 27 hours every weekend. Existing tests only
  call `is_open` on a weekend, never `bar_start`.
- The daily 15:15-15:30 CT equity-index halt is not modelled — upstream
  `CMEGlobexEquitiesExchangeCalendar` carries no break, so `is_open` is True at 15:20
  CT. Every weekday that produces `no_progress`, then `stuck_threshold_crossed`, plus
  `partial_aggregate` on the closed hourly bucket and 15 missing minutes per symbol per
  day in the nightly integrity scan. That fails this plan's own success criterion
  ("zero `no_progress`, `stuck_threshold_crossed` or `partial_aggregate` for
  `ES1!:CME_MINI` across one full week") on day one. Confirm the halt against CME's
  contract specs before modelling it.


**User decision, 2026-09-22 — the TradingView entitlement is deferred, so both paths
must be supported.** No data add-on is being bought now. The requirement is that the
free plan works with no configuration, that buying the ~$10/month CME non-professional
add-on later is a configuration change rather than a code change, and that the design
extends to a further plan without a rewrite.

Phase 5 Task 1 originally carried three independent settings — `tradingview_max_bars`,
`tradingview_poll_seconds` and `tradingview_delayed_data`. They are not independent:
each is a consequence of the plan the account holds, and setting them separately lets
an operator express states that cannot exist, such as real-time data on a free account
or a five-second poll against a feed delayed ten minutes, which is ban risk for no
benefit. They are now derived from one `tradingview_plan` setting through a
`TradingViewCapabilities` record, with explicit per-field overrides still winning —
the same shape Phase 2 Task 3 used to derive `calendar_id` from `asset_class`.

This reverses the "no branching on the TradingView plan tier" non-goal. The part of
that non-goal worth keeping is kept: no consumer below `Settings` branches on a plan
name, they ask the capability record what they may do. Adding a plan is one map entry;
adding a capability is one field.

Phase 6 Task 5 and Task 7 must read `capabilities.min_poll_seconds` as a floor —
`max(configured, floor)` — rather than reading `tradingview_poll_seconds` directly, so
a paid plan can poll faster while no plan polls below its own safe limit. Phase 7's UI
surfaces `capabilities.realtime` rather than the old `tradingview_delayed_data` flag.

### Session 6 — 2026-09-22 (pre-Phase-5 calendar fixes)

Both issues the post-Phase-4 review raised were reproduced directly against the adapter
before being fixed, and both are fixed and deployed.

**The session-lookup window was shorter than the gap it had to clear.** `_window_rows`
reached one day either side of the instant. Between Friday's 16:00 Chicago close and
Sunday's evening open there is no session at all, so a Saturday instant found none
ahead of it and a Sunday-morning instant none behind, and the lookup raised `KeyError`.

Three callers sit on that gap, and the worst one was not the one first reported.
`bar_start` and `session_date` would have failed per symbol per minute all weekend,
which is noisy but contained. `previous_close` also raised, and the sync job evaluates
it for every symbol at `sync_jobs.py:186` — *before* the per-symbol `try` that begins
at line 214. One tracked futures symbol would therefore have aborted the whole
`_sync_by_intervals` loop every Sunday morning, stopping BTC, ETH and SOL as well.

The window is now four days either side, which clears a weekend plus an adjacent
holiday. Widening is safe for every caller because each filters on the session
boundaries themselves, so an extra row ahead of the instant can neither contain it nor
precede it. A guard walks every hour of a full weekend and asserts that the sync gate's
own expression, `bar_start`, and `session_date` all resolve. Mutation-tested at one day
(3 tests fail) and at two days (1 still fails), so the width is load-bearing rather
than arbitrary.

**The daily equity-index halt was not modelled.** ES, NQ and YM pause 15:15-15:30
Chicago, just after the cash equity close, on top of the 16:00-17:00 maintenance break.
Confirmed against CME's published contract hours before implementing, because modelling
a halt that does not exist would skip real bars — and the halt is specific to the index
products, where CME's crude and gold contracts run straight through that window.

Left unmodelled it would have produced, every weekday and for each of the three
symbols, a no-progress streak crossing its threshold, a partial hourly bucket, and
fifteen missing minutes in the nightly integrity scan with the repair job re-fetching
gaps that were never gaps. That is the direct opposite of this plan's own success
criterion of a clean live week for `ES1!:CME_MINI`.

The halt is clipped to each session's boundaries, so an early close landing before it
leaves that session with a shortened halt or none. It is stored as a local wall-clock
time and converted per session, never as an offset — 15:15 Chicago is 20:15 UTC in
summer and 21:15 in winter, and the fixed-offset mutation is one of the four that turn
a test red.

**`periods_per_year(HOUR_1)` moves from 5910.0 to 5848.0.** Correction 12 pinned 5910
as an exact equality on the reasoning that a closed reference year cannot change. That
reasoning still holds; what changed is the model, not the year. The 62-hour difference
is not a clean 259 x 15 minutes because early closes shorten or remove the halt.
`periods_per_year(DAY_1)` is unchanged at 259.0.

**Measured after the calendar fixes.**

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `792 passed, 1 skipped` |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 9 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| `just test-tz` | `792 passed` under all three zones |

Deployed as `dffe5ed`, Actions run `35742858417` green, three post-deploy `sync_1m`
cycles at `synced_count=3, error_count=0` and zero errors of any kind. Production
behaviour is unchanged today by construction: every tracked symbol is on the 24/7
calendar, so none of this code runs until a futures symbol is seeded in Phase 5.

### Session 7 — 2026-09-22/23 (execution, Phase 5)

Tasks 1-11 are delivered in code. Task 12 is a week-long observation gate and is open
by construction. Every [UNVERIFIED] item was checked against the installed package
rather than reasoned about, and three of the checks contradicted the phase text.

**The two items the plan said to verify in place, verified.** `tvDatafeed.Interval`
carries all seven member names the phase assumed (`in_1_minute`, `in_5_minute`,
`in_15_minute`, `in_1_hour`, `in_4_hour`, `in_daily`, `in_weekly`), plus six the domain
has no equivalent for. `pandas_market_calendars.get_calendar("CME Globex Equity")`
resolves to `CMEGlobexEquitiesExchangeCalendar` with 259 sessions in 2025, which is
Correction 12's number reproduced independently.

**Correction 17 — `uv sync` cannot install a git dependency until hatchling is told
to allow one, and that is not the failure Task 1 step 3 guards.** The step says to STOP
and follow the Failure Protocol if `uv sync` "fails to resolve the dependency". It
failed with `Dependency #19 ... cannot be a direct reference unless field
tool.hatch.metadata.allow-direct-references is set to true` — our own build backend
rejecting the metadata shape, before resolution was attempted, and independent of which
dependency it is. Adding the flag let the pinned sha resolve unchanged, which is the
evidence the guarded condition was never met. Recorded because the gate reads as
broader than the failure it is for, and a literal executor would have stopped here for
no reason.

The sha is `e6f6aaa7de439ac6e454d9b26d2760ded8dc4923`, resolved 2026-09-22.

**Correction 18 — three claims in Task 3 about the library are wrong, and the phase
text depends on all three.** Read off the installed package:

- *`tradingview_auth_token` is not a constructor argument.* `TvDatafeed.__init__` takes
  `username` and `password` only. The setting is kept and the token is assigned to
  `tv.token` after construction, where `get_hist` reads it — which also makes it the
  way past a broken login, the highest-likelihood risk in this phase's own table.
- *Step 2's "on any exception fall back to `TvDatafeed()`" is unreachable.* `__auth`
  catches every exception and returns `None`; `__init__` then substitutes the literal
  `"unauthorized_user_token"` and continues. Login never raises, so
  `is_authenticated()` compares the token value. A genuine construction exception is
  re-raised rather than degraded to anonymous mode, because Correction 15 established
  that an outage reported as an empty result becomes a successful sync that inserted
  nothing.
- *One instance cannot serve two callers.* `get_hist` calls `__create_connection`,
  which assigns `self.ws`, then reads `self.ws.recv()` in a loop; `chart_session` is
  fixed at construction and shared. Two concurrent calls overwrite each other's socket
  and share one chart session, so the loser reads the winner's series and ES bars are
  stored under NQ — corruption that passes alignment, deduplication and the integrity
  scan because every bar is individually well-formed. An `asyncio.Lock` serialises
  construction and every fetch. Removing it turns the re-entrancy test red.

**Correction 19 — Task 5's host-zone test asserts a property of the standard library,
not of our code.** `test_naive_local_datetime_recovers_the_same_epoch` builds
`datetime.fromtimestamp(epoch)` and asserts `naive.timestamp() == epoch`. That holds
for every non-ambiguous instant whatever the adapter does, so it cannot fail if the
epoch recovery is wrong — and Task 3's own Verify points at this module, so nothing in
the phase tested Task 3's code at all.

A client-level test now drives `TvDatafeedClient` against a DataFrame with a naive
index. Mutating the recovery to read that index as UTC keeps the suite green under
`TZ=UTC` and turns it red under `TZ=America/Chicago`. That pair is the clearest
evidence in this plan for why the timezone matrix exists: the bug is invisible on the
host the tests usually run on.

The fixture straddles the 2026-03-08 spring-forward deliberately. Spring forward skips
local times, so the naive round trip stays exact; the autumn fall-back is the ambiguous
direction, where it could be an hour out. That cannot bite here because the ambiguous
01:00-02:00 window falls on a Sunday morning while CME equity-index futures are shut,
and it is noted in the test so nobody "improves" the fixture into November.

**Correction 20 — Task 10's stated reason is wrong, and the real failure is worse.**
The step says cascading a futures daily bar would bucket it at UTC midnight and produce
a bar that never matches the vendor chart. Phase 3 already prevents that: `cascade_tfs`
omits `DAY_1` for a session calendar. The actual consequence is that a daily backfill in
cascade mode fetches and persists 1m bars, builds no daily bar at all, and still reports
success for work it did not do. The override is kept and is now audible when it
contradicts an explicit `mode="cascade"`, because honouring that request would be the
silent failure and overriding it without a word would be the other kind.

**Correction 21 — Task 11 step 6 cannot be followed as written, and step 1 is not the
cheapest way to satisfy steps 4-6.** `emit_no_progress` takes no instant; it reads
`datetime.now(UTC)` itself, so "run it with a closed instant" means faking the clock
while the real calendar still decides. The step also prescribes `caplog`, which captures
nothing here because structlog renders outside stdlib logging — the repository's own
pattern is `structlog.testing.capture_logs()`. Step 1's "build the app through
`app_factory`" was not followed either: dishka offers no way to override one binding in a
built container and no assertion in steps 4-6 involves HTTP, which is the same reasoning
`test_sync_backfill_gap_fill.py` already records for skipping the handler graph.

**Two defects in the new tests, both of the class this plan keeps rediscovering.**

- The adapter's ascending-order assertion was vacuous: the fixture is already sorted, so
  removing the sort left it green. The fake now replays the bars reversed, and removing
  the sort turns it red.
- The end-to-end test broke two unrelated unit tests in the same run without touching
  them. structlog is configured `cache_logger_on_first_use=True`, so a module-level
  logger first used inside `capture_logs()` stays bound to that configuration and
  silently stops being capturable after any later reconfigure — and `make_test_app`
  reconfigures on every integration test. The two victims asserted on captured logs and
  received an empty list. Fixed by monkeypatching a fresh proxy so the module's own
  logger is never cached. The suite passed before only because those two tests happened
  to be the first users of that logger.

**A tenth import contract, and the count in `plan.md` changes.** The success criteria say
"9 contracts from Phase 2 onward". The scraper is isolated behind `ITradingViewClient`
only if nothing outside `core.infra.tradingview` can import it, and Task 8's grep checks
the string `"tradingview"` rather than the library import. The new contract mirrors the
`pandas_market_calendars` one, including `allow_indirect_imports = true` for DI wiring.
Mutation-verified by planting a direct import in `engine/`.

**Everything Phase 4 could only mutation-test now has a second provider, and the entire
new surface was mutation-tested too.** Dead mutations: removing the lock; reading the
naive index as UTC; dropping the `n_bars` clamp; keeping the in-progress bar; dropping
the sort; removing the Task 10 override, applying it to crypto, and applying it
silently; planting a `tvDatafeed` import in `engine/`; removing the closed-market
silence; dropping the `calendar_id` stamp; deriving `session_date` from the UTC date;
and replacing the integrity grid with a flat UTC one.

**Verified against the live venue before deploying, not only against fakes.** A single
anonymous fetch of `ES`/`CME_MINI`/`fut_contract=1` returned five real 1h bars. The
last was the bar still forming — 2754 contracts against 100k-190k on the closed ones —
and the adapter dropped exactly that one, logging
`tradingview.in_progress_bar_filtered count=1` and returning four. This is the only
check that could have caught a wrong exchange alias or a wrong contract argument, and
nothing in the phase's own gates performs it. The free plan works unauthenticated, as
the entitlement design requires.

`bar_start` was also walked across every hour of a full weekend for all seven intervals
with zero failures, because the adapter calls it on every fetch whether or not the
market is open — the Session 6 fix holds for this new caller.

**Measured at Phase 5 code-complete.**

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `820 passed, 1 skipped` (baseline 792) |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 10 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| `uv run pyright` (src + tests) | `27 errors`, all pre-existing, 0 in new files |
| `just test-tz` | `820 passed` under all three zones |
| `cd web && npx tsc --noEmit` | exit 0 |
| `docker build -f deploy/Dockerfile` | exit 0; runtime image imports `tvDatafeed`, the adapter and `ZoneInfo("America/Chicago")` |

The first commit was verified green in isolation (`812 passed`, 10 contracts, pyright 0),
so no revision on the branch is red.

**A hazard worth recording for whoever runs the seed in production.** The repository's
local `.env` points `MONGODB_URL` at the production host, which is the documented
remote-db dev mode. `scripts/seed_index_futures.py` is a dry run by default, so the
first run read production and wrote nothing, but `--apply` from a developer machine in
that mode writes straight to production. The script's write path was therefore proved
against a disposable Mongo on port 27117 instead: three documents with the right
multipliers and calendar, and still three after a second `--apply`.

**Correction 22 — advisory review before the deploy: an empty answer from this
provider is never a quiet market, and a stalled login could stop crypto.** Two
guards landed before the push; both are deviations from Task 3, and one is a latent
G5 violation reachable from configuration rather than from code.

*The rejection amplifier.* Task 3 step 6 says to treat a `None` frame as an empty
list. But `get_hist` returns `None` only when its response regex finds no series —
a bad symbol, an entitlement refusal or a rate limit — and TradingView serves the
last N bars whatever the session state, so this provider can never answer "the
market is quiet". Returning `[]` made a refusal indistinguishable from emptiness to
`fetch_with_retry`, which retries on empty: three sockets per symbol per minute
against a venue that had just refused us, which is precisely the cost Correction 15
was written to avoid, arriving through the other branch. `fetch_bars` now raises
`TradingViewNoSeriesError`, so Correction 15's path gives one socket, one
`market_data.sync.failed` ERROR and `status=error`.

*The unbounded sign-in under the lock.* Upstream `__auth` calls `requests.post`
with no timeout, and it runs while this client holds its lock. A stalled sign-in
would hold the lock indefinitely, `sync_1m` would never finish, APScheduler's
per-job `max_instances=1` would skip every later tick, and BTC/ETH/SOL would stop
syncing — a crypto outage caused entirely by futures configuration. Verified that no
TradingView credentials exist anywhere in `../pocketquant-config/`, so the path is
currently unreachable, which is exactly why it is worth closing now rather than
after someone buys the add-on. Both `to_thread` calls are now wrapped in
`asyncio.wait_for`.

The instance is discarded on either timeout, and that is the load-bearing half.
Cancelling a `to_thread` does not stop the thread — confirmed directly: `wait_for`
returned after 0.10s while its thread slept 2.0s — so the orphan keeps running and
keeps writing to that instance's `ws`. Reusing it would hand the next fetch a socket
another thread is still reading, which is the corruption the lock exists to prevent.
Setting `self._tv = None` means the orphan keeps the old instance to itself.

*Two smaller items from the same review.* `test_an_override_lowers_the_cap_further`
passed with the `min()` removed, because an override of 250 is its own answer either
way; the load-bearing direction (an override of 9999 still yields 5000) now has a
test, and dropping the clamp turns it red. Both override fields gained `gt=0`,
because `tradingview_max_bars=0` is not "unset" — it would ask for no bars and
insert nothing, silently.

All three new guards are mutation-tested: returning `[]` instead of raising, keeping
the instance after a fetch timeout, and dropping the `min()` clamp each turn one test
red. Tests were also added for the construction re-raise and for the rebuild on the
following call.

**Measured after the guards.**

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `823 passed, 1 skipped` |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 10 kept, 0 broken` |
| `uv run pyright src` | `0 errors` |
| `just test-tz` | `823 passed` under all three zones |

**Carried to the seeding window, not done here.** The review's remaining findings all
concern the free plan's roughly ten-minute CME delay, which `capabilities.realtime`
records but nothing yet acts on. Three consumers assume the newest vendor bar is
current: the in-progress filter drops nothing on a delayed feed (so a forming bar can
be persisted once and never refreshed, with the cascade building on it); the stuck
threshold would fire at every 17:00 CT open and every 15:30 CT halt resume, which
fails Task 12's own criterion by design; and the last minutes of each session arrive
after the closed-market gate has shut, healing only at the next open. Each needs
verification against the live feed before it is treated as fact — fetch the same 1m
bar twice a minute apart and diff it — and Phase 6 already owns the poll floor, so it
is the natural home for delay-awareness.

Also recorded for Task 12's arithmetic: 5000 1m bars cover about 3.5 CME sessions
while `check_integrity` scans a fixed 7 days, so the first nightly scans after the
backfill will report gaps that are not gaps. Judge the clean week from one starting at
least seven days after the backfill.
