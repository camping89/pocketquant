# Immutable evidence packet — ak:plan --ultra --advice

Every candidate receives this packet verbatim. Do not assume anything outside it
without verifying against the repository.

## Project

- Repo root: `/home/ubuntu-1/W/_me/algotrading/pocketquant`
- One Python package `src/pocketquant/` (subpackages: core, engine, backtest, app) + Vite SPA in `web/`
- Python 3.14, uv, FastAPI (single uvicorn worker), Mongo, Redis, Dishka DI, pytest, ruff, import-linter (8 contracts)
- Branch: `develop`. Today: 2026-09-21.
- Plan directory (already scaffolded): `plans/260921-1436-asset-class-index-futures/`

## Source documents (READ BOTH — they are the grounding for this plan)

- `plans/reports/advise-260921-2001-index-futures-data-provider.md` — the confirmed advice, including the user-confirmed reframing, the 7-phase route, do/don't, trade-offs, a 24-item checklist and 18 success metrics.
- `plans/reports/kongming-260921-2106-datetime-timezone-audit.md` — file:line-verified datetime/timezone audit.

## Task

Produce a complete implementation plan covering **all seven phases (advice Phase 0 through Phase 6)** of the confirmed advice. The plan is scaffolded as phases 1-7 in the plan directory; map advice Phase 0 -> plan Phase 1, ..., advice Phase 6 -> plan Phase 7, and say so once in the plan overview.

## User-confirmed reframing (authoritative; do not re-litigate)

PROBLEM: PocketQuant is hardwired to one 24/7 crypto venue. DI binds exactly one REST provider and one WS provider, and sync/cascade/annualization/paper-broker math assume continuous trading and price x quantity units. The user wants ES1!/NQ1!/YM1! (CME/CBOT continuous front-month index futures) for charts, live paper trading and higher-timeframe forward-accumulating backtests, sourced from TradingView via tvdatafeed or an equivalent scraper, delivered through (a) an asset-class model that drives session, annualization and contract math inside the EXISTING pipeline, and (b) provider resolution keyed by asset class + provider id.

REQUIREMENTS:
- R1 `AssetClass` enum on Symbol (replaces free-string `asset_type`; CRYPTO_SPOT, CRYPTO_PERP, INDEX_FUTURE) binding annualization basis and contract-spec shape. Per-symbol values: ES $50/point, NQ $20/point, YM $5/point.
- R1b TradingSchedule is persisted DATA stored alongside the asset class; 24/7 is simply crypto's schedule, not a default. Covers exchange IANA timezone, weekly session open/close, daily maintenance halt, weekend closure, holiday hook, session-day boundary for 1d/1w. A future asset class = new enum member + new schedule record, no new branching.
- R2 Provider registry/resolver replacing the single DI binding for BOTH ports: config maps asset class -> ordered provider ids (primary + fallback), optional per-symbol override; sync, backfill and WS subscription manager resolve per symbol.
- R3 TradingView adapter pair, with the scraper library isolated behind an internal client interface so it can be swapped.
- R4 Entitlement is config: credentials, bar cap, delay flag, provider map via Settings from env. NO branching on TradingView plan tier anywhere.
- R5 Schedule-aware sync/retry/anomaly gating; 1d/1w bucketed on the schedule's session day, never UTC midnight; crypto path unchanged.
- R6 Initial backfill to the configured cap per timeframe; cron accumulates forward.
- R7 Paper broker, backtest engine and performance calculator read the asset-class spec (points x multiplier x contracts, integer contracts, per-contract commission option, session annualization); existing margin accounting kept.
- R8 UI: 3 symbols selectable, exchange badge, generic placeholders.
- R9 Tests: resolver, TV mappers on offline fixtures, session calendar, contract math, one end-to-end futures sync; crypto tests stay green.
- R10 Timezone correctness: no naive datetime crosses a boundary; UTC storage and arithmetic; exchange-local session times via zoneinfo (America/Chicago for CME) with DST handled; explicit tests for DST spring-forward/fall-back on session boundaries, holiday/half-day sessions, Sunday reopen, session spanning UTC midnight.
- R11 UTC enforcement as a VERIFIED system-wide invariant, crypto included: TZ=UTC pinned in Dockerfile/compose/systemd; startup assertion that the process timezone is UTC, fail fast; ruff DTZ rules + a test that fails on naive datetime construction; Mongo client tz_aware=True or boundary coercion that raises instead of silently attaching UTC.

