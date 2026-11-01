# Planner debate candidate 1: KISS, smallest owning diff

Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8`, 2026-11-01 (Asia/Bangkok). Contract C1-C13 in `reports/debate-evidence-packet.md` is fixed. Every `path:line` below was re-read on `e4a998b8` unless tagged [UNVERIFIED]. Paths without a prefix are under `src/pocketquant/`.

## 1. Lens

Every piece reuses an existing path. Context goes through the one bar handler, and warm-up gets it from the same helper. The closed filter is the existing `_closed_bars` (`engine/strategy/strategy_app_service.py:285-289`). The snapshot is a JSON value in the existing `Cache.set`. Manual actions ride the existing reconcile tick. EXIT goes through the existing order path. The backtest reuses the live engine with real dependencies. The plan adds no new collection, Redis structure, CI job, flag or config key. New files: one strategy, one test-doubles module, two web helpers with tests, one shared web control. Two deploys: an early one so the one-week 1d clock starts, and one release.

## 2. Answers to Q1-Q11

| Q | Choice | Reason and evidence |
|---|---|---|
| Q1 key shape | `Subscription.to_mongo` also writes `intervals_key = ",".join(intervals)`. It is a derived Mongo field, not an entity field. The unique index is `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`. The old `ix_subscriptions_dedup_triple` is dropped once on prod by an ops step in Phase 11, with no drop code in src. | A multikey unique index collides per element (scout-backend §0.1). The old index is at `core/infra/persistence/repositories/subscription_repository.py:79-83`. A new name avoids the same-name conflict at startup (`app/main_extensions.py:114-117`). Drop code would be dead after one prod run (CLAUDE.md, "delete dead code"). Test DBs are fresh containers (`tests/conftest.py:69-72`). |
| Q2 api to trader | New entity field `manual_action: "close" \| "cancel" \| None`. Routes set it with a conditional update (only when it is null). The reconcile tick acts on it through `StrategyAppService.manual_action` and then clears it. | Routes only write Mongo, and the loop owns the trader side (`engine/live/strategy_reconcile_app_service.py:20-23`). The tick reads every subscription every 5 s (`:77-78`, `core/config.py:96`). The loop runs only while the lease is held (`app/roles.py:204-205,223`), so a standby never takes the action. A Redis pub/sub listener or a commands collection would add a task, or a repo plus an index plus cleanup. See unresolved question 2 on C13. |
| Q3 backtest exit quantity | Start `PositionAppService` in the sandbox. | `start()` only loads and subscribes on the bus it was given (`engine/execution/position_app_service.py:31-34`). The sandbox bus is private (`engine/backtest/backtest_sandbox_app_service.py:118-124`). The in-memory repo already has `save` and `find_open` (`:38-55`). One quantity source (`strategy_app_service.py:545`) serves live and backtest, and the backtest risk check then matches live (scout trap 5). |
| Q4 restore rule | Delete the drop of paper rows that have no SL and no TP (`strategy_app_service.py:157-165`). Restore every open paper row and its resting stop. | With EXIT, a position without SL/TP is valid. The rule existed because nothing could close such a row. |
| Q5 reload after edit | In `_ensure_instances`, unload a loaded instance that is not running and whose `(intervals, parameters)` differ from the doc, then fall through to the existing load. The edit route refuses unless desired and actual state are stopped and the subscription has no open position or pending order. | Today a loaded instance is skipped (`strategy_reconcile_app_service.py:119-120`). `unload_strategy` drops paper positions (`strategy_app_service.py:315-318`), so the edit guard makes the unload lossless. |
| Q6 sandbox wiring | `build_backtest_sandbox(bar_repository, calendar_factory)` takes the real ones from its only caller (`engine/backtest/backtest_execution_service.py:120`, which holds `self._bar_repo` and `self._calendar_factory`). `NoStoredBars` and `Continuous24x7CalendarFactory` move to `tests/strategy_doubles.py`. | The context path calls only `BarRepository.find`, which the stub has (`backtest_sandbox_app_service.py:58-60`), so the 20 fixtures keep working after an import change. Without a src caller the stubs are test code. `from tests.x import` already works (`tests/app_test/integration/test_safeguards_api.py:18`). |
| Q7 web gates | Fix the two pre-existing `tsc` errors in Phase 03 (add `interrupted` to both records, `web/src/components/monitor/job-status-palette.ts:3,13`; the type has it at `web/src/types/job-history.ts:4`). Run `tsc -b`, lint and vitest as local Verify steps. Add no web CI job. UI tests cover pure helpers in `*.test.ts`. Add no jsdom. | The contract does not ask for CI. A green local `tsc -b` makes each UI Verify a comparison. Vitest runs in node only (`web/vitest.config.ts`). |
| Q8 compare cap | Keep the cap at 3. Show four runs in three compare views: set A V1 vs V2, set B V1 vs V2, and the two set winners. | C9 asks for intervals and parameters in the existing view, not for a bigger view. The cap is in three files (`web/src/routes/backtest_.compare.tsx:16`, `run-compare-view.tsx:15-19`, `run-history-rail.tsx:135`). |
| Q9 swing doc, rubric | Delete `docs/swing-pivot-key-level.md` and its only link (`web/src/lib/indicators/engulfing.ts:65`). Keep `scripts/rubric/static_audit.py` and read `cls.DEFAULTS` instead of parsing `_DEFAULTS` by AST. That deletes `_find_defaults` (`:39-51`). | The doc is all about the engulfing strategy (scout-web §6). The rubric is generic and used by `run_rubric.py:36,106`, and the class already imports (`static_audit.py:16`). |
| Q10 defaults endpoint | `GET /strategies/{code}` returns `parameters: dict(cls.DEFAULTS)`. Defaults are a class attribute `DEFAULTS` on `IStrategyService` (base `{}`). | The route exists with no web caller (`app/routes/strategy.py:35-43`, `engine/strategy/strategy_query_service.py:24-31`). Changing `/backtest/strategies` would change three web callers (scout-web §1). `DEFAULTS` has four readers: the query service, `check_strategy_inputs`, `static_audit`, and the strategy itself. |
| Q11 snapshot cleanup | The key `strategy:snapshots:{subscription_id}` has a 7-day TTL and no explicit delete. | A UUIDv7 id is never reused, and no reader lists keys. The TTL covers a weekend gap for a 1d entry interval. Zero cleanup code is needed in `remove_symbol` (`engine/strategy/strategy_command_service.py:91-92`) or in symbol removal (`engine/market_data/tracked_symbols_service.py:130-139`). |

## 3. Design and data flows (one paragraph each)

- **Subscription**: the form posts `{symbol, intervals, parameters, broker}` to the existing create route. `check_strategy_inputs` validates the inputs. Mongo stores `intervals`, `intervals_key` and `parameters`. Reconcile builds `StrategyConfig(intervals, parameters)`. `StrategyConfig.interval` becomes `intervals: list[str]`, and the entry interval is `intervals[0]`.
- **Higher-timeframe context**: the entry `BarCompletedEvent` (live, backtest) or a stored entry bar (warm-up) goes to `_decide(strategy, bar)`. It adds `bar["context"] = {interval: [closed Bar, ascending]}` for `intervals[1:]` and calls `strategy.on_bar_completed(bar)`. The filter instant is the **entry bar start**: a bar is visible when `b.datetime + step <= entry_bar_start`. That satisfies both no-look-ahead rules (`docs/governance/no-look-ahead-rules.md:7-8`). It also means the bucket being read closed at least one entry step before the live handler runs, which is after the `sync_1m` cascade at second 12. An end-instant variant would need a 20 s wait, and that breaks the 1m stale budget of 10 s (`strategy_app_service.py:43`).
- **Cache**: `self._htf[(symbol, interval)] = (bucket_start, trusted, bars)` lives on the `StrategyAppService` instance. That is per process in live and per run in the sandbox. `_refresh_context(config, instant)` re-fetches through `_closed_bars` only when `calendar.bar_start(instant)` moves past the cached bucket, or when the cached fetch is untrusted. A fetch is trusted when `get_current_time() >= bucket_start + 20 s` (reuse `_WARMUP_READY_SECOND`, `:47`), so a bucket read before the cascade finished is read again once. `_context_at(config, instant)` is pure: a bisect slice with no await. Warm-up refreshes before `on_start()`, so the "no I/O" block (`:250-271`) stays I/O-free. The cost is at most two reads per `(symbol, interval)` per rollover, not per bar.
- **Capabilities**: `Signal.entry_type` and `Direction.EXIT` already exist (`core/domain/strategy/enums.py:4-8`). `_process_signal` first cancels the subscription's resting stop, so every signal is "cancel then place". EXIT means go flat: cancel the pending stop, then close the open position at market with an opposite MARKET order for the full quantity. A stop entry becomes a `STOP_MARKET` order. The paper broker rests it and fills it on the first later finest bar that touches it. The fill reaches `OrderAppService.on_order_update` through the broker's order callback, now subscribed for every broker. A status guard keeps immediate fills from being processed twice. Exness: `placePendingOrder`, `cancelPendingOrder` and `closePosition` join `_ORDER_OPS` (`core/infra/exness/exness_client.py:44-46`).
- **Snapshot**: the strategy sets `self.snapshot = {"readings": [...], "decision": {...}}`. `_decide` appends `{bar_start, interval, readings, decision, pending}` to an in-memory ring of 20; the engine fills `pending` from its own order store. A live bar writes the ring with `Cache.set(key, ring, ttl)`, only while `trading_until` is set (lease holder). The api serves `GET /subscriptions/{id}/snapshots`. The subscription list adds the latest entry through one `mget`.
- **Manual action**: UI confirm, then `POST /subscriptions/{id}/close|cancel`, which sets `manual_action`. The reconcile tick calls `manual_action(sid, action)`, which reuses `_cancel_pending` and `_submit_exit`, then clears the field.

## 4. Conventions (every phase)

- Phases run in strict numeric order, one fresh worker each. The working dir is `D:/w/_me/algotrading/pocketquant`. Reports go to `plans/261101-0843-stf-to-mtf-foundation/reports/phase-NN-<slug>.md`.
- **Entry gate (EG)**: `git status --porcelain -- src web deploy tests scripts docs` prints nothing. `git rev-parse HEAD` equals `git rev-parse origin/develop`. The previous phase report exists. A miss ends the phase with exactly `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from NN after <UTC>`. Edit nothing on a miss.
- **[ASK]**: ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason. Only an explicit yes counts. Every `develop:master` push is an [ASK]. **[USER]**: the owner acts and replies with the stated token.
- **Failure protocol**: a failed Verify stops the phase. Send the evidence and the question to `kongming`. A `NOT_YET` exit does not go to `kongming`.
- **Ops recipe**: reuse `plans/261028-0652-exness-only-parallel-runtime/plan.md` "Ops recipe" for the SSH key, push URL, `GH_TOKEN`, `dc()` and `rm -f .cache/ssh/vps_key`. **PRODPY f**: write `.cache/f.py`, then `ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy; docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py'`. Scripts read Mongo through `get_settings()` (`core/config.py:47-48`). Admin HTTP calls run inside the container with the header `X-Admin-Token` taken from `get_settings().admin_token.get_secret_value()` (`core/config.py:85`). No secret ever goes on a command line.
- **FULLSUITE**: run `docker ps` (start Docker Desktop if it fails), then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Expected: the last line contains `4 failed` and `4 errors`, then `0`.
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.` `uv run python scripts/code_metrics.py --ratchet` exits 0. If only the ratchet fails, raise the ceiling in `pyproject.toml:130-132` in its own commit `chore(metrics): raise code metric ceiling`, and say so in the report. `uv run ruff check src tests scripts` exits 0. The error count from `uv run pyright src | tail -1` is no higher than the Phase 01 baseline. With web touched, in `web/`: `npx tsc -b` exits 0, `npm run lint` reports `0 errors`, and `npx vitest run` passes everything.
- **CLOSE**: GATES and FULLSUITE pass. Then commit (conventional, English, no plan ids or phase numbers), push `develop`, and run `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` until `status` is `completed`. Expected: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`.
- Code follows CLAUDE.md: no docstrings, a WHY goes in a `#` comment, log level by frequency, UUIDv7 ids, `git grep` (no `rg`).

