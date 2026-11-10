# Planner debate candidate 2: money-path correctness and no look-ahead

Date 2026-11-01 (Asia/Bangkok). Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8`. Paths are relative to `src/pocketquant/` unless they start with `tests/`, `web/`, `docs/`, `scripts/`, `.github/` or `plans/`. Every `path:line` was read on `e4a998b8`; `[UNVERIFIED]` marks what I could not read.

## 1. Lens statement

I planned from the two places where this change can lose real money or fake a backtest: (a) the strategy reads a higher-timeframe (HTF) bar that was not final at decision time, and (b) an order path closes, opens or cancels the wrong thing. Five facts I found in the code shape the plan beyond the evidence packet:

1. **Live partial-bar race.** The trader publishes the entry bar at the bucket boundary from ticks (`engine/market_data/app_services/bar_app_service.py:108-128`), but `sync_1m` writes the last 1m bar and re-cascades only at second 12 (`engine/strategy/strategy_app_service.py:46-47`, advice Corrections). At 11:00:00 the stored 10:00 1h bar is still partial, yet `datetime + step <= instant` admits it. A "closed" filter alone breaks "backtest view = live view". The plan adds a "final" check (`updated_at >= bucket end`, `core/domain/bar/entities.py:42-44`, `core/infra/persistence/repositories/bar_repository.py:42-98`) and a live wait to second 20.
2. **The wait must never block the event bus.** `EventBus.publish` awaits handlers one by one (`core/common/messaging/event_bus.py:28-38`), and `add_tick` awaits the publish (`bar_app_service.py:108-128`). So a live multi-interval decision runs as a task, like venue entries already do (`strategy_app_service.py:422-430`).
3. **Warm-up does not pass through `_on_bar_completed`.** It calls `strategy.on_bar_completed` directly (`strategy_app_service.py:252-264`) under `_lock`, with a "No I/O" invariant (`:250`). Advice "what could be better" item 2 is false. The plan preloads HTF bars before the replay and reuses the same pure filter.
4. **Order persistence drops SL/TP.** `OrderAggregate.to_mongo`/`from_mongo` omit `sl_price`/`tp_price` (`core/domain/order/entities.py:172-205`). A pending stop restored after a restart would fill without a stop loss. Fixed in Phase 06.
5. **An EXIT can race an SL fill and open a reverse position.** The paper fill path treats an opposite order with no live position as a new open (`core/infra/brokers/paper/paper_broker_adapter.py:337-358`). So does the position store (`engine/execution/position_app_service.py:49-80`). The plan adds `OrderAggregate.reduce_only`. Both brokers reject a reduce-only order when no opposite position is held. This also makes a manual close that runs twice harmless.

## 2. Answers to Q1-Q11

| Q | Choice | Reason and evidence |
|---|---|---|
| Q1 | Store `intervals` (ordered list, lowest first) and a derived scalar `intervals_key = ",".join(intervals)`. Put a unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`. `ensure_indexes` drops `ix_subscriptions_dedup_triple` if it exists. | A unique multikey index is enforced per element (scout-backend trap 1). A new name avoids the same-name key conflict (`core/infra/persistence/repositories/subscription_repository.py:79-83`). The drop follows the drop-then-create precedent (`job_history_repository.py:322-341`). The server sorts the list, so `["1h","15m"]` and `["15m","1h"]` get the same key. |
| Q2 | Add a `manual_action {id, kind: close\|cancel, requested_at}` field on the subscription document. The api sets it only when it is empty (otherwise 409). The lease holder's reconcile loop runs it through the engine's own exit/cancel helpers and writes `last_action {id, kind, outcome, at}`. A request older than 30 s when the trader sees it expires unexecuted. | Routes only write Mongo and the trader owns the brokers (`engine/live/strategy_reconcile_app_service.py:20-23`). The loop runs only on the lease holder (`app/roles.py:203-206`) and already reads every subscription each tick (`:77-80`). A handover keeps the request, which Redis pub/sub would lose. A duplicate close does no harm because of `reduce_only`. |
| Q3 | Start `PositionAppService` in the backtest sandbox (its in-memory repo exists). EXIT size and the risk check read the tracker in every path. | Today the tracker never starts in a backtest (`engine/backtest/backtest_sandbox_app_service.py:120-139`), so the risk check always sees "no position" there (`strategy_app_service.py:545-552`). That makes the backtest view differ from live, which `docs/governance/no-look-ahead-rules.md` forbids. With one quantity source there is one EXIT path. |
| Q4 | Restore every open paper row. Delete the no-SL/TP drop branch. Also restore paper pending stops. | Once strategies can EXIT and the UI can close manually, a row with no SL/TP can be closed (`strategy_app_service.py:157-165`). Dropping it on each restart would lose a real position record. |
| Q5 | Reconcile compares the loaded `(intervals, parameters)` with the document. When they differ and the instance is not running, it unloads, then loads. Edit is refused while the subscription is running, holds an open position, or has an active order. | The loop never reloads (`strategy_reconcile_app_service.py:119-120`). Unloading drops a paper position silently (`strategy_app_service.py:315-320`), so an edit with exposure would destroy state. |
| Q6 | Change `build_backtest_sandbox(bar_repository, calendar_factory)` and have its one caller pass the real ones. Move `NoStoredBars` and `Continuous24x7CalendarFactory` to `tests/strategy_stubs.py`. Context reads use only `BarRepository.find`, which the stub already has. | The caller already holds both (`engine/backtest/backtest_execution_service.py:59,63,120`). The stubs become dead in src, so they move to tests in the same change. A single-interval config never reads context, so the fixtures that build the engine with the stub keep passing. |
| Q7 | Fix the two `tsc` errors (`web/src/components/monitor/job-status-palette.ts:3,13`). Add a `web` CI job (lint, `tsc -b`, vitest) that `build-web` needs. Test the UI through pure helpers in `*.test.ts`, with no jsdom. | This plan adds real-money buttons. `vite build` does no type check (`web/Dockerfile`), so a type error would ship silently. Pure helpers match the existing vitest setup (`web/vitest.config.ts`, node env). |
| Q8 | Raise the compare cap to 6 through one constant used by the route, the view and the rail. The view uses `useQueries`. | 3 interval sets x 2 variants = 6 runs. Today three places each hard-code 3 (`web/src/routes/backtest_.compare.tsx:16`, `run-compare-view.tsx:17-19`, `run-history-rail.tsx:135`). C9 asks for the existing compare view, not a metric change. |
| Q9 | Delete `docs/swing-pivot-key-level.md`, its link, and the stale strategy comment in `web/src/lib/indicators/engulfing.ts:62-64`. Keep `scripts/rubric/static_audit.py`, but read the class `DEFAULTS` in place of the AST `_DEFAULTS` finder. | Every line of the doc is about the engulfing strategy (scout-web finding 6). `run_rubric.py:36` still uses the audit, so the script stays. With `DEFAULTS` as a class attribute it needs no AST parse (`static_audit.py:39-51`). |
| Q10 | `GET /strategies/{code}` returns `parameters` (the class `DEFAULTS`). Both forms call it. `GET /backtest/strategies` stays a code list. | It is the strategy resource (`app/routes/strategy.py:35-43`). It has two callers (the subscription form and the backtest form). Nothing else changes. |
| Q11 | Key `strategy:snapshot:{subscription_id}` with a 7-day TTL. `StrategyCommandService.remove_symbol` deletes it. | Removing a tracked symbol calls `remove_symbol` for each subscription (`engine/market_data/tracked_symbols_service.py:120-125`), so one delete covers both paths. The TTL clears a key the trader rewrites in the up-to-5 s before the orphan unload (`strategy_reconcile_app_service.py:166-178`). |

## 3. Phases

| # | Title | Deploy | Depends on | Effort |
|---|---|---|---|---|
| 01 | Spike in a throwaway worktree: go/no-go per piece | none | - | 1d |
| 02 | 1d cascade for session calendars | D-1 | 01 | 0.5d |
| 03 | Delete STF code | none (CI) | 02 | 0.5d |
| 04 | Subscription contract: intervals, parameters, edit, defaults, reload | none | 03 | 1d |
| 05 | HTF context from Mongo: closed+final filter, shared cache, live/warm-up/backtest | none | 04 | 1.5d |
| 06 | Capabilities: stop entry, EXIT, reduce-only, paper, Exness behind the flag, restore, architecture doc | none | 05 | 2.5d |
| 07 | Snapshot to Redis, manual-action channel, read endpoints | none | 06 | 1d |
| 08 | Web gates and the generic subscription UI | none | 07 | 2d |
| 09 | Backtest intervals and compare view | none | 08 | 1d |
| 10 | Triple Screen strategy | none | 09 | 1d |
| 11 | Prod migration and deploy D-2 | D-2 | 10 | 0.5d |
| 12 | Prod backtests, pick the live set, start one paper subscription | none | 11 | 1d + 24h |
| 13 | Prod STF data delete | none | 12 | 0.5d |
| 14 | Paper run observation | none | 13 | days (wait) |
| 15 | One-week 1d comparison and plan close | none | 14, D-1 + 7 days | 0.5d |

### Conventions (every phase)

