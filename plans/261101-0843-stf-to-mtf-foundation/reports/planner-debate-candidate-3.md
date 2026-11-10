# Candidate 3 — STF to MTF foundation (lens: executability and operations)

Repo `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `e4a998b8`, 2026-11-01. Contract C1-C13 is taken as given. Paths are relative to the repo root; `src/` means `src/pocketquant/`.

## 1. Lens statement

A Sonnet-class worker runs each phase cold, one per phase. So phases are small (one subsystem, one push) and ordered by dependency and by the clock. Every Verify is one command with a literal expected output. Three ops facts shaped the order:
- The 1d cascade (advice item 6) is independent of everything else, and its acceptance needs one week of prod data. It ships first (Phase 03, deploy D-1), so the week runs while the build happens.
- Prod keeps 4 STF subscriptions until the very last phase (C12), and the new code cannot parse a document without `intervals`. So D-2 runs a reviewed additive `$set` on those 4 documents and drops the old unique index before the push. No compatibility code goes into `src/`.
- The spike runs in a throwaway git worktree. Only its report reaches `develop`. Every line of spike code is rewritten from the phase specs, so nothing rough leaks.

## 2. Answers to Q1-Q11

| Q | Choice | Reason and evidence |
|---|---|---|
| Q1 | Store a scalar `intervals_key = ",".join(intervals)` (for example `"15m,1h,4h"`) next to `intervals`. Put the unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`. Drop `ix_subscriptions_dedup_triple` on prod by hand in D-2, before the push. | A unique multikey index treats each list element separately (scout-backend §0.1). The old index is defined at `src/core/infra/persistence/repositories/subscription_repository.py:79-83`. If it stays, every new document has a null `interval`, so two subscriptions with the same code and symbol collide. I chose an ops step over a drop at startup for two reasons: all role containers start at once and race on a drop (`job_history_repository.py:320-321`), and a startup drop stays as dead code forever. |
| Q2 | Add a field `requested_action: "close" \| "cancel" \| null` on the subscription document. Routes `POST /subscriptions/{id}/close` and `/cancel` write it. The reconcile loop runs the action through `StrategyAppService`, then clears the field with a filter that matches the same value. | Routes only write Mongo and the trader owns the brokers (`src/engine/live/strategy_reconcile_app_service.py:77-111`, scout-backend §7). The loop already reads every subscription each tick (`:77-79`), so a new channel or collection is not needed. Running an action twice is harmless: the second close finds no position and the second cancel finds no pending order. |
| Q3 | Start the position tracker inside the backtest sandbox (`await position_app_service.start()` in `build_backtest_sandbox`). | The risk check and the EXIT size then read the same `PositionAppService.get` in live and in backtest (`strategy_app_service.py:545`). The sandbox bus is private (`backtest_sandbox_app_service.py:118-127`), so the tracker cannot leak into live. Today a backtest never rejects an entry against an open position, which is a live/backtest mismatch. This fixes it. |
| Q4 | Delete the takeover branch that drops a paper row with no SL and no TP (`strategy_app_service.py:157-165`). Restore every open paper row. | The branch existed because such a row could never close. EXIT and manual close remove that reason. The test at `tests/engine_test/test_paper_restore.py:209` is inverted. |
| Q5 | `_ensure_instances` compares the loaded config with the document (`intervals`, `parameters`). When they differ and the instance is stopped, it calls `unload_strategy`, then loads again. The edit route updates only a document that is stopped/stopped. | The loop skips an already-loaded instance (`strategy_reconcile_app_service.py:119-120`). `unload_strategy` already exists (`strategy_app_service.py:306-328`). The change is about 5 lines and needs no new field. |
| Q6 | `build_backtest_sandbox(*, bar_repository, calendar_factory)` receives the real `self._bar_repo` and `self._calendar_factory` from `BacktestExecutionService` (`backtest_execution_service.py:59,63,120`). `NoStoredBars` and `Continuous24x7CalendarFactory` move verbatim to `tests/sandbox_stubs.py`. | `build_backtest_sandbox` has one caller (`:120`). The context read uses only `BarRepository.find`, so the 18 importing fixtures keep working without a new stub method. Code that only tests use does not stay in `src/`. |
| Q7 | Fix `web/src/components/monitor/job-status-palette.ts:3,13` (add `interrupted`) in its own commit. Add a CI job `web` (Node 22, as in `web/Dockerfile:4`) that runs `npm ci`, `npm run lint`, `npx tsc -b` and `npm test`, and make `build-web` need it. Test UI logic as pure helpers in `*.test.ts`; add no jsdom. | `tsc -b` exits 2 today (scout-web §8). CI has no web step (`.github/workflows/cicd.yml:49-56`). `web/vitest.config.ts` runs in node on `*.test.ts` only. Adding jsdom and testing-library would be a new dev stack with no second need. |
| Q8 | Keep the 3-run cap. One compare view per variant (its 2-3 interval sets), plus one view with both variants on the picked set. The report lists every run in one table. | The cap lives in 3 files (`routes/backtest_.compare.tsx:16`, `run-compare-view.tsx:15-19`, `run-history-rail.tsx:135`). Lifting it is UI churn the decision does not need. |
| Q9 | Delete `docs/swing-pivot-key-level.md` and its only inbound link (`web/src/lib/indicators/engulfing.ts:65`). Keep `scripts/rubric/static_audit.py`, because it is generic over the registry and parses `_DEFAULTS` (`:12-16,44`). Trim its tests to the unknown-code case in Phase 05. Add the Triple Screen cases in Phase 13. | The doc describes only the deleted strategy (scout-web §6). The rubric still audits any registered strategy. |
| Q10 | `GET /strategies/{code}` returns `default_parameters`, read from a class attribute `default_parameters` that each strategy sets to its `_DEFAULTS`. The subscription form and the backtest form both use it. `GET /backtest/strategies` stays the code list. | The route exists and has no web caller (`app/routes/strategy.py:35-43`, `engine/strategy/strategy_query_service.py:24-31`). It has two real callers, and it keeps `_DEFAULTS` for the rubric. |
| Q11 | TTL only: `strategy:snapshot:{subscription_id}` with an 8-day TTL. No explicit delete. | Ids are UUIDv7 and are never reused. No reader lists these keys. The symbol cascade deletes by symbol pattern (`engine/market_data/tracked_symbols_service.py:130-139`), and a subscription-keyed value has no symbol in its key. 8 days covers a 1d entry interval over a weekend. An explicit delete would add a `Cache` dependency to `StrategyCommandService` for one caller. |

