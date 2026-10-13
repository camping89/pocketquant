---
phase: 8
title: "Validation: spread, backtests, paper week"
status: pending
priority: P1
effort: 7d + weekend
dependencies: [7]
---

# Phase 08: Validation (spread, backtests, paper week across a weekend)

<!-- Updated: 2026-10-13 develop reshape - develop paths (PaperBrokerAdapter, engine/backtest), no OpenAPI snapshot, develop gate and push -->
## Develop status
- Base branch: `develop` (`develop-sync` tracking `origin/develop`); ship with `git push origin develop-sync:develop`. There is no feature branch, no merge step and no `master` step.
- Develop has no `tests/baseline` (no OpenAPI snapshot and no venue command). The OpenAPI check in T8.2 compares the request model schema, and the gate is develop's gate.
- Remote pattern used below: `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app <command>"` (`KEY` and `HOST` as in Phase 06 T6.19). The app listens on `41921` inside the container (`deploy/compose.prod.yml:38`), and every route is under `/api/v1` (`Settings.api_prefix`, `core/config.py:51`).

## Context Links
- Advice §2.8 and §3 (bid-only backtests flatter shorts).
- `PaperBrokerAdapter` (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:88`): `__init__` :109 (last parameter `contract_spec` :118); `_handle_market` :206 (`base_price` :212, market fill `_apply_slippage(base_price, order.side)` :227); limit fills :296 and :730; `_apply_slippage` :483; `_check_sl_tp` :773-789 (LONG branch :779-781, SHORT branch :784-786 compares `bar_high >= sl` and `bar_low <= tp`); synthetic exit fill `_apply_slippage(trigger_price, exit_side)` :797; the exit publishes `OrderFilledEvent` at :837. Strategies enter with MARKET orders by default (`entry_type="market"`, `src/pocketquant/core/domain/strategy/value_objects.py:51`). Existing paper tests: `tests/core_test/infra/brokers/test_paper_broker_sl_tp_fill.py`, `test_paper_broker_contract_spec.py`, `paper_broker_commission_test.py`, `paper_broker_futures_accounting_test.py`.
- Backtest plumbing:
  - `src/pocketquant/engine/backtest/backtest_command_service.py` (`RunBacktestCommand` :23, `slippage_bps` :35, `commission_bps` :36; `BacktestCommandService.run` config dict :61-72)
  - `src/pocketquant/engine/backtest/backtest_dispatch.py` (`_config_from_dict` :47; `run_single` :63, `contract_spec` lookup :77, `sandbox.create_broker(...)` :100-105)
  - `src/pocketquant/core/domain/backtest/config.py` (`BacktestConfig` :11)
  - `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` (`create_broker` :112, `PaperBrokerAdapter(` :121)
- Run API (`app/routes/backtest.py`): `POST /api/v1/backtest/run` returns 202 with the run id (:52); `GET /api/v1/backtest/{run_id}` returns `status` `started`, `finished` or `failed` (:74); `GET /api/v1/backtest/{run_id}/trades` returns a page `{items, next_cursor, has_more, total, total_pnl, total_commission}` (:120; `PagedTradesResponse`, `engine/backtest/backtest_stats_service.py:94`).
- Subscriptions (`app/routes/strategy.py`): `POST /api/v1/strategies/{strategy_code}/subscriptions` with `{"symbol","interval"}` (:56, 201); `GET /api/v1/subscriptions/` (:85; items carry `id`, `symbol`, `actual_state`); `POST /api/v1/subscriptions/{sub_id}/start` (:93) and `/stop` (:102). Live subscriptions run on the paper broker: `StrategyReconcileAppService` builds `StrategyConfig` without `broker` (`engine/live/strategy_reconcile_app_service.py:167`), so `config.broker` is `"paper"` with the symbol's `contract_spec`, built from `default_broker_config` (`app/di/services.py:158-166`), which has no `spread`.
- Integrity API: `POST /api/v1/market-data/integrity/check` with `{"symbol","interval","days_back"}` (`days_back` 1–90, `app/routes/market_data.py:103-120`) returns `missing_count` and `misaligned_count`, checked against `TradingCalendarFactory.for_symbol` (`engine/market_data/app_services/integrity_jobs.py:87`, :107).
- Job stats: `GET /api/v1/system/jobs/sync_1m/stats?window=24h` returns `{by_status, p50_ms, p95_ms}` (`app/routes/system_jobs.py:50`; `job_history_repository.py:304`).
- Logs: `deploy/compose.prod.yml:60-64` caps app logs at 3 × 10 MB, and a deploy recreates the container, so a week-long log count proves nothing by itself.
- Spike journal `docs/journals/2026-10-13-exness-api-spike.md` median spreads (Ticks table): XAUUSD `0.168`, EURUSD `0.00006`, BTCUSD `4.48`. Deep backfill: `scripts/backfill/provider_bars.py` (Phase 06 T6.17). Calendars: XAUUSD and EURUSD use the Exness session calendars, BTCUSD uses `CRYPTO_24_7` (Phase 06 T6.14).

<!-- Updated: Validation Session 1 - paper-only validation; no live order, no U3 -->
## Goal
Make D3 true and validate Exness end to end without live money: CFD backtests model the spread (ask = bid + spread), and both strategies run on the paper broker on `:EXNESS` symbols for one market week that includes a weekend close and reopen. No live order is placed in this phase; the Exness broker stays off.

## Files to Create or Modify
- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`, `src/pocketquant/engine/backtest/backtest_command_service.py`, `src/pocketquant/engine/backtest/backtest_dispatch.py`, `src/pocketquant/core/domain/backtest/config.py`, `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py`.
- Create: `tests/core_test/infra/brokers/test_paper_broker_spread.py`.
- Create reports: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtest-results.md` and `.../reports/exness-paper-week.md`.

## Tasks

<!-- Updated: 2026-10-13 develop reshape - PaperBrokerAdapter lines on develop; no feature branch -->
### T8.1 Base and the `PaperBrokerAdapter` `spread` parameter
- **Goal:** Bid candles plus a constant spread give an ask side: BUY entries and SHORT exits fill at ask, and SHORT SL/TP trigger on the ask high/low. The default `0.0` keeps every result byte-identical.
- **Target files and symbols:** `PaperBrokerAdapter.__init__(..., spread: float = 0.0)`, the market fill in `_handle_market` (:227), `_check_sl_tp` (:773-789)
- **Steps:**
  1. `git switch develop-sync && git pull --ff-only && git rev-parse HEAD > .cache/phase08-base`
  2. Add `spread: float = 0.0` after `contract_spec` (:118) and store `self._spread = spread`.
  3. Market fill (:227): `fill_price = self._apply_slippage(base_price + (self._spread if order.side == OrderSide.BUY else 0.0), order.side)`. A market BUY that covers a short is a SHORT exit, so it also fills at ask.
  4. `_check_sl_tp`, SHORT branch only (:784-786): `if sl is not None and bar_high + self._spread >= sl` and `if tp is not None and bar_low + self._spread <= tp`. The LONG branch is unchanged (bid side).
  5. The synthetic exit fill (:797) stays `self._apply_slippage(trigger_price, exit_side)`: a SHORT trigger level is already an ask price and a LONG trigger is a bid price. Limit fills (:296, :730) are unchanged.
  6. Write `tests/core_test/infra/brokers/test_paper_broker_spread.py` with `slippage_percent=0`, `fill_delay_ms=0` and `spread=0.4`, following the setup of `test_paper_broker_sl_tp_fill.py`:
     - a MARKET BUY at `price=100` fills at `100.4`; a MARKET SELL fills at `100.0`;
     - a SHORT with `sl=101`: a bar with `high=100.7` triggers (100.7 + 0.4 ≥ 101) and the exit fills at `101.0`; with `high=100.5` it does not trigger;
     - a SHORT with `tp=99`: a bar with `low=98.7` does not trigger (98.7 + 0.4 > 99); with `low=98.5` it triggers and fills at `99.0`;
     - a LONG with `sl=95` and a bar with `low=94.9` exits at `95.0`;
     - with `spread=0` the same scenarios give the fills and triggers of today's code.
- **Success criteria:** Existing paper tests are untouched and still pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/brokers -q` exits 0. `git diff --name-only $(cat .cache/phase08-base) -- tests/core_test/infra/brokers | grep -v test_paper_broker_spread.py` prints nothing.

<!-- Updated: 2026-10-13 develop reshape - no OpenAPI snapshot on develop; the request model schema is compared instead -->
### T8.2 Backtest plumbing for `spread`
- **Goal:** The backtest API accepts a constant spread in price units.
- **Target files and symbols:**
  - `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant spread in price units; ask = bid + spread, so BUY entries and SHORT exits fill at ask")` (after `commission_bps` :36)
  - `BacktestCommandService.run` config key `"spread": cmd.spread`
  - `BacktestConfig.spread: float = 0.0`
  - `_config_from_dict` with `spread=payload.get("spread", 0.0)`
  - `BacktestSandboxAppService.create_broker(..., spread: float = 0.0)`, which passes it to `PaperBrokerAdapter(` (:121)
  - `run_single`, which passes `spread=config.spread` to `sandbox.create_broker` (:100-105)
- **Steps:**
  1. Before editing, save the request schema: `uv run python -c "import json;from pocketquant.engine.backtest.backtest_command_service import RunBacktestCommand as R;json.dump(R.model_json_schema(),open('.cache/run-backtest-schema-before.json','w'))"`.
  2. Apply each of the edits above.
  3. Add one case to `test_paper_broker_spread.py`: `_config_from_dict({... "spread": 0.4}, LINEAR_SPEC).spread == 0.4`, and a payload without `spread` gives `0.0`.
- **Success criteria:** The only API change is the new optional `RunBacktestCommand.spread`; no route file changes.
- **Verify:** `uv run python -c "import json;from pocketquant.engine.backtest.backtest_command_service import RunBacktestCommand as R;old=json.load(open('.cache/run-backtest-schema-before.json'));new=R.model_json_schema();del new['properties']['spread'];print(old==new)"` prints `True`. `git diff --name-only $(cat .cache/phase08-base) -- src/pocketquant/app` prints nothing.

<!-- Updated: 2026-10-13 develop reshape - develop gate; push develop-sync to develop -->
### T8.3 Gate and ship
- **Goal:** `spread` is in prod.
- **Target files and symbols:** git
- **Steps:**
  1. `uv run lint-imports`
  2. `uv run ruff check src $(git diff --name-only $(cat .cache/phase08-base) -- tests)` and `uv run pyright src $(git diff --name-only $(cat .cache/phase08-base) -- tests)`
  3. `just test 2>&1 | tail -n 15`
  4. `uv run python scripts/code_metrics.py --ratchet`
  5. `git add -A src tests plans/261009-0858-exness-venue-lean-sync-refactor && git commit -m "feat(backtest): model a constant bid/ask spread in paper broker fills"`
  6. `git push origin develop-sync:develop`. Wait for the CI run whose `headSha` equals `git rev-parse HEAD`, then `gh run watch <databaseId> --exit-status`.
- **Success criteria:** Green and deployed.
- **Verify:** Step 1 prints `Contracts: 8 kept, 0 broken.` Step 2 reports 0 errors in `src/` and in every touched file. Step 3 shows no new failure (the only failures are the 4 pre-existing Windows `time.tzset` tests). Step 4 exits 0. `gh run watch` exits 0, and `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.

<!-- Updated: 2026-10-13 develop reshape - provider_bars.py; BTCUSD minimums from CRYPTO_24_7 -->
### T8.4 Backfill Exness history in prod
- **Goal:** Enough Exness bars for backtests: M1 for 90 days and H1 for 730 days, on 3 instruments.
- **Target files and symbols:** `scripts/backfill/provider_bars.py` in the app image (`/app/scripts`, `deploy/Dockerfile:44`)
- **Steps:**
  1. Run for each `S` in XAUUSD, EURUSD and BTCUSD, one instrument per ssh call to stay under the 10-minute command limit:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     python scripts/backfill/provider_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 90 --rate-fraction 0.5
     python scripts/backfill/provider_bars.py --symbol XAUUSD:EXNESS --interval 1h --days 730 --rate-fraction 0.5
     EOF
     ```
     Substitute `S` for XAUUSD on the other instruments. The script refuses to run (exit 3) if `EXNESS_LIVE_TRADING` is true. M1 history reaches back one year and H1 has full history (spike journal), so both windows are inside the available depth.
  2. BTCUSD:EXNESS uses `CRYPTO_24_7`, so every slot is open; its minimums are 80% of all slots: 1m `int(0.8 * 90 * 1440) = 103680`, 1h `int(0.8 * 730 * 24) = 14016`.
- **Success criteria:** The bar counts are plausible for each calendar.
- **Verify:** Each output line exits 0, and its `total_bars` meets these minimums:
  - 1m: EURUSD and XAUUSD ≥ 60000, BTCUSD ≥ 103680
  - 1h: EURUSD and XAUUSD ≥ 8000, BTCUSD ≥ 14016

### T8.5 Backtests of both strategies on Exness bars
- **Goal:** D3 holds.
- **Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`, `GET /api/v1/backtest/{run_id}/trades?limit=1`
- **Steps:**
  1. For each `S` in XAUUSD, EURUSD and BTCUSD, post two runs with the remote pattern, using `SPREAD_S` = the journal's median spread for S (0.168, 0.00006, 4.48):
     - `{"strategy_id":"hitnrun2","symbol":"S:EXNESS","interval":"1m","start_date":"<now-30d ISO, minute precision>","end_date":"<now ISO>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
     - `{"strategy_id":"engulfing","symbol":"S:EXNESS","interval":"1h","start_date":"<now-365d>","end_date":"<now>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
  2. Record each run id from the 202 response. Poll `GET /api/v1/backtest/{id}` every 60 s (at most 30 times per run) until `status` is not `started`.
  3. Write `exness-backtest-results.md` with one table row per run: strategy, symbol, run id, status, trade count (`total` from `/trades`), total return and max drawdown.
- **Success criteria:** All 6 runs are `finished`, and each strategy has at least one run with trades.
- **Verify:** Each `GET /api/v1/backtest/{id}` contains `"status":"finished"`. For each strategy, at least one `GET .../trades?limit=1` piped to `python -c "import json,sys;print(json.load(sys.stdin)['total']>0)"` prints `True`.

<!-- Updated: 2026-10-13 develop reshape - live paper broker from config.broker default; develop-only deploy trigger; session re-check -->
### T8.6 Start the paper week
- **Goal:** Both strategies run on the paper broker on `:EXNESS` symbols, starting on a Tuesday, Wednesday or Thursday so the 7 days include a weekend close and reopen, with no deploy during the week.
- **Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, `GET /api/v1/subscriptions/`, `reports/user-preconditions.md`, `reports/exness-paper-week.md`
- **Steps:**
  1. Ask the user verbatim: "May I start a 7-day paper observation on XAUUSD:EXNESS (hitnrun2, 1m) and EURUSD:EXNESS (engulfing, 1h), and do you confirm there will be no push to develop or master and no manual workflow run during those 7 days?" Append `paper week: approved, no-deploy until <start + 7 days, ISO>` or `paper week: declined` to `user-preconditions.md`. On `declined`, STOP.
  2. Re-read the instrument sessions and compare them with the Exness calendar constants (Phase 06 T6.14):
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
     import asyncio
     from pocketquant.core.config import get_settings
     from pocketquant.core.infra.exness.exness_client import ExnessClient
     from pocketquant.core.infra.calendars.exness_session_calendar_adapter import _EURUSD_SESSIONS, _XAUUSD_SESSIONS
     async def main():
         c = ExnessClient(get_settings())
         try:
             return [(await c.conditions(n))["trade_sessions"] for n in ("XAUUSD", "EURUSD")]
         finally:
             await c.close()
     print(asyncio.run(main()) == [_XAUUSD_SESSIONS, _EURUSD_SESSIONS])
     EOF
     ```
     It must print `True`. If the week spans the 2026-11-01 US DST change, run it again on the Monday after the change. `False` is a STOP.
  3. Using the remote pattern, create the two subscriptions (no broker field exists; the engine uses the paper broker):
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m"}'
     curl -s -X POST http://localhost:41921/api/v1/strategies/engulfing/subscriptions -H "Content-Type: application/json" -d '{"symbol":"EURUSD:EXNESS","interval":"1h"}'
     ```
     Record the returned `id`s, then `POST /api/v1/subscriptions/<id>/start` for each.
  4. Record the container start: `ssh -i "$KEY" "$HOST" "docker inspect -f '{{.State.StartedAt}}' pocketquant-app"`. Write `week_start_utc: <now ISO>`, `container_started_at: <value>` and both subscription ids at the top of `exness-paper-week.md`.
  5. Do not change how the live paper broker is built. It comes from `default_broker_config` without `spread`, so paper fills carry no spread (ask = bid); the week validates data, calendar and quotes, not P&L. Plumbing `spread` into the live broker is out of scope for this plan.
- **Success criteria:** Both subscriptions run, and the week's baseline is recorded.
- **Verify:** `grep -c "paper week: approved" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `1`. After 30 s, `curl -s http://localhost:41921/api/v1/subscriptions/` (remote pattern) piped to `python -c "import json,sys;d=json.load(sys.stdin);ids={'<id1>','<id2>'};print(sum(1 for s in d if s['id'] in ids and s['actual_state']=='running'))"` prints `2`.

<!-- Updated: Validation Session 1 - daily checks with proven log coverage instead of one week-long log count -->
### T8.7 Daily observation with proven log coverage
- **Goal:** Each day's counters are trustworthy: the container was not restarted and the logs reach back the full window.
- **Target files and symbols:** container logs, `reports/exness-paper-week.md`
- **Steps:**
  1. Once per day for 7 days (at least one run on the Monday after the weekend reopen), run:
     ```bash
     ssh -i "$KEY" "$HOST" 'S=$(docker inspect -f "{{.State.StartedAt}}" pocketquant-app); F=$(docker logs --timestamps --since 25h pocketquant-app 2>&1 | head -1 | cut -d" " -f1); CB=$(docker logs --since 25h pocketquant-app 2>&1 | grep -c exness_ws.circuit_breaker_open); RC=$(docker logs --since 25h pocketquant-app 2>&1 | grep -c exness_ws.reconnecting); RL=$(docker logs --since 25h pocketquant-app 2>&1 | grep -c exness.rate_limited_retry); echo "$S $F $CB $RC $RL"'
     ```
  2. Append one row `| <date UTC> | <S> | <F> | <CB> | <RC> | <RL> |` to the daily table in `exness-paper-week.md`.
  3. If `S` differs from `container_started_at`, or the first log line `F` is later than 24 hours ago, the day has no coverage: STOP and report to the user (a deploy or restart happened, or logs rotated away).
- **Success criteria:** Seven rows, each with unchanged `S` and full 24-hour coverage.
- **Verify:** For each run, `uv run python -c "import sys,datetime as d;f=d.datetime.fromisoformat(sys.argv[2][:19]).replace(tzinfo=d.UTC);print(sys.argv[1]==sys.argv[3] and f<=d.datetime.now(d.UTC)-d.timedelta(hours=24))" <S> <F> <container_started_at>` prints `True`. `RC` and `RL` (429 data-call retries) have no pass condition; record them only.

<!-- Updated: 2026-10-13 develop reshape - sync_1m duration check from job stats -->
### T8.8 Close the paper week
- **Goal:** Calendar and staleness behaved correctly across the weekend: zero circuit-breaker trips, zero integrity issues for the FX symbols, and Exness did not slow the shared 1m sync job.
- **Target files and symbols:** `POST /api/v1/market-data/integrity/check`, `GET /api/v1/system/jobs/sync_1m/stats`, `reports/exness-paper-week.md`
- **Steps:**
  1. After the seventh daily row, run with the remote pattern for each `(S, I)` in `(XAUUSD:EXNESS, 1m)`, `(XAUUSD:EXNESS, 1h)`, `(EURUSD:EXNESS, 1m)` and `(EURUSD:EXNESS, 1h)`:
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/market-data/integrity/check -H "Content-Type: application/json" -d '{"symbol":"S","interval":"I","days_back":7}'
     ```
  2. `curl -s "http://localhost:41921/api/v1/system/jobs/sync_1m/stats?window=7d"` (remote pattern).
  3. Re-run the T8.6 subscriptions check.
  4. Write the four integrity results, the `sync_1m` `p95_ms`, the sums of the daily `CB`, `RC` and `RL` values, and the `exness-backtest-results.md` summary to `exness-paper-week.md`.
  5. Ask the user whether to keep the two paper subscriptions running or stop them. Run `POST /api/v1/subscriptions/<id>/stop` if they say stop.
- **Success criteria:** Zero circuit-breaker trips, zero FX integrity issues, a `sync_1m` p95 under one minute, and both strategies still running.
- **Verify:** Each step 1 response piped to `python -c "import json,sys;d=json.load(sys.stdin);print(d['missing_count']==0 and d['misaligned_count']==0)"` prints `True`. Step 2 piped to `python -c "import json,sys;print(json.load(sys.stdin)['p95_ms']<60000)"` prints `True`. The sum of the daily `CB` column is `0`. Step 3 prints `2`.

## Verification
T8.1 and T8.2 (spread and the request schema diff), T8.4 and T8.5 (D3), T8.6–T8.8 (paper week across a weekend).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any step that would place a live order, set `config.broker = "exness"`, or set `EXNESS_LIVE_TRADING=true`.
- A deploy or restart during the observation week (T8.7 step 3).
- The instrument sessions differ from the calendar constants (T8.6 step 2).
- The paper week is declined, or a test failure stays unexplained.

## Risks
- **Swap costs are not modelled** (known, accepted in the advice). They are noted in the results report and not built.
- **Paper week fills ignore the spread** (known, accepted): the live paper broker is built from `default_broker_config` without `spread`; D3 covers spread through backtests.
- **No paper trade happens during the week** (M/L). That is not a failure; D3 covers trading behaviour through backtests, and the week validates data, calendar and quotes.
- **Log rotation hides events** (M/M). Mitigation: daily windows with a coverage proof, and integrity is checked from stored bars, not from logs.
- **Exness answers 429 below the published rate** (M/M). Data calls retry up to 3 times and log `exness.rate_limited_retry`; the deep backfill runs at half the request rate. The daily `RL` column shows how often it happens.
- **Exness session times shift at the 2026-11-01 US DST change** (M/M, unverified). T8.6 step 2 re-reads the sessions; a difference stops the week.

## Security
No credentials are printed. Paper subscriptions never touch the Exness order endpoints, and the client refuses them anyway while live trading is off.

## Rollback
Stop the paper subscriptions with `POST /api/v1/subscriptions/<id>/stop`. Then `git revert` the spread commit and push it with `git push origin develop-sync:develop`. `spread` defaults to 0, so reverting is safe; no data shape changes.

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