## 5. Phases

| # | Title | Deploy | Depends on |
|---|---|---|---|
| 01 | Spike: prove each piece, record go/no-go | no | - |
| 02 | 1d cascade for session calendars (D1) | yes, D1 | 01 |
| 03 | Delete STF code, add test doubles, fix the web type errors | no | 01 |
| 04 | Subscription contract: intervals, parameters, edit, defaults | no | 03 |
| 05 | Higher-timeframe context (live, warm-up, backtest) and backtest intervals backend | no | 04 |
| 06 | Capabilities: stop entry, EXIT, paper and Exness, restore, architecture doc | no | 05 |
| 07 | Snapshot, manual actions, read endpoints | no | 06 |
| 08 | Backtest UI: intervals, parameters, compare labels | no | 05 |
| 09 | Generic subscription UI per the mockup | no | 07, 08 |
| 10 | Triple Screen strategy | no | 05, 06, 07 |
| 11 | Release D2: migrate legacy docs, deploy, drop the old index | yes, D2 | 02-10 |
| 12 | Triple Screen backtests on prod, pick the live set | no | 11 |
| 13 | Paper subscription: start and observe | no | 12 |
| 14 | One-week 1d cascade comparison | no | 02 (D1 + 7 days) |
| 15 | Prod STF data delete and close | no | 13, 14 |

### Phase 01: Spike (C11)

EG, and also: `docker ps` succeeds.

**T1.1 Baseline.** Goal: record the starting numbers that later phases compare against. Files: `reports/spike-go-no-go.md` (new). Steps: (1) Run FULLSUITE, `lint-imports`, `code_metrics.py --json`, `pyright src | tail -1`, and in `web/` `npx tsc -b; echo $?`, `npm run lint`, `npx vitest run`. (2) Write each output line under "Baseline". Success: all seven values are recorded. Verify: `grep -c "^- " plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints at least `7`.

**T1.2 Rough spike, uncommitted.** Goal: prove each piece in the develop working tree with the least code. Commit nothing. Files: any under `src`, `tests/spike_test/`, `web/src`. Steps: build each piece the rough way the named later task describes. Read that task first. Skip validation, docs and polish. Write one test per piece in `tests/spike_test/test_spike.py` (P1-P8) that asserts the go criterion:
- P1 (T4.2-T4.3): the API accepts `["15m","1h"]` and `["15m","4h"]` for the same code and symbol (both 201), and a repeat of `["15m","1h"]` returns 409.
- P2 (T5.1, T5.4 a-c): with real Mongo seeded with 1m and 1h bars, the first 1m bar of the 01:00 bucket sees last context bar 00:00. The 00:59 bar does not see 00:00. The partial 02:00 bar is never visible.
- P3 (T7.1, T7.3): after one live bar, `GET /subscriptions/{id}/snapshots` returns one entry with `readings`.
- P4 (T6.4): a paper LONG, then EXIT, gives a closed position, one `TradeClosedEvent` and the exit order `filled` in the order store.
- P5 (T6.3-T6.4): a stop LONG is `submitted`, fills on the next bar whose high reaches it, and a second signal cancels the first order (`cancelled`).
- P6 (T7.2): `manual_action="close"` on the doc closes the position on the next reconcile tick and clears the field.
- P7 (T5.3): a backtest with `intervals=["1m","1h"]` stores `config_snapshot.intervals == ["1m","1h"]`. The wall time over 30 days of seeded 1m data is less than 2x the run with `["1m"]`.
- P8: three fake-transport client calls (`placePendingOrder`, `cancelPendingOrder`, `closePosition`) raise `LIVE_TRADING_DISABLED` while the flag is off. The spec facts (`https://www.exness-api.com/exness_api.yaml`, read 2026-11-01: POST `/orders` with `type: stop`, DELETE `/orders/{order_id}`, DELETE `/positions/{position_id}` with an optional `volume`) are copied into the report.

Also P9, a prod read-only check: read `sync_status.last_bar_at` for `XAUUSD:EXNESS` 5m and 1h twice, 6 minutes apart, with PRODPY. Go means 5m moved. P10: render the snapshot table and the compare legend with intervals in the web; go means `npx tsc -b` and `npx vite build` both exit 0. Success: every piece has a pass or fail outcome. Verify: `uv run python -m pytest tests/spike_test -q 2>&1 | tail -1` shows a pass/fail count that matches the go/no-go table in T1.3.

