---
phase: 7
title: "UI, Docs and Success-Metric Run-Through"
status: completed
priority: P2
effort: "1d"
dependencies: [6]
---

## Context

(Advice Phase 6.) The three futures symbols must be selectable everywhere a crypto
symbol is, the SPA must stop presenting Binance as the only possible venue, the
"closed" state added in Phase 3 must be visible, and the documentation must describe
the provider table and the new settings. The phase closes with a run-through of the
18 success metrics.

## Tasks

### Task 1 — Generic SPA placeholders

**Goal.** No input hint in the SPA implies Binance is the only venue.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx` — lines 21, 23, 24, 72.
- `web/src/components/backtest/backtest-form.tsx` — line 72.
- `web/src/lib/symbol-format.ts` — the module docstring at line 2.
- `web/src/components/chart/trading-chart.tsx` — the prop docstring at line 38.
- `web/src/components/controls/symbol-selector.tsx` — line 6.
- `web/src/components/ticker-widget/ticker-widget.tsx` — line 6.
- `web/src/types/market-data.ts` — line 20.
- `web/src/types/quote.ts` — line 3.

**Steps.**
1. Replace the user-visible strings in `add-symbol-dialog.tsx` (the error messages at
   lines 23-24 and the `placeholder` at line 72) with
   `CODE:EXCHANGE (e.g. BTCUSDT:BINANCE or ES1!:CME_MINI)`.
2. Do the same for the error message in `backtest-form.tsx` line 72.
3. In every docstring listed above, change the example from
   `"BTCUSDT:BINANCE"` to `"BTCUSDT:BINANCE" or "ES1!:CME_MINI"`.
4. Do NOT change the default symbol values at `web/src/routes/__root.tsx:17`,
   `web/src/routes/index.tsx:21` or `web/src/components/backtest/backtest-form.tsx:44`
   — the default landing symbol stays `BTCUSDT:BINANCE`.
5. Confirm the composite parser at `web/src/lib/symbol-format.ts:6-10` splits on the
   FIRST `:` and therefore handles `ES1!:CME_MINI` with no change.

**Success criteria.** The SPA builds and no user-visible hint names only Binance.

**Verify.** `cd web && npm run build` exits 0.

---

### Task 2 — Exchange badge and closed-market state

**Goal.** A futures symbol renders its exchange badge and shows CLOSED rather than a
red stuck badge outside session hours.

**Target files and symbols.**
- `web/src/components/monitor/data-health-row.tsx` — lines 50, 55, 72
  (`StuckBadge show={!!s.is_stuck}`).
- `web/src/components/monitor/format-helpers.ts` — line 19.
- `web/src/types/market-data.ts` — the `SyncStatus` interface (line 88).
- `web/src/lib/datetime.ts` — `ageColorClass` (lines 88-97).

**Steps.**
1. These edits were started in Phase 3 Task 5. Finish them: when
   `s.is_market_open === false`, render a neutral `CLOSED` badge instead of
   `StuckBadge`, and return `'age-neutral'` from the status helper.
2. In `ageColorClass`, add an optional third parameter `isMarketOpen?: boolean` and
   return `'age-neutral'` when it is explicitly `false`. Update the call sites — grep
   for `ageColorClass(` across `web/src`.
3. Confirm the exchange badge component renders `CME_MINI` and `CBOT_MINI` — it uses
   `parseSymbol(...).exchange`, which is venue-agnostic.

**Success criteria.** With `is_market_open: false` the row shows CLOSED, not STUCK.

**Verify.** `cd web && npm run build` exits 0 and `grep -c "is_market_open" web/src/components/monitor/data-health-row.tsx web/src/types/market-data.ts` reports at least `1` per file.

---

### Task 3 — Provider status on `/health`

**Goal.** "Why are there no ES bars" is answered by one request.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py` — `register_health_checks` (lines 267-270)
  and the `health_check` route (around line 366).

**Steps.**
1. Add a health check named `market_data_providers` that reports, per registered
   provider id: whether it is authenticated (for TradingView, `client.is_authenticated()`;
   for Binance, `True`), and per tracked symbol the resolved provider id and
   `calendar.is_open(now)`.
2. Keep the payload bounded: report at most the tracked symbols, never bar arrays.
3. Register it beside the existing `database` and `redis` checks with
   `hc.register("market_data_providers", ...)`.
4. Report a degraded TradingView login as a non-fatal `degraded` status, not as
   unhealthy — the container health check at `deploy/Dockerfile:53-54` must not start
   flapping because the scraper lost its session.

**Success criteria.** `/health` includes a `market_data_providers` entry and the
overall status stays healthy when TradingView is degraded.

**Verify.** `curl -s http://localhost:41921/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('market_data_providers' in json.dumps(d))"` prints `True`.

---

### Task 4 — Update the architecture documentation

**Goal.** The docs describe the provider table, the calendar port and the new
settings.

**Target files and symbols.**
- `docs/system-architecture.md` — `## Where Does X Live?` (line 479),
  `## Dependency Injection (Dishka)` (line 670), `## Configuration` (line 773),
  `## Dependencies` (line 777), `## Ops Context` external services (line 796), and
  the Symbol description at line 173.
- `README.md` — the settings list and the line claiming 7 import-linter contracts.
- `docs/visuals/collection-erd.mmd` — line 20 (`string asset_type`).

**Steps.**
1. In `## Where Does X Live?`, add five rows:
   | Trading calendar port + 24/7 implementation | `core/domain/market_data/trading_calendar_port.py`, `core/domain/market_data/continuous_24x7_calendar.py` |
   | CME Globex equity calendar | `core/infra/calendars/cme_globex_calendar_adapter.py` |
   | Provider routing adapters | `core/infra/market_data/` |
   | TradingView client, mappers, adapters | `core/infra/tradingview/` |
   | Asset class + contract spec | `core/domain/shared/enums.py`, `core/domain/symbol/value_objects.py` |
2. In the DI section, update the provider description: `InfrastructureProvider` now
   builds a `RoutingDataProviderAdapter` over `{binance, tradingview}` and
   `MarketDataProvider` builds a `RoutingRealtimeQuoteAdapter`.
3. In `## Configuration`, add `MARKET_DATA_PROVIDERS`, `SYMBOL_PROVIDER_OVERRIDES`,
   `TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD`, `TRADINGVIEW_AUTH_TOKEN`,
   `TRADINGVIEW_MAX_BARS`, `TRADINGVIEW_POLL_SECONDS`, `TRADINGVIEW_DELAYED_DATA` and
   `TZ` (names only, never values).
4. In `## Dependencies`, add `pandas_market_calendars` (CME session calendar) and
   `tvdatafeed` (TradingView scraper, installed from git).
5. In `## Ops Context`, add TradingView to the external-services list with a note that
   it is an unofficial scraper with no stability promise.
6. Fix line 173: `Symbol` now carries `asset_class`, `calendar_id` and `contract_spec`
   instead of `asset_type`.
7. In `docs/visuals/collection-erd.mmd` line 20, replace `string asset_type` with
   `string asset_class`, `string calendar_id` and `object contract_spec`.
8. In `README.md`, list the new settings by name and correct "7 import-linter
   contracts" to "8" (`pyproject.toml` defines 8).
9. `docs/vi/system-architecture.md:173` mirrors line 173 of the English file — update
   it too, keeping the Vietnamese wording.

**Success criteria.** No document still says `asset_type` for the `symbols` collection.

**Verify.** `grep -rn "asset_type" docs/ README.md web/src src/ | wc -l` prints `0`.

---

### Task 5 — Journal the timezone and calendar decision

**Goal.** The reasoning behind the UTC invariant and the calendar port survives in the
repository.

**Target files and symbols.**
- New file `docs/journals/2026-09-21-asset-class-trading-calendar.md`
  (follow the format of `docs/journals/2026-06-28-paper-broker-futures-accounting.md`).

**Steps.**
1. Record: the `CronTrigger` host-zone bug and how it was found; the
   `tz_aware` + `integrity_jobs` commit-ordering constraint and why splitting it
   triggers a full resync; why calendar rules live in code while `calendar_id` lives
   on the symbol record; why realtime routing has no fallback chain; why the
   TradingView mapper recovers the epoch through `.timestamp()` instead of trusting
   the library's index.
2. Do not name plan ids, phase numbers or audit labels in any source comment — those
   belong here, in the journal.

**Success criteria.** The journal exists and covers the five points.

**Verify.** `test -f docs/journals/2026-09-21-asset-class-trading-calendar.md && grep -c "tz_aware" docs/journals/2026-09-21-asset-class-trading-calendar.md` prints a number of at least `1`.

---

### Task 6 — Success-metric run-through

**Goal.** Every stated metric is measured and recorded, not assumed.

**Target files and symbols.**
- New file `plans/260921-1436-asset-class-index-futures/completion-report.md`.

**Steps.**
1. Measure and record each of the following, with the command used and the observed
   value:
   1. `TZ=Asia/Ho_Chi_Minh` startup refuses; `TZ=UTC` starts.
   2. Identical cron `next_run_time` under the three zones; `sync_backfill` fires at
      03:00 UTC.
   3. On a Thursday-to-Sunday run, the latest `1w` bar for `BTCUSDT:BINANCE` opens on
      the previous Monday 00:00 UTC.
   4. Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
      `stuck_threshold_crossed` and `partial_aggregate` for `ES1!:CME_MINI` over one
      week including a weekend and one early-close holiday.
   5. Futures 1d bars open 17:00 CT and close 16:00 CT on both sides of a DST
      transition, with `session_date` populated.
   6. Golden-file comparison: crypto bars, cascade output and metrics unchanged.
   7. `uv run ruff check src tests scripts` passes with `DTZ`; `uv run pytest` passes with no added skips.
   8. The DST suite passes: `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
      `session_open(2026-11-02) == 2026-11-01T23:00:00Z`.
   9. G1 during a session.
   10. Weekend quiet: `job_history` shows `sync_1m` runs for the three futures symbols
       with a skipped-closed detail and zero `no_progress` entries.
   11. `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0` for
       24 consecutive runs, and 4h bar datetimes are session-open anchored.
   12. Backfill depth at 1m equals `min(tradingview_max_bars, available)` and grows by
       about 1,380 per trading day.
   13. G2.
   14. G3.
   15. G4: a mock third provider registered via config only receives fetches for an
       overridden symbol, and the change touches no file under `engine/` or `app/`.
   16. G5: `sync_1m` for BTC/ETH/SOL produces the same `synced_count` and bar values
       as before; crypto `periods_per_year` at 1m is still 525600.
   17. G6: the app refuses to start on a non-UTC host and the DST suite passes.
   18. Secrets: the credential grep below finds only field declarations.
2. For any metric that cannot be measured yet (a holiday that has not occurred, a
   full week that has not elapsed), record the date on which it will be measured
   rather than marking it passed.

**Success criteria.** All 18 metrics are recorded with a command and a value.

**Verify.** `git grep -i "tradingview_.*=" -- ':!*.md' | grep -v "SecretStr\|str | None\|int =\|bool =" | wc -l` prints `0`.

---

### Task 7 — Final full gate

**Goal.** The repository is green on every gate the project defines.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the suite under all three CI timezones.
2. Run ruff, `pyright src` and the import contracts.
3. Build the SPA.
4. Build the Docker image to confirm the git dependency resolves in the builder stage.

**Success criteria.** Every command exits 0.

**Verify.** `uv run pytest tests/ -q && TZ=Asia/Ho_Chi_Minh uv run pytest tests/ -q && TZ=America/Chicago uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run pyright src && uv run lint-imports && (cd web && npm run build)` exits 0.

## Todo

- [x] Task 1 — Generic SPA placeholders
- [x] Task 2 — Exchange badge and closed-market state
- [x] Task 3 — Provider status on `/health`
- [x] Task 4 — Update the architecture documentation
- [x] Task 5 — Journal the timezone and calendar decision
- [x] Task 6 — Success-metric run-through
- [x] Task 7 — Final full gate

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The `/health` provider check makes a blocking scraper call and the container health check times out | Medium | High — the container restarts in a loop | Task 3 step 1 reads a cached `is_authenticated()` flag; it must never issue a network call |
| A metric cannot be measured because the week or holiday has not passed | High | Low | Task 6 step 2 records the future measurement date rather than a false pass |
| SPA build breaks on the renamed `SymbolInfo` field | Medium | Low | Task 1's Verify builds the SPA |
| Docs drift again after the next change | Medium | Low | The journal in Task 5 records the reasoning, so the next editor has context |

**Rollback.** Every task in this phase is documentation or presentation and can be
reverted individually with no runtime effect, except Task 3, which is removed by
deleting one `hc.register(...)` line.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