Design decisions the phases rely on (each one was checked against code):
- **D-A: context instant.** `t_ctx = entry_bar_start + INTERVAL_SECONDS[entry] - _CONTEXT_LAG`, the same in every path. In a backtest the simulation time is the bar start (`backtest_app_service.py:109`), and in live the cascade lands the final 5m-4h value about 12-19 s after the bucket end (advice Prod checks). Without a lag, the entry bar that closes at 16:00:00.5 would cache a 4h bar that is still partial for 4 hours, and live would differ from backtest. The lag must be at least the landing p99 and at most the smallest entry step (60 s). The spike measures the landing lag and fixes the value (45 s if p99 ≤ 40 s).
- **D-B: cache.** `StrategyAppService._context: dict[(symbol, interval), (window_start, list[Bar])]`, with `window_start = calendar.bar_start(t_ctx, interval)`. A hit returns the cached list. A miss calls `closed_before(find(symbol, interval, end_date=t_ctx, limit=_CONTEXT_BARS), step, t_ctx)`. The miss result is cached only when the previous bucket is present or has no trading minutes (`calendar.trading_minutes(window_start - step, window_start)` is empty). This stops a late bar from being frozen for a whole window. There is no new class (one caller).
- **D-C: one filter.** `closed_before(bars, step, instant)` is a module-level pure function that keeps `b.datetime + step <= instant`. It replaces the body of `_closed_bars` (`strategy_app_service.py:285-289`). Warm-up does one prefetch per context interval before `on_start()`, then slices in memory with `closed_before`, which keeps the rule "No I/O from here to the direction restore" (`:250`).
- **D-D: paper pending stop.** The engine holds it per subscription (`_pending_stops: dict[sid, Signal]`). On the next entry bar, before the strategy decides, a BUY triggers when `high >= stop` at `max(open, stop)`, and a SELL when `low <= stop` at `min(open, stop)`. A trigger goes through the normal market path (`_process_signal(..., price=fill)`). The paper broker keeps "market orders only" (`paper_broker_adapter.py:146`). Paper fills are synchronous and are never wired to `on_order_update` (`strategy_app_service.py:676-677`), so a broker-side pending order would need a second fill channel. A venue broker (Exness) gets a real `STOP_MARKET` order instead. A restart drops a paper pending stop. The strategy places it again on its next signal.
- **D-E: EXIT.** `_exit(strategy)` cancels the pending stop, then closes an open position with a MARKET order on the opposite side for its full quantity and `price=None` (the paper broker falls back to the current price, `paper_broker_adapter.py:286-297`). An EXIT signal and a manual close both call `_exit`. A manual cancel calls `_cancel_pending`. Both check `trading_until`, so a standby trader never acts.
- **D-F: snapshot.** The strategy sets `self.snapshot = StrategySnapshot(readings, action, reason)` inside `on_bar_completed`. Then the engine, still on the lease, adds `bar_start`, `pending` and `freshness: [{interval, last_closed, stale}]` from the context it served. It appends the entry to an in-memory ring of 50 and writes the whole ring with one `Cache.set(..., ttl)` after `_process_signal`. A backtest sandbox passes `snapshot_cache=None`.

## 3. Phases

| # | Phase | Deploy | Depends on |
|---|---|---|---|
| 01 | Spike A: data path in a throwaway worktree | none | — |
| 02 | Spike B: money path, snapshot, UI; go/no-go table; remove the worktree | none | 01 |
| 03 | 1d cascade for session calendars | D-1 [ASK] | 02 |
| 04 | Web gate: fix tsc, CI web job | none (CI) | 03 |
| 05 | Delete STF code, tests, doc | none (CI) | 04 |
| 06 | Subscription contract (backend + minimal web types) | none (CI) | 05 |
| 07 | Higher-timeframe context: live and warm-up | none (CI) | 06 |
| 08 | Backtest intervals, sandbox wiring, backtest-path context test | none (CI) | 07 |
| 09 | Capabilities in paper: stop entry, EXIT, risk, restore; architecture doc | none (CI) | 08 |
| 10 | Exness close, pending stop, cancel behind the live flag | none (CI) | 09 |
| 11 | Snapshot ring, orders, manual close/cancel backend | none (CI) | 10 |
| 12 | Generic subscription UI and backtest UI | none (CI) | 11 |
| 13 | Triple Screen strategy | none (CI) | 12 |
| 14 | Deploy D-2, backtests on prod, pick the live set | D-2 [ASK] | 13 |
| 15 | Paper run observation | none | 14 |
| 16 | 1d comparison (≥ 7 days after D-1), prod STF delete [ASK], close-out | none | 15 |

## Conventions (every phase)

- **Inherited** from `plans/261028-0652-exness-only-parallel-runtime/plan.md` "Conventions" and "Ops recipe": strict run order; the entry gate runs first; a miss ends with exactly `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: ... --from NN after <UTC>`; [ASK] questions go to the owner in Vietnamese and lead with `Recommended:`; only an explicit yes counts; `git grep` (no `rg`); secrets never go on a command line; the SSH key steps are run and the key is removed with `rm -f .cache/ssh/vps_key`; the push uses the camping89 token URL; no plan ids in code, tests or commits; the literal **Failure Protocol** block (a failed Verify stops the phase and goes to `kongming`).
- **Every entry gate:** `git status --porcelain -- src web deploy tests scripts docs` prints nothing; `git rev-parse --abbrev-ref HEAD` prints `develop`; `docker ps` exits 0.
- **Report:** every phase appends a `## Phase NN` section to `plans/261101-0843-stf-to-mtf-foundation/reports/run-log.md`. It records commits, Verify outputs, and any metric-ceiling raise.
- **Standard Verify commands** (run from the repo root; the result must match exactly):
  - `PY`: `uv run python -m pytest tests/ -q 2>&1 | tail -1` contains `4 failed` and `4 errors`, and `uv run python -m pytest tests/ -q 2>&1 | grep -E "^(FAILED|ERROR) " | grep -v -E "test_utc_runtime_guard.py|test_cron_trigger_timezone.py" | wc -l` prints `0`.
  - `LINT`: `uv run lint-imports | grep -c "Contracts: 6 kept, 0 broken."` prints `1`.
  - `METRICS`: `uv run python scripts/code_metrics.py --ratchet; echo exit=$?` prints `exit=0`. If it fails only on `max_tiny_share`/`max_delegations`, set the ceiling in `pyproject.toml` `[tool.code-metrics]` to the value `--json` prints. Commit that alone as `chore(metrics): raise the code-metric ceiling` and log it. Never pad code to pass.
  - `WEB` (from Phase 04 on): `cd web && npm run lint >/dev/null && npx tsc -b && npm test 2>&1 | grep -c " failed"`. It exits 0 and prints `0`.
  - `PUSH`: the inherited push command to `develop`, then `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json conclusion,headSha -q '.[0]'` after `sleep 15` and `gh run watch <id> --exit-status`. It exits 0 and `headSha` equals `git rev-parse HEAD`.
  - `MONGO`: write the Python to `.cache/q.py` and run `ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env exec -T api python -' < .cache/q.py`. Every script starts with `from pymongo import MongoClient; from pocketquant.core.config import get_settings; s=get_settings(); db=MongoClient(str(s.mongodb_url))[s.mongodb_database]`. Phase 01 Task 1.2 proves this route works.
- **Deploy recipe** (D-1, D-2): (1) MONGO-style `free -m` via `ssh ... 'free -m'`, logged; (2) [ASK] with the commit list `git log --oneline origin/master..develop`; (3) push `develop:master`; (4) watch the master run, which must conclude `success` (the run includes `11-verify.sh`); (5) `free -m` again, logged; (6) the phase's post-deploy checks.

---

## Phase 01 — Spike A: data path

**Entry gate:** the standard checks; `git worktree list` does not list `pocketquant-spike`.

**Task 1.1** Goal: an isolated spike tree. Target: `D:/w/_me/algotrading/pocketquant-spike` (branch `spike/mtf`, local only). Steps: `git worktree add ../pocketquant-spike -b spike/mtf develop`; `cd ../pocketquant-spike && uv sync --frozen`. Success: the worktree exists. Verify: `git -C ../pocketquant-spike rev-parse --abbrev-ref HEAD` prints `spike/mtf`.

**Task 1.2** Goal: measure on prod (read-only) how long after a bucket end the final cascade value lands. Target: the MONGO route. Steps: the script prints `ok`, then, for each Exness symbol and for 5m, 15m, 1h and 4h over the last 72 h of closed buckets, prints `symbol interval n p99_s max_s share_le_40s`, where lag = `updated_at - (datetime + step)`. Success: the route works and the table is in `reports/spike-results.md` §G4. Verify: `grep -c "^| G4" plans/261101-0843-stf-to-mtf-foundation/reports/spike-results.md` prints `1`.