**T1.3 Record and reset.** Goal: keep the evidence and return the tree to HEAD. Steps: (1) Write a table `piece | go/no-go | evidence | fix carried to phase` into `spike-go-no-go.md`. (2) `git add -A -N src tests web && git diff -- src tests web > plans/261101-0843-stf-to-mtf-foundation/reports/spike.patch && git reset -q && git checkout -- src tests web && git clean -fdq src tests web`. Success: the patch is saved and the tree is clean. Verify: `test -s plans/261101-0843-stf-to-mtf-foundation/reports/spike.patch && git status --porcelain -- src web tests | wc -l` prints `0`.

**T1.4 Gate.** Goal: apply the C11 stop rule. Steps: if P2 or P4 is no-go, end with `Status: BLOCKED` and [ASK] the owner with the evidence. Any other no-go becomes a line "fix carried to phase NN". Verify: no verification needed; the report table is the output.

Rollback: nothing is committed. The patch file is a record.

### Phase 02: 1d cascade (advice item 6) and D1

EG.

**T2.1 Cascade 1d for every calendar.** Goal: Exness 1d bars are final in Mongo seconds after 00:00Z. Files: `engine/market_data/app_services/cascade_aggregator.py` (delete `_INTRADAY_CASCADE_TFS` `:26-31`, the comment `:34-37`, `cascade_tfs` `:38-41` and the `CALENDAR_CRYPTO_24_7` import `:10`; `cascade_for_symbol` iterates `CASCADE_TFS` at `:132`), `engine/market_data/tracked_symbols_backfill.py` (delete the DAY_1 override `:80-102` and the import `:10`), `engine/market_data/app_services/sync_jobs.py:48-56` (comment: 1d cascades for every calendar; 1w stays REST because Binance weeks open Monday and Exness weeks open Sunday). Steps: exactly as advice item 6 (a)-(c). Success: no reference to `cascade_tfs` remains. Verify: `git grep -n "cascade_tfs\|_INTRADAY_CASCADE_TFS" -- src tests scripts | wc -l` prints `0` after T2.2.

**T2.2 Tests.** Files: `tests/app_test/market_data/test_cascade_aggregator.py:511-544`, `tests/engine_test/market_data/test_backfill_daily_mode.py`. Steps: (1) Replace the class with two tests. A session calendar cascades `DAY_1` with the bar at UTC midnight, `session_date` equal to the UTC date, and `find` called with `limit = len(trading_minutes) + 5` (1383 for an XAUUSD Monday, 124 for its Sunday). The timeframe order is unchanged. (2) Delete the tests at `:73,:97,:114` and the header `:1-3`. Keep `:84`. Add a test that a session-calendar `DAY_1` auto backfill resolves to cascade. Drop unused imports. Verify: `uv run python -m pytest tests/app_test/market_data tests/engine_test/market_data -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T2.3 CLOSE.** Verify: as CLOSE.

**T2.4 Deploy D1.** Goal: start the one-week clock. Steps: (1) Record `free -m` on the VPS. (2) [ASK] in Vietnamese: "Deploy the 1d cascade only (develop = HEAD, no strategy change)". Recommended: yes, it starts the one-week comparison now. (3) Push `develop:master` and wait for the master run (`gh run list --branch master --limit 1`) to reach `completed` with `success`. (4) PRODPY: read the latest `bars` doc for `BTCUSD:EXNESS` (24/7) with `interval` `1d`. (5) Record `free -m` again. Write the deploy UTC time as `d1_deployed_at=<iso>` in `reports/phase-02-d1.md`. Success: `source == "cascade"` and `updated_at` within 120 s of the read. Verify: `grep -c "^d1_deployed_at=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-02-d1.md` prints `1`.

Rollback: revert the cascade commit and redeploy [ASK]. The cascaded bars equal vendor bars (advice prod checks), `sync_backfill` never rewrites an existing datetime, and `sync_repair` refills only gaps.

### Phase 03: Delete STF (C1, C2, Q9)

EG.

**T3.1 Test doubles.** Goal: tests stop depending on STF classes. Files: new `tests/strategy_doubles.py`, `tests/conftest.py`. Steps: (1) Add `ProbeStrategy(IStrategyService)`. It emits `Signal(LONG, confidence=1, stop_loss=close*0.99, take_profit=close*1.01)` on every bar while `_open_direction is None`, and copies the open and reset bookkeeping of `hitnrun2_strategy_service.py` `on_order_filled` and `on_order_rejected` (read before deleting). (2) Add a fixture `probe_registry(monkeypatch)` that runs `monkeypatch.setitem(STRATEGY_REGISTRY, "probe", ProbeStrategy)`. This mirrors `tests/app_test/integration/test_trader_lifespan_handover.py:139`. Verify: no verification needed; T3.3's Verify covers it.

**T3.2 Delete src.** Files: delete `core/domain/strategy/services/{hitnrun2,engulfing,engulfing_pullback30_touch}_strategy_service.py` and `core/domain/strategy/patterns/` (whole package). Set `STRATEGY_REGISTRY` to `{}` and trim `__all__` in `core/domain/strategy/services/__init__.py:11-22`. Remove the `NEW_MODULES` entry at `tests/core_test/test_core_layout_contract.py:11`. Verify: `git grep -n -E "hitnrun2|engulfing" -- src | wc -l` prints `0`.

**T3.3 Tests.** Steps: (1) Delete `tests/core_test/unit/domain/strategy/test_{hitnrun2,engulfing,engulfing_pullback30_touch}.py`, `tests/core_test/unit/domain/strategy/patterns/` (detector test and the Python fixture copy), and `tests/backtest_test/engine/test_{hitnrun2,engulfing,engulfing_pullback30_touch}_backtest.py`. (2) Rewrite the class importers to `ProbeStrategy`: `tests/engine_test/test_strategy_warm_up.py:17,156`, `tests/engine_test/test_strategy_reject_delivery.py:22,126`, `tests/backtest_test/test_backtest_single_run_direct_task.py:76,269`. (3) Point the registry-key users at `"probe"` plus the fixture: `tests/engine_test/test_live_trade_collector_integration.py:38`, `test_reconcile_restart_resume_integration.py:43`, `test_strategy_reconcile_service.py:20`, `test_strategy_service.py:140-261`, `tests/app_test/integration/test_app_standalone_runtime.py:30`, `test_trader_lifespan_handover.py:139,151`, `tests/backtest_test/test_backtest_dispatch_contract_spec.py:57`. (4) Replace opaque strings with `"probe"` in the 12 files in scout-backend §2 "opaque string only" and the rubric data tests. (5) In `tests/scripts/rubric/test_static_audit.py` delete the three STF cases (`:7-36`) and keep the unknown-code case. (6) In `tests/http/backtest/*.bru` and `tests/manual/api-test.http` use `triple_screen`. Success: no STF names remain in tests. Verify: `git grep -n -E "hitnrun2|engulfing" -- src tests scripts | wc -l` prints `0`, and FULLSUITE matches its expected result.

**T3.4 Web and docs.** Files: `web/src/lib/indicators/engulfing.ts:4-6,65`, `engulfing.test.ts:4-5`, `web/src/components/monitor/job-status-palette.ts`, `docs/swing-pivot-key-level.md`. Steps: (1) Rewrite the comments: the overlay and its golden fixture are owned by the web, and no Python copy exists. (2) Delete the line `:65` pointer. (3) Add `interrupted` to `STATUS_COLOR` and `STATUS_LABEL`. (4) Delete the doc. Verify: `cd web && npx tsc -b; echo $?` prints `0`, and `git grep -n -i "swing-pivot\|python detector" -- web/src docs | wc -l` prints `0`.

**T3.5 CLOSE.**

Rollback: `git revert` of the phase commits. Nothing is on prod.

### Phase 04: Subscription contract (C3, Q1, Q5, Q10)

EG.

