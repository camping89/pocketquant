# Scout: web, docs and prod-ops evidence for the STF-to-MTF foundation

Date 2026-11-01 (Asia/Bangkok). Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8`. Read-only repo scout; no VPS access. Scope: items 3-11 of `plans/reports/advise-261101-0847-stf-to-mtf-migration.md`, frontend + docs + prod ops. Every bullet is a fact read in the repo unless marked [INFERENCE].

## Findings that change the plan (read first)

1. **The golden fixture is two byte-identical copies, not one shared file.** `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json` and `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` (`cmp` = identical). The Python test reads its own copy (`test_engulfing_detector.py:13`); the web test imports its copy (`engulfing.test.ts:2`). Deleting the Python detector test leaves the Python copy dead. Two web comments name the Python side, not one: `engulfing.ts:4-6` and `engulfing.test.ts:4-5`.
2. **No web gate runs in CI.** `.github/workflows/cicd.yml` runs only `lint-imports`, the code-metrics ratchet and pytest (`:49-56`). The web image builds with `npx vite build` (`web/Dockerfile`), which does no type check. No eslint, `tsc` or vitest step exists.
3. **The local web build is red today.** `npx tsc -b` exits 2 with 2 errors, both in `web/src/components/monitor/job-status-palette.ts:3,13` (`interrupted` missing from `Record<JobRunStatus, string>`). So `npm run build` (`tsc -b && vite build`) fails before any MTF change. `npx eslint .`: 0 errors, 6 warnings. `npx vitest run`: 9 files, 70 tests pass.
4. **Vitest cannot run component tests.** `web/vitest.config.ts`: `environment: 'node'`, `include: ['src/**/*.test.ts']`. No `.test.tsx`, no jsdom, no testing-library in `web/package.json`. Every existing web test is a pure-function test. [INFERENCE] UI tests for the drawer and form need either extracted pure helpers (`*.test.ts`) or new dev dependencies, which a KISS reviewer must accept.
5. **The compare view holds at most 3 runs.** `routes/backtest_.compare.tsx:16` (`.slice(0, 3)`), `run-compare-view.tsx:15-19` (three fixed hook slots), `run-history-rail.tsx:135` (`disableSelect` at 3). The advice's success metric "at least four backtests (2 interval sets x 2 variants) appear in the compare view" cannot show four in one view. Either lift the cap or change the metric to two compare views.
6. **The create dialog sends no broker.** `new-subscription-dialog.tsx:58-59` posts `{ symbol, interval }`; the "+ New" button title says "Creates a paper subscription" (`strategy-list-sidebar.tsx:55`). The route accepts `broker` (`app/routes/strategy.py:13-16`). The mockup's broker selector is new UI work.
7. **No endpoint serves strategy defaults or pending orders.** `GET /api/v1/strategies/{code}` returns only `strategy_code` and `class_name` (`engine/strategy/strategy_query_service.py:24-31`). The web lists codes from `GET /api/v1/backtest/strategies` (`backtest-api.ts:214-216`, route `app/routes/backtest.py:41-43`). No route lists a subscription's orders. `/positions` returns open positions and `/trades` returns closed positions.
8. **The subscription unique index keeps its name across a key change.** `ix_subscriptions_dedup_triple` on `(strategy_code, symbol, interval)` (`subscription_repository.py:77-84`), created at startup through `main_extensions.py:116`. [INFERENCE, MongoDB behaviour not checked here] `create_index` with the same name and new keys fails with an index conflict, so the prod index needs a drop or a new name, and the drop belongs in the deploy step.
9. **Positions and orders carry no `strategy_code`.** They link to a subscription only by `subscription_id`; trades link by `run_id` (= subscription id). Subscription delete removes only the subscription document (`strategy_command_service.py:91-92` → `subscription_repository.py:65-69`). [INFERENCE] Earlier deletes may have left orphan positions/orders/trades, so the prod delete filter must be built from subscription ids, plus a separate orphan check.

## 1. Web subscriptions UI (`web/src`)

Page and layout
- Route `/strategies` → `routes/strategies.tsx:5-11` renders `StrategiesPageLayout`.
- `components/strategies/strategies-page-layout.tsx` (236 lines): three columns (sidebar list, main = chart + config card, right = dashboard) plus a mobile tab view (`:15-21`, `:180-233`). The subscription list query is `['subscriptions']` at `:46-51`, with `refetchInterval: 5_000` and `staleTime: 10_000`. The selected row is held as an id and re-read from the polled list (`:43-45`, `:52`). The trade-to-marker adapter has a `TODO(backend)` (`:64-87`). The position adapter is at `:89-98`.
- Chart: `<StrategyChart interval={selectedSub.interval as Interval}>` at `:142-148` (desktop) and `:209-215` (mobile). Indicator defaults turn `engulfing: true` on (`:25-32`, localStorage key `strategies.indicators` `:23`).

List / row
- `strategy-list-sidebar.tsx` (126 lines): the filter matches `symbol`, `strategy_code` and `interval` (`:17-26`). "+ New" opens `NewSubscriptionDialog` (`:52-58`, `:123`). Rows are `StrategyCard` (`:99-106`).
- `strategy-card.tsx` (83 lines): `toRowState` (running/starting/stopped from `actual_state`/`desired_state`, `:10-16`). The LIVE/PAPER badge comes from `broker === 'exness'` (`:21`, `:62-64`). It shows `{sub.interval} · {sub.strategy_code}` (`:77`). The row has no position, pending order, decision or freshness column.

Detail / config / actions
- No drawer exists. The detail is `strategy-config-card.tsx` (179 lines) in the main column. It shows the Symbol, Exchange, Interval (`:109-112`), Strategy and Sub ID rows. Start/Stop is `StartStopButton` (`:74-81`, label `${code} · ${sub.interval}`). Delete is `handleDelete` (`:45-52`). Delete uses `window.confirm` with the interval in its text, and it is disabled while running (`:151-159`).
- `start-stop-button.tsx` (172 lines): Start confirms only for exness, Stop always confirms (`:15`, `:29-74`). `ConfirmDialog` (`:129-171`) is exported and reused by `exness-strip.tsx:6,101`. It is the existing real-money confirmation component.
- `lib/money-hint.ts` gives the per-broker chip/title (`moneyHint(broker, action)`); `money-hint.test.ts` covers it.
- `dashboard-column.tsx` (52 lines): the unrealized PnL badge and `RecentTradesTable` (closed trades).
- `recent-trades-table.tsx`: `StrategyTrade` type (`:3-12`).
- `exness-strip.tsx` (123 lines): safeguards query `['safeguards']` every 5 s (`:27-31`). Pause/resume mutations (`:33-40`). Resume goes through `ConfirmDialog`.

Create form
- `new-subscription-dialog.tsx` (184 lines): `const INTERVALS = ['1m','5m','15m','1h','4h','1d']` (`:7`, no `1w`). Single-select interval buttons (`:141-155`). Strategy select from `useStrategiesList` (`:33`, `:98-111`). Symbol select from active tracked symbols (`:36-39`, `:114-139`). Error codes handled: `SUBSCRIPTION_ALREADY_EXISTS`, `SYMBOL_NOT_TRACKED` (`:64-68`). No parameters field, no broker field, no edit mode.

API client and types
- `api/strategy-api.ts`: `interface Subscription` (`:7-20`) has `interval: string` (`:11`), `desired_state`, `actual_state`, `is_running` ("kept for back-compat", `:16-17`) and `broker: 'paper' | 'exness'`. Functions: `listSubscriptions` → `GET /api/v1/subscriptions/` (`:22-25`), `addSymbol` → `POST /api/v1/strategies/{code}/subscriptions` body `{symbol, interval}` (`:27-32`), `removeSubscription` → `DELETE /api/v1/subscriptions/{id}` (`:34-36`).
- `hooks/use-strategy-mutations.ts`: `startSubscription`/`stopSubscription` → `POST /api/v1/subscriptions/{id}/start|stop` (`:7-13`). Hooks `useStartStrategy`, `useStopStrategy`, `useDeleteSubscription` and `useCreateSubscription` (body `{symbol, interval}`, `:45-53`) all invalidate `['subscriptions']` (comment `:1-2`).
- `hooks/use-strategies.ts`: `useStrategiesList` → `fetchStrategies` (`GET /api/v1/backtest/strategies`), `staleTime 30_000`.
- `hooks/use-open-position.ts`: `GET /api/v1/subscriptions/{id}/positions`, first row only (`:15-20`), `refetchInterval 5_000`. The `OpenPosition` type (`:4-13`) omits `sl_price`/`tp_price`, which the backend returns (`strategy_query_service.py:69-70`).
- `hooks/use-strategy-trades.ts`: `GET /api/v1/subscriptions/{id}/trades` via raw `fetch` (`:7-11`), `refetchInterval 15_000`.
- `types/strategy.ts`: chart-side `Trade` and `OpenPosition` (17 lines).
- `api/api-client.ts`: `ApiError{status, code}` (`:3-12`). `send` adds `X-Admin-Token` from localStorage `pq.adminToken` and prompts once on 401 (`:35-57`). Exports `apiPost`, `apiPatch`, `apiDelete` and `apiFetch`. `api-client.test.ts` covers it.

Live state transport
- Everything on the strategies page is a TanStack Query poll: subscriptions 5 s, open position 5 s, safeguards 5 s, trades 15 s. No SSE or WebSocket is used there.
- `strategy-chart.tsx:30-32` has `TODO(realtime)`: the strategy chart has no live bar.
- SSE exists only for market data: `hooks/use-realtime-bar.ts:47-48` (`/api/v1/market-data/bars/stream/{symbol}?interval=`) and `hooks/use-realtime-quote.ts:78-79` (`/api/v1/quotes/stream/{symbol}`). They are used by `TradingChart` (`trading-chart.tsx:252`) and the ticker widget.
- Live orders/pending view: none exists in web.

Tests covering this area: none for the components. Web tests: `api-client.test.ts`, `chart/position-format.test.ts`, `chart/trade-hit-test.test.ts`, `lib/chart-history.test.ts`, `lib/data-lag.test.ts`, `lib/datetime.test.ts`, `lib/indicators/engulfing.test.ts`, `lib/money-hint.test.ts`, `lib/number-format.test.ts`. Backend: `tests/app_test/integration/test_strategy_subscriptions_api.py` (40 lines, one test, `test_create_refuses_an_unknown_broker`, posts `interval`, `:34-40`). Bruno files: `tests/http/strategies/{get,list,start,stop}-strategy.bru`.

Freshness inputs for the mockup's per-interval column (the mockup marks it [assumption])
- `GET /api/v1/market-data/sync-status` → `SyncStatus{symbol, interval, last_bar_at, last_sync_at, is_delayed, lag_seconds…}` (`types/market-data.ts:79-96`, `api/market-data-api.ts:34`). It is already polled by `useAvailableIntervals` (`hooks/use-available-intervals.ts:25-30`).
- `GET /api/v1/market-data/data-lag/{symbol}`, hook `use-data-lag.ts` (30 s).
- [INFERENCE, unverified] whether `sync_status.last_bar_at` moves for cascaded 5m-4h bars is not checked here.

## 2. Web backtest UI

- `components/backtest/backtest-form.tsx` (167 lines): `const INTERVALS = ['1m','5m','15m','1h','4h','1d']` (`:11`, no `1w`). Interval `useState('1m')` (`:45`). A single `<select>` (`:129-135`). Parameters is a JSON textarea (`paramsText` `:55`, parse `:76-84`, field `:146-154`). The placeholder is STF-flavoured: `'{"direction": "long", "key_level_lookback_bars": 5}'` (`:150`), and so is the error hint (`:81`). It submits `RunBacktestBody` (`:86-94`).
- `api/backtest-api.ts`: `RunBacktestBody` (`:176-187`, `interval: string`, `parameters?`). `BacktestRunDoc` (`:189-212`). `fetchBacktestRun` lifts `interval` from `config_snapshot` (`:222-256`, `:247`). `BacktestRunResult` (`:44-62`, `interval?`, `parameters?`, `config_snapshot?`). `BacktestRunRow` (`:259-271`, `interval: string`, no `parameters` field although the route sends it). `listBacktestRuns` filters by `interval` (`:281-286`). `listAllBacktestRuns` fans out over `fetchStrategies` (`:290-302`).
- `run-compare-view.tsx` (50 lines): legend `{strategy_code} · {config_snapshot.symbol}` (`:36-43`); no interval or parameters shown. Max 3 runs (`:15-19`).
- `metrics-diff-table.tsx` (71 lines): column header = `strategy_code` + `config_snapshot.symbol` (`:48-50`); `METRIC_ROWS` (`:9-24`); no interval/parameter rows.
- `run-history-rail.tsx` (166 lines): `INTERVALS = ['', '1m', … '1d']` (`:9`, no `1w`). Interval filter (`:52`, `:57`, `:107-111`). "Compare N" appears at ≥2 runs (`:79-85`) and selection is capped at 3 (`:135`).
- `run-list-item.tsx:34`: `{row.symbol} · {row.interval}`.
- `run-header.tsx` (147 lines): props `symbol?`, `interval?` (`:12-13`). `pair = [symbol, interval].join(' · ')` (`:70`). No parameters shown. Its only caller is `backtest-detail-pane.tsx:40-49` (`interval={run.interval}` `:47`).
- Compare route `routes/backtest_.compare.tsx` (`?runs=a,b,c`, `:9-17`).
- `backtest-result-view.tsx:25,32`: backtest chart indicators default `engulfing: false`.
- Backend: `RunBacktestCommand` (`engine/backtest/backtest_command_service.py:17-33`, `interval: str`, `parameters: dict | None`). `BacktestConfig` dataclass (`core/domain/backtest/config.py:10-24`, `interval: str`, `parameters: dict`). The `backtest_runs` document stores top-level `symbol`, `interval`, `parameters`, `config_snapshot` (`core/domain/backtest/entities.py:59-75`). List route `GET /api/v1/backtest/strategy/{strategy_id}?symbol=&interval=` (`app/routes/backtest.py:158-197`). Index `ix_backtests_strategy_symbol_interval_started` (`backtest_repository.py:125-128`). Query `query["interval"] = interval` (`:50-51`).
- Bruno: `tests/http/backtest/run-backtest.bru:14-16` and `list-results.bru:13` use `hitnrun2` and `interval`.
- Tests: no web test covers backtest components.

## 3. Engulfing mirror comment and golden fixture

- Mirror comment: `web/src/lib/indicators/engulfing.ts:4-6`:
  `// Mirror of the Python detector in` / `// src/pocketquant/core/domain/strategy/patterns/engulfing_detector.py.` / `// Locked to it by the shared golden fixture (engulfing.test.ts).`
