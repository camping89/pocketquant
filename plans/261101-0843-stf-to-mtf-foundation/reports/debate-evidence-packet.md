# Debate evidence packet — STF to MTF foundation

Date: 2026-11-01 (Asia/Bangkok). Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8` (one local commit ahead of `origin/develop`: `docs(governance): add no look-ahead rules for multi-timeframe strategies`).

## Sources (read in this order)

1. Accepted advice and owner decisions: `plans/reports/advise-261101-0847-stf-to-mtf-migration.md` (items 3-11, "What you shouldn't do", Work checklist, Success metrics, Handoff brief). Its Corrections section supersedes the state file's R6 (no hourly job) and the stale data-path claims.
2. Interview record: `plans/reports/advise-261101-0847-stf-to-mtf-migration-state.md` (qa-log A1-A19, requirements R1-R13; R6 superseded by advice item 6).
3. UI mockup the owner confirmed (A19): `plans/reports/advise-261101-0847-stf-to-mtf-migration-ui-mockup.html`.
4. Backend scout (exact code locations): `reports/scout-backend.md`.
5. Web, docs and prod-ops scout: `reports/scout-web-docs-ops.md`.
6. Project rules: `CLAUDE.md`, `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`.
7. Conventions model (finished sibling plan): `plans/261028-0652-exness-only-parallel-runtime/plan.md`, sections Conventions and Ops recipe.

## Confirmed contract (owner decisions, do not reopen)

| # | Decision |
|---|---|
| C1 | Retire STF fully: delete engulfing, engulfing_pullback30_touch, `engulfing_detector.py`, registry entries and their tests; no STF baseline, no compatibility, no deprecate-and-keep (A1, A5, A10). |
| C2 | Keep the web Engulf overlay; its golden fixture becomes web-owned; rewrite the "mirror of the Python detector" comment (A10). |
| C3 | Subscription replaces `interval` with ordered `intervals` (lowest = entry) and adds generic `parameters` validated by the strategy class with strategy-declared defaults; unique `(strategy_code, symbol, intervals)`; each higher interval is a multiple of the entry interval; edit only while stopped (A6, A16). |
| C4 | Higher-timeframe context is read from Mongo by the engine in `StrategyAppService._on_bar_completed` (one path for live, warm-up, backtest) through a per-(symbol, interval) cache shared by instances, re-queried only on bucket rollover, with one calendar-aware "closed before this instant" filter (A13). Never in the strategy class (import-linter). Never from live 1d/1w `BarCompletedEvent`s. |
| C5 | Cascade the 1d bar from 1m for session (Exness) calendars exactly as advice item 6 lists; 1w stays REST; no hourly job. |
| C6 | Platform capabilities, not modes: `Signal.entry_type: market | stop` and `Direction.EXIT`; risk check accepts EXIT with an open position; paper pending stop fills on next-bar high/low touch; paper EXIT closes at market; Exness `DELETE positions/{id}` and `POST orders` type `stop` exist behind the live flag; a new signal cancels then places the pending stop (A8, A9, A11). Rewrite the "Exits are SL/TP only" decision and "One take-profit per entry" table in `docs/system-architecture.md` in the same change. |
| C7 | Generic snapshot per entry bar: `readings[{interval, name, value, ok}]`, `decision{action, reason}`, `pending{side, price} | null`; trader writes to Redis per subscription (bounded ring); api serves it; UI renders a table. No Mongo decision history (A15). |
| C8 | Generic UI per the mockup: list row, detail drawer, create and edit form (intervals multi-select, parameters from strategy defaults), actions start, stop, edit while stopped, delete with warning, close at market and cancel pending with a real-money confirmation through the same paths strategies use. Nothing strategy-specific (A14, A16, A19). |
| C9 | Backtest: `BacktestConfig.intervals` plus existing `parameters`; form offers intervals; run header and existing compare view show intervals and parameters; no sweep runner (A-6). |
| C10 | Triple Screen is the first consumer only, one strategy file plus registry entry; its own parameters choose `entry_type` and exit mode; backtest 2-3 interval sets x both variants, then pick the live set (A7, A9). |
| C11 | Spike first (R13): one rough end-to-end spike on `develop` proves every foundation piece with go/no-go recorded per piece in the plan; stop and rethink only on no-go for the Mongo context path or paper EXIT. |
| C12 | Prod STF delete runs last, after the new paper subscription runs. No backup (owner, 2026-11-01). The executor lists the exact documents and waits for an explicit yes. The two open BTCUSDT:BINANCE paper positions are deleted with the STF data. Never remove a tracked symbol. |
| C13 | Out of scope: Exness live go-live (stays disarmed), MT5, partial close or multi-TP, Triple-Screen-specific anything in platform/UI, Mongo decision history, sweep runner, 100-instance measurement (design stays scale-aware), changes to symbol-suffix provider model, lease roles, reconcile loop, any 1w cascade. |

## Prod state (verified 2026-11-01 ~08:00Z, read-only, from the advice report)

All four subscriptions stopped; 0 exness-broker subscriptions; `entries_paused=true`; `live_trading=false`; 234 positions (2 open, BTCUSDT:BINANCE); 241 filled + 18 rejected orders; 215 trades; 21 backtest runs. Repeat the subscription and position queries right before the delete.

## Repo conventions the plan must carry

- Branch model: all work on `develop`; a `develop:master` push deploys prod and needs an owner yes.
- Tests need Docker Desktop; expected local Windows red is exactly the 4 failed + 4 errors `tzset` tests.
- Questions to the owner in Vietnamese; plan text, code, comments, commits in English; no plan ids or phase numbers in code, test names or commits.
- `CLAUDE.md` KISS limits: flow in at most 3 files, at most 2 hops to I/O, a new class/flag/config key needs a second real caller today, delete dead code in the same change, no docstrings, UUIDv7 keys, log level by frequency.

## Scout findings that change the advice (details and `path:line` in the scout reports)

Backend (`reports/scout-backend.md`, Section 0):
- A Mongo unique index on a list field is multikey: `["15m","1h"]` and `["15m","4h"]` would collide on `15m`. The uniqueness needs one derived scalar key (for example the joined string `"15m,1h,4h"`).
- `ix_subscriptions_dedup_triple` must be dropped before it is recreated with new keys; precedent for drop-then-create: `job_history_repository.py:322-341`.
- The backtest sandbox builds `StrategyAppService` with stubs (`NoStoredBars`, a 24/7 calendar); 20 fixtures use the stub, which only implements `find()`. Advice item 5's "one code path already reaches Mongo in backtests" is false until the sandbox gets the real bar repository and calendar.
- The position tracker never starts in a backtest; the risk check always sees "no position" there.
- Backtest sim time is the bar start, not the bar end; a "closed before now" filter must use the entry bar's end in every path.
- Code-metric gate has zero headroom (delegations 73/73, small-function share 0.4809/0.4810); raising the ceiling in its own commit is allowed (owner memory: the ratchet is flexible, KISS wins).
- `test_admin_token_guard.py:46` asserts exactly 17 mutation routes.
- Trader restore drops paper positions with no SL and no TP (`strategy_app_service.py:157-165`).
- Reconcile loads every subscription and never reloads an existing one; an edit of a stopped subscription keeps the old config in memory.
- The engine prices orders at bar close and ignores `Signal.entry_price`; `_create_order` maps every non-LONG to SELL and always MARKET.
- Exness order code lives in `core/infra/brokers/exness/exness_broker_adapter.py`; `_submit_open` rejects while a position is open; any new close or pending call must join `_ORDER_OPS` (`exness_client.py:46`) to stay behind the live flag.
- `scripts/rubric/static_audit.py` imports the registry and its tests list the STF codes.
- There is no api-to-trader channel for manual close or cancel; routes only write Mongo and the trader owns the brokers.

Web, docs, ops (`reports/scout-web-docs-ops.md`):
- The golden fixture is two identical copies (Python test, web test); two web comments mention the Python detector (`engulfing.ts:4-6`, `engulfing.test.ts:4-5`).
- CI has no web lint, type-check or test step; the web image builds with `npx vite build` (no type check).
- Local `npx tsc -b` already exits 2 (`web/src/components/monitor/job-status-palette.ts:3,13`); lint 0 errors 6 warnings; vitest 70/70.
- Vitest runs in node on `src/**/*.test.ts` only; no jsdom, no testing-library.
- The compare view caps at 3 runs (route, view, history rail); "four backtests in one compare view" cannot render.
- The create dialog sends no `broker`; interval lists in create dialog, backtest form and history rail omit `1w`; the strategy chart has no interval switcher and no live bar.
- Missing endpoints: strategy default parameters, orders per subscription, close position, cancel order.
- No per-subscription Redis key exists; `Cache` has no list operations; subscription delete and symbol removal would not clean a new snapshot key.
- Positions and orders link by `subscription_id`; trades by `run_id`; prod counts did not cover `backtest_orders` or `backtest_trades`.
- Docs to rewrite: `docs/system-architecture.md:12,34,37-48`; `docs/code-standards.md:93,95`; `docs/swing-pivot-key-level.md` (16 lines, all engulfing).

## Open design questions the candidates must answer (state the choice and why)

Q1 Unique key shape for `intervals`. Q2 api-to-trader channel for manual close and cancel. Q3 Backtest exit quantity source (paper broker vs starting the position tracker). Q4 Restore rule for exit-only paper positions with no SL/TP. Q5 Reload of an edited stopped subscription. Q6 Backtest sandbox wiring to the real bar repository and calendar without breaking the 20 stub fixtures. Q7 Web gates: fix the two pre-existing type errors, add a web CI job, how to test UI (pure helpers vs jsdom). Q8 Compare cap vs the four-run metric. Q9 Fate of `docs/swing-pivot-key-level.md` and `scripts/rubric/static_audit.py`. Q10 Where default parameters are served (`GET /strategies/{code}` vs `GET /backtest/strategies`). Q11 Snapshot key cleanup on subscription delete and symbol removal.