**Task 1.3** Goal: rough code for subscription `intervals`/`parameters`, context per D-A to D-C, and `BacktestConfig.intervals` with the real sandbox repos (Q6). Target: the spike tree only. Steps: implement the minimum. Then write three tests in the spike tree, all asserting that the first entry bar of a new 1h bucket sees the previous bucket's close: (a) live, through `_on_bar_completed` with `bar_end` set; (b) warm-up, through `start_strategy` over stored bars; (c) a backtest, through `BacktestExecutionService.run` on the test Mongo. Add (d) a counting `find` wrapper that asserts calls = context rollovers, and (e) two subscriptions `["15m","1h"]` and `["15m","4h"]` that both insert, while a third copy of `["15m","1h"]` raises. Success: all five pass in the spike tree. Verify: `cd ../pocketquant-spike && uv run python -m pytest <the five node ids> -q 2>&1 | tail -1` contains `5 passed`.

**Task 1.4** Goal: the backtest cost. Steps: seed the test Mongo with 100 000 1m bars and their 1h/4h aggregates, then time one backtest of a fake strategy over `["1m","1h","4h"]` and one over `["1m"]`. Success: the result is recorded in §G5 as `find_calls`, `rollovers`, `t_mtf_s`, `t_stf_s`. no verification needed (Task 2.4 checks §G5).

**Rollback:** `git worktree remove --force ../pocketquant-spike && git branch -D spike/mtf`. Nothing on `develop` changed.

## Phase 02 — Spike B: money path, snapshot, UI, decision

**Entry gate:** the standard checks; the spike worktree exists; `spike-results.md` has rows G1-G5 (`grep -c "^| G[1-5]"` prints `5`).

**Task 2.1** Goal: rough paper capabilities per D-D/D-E, Q3 and Q4. Tests in the spike tree: (f) a stop entry fills on the next bar's touch at `max(open, stop)`; (g) a new stop signal replaces the old one; (h) EXIT closes the open paper position and a trade is recorded; (i) EXIT in a backtest closes using the sandbox tracker; (j) a manual close through `requested_action` runs on the next reconcile tick and clears the field. Verify: `uv run python -m pytest <5 node ids> -q 2>&1 | tail -1` in the spike tree contains `5 passed`.

**Task 2.2** Goal: the snapshot reaches the UI. Steps: write the ring to Redis per D-F; add `GET /subscriptions/{id}/snapshot`; show the JSON raw in a `<pre>` inside `strategy-config-card.tsx`. Verify: test (k), where `GET` returns the ring after two bars (2 items, different `bar_start`), passes. `cd ../pocketquant-spike/web && npx tsc -b 2>&1 | grep -c "error TS"` prints `2`, which is only the 2 known `job-status-palette.ts` errors (the spike tree branches before Phase 04 fixes them).

**Task 2.3** Goal: confirm the Exness API paths (read-only). Steps: WebFetch `https://www.exness-api.com/exness_api.yaml`. Record the method and path for: closing a position, creating a `stop` order, cancelling a pending order, and the event or deal field that links a pending fill to its order. Success: four rows in §G11, each `present` or `absent`. Verify: `grep -c "^| G11" .../spike-results.md` prints `1`.

**Task 2.4** Goal: the go/no-go table. Target: `reports/spike-results.md`, a table `| G# | piece | evidence | go/no-go |` with: G1 subscription key; G2 closed filter in 3 paths; G3 cache rollover; G4 landing lag ≤ 40 s p99 (sets `_CONTEXT_LAG` = 45 s; if p99 is 40-55 s, use p99 + 5 s; above 55 s is no-go); G5 backtest cost (`find_calls ≤ rollovers + 2` and `t_mtf_s ≤ 2 × t_stf_s`); G6 stop entry; G7 EXIT live; G8 EXIT backtest; G9 manual action channel; G10 snapshot to UI; G11 Exness paths; G12 traps found (free text). Add the "Kept vs rewritten" table: **kept** = this report, the measured numbers, the test scenarios (a)-(k) as prose with their asserted values, and the traps; **rewritten** = all code and tests. Never cherry-pick, merge, `git checkout spike/mtf -- <path>` or copy a spike file. Verify: `grep -c -E "^\| G([1-9]|1[0-2]) " .../spike-results.md` prints `12`.

**Task 2.5** Goal: decide and clean up. Steps: if G2, G3, G4 (Mongo context path) or G7/G8 (paper EXIT) is no-go, [ASK] the owner with the evidence, and end with `NOT_YET: spike no-go <G#>` until the owner decides. If G11 has an `absent` row, record it; Phase 10 then stops at its gate. Otherwise remove the tree: `git worktree remove --force ../pocketquant-spike && git branch -D spike/mtf`. Commit the plan dir: `git add plans/261101-0843-stf-to-mtf-foundation && git commit -m "docs(plans): record the multi-timeframe spike results"`. Verify: `git branch --list spike/mtf | wc -l` prints `0` and `git status --porcelain -- src web tests` prints nothing.

**Rollback:** report only; delete the commit with `git revert`.

## Phase 03 — 1d cascade for session calendars (D-1)

**Entry gate:** the standard checks; `spike-results.md` G2-G4 and G7-G8 read `go`.

**Task 3.1** Goal: cascade 1d for every calendar (advice item 6). Targets: `src/engine/market_data/app_services/cascade_aggregator.py` (delete `_INTRADAY_CASCADE_TFS` `:26-31`, the comment `:34-37` and `cascade_tfs()` `:38-41`; `cascade_for_symbol` iterates `CASCADE_TFS` at `:132`; drop the `CALENDAR_CRYPTO_24_7` import `:10`); `src/engine/market_data/tracked_symbols_backfill.py` (delete the DAY_1 override `:80-102` and the import `:10`); `src/engine/market_data/app_services/sync_jobs.py:48-56` (comment: 1d cascades for every calendar; 1w stays REST because Binance weeks open Monday and Exness weeks Sunday). Success: `git grep -n "cascade_tfs\|_INTRADAY_CASCADE_TFS" -- src tests` prints nothing after Task 3.2.

**Task 3.2** Goal: the tests per advice item 6. Targets: `tests/app_test/market_data/test_cascade_aggregator.py:511-544` becomes two tests: a session calendar cascades `DAY_1` stamped at UTC midnight with `session_date` = the UTC date, and `find` is called with `limit = len(trading_minutes) + 5` (1383 for an XAUUSD Monday, 124 for its Sunday); the 24/7 order is unchanged. In `tests/engine_test/market_data/test_backfill_daily_mode.py`, delete the tests at `:73,97,114` and the header `:1-3`, keep `:84`, add `test_a_session_calendar_daily_auto_backfill_cascades`, and remove an unused `CALENDAR_EXNESS_FX` import. Verify: `uv run python -m pytest tests/app_test/market_data/test_cascade_aggregator.py tests/engine_test/market_data/test_backfill_daily_mode.py tests/app_test/market_data/test_cascade_calendar_golden.py -q 2>&1 | tail -1` contains `passed` and no `failed`; then PY, LINT, METRICS.

**Task 3.3** Goal: commit and push. Steps: `git commit -am "feat(market-data): cascade the daily bar for session calendars"`; PUSH. Verify: PUSH.

**Task 3.4** Goal: deploy D-1 by the recipe. [ASK] gist: "Deploy the 1d cascade for Exness symbols now. Recommended: yes, because it is independent and starts the one-week check." Post-deploy: log `d1_deploy_utc=<ISO>` in run-log. Verify: `grep -c "^d1_deploy_utc=" .../run-log.md` prints `1`.

**Rollback:** `git revert <sha>` and redeploy. REST 1d stays in `SYNC_INTERVALS`, so `sync_repair` refills 1d.