- Phases run in strict numeric order, one fresh worker per phase. The **entry gate** runs first. A miss edits nothing and ends with three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: --from NN after <UTC>`. Every gate checks that `git rev-parse --abbrev-ref HEAD` prints `develop` and `git status --porcelain -- src web deploy tests scripts docs` prints nothing. A gate also accepts the state this phase's own finished tasks left, and skips a task whose Verify already passes.
- **[ASK]**: ask the owner in Vietnamese, starting with `Recommended: <reply>` and a one-line reason. Only an explicit yes counts; no approval carries forward. **[USER]**: the owner acts and replies with a stated token.
- **Failure protocol**: a failed Verify stops the phase and goes to `kongming` with the command, its output and the task. A `NOT_YET` exit does not.
- Every Verify runs from `D:/w/_me/algotrading/pocketquant`. Search uses `git grep` (`rg` is not installed). Code, comments, test names and commits are English, carry no plan ids or phase numbers, and follow `CLAUDE.md` KISS limits. Secrets never go on a command line.
- **Standard gates** (G): `docker ps >/dev/null || ("/c/Program Files/Docker/Docker/Docker Desktop.exe" & sleep 60)`, then:
  - G1 `uv run python -m pytest tests/ -q 2>&1 | tail -1 | grep -cE "^4 failed, [0-9]+ passed, .*4 errors"` prints `1` (the expected tzset red, `tests/core_test/unit/common/test_utc_runtime_guard.py`, `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`).
  - G2 `uv run lint-imports | grep -c "Contracts: 6 kept, 0 broken."` prints `1`.
  - G3 `uv run python scripts/code_metrics.py --ratchet; echo $?` prints `0`. When only a ceiling fails, raise `pyproject.toml:131-132` by the smallest amount in its own commit, `chore(metrics): raise code metric ceiling`, and name it in the phase report.
  - G4 (web phases) `cd web && npm run lint && npx tsc -b && npm test; echo $?` prints `0`.
- **Push**: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`. Check: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. CI check: `sleep 15; GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json conclusion -q '.[0].conclusion'`. Poll it until it prints `success`.
- **Ops recipe** (copied from `plans/261028-0652-exness-only-parallel-runtime/plan.md:70-80`):
  - Key: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
  - Host and compose helper: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')`, then `dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }` inside `/opt/pocketquant/deploy`.
  - Prod Python: write it to `.cache/<name>.py` and run `ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; docker compose -f compose.prod.yml --env-file .env exec -T api python - <args>' < .cache/<name>.py`. The script reads settings with `get_settings()`, never from a command line.
  - Logs: strip ANSI with `sed 's/\x1b\[[0-9;]*m//g'`.
  - Every phase that made the key ends with `rm -f .cache/ssh/vps_key`, also on a `NOT_YET` exit.
  - Every deploy (`develop:master` push) is an [ASK]. It records `free -m` on the VPS before and after in `plans/261101-0843-stf-to-mtf-foundation/reports/deploys.md`.

## 4. Phase detail

### Phase 01: Spike (go/no-go per piece, C11)

Entry gate: the conventions gate, and `git log -1 --format=%h` prints `e4a998b8` or a descendant.
Rollback: `git worktree remove --force ../pocketquant-spike && git branch -D spike/mtf`. `develop` is never touched.

- **T1.1 Worktree.** Goal: an isolated rough-code area. Files: none in `develop`. Steps: (1) `git worktree add ../pocketquant-spike -b spike/mtf develop`. (2) Run G1 inside it. Success: the baseline red is exactly the tzset 4+4. Verify: `cd ../pocketquant-spike && git rev-parse --abbrev-ref HEAD` prints `spike/mtf`.
- **T1.2 S1 unique key.** Goal: prove trap 1. Steps: write a throwaway pytest on the test Mongo. A unique index on `(code, symbol, intervals)` rejects `["15m","4h"]` after `["15m","1h"]`. A unique index on `intervals_key` accepts it. Success: both assertions hold. Verify: `uv run python -m pytest tests/spike/test_s1.py -q` reports `2 passed`.
- **T1.3 S2 context path.** Goal: prove the Mongo context path in all three paths. Steps:
  1. In `strategy_app_service.py` add a rough filter `b.datetime + step <= bar_start + entry_step` plus "newest bar `updated_at >= its end`".
  2. Add a cache keyed `(symbol, interval)`, refreshed when `bar_start + entry_step >= valid_until`.
  3. Write three tests with 15m entry and 1h context. Live: a published event with `bar_end` set and a fake clock. Warm-up: `start_strategy` over stored bars that cross a boundary. Backtest: the sandbox with the real `BarRepository`, seeded with a partial current-hour 1h bar.
  4. Each test asserts that the first 15m bar of each hour sees the previous hour's close, and that `find` is called once per hour, not once per bar.
  Success: all three pass. Verify: `uv run python -m pytest tests/spike/test_s2.py -q` reports `3 passed`. **No-go = stop: [ASK] to rethink (C11).**
- **T1.4 S2 prod measurement (read-only).** Goal: evidence for the final check and the 20 s wait. Steps: run the ops recipe with `.cache/spike_measure.py`.
  1. For 1h/4h/1d bars with `source=cascade` over the last 30 days, on all six tracked symbols: count bars whose `updated_at < datetime + step` and whose bucket ended at least 2 min before the query.
  2. Read one `job_history` document of `sync_1m` to learn the field names. Then report the p99 of `finished_at` seconds-past-minute over the last 1440 runs.
  Write both numbers to `reports/spike-go-no-go.md`. Success: the final check is GO when the count is at most 0.5% of buckets. The 20 s wait is GO when p99 is at most 18 s. Verify: `git grep -c "S2-measure:" -- plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`.
- **T1.5 S3 snapshot.** Goal: the strategy snapshot reaches the api. Steps: a rough `cache.set` per live bar in the engine, plus a rough `GET /subscriptions/{id}/snapshot`. One integration test publishes a bar and reads the route through `app_client`. Verify: `uv run python -m pytest tests/spike/test_s3.py -q` reports `1 passed`.
- **T1.6 S4 paper EXIT.** Goal: a strategy exit closes a paper position. Steps: a rough `Direction.EXIT` path. The risk check accepts EXIT when a position is open. The engine sends an opposite MARKET order for the tracker's quantity. Test it in the live engine and in the sandbox with the tracker started. Success: the position is closed, one `TradeClosedEvent` fires, and the tracker is empty. Verify: `uv run python -m pytest tests/spike/test_s4.py -q` reports `2 passed`. **No-go = stop: [ASK] to rethink (C11).**
- **T1.7 S5 paper pending stop.** Steps: a rough `_stops` dict in the paper broker. It is not triggered on the placement bar, triggers on the next bar at `max(open+spread, stop)`, and cancel-then-place leaves exactly one stop. Verify: `uv run python -m pytest tests/spike/test_s5.py -q` reports `3 passed`.
- **T1.8 S6 manual action.** Steps: a test writes `manual_action {kind: close}` on a test-Mongo subscription. One reconcile tick then closes the paper position and writes `last_action.outcome == "filled"`. Verify: `uv run python -m pytest tests/spike/test_s6.py -q` reports `1 passed`.
- **T1.9 S7 backtest with intervals.** Steps: seed one synthetic year of 15m, 1h and 4h bars. Time `BacktestExecutionService.run` once with intervals `(15m,1h,4h)` and once with `(15m,)`. Success: GO when the ratio is at most 2.0, or when the absolute time is at most 60 s. Verify: `git grep -c "S7-ratio:" -- plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`.
- **T1.10 S8 Exness spec (read-only, no venue call).** Steps:
  1. Download `https://www.exness-api.com/exness_api.yaml` to `.cache/exness_api.yaml`.
  2. Record verbatim: `closePosition` (DELETE `/positions/{position_id}`, optional `volume` query); the `placePendingOrder` `NewPendingOrderRequest` schema; `cancelPendingOrder` (DELETE `/orders/{order_id}`); the `orders` entries in the trading snapshot; and how a pending-order fill deal links to its order (`deal.order_id` or `orders[].order_id` plus `position_id`).
  3. Write a unit test that the three op names in `_ORDER_OPS` raise `LIVE_TRADING_DISABLED`.
  Success: GO when the schema has a `stop` type with a price field and the fill link is named. Verify: `git grep -c "S8-schema:" -- plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`. **No-go = [ASK] (advice Handoff "stop and ask").**
- **T1.11 S9 1d cascade replay.** Steps:
  1. Read 3 UTC days of XAUUSD:EXNESS 1m bars and the matching REST 1d bars from prod (read-only, ops recipe). Write them to the local test Mongo.
  2. Run `cascade_for_symbol` with `DAY_1` enabled.
  3. Compare OHLCV.
  Success: equal OHLC and volume within 0.01%. Verify: `git grep -c "S9-equal: 3/3" -- plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`.
- **T1.12 Record and clean.** Steps:
  1. Write the go/no-go table S1-S9 to `reports/spike-go-no-go.md`, one line `Sx: GO|NO-GO <evidence>` each.
  2. Copy the table into this plan's section 5 note.
  3. Remove the worktree and branch, then delete the key.
  4. Ask an [ASK] if any of S2, S4 or S8 is NO-GO. If S2-measure fails, replace the final check in Phase 05 with the wait only, and record that.
  Verify: `git worktree list | grep -c pocketquant-spike` prints `0`.

### Phase 02: 1d cascade for session calendars (advice item 6) and deploy D-1

Entry gate: the conventions gate, and S9 GO in `reports/spike-go-no-go.md`.
Rollback: `git revert` the commit and redeploy. REST 1d stays in `SYNC_INTERVALS` as the backfill, so the data heals.