GOALS: G1 fresh futures bars within one cron cycle during session hours. G2 a paper ES strategy runs a full session with correct USD PnL. G3 a 1h ES backtest reports dollar PnL/Sharpe consistent with contract spec. G4 adding a provider = one adapter + one config entry, zero caller edits. G5 BTC/ETH/SOL behaviour and tests unchanged. G6 the app refuses to start on a non-UTC host and the DST-boundary test suite passes.

NON-GOALS: real futures broker; multi-year 1m futures history (deferred, accepted trade-off); Databento/IBKR adapters; tick-level fidelity beyond the scraper; modelling contract roll inside paper positions; redoing the margin accounting that shipped in plan 260628-2013; plan-tier branching in code.

CONSTRAINTS: single uvicorn process; ports in `core/domain`, adapters in `core/infra`, ALL repositories in `core.infra.persistence.repositories` (zero repos in backtest/app); fastapi only in `app` (import-linter enforced); routes use `FromDishka[...]` + `DishkaRoute`, never `Depends()`; primary keys UUIDv7 only; composite symbol format `{CODE}:{EXCHANGE}`; credentials ONLY in `../pocketquant-config/`, never in this repo; log level = frequency + audience (DEBUG for per-bar/per-tick, INFO for one-shot lifecycle and per-trade, never unbounded payloads above DEBUG); KISS/DRY, reuse the existing pipeline, NO parallel futures pipeline.

## Verified code facts (file:line evidence from the audit — verify before relying, but these were checked)

Live bugs affecting crypto today, independent of futures:
- `core/infra/scheduling/scheduler.py:79` sets `timezone="UTC"` on the scheduler, but `:219-233` builds `CronTrigger(...)` with no `timezone=` and passes the prebuilt trigger to `add_job` at `:245`. APScheduler 3.11.2 falls back to `get_localzone()` and pickles the host zone into the Mongo jobstore. Affects `sync_backfill hour=3`, `sync_integrity hour=4`, `sync_repair "0 */12"`, `sync_verify_cascade "0 * * * *"` (`sync_jobs.py:690-720`).
- `core/infra/binance/binance_adapter.py:80-83` floors `now` to 604800000 ms, a THURSDAY-aligned epoch week, so from Thursday to Sunday the in-progress Monday-open weekly kline passes the `< cutoff_dt` guard at `:108` and is persisted partial. Fix: derive the cutoff from `get_bar_start(now, WEEK_1)`.

Five P0s that fire on day one of a session-scheduled asset class:
- Alignment: `bar_builder_domain_service.py:10-32` defines 1d as `replace(hour=0)` and 1w as Monday 00:00 in the timestamp's own tz; `sync_internals/bar_filters.py:72-82` drops anything else on every sync (called from `sync_service.py:79-81`); `SYNC_INTERVALS` includes 1d/1w (`sync_jobs.py:54-62`). A CME daily bar opening 17:00 CT would be 100% dropped.
- Cascade: `cascade_aggregator.py:127-129` floors to a fixed UTC epoch grid; `_TF_EXPECTED_BARS[DAY_1] = 1440` at `:46`; `compute_boundaries` spans `:98-137`. Every futures session spans UTC midnight, and DST moves the session open between 22:00 and 23:00 UTC.
- Integrity: `integrity_jobs.py:62-63` builds a dense arithmetic grid `expected = {start + i*step}` (docstring at `:46-47` admits 24/7-only). Weekend (~2,940 min) + halts + holidays read as gaps; `repair_integrity` at `:79-116` then resyncs 5000 bars per symbol/interval every 12h.
- Freshness/stuck: `sync_status_service.py:62-69`, `anomaly_log.py:35-40,52-59`, `web/src/lib/datetime.ts:88-97` measure `now - last_bar`. A futures symbol reads "stuck" 3 minutes after Friday close; ~2,900 `no_progress` WARNs per symbol per weekend violates the CLAUDE.md log-frequency rule.
- Annualization: `core/domain/shared/enums.py:5-13` and `performance_calculator_domain_service.py:13-14,108-109,166-167` hardcode 365x24. ES is ~252 sessions x 23h; Sharpe overstated ~1.20x (1d) / ~1.23x (1m).