## Phase 04 — Web gate

**Entry gate:** standard.

**Task 4.1** Goal: `tsc -b` goes green. Target: `web/src/components/monitor/job-status-palette.ts`. Add `interrupted` to `STATUS_COLOR` (`:3`) and `STATUS_LABEL` (`:13`), using the `failed` colour and the label `interrupted`. Commit `fix(web): cover the interrupted job status in the palette`. Verify: `cd web && npx tsc -b; echo exit=$?` prints `exit=0`.

**Task 4.2** Goal: a CI web job. Target: `.github/workflows/cicd.yml`. Add job `web` (`runs-on: ubuntu-24.04`, `timeout-minutes: 10`, `actions/checkout@v5`, `actions/setup-node@v4` with `node-version: 22`, `cache: npm`, `cache-dependency-path: web/package-lock.json`; steps in `web/`: `npm ci`, `npm run lint`, `npx tsc -b`, `npm test`). Change `build-web` `needs: [tests]` (`:106`) to `needs: [tests, web]`. Commit `ci: run web lint, type check and tests`. Verify: PUSH, then `GH_TOKEN=... gh run view <id> --json jobs -q '.jobs[].name' | grep -c "^web$"` prints `1`.

**Rollback:** revert the commits.

## Phase 05 — Delete STF

**Entry gate:** standard; WEB passes.

**Task 5.1** Goal: tests stop depending on STF classes. Target: new `tests/strategy_fakes.py` with `LongEveryBarStrategy(IStrategyService)` (LONG with SL −1% / TP +1% from `bar["close"]` when flat, and `default_parameters = {}`), `CountingStrategy` (signals LONG once it has seen `parameters["min_bars"]` bars), and `use_fake_registry(monkeypatch)`, which does `monkeypatch.setitem(STRATEGY_REGISTRY, "test_long", LongEveryBarStrategy)` and the same for `"test_counting"`. Repoint every file that scout-backend §2 lists under "Import an STF class directly" and "Use a code as a registry key that must resolve" to these codes. For "opaque string" files, replace the code with `test_long`. Success: no test imports an STF module. Verify: `git grep -n -E "engulfing_pullback|EngulfingStrategy" -- tests | wc -l` prints `0`.

**Task 5.2** Goal: delete the STF code. Delete: `src/core/domain/strategy/services/{engulfing,engulfing_pullback30_touch}_strategy_service.py`, `src/core/domain/strategy/patterns/` (whole dir), the two registry entries and the `__all__` names (`services/__init__.py:11-22`, which leaves `STRATEGY_REGISTRY: dict[str, type] = {}`), the tests `tests/core_test/unit/domain/strategy/test_{engulfing,engulfing_pullback30_touch}.py`, `tests/core_test/unit/domain/strategy/patterns/`, and `tests/backtest_test/engine/test_{engulfing,engulfing_pullback30_touch}_backtest.py`. Remove the module path from `tests/core_test/test_core_layout_contract.py:11`. Verify: `git grep -n -i -E "engulfing" -- src | wc -l` prints `0`.

**Task 5.3** Goal: the rubric, manual files, doc and web comments. Steps: in `tests/scripts/rubric/test_static_audit.py`, delete everything except `test_unknown_strategy_falls_back_not_raises`; replace `engulfing` in `tests/http/backtest/*.bru` and `tests/manual/api-test.http` with `triple_screen`; delete `docs/swing-pivot-key-level.md`; rewrite `web/src/lib/indicators/engulfing.ts:4-6` to `// Chart overlay only; no strategy trades on it. Locked by its golden fixture (engulfing.test.ts).`; rewrite `engulfing.test.ts:4-5` to `// The web owns this fixture.`; remove the doc link at `engulfing.ts:65`. Verify: `git grep -n -i -E "engulfing_detector|swing-pivot|Python detector" -- src tests web/src docs scripts README.md | wc -l` prints `0`.

**Task 5.4** Goal: gates and push. Commit `refactor(strategy): remove the single-timeframe strategies`. Verify: PY, LINT, METRICS, WEB, PUSH.

**Rollback:** `git revert` the commit. No data changed.

## Phase 06 — Subscription contract

**Entry gate:** standard.

**Task 6.1** Goal: the domain shape. Targets: `src/core/domain/shared/value_objects.py`: add `validate_intervals(intervals: list[str]) -> tuple[Interval, ...]`, which raises `DomainError(..., error_code="INVALID_INTERVALS", status_code=422)` when the list is empty, has a duplicate or is unsorted, or when a higher interval's seconds are not a multiple of the entry interval's. `src/core/domain/subscription/entities.py:29-70`: replace `interval` with `intervals: tuple[Interval, ...]`, add `parameters: dict` (default `{}`), `to_mongo` writes `intervals`, `intervals_key` and `parameters`, `from_mongo` reads `intervals`, and `SubscriptionAlreadyExistsError` carries `intervals_key`. `src/core/domain/strategy/value_objects.py:26-35`: `StrategyConfig.interval` becomes `intervals: tuple[str, ...]` with property `entry_interval`. Add `default_parameters: ClassVar[dict] = {}` to `IStrategyService` (`strategy_service_interface.py:16`). Steps: update all 29 `StrategyConfig(` sites (`git grep -n "StrategyConfig(" -- src tests`) and the 12 `Subscription(` test sites; replace `config.interval` reads with `config.entry_interval`. Verify: `git grep -n -E "config\.interval\b|sub\.interval\b" -- src | wc -l` prints `0`.

**Task 6.2** Goal: the repository. Target: `subscription_repository.py`: the index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`, unique; a new method `update_config(sub_id, intervals, parameters) -> int` that filters `{_id, desired_state: "stopped", actual_state: "stopped"}`. Update `tests/core_test/infra/persistence/test_subscription_repository.py:75-104` and add `test_two_interval_sets_sharing_the_entry_interval_coexist`. Verify: `uv run python -m pytest tests/core_test/infra/persistence/test_subscription_repository.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 6.3** Goal: create, edit and defaults. Targets: `src/engine/strategy/strategy_command_service.py`: `add_symbol(strategy_code, symbol, intervals, parameters, broker)`. It validates the intervals, rejects keys missing from `cls.default_parameters` (`INVALID_PARAMETERS`, 422), and builds `cls(StrategyConfig(...merged...))` inside `try`, mapping a `ValueError` to `INVALID_PARAMETERS`. A new method `edit(sub_id, intervals, parameters)` validates the same way and calls `update_config`; on 0 matches it raises `NotFoundError` when the id is missing, else `DomainError("SUBSCRIPTION_NOT_STOPPED", 409)`. `strategy_query_service.py`: `list_symbols` returns `intervals` and `parameters`; `get_one` returns `default_parameters`. `app/routes/strategy.py`: `CreateSubscriptionBody{symbol, intervals: list[str], parameters: dict = {}, broker}`; `PATCH /subscriptions/{sub_id}` with `EditSubscriptionBody{intervals, parameters}`. In `tests/app_test/integration/test_admin_token_guard.py:46`, 17 becomes 18. Tests use `use_fake_registry`. Verify: `uv run python -m pytest tests/engine_test/test_strategy_service.py tests/app_test/integration/test_strategy_subscriptions_api.py tests/app_test/integration/test_admin_token_guard.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 6.4** Goal: reconcile passes the config and reloads an edit (Q5). Target: `strategy_reconcile_app_service.py:115-161`: `StrategyConfig(intervals=..., parameters=sub.parameters, ...)`. For an existing instance whose `config.intervals`/`config.parameters` differ from the doc and that is not running, `await self._strategy_service.unload_strategy(sub_id)`, then load. New test `test_an_edited_stopped_subscription_reloads_its_config`. Verify: `uv run python -m pytest tests/engine_test/test_strategy_reconcile_service.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 6.5** Goal: the web still type-checks. Targets: `web/src/api/strategy-api.ts:7-32` (`intervals: string[]`, `parameters`), `hooks/use-strategy-mutations.ts:45-53` (sends `intervals: [interval]`), `strategy-card.tsx:77` and `strategy-list-sidebar.tsx:17-26` (`intervals.join(' · ')`), `strategy-config-card.tsx:109-112,151-159`, and `strategies-page-layout.tsx:142,209` (`intervals[0]`). Verify: WEB.