**T4.1 Domain inputs.** Goal: one validation that serves subscriptions and backtests. Files: `core/domain/strategy/value_objects.py:26-35` (`interval: str` becomes `intervals: list[str]`), `core/domain/strategy/strategy_service_interface.py:16` (add `DEFAULTS: ClassVar[dict[str, object]] = {}`), `core/domain/strategy/services/__init__.py` (add `check_strategy_inputs(strategy_code, intervals, parameters) -> type[IStrategyService]`). Steps: (1) The function raises `NotFoundError` for an unknown code. It raises `DomainError(error_code="INVALID_INTERVALS", status_code=422)` unless there is at least one valid `Interval`, the list is strictly ascending by `INTERVAL_SECONDS`, and every interval is a multiple of `intervals[0]`. It raises `INVALID_PARAMETERS` (422) for keys not in `cls.DEFAULTS`, or when `cls(StrategyConfig(id="check", name=code, symbol="CHECK", intervals=..., parameters=...))` raises `ValueError`. (2) Update the src readers: `strategy_app_service.py:235-236,256,499` use `intervals[0]`. `backtest_execution_service.py:114` waits for T5.3. Update the other `StrategyConfig(` sites in tests: `git grep -n "StrategyConfig(" -- src tests` lists 29 sites; each gets `intervals=[...]`. Verify: `git grep -n -E "config\.interval\b|interval=\"[0-9]+[mhdw]\"," -- src/pocketquant/engine/strategy src/pocketquant/engine/live | wc -l` prints `0`.

**T4.2 Entity and repository.** Files: `core/domain/subscription/entities.py:19-70`, `core/infra/persistence/repositories/subscription_repository.py:19-84`. Steps: (1) Replace `interval: Interval` with `intervals: tuple[Interval, ...]` and add `parameters: dict` (`field(default_factory=dict)`). `to_mongo` writes `intervals` as a list of values, `intervals_key` and `parameters`. `from_mongo` reads `intervals` and `parameters`. `SubscriptionAlreadyExistsError` takes `intervals_key`. (2) The repo `add` maps the duplicate key with `intervals_key`. The index becomes `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`. Add `update_config(sub_id, intervals, parameters) -> int`, filtered on `desired_state: "stopped", actual_state: "stopped"`. (3) Update the tests in `test_subscription_desired_actual_state.py` and `test_subscription_repository.py:75-104`, and add `test_lists_sharing_an_entry_interval_coexist` (`["15m","1h"]` and `["15m","4h"]`). Verify: `uv run python -m pytest tests/core_test/unit/domain/subscription tests/core_test/infra/persistence/test_subscription_repository.py -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T4.3 Command, query, routes.** Files: `engine/strategy/strategy_command_service.py:48-89`, `engine/strategy/strategy_query_service.py:24-57`, `app/routes/strategy.py:13-52`, DI in `app/di/services.py` (command service provider). Steps: (1) `add_symbol(strategy_id, symbol, intervals, parameters, broker)` calls `check_strategy_inputs` after the tracked-symbol check and returns `intervals` and `parameters`. (2) `edit(sub_id, intervals, parameters)` works like this. A missing doc gives 404. A running doc gives 409 `SUBSCRIPTION_RUNNING`. An open position (`PositionRepository.find_open_by_subscription`, `position_repository.py:25`) or a pending order (`OrderRepository.find_pending()` filtered by `subscription_id`) gives 409 `SUBSCRIPTION_HAS_EXPOSURE`. Then it calls `check_strategy_inputs`, then `update_config`, and 0 matched gives 409 `SUBSCRIPTION_RUNNING`. Add the two repos as deps. (3) Bodies: `CreateSubscriptionBody{symbol, intervals: list[str], parameters: dict = {}, broker}` and `EditSubscriptionBody{intervals, parameters}`. Add `PATCH /subscriptions/{sub_id}` returning the updated row. (4) `get_one` returns `parameters: dict(cls.DEFAULTS)`. `list_symbols` returns `intervals` and `parameters`. (5) `tests/app_test/integration/test_admin_token_guard.py:46` becomes `18`, and its create path posts `intervals`. Add tests for 201, 409 on a duplicate, 422 on unsorted, 422 on an unknown parameter, 409 on running, 409 on exposure, and the defaults endpoint. Verify: `uv run python -m pytest tests/engine_test/test_strategy_service.py tests/app_test/integration -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T4.4 Reconcile and rubric.** Files: `engine/live/strategy_reconcile_app_service.py:115-161`, `scripts/rubric/static_audit.py:27,39-51`, `docs/code-standards.md:93,95`. Steps: (1) Build `StrategyConfig(intervals=[i.value for i in sub.intervals], parameters=dict(sub.parameters), ...)`. (2) Replace the skip at `:119-120`. If the instance exists and `is_running`, or its config `(intervals, parameters)` equals the doc, `continue`. Otherwise call `await self._strategy_service.unload_strategy(sub_id)` and fall through to load. Comment the WHY: an edit is allowed only while stopped and flat. (3) `defaults = dict(cls.DEFAULTS)`; delete `_find_defaults` and `_literal` if unused. (4) Docs: the subscription is one `(strategy_code, symbol, intervals)` binding, and the guard is `ix_subscriptions_dedup_intervals` on the derived `intervals_key`. Write it as a pointer, not a copy. Add a reconcile test: an edited stopped instance reloads with the new parameters, and a running one does not. Verify: `uv run python -m pytest tests/engine_test/test_strategy_reconcile_service.py tests/scripts -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T4.5 CLOSE.**

Rollback: `git revert`. Nothing is on prod.

### Phase 05: Higher-timeframe context (C4) and backtest intervals backend (C9)

EG.

**T5.1 Engine context.** Goal: one context path for live, warm-up and backtest. Files: `engine/strategy/strategy_app_service.py`. Steps: (1) Add `self._htf: dict[tuple[str, str], tuple[datetime, bool, list[Bar]]] = {}` in `__init__` (`:57-102`). (2) `async def _refresh_context(self, config, instant)`. For each interval in `config.intervals[1:]`: `bucket = calendar.bar_start(instant, Interval(i))`. Skip when the cached bucket is newer, or when it is equal and trusted. Otherwise `bars = await self._closed_bars(config.symbol, Interval(i), step, bucket)`, then store `(bucket, get_current_time() >= bucket + timedelta(seconds=_WARMUP_READY_SECOND), bars)`. (3) `def _context_at(self, config, instant) -> dict[str, list[Bar]]` returns `bars[: bisect_right(bars, instant, key=lambda b: b.datetime + step)]` per interval. (4) `async def _decide(self, strategy, bar: dict) -> Signal | None` sets `bar["context"] = self._context_at(strategy.config, bar["timestamp"])` and returns `await strategy.on_bar_completed(bar)`. (5) Warm-up: call `await self._refresh_context(config, now)` before `on_start()` (`:250`); the replay loop `:252-264` calls `_decide`. Live: in `_on_bar_completed`, call `await self._refresh_context(strategy.config, event.bar_start)` before the bar dict, then `_decide` replaces `:391`. Add a WHY comment above `_context_at`: the entry bar start is the instant, so a bar never sees its own higher bucket (`docs/governance/no-look-ahead-rules.md`). Verify: no verification needed; T5.4 covers it.

**T5.2 Sandbox with real dependencies.** Files: `engine/backtest/backtest_sandbox_app_service.py:58-70,118-139`, `backtest_execution_service.py:120`, `tests/strategy_doubles.py`, the 20 fixture imports (scout-backend §3 list). Steps: (1) `build_backtest_sandbox(bar_repository, calendar_factory)` passes them to `StrategyAppService` and calls `await position_app_service.start()`. Rewrite the comment `:118-124`: the private bus isolates the tracker. (2) The caller passes `self._bar_repo, self._calendar_factory`. (3) Move `NoStoredBars` and `Continuous24x7CalendarFactory` to `tests/strategy_doubles.py` and change the 20 imports. Verify: `git grep -n "class NoStoredBars\|class Continuous24x7CalendarFactory" -- src | wc -l` prints `0`.

**T5.3 Backtest intervals backend.** Files: `core/domain/backtest/config.py:10-24`, `engine/backtest/backtest_command_service.py:17-67`, `backtest_execution_service.py:31-46,110-118`, `backtest_app_service.py:103-113`, `backtest_report_app_service.py:308-359`. Steps: (1) `BacktestConfig.intervals: list[str]` replaces `interval`. (2) `RunBacktestCommand.intervals: list[str]`. `run` calls `check_strategy_inputs(cmd.strategy_id, cmd.intervals, cmd.parameters or {})` and writes `"intervals"` into the payload. (3) Stream and publish `intervals[0]`. The report annualizes and persists the top-level `interval` as `intervals[0]`, so the index `ix_backtests_strategy_symbol_interval_started` and the list filter stay. `config_snapshot` carries `intervals`. (4) Update `tests/backtest_test` payloads (`git grep -n "\"interval\":" -- tests/backtest_test tests/app_test`). Verify: `uv run python -m pytest tests/backtest_test -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T5.4 No-look-ahead tests.** Files: new `tests/backtest_test/test_higher_timeframe_context.py` (uses `database` from `tests/backtest_test/conftest.py:39`). Steps: seed 1m bars for 2026-01-05 00:00-03:10 with a 20-minute gap at 01:30, 1h bars 00:00-03:00 (03:00 partial), and a recording strategy (intervals `["1m","1h"]`) that stores `bar["context"]["1h"][-1].datetime`. Tests: (a) the live path (events with `bar_end`) at 01:00 sees 00:00; (b) 00:59 sees nothing or the bar before 00:00; (c) 03:00 never sees the 03:00 partial; (d) warm-up replay contexts equal the live contexts at the same instants; (e) a backtest through `BacktestExecutionService.run` over the whole range gives the same per-bar contexts as live, including across the gap; (f) two instances on one symbol cause at most 2 `find` calls per hour rollover (wrap the repo and count); (g) an Exness calendar with 1w rolls on Sunday 00:00Z (`EXNESS_CALENDARS` as in `tests/app_test/market_data/test_cascade_aggregator.py:26`). Verify: `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` shows `7 passed`.