- **T2.1 Code.** Files: `engine/market_data/app_services/cascade_aggregator.py`, `engine/market_data/tracked_symbols_backfill.py`, `engine/market_data/app_services/sync_jobs.py`. Steps:
  1. Delete `_INTRADAY_CASCADE_TFS` (`cascade_aggregator.py:26-31`), the comment and `cascade_tfs()` (`:34-41`), and the `CALENDAR_CRYPTO_24_7` import (`:10`).
  2. In `cascade_for_symbol`, loop `for tf in CASCADE_TFS` (`:132`).
  3. Delete the `DAY_1` direct override (`tracked_symbols_backfill.py:80-102`) and its import (`:10`).
  4. Rewrite the comment at `sync_jobs.py:48-56`: "1m via REST, 5m-1d via cascade for every calendar; 1w via REST because Binance weeks open Monday and Exness weeks Sunday, and no cascade convention exists."
  Success: no reference is left. Verify: `git grep -n -E "cascade_tfs|_INTRADAY_CASCADE_TFS" -- src tests scripts | wc -l` prints `0`.
- **T2.2 Tests.** Files: `tests/app_test/market_data/test_cascade_aggregator.py:511-544`, `tests/engine_test/market_data/test_backfill_daily_mode.py`. Steps:
  1. Replace the class with two tests. (a) A session calendar cascades `DAY_1` stamped at UTC midnight, with `session_date` equal to the UTC date, and `find` gets `limit = len(trading_minutes) + 5` (XAUUSD Monday and Sunday). (b) The timeframe order equals `CASCADE_TFS`.
  2. Delete the tests at `:73`, `:97`, `:114` and the header at `:1-3`. Keep `:84`.
  3. Add `test_session_calendar_daily_auto_backfill_cascades`. Drop the now-unused imports.
  Verify: `uv run python -m pytest tests/app_test/market_data/test_cascade_aggregator.py tests/engine_test/market_data/test_backfill_daily_mode.py tests/app_test/market_data/test_cascade_calendar_golden.py -q` ends with `passed` and no `failed`.
- **T2.3 Gates and push.** Steps: run G1-G3, commit `feat(market-data): cascade the daily bar for session calendars`, then push. Verify: the CI check prints `success`.
- **T2.4 [ASK] Deploy D-1.** Steps:
  1. Ask, with the diff stat.
  2. On yes, push `develop:master` (the push command with `develop:master`) and wait for the master run to print `success`.
  3. Record `D-1=<UTC ISO>` and `free -m` before and after in `reports/deploys.md`.
  Verify: `git grep -c "^D-1=" -- plans/261101-0843-stf-to-mtf-foundation/reports/deploys.md` prints `1`.
- **T2.5 Smoke.** Steps: 5 min after the deploy, count prod `bars` with `interval=1d`, `source=cascade` and `datetime=today 00:00Z` for the three `:EXNESS` symbols. Verify: the script prints `cascade_today=3`. Before the market opens, it prints `cascade_today=1` (BTCUSD only). Then delete the key.

### Phase 03: Delete STF code (C1, C2)

Entry gate: the conventions gate. Rollback: `git revert`. Nothing is deployed.

- **T3.1 Test strategy stub.** Files: new `tests/strategy_stubs.py`. Steps:
  1. Add `ScriptedStrategy(IStrategyService)`. It returns `script[i]` (a `Signal | None`) on the i-th bar and records each bar dict it receives.
  2. Add `register(monkeypatch, code="scripted")`, which runs `monkeypatch.setitem(STRATEGY_REGISTRY, code, ScriptedStrategy)`.
  Verify: no verification needed (T3.3 covers it).
- **T3.2 Delete.** Steps:
  1. Delete `core/domain/strategy/services/{engulfing,engulfing_pullback30_touch}_strategy_service.py` and the whole `core/domain/strategy/patterns/` directory.
  2. Set `STRATEGY_REGISTRY: dict[str, type] = {}` and fix `__all__` (`services/__init__.py:11-22`).
  3. Delete `tests/core_test/unit/domain/strategy/{test_engulfing,test_engulfing_pullback30_touch}.py`, the folder `tests/core_test/unit/domain/strategy/patterns/` (the test and the Python fixture copy), and `tests/backtest_test/engine/test_{engulfing,engulfing_pullback30_touch}_backtest.py`.
  Verify: `git grep -n -E "engulfing" -- src | wc -l` prints `0`.
- **T3.3 Repoint tests.** Steps:
  1. Every test that fails because a code no longer resolves, or because it imports a deleted class, switches to `ScriptedStrategy` through `register`. The known sites are listed in scout-backend section 2 ("Import an STF class directly" and "Use a code as a registry key").
  2. Fix the module path list in `tests/core_test/test_core_layout_contract.py:11`.
  5. In `tests/scripts/rubric/test_static_audit.py`, delete the STF parametrized tests and keep `test_unknown_strategy_falls_back_not_raises`.
  6. Leave tests that use a code only as an opaque string unchanged.
  Verify: G1.
- **T3.4 Web comment and doc.** Steps:
  1. Replace `web/src/lib/indicators/engulfing.ts:4-6` with `// Locked by the golden fixture in engulfing.test.ts.`
  2. Replace `:62-64` with `// Visual aid only: a fixed display threshold for strong/weak coloring.`
  3. Replace `engulfing.test.ts:4-5` with `// Golden fixture for detectEngulfing; change both together.`
  4. Delete `docs/swing-pivot-key-level.md`.
  5. Delete the stale sentence "No current strategy adds; each holds at most one position." in `docs/system-architecture.md:34`.
  Verify: `git grep -n -i -E "python detector|swing-pivot-key-level|max_rejection_wick" -- web docs README.md | wc -l` prints `0`, and `cd web && npm test` exits 0.
- **T3.5 Gates and push.** Steps: G1-G3, commit `refactor(strategy): remove single-timeframe strategies`, then push. Verify: the CI check prints `success`.

### Phase 04: Subscription contract (C3)

Entry gate: the conventions gate, and S1 GO. Rollback: `git revert`. The prod data migration happens only in Phase 11.

- **T4.1 Domain.** Files: `core/domain/subscription/entities.py`, `core/domain/strategy/value_objects.py`, `core/domain/strategy/strategy_service_interface.py`, new `core/domain/strategy/config_validation.py`. Steps:
  1. `Subscription` replaces `interval` with `intervals: tuple[Interval, ...]` and adds `parameters: dict` (default empty). Add a property `intervals_key` (comma join). `to_mongo` writes `intervals` (values), `intervals_key` and `parameters`. `from_mongo` reads them; no `interval` fallback.
  2. `SubscriptionAlreadyExistsError(strategy_code, symbol, intervals_key)`.
  3. `StrategyConfig` replaces `interval: str` with `intervals: tuple[str, ...]` and adds the property `interval`, which returns `intervals[0]` (the entry interval).
  4. `IStrategyService` gains `DEFAULTS: ClassVar[dict] = {}`.
  5. `config_validation.py`:
     - `ordered_intervals(values: list[str]) -> tuple[str, ...]` rejects an empty list, unknown values, duplicates, or a higher interval that is not a multiple of the lowest (`INTERVAL_SECONDS`, `core/common/constants.py:42-50`), raising `DomainError(error_code="INVALID_INTERVALS", status_code=422)`. It returns the values sorted ascending.
     - `validate_parameters(strategy_class, symbol, intervals, parameters)` rejects keys not in `DEFAULTS`, then instantiates the class with a throwaway `StrategyConfig` and maps a `ValueError` to `INVALID_PARAMETERS` (422).
  Verify: `uv run python -m pytest tests/core_test/unit/domain/subscription -q` passes after T4.5.