- Second comment naming the Python side: `web/src/lib/indicators/engulfing.test.ts:4-5`: `// Same fixture as the Python detector test. Keep the two copies byte-identical;` / `// no check diffs them.`
- Web fixture: `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json`. Web test: `engulfing.test.ts` (`describe('detectEngulfing golden-fixture parity')`, `:22-31`).
- Python fixture (separate copy): `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json`. Python test: `tests/core_test/unit/domain/strategy/patterns/test_engulfing_detector.py` (header `:1-2` "Python half of the cross-runtime lock", `_FIXTURE` `:13`).
- Web consumers of the overlay: `engulfingMarkers` in `strategy-chart.tsx:22,182-192` and `trading-chart.tsx:25,353-364`. The toggle is `controls/indicator-toggles.tsx:9` (label `Engulf`). `IndicatorConfig.engulfing` is at `types/market-data.ts:151`. Defaults: `routes/index.tsx:32` (true), `strategies-page-layout.tsx:31` (true), `backtest-result-view.tsx:32` (false). `STRONG_THRESHOLD` lives in `engulfing.ts`, and `docs/swing-pivot-key-level.md:15` names it.
- Other STF test files (backend scout owns them): `tests/backtest_test/engine/test_{engulfing,engulfing_pullback30_touch,hitnrun2}_backtest.py`, `tests/core_test/unit/domain/strategy/test_{engulfing,engulfing_pullback30_touch,hitnrun2}.py`.