**T5.5 CLOSE.**

Rollback: `git revert`.

### Phase 06: Capabilities (C6)

EG.

**T6.1 Signal and risk.** Files: `core/domain/strategy/value_objects.py:9-23`, `engine/execution/risk_check.py:12-46`, `tests/engine_test/test_risk_check.py:40`. Steps: (1) Add `entry_type: Literal["market","stop"] = "market"`. `__post_init__` requires `entry_price` and a LONG or SHORT direction for `stop`. (2) The first branch of `validate`: EXIT returns `(True, "")` when the position is open, else `(False, "no open position")`. FLAT stays rejected. Rewrite the comment `:12-14`. (3) Split `test_exit_and_flat_signals_are_rejected` into three tests: EXIT with a position, EXIT without one, FLAT. Verify: `uv run python -m pytest tests/engine_test/test_risk_check.py -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T6.2 Order store.** Files: `engine/execution/order_app_service.py:129-172`, `strategy_app_service.py:334-347,676-677`. Steps: (1) `pending_stop(subscription_id) -> OrderAggregate | None` returns the `SUBMITTED` `STOP_MARKET` order in `_pending`. `async cancel(order)` runs `order.cancel()`, saves, pops and logs INFO `order_cancelled`. (2) At the top of `on_order_update`: `if order.status is not OrderStatus.SUBMITTED: return`. Comment the WHY: an immediate fill is finished by `submit`. (3) Subscribe `on_order_update` for every broker in `_get_or_create_broker` (drop the `fills_async` guard) and in `inject_prepared_strategy`. Add a test that a paper immediate fill publishes one `OrderFilledEvent`, not two (`tests/engine_test/test_order_app_service_immediate_fill.py`). Verify: `uv run python -m pytest tests/engine_test -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T6.3 Paper resting stop.** Files: `core/infra/brokers/paper/paper_broker_adapter.py:119-246,472-503`. Steps: (1) `submit_order` with `STOP_MARKET` stores the order in `self._resting[broker_order_id] = (order, now)` and returns `OrderResult(status=SUBMITTED)`. Other non-market types stay rejected. (2) `cancel_order` pops and returns whether it was found. (3) In `_on_bar_completed`, after the finest check and before SL/TP, check every resting order on the symbol placed before `event.occurred_at`. A BUY fills when `high + spread >= stop`, at `max(open + spread, stop)`. A SELL fills when `low <= stop`, at `min(open, stop)`. Apply the affordability check, then `_execute_fill_with_commission`, `_emit_event`, `_notify_callbacks(FILLED, order_id=str(order.id), sl, tp)` and the trade callbacks. Publish no `OrderFilledEvent` (`OrderAppService` does it). (4) `drop_positions` also drops the subscription's resting orders. `reset` clears them. `restore(rows, realized, resting)` accepts orders. (5) Tests in `tests/core_test/infra/brokers/test_paper_broker_sl_tp_fill.py`: a touch fills, a gap fills at the open, no fill on the placing bar, cancel, SELL symmetry. Verify: `uv run python -m pytest tests/core_test/infra/brokers -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T6.4 Engine signal paths.** Files: `strategy_app_service.py:144-186,505-651`. Steps: (1) `_cancel_pending(sid, broker) -> bool`: if `pending_stop` exists and `await broker.cancel_order(o.broker_order_id)` succeeds, then `await order_app_service.cancel(o)`. (2) `_submit_exit(strategy, broker, position, price, deadline)` builds a MARKET order on the opposite side of the position for `position.quantity`, with no SL/TP, and calls `order_app_service.submit`. (3) In `_process_signal` after the broker lookup: `cancelled = await self._cancel_pending(...)`. EXIT: with no open position, reject with `"nothing to exit"` unless something was cancelled, and return. Otherwise run the risk check, then `_submit_exit`. Entries: `entry = signal.entry_price if signal.entry_type == "stop" else current_price` for sizing. `_create_order` sets `STOP_MARKET`, `stop_price=entry` and `price=entry` for a stop, and BUY only for LONG. (4) `take_over`: delete `:157-165`. Pass `[o for sid in ids if (o := self._order_app_service.pending_stop(sid))]` to `restore`. Rewrite `tests/engine_test/test_paper_restore.py:198` to `test_a_paper_row_without_exits_is_restored`. Add tests in `tests/engine_test/test_paper_position_lifecycle.py`: EXIT closes, EXIT cancels a pending order only, a new stop signal cancels then places, a stop fill opens the tracked position. Verify: `uv run python -m pytest tests/engine_test -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T6.5 Exness behind the flag.** Files: `core/infra/exness/exness_client.py:28-47,110-120`, `core/infra/brokers/exness/exness_broker_adapter.py:1-6,209-286,547-591,750-752`, tests under `tests/core_test/infra/exness/` and `tests/core_test/infra/brokers/exness/`. Steps: (1) Add `"placePendingOrder": ("POST", "/v1/trading/accounts/{account_id}/orders")`, `"cancelPendingOrder": ("DELETE", ".../orders/{order_id}")` and `"closePosition": ("DELETE", ".../positions/{position_id}")`. Put all three in `_ORDER_OPS` and in the `order_request_interval` op list. (2) `submit_order` routes `STOP_MARKET` to `_submit_pending`. That method uses the `_submit_open` pre-checks, rejects while a position is held, and sends the body `{instrument, side, type: "stop", volume, price, stop_loss_price[, take_profit_price]}`. A MARKET order on the opposite side of a held position for the held units goes to `_submit_close` (DELETE with no `volume` = full close). (3) `cancel_order` calls `cancelPendingOrder` and returns True on the ack. (4) `_on_transaction` maps an `open` deal of a tracked pending order to a FILLED callback [UNVERIFIED: the venue's pending-fill deal payload; test against the existing fakes]. (5) Rewrite the header `:1-6`. Update the LIMIT test at `test_exness_broker_adapter.py:227`. Add tests: three `LIVE_TRADING_DISABLED` fence tests and the body shapes for stop, close and cancel. Verify: `uv run python -m pytest tests/core_test/infra/exness tests/core_test/infra/brokers/exness -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T6.6 Architecture doc (same change).** Files: `docs/system-architecture.md:12,34,37-48`, `docs/deployment.md:124`. Steps: (1) Replace the `:12` decision. A position exits at SL, at TP, on a strategy EXIT, or on a manual close. EXIT means go flat: cancel the pending stop, then close at market. The risk check rejects an entry against an open position. (2) Replace the section `:37-48` with "One pending stop per subscription, closed in full". A new signal cancels then places. Paper fills a stop on the first later bar that touches it (approximation, optimistic in fast markets). There is no partial close and no multi-TP. A venue pending order placed before a trader restart is not tracked after it (not exercised against the venue). (3) Delete `:34` "No current strategy adds" if it is false, else keep it. (4) Make `deployment.md:124` say that pending paper stops are restored too. Verify: `git grep -n -i "SL/TP only\|One take-profit per entry" -- docs | wc -l` prints `0`.

**T6.7 CLOSE.**

Rollback: `git revert`. No prod effect; the Exness ops stay fenced by `exness_client.py:231-232`.

### Phase 07: Snapshot, manual actions, read endpoints (C7, C8 backend, Q2, Q11)

EG.

**T7.1 Snapshot ring.** Files: `strategy_service_interface.py` (set `self.snapshot: dict | None = None` in `__init__`), `strategy_app_service.py`, `core/common/constants.py:20-32`, `app/di/services.py:122-153`. Steps: (1) Add the constants `CACHE_KEY_STRATEGY_SNAPSHOTS = "strategy:snapshots:{subscription_id}"` and `TTL_STRATEGY_SNAPSHOTS = 7 * 86400`, with a WHY comment: no cleanup, an id is never reused, and the TTL covers a 1d weekend. (2) `StrategyAppService(..., cache: Cache | None = None)`, and DI passes `Cache`. Add `self._snapshots: dict[str, deque] = {}` with `maxlen=20`. (3) In `_decide`, after the call, when `strategy.snapshot` is set, append `{bar_start, interval, readings, decision, pending}`, where `pending` comes from `pending_stop` (`{side, price}` or None). (4) In `_on_bar_completed` after `_decide`: `if self._cache and self.trading_until is not None: await self._cache.set(key, list(ring), ttl)`. `unload_strategy` pops the ring. Add tests: a live bar writes one entry, a standby writes nothing, warm-up fills the ring without a Redis write. Verify: `uv run python -m pytest tests/engine_test -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T7.2 Manual action.** Files: `core/domain/subscription/entities.py` (`manual_action: Literal["close","cancel"] | None = None`, round-tripped), `subscription_repository.py` (`request_action(sub_id, action) -> int` filtered on `manual_action: None`; `clear_action(sub_id) -> int`), `strategy_command_service.py` (`request_action`: 404 when missing, 409 `ACTION_PENDING` when 0 matched), `app/routes/strategy.py` (`POST /subscriptions/{sub_id}/close` and `/cancel`, both 202), `strategy_reconcile_app_service.py:77-111`, `strategy_app_service.py` (`async manual_action(sid, action) -> bool`). Steps: (1) The engine returns False without a broker or `trading_until`. `close` runs `_cancel_pending`, then `_submit_exit` with `price=None` when a position is open. `cancel` runs `_cancel_pending`. Each acted action logs INFO `manual_action.done` once. (2) In `_reconcile`, after `_converge_one`, for each `sub.manual_action`: call `await manual_action(...)`, then `clear_action`. A False result logs WARNING `manual_action.nothing_to_do`. (3) Admin guard count becomes `20`. Tests: route 202 and 409, a reconcile tick closes and clears, a standby does nothing. Verify: `uv run python -m pytest tests/engine_test/test_strategy_reconcile_service.py tests/app_test/integration -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T7.3 Read endpoints.** Files: `app/routes/strategy.py`, `strategy_query_service.py:35-91`, `core/infra/persistence/repositories/order_repository.py` (add `list_by_subscription(sub_id, limit)`, served by `ix_orders_subscription_id` at `:29`). Steps: (1) `GET /subscriptions/{sub_id}/snapshots`: the route injects `Cache` directly and returns `await cache.get(key) or []`. (2) `GET /subscriptions/{sub_id}/orders?limit=50`. (3) `list_symbols` adds `position` (from one `find_open()`, mapped by `subscription_id`), `snapshot` (the last ring entry, from one `cache.mget`) and `manual_action`. Verify: `uv run python -m pytest tests/app_test -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T7.4 Docs.** File: `docs/system-architecture.md`. Steps: add two decision lines. (1) Strategy state reaches the api as a bounded Redis ring per subscription. There is no Mongo decision history; it was rejected because it needs cleanup and a symbol cascade. (2) Manual close and cancel travel as `manual_action` on the subscription doc, applied by the lease-holding trader's reconcile tick. Verify: `git grep -n "manual_action" -- docs/system-architecture.md | wc -l` prints at least `1`.