Timezone plumbing:
- `coerce_utc` silently attaches UTC to naive values; the Mongo client is NOT `tz_aware` (`core/infra/persistence/mongodb.py:44-49`); `bar_repository.py:219-242` returns naive raw projections; acknowledged in `sync_internals/bar_filters.py:54-55`.
- One DELIBERATE naive site: `integrity_jobs.py:50` `datetime.now(UTC).replace(tzinfo=None)` exists so `expected` set-compares with naive projections; `bar_builder_domain_service.py:24` has a naive epoch branch only for this. **HARD ORDERING CONSTRAINT: `AsyncMongoClient(tz_aware=True)` and the `integrity_jobs.py:50` fix MUST land in the SAME commit**, or the integrity check reports every bar missing and triggers a full resync of every symbol.
- `engine/backtest/backtest_strategy_loader.py:37` uses `date.today()` (host-dependent).
- No `utcnow()`, bare `now()`, or naive `fromtimestamp()` anywhere in `src/` (grep verified).
- `deploy/Dockerfile:44-47` pins no `TZ`; `deploy/compose.prod.yml:43-44` only `env_file`. `tzdata` 2025.3 is locked so `zoneinfo` works.
- Naive datetimes accepted at the API edge: `market_data_ohlcv.py:42-43`, `backtest_command_service.py:31-32`, `backtest_strategy_loader.py:58-59`, `backtest_dispatch.py:47-48`.
- Serialization drift: `docs/code-standards.md:777` mandates `to_utc_iso()`, but `entities.py:104`, `ohlcv_service.py:66`, `backtest_command_service.py:74-75`, `backtest_report_app_service.py:396-397` use `.isoformat()`; `sync_status_service.py:72-73` hand-rolls `Z`.
- `get_bar_start` (`bar_builder_domain_service.py:13-22`) does wall-clock arithmetic in whatever zone it is given, with no UTC assertion.
- ruff `select` in `pyproject.toml` is currently `E,F,I,N,W,UP,TID` (no `DTZ`).

Domain / provider surface:
- Two ports: `core/domain/market_data/data_provider_port.py` (`IDataProviderPort`, REST history) and `realtime_quote_provider_port.py` (`IRealtimeQuoteProviderPort`, a 9-member Protocol). Exactly one Binance implementation each; DI binds one of each in `app/di/infrastructure.py` and `app/di/market_data.py`.
- `Symbol.asset_type` is already a free-string field — the natural home for the enum.
- `COMPOSITE_SYMBOL_RE` in `core/domain/symbol/entities.py` is `^[A-Z0-9_-]+:[A-Z0-9_-]+$` and REJECTS `!`.
- No `multiplier` / `contract_size` / `tick_size` / `point_value` anywhere in `src/` (grep verified; the only hits are an OKX websocket reconnection backoff multiplier and a backtest replay-speed multiplier).
- PaperBroker already migrated to futures/margin accounting (1x leverage, only close/reduce touches balance) in plan `260628-2013`; see `docs/journals/2026-06-28-paper-broker-futures-accounting.md`. That is MARGIN accounting, NOT contract specs. Keep it; add only the unit conversion.
- `core/domain/trading/commission_model.py` exposes `PercentageCommissionModel` with `compute(price, quantity)`.
- `core/domain/risk/services/position_calculator_domain_service.py` handles sizing.
- `tvdatafeed` builds timestamps with naive LOCAL time at `tvDatafeed/main.py:143` — map from the raw epoch field instead.
- `LIMIT_TVDATAFEED_MAX_BARS` and the backfill script docstring are fossils of an earlier migration away from tvdatafeed.