## 4. Chart: interval switcher, overlays

- Main chart page `routes/index.tsx`: `useAvailableIntervals(symbol)` (`:66`) → `AppHeader` → `IntervalSelector` (`layout/app-header.tsx:1,27`). The selection is persisted per symbol (`:62-72`).
- `controls/interval-selector.tsx` (43 lines): props `intervals: IntervalOption[]`, `value`, `onChange`. It disables intervals with no completed sync ("No data synced for this timeframe", `:33-40`). It is reusable for a per-subscription switcher fed with the subscription's `intervals`.
- Interval lists in web (5 copies):
  - `hooks/use-available-intervals.ts:6-10`: `INTERVAL_ORDER` includes `1w`, with labels at `:12-16`.
  - `constants/active-intervals.ts:3`: `ACTIVE_INTERVALS` includes `1w`, "keep in sync with backend SYNC_INTERVALS".
  - `types/market-data.ts:143`: `type Interval = '1m'|'5m'|'15m'|'1h'|'4h'|'1d'|'1w'`.
  - The three form lists without `1w`: `new-subscription-dialog.tsx:7`, `backtest-form.tsx:11`, `run-history-rail.tsx:9`.
- `strategies/strategy-chart.tsx` (311 lines): no symbol/interval controls by design (`:42-44`). Props `interval: Interval` (`:34-40`). The view resets on interval change (`:71-74`). Trade markers and engulf markers are merged into one marker plugin (`:182-192`). Entry/liq price lines come from `openPosition` (`:217-265`). No SL/TP lines and no pending-order line.
- `chart/trading-chart.tsx` (601 lines): live SSE bar (`:252`). Engulf markers (`:353-364`). Backtest position boxes come from `chart/position-box-primitive.ts` (268 lines). `docs/system-architecture.md:39` names "the position box in `web/`" as a one-exit layer.
- `controls/indicator-toggles.tsx:4-11`: SMA/EMA/RSI/MACD/BB/Engulf. The UI has no strategy overlays apart from Engulf; the mockup says "no strategy overlays", and the owner keeps the Engulf overlay (A10).