**T7.5 CLOSE.**

Rollback: `git revert`.

### Phase 08: Backtest UI (C9, Q8)

EG.

**T8.1 Interval helper and control.** Files: new `web/src/lib/intervals.ts`, `web/src/lib/intervals.test.ts`, `web/src/components/controls/interval-multi-select.tsx`. Steps: (1) Use `ACTIVE_INTERVALS` (`web/src/constants/active-intervals.ts:3`, includes `1w`) as the list. Add a seconds map and `sortIntervals` and `intervalsError` (strictly ascending, multiples of the lowest), with the same rules as T4.1. (2) The control renders checkbox chips, keeps the value sorted, and marks the lowest as the entry. Tests cover sort, the multiple rule and empty input. Verify: `cd web && npx vitest run src/lib/intervals.test.ts 2>&1 | grep -c "passed"` prints at least `1`, with no failures.

**T8.2 Form and labels.** Files: `web/src/components/backtest/backtest-form.tsx:11,45,76-94,129-154`, `web/src/api/backtest-api.ts:176-187,259-271`, `web/src/hooks/use-strategies.ts` (add `useStrategyDefaults(code)` → `GET /api/v1/strategies/{code}`), `run-header.tsx:12-13,70`, `run-compare-view.tsx:36-43`, `metrics-diff-table.tsx:48-50`, `run-history-rail.tsx:9`, `run-list-item.tsx:34`. Steps: (1) The form posts `intervals`. The params textarea is prefilled from the defaults when the strategy changes, the placeholder is `{}`, and the error hint is generic. (2) The header, legend and diff header show `config_snapshot.intervals` joined with spaces plus `key=value` parameters. A run without `intervals` shows `interval`. (3) The rail filter list comes from `ACTIVE_INTERVALS`. Verify: GATES web part.

**T8.3 CLOSE.**

Rollback: `git revert`.

### Phase 09: Generic subscription UI (C8)

EG.

**T9.1 Client.** Files: `web/src/api/strategy-api.ts:7-36`, `web/src/hooks/use-strategy-mutations.ts`. Steps: (1) `Subscription` gets `intervals`, `parameters`, `position`, `snapshot` and `manual_action`; `interval` goes. (2) Add `addSymbol(code, {symbol, intervals, parameters, broker})`, `editSubscription`, `requestAction(id, 'close'|'cancel')`, `fetchSnapshots` and `fetchOrders`. (3) Add the hooks `useEditSubscription`, `useSubscriptionAction`, `useSnapshots(id)` (5 s) and `useSubscriptionOrders(id)` (5 s), each invalidating `['subscriptions']`. Verify: no verification needed; T9.5 covers it.

**T9.2 Pure view helpers.** Files: new `web/src/lib/subscription-view.ts` and its test. Steps: add `positionText`, `pendingText`, `decisionText`, `parameterRows(defaults, values)`, `parseParameters(json) -> {value} | {error}` and `timeline(orders, trades)` (newest first, with an exit labelled when a filled market order has no SL and no TP). Test each. Verify: `cd web && npx vitest run src/lib/subscription-view.test.ts` reports all tests passed.

**T9.3 Create and edit form.** File: `web/src/components/strategies/new-subscription-dialog.tsx`. Steps: (1) Fields: strategy, symbol, `IntervalMultiSelect`, broker paper or live (`moneyHint`), and a parameter table from `useStrategyDefaults` with a raw JSON toggle. (2) Edit mode takes a subscription, locks strategy, symbol and broker, and is enabled only while stopped. (3) Show the error codes `SUBSCRIPTION_ALREADY_EXISTS`, `SYMBOL_NOT_TRACKED`, `INVALID_INTERVALS`, `INVALID_PARAMETERS`, `BROKER_DISABLED`, `SUBSCRIPTION_RUNNING` and `SUBSCRIPTION_HAS_EXPOSURE`. Verify: no verification needed; T9.5 covers it.