- **T4.2 Repository.** File: `core/infra/persistence/repositories/subscription_repository.py`. Steps:
  1. `ensure_indexes` reads `index_information()`. When `ix_subscriptions_dedup_triple` is present, it drops it (log a warning if the drop fails). It then creates the unique `ix_subscriptions_dedup_intervals` on `[("strategy_code",1),("symbol",1),("intervals_key",1)]`, with a comment explaining why the key is a scalar (multikey uniqueness).
  2. Add `update_config(sub_id, intervals, intervals_key, parameters) -> int` with the filter `{_id, desired_state: "stopped", actual_state: "stopped"}`. Map `DuplicateKeyError` to the 409.
  3. Rewrite `test_dedup_triple_unique_index_exists` (`tests/core_test/infra/persistence/test_subscription_repository.py:99-104`). Add `test_intervals_sharing_the_entry_interval_do_not_collide` and `test_the_old_triple_index_is_dropped`.
  Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_subscription_repository.py -q` has no failures.
- **T4.3 Command, query, routes.** Files: `engine/strategy/strategy_command_service.py`, `engine/strategy/strategy_query_service.py`, `app/routes/strategy.py`, `app/di/services.py`, `core/infra/persistence/repositories/order_repository.py`. Steps:
  1. The body becomes `CreateSubscriptionBody{symbol, intervals: list[str], parameters: dict = {}, broker}`.
  2. `add_symbol(strategy_id, symbol, intervals, parameters, broker)` runs `ordered_intervals`, then `validate_parameters`.
  3. Add `edit(sub_id, intervals, parameters)`:
     - 404 when the subscription is missing.
     - `SUBSCRIPTION_RUNNING` (409) unless both states are `stopped`.
     - `SUBSCRIPTION_HAS_EXPOSURE` (409) when `PositionRepository.find_open_by_subscription` or the new `OrderRepository.find_active_by_subscription` (status `pending|submitted|partially_filled`) is non-empty.
     - Then validate and call `update_config`.
  4. Add `PATCH /subscriptions/{sub_id}` with body `{intervals, parameters}`.
  5. `list_symbols` returns `intervals`, `parameters`, `broker`. `get_one` returns `parameters: dict(cls.DEFAULTS)`.
  6. In DI, inject `PositionRepository` and `OrderRepository` into the command service.
  7. Set `test_admin_token_guard.py:46` to `18`.
  Verify: `uv run python -m pytest tests/engine_test/test_strategy_service.py tests/app_test/integration -q` has no failures.
- **T4.4 Reconcile reload.** File: `engine/live/strategy_reconcile_app_service.py`. Steps:
  1. Build `StrategyConfig(intervals=tuple(i.value for i in sub.intervals), parameters=dict(sub.parameters), ...)` (`:144-155`).
  2. In `_ensure_instances`, for a loaded instance whose `get_config(sid)` differs on `(intervals, parameters)` and which is not running, call `unload_strategy`, then load.
  3. Add tests `test_an_edited_stopped_subscription_reloads_with_the_new_config` and `test_a_running_subscription_is_never_reloaded`.
  Verify: `uv run python -m pytest tests/engine_test/test_strategy_reconcile_service.py -q` has no failures.
- **T4.5 Sweep.** Steps:
  1. Every `StrategyConfig(` call site (29 sites, scout section 2) uses `intervals=(...)`. Every `Subscription(` call site (12) uses `intervals=`.
  2. `backtest_execution_service.py:110-118` passes `intervals=(config.interval,)` until Phase 09.
  3. In `scripts/rubric/static_audit.py`, replace `_find_defaults(tree)` with `dict(getattr(cls, "DEFAULTS", {}))`. Add one audit test that uses a monkeypatched registry class.
  4. In `docs/code-standards.md`, line 93 becomes `(strategy_code, symbol, intervals)`. Line 95 replaces the index name with the pointer `SubscriptionRepository.ensure_indexes` and keeps the upper-case rule.
  Verify: `git grep -n "interval=" -- src | grep -c "StrategyConfig\|Subscription("` prints `0`, then G1-G3.
- **T4.6 Commit and push.** Commit `feat(subscription): ordered intervals and strategy parameters`, then push. Verify: the CI check prints `success`.

### Phase 05: HTF context from Mongo (C4, no-look-ahead rules)

Entry gate: the conventions gate, and S2 GO. Rollback: `git revert`.

- **T5.1 Context module.** File: new `engine/strategy/htf_context.py`. Steps:
  1. Constants: `CONTEXT_BARS = 200`, and `STORED_READY_SECOND = 20`, moved from `_WARMUP_READY_SECOND` (`strategy_app_service.py:46-47`) with its comment, so it has two callers.
  2. Pure `closed_final(bars, step, instant) -> list[Bar]`: ascending bars with `datetime + step <= instant`. Drop the newest kept bar when `updated_at is not None and updated_at < datetime + step` (a partial or not-yet-final cascade bucket). Skip this check when S2-measure was NO-GO.
  3. Pure `is_complete(closed, calendar, interval, instant) -> bool`: let `prev = calendar.bar_start(instant, interval) - step`. It is true when `calendar.trading_minutes(prev, prev + step)` is empty, or when the newest closed bar starts at `prev`.
  4. Class `HtfContextCache(bar_repository, calendar_factory)` keeps a dict `(symbol, interval) -> (bars, valid_until)` and one `asyncio.Lock` per key.
     - `async get(symbol, interval, instant, *, live) -> tuple[list[Bar], bool]`. When there is no entry, or `instant >= valid_until`, take the key lock.
     - If `live` and the wall clock is before `calendar.bar_start(instant, interval) + STORED_READY_SECOND s`, sleep until then.
     - Run `find(symbol, Interval(interval), end_date=instant, limit=CONTEXT_BARS + 1)`, reverse it, and compute `closed_final` and `is_complete`.
     - Store `valid_until = bar_start(instant) + step` only when complete; otherwise store `instant`, so the next bar re-queries.
     - Return `(closed[-CONTEXT_BARS:], complete)`. Log a DEBUG `strategy.context_loaded` with `symbol, interval, bars`.
  5. `async preload(symbol, interval, end, count) -> list[Bar]` is the warm-up read.
  Verify: no verification needed (T5.4 covers it).
- **T5.2 Engine wiring.** File: `engine/strategy/strategy_app_service.py`. Steps:
  1. In the constructor, create `self._context = HtfContextCache(bar_repository, calendar_factory)`.
  2. Add `_bar_dict(symbol, interval, o, h, l, c, v, start)`, used by warm-up and live (it replaces the two copies at `:253-263` and `:380-389`).
  3. Move the per-strategy body of `_on_bar_completed` (from the bar dict to the signal dispatch) into `_decide(strategy, event, successor, published_at)`.
  4. `_decide` sets the instant to `event.bar_start + INTERVAL_SECONDS[event.interval]` in every path, because backtest simulation time is the bar start (`engine/backtest/backtest_app_service.py:109`). For each `config.intervals[1:]` it calls `await self._context.get(...)` and sets `bar["context"] = {iv: [bar dicts]}`. When any interval is incomplete and the strategy returns a signal, the entry is skipped with `reason="context"`, using the existing skip block.
  5. In `_on_bar_completed`, a strategy with more than one interval and `event.bar_end is not None` runs `_decide` as a task, stored in `_signal_tasks` and forgotten through the existing callback. Everything else awaits `_decide` inline.
  6. In warm-up, before the "No I/O" comment, preload each HTF with `count = CONTEXT_BARS + ceil(len(bars) * entry_step / htf_step) + 2`. In the replay loop, compute each bar's context with `closed_final` and `is_complete` (no I/O).
  Verify: G1.
- **T5.3 Sandbox.** Files: `engine/backtest/backtest_sandbox_app_service.py`, `engine/backtest/backtest_execution_service.py:120`, `tests/strategy_stubs.py`, and the 17 files that import the stubs (git grep `NoStoredBars`). Steps:
  1. Change to `build_backtest_sandbox(bar_repository, calendar_factory)`; the caller passes `self._bar_repo, self._calendar_factory`.
  2. Move `NoStoredBars` and `Continuous24x7CalendarFactory` to `tests/strategy_stubs.py` and fix the imports.
  Verify: `git grep -n "NoStoredBars\|Continuous24x7CalendarFactory" -- src | wc -l` prints `0`.
- **T5.4 No-look-ahead tests.** File: new `tests/engine_test/test_htf_context.py`. Tests:
  1. `closed_final` drops the current partial bucket and keeps the previous one.
  2. It drops a newest bar whose `updated_at` is before its end.
  3. Exness 1w buckets start Sunday and Binance 1w buckets start Monday (real calendars from `core/infra/calendars`).
  4. `is_complete` is false when the expected bucket is missing during trading minutes, and true across a closed weekend.
  5. Live: the first 15m bar of a new hour sees the previous hour's close; the wait runs only on rollover; one `find` per rollover.
  6. Warm-up: every replayed bar's context equals the live rule.
  7. Backtest through `BacktestExecutionService` with seeded Mongo, including a partial current bucket: at each hour boundary, `context["1h"][-1]["close"]` equals the previous bucket's close. Assert it on every boundary, not only the end (governance check 2).
  8. An incomplete context skips the entry with `strategy.entry_skipped reason=context`.
  Verify: `uv run python -m pytest tests/engine_test/test_htf_context.py -q` has no failures, then G1-G3.
- **T5.5 Doc and push.** Steps:
  1. Add one bullet to `docs/system-architecture.md` "Design decisions": "Higher-timeframe context is read from stored bars through `HtfContextCache`, never from the trader's live bar events. Rejected: tick-built bars, which can differ from stored bars after a feed gap and which a backtest cannot read. On a live bucket rollover the decision runs as a task that waits for the cascade of that minute."
  2. Commit `feat(strategy): closed higher-timeframe context from stored bars`, then push.
  Verify: the CI check prints `success`.

### Phase 06: Capabilities: stop entry, EXIT, reduce-only (C6)

Entry gate: the conventions gate, S4, S5 and S8 GO, and Unresolved Q1 answered and recorded in `plan.md`. Rollback: `git revert` of the phase's commits. Live stays disarmed.

- **T6.1 Contracts.** Files: `core/domain/strategy/value_objects.py`, `core/domain/order/entities.py`, `core/domain/brokers/broker_port.py`, `core/domain/brokers/events.py`. Steps:
  1. `Signal.entry_type: Literal["market","stop"] = "market"`. `__post_init__` raises when `stop` has no `entry_price` or is not LONG/SHORT, and when EXIT is not `market`.
  2. `OrderAggregate.reduce_only: bool = False`. `to_mongo`/`from_mongo` persist `sl_price`, `tp_price` and `reduce_only`, read with `.get` defaults. This fixes the dropped SL/TP at `entities.py:172-205`.
  3. Change the port to `cancel_order(order: OrderAggregate) -> bool`. It has no src caller today (git grep). Update the two test fakes (`tests/engine_test/test_async_broker_fill_wiring.py:80`, `test_concurrent_opens.py:80`).
  4. Add `REASON_STOP_FILL = "stop_fill"`.
  Verify: `uv run python -m pytest tests/core_test/unit/domain -q` has no failures.
- **T6.2 Risk check.** File: `engine/execution/risk_check.py`. Steps:
  1. EXIT passes only when an open position exists; otherwise return `(False, "no open position to exit")`.
  2. FLAT is rejected. If the owner approved Q1, FLAT passes only while the engine reports an active stop; it never reaches sizing.
  3. Rewrite the comment `:12-14`.
  4. Split `test_exit_and_flat_signals_are_rejected` (`tests/engine_test/test_risk_check.py:40`) into `test_an_exit_with_an_open_position_passes`, `test_an_exit_without_a_position_is_rejected` and `test_a_flat_signal_is_rejected`.
  Verify: `uv run python -m pytest tests/engine_test/test_risk_check.py -q` has no failures.
- **T6.3 Engine and order service.** Files: `engine/strategy/strategy_app_service.py`, `engine/execution/order_app_service.py`, `engine/backtest/backtest_sandbox_app_service.py`, `engine/live/strategy_reconcile_app_service.py`. Steps:
  1. `OrderAppService`:
     - `active_stop(sid)` returns the SUBMITTED `STOP_MARKET` in `_pending` for that subscription.
     - `active_stops()` returns all of them.
     - `cancel(order, broker, *, notify) -> bool` calls `broker.cancel_order(order)`. On True it runs `order.cancel()`, saves, pops, and publishes `OrderCancelledEvent` only when `notify`.
     - `on_order_update` ignores an order whose status is still `PENDING`, because `submit` owns it.
  2. `_process_signal`, EXIT: read the tracker position and build `_exit_order(strategy, position, price)`, an opposite-side MARKET order for `position.quantity` with `reduce_only=True` and no SL/TP. Skip sizing.
  3. `_process_signal`, stop entry: first `cancel(active_stop, notify=False)`. If that returns False, reject with `"pending cancel unconfirmed"`. Size against `signal.entry_price`. `_create_order` uses `STOP_MARKET`, `stop_price=entry_price`, `price=None`.
  4. FLAT (only if Q1 = yes): `cancel(active_stop, notify=False)`.
  5. `_get_or_create_broker` subscribes `on_order_update` for every broker. `inject_prepared_strategy` subscribes it too.
  6. `unload_strategy` cancels the active stop (`notify=False`) before it drops positions.
  7. Add `cancel_active_stop(sid, *, notify) -> str`, which returns `cancelled|no_pending|cancel_failed`. The reconcile `_converge_one` calls it after `stop_strategy` when desired is `stopped`. Engine `stop()` does not call it, so a handover keeps the stop (`strategy_app_service.py:121-140`).
  8. The sandbox calls `await position_app_service.start()`. Rewrite its comment (`:120-124`).
  Tests: an EXIT closes the position and the tracker. An EXIT after an SL already closed it is rejected and opens nothing. Cancel-then-place leaves one active stop. Stopping a subscription cancels its stop. A backtest EXIT closes through the tracker.
  Verify: `uv run python -m pytest tests/engine_test -q` has no failures.
- **T6.4 Paper broker.** File: `core/infra/brokers/paper/paper_broker_adapter.py`. Steps:
  1. `_stops: dict[str, tuple[OrderAggregate, datetime]]`.
  2. `submit_order` with `STOP_MARKET` stores the stop with `placed_at = get_current_time()`, emits SUBMITTED, and returns `OrderResult(status=SUBMITTED)`.
  3. A MARKET order with `reduce_only` is rejected (`"no position to close"`) when no live opposite position exists. Otherwise its quantity is capped at the live quantity. Other non-market types stay rejected.
  4. `cancel_order(order)` pops the stop and returns whether it existed.
  5. In `_on_bar_completed`, after the SL/TP loop and before mark-to-market, check stops for this symbol on the finest interval only, skipping `placed_at >= event.occurred_at`:
     - A BUY triggers when `high + spread >= stop` and fills at `max(open + spread, stop)`.
     - A SELL triggers when `low <= stop` and fills at `min(open, stop)`.
     - Apply slippage, run `_execute_fill_with_commission`, emit SUBMITTED to FILLED with `REASON_STOP_FILL`, and call `_notify_callbacks`. `OrderAppService.on_order_update` publishes the fill.
     - Then a worst-case check: if the trigger bar also crosses the new position's SL, close it at the SL on that bar (TP is not checked on the trigger bar). Put the reason in a comment.
  6. `drop_positions` also drops that subscription's stops. `restore(rows, realized, stops)` re-adds the stops. `reset` clears them.
  Tests in a new `tests/core_test/infra/brokers/test_paper_broker_stop_entry.py`: no trigger on the placement bar, buy and sell trigger prices, gap fill at the open, worst-case SL on the trigger bar, cancel, restore, reduce-only closes a long, rejects when flat, rejects same-side, caps quantity.
  Verify: `uv run python -m pytest tests/core_test/infra/brokers -q` has no failures.
- **T6.5 Restore.** File: `strategy_app_service.py:144-186`. Steps:
  1. Delete the drop branch `:157-165` and the `dropped` counter.
  2. Pass `[o for o in order_app_service.active_stops() if o.subscription_id in ids]` to `broker.restore`.
  3. Log `paper_stops=`.
  4. Update `tests/engine_test/test_paper_restore.py`: a row with no SL/TP is restored, and a stop survives a takeover with its SL/TP.
  Verify: `uv run python -m pytest tests/engine_test/test_paper_restore.py -q` has no failures.
- **T6.6 Exness close behind the flag.** Files: `core/infra/exness/exness_client.py`, `core/infra/brokers/exness/exness_broker_adapter.py`. Steps:
  1. `_ENDPOINTS` adds `closePosition` (`DELETE .../positions/{position_id}`), `placePendingOrder` (`POST .../orders`) and `cancelPendingOrder` (`DELETE .../orders/{order_id}`). `_ORDER_OPS` adds all three (`:46`). `order_request_interval` is unchanged.
  2. `submit_order` dispatches: `reduce_only` goes to `_submit_close`, `STOP_MARKET` to `_submit_pending`, `MARKET` to `_submit_open`, anything else is rejected.
  3. `_submit_close` runs under `_open_lock`:
     - Reject `"no position to close"` without `_held_for(sid)`.
     - Reject when anything for that subscription is in `_inflight`.
     - Check the deadline.
     - Register `_Inflight(order, name, now, position_id=pid)` (new optional field).
     - Call `closePosition` with `path_params={"position_id": pid}` and `idempotency_key=rid`, with no `volume` (full close).
     - It does not check `entries_paused` or the loss cap, because exits are always allowed.
  4. Generalize `_send_tracked(order, op, json_body, path_params, deadline)`.
  5. In `_on_transaction`, an in-flight close rid with success and a `close` deal for its `position_id` calls `_apply_close(rid, deal)`. Under `_state_lock`, a held position that is already gone finishes `CANCELLED "position already closed"`. Otherwise it reduces or pops the held position, runs `_emit_trade`, invalidates the realized cache, and finishes `FILLED` with the deal units and price. It does **not** call `_publish_close_fill`, so the fill is published once.
  6. `_recover_fill` searches the `close` deal by `position_id` for close rids.
  7. Rewrite the header comment `:1-6`.
  Tests (the existing `_Harness`): exactly one `OrderFilledEvent` reaches the position store on a close. A close of an already closed position finishes CANCELLED. A close is rejected while another order is in flight. A close is not blocked by `entries_paused`. `test_exness_client.py` gets one `LIVE_TRADING_DISABLED` test per new op.
  Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness tests/core_test/infra/exness -q` has no failures.
- **T6.7 Exness pending stop behind the flag.** Same files. Steps:
  1. `_submit_pending` runs the same checks as `_submit_open` (pause, held, in-flight, presubmit, SL required, loss cap, lot grid) and builds the body from the schema recorded in S8. `_submit_open` also rejects `"pending order open"` while `_pending_orders` holds the subscription.
  2. On a placement success transaction, store the venue `order_id` in `_pending_orders[rid]` and pop `_inflight`. The order stays SUBMITTED.
  3. A later `open` deal linked to a `_pending_orders` entry (the link named in S8) re-registers the in-flight entry and calls `_apply_success`.
  4. `cancel_order(order)` calls `cancelPendingOrder` for the venue id and returns True only after a confirmed status (stream or up to `_STATUS_POLLS` polls).
  5. In `_on_snapshot`, a venue stop order that is not in `_pending_orders` adds its instrument to `_held_unmapped` and logs ERROR `exness.pending_order_unmapped`.
  Tests: placement, fill, confirmed cancel, unconfirmed cancel returns False, unmapped venue order blocks opens. Update the "market orders only" test (`test_exness_broker_adapter.py:227`) so it still rejects LIMIT.
  Verify: same command as T6.6, then G1-G3.
- **T6.8 Docs in the same change (C6).** Steps:
  1. Rewrite `docs/system-architecture.md:12` as **Exits**: "A paper position closes at its SL or TP, on a strategy EXIT, or on a manual close. An Exness position closes at the venue's SL, TP or a stop-out, on a strategy EXIT, or on a manual close, which is a full close through `closePosition`. Every close is a reduce-only order, so it never opens a position. The risk check rejects an EXIT without a position and any entry against an opposite position. Unloading a subscription leaves a venue position open under its own SL/TP and cancels its pending stop."
  2. Retitle `:37-48` "One exit per position, closed in full". Rows: Signal = `take_profit_price` or `Direction.EXIT`; paper exit = `_check_sl_tp`, `_fire_synthetic_exit` and a reduce-only market order. Keep "no partial close".
  3. Add negative knowledge: "An Exness pending stop is not re-adopted after a trader restart. An untracked venue pending order blocks new opens on its instrument. Adoption must exist before live is armed."
  4. In `docs/deployment.md:124`, add "and paper pending stops".
  5. Commit `feat(execution): stop entries and strategy exits`, then push.
  Verify: `git grep -n -i "SL/TP only\|One take-profit per entry" -- docs | wc -l` prints `0`, and the CI check prints `success`.

### Phase 07: Snapshot, manual-action channel, read endpoints (C7, C8 backend)

Entry gate: the conventions gate. Rollback: `git revert`.

- **T7.1 Snapshot.** Files: `strategy_service_interface.py`, `strategy_app_service.py`, `core/common/constants.py`, `app/di/services.py`. Steps:
  1. `IStrategyService.last_snapshot: dict | None = None`. A strategy sets `{"readings": [{interval, name, value, ok}], "decision": {action, reason}}`.
  2. `_decide` resets it to None before each call. After the skip and dispatch it composes `{bar_start, interval, readings, decision, outcome, pending, freshness}`:
     - `outcome` is one of `no_signal|sent|skipped:<reason>|rejected:<reason>`. `_process_signal` returns the outcome string.
     - `pending` is `{side, price}` from `active_stop`, or None.
     - `freshness` is `[{interval, last_closed, ok}]` from the context.
  3. Append to `deque(maxlen=50)` per subscription. When `event.bar_end is not None` and `snapshot_cache` is set, run `cache.set(CACHE_KEY_STRATEGY_SNAPSHOT.format(subscription_id=sid), list(ring), ttl=TTL_STRATEGY_SNAPSHOT)`. A failure logs WARNING and never blocks the decision.
  4. New constants `CACHE_KEY_STRATEGY_SNAPSHOT = "strategy:snapshot:{subscription_id}"` and `TTL_STRATEGY_SNAPSHOT = 604800`. Constructor kwarg `snapshot_cache: Cache | None = None`; only live DI passes it.
  5. `unload_strategy` drops the ring.
  Tests: the ring is bounded at 50, the outcome for a risk rejection, no write in a backtest.
  Verify: `uv run python -m pytest tests/engine_test -q` has no failures.
- **T7.2 Manual actions.** Files: `core/domain/subscription/entities.py`, `subscription_repository.py`, `strategy_command_service.py`, `app/routes/strategy.py`, `strategy_app_service.py`, `strategy_reconcile_app_service.py`. Steps:
  1. `Subscription` gains `manual_action: dict | None = None` and `last_action: dict | None = None`.
  2. Repository:
     - `request_action(sub_id, action) -> int` filters `{_id, manual_action: None}`.
     - `finish_action(sub_id, action_id, outcome) -> int` filters `{_id, "manual_action.id": action_id}` and sets `manual_action: None, last_action: {id, kind, outcome, at}`.
  3. `request_action(sub_id, kind)` returns 404 when the subscription is missing and `ACTION_PENDING` (409) on 0 matched. It returns `{action_id}`, with the id from `generate_id`.
  4. Routes `POST /subscriptions/{id}/close` and `POST /subscriptions/{id}/cancel-pending`, both 202. Set `test_admin_token_guard.py:46` to `20`.
  5. `run_manual_action(sid, kind) -> str`:
     - Return `not_loaded`, `no_lease` (`trading_until` None or past) or `broker_disconnected` first.
     - Close: no tracker position returns `no_position`; otherwise submit `_exit_order(strategy, position, price=None)` (paper prices from `_get_market_price`, `paper_broker_adapter.py:286`) and return `filled|submitted|rejected:<msg>`.
     - Cancel: `cancel_active_stop(sid, notify=True)`.
  6. Reconcile `_reconcile`: for each subscription with `manual_action`, a request older than `MANUAL_ACTION_TTL_S = 30` finishes `expired`. Otherwise it runs `run_manual_action` and finishes with its outcome. Log INFO `strategy.manual_action` with `sub_id, kind, outcome`.
  Tests: close, cancel, expiry, 409 on a second request, the outcome written, a second execution after a restart returns `no_position`.
  Verify: `uv run python -m pytest tests/engine_test tests/app_test/integration -q` has no failures.
- **T7.3 Read endpoints and cleanup.** Steps:
  1. `GET /subscriptions/{id}/snapshot`: the route injects `Cache` and returns the list or `[]`.
  2. `GET /subscriptions/{id}/orders?limit=50`: query service plus `OrderRepository.find_by_subscription` (newest first).
  3. `list_symbols` adds `manual_action` and `last_action`.
  4. `remove_symbol` deletes the snapshot key; the command service gets `Cache`.
  5. Update `test_tracked_symbol_cascade_delete_api.py:142` to assert that the snapshot key is gone.
  Verify: G1-G3.
- **T7.4 Doc and push.** Steps:
  1. Add a `docs/system-architecture.md` bullet: "Manual close and cancel go api → `manual_action` on the subscription → the lease holder's reconcile loop, which runs them through the order path strategies use. Rejected: an api-to-trader call (the api holds no broker) and Redis pub/sub (lost during a handover). A stale request expires unexecuted (`MANUAL_ACTION_TTL_S`). Strategy snapshots live only in Redis, as a bounded ring per subscription with a TTL. No decision history exists in Mongo."
  2. Commit `feat(strategy): snapshots and manual close and cancel`, then push.
  Verify: the CI check prints `success`.

### Phase 08: Web gates and the generic subscription UI (C8, mockup A19)

Entry gate: the conventions gate. Rollback: `git revert`. The web is not deployed until D-2.

- **T8.1 Gates.** Steps:
  1. Add `interrupted` to both records in `web/src/components/monitor/job-status-palette.ts`. Match the colour to `failed` and the label to `interrupted`.
  2. Add a `web` job to `.github/workflows/cicd.yml`: `ubuntu-24.04`, `actions/setup-node@v4` node 22 with an npm cache on `web/package-lock.json`, `npm ci`, `npm run lint`, `npx tsc -b`, `npm test`, all with `working-directory: web`.
  3. Set `build-web.needs: [tests, web]`.
  Verify: G4, and `git grep -c "needs: \[tests, web\]" -- .github/workflows/cicd.yml` prints `1`.
- **T8.2 API and hooks.** Files: `web/src/api/strategy-api.ts`, `web/src/hooks/use-strategy-mutations.ts`, new `web/src/hooks/use-subscription-detail.ts`. Steps:
  1. `Subscription` gets `intervals: string[]`, `parameters`, `manual_action`, `last_action`. Remove `interval`.
  2. Add the calls `addSymbol({symbol, intervals, parameters, broker})`, `editSubscription`, `requestClose`, `requestCancel`, `fetchSnapshot`, `fetchOrders`, `fetchStrategy(code)`.
  3. Snapshot and orders poll every 5 s. Every mutation invalidates `['subscriptions']`.
  Verify: G4.
- **T8.3 Pure helpers.** Files: new `web/src/lib/subscription-view.ts` and `.test.ts`, `web/src/lib/money-hint.ts` and its test. Steps:
  1. `sortIntervals`, `parameterRows(defaults, values)`, `parseParametersJson(text)`, and `rowView(sub, snapshot, position)`, which returns the position, pending, last decision and freshness labels.
  2. Add `MoneyAction` `close` and `cancel` with real-money titles, for example `'Real money: closes the Exness position at market'`.
  Verify: `cd web && npx vitest run src/lib/subscription-view.test.ts src/lib/money-hint.test.ts` exits 0.
- **T8.4 Form.** Steps:
  1. `git mv web/src/components/strategies/new-subscription-dialog.tsx web/src/components/strategies/subscription-form-dialog.tsx`, with create and edit modes.
  2. New `interval-multi-select.tsx` with all 7 intervals including `1w`, the entry chip marked, and a hint that the lowest is the entry interval.
  3. Broker selector: exness is disabled with a hint while `['safeguards'].live_trading` is false.
  4. Parameters table from `fetchStrategy(code).parameters`, with a raw-JSON toggle.
  5. Show the server message for `INVALID_INTERVALS`, `INVALID_PARAMETERS`, `SUBSCRIPTION_ALREADY_EXISTS`, `SYMBOL_NOT_TRACKED`, `BROKER_DISABLED`, `SUBSCRIPTION_RUNNING`, `SUBSCRIPTION_HAS_EXPOSURE`.
  6. Edit is enabled only when both states are stopped.
  Verify: G4.
- **T8.5 List row.** Steps:
  1. `strategy-card.tsx` shows: strategy, symbol, interval chips, broker badge, state, position, pending, last decision, freshness, actions.
  2. The sidebar filter matches the intervals.
  3. Delete warns with the position and pending text when either exists, using `ConfirmDialog` (`start-stop-button.tsx:129-171`).
  Verify: G4.
- **T8.6 Drawer.** Steps:
  1. New `subscription-detail-drawer.tsx` with: readings table, decision and outcome, pending with Cancel pending, open position with Close at market, the `last_action` result, recent decisions (the ring), and an orders and trades timeline (orders plus trades merged by time).
  2. Close and Cancel always go through `ConfirmDialog` with `moneyHint(broker, 'close'|'cancel')`.
  3. Add a chart with `IntervalSelector` over `sub.intervals`.
  4. `strategies-page-layout.tsx` opens the drawer on row click. Delete `strategy-config-card.tsx` if git grep finds no other user.
  Verify: G4, and `git grep -n -i -E "triple|macd|force.index" -- web/src | wc -l` prints `0`.
- **T8.7 Commit and push.** Commit `feat(web): generic multi-timeframe subscription UI`, then push. Verify: the CI check prints `success` (the `web` job included).

### Phase 09: Backtest intervals and compare view (C9)

Entry gate: the conventions gate. Rollback: `git revert`. Old backtest documents are migrated in Phase 11.

- **T9.1 Backend.** Files: `core/domain/backtest/config.py`, `engine/backtest/backtest_command_service.py`, `engine/backtest/backtest_execution_service.py`, `core/domain/backtest/entities.py`, `app/routes/backtest.py`. Steps:
  1. `BacktestConfig.intervals: list[str]` plus the property `interval` (the entry interval).
  2. `RunBacktestCommand.intervals` runs `ordered_intervals` and `validate_parameters` at command time (422 before a run starts).
  3. The payload and `config_snapshot` carry `intervals`. `StrategyConfig(intervals=tuple(config.intervals))`.
  4. The result document keeps the top-level `interval` (the entry interval, used by `ix_backtests_strategy_symbol_interval_started` and the rail filter) and adds `intervals`.
  5. The list route returns `intervals` and `parameters`.
  6. Annualization stays on the entry interval (`backtest_report_app_service.py:308-316`).
  Verify: `uv run python -m pytest tests/backtest_test tests/app_test/integration -q` has no failures.
- **T9.2 Web.** Steps:
  1. `backtest-form.tsx` uses `interval-multi-select` and the defaults rows. Remove the STF placeholder and hint (`:81`, `:150`).
  2. `RunBacktestBody.intervals`.
  3. The rail's `INTERVALS` gets `1w`. The run list item, header and compare legend show the intervals and parameters. `metrics-diff-table.tsx` adds Intervals and Parameters rows.
  4. New `web/src/constants/backtest.ts` with `MAX_COMPARE_RUNS = 6`, used by the compare route `.slice`, the rail `disableSelect`, and the view (`useQueries` over the run ids).
  Verify: G4, and `git grep -n "slice(0, 3)\|>= 3" -- web/src/routes/backtest_.compare.tsx web/src/components/backtest | wc -l` prints `0`.
- **T9.3 Gates and push.** G1-G4, commit `feat(backtest): run with multiple intervals`, push. Verify: the CI check prints `success`.

### Phase 10: Triple Screen (C10)

Entry gate: the conventions gate. Rollback: `git revert`.

- **T10.1 Strategy.** Files: new `core/domain/strategy/services/triple_screen_strategy_service.py`, `services/__init__.py`. Steps:
  1. Add `TripleScreenStrategyService` with `DEFAULTS = {"entry_type": "market", "exit_mode": "sl_tp", "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "force_period": 2, "stop_lookback": 5, "risk_reward": 2.0}`. `__init__` raises `ValueError` unless there are exactly 3 intervals and values are valid.
  2. Top screen: the slope of the MACD histogram over `bar["context"][intervals[2]]` closes.
  3. Middle screen: the `force_period` EMA of Force Index over `context[intervals[1]]`; below 0 is a long setup, above 0 a short setup.
  4. Entry screen: `market` sends LONG/SHORT at the bar close. `stop` sends `entry_type="stop"` at the previous entry bar's high for a long (low for a short), each bar while the setup holds.
  5. SL is the extreme of the last `stop_lookback` entry bars. `sl_tp` sets TP at `risk_reward` times the risk. `strategy` sets no TP and sends EXIT when the top-screen slope turns against the open direction. If Q1 = yes, it sends FLAT when the setup ends with a stop armed.
  6. It sets `last_snapshot` readings for the three intervals and the decision.
  7. Add the EMA inline, with no new module. Add the registry entry `"triple_screen"`.
  Verify: no verification needed (T10.2 covers it).
- **T10.2 Tests.** File: new `tests/core_test/unit/domain/strategy/test_triple_screen.py`. Tests:
  1. Each screen.
  2. Both entry types and both exit modes.
  3. A wrong interval count raises.
  4. Context lists end at the previous bucket only (a fed context with the current bucket missing gives a different decision than one with the leaked bucket).
  5. The snapshot shape.
  Also add a `test_static_audit.py` test that the DoF equals `len(DEFAULTS)`, and update `tests/http/backtest/*.bru` and `tests/manual/api-test.http` to `triple_screen` with `intervals`.
  Verify: G1-G3.
- **T10.3 Commit and push.** Commit `feat(strategy): add the triple screen strategy`, then push. Verify: the CI check prints `success`.

### Phase 11: Prod migration and deploy D-2

Entry gate: the conventions gate. At least one UTC midnight has passed since `D-1`; otherwise `NOT_YET`. Rollback: re-roll the previous image with `IMAGE_TAG=sha-<prev> bash deploy/vps/10-deploy.sh` (`deploy/vps/10-deploy.sh:9`). Migrated documents keep `interval`, so the old code still reads them.

- **T11.1 D-1 check (read-only).** Steps:
  1. For each `:EXNESS` symbol, every 1d bar with `datetime >= D-1 date` has `source=cascade`.
  2. Each closed day has `updated_at < next day 00:01:00Z`.
  3. Count 1d bars with `source=rest_repair` and `created_at > D-1`.
  Verify: the script prints `non_cascade=0 late=0 repair_1d=0`. Otherwise [ASK].
- **T11.2 Prod state (read-only).** Steps: list the subscriptions (expected 4, all `actual_state=stopped`), the open positions (expected 2) and the backtest runs without `intervals`. Write them to `reports/pre-d2-state.md`. Verify: `git grep -c "running=0" -- plans/261101-0843-stf-to-mtf-foundation/reports/pre-d2-state.md` prints `1`.
- **T11.3 [ASK] Migrate and deploy.** Steps:
  1. Ask, showing the migration counts and the diff stat.
  2. On yes, run `.cache/mtf_migrate.py`:
     - Subscriptions without `intervals`: `$set {intervals: [interval], intervals_key: interval, parameters: {}}` and keep `interval`.
     - Backtest runs without `intervals`: `$set {intervals: [interval], "config_snapshot.intervals": [config_snapshot.interval]}`.
     - Print `subs=<n> runs=<n>`.
  3. Push `develop:master`, wait for `success`, and record `D-2` and `free -m` in `reports/deploys.md`.
  Verify: the script output matches the T11.2 counts, and `git grep -c "^D-2=" -- plans/261101-0843-stf-to-mtf-foundation/reports/deploys.md` prints `1`.
- **T11.4 Post-deploy.** Steps:
  1. The subscription indexes include `ix_subscriptions_dedup_intervals` and not `ix_subscriptions_dedup_triple`.
  2. Over 5 min, the trader log has 0 `reconcile.failed` and exactly 4 `reconcile.unknown_template`.
  3. `GET /api/v1/strategies/triple_screen` returns `parameters` with 8 keys.
  Delete the key.
  Verify: the script prints `index_ok=1 failed=0 unknown=4 params=8`.

### Phase 12: Prod backtests, live set, one paper subscription

Entry gate: the conventions gate, and D-2 recorded. Rollback: stop and delete the new subscription through the API. Backtest runs stay.

- **T12.1 [ASK] Sets.** Recommended: XAUUSD:EXNESS, sets `(15m,1h,4h)`, `(1h,4h,1d)`, `(4h,1d,1w)`, range `2025-11-01..2026-10-31` (1m history starts 2025-10-21, advice Prod checks). Variants: A `market+sl_tp`, B `stop+strategy`. Verify: the reply is recorded in `reports/backtests.md`.
- **T12.2 Run 6 backtests.** Steps: in a prod script, `POST /api/v1/backtest/run` six times. The admin token is read inside the container from settings and sent as a header from Python. Poll `GET /backtest/{id}` until `completed` and record the run ids and key metrics. Verify: `git grep -c "^run=" -- plans/261101-0843-stf-to-mtf-foundation/reports/backtests.md` prints `6`, all `completed`.
- **T12.3 [USER] Compare and pick.** Steps:
  1. Send the compare URL `/backtest/compare?runs=<6 ids>`.
  2. The owner replies `PICK <set> <variant>` and confirms the intervals show. Recommended for the observation run: variant B, because it exercises both capabilities.
  Verify: the reply is recorded.
- **T12.4 Start the paper subscription.** Steps: create it (paper broker, the picked intervals and parameters) through the API, then start it. Within 15 s `actual_state` is `running`. Verify: the script prints `state=running broker=paper`.
- **T12.5 24 h run.** Entry: 24 h after start, otherwise `NOT_YET`. Steps: check the snapshot ring length (at least the number of closed entry bars, capped at 50), the count of `strategy_on_bar_error` = 0, and the count of `strategy.entry_skipped reason=context`, recorded. Verify: the script prints `ring_ok=1 errors=0`.

### Phase 13: Prod STF data delete (C12)

Entry gate: the conventions gate, and the Phase 12 subscription `running` for at least 24 h. Rollback: none. There is no backup by owner decision, so the document list is the only guard.

- **T13.1 List (read-only).** Steps: run `.cache/stf_delete.py list` with `STF = ["engulfing","engulfing_pullback30_touch"]`.
  - `S` = subscription ids with `strategy_code ∈ STF`. Assert that no subscription in `S` is running and that the Phase 12 subscription id is not in `S`.
  - `R` = backtest run ids with `strategy_code ∈ STF`.
  - Print the counts and every `_id` for:
    - `subscriptions{_id ∈ S}`
    - `positions{subscription_id ∈ S}` (the open ones flagged; 2 expected on BTCUSDT:BINANCE)
    - `orders{subscription_id ∈ S}`
    - `trades{run_id ∈ S} ∪ {strategy_code ∈ STF}`
    - `backtest_runs{_id ∈ R}`
    - `backtest_orders` and `backtest_trades{run_id ∈ R} ∪ {strategy_code ∈ STF}`
  - Separately list orphans: positions or orders whose `subscription_id` is in no subscription, and trades whose `run_id` is in no subscription.
  - Print `tracked_symbols` count and `bars` count as a guard baseline.
  Save the output to `reports/stf-delete-list.md`. Verify: the file has one `count:` line per collection (7) plus `orphans:`.
- **T13.2 [ASK] Delete.** Steps: ask with the list file. Recommended: yes, including the orphans, because only STF strategies ever ran live. Only an explicit yes counts; the owner may exclude the orphans. Verify: the answer is recorded in the list file.
- **T13.3 Delete.** Steps: run `.cache/stf_delete.py delete <include_orphans>`. It deletes by the exact `_id` lists saved in T13.1, never by a broader filter, in this order: backtest_orders, backtest_trades, backtest_runs, trades, orders, positions, subscriptions. It never touches `tracked_symbols`, `symbols`, `bars`, `sync_status` or `job_history`, and never calls `TrackedSymbolService.remove`. It asserts that each `deleted_count` equals the listed count. Verify: the script prints `mismatch=0`.
- **T13.4 Post-check.** Steps: re-run `list`. Verify: every STF count is `0`, orphans are `0` (when included), the `tracked_symbols` and `bars` counts are unchanged, the Phase 12 subscription is still `running`, and the API returns no STF subscription. Delete the key.

### Phase 14: Paper run observation

Entry gate: the conventions gate. `reports/observation.md` holds the items done so far; the gate exits `NOT_YET` until all are done. Rollback: none needed (paper only).

- **T14.1 Pending stop fill.** Steps: find an order of the paper subscription with `order_type=stop_market` and `status=filled`, plus its position. Verify: an `obs-stop-fill: <order_id>` line in the report.
- **T14.2 Strategy exit.** Steps: find a filled `reduce_only` order that does not come from a manual action, and a closed trade. Verify: an `obs-exit: <order_id>` line.
- **T14.3 [USER] Manual close.** Steps: when a position is open, the owner presses Close at market in the drawer, confirms, and replies `CLOSED`. Check that `last_action.outcome=filled`, that a reduce-only order exists, and that the trade is closed. Verify: an `obs-close: <order_id>` line.
- **T14.4 [USER] Manual cancel.** Steps: when a pending stop exists, the owner presses Cancel pending and replies `CANCELLED`. Check `last_action.outcome=cancelled` and the order `status=cancelled`. Verify: an `obs-cancel: <order_id>` line.
- **T14.5 UI readings.** Steps: the owner confirms that the drawer readings change between two entry bars (`READINGS OK`). Verify: an `obs-readings: ok` line.

### Phase 15: One-week 1d comparison and plan close (advice item 6)

Entry gate: the conventions gate, and now at least `D-1 + 8 days`. Rollback: none (read-only).

- **T15.1 Comparison.** Steps: inside the api container, fetch the vendor D1 candles for the last 7 closed UTC days of each `:EXNESS` symbol with `ExnessAdapter.fetch_ohlcv` (`core/infra/exness/exness_adapter.py:28`). That is a market-data call, not an order op. The stored 1d bar is now the cascade, because `sync_backfill` never overwrites an existing datetime. Compare OHLC exactly and volume within 0.01%. Write `reports/1d-comparison.md`. Verify: the script prints `days=21 ohlc_mismatch=0`. Otherwise [ASK] (advice Handoff).
- **T15.2 Docs check and close.** Steps:
  1. For every doc touched in Phases 02-10, check that each named path and symbol exists (`git grep`). Each doc stays under 800 lines.
  2. Run `ak plan --help`, then mark the plan completed through the CLI.
  Verify: `wc -l docs/*.md | awk '$1>800' | wc -l` prints `0`.

## 5. Acceptance criteria

| # | Criterion | Check |
|---|---|---|
| A1 | No STF code is left | `git grep -n -E "engulfing" -- src` prints 0 lines. The registry holds only `triple_screen`. |
| A2 | Spike recorded | `reports/spike-go-no-go.md` has S1-S9, each GO or NO-GO with evidence. |
| A3 | Subscription contract | `intervals` and `parameters` are stored. `ix_subscriptions_dedup_intervals` exists in prod. Edit is refused while running or with exposure. |
| A4 | No look-ahead in three paths | `tests/engine_test/test_htf_context.py` passes in CI: live, warm-up and backtest each give the previous bucket's close on every first entry bar of a bucket. A partial or non-final bucket is excluded. |
| A5 | Reads per rollover, not per bar | A test asserts the count of `find` calls equals the count of HTF rollovers. |
| A6 | 1d cascade | `non_cascade=0 late=0 repair_1d=0` (T11.1). `days=21 ohlc_mismatch=0` (T15.1). |
| A7 | Capabilities | Paper stop and reduce-only tests pass. The Exness close and pending tests pass, and each new op raises `LIVE_TRADING_DISABLED` with the flag off. The architecture doc is rewritten. |
| A8 | Snapshot and UI | The drawer readings change per entry bar (T14.5). There are no strategy-specific strings in `web/src`. |
| A9 | Paper observations | `obs-stop-fill`, `obs-exit`, `obs-close`, `obs-cancel` lines exist. |
| A10 | Backtests | 6 completed runs show their intervals in one compare view (T12.3). |
| A11 | Prod delete | Every STF count is 0, the tracked symbols are unchanged, and the new subscription is running (T13.4). |
| A12 | Gates | G1-G4 are green in CI, including the `web` job. |

## 6. Risks

| Risk | L x I | Mitigation |
|---|---|---|
| A live decision reads a partial HTF bar | M x H | The final check (`updated_at >= end`) plus the second-20 wait. An incomplete context skips the entry. Both are measured in S2. |
| The final check flags a bar whose final cascade did not change its OHLCV | L x M | S2-measure rate gate. On NO-GO the plan falls back to the wait only, recorded in Phase 05. |
| A 1m entry with HTF context: rollover bars decide about 20 s late and skip as `stale` (budget 10 s, `strategy_app_service.py:43`) | M x L | Accepted; the snapshot shows the reason. Unresolved Q2. |
| An EXIT races an SL, or a manual close runs twice | M x H | `reduce_only` in both brokers. A test proves no reverse open. |
| Exness close is published twice (adapter and order service) | M x H | `_apply_close` never calls `_publish_close_fill`. A test asserts exactly one fill. |
| Exness pending cancel is async, so two stops could live at once | L x H | `cancel_order` returns True only after confirmation. The engine places a new stop only on True. |
| Exness pending stops are not adopted after a restart | M x M (live disarmed) | An unmapped venue order blocks opens. The doc states negative knowledge, which must be resolved before arming (C13). |
| A paper stop and SL fire on the same bar | M x M | A worst-case SL check on the trigger bar. |
| Paper stop granularity differs: 1m bars live, entry bars in a backtest | H x L | Accepted (A-3). Stated as a code comment. |
| D-2 is a big deploy | M x M | Paper only, `live_trading=false`, a one-command re-roll. Migrated documents stay readable by the old code. |
| A wrong delete filter (no backup) | L x H | Exact `_id` lists, an owner yes, count assertions, a tracked-symbol guard. |
| A Mongo index drop races between role containers | L x M | Drop only when present. A failed drop is a warning (precedent `job_history_repository.py:322-341`). |

## 7. What I deliberately did differently from the advice

1. Warm-up preloads HTF bars before the replay. The advice said warm-up gets context free through `_on_bar_completed`, but warm-up never calls it (`strategy_app_service.py:252-264`).
2. The filter is "closed and final", with a live rollover wait running as a task. The advice had a closed-only filter, which admits the partial bucket stored at the boundary (Lens fact 1).
3. Backtests re-query on each rollover, as C4 states, instead of the advice bullet "load each interval once". S7 measures the cost.
4. "At most one read per rollover" is proven by a test and a DEBUG log, not an INFO log line. Per-rollover INFO would scale with 5m HTFs, against the `CLAUDE.md` log policy.
5. Added `reduce_only`, SL/TP persistence on orders, the stop-cancels-pending rule, and the tracker in the sandbox. Each closes a money-path hole the advice did not name (Lens facts 4-5, Q3).
6. The compare cap goes to 6 instead of restating the metric.
7. The week-after comparison fetches vendor D1 from Exness, because the cascade now owns the stored 1d bar and `sync_backfill` never overwrites it.
8. D-1 ships the cascade alone and early, so the one-week clock starts before the big build.
9. A one-shot prod migration of 4 subscriptions and the backtest runs replaces any `interval` fallback code (C1: no compatibility).
10. The spike runs in a local throwaway worktree branched from `develop`, so rough code never lands on `develop` (Unresolved Q3).

## 8. Unresolved questions for the owner

1. **FLAT = cancel the pending stop.** C6 gives strategies no way to withdraw a stop when the setup ends, so Triple Screen's stop variant would leave stale stops armed. Recommended: yes. `Direction.FLAT` cancels the active stop through the same path as manual cancel. It is needed before Phase 06.
2. **1m entry with higher intervals.** Rollover bars decide about 20 s late and skip as stale. Recommended: accept and show the reason. The alternative is to reject a 1m entry with more than one interval at create time.
3. **Spike location.** C11 says "on `develop`". Recommended: a local worktree branched from `develop`, deleted after the go/no-go is recorded.
4. **Broker on edit.** Recommended: the broker is not editable. To change it, delete and recreate (a paper-to-exness switch should be a deliberate new subscription).
5. **Web CI job.** It adds a CI job and gates `build-web`. Recommended: yes, because real-money buttons ship with this plan.