## 5. API routes (FastAPI, app layer)

Mount: `api = APIRouter(prefix=settings.api_prefix, dependencies=[Depends(verify_admin_token)])` (`app/main_extensions.py:332-336`). `api_prefix = "/api/v1"` (`core/config.py:45`). Routers are included at `main_extensions.py:350-357`.

`src/pocketquant/app/routes/strategy.py` (119 lines)
- `CreateSubscriptionBody{symbol, interval, broker: Literal["paper","exness"]="paper"}` (`:13-16`).
- `GET /api/v1/strategies/` → `list_strategy_templates` (`:28-32`). `GET /api/v1/strategies/{strategy_code}` → `get_strategy_template` (`:35-43`).
- `POST /api/v1/strategies/{strategy_code}/subscriptions` (201) → `StrategyCommandService.add_symbol(code, symbol, interval, broker)` (`:46-52`).
- `GET /api/v1/subscriptions/?strategy_code=` → `StrategyQueryService.list_symbols` (`:62-67`).
- `POST /api/v1/subscriptions/{sub_id}/start` and `/stop` → `cmd_svc.start/stop` (`:70-85`). They write `desired_state` only (`strategy_command_service.py:34-44`).
- `GET /api/v1/subscriptions/{sub_id}/positions` → `get_positions` (open; `:88-93`). `GET …/trades?limit=` → `get_trades` (closed positions; `:96-102`). `GET …/metrics` → `LiveMetricsQueryService.get_metrics` (`:105-110`).
- `DELETE /api/v1/subscriptions/{sub_id}` (204) → `cmd_svc.remove_symbol` → `SubscriptionRepository.delete` (`:113-119`). No PATCH or edit route exists. No close or cancel route exists.
- Services: `engine/strategy/strategy_query_service.py` (91 lines). `list_symbols` returns `id, strategy_code, symbol, interval, created_at, desired_state, actual_state, is_running, broker` (`:35-57`). `get_positions` (`:59-73`). `get_trades` (`:76-91`). `engine/strategy/strategy_command_service.py` (92 lines). `add_symbol` (`:48-89`) checks the symbol is tracked (`SYMBOL_NOT_TRACKED`), checks the registry, and refuses exness when the stored live flag is false (`BROKER_DISABLED`, `:61-66`). It builds `Subscription(... interval=Interval(interval) ...)` with no parameters (`:71-80`).