**T9.4 Row and detail.** Files: `strategy-card.tsx`, `strategy-list-sidebar.tsx:17-26`, `strategy-config-card.tsx`, `start-stop-button.tsx` (label), `strategies-page-layout.tsx:142-148,209-215`. Steps: (1) The row shows interval chips (entry highlighted), the badge, state, position, pending and last decision, plus freshness per interval from `useAvailableIntervals` (`web/src/hooks/use-available-intervals.ts:25-30`). (2) The detail panel (main column; see unresolved question 1) has these sections. Readings table. Decision with its bar time. Pending order (from `useSubscriptionOrders`) with Cancel pending. Open position with Close at market. Recent decisions (ring). Orders and trades timeline. Edit and Delete; Delete warns when a position or pending order exists. Both actions use `ConfirmDialog` (`start-stop-button.tsx:129-171`) with the real-money text for `exness`, and the close text says it also cancels a pending order. (3) The chart gets an `IntervalSelector` (`components/controls/interval-selector.tsx`) over `sub.intervals`. Verify: `git grep -n -i -E "triple|macd|force" -- web/src | wc -l` prints `0` (no strategy-specific UI).

**T9.5 CLOSE.**

Rollback: `git revert`.

### Phase 10: Triple Screen (C10)

EG.

**T10.1 Strategy.** Files: new `core/domain/strategy/services/triple_screen_strategy_service.py`, registry entry `"triple_screen"` in `services/__init__.py`. Steps: (1) `DEFAULTS = {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "force_period": 2, "entry_type": "market", "exit_mode": "sl_tp", "risk_reward": 2.0, "stop_lookback": 5, "direction": "both"}`. `__init__` raises `ValueError` unless there are exactly 3 intervals, `entry_type` is in `market|stop`, `exit_mode` is in `sl_tp|strategy`, and the numbers are positive. (2) Top screen: MACD histogram on `context[intervals[2]]` closes; the trend is up when `hist[-1] > hist[-2]`. With fewer than `macd_slow + macd_signal + 1` bars, decide `skip` with "top interval warming up". (3) Middle screen: `EMA(force_period)` of `(close - prev_close) * volume` on `context[intervals[1]]`. A long setup is trend up with force below 0. (4) Entry: keep the last `stop_lookback` entry bars. SL is the lowest low (long). `market` enters at the close; `stop` enters at the current bar's high (the trailing buy stop, replaced each bar while the setup holds). TP is `entry + risk_reward * risk` only for `sl_tp`. (5) EXIT when a stop is armed and the setup is gone, or, for `strategy`, when a position is held and the trend flips. (6) Short entries mirror the long ones. (7) Set `self.snapshot` with three readings (`macd_hist_slope`, `force_index`, `trigger`) and a decision `{action: enter_long|enter_short|exit|hold|skip, reason}`. Verify: no verification needed; T10.2 covers it.

**T10.2 Tests.** Files: new `tests/core_test/unit/domain/strategy/test_triple_screen.py`, `tests/scripts/rubric/test_static_audit.py`. Steps: test each screen, both entry types, both exit modes, EXIT on a lost setup, the 3-interval rule, the snapshot keys, and that `check_strategy_inputs` rejects an unknown key. The rubric test asserts `degrees_of_freedom == len(DEFAULTS)`. Add one backtest over seeded Mongo for each variant that ends `completed`. Verify: `uv run python -m pytest tests/core_test/unit/domain/strategy tests/scripts -q 2>&1 | tail -1` shows `passed` and no `failed`.

**T10.3 CLOSE.**

Rollback: `git revert`.

### Phase 11: Release D2

EG. Also, PRODPY confirms 4 subscriptions, all stopped, and 0 with `broker: exness`. A miss is `NOT_YET`.

**T11.1 [ASK] release.** Steps: (1) Record `free -m`. (2) Ask in Vietnamese. Recommended: yes. Include the list of what ships (STF delete in code, intervals, context, capabilities, snapshot, UI, Triple Screen) and the two prod writes in T11.2 and T11.4. Verify: no verification needed; the owner's yes is recorded in the report.

**T11.2 Pre-deploy migration.** Goal: the new code can read the 4 legacy docs, and the old code ignores the new fields. Steps: PRODPY `migrate_legacy.py`: `update_many({"intervals": {"$exists": False}}, [{"$set": {"intervals": ["$interval"], "intervals_key": "$interval", "parameters": {}}}])` and print `modified_count`. Verify: the output is `modified 4`.

**T11.3 Deploy.** Steps: push `develop:master`, then wait for the master run `completed` with `success`. Verify: `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json conclusion -q '.[0].conclusion'` prints `success`.

**T11.4 Post-deploy.** Steps: (1) PRODPY: `db.subscriptions.drop_index("ix_subscriptions_dedup_triple")`, then print `sorted(index_information())`. (2) Trader log since the deploy: count `reconcile.failed` (expect 0) and `reconcile.unknown_template` (expect 4). (3) `GET /api/v1/strategies/` from inside the api container. (4) Record `free -m`. Verify: the index list contains `ix_subscriptions_dedup_intervals` and not `ix_subscriptions_dedup_triple`; the counts are 0 and 4; the response is `[{"strategy_code":"triple_screen"}]`.

Rollback: `IMAGE_TAG=sha-<previous> bash deploy/vps/10-deploy.sh` [ASK]. The old code ignores the added fields. Its startup re-creates the old unique index, which fails if two new subscriptions share code and symbol; delete the extra one first.

### Phase 12: Triple Screen backtests (C10, Q8)

EG.

**T12.1 Data check.** Steps: PRODPY: count `bars` for `XAUUSD:EXNESS` in 15m, 1h, 4h and 1d over 2025-11-01..2026-10-31. Verify: every count is above 0. Record them.

**T12.2 Runs.** Steps: PRODPY posts 4 runs to `/api/v1/backtest/run` over that range. Set A is `["15m","1h","4h"]` and set B is `["1h","4h","1d"]`. V1 is `{"entry_type":"market","exit_mode":"sl_tp"}` and V2 is `{"entry_type":"stop","exit_mode":"strategy"}`. Name each run `ts-<set>-<variant>`. Poll `GET /api/v1/backtest/{id}` until done. Verify: 4 runs report `completed`.

**T12.3 Record and pick.** Steps: (1) Write a metrics table from `/stats` and the three compare URLs (`/backtest/compare?runs=a,b` for A V1/V2, B V1/V2, and the two winners) to `reports/triple-screen-backtests.md`. (2) [ASK]: which set and variant go to paper. Recommended: the best set with V2, because it exercises the stop entry and the strategy EXIT. Verify: the report holds 4 rows and 3 URLs.

Rollback: none needed. The runs are data the owner can delete in the UI.

### Phase 13: Paper subscription

EG.

**T13.1 Start.** Steps: PRODPY creates the chosen subscription (broker paper) and starts it. After 30 s, read `actual_state`. After two entry bars, read the ring length. Verify: the state is `running` and the ring length is at least 2, with different `bar_start` values.

**T13.2 [USER] UI.** Steps: the owner opens the strategies page and checks the row, readings, decision and chart switcher, then replies `UI OK`. Verify: the reply is recorded.

**T13.3 Observe.** Steps: each run reads the subscription's orders and trades. On a new event, record it: (a) a filled `stop_market` order, (b) a filled market order with no SL and no TP (strategy EXIT), (c) [USER] the owner runs Close at market or Cancel pending with confirmation, and the order shows `filled` or `cancelled` with `manual_action` cleared. A missing event ends with `NOT_YET` and a resume time of now + 12 h. Verify: the report holds a, b and c, each with an order id.

Rollback: stop the subscription (`POST /subscriptions/{id}/stop`).

### Phase 14: One-week 1d comparison (advice item 6)

EG. Also, now is at least `d1_deployed_at + 7 days` (`reports/phase-02-d1.md`); otherwise `NOT_YET`.