**Task 6.6** Goal: docs and push. Rewrite `docs/code-standards.md:93,95` (the binding is `(strategy_code, symbol, intervals)`, and the guard is the unique index on the joined key). Commit `feat(subscription): ordered intervals and strategy parameters`. Verify: PY, LINT, METRICS, WEB, PUSH.

**Rollback:** `git revert`. No prod change happens before D-2.

## Phase 07 — Higher-timeframe context (live and warm-up)

**Entry gate:** standard; now is after the first 00:05Z following `d1_deploy_utc`, and the D-1 day-1 check passes: MONGO prints `<symbol> cascade <updated_at>` for yesterday's 1d bar of each of the 3 Exness symbols, with `source == "cascade"` and `updated_at < 00:01Z` (3 lines). If the time has not come, end with `NOT_YET`.

**Task 7.1** Goal: one filter and the cache per D-A to D-C. Target: `src/engine/strategy/strategy_app_service.py`. Add module constants `_CONTEXT_BARS = 200` and `_CONTEXT_LAG = timedelta(seconds=<G4 value>)` with a `#` comment giving the reason (the cascade lands about 12-19 s after a bucket end, so a bucket is read only after the lag). Add the module function `closed_before`; make `_closed_bars` use it; add `self._context = {}` in `__init__`; add `async def _context_for(self, config, t_ctx) -> dict[str, list[Bar]]`. A per-miss `strategy.context_requery` is logged at DEBUG; a WARNING `strategy.context_previous_bucket_missing` is logged once per (symbol, interval, window). Verify: no verification needed (7.3 covers it).

**Task 7.2** Goal: strategies receive context. Steps: in `_on_bar_completed` (`:363-432`), build the bar dict once through a new helper `_bar_dict(symbol, interval, o, h, l, c, v, start)`, which the warm-up at `:253-263` also uses (DRY). Add `bar["context"] = await self._context_for(...)` only when `len(config.intervals) > 1`. `_find_strategies` (`:492-502`) matches `config.entry_interval`. In `start_strategy`, before `on_start()`, prefetch each context interval with `find(end_date=now, limit=_CONTEXT_BARS + span_buckets)`. In the replay loop, slice with `closed_before(...)[-_CONTEXT_BARS:]` and do no await. Verify: no verification needed.

**Task 7.3** Goal: rewrite the spike tests (a), (b) and (d) from `spike-results.md`. Target: new `tests/engine_test/test_strategy_context.py`: `test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`, `test_warm_up_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`, `test_context_is_read_once_per_rollover`, `test_a_partial_bucket_is_never_served`, `test_a_missing_previous_bucket_is_requeried_next_bar`, `test_a_session_gap_bucket_is_cached`. Verify: `uv run python -m pytest tests/engine_test/test_strategy_context.py tests/engine_test/test_strategy_warm_up.py tests/engine_test/test_strategy_entry_guards.py -q 2>&1 | tail -1` contains `passed` and no `failed`; then PY, LINT, METRICS.

**Task 7.4** Commit `feat(strategy): closed higher-timeframe context from stored bars`; PUSH.

**Rollback:** `git revert`. Strategies with one interval are unaffected because context is skipped.

## Phase 08 — Backtest intervals and sandbox wiring

**Entry gate:** standard.

**Task 8.1** Goal: `BacktestConfig.intervals`. Targets: `src/core/domain/backtest/config.py:10-28` (`interval` becomes `intervals: list[str]`); `engine/backtest/backtest_command_service.py:17-67` (`RunBacktestCommand.intervals`, validated by `validate_intervals`); `backtest_execution_service.py:32-46,110-118`; `backtest_app_service.py:103-123` (streams `intervals[0]`); `backtest_report_app_service.py:308-316,336,359` (annualizes on `intervals[0]` and persists `intervals`); `core/domain/backtest/entities.py:25-27,51,64,96`; `backtest_repository.py:34-51,125-128` (filters `intervals.0`; the index is `ix_backtests_strategy_symbol_intervals_started`); `app/routes/backtest.py:157-196` (the `interval` query filters the entry interval). Verify: `git grep -n -E "config\.interval\b|\[\"interval\"\]" -- src/pocketquant/engine/backtest src/pocketquant/core/domain/backtest | wc -l` prints `0`.

**Task 8.2** Goal: the sandbox reads Mongo and tracks positions (Q3, Q6). Target: `backtest_sandbox_app_service.py:58-70,125-139`: the signature becomes `build_backtest_sandbox(*, bar_repository, calendar_factory)`; call `await position_app_service.start()`; rewrite the comment at `:118-124`; move `NoStoredBars` and `Continuous24x7CalendarFactory` verbatim to `tests/sandbox_stubs.py` and fix the 18 importing test files (`git grep -l "NoStoredBars\|Continuous24x7CalendarFactory" -- tests`). The caller at `backtest_execution_service.py:120` passes `self._bar_repo` and `self._calendar_factory`. Verify: `git grep -n "NoStoredBars\|Continuous24x7CalendarFactory" -- src | wc -l` prints `0`.

**Task 8.3** Goal: rewrite spike test (c). Target: new `tests/backtest_test/test_backtest_context.py::test_backtest_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close` (test Mongo, seeded 15m and 1h bars, a context-recording fake strategy, `BacktestExecutionService.run`) and `::test_backtest_rejects_an_entry_against_its_open_position`. Web: `web/src/api/backtest-api.ts:176-302` uses `intervals`; `backtest-form.tsx:86-94` sends `intervals: [interval]`; `run-header.tsx:70` and `run-list-item.tsx:34` use `intervals.join(' · ')`. Verify: `uv run python -m pytest tests/backtest_test -q 2>&1 | tail -1` contains `passed` and no `failed`; then PY, LINT, METRICS, WEB.

**Task 8.4** Commit `feat(backtest): run over ordered intervals with stored context`; PUSH.

**Rollback:** `git revert`.

## Phase 09 — Capabilities in paper

**Entry gate:** standard.