`src/pocketquant/app/routes/safeguards.py` (72 lines)
- `GET /api/v1/admin/safeguards` (public read, 1 s per-process cache, `:23-37`). `POST …/pause` and `…/resume` (`:40-51`). A store write failure returns 503 (`:57-61`). Body = `Safeguards` fields + `live_trading` + `entries_paused` (`:71-72`).
- Tests: `tests/app_test/integration/test_safeguards_api.py` (`:39-133`, 7 tests) and `test_admin_token_guard.py`.

Backtest routes `app/routes/backtest.py`: `GET /backtest/strategies` (`:41-43`, `STRATEGY_REGISTRY.keys()`), `POST /backtest/run` (`:48-60`), `GET /backtest/{run_id}` (`:63`), `/verdict` and `/name` PATCH (`:72`, `:82`), `/equity` `/trades` `/trade-markers` `/stats` `/orders` (`:92-148`), `GET /backtest/strategy/{strategy_id}` (`:158-197`).

How the api reads trader state from Redis
- Keys (`core/common/constants.py:20-25`): `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`, `ohlcv:{symbol}:{interval}:{limit}`, `data_lag:{symbol}`. TTLs are at `:28-32`. Other keys: `job_stats:{job_id}:{window}` (`routes/system_jobs.py:48`) and `rate_limit:{ip}` (`core/common/rate_limit/middleware.py:42`).
- Writer: the trader writes `quote:latest` (`engine/market_data/app_services/quote_app_service.py:57`) and `bar:current` (`bar_app_service.py:309-386`).
- Reader: the api's SSE routes poll Redis through `app/common/sse_poll.py::poll_stream` (40 lines). `GET /api/v1/quotes/stream/{symbol}` → `cache.get(quote:latest…)` (`routes/market_data_quotes.py:68-79`). `GET /api/v1/market-data/bars/stream/{symbol}?interval=` → `BarAppService.get_current_bar` (`routes/market_data.py:195-207`).
- No per-subscription Redis key exists today. Subscription state reaches the api only through Mongo (`actual_state` written by the reconcile loop; `strategy_query_service.py:33-34`).
- `Cache` (`core/infra/persistence/redis.py:15`) has `get`, `mget`, `set`, `delete`, `delete_pattern`, `exists` (`:44-107`). It has no list operations. [INFERENCE] The bounded "recent decisions" ring in the mockup needs a new `Cache` method or a capped list kept inside one JSON value.
- The symbol-removal cascade deletes only the four symbol key patterns (`engine/market_data/tracked_symbols_service.py:129-137`). [INFERENCE] A new per-subscription snapshot key is not covered by that cascade or by `DELETE /subscriptions/{id}`, unless it has a TTL or an explicit delete.
- `docs/system-architecture.md:20` states the Redis/SSE poll rule ("the shortest bar interval is one minute").