## The seven phases from the confirmed advice (plan phases 1-7)

1. (advice Phase 0) UTC invariant + the two live crypto bugs. Gate: refuses to start under `TZ=Asia/Saigon`; identical cron `next_run_time` across three zones.
2. (advice Phase 1) Calendar port + domain model: `ITradingCalendarPort`, `Continuous24x7Calendar`, `CmeGlobexEquityCalendar` over `pandas_market_calendars` ("CME Globex Equity", America/Chicago, open time(17) at -1 day, close time(16), explicit holiday and early-close rules; pandas is already a dependency), `AssetClass`, `ContractSpec`, `calendar_id`/`session_date` persisted, composite regex widened, symbol migration. Gate: DST tests for 2026-03-08 and 2026-11-01, Juneteenth early close.
3. (advice Phase 2) Thread the calendar through alignment, cascade, integrity, freshness and annualization USING THE 24/7 CALENDAR ONLY. Gate: golden-file test proves crypto bars, cascade output and metrics byte-identical; full suite green; one prod cron cycle identical.
4. (advice Phase 3) Routing adapters + settings, Binance-only registration. Gate: full suite green, one prod cron cycle identical.
5. (advice Phase 4) TradingView history adapter + credentials, seed the three symbols, backfill to the cap. Gate: G1 during a session; zero anomaly events for ES across one full week including a weekend; `sync_verify_cascade` on ES reports zero divergent bars.
6. (advice Phase 5) Polling quote adapter, contract-aware paper broker and backtest. Gate: G2 and G3.
7. (advice Phase 6) UI placeholders and "closed" state, docs, success-metric run-through. Gate: G4, G5, metrics recorded.

Symbols to seed: `ES1!:CME_MINI`, `NQ1!:CME_MINI`, `YM1!:CBOT_MINI`.

## MANDATORY OUTPUT CONTRACT — `--advice` handover shape

This plan will be executed by a WEAKER model (Sonnet-class or Flash-class) that follows instructions well but under-infers. It will read ONLY `plan.md` and the `phase-NN-*.md` files. Everything must be materialized as output text.

Every phase decomposes into an ordered list of numbered TASKS. For each task state, in plain imperative language:
- **Goal** — the one observable outcome this task produces.
- **Target files and symbols** — exact paths plus the function, type, endpoint or config key. NEVER "update the relevant file"; name it.
- **Steps** — ordered actions concrete enough that no intermediate step is left to infer.
- **Success criteria** — observable, not a feeling of completion.
- **Verify** — either the literal text `no verification needed` for a pure edit whose effect the next task's verification covers, or a MECHANICAL PASS CONDITION: the exact command plus the exact expected result (exit code, expected substring, file that must exist, expected value). "Confirm it works" is NOT a verification. "`uv run pytest tests/core_test/unit/test_calendar.py` exits 0 and prints `12 passed`" is.

Every phase file MUST literally contain this block verbatim:

```markdown
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
```

Phase file frontmatter:
```yaml
---
phase: <N>
title: "<Phase Name>"
status: pending
priority: P1|P2|P3
effort: "<e.g. 6h, 2d>"
dependencies: [<phase numbers>]
---
```

`plan.md` frontmatter needs: title, description, status: pending, priority, effort (sum), tags, blockedBy: [], blocks: [], created: 2026-09-21. `plan.md` stays under ~80 lines: overview, the phase-number mapping note, a Phases table linking each phase by HUMAN-READABLE name (not filename), goals, success criteria, dependencies.

## What you must produce

Write ONE file: the path given in your prompt. It contains the COMPLETE plan — the full intended body of `plan.md`, then the full intended body of each of the seven `phase-NN-*.md` files, separated by clear `=== FILE: <filename> ===` markers so the controller can split it. Do not write any other file. Do not modify any repository source file.

Quality bar: real file paths verified against the repo, real commands that exist in this project (`uv run pytest ...`, `uv run ruff check ...`, `just ...` — check the `justfile`), no placeholders, no invented APIs. Where you are unsure of a path or symbol, grep for it before writing. Tag anything you could not verify with `[UNVERIFIED]`.