**Task 9.1** Goal: the Signal and the risk check. Targets: `src/core/domain/strategy/value_objects.py:9-23`: add `entry_type: Literal["market", "stop"] = "market"`; `__post_init__` requires `entry_price` when `entry_type == "stop"`. `src/engine/execution/risk_check.py:10-46`: EXIT returns `(True, "")` with an open position and `(False, "no open position")` without one; FLAT stays rejected; rewrite the comment `:11-13`. `tests/engine_test/test_risk_check.py:40` becomes `test_exit_passes_only_with_an_open_position` plus `test_flat_is_rejected`. Verify: `uv run python -m pytest tests/engine_test/test_risk_check.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 9.2** Goal: the engine paths per D-D and D-E. Target: `strategy_app_service.py`: `_process_signal(..., price: float | None = None)` (`current_price = price if price is not None else event.close`); the EXIT branch calls `_exit`; a `stop` entry calls `_cancel_pending`, then stores it in `_pending_stops[sid]` (paper) or submits `OrderType.STOP_MARKET` with `stop_price=entry_price` (other brokers); in `_on_bar_completed`, check the trigger before calling the strategy, under the same stale/gap/inflight skips; `_create_order` (`:633-651`) takes its side from the direction and the position. Delete the takeover drop `:157-165` (Q4). Rewrite `tests/engine_test/test_paper_restore.py:209` to `test_a_paper_position_without_exits_is_restored`. New `tests/engine_test/test_paper_capabilities.py`: rewrites of spike (f), (g), (h); `test_exit_with_nothing_open_is_a_no_op`; `test_a_standby_trader_never_exits`. Verify: `uv run python -m pytest tests/engine_test -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 9.3** Goal: rewrite spike test (i). Target: `tests/backtest_test/test_backtest_context.py::test_backtest_exit_closes_through_the_sandbox_tracker` and `::test_backtest_stop_entry_fills_on_the_next_bar_touch`. Verify: `uv run python -m pytest tests/backtest_test/test_backtest_context.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 9.4** Goal: the architecture doc in the same commit (C6). Target: `docs/system-architecture.md:12` becomes a decision: exits are SL/TP, a strategy EXIT, or a manual close; a paper stop entry is held by the engine and fills on the next entry bar's touch, approximated from high/low; a restart drops it. The `:37-48` table header becomes "One take-profit per entry; one position per subscription", and its rows add EXIT and stop entry. Check `docs/deployment.md:124`. Verify: `git grep -n -i "SL/TP only\|rejects EXIT" -- docs | wc -l` prints `0`; then PY, LINT, METRICS.

**Task 9.5** Commit `feat(execution): stop entries and strategy exits`; PUSH.

**Rollback:** `git revert`. No prod change happens before D-2.

## Phase 10 — Exness capabilities behind the live flag

**Entry gate:** standard; `spike-results.md` G11 has 4 `present` rows. If not, [ASK] the owner whether to ship the Exness close only, and stop with `NOT_YET`.

**Task 10.1** Goal: the client ops. Target: `src/core/infra/exness/exness_client.py:28-47,110-120`: add `closePosition`, `createOrder` and `cancelOrder` with the G11 method and path; add all three to `_ORDER_OPS` and to the order pacer tuple at `:115`. Test: extend `tests/core_test/infra/exness/test_exness_client.py:284` parametrized over the 3 ops, each raising `LIVE_TRADING_DISABLED`. Verify: `uv run python -m pytest tests/core_test/infra/exness/test_exness_client.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 10.2** Goal: the adapter. Target: `src/core/infra/brokers/exness/exness_broker_adapter.py`. `submit_order` (`:209-214`) routes an opposite-side MARKET order with a held position to `_submit_close` (`closePosition`, full volume, tracked like `_send_tracked` `:385-428`); routes `STOP_MARKET` to `_submit_pending` (`createOrder` type stop, with SL); keeps rejecting everything else. `cancel_order` (`:750-752`) calls `cancelOrder`. A pending fill is mapped to `OrderResult FILLED` through the G11 link field. Rewrite the header `:1-6`. `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py:227` keeps LIMIT rejected. New tests with the fake client: close, pending place, cancel, pending fill, entries-paused still allows close. Verify: `uv run python -m pytest tests/core_test/infra/brokers/exness -q 2>&1 | tail -1` contains `passed` and no `failed`; then PY, LINT, METRICS.

**Task 10.3** Commit `feat(exness): close, stop orders and cancel behind the live flag`; PUSH.

**Rollback:** `git revert`. The live flag stays off on prod (`deploy/compose.prod.yml` pins the api; the trader flag is false).

## Phase 11 — Snapshot, orders, manual actions

**Entry gate:** standard.

**Task 11.1** Goal: the snapshot per D-F. Targets: `src/core/domain/strategy/value_objects.py`: `Reading(interval, name, value, ok)` and `StrategySnapshot(readings, action, reason)`; `IStrategyService.snapshot: StrategySnapshot | None = None` in `__init__`; `src/core/common/constants.py`: `CACHE_KEY_STRATEGY_SNAPSHOT = "strategy:snapshot:{subscription_id}"` and `TTL_STRATEGY_SNAPSHOT = 8 * 86400`; `StrategyAppService.__init__` gets `snapshot_cache: Cache | None = None` (live DI `app/di/services.py:122-153` passes `Cache`; the sandbox passes nothing). Log one WARNING `strategy.snapshot_write_failed` per failure streak. Verify: no verification needed.

**Task 11.2** Goal: the read endpoints. Targets: `app/routes/strategy.py`: `GET /subscriptions/{id}/snapshot` (injects `Cache`, returns the ring or `[]`) and `GET /subscriptions/{id}/orders?limit=50`; the latter uses `strategy_query_service.get_orders` and a new `OrderRepository.find_by_subscription(sub_id, limit)` (index `ix_orders_subscription_id` exists, `order_repository.py:29`). Verify: no verification needed.