## 6. Docs

Line counts (limit 800): `docs/deployment.md` 230, `docs/code-standards.md` 157, `README.md` 93, `docs/governance/documentation-rules.md` 52, `docs/system-architecture.md` 48, `CLAUDE.md` 38, `docs/governance/no-look-ahead-rules.md` 22, `docs/swing-pivot-key-level.md` 16, `docs/governance/README.md` 12. All are far below the limit.

`docs/system-architecture.md` lines that state SL/TP-only, one exit, or a single position:
- `:12` — "**Exits are SL/TP only.** The risk check rejects EXIT and FLAT signals and any entry against an open position. A paper position closes at its SL or TP. An Exness position closes only at the venue's SL, TP or a stop-out. Unloading a subscription leaves a venue position open under its own SL/TP."
- `:34` — "A strategy that adds to a position sizes each add against the full paper balance. No current strategy adds; each holds at most one position." The second sentence says "current strategy"; [INFERENCE] review it after STF deletion.
- `:37-48` — section "### One take-profit per entry, closed in full". `:39` says there is no scale-out, no multi-TP and no partial close, and that four layers plus the web position box change together. The table `:41-46` covers Signal `take_profit_price`, the strategy hook `Signal | None`, the paper exit `_check_sl_tp`/`_fire_synthetic_exit`, and the position store `{subscription_id}:{symbol}`. `:48` says "The Exness broker also sends one take-profit per order."
- `:20` — the Redis/SSE poll rule (touched only if the snapshot uses SSE).

Other doc lines bound to STF or to the single-interval subscription:
- `docs/code-standards.md:93` — "`subscription_id` is the UUIDv7 of one `(strategy_code, symbol, interval)` binding."
- `docs/code-standards.md:95` — "The only duplicate guard … is the unique index `ix_subscriptions_dedup_triple` … `add_symbol` upper-cases `symbol` …". The index name and the triple both change with `intervals`.
- `docs/swing-pivot-key-level.md:1-16` — the whole file is about the engulfing strategy: `engulfing_strategy_service.py` (`:3`), "held by the engulfing strategy itself" (`:7`), `EngulfingStrategyService.on_bar_completed` and its gates (`:13`), the strategy's `max_rejection_wick_pct` (`:15-16`). No doc links to it (grep). [INFERENCE] After the STF deletion only the overlay-related facts survive (marker ≠ entry no longer applies; `STRONG_THRESHOLD` is a web constant). Per the documentation rules the file is deleted or cut. Deleting a doc needs no new-file approval; adding one does (`documentation-rules.md:52`).
- Requested grep `git grep -n -i -E "SL/TP only|sl/tp-only|one take-profit|hitnrun2|engulfing|interval" -- docs README.md CLAUDE.md` (excluding journals): 14 hits. Besides the lines above: `README.md:59,63,64` and `docs/deployment.md:224` are market-data sync examples with `"interval"` (unaffected). `hitnrun2` appears in no doc. `CLAUDE.md` has no hit.
- `docs/deployment.md:124` ("restores each open direction from the open positions (`StrategyAppService.take_over`)") holds for one position per subscription. [INFERENCE] Pending stop orders are not restored by that path; check it when pending orders land.
- Tracked root `TODO.md`, `question.md`, `questions.md` are outside the documentation-rules scope (`documentation-rules.md:7`). `questions.md:9` mentions `engulfing:true` defaults.

## 7. Prod ops recipe

Sibling conventions to reuse (`plans/261028-0652-exness-only-parallel-runtime/plan.md`)
- Conventions `:49-68`: entry gate with a clean `git status --porcelain -- src web deploy tests scripts docs` (`:53`). [ASK] questions to the owner are in Vietnamese with `Recommended:` first (`:54`). Every `develop:master` push is an [ASK] (`:57`). Report paths are written from the repo root (`:59`). No plan ids in code or commits (`:60`). `git grep`, because `rg` is not installed (`:64`). Prod logs: strip ANSI with `sed 's/\x1b\[[0-9;]*m//g'` (`:65`). OOM rule (`:66`). Secrets never go on a command line (`:68`).
- Ops recipe `:70-80`:
  - SSH key normalisation: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')`, and `rm -f .cache/ssh/vps_key` at the end (`:73`).
  - Push with the camping89 token URL; a release is `develop:master` (`:74`).
  - `GH_TOKEN=$(gh auth token --user camping89)` and `sleep 15` before a run-id lookup (`:75`).
  - Tests need Docker; the expected local red is `4 failed, 4 errors` in the tzset/cron files (`:77`).
  - `lint-imports` currently prints `Contracts: 6 kept, 0 broken.` (`:78`).
  - The ratchet is flexible: raise the ceiling in its own commit (`:79`).
  - Containers: `dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }` in `/opt/pocketquant/deploy`, then `dc exec -T api|worker|trader …` (`:80`).