**T14.1 Compare.** Steps: PRODPY `compare_1d.py` runs for `XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS`. It reads the 7 full UTC days after D1 from `bars` (`interval` `1d`: OHLCV, `source`, `updated_at`). It fetches the vendor bars with `ExnessAdapter(ExnessClient(get_settings())).fetch_ohlcv(symbol, Interval.DAY_1, n_bars=12)`, a read op not in `_ORDER_OPS` (`core/infra/exness/exness_adapter.py:28-33`). It also counts 1d docs with `source=rest_repair` and `created_at > d1_deployed_at`. Write `reports/phase-14-d1-comparison.md`. Success: OHLC is equal on every pair, volume is within 0.01%, every stored bar is `source=cascade` with `updated_at` before 00:01Z of the next day, and the `rest_repair` count is 0. Verify: the report's last line is `mismatches=0 repair_1d=0`. Any mismatch stops the phase and goes to [ASK] (advice handoff stop rule).

Rollback: if bars differ, revert the cascade commit (Phase 02 rollback) after the owner's decision.

### Phase 15: Prod STF delete (C12) and close

EG. Also, Phase 13 a-c are recorded (or the owner says delete now), and Phase 14 passed.

**T15.1 List.** Steps: PRODPY `stf_list.py` with STF = `["hitnrun2","engulfing","engulfing_pullback30_touch"]` and S = the `_id`s of subscriptions with `strategy_code` in STF. It prints the ids and counts of: `subscriptions` in S, `positions` and `orders` with `subscription_id` in S, `trades` with `run_id` in S, and `backtest_runs`, `backtest_orders` and `backtest_trades` with `strategy_code` in STF. Separately it prints orphans: positions, orders and trades whose link matches no subscription. Save the output to `reports/stf-delete-list.md`. Verify: the subscription count is 4 and the open positions in S are 2.

**T15.2 [ASK] delete.** Steps: show the list and ask in Vietnamese. Recommended: yes for the STF list; orphans need their own yes or no. Verify: no verification needed; the explicit yes is recorded.

**T15.3 Delete and confirm.** Steps: PRODPY `stf_delete.py` uses the same filters (orphans only if approved) and prints the deleted counts, then reruns `stf_list.py`. Verify: the deleted counts equal the listed counts, the rerun prints 0 for every STF filter, and the `triple_screen` subscription is still `running`.

**T15.4 Docs audit and close.** Steps: (1) Apply the line test (`docs/governance/documentation-rules.md:9-25`) to every doc touched in this plan. Check that every path and symbol they name exists. (2) Run `git grep -n -i -E "hitnrun2|engulfing_pullback|interval\b.*triple|dedup_triple" -- docs README.md CLAUDE.md src tests scripts | wc -l`. (3) Write the acceptance table result to the report. Verify: the grep prints `0`, and FULLSUITE matches its expected result.

Rollback: none. The delete is irreversible (owner decision, no backup).

## 6. Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| A1 | Go/no-go recorded per piece | `reports/spike-go-no-go.md` table, 10 rows |
| A2 | No STF code | `git grep -n -E "hitnrun2\|engulfing" -- src tests scripts` = 0; the registry is `{"triple_screen"}` |
| A3 | Subscription carries `intervals`, `parameters`, unique `intervals_key` | T4.2 tests; prod index list (T11.4) |
| A4 | No look-ahead in live, warm-up and backtest | `test_higher_timeframe_context.py` 7 passed |
| A5 | No per-bar context reads | T5.4 (f): at most 2 finds per rollover |
| A6 | 1d cascade correct for one week | `mismatches=0 repair_1d=0` (T14.1) |
| A7 | Stop entry, EXIT, manual close/cancel in paper | Phase 13 a-c order ids |
| A8 | Exness paths fenced | three `LIVE_TRADING_DISABLED` tests (T6.5) |
| A9 | Snapshot visible and changing | T13.1 ring of at least 2 with distinct `bar_start`; `UI OK` |
| A10 | 2 sets x 2 variants comparable | 4 runs, 3 compare URLs (T12.3) |
| A11 | Prod STF data gone | T15.3 rerun = 0 |
| A12 | Gates | FULLSUITE expected red only; lint-imports 6 kept; ratchet 0; `tsc -b` 0 |
| A13 | Architecture doc rewritten | T6.6 grep = 0 |

## 7. Risks

| Risk | L x I | Mitigation |
|---|---|---|
| A context bucket read before the cascade finished (warm-up within 20 s of a boundary) | M x H | The trust rule re-reads once (T5.1); the entry-start instant gives live at least one entry step of margin |
| `sync_1m` late or failing: a partial bucket passes the closed filter | L x H | Data-lag monitor already exists; named here; no new code |
| The on_order_update subscription change double-fills paper immediates | M x H | Status guard plus the explicit one-event test (T6.2) |
| Starting the tracker in backtests changes old backtest outcomes (opposite signals now rejected) | M x L | Old runs keep their stored results; this makes backtest equal live |
| Exness pending-fill payload is not verified against the venue | H x M | Behind the flag; live is out of scope; recorded as negative knowledge (T6.6) |
| Paper stop fills are optimistic | H x L | Documented approximation (A-3) |
| The list poll moves whole rings (about 12 KB per subscription) | L x L | Scale measurement is out of scope; split a latest key when measured |
| The snapshot `pending` in the row lags one entry bar | M x L | The detail panel reads orders, which are fresh |
| Code-metric ratchet has zero headroom | H x L | Raise in its own commit (convention) |
| The wrong delete filter is unrecoverable | L x H | List first, exact filters, explicit yes, orphans separate |

## 8. What this plan does differently from the advice, and why

1. **The closed filter uses the entry bar start, not its end.** The governance rule forbids joining a bar to its own bucket (`no-look-ahead-rules.md:8`). The end instant would need a 20 s wait for the cascade, which breaks the 1m stale budget (`strategy_app_service.py:43`).
2. **"At most one read per rollover" becomes at most two**, because of the trust rule for buckets read before the cascade finished.
3. **The spike is discarded.** It is saved as a patch and the tree is reset. The phases then build clean. This keeps `develop` and CI green, and C11 does not ask to keep the code.
4. **The cascade ships first (D1)**, so the week-long comparison overlaps the build. There are two deploys in total.
5. **The compare cap stays at 3.** Four runs are compared in three views.
6. **EXIT has one meaning, "go flat".** A manual close reuses it, so the cancel and close paths each exist once.
7. **The engine fills the snapshot's `pending` field**, not the strategy, because the order store is the truth.
8. **Cleanup is TTL only**, with no per-delete Redis code.
9. **The legacy prod docs get a one-shot prod migration and an ops index drop** instead of a compatibility shim or drop code in src.
10. **The 1d comparison fetches vendor bars fresh**, because the cascade overwrites the stored REST bar with an upsert on the same key.
11. **Edit covers only intervals and parameters**, and is refused with an open position or a pending order, because the reload would drop paper state.
12. **No web CI job and no jsdom.**

## 9. Unresolved questions for the owner

1. The mockup shows a detail drawer. This plan renders the same sections in the existing main column (`strategy-config-card.tsx`), and a drawer can wrap the panel later. Is the main column acceptable?
2. C13 excludes "changes to the reconcile loop". Q2 and Q5 add an action step in `_reconcile` and a reload branch in `_ensure_instances`, and the loop's period, lease and ownership stay unchanged. Is that within the decision? The alternative is a separate trader poll task on a Redis key.
3. Are the "both variants" V1 = market + SL/TP and V2 = stop + strategy exit, or the full 2x2 (8 runs, more compare views)?
4. Backtest symbol and sets: `XAUUSD:EXNESS`, A = 15m/1h/4h and B = 1h/4h/1d, over 2025-11-01..2026-10-31. Confirm, or name others.
5. Should the freshness column (marked [assumption] in the mockup) be kept? It uses existing sync-status data.
6. Orphan positions, orders or trades that link to no subscription, if any are found in T15.1: delete them or keep them?
7. Is it accepted that a venue pending order placed before a trader restart is not re-tracked? This only matters at a future go-live.

Status: DONE_WITH_CONCERNS
Summary: Candidate 1 plan written with 15 phases, two deploys, all Q1-Q11 answered with evidence, and spike-first gating; it changes the advice on the closed-filter instant (entry bar start) and the compare cap.
Concerns/Blockers: Q2/Q5 touch `_reconcile`/`_ensure_instances`, which may conflict with C13; the Exness pending-fill event payload is unverified against the venue.