**Task 11.3** Goal: manual actions (Q2). Targets: `Subscription.requested_action`; repo `set_requested_action(sub_id, action) -> int` and `clear_requested_action(sub_id, action)`; `StrategyCommandService.request_action(sub_id, action)`; routes `POST /subscriptions/{id}/close` and `/cancel` (202); reconcile `_reconcile` calls `StrategyAppService.run_requested_action(sub_id, action)`, which returns False while not on the lease (the field is kept), and clears the field otherwise; an unknown instance clears it with a WARNING. In `test_admin_token_guard.py:46`, 18 becomes 20. Rewrite spike tests (j) and (k) in `tests/engine_test/test_manual_actions.py` and `tests/app_test/integration/test_subscription_snapshot_api.py`, plus `test_a_backtest_writes_no_snapshot` and `test_a_standby_trader_writes_no_snapshot`. Verify: `uv run python -m pytest tests/engine_test/test_manual_actions.py tests/app_test/integration/test_subscription_snapshot_api.py tests/app_test/integration/test_admin_token_guard.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

**Task 11.4** Goal: the doc. `docs/system-architecture.md` gets one decision line: strategy state reaches the api as a TTL'd Redis ring that the lease-holding trader writes; there is no Mongo decision history; manual actions travel as a subscription field that the reconcile loop runs. Verify: PY, LINT, METRICS; commit `feat(strategy): decision snapshot and manual close or cancel`; PUSH.

**Rollback:** `git revert`. The Redis keys expire by TTL.

## Phase 12 — Generic UI (subscriptions and backtest)

**Entry gate:** standard; WEB passes.

**Task 12.1** Goal: pure helpers with tests. New `web/src/lib/intervals.ts` (`INTERVAL_ORDER` re-export with `1w`; `sortIntervals`; `intervalError(list)` mirroring the backend rule), `web/src/lib/subscription-view.ts` (`rowView(sub, position, snapshot)` → state, position text, pending text, last decision, freshness chips; `parametersFromDefaults(defaults, values)`), each with a `*.test.ts`. Replace the three short interval lists (`new-subscription-dialog.tsx:7`, `backtest-form.tsx:11`, `run-history-rail.tsx:9`) with `INTERVAL_ORDER`. Verify: `cd web && npx vitest run src/lib/intervals.test.ts src/lib/subscription-view.test.ts 2>&1 | grep -c " failed"` prints `0`.

**Task 12.2** Goal: hooks. New `hooks/use-strategy-defaults.ts` (`GET /api/v1/strategies/{code}`), `hooks/use-subscription-snapshot.ts` and `hooks/use-subscription-orders.ts` (5 s poll), and mutations `editSubscription` (PATCH), `closeSubscription` and `cancelSubscription` in `use-strategy-mutations.ts`, all invalidating `['subscriptions']`. Verify: no verification needed.

**Task 12.3** Goal: list row and drawer per the mockup. Targets: `strategy-card.tsx` (chips with the entry interval highlighted, broker badge, state, position, pending, last decision, freshness, Start/Stop/Edit/Delete); new `strategies/subscription-drawer.tsx` (readings table, decision with bar time, pending with Cancel pending, position with Close at market, recent decisions, orders and trades timeline, `StrategyChart` with `IntervalSelector` over `sub.intervals`). Close and cancel use `ConfirmDialog` from `start-stop-button.tsx:129-171` with `moneyHint(broker, ...)`. Delete warns when a position or pending exists. Verify: no verification needed.

**Task 12.4** Goal: one form for create and edit, and the backtest form. New `strategies/subscription-form.tsx` replaces `new-subscription-dialog.tsx` (delete it in the same commit): strategy, symbol, interval multi-select (shows `intervalError`), broker PAPER/LIVE, a parameters table from `useStrategyDefaults` with a raw JSON toggle, and `Create (stopped)`. Edit is enabled only when stopped. New `components/params-editor.tsx` is used by both forms. `backtest-form.tsx` uses the multi-select and `params-editor` (it drops the STF placeholder at `:150`). `run-header.tsx`, `run-compare-view.tsx:36-43` and `metrics-diff-table.tsx:48-50` show intervals and parameters. Verify: WEB.

**Task 12.5** Goal: the owner looks at the UI. [USER] The owner runs `just be` and `just fe` locally, opens `/strategies` and `/backtest`, and replies `UI OK` or lists defects. Commit `feat(web): generic multi-timeframe subscription and backtest UI`; PUSH. Verify: run-log contains `UI OK` (`grep -c "UI OK"` prints ≥ `1`).

**Rollback:** `git revert`.

## Phase 13 — Triple Screen

**Entry gate:** standard.

**Task 13.1** Goal: the first consumer (C10). Target: new `src/core/domain/strategy/services/triple_screen_strategy_service.py` with module `_DEFAULTS = {"entry_type": "market", "exit_mode": "sl_tp", "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "force_length": 2, "sl_lookback": 5, "risk_reward": 2.0}` and `default_parameters = _DEFAULTS`. `__init__` raises `ValueError` unless `len(intervals) == 3` and every value is valid. Logic: the top interval's MACD-histogram slope gives the tide; on the middle interval, a 2-bar EMA of Force Index against the tide gives the setup; the entry is on the entry interval. `market` gives LONG/SHORT at the close; `stop` gives a stop at the previous entry-bar high (long) or low (short), placed again every bar while the setup holds. SL is the extreme of the last `sl_lookback` entry bars. `sl_tp` sets TP = `risk_reward × risk`; `strategy` sets no TP and sends EXIT on a tide flip. When the setup is gone and a pending order exists, it sends EXIT. It sets `self.snapshot` every bar and tracks `_open_direction` in `on_order_filled`. Register `"triple_screen"` in `services/__init__.py`. Verify: no verification needed.

**Task 13.2** Goal: tests. New `tests/core_test/unit/domain/strategy/test_triple_screen.py`: rejects 2 intervals; rejects an unknown `entry_type`; tide up + setup + market gives LONG with SL < close < TP; the stop variant sets `entry_type="stop"` and `entry_price` = previous high; strategy exit sends EXIT on a tide flip; the snapshot has 3 intervals; the first bar of a top bucket uses the previous bucket (a no-look-ahead check on indicator values). Add to `tests/scripts/rubric/test_static_audit.py`: `audit_strategy("triple_screen")["degrees_of_freedom"] == 8`. Verify: `uv run python -m pytest tests/core_test/unit/domain/strategy/test_triple_screen.py tests/scripts/rubric -q 2>&1 | tail -1` contains `passed` and no `failed`; then PY, LINT, METRICS.

**Task 13.3** Commit `feat(strategy): add the triple screen strategy`; PUSH.

**Rollback:** `git revert` (the registry becomes empty again).

## Phase 14 — Deploy D-2, backtests, pick the live set

**Entry gate:** standard; `git log --oneline origin/master..develop` is not empty; MONGO shows exactly 4 subscriptions, all `stopped/stopped`.

**Task 14.1** Goal: prepare prod data. [ASK] gist: "Before deploying, add `intervals`, `intervals_key` and `parameters` to the 2 stopped STF subscriptions (additive, `interval` kept), and drop the indexes `ix_subscriptions_dedup_triple` and `ix_backtests_strategy_symbol_interval_started`. Recommended: yes; without this the new trader cannot read those documents and two Triple Screen subscriptions on one symbol would collide on a null key." Script: `db.subscriptions.update_many({"intervals": {"$exists": False}}, [{"$set": {"intervals": ["$interval"], "intervals_key": "$interval", "parameters": {}}}])`; `db.backtest_runs.update_many({"intervals": {"$exists": False}}, [{"$set": {"intervals": ["$interval"]}}])`; drop both indexes when present; print the counts and `index_information()` names. Verify: the output contains `subscriptions_modified=4` and has no `ix_subscriptions_dedup_triple`.

**Task 14.2** Goal: deploy D-2 by the recipe. Post-deploy: MONGO shows `ix_subscriptions_dedup_intervals` present; the trader log since the deploy (`dc logs --since 15m trader | sed 's/\x1b\[[0-9;]*m//g'`) has 0 `reconcile.failed` and 4 `reconcile.unknown_template`. Verify: two `grep -c` counts print `0` and `4`.

**Task 14.3** Goal: backtests (C10). Steps: for XAUUSD:EXNESS over `2025-11-03..2026-10-30` (stored 1m starts 2025-10-21), run 3 interval sets `["15m","1h","4h"]`, `["1h","4h","1d"]` and `["5m","1h","4h"]` × 2 variants (`A = {"entry_type": "market", "exit_mode": "sl_tp"}`, `B = {"entry_type": "stop", "exit_mode": "strategy"}`) through `POST /api/v1/backtest/run`, with the admin token passed via `curl -H @-` inside the api container, one run at a time, logging `free -m` after each. Record `run_id, set, variant, trades, net_pnl, profit_factor, max_dd, sharpe` from `GET /backtest/{run_id}/stats` in run-log, plus the 3 compare URLs (Q8). Verify: `grep -c "^| bt-" .../run-log.md` prints `6`, and every row's status is `completed`.

**Task 14.4** Goal: the owner picks. [ASK] with the table. "Recommended: the set with the highest profit factor among runs with ≥ 30 trades, variant B for the paper run, because only B exercises the pending stop and the strategy exit." Log `live_set=<set> variant=<A|B>`. Verify: `grep -c "^live_set=" .../run-log.md` prints `1`.

**Rollback:** redeploy the previous image tag (`IMAGE_TAG=sha-<prev> bash deploy/vps/10-deploy.sh`) only after deleting every subscription with `intervals_key` not equal to `$interval` and recreating the old index, because the old code rebuilds `ix_subscriptions_dedup_triple` at startup.

## Phase 15 — Paper run

**Entry gate:** standard; `live_set=` is logged.

**Task 15.1** Goal: one paper subscription. Steps: create it through the API (`broker: paper`, `live_set`, the variant parameters), then start it. Verify: MONGO prints `triple_screen <symbol> <intervals_key> running running paper` (1 line).

**Task 15.2** Goal: observe. Each check is MONGO or an API read, logged with a UTC time. (1) The snapshot ring has ≥ 2 entries with different `bar_start`. (2) ≥ 1 pending stop placed, then filled (an order `filled` whose fill time is later than the snapshot showing `pending`). (3) ≥ 1 EXIT by the strategy (a closed trade whose exit order is not an SL/TP fill). (4) One manual close: when a position is open after (3), `POST /subscriptions/{id}/close`; within 10 s the position is closed and `requested_action` is null. (5) One manual cancel: when a pending order exists, `POST .../cancel`; the snapshot `pending` becomes null. (6) [USER] the owner opens the drawer and replies `DRAWER OK`. While any of these is missing, end with `NOT_YET: waiting for <item>` and `Resume ... after <now+12h>`. Verify: run-log has 6 lines `obs-1` ... `obs-6`, each marked `PASS` (`grep -c "^obs-[1-6] PASS"` prints `6`).

**Rollback:** stop the subscription (`POST /subscriptions/{id}/stop`).

## Phase 16 — 1d comparison, prod STF delete, close-out

**Entry gate:** standard; `now ≥ d1_deploy_utc + 7 days`, else `NOT_YET`.

**Task 16.1** Goal: the one-week 1d check (advice item 6). MONGO: for each Exness symbol and each UTC day since `d1_deploy_utc`, compare the stored 1d bar (`source`) with the aggregate of that day's 1m bars on OHLC and print `symbol day equal|diff source`. Success: every row is `equal cascade`. A `diff` row means stop and [ASK] (handoff brief). Verify: `grep -c " diff " .../run-log.md` prints `0`.

**Task 16.2** Goal: list what will be deleted (C12). MONGO prints: STF subscription ids (`strategy_code ∈ {engulfing, engulfing_pullback30_touch}`); counts and ids of `positions`/`orders` where `subscription_id ∈ S`; `trades` where `run_id ∈ S`; `backtest_runs`/`backtest_orders`/`backtest_trades` where `strategy_code ∈ STF`; and, separately, orphans (`positions`/`orders`/`trades` whose subscription id is in no subscription). It also prints the open positions, which must be the 2 BTCUSDT:BINANCE ones. Write the list to `reports/stf-delete-list.md`. Verify: the file exists and its subscription count is 2.

**Task 16.3** Goal: delete. [ASK] with the list. "This cannot be undone; no backup (owner decision). Recommended: yes after reading the list. Orphans are not deleted unless you say so." Run `delete_many` with exactly the listed filters. Never call `TrackedSymbolService.remove` or the symbol delete route. Verify: MONGO re-counts every filter and prints 7 zeros; `db.tracked_symbols.count_documents({})` is unchanged; the new Triple Screen subscription still reads `running`.

**Task 16.4** Goal: docs and close. `git grep -n -i -E "engulfing_strategy|single-timeframe|interval\)" -- docs README.md CLAUDE.md` shows only market-data examples (log them); every path in a doc touched in this plan exists. Set the plan status with the `ak plan` CLI (`ak plan --help` first). Commit `docs(plans): close the multi-timeframe foundation plan`. Verify: `git status --porcelain -- docs src` prints nothing.

**Rollback:** none for 16.3 (owner decision). 16.1 and 16.4 are read-only or docs.

---

## 5. Acceptance criteria

| # | Criterion | Check (phase) |
|---|---|---|
| A1 | The spike go/no-go table has 12 rows and spike code never reached `develop` | 02 Verify; `git branch --list spike/mtf` is empty |
| A2 | No STF code and the registry lists only `triple_screen` | 05, 13 git grep |
| A3 | Subscriptions carry `intervals`, `intervals_key` and `parameters`; the unique index works for overlapping sets | 06.2 test; 14.2 index check |
| A4 | The first entry bar of a new bucket sees the previous bucket close in live, warm-up and backtest | 07.3, 08.3 tests |
| A5 | One `find` per rollover; never one per entry bar | `test_context_is_read_once_per_rollover` |
| A6 | Exness 1d is `source=cascade` before 00:01Z, and one week equals the 1m aggregate | 07 gate; 16.1 |
| A7 | Stop entry, EXIT and manual close/cancel work in paper; Exness paths exist and raise `LIVE_TRADING_DISABLED` | 09, 10, 11 tests; 15 obs-2..5 |
| A8 | The snapshot updates each entry bar and the UI is generic | 15 obs-1, obs-6; `git grep -n -i "triple" -- web/src` prints 0 |
| A9 | 6 backtests with intervals and parameters shown; 3 compare views | 14.3 |
| A10 | Prod has 0 STF subscriptions, positions, orders, trades and backtests; tracked symbols unchanged | 16.3 |
| A11 | PY, LINT, METRICS and WEB are green on the last commit; CI includes the web job | every phase; 04.2 |
| A12 | `docs/system-architecture.md` has no SL/TP-only statement; the swing-pivot doc is gone | 09.4, 05.3 |

## 6. Risks

| Risk | L × I | Mitigation |
|---|---|---|
| A late cascade (worker handover, Exness REST slow) lets live cache a partial HTF bar for one window | M × H | The lag comes from the measurement (G4). The previous-bucket presence rule covers missing bars, but a partial bar that exists is not detected. This is a documented limit. Re-measure in Phase 16 with the Task 1.2 script. |
| The new trader meets old-shape documents | H × H if missed | Task 14.1 runs the additive `$set` before the push, and 14.2 checks for 0 `reconcile.failed`. |
| The old unique index blocks a second subscription on one symbol | H × M | It is dropped in 14.1 and checked in 14.2. |
| Starting the sandbox tracker changes backtest results (entries against an open position are now rejected) | M × M | This is intended (live parity). STF backtests are deleted. Test 08.3 covers it. |
| An Exness pending fill maps wrongly | M × H | The code is behind `_ORDER_OPS` and the live flag stays off (C13). Fake-client tests cover it; an absent G11 path stops Phase 10. |
| The paper run takes days to show a stop fill and an EXIT | H × L | The `NOT_YET` resume runs every 12 h. Variant B is recommended. |
| A wrong delete filter cannot be undone (no backup) | L × H | The list file and an explicit yes come first; filters are built from ids; orphans are kept apart; the symbol delete is never used. |
| The metric ceiling or a long function grows | M × L | The ceiling is raised in its own commit and logged. |

## 7. Deliberate differences from the advice

- **The 1d cascade ships first (Phase 03), not inside the context phase.** It is independent, and its acceptance needs a week. Shipping it early gives Triple Screen a final 1d bar in live.
- **A context lag (D-A).** The advice filter `end ≤ entry end` is stricter than look-ahead requires but too loose for live data: the cascade is final only seconds after the bucket end. This is an owner-visible refinement of C4's "closed before this instant" (see Unresolved 1).
- **Paper pending stop held by the engine (D-D), not by the paper broker.** It reuses the tested market path in live and backtest alike. A broker-side pending order would need a fill channel that synchronous paper fills do not have (`strategy_app_service.py:676-677`).
- **Compare view stays capped at 3 (Q8)**; the "four in one view" metric becomes three views plus a table.
- **The "trader log shows one context read per rollover" metric becomes a test.** Prod runs at INFO, and a per-rollover line is DEBUG by the log-level rule.
- **D-2 does an additive prod `$set` and a manual index drop** instead of compatibility code or a startup drop.
- **One spike, two phases, in a worktree.** C11 says the spike runs "on develop". Here it starts from `develop` but lives on a local branch that is deleted, so no rough code is committed.

## 8. Unresolved questions for the owner

1. Is the 45 s context lag (D-A) acceptable as part of "closed before this instant"? It delays when a closed HTF bar becomes visible by under one entry bar, so live and backtest stay equal.
2. Should the paper run use variant B (stop entry and strategy exit) even if the backtests favour A? Otherwise the pending fill and the strategy exit cannot be observed in one subscription.
3. Should the orphan positions, orders and trades found in Task 16.2 (if any) be deleted with the STF data?
4. Can the parameter form show free inputs typed by their default value, instead of the mockup's enum choices? Choices would need a per-strategy schema, which no second caller needs today.
5. Can the 21 old backtest runs get the additive `intervals` field in Task 14.1? They are deleted in Phase 16 anyway.