Container names now
- `deploy/compose.prod.yml`: services `api` (`:76`, `APP_ROLES: "api"`, pinned `EXNESS_LIVE_TRADING: "false"`), `worker` (`:92`), `trader` (`:109`, `stop_grace_period: 180s`, healthy = warm standby). None has a `container_name`, because a deploy starts a second copy beside the old one (`:72-73`).
- Fixed names: `pocketquant-web` (`:25`), `pocketquant-cloudflared` (`:50`), `pocketquant-mongodb` (`:130`), `pocketquant-redis` (`:157`), `pocketquant-portainer` (`:179`). The pre-cutover `pocketquant-app` used in early sibling phases no longer exists.

Read prod Mongo read-only (pattern proven in sibling phases 09-10; there `python -c` was run through `dc exec -T api`)
- Settings fields: `get_settings().mongodb_url` (`MongoDsn`, `core/config.py:47`) and `.mongodb_database` (`:48`).
- Template (run from the repo root after the key step; no secret on the command line):
  `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }; dc exec -T api python -c "from pymongo import MongoClient; from pocketquant.core.config import get_settings; s=get_settings(); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]; [print(d[\"_id\"], d[\"strategy_code\"], d[\"symbol\"], d.get(\"interval\"), d[\"actual_state\"], d.get(\"broker\")) for d in db.subscriptions.find()]"'`
- Quirks (user memory, 2026-10-31): `docker exec -i` inside a script piped to `ssh 'bash -s'` swallows the rest of the script, so drop `-i` or use `< /dev/null`. Long nested-quote Bash commands fail in this shell, so write them to a `.cache/` script and run `bash <file>` / `ssh … 'bash -s' < file`.
- An HTTP read without Mongo also works: `dc exec -T api python -c "import json,urllib.request as u; …urlopen('http://localhost:41921/api/v1/subscriptions/')…"` (sibling `phase-10*.md:157,179`).
- The prod Mongo backup recipe exists (`docs/deployment.md:161-175`). The owner decided no dump before the STF delete (advice "Needs from you" 2).

Deploy and CI trigger rules
- `docs/deployment.md:5-19`: a `develop` push runs tests only, and `master` is production. A release is `git push origin develop:master` (fast-forward). `master` must stay an ancestor of `develop` (no CI check). `gh workflow run cicd.yml --ref master` redeploys.
- `.github/workflows/cicd.yml:3-11`: it triggers on a push to `master`/`develop` with `paths-ignore: docs/**, plans/**, **/*.md, LICENSE`, plus `workflow_dispatch`. `tests` runs on every trigger with a 3-zone TZ matrix (`:27-30`): `uv sync --frozen`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`, `uv run pytest tests/ -q` (`:40-56`). `build-app`, `build-web`, `cleanup-tags` and `deploy` run only on `refs/heads/master` (`:61`, `:107`, `:152`, `:195`). Deploy: rsync `compose.prod.yml` + `.env` + `deploy/vps/` to `/opt/pocketquant/deploy/` (`:227-237`), then `bash deploy/vps/10-deploy.sh` (`:239-242`) and `11-verify.sh` (`:244-247`). A master run is never cancelled (`:13-17`).
- `deploy/vps/10-deploy.sh:12-18`: it `cd`s to `deploy/` and takes the deploy lock `/opt/pocketquant/deploy.lock`. A manual re-roll is `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh` (`:9`). VPS scripts in the repo: `10-deploy.sh`, `11-verify.sh`, `90-cleanup.sh`, `leases.sh`.
- `docs/deployment.md:122-135` ("Restart while live") applies only while an `exness` subscription exists; prod has none (advice Prod checks).

Collections and the link to a subscription / strategy (repositories in `src/pocketquant/core/infra/persistence/repositories/`)

| Collection | Name source | Link field(s) | Index on link |
|---|---|---|---|
| `subscriptions` | literal `_collection_name = "subscriptions"` (`subscription_repository.py:15`; not in `constants.py`) | `_id` = subscription id; `strategy_code`, `symbol`, `interval`, `desired_state`, `actual_state`, `broker` (`core/domain/subscription/entities.py:40-50`) | `ix_subscriptions_strategy_code`; unique `ix_subscriptions_dedup_triple` (`:73-84`) |
| `positions` | `COLLECTION_POSITIONS` (`constants.py:10`) | `subscription_id` only (`core/domain/position/entities.py:243`), `is_closed` | `ix_positions_subscription_id` (`position_repository.py:54`) |
| `orders` | `COLLECTION_ORDERS` (`constants.py:9`) | `subscription_id` only (`core/domain/order/entities.py:176`), `status` | `ix_orders_subscription_id` (`order_repository.py:29`) |
| `trades` | `COLLECTION_TRADES` (`constants.py:11`) | `run_id` = subscription id ("Live trades set run_id to the subscription_id", `trade_repository.py:24-27`) + `strategy_code` (`core/domain/trading/value_objects.py:107-108`) | `ix_trades_run_id`, `ix_trades_run_entry` (`:48-52`) |
| `backtest_runs` | `COLLECTION_BACKTEST_RUNS` (`constants.py:12`) | `strategy_code`, `symbol`, `interval`, `parameters` (`core/domain/backtest/entities.py:59-75`) | `ix_backtests_strategy_code` and others (`backtest_repository.py:118-140`) |
| `backtest_orders` | `COLLECTION_BACKTEST_ORDERS` (`constants.py:13`) | `run_id`, `strategy_code` (`core/domain/order/records.py:18-21,39-40`) | `ix_btorders_run_id`, `ix_btorders_strategy_code_status` (`backtest_order_repository.py:54-57`) |
| `backtest_trades` | `COLLECTION_BACKTEST_TRADES` (`constants.py:14`) | `run_id`, `strategy_code` | `ix_bttrades_run_id`, `ix_bttrades_strategy_code_direction` (`backtest_trade_repository.py:177-180`) |

- [INFERENCE] STF delete filter: `S = subscriptions.find({strategy_code: {$in: [hitnrun2, engulfing, engulfing_pullback30_touch]}})._id`. Then delete `positions.subscription_id ∈ S`, `orders.subscription_id ∈ S`, `trades.run_id ∈ S`, and `backtest_runs|backtest_orders|backtest_trades.strategy_code ∈ STF`. Also count `positions/orders/trades` whose subscription id is in no subscription document (orphans) and show them to the owner separately. The advice's Prod checks counted 234 positions, 241+18 orders, 215 trades and 21 backtest runs, but did not count `backtest_orders`/`backtest_trades`.
- `TrackedSymbolService.remove` cascades every collection above by symbol (`tracked_symbols_service.py:93-100,120-137`). Never use it (advice).
- Unique index change: [INFERENCE] prod already holds `ix_subscriptions_dedup_triple` on the old keys, so the index rename or drop must be planned in the deploy step (see finding 8).

## 8. Web quality gates

- `web/package.json` scripts: `dev` (vite), `build` (`tsc -b && vite build`), `lint` (`eslint .`), `preview`, `test` (`vitest run`), `test:watch`.
- Commands (run in `web/`): `npm run lint`, `npx tsc -b` (the type check; build info goes to `node_modules/.tmp`, `tsconfig.app.json:3`; `noEmit: true` `:16`), `npm test`, `npm run build`.
- Baseline on `e4a998b8` (run 2026-11-01 15:52 local): vitest 70/70 pass in 9 files. eslint 0 errors, 6 warnings (one is `react-hooks/exhaustive-deps` in `routes/monitor_.jobs.$jobId.tsx:49`). `tsc -b` exit 2, with 2 errors in `components/monitor/job-status-palette.ts:3,13`.
- `tsconfig.json` references `tsconfig.app.json`, `tsconfig.node.json` and `tsconfig.test.json`. The test tsconfig includes only `src/**/*.test.ts` with `vitest/globals`.
- CI: no web job (finding 2). `justfile` has only `fe` (`npm run dev`) for web; it has no web lint/test recipe.
- The comment and docstring rule covers TS too: no `/** */` blocks (`CLAUDE.md`).

## Unresolved questions

1. Fix the 2 pre-existing `tsc` errors in `job-status-palette.ts` inside this plan, so the web gate starts green, or leave them out of scope?
2. Raise the compare cap above 3 runs, or restate the "four backtests in the compare view" success metric as two views?
3. Add a web gate (lint + `tsc -b` + vitest) to CI in this plan, or keep the web gate local-only as today?
4. UI tests: extract pure helpers tested as `*.test.ts`, or add jsdom + testing-library (a new dev dependency)?
5. `docs/swing-pivot-key-level.md`: delete it with the STF code, or cut it to the overlay facts?
6. Where do strategy-declared default parameters reach the form: extend `GET /api/v1/strategies/{code}` (no web caller today) or `GET /api/v1/backtest/strategies` (the web's current source)?
