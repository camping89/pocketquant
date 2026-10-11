---
phase: 8
title: "Validation: spread, backtests, paper week"
status: pending
priority: P1
effort: 7d + weekend
dependencies: [7]
---

# Phase 08: Validation (spread, backtests, paper week across a weekend)

## Context Links
- Advice §2.8 and §3 (bid-only backtests flatter shorts).
- PaperBroker: constructor `src/pocketquant/core/infra/brokers/paper/paper_broker.py:93`; `_apply_slippage` :436 with call sites :199 (market fill), :261 and :617 (limit fills) and :678 (synthetic SL/TP exit fill); `_check_sl_tp` :654-669 (SHORT branch compares `bar_high >= sl` and `bar_low <= tp`); the exit publishes `OrderFilledEvent` at :715. Strategies enter with MARKET orders by default (`entry_type="market"`, `src/pocketquant/core/domain/strategy/value_objects.py:51`).
- Backtest plumbing:
  - `src/pocketquant/backtest/backtest_command_service.py:22` (`RunBacktestCommand`, `run` config dict)
  - `src/pocketquant/backtest/workers/backtest_dispatch.py` (`_config_from_dict`, `run_single` → `sandbox.create_broker`)
  - `src/pocketquant/backtest/models/backtest_config.py:9`
  - `src/pocketquant/backtest/engine/backtest_engine_sandbox.py:110` (`create_broker`)
- Run API: `POST /api/v1/backtest/run` returns 202 `{"request_id"}`. `GET /api/v1/backtest/{run_id}` returns `status` started, finished or failed. `GET /api/v1/backtest/{run_id}/trades`.
- Subscriptions: `POST /api/v1/strategies/{strategy_code}/subscriptions` with `{"symbol","interval"}` (`app/routes/strategy.py:69`; the engine builds `StrategyConfig(broker="paper")`), `POST /api/v1/subscriptions/{sub_id}/start|stop`, `GET /api/v1/subscriptions/` (items carry `id` and `actual_state`).
- Integrity API: `POST /api/v1/market-data/integrity/check` with `{"symbol","interval","days_back"}` returns `missing_count` and `misaligned_count`, calendar-aware since Phase 03.
- Logs: `deploy/compose.prod.yml:56-60` caps app logs at 3 × 10 MB, and a deploy recreates the container, so a week-long log count proves nothing by itself.
- Spike journal median spreads: `docs/journals/*-exness-api-spike.md`. Deep backfill: `scripts/backfill/policy_bars.py` (Phase 06 T6.16).

<!-- Updated: Validation Session 1 - paper-only validation; no live order, no U3 -->
## Goal
Make D3 true and validate Exness end to end without live money: CFD backtests model the spread (ask = bid + spread), and both strategies run on PaperBroker on `:EXNESS` symbols for one market week that includes a weekend close and reopen. No live order is placed in this phase; the Exness broker stays off.

## Files to Create or Modify
- Modify: `paper_broker.py`, `backtest_command_service.py`, `backtest_dispatch.py`, `backtest_config.py`, `backtest_engine_sandbox.py` and `tests/baseline/openapi_app_snapshot.json`.
- Create: `tests/backtest_test/engine/test_paper_broker_spread.py`.
- Create reports: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtest-results.md` and `.../reports/exness-paper-week.md`.

## Tasks

<!-- Updated: Validation Session 1 - ask = bid + spread; BUY entries and SHORT exits at ask; SHORT triggers on ask; spread=0 byte-identical -->
### T8.1 Branch and the PaperBroker `spread` parameter
- **Goal:** Bid candles plus a constant spread give an ask side: BUY entries and SHORT exits fill at ask, and SHORT SL/TP trigger on the ask high/low. The default `0.0` keeps every result byte-identical.
- **Target files and symbols:** `PaperBroker.__init__(..., spread: float = 0.0)`, the market fill at :199, `_check_sl_tp`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/paper-spread-validation`
  2. Add `spread: float = 0.0` as the last constructor parameter and store `self._spread = spread`.
  3. Market fill (:199): `fill_price = self._apply_slippage(base_price + (self._spread if order.side == OrderSide.BUY else 0.0), order.side)`. A market BUY that covers a short is a SHORT exit, so it also fills at ask.
  4. `_check_sl_tp`, SHORT branch only: `if sl is not None and bar_high + self._spread >= sl` and `if tp is not None and bar_low + self._spread <= tp`. The LONG branch is unchanged (bid side).
  5. The synthetic exit fill (:678) stays `self._apply_slippage(trigger_price, exit_side)`: a SHORT trigger level is already an ask price and a LONG trigger is a bid price. Limit fills (:261, :617) are unchanged.
  6. Write `tests/backtest_test/engine/test_paper_broker_spread.py` with `slippage_percent=0` and `spread=0.4`:
     - a MARKET BUY at `price=100` fills at `100.4`; a MARKET SELL fills at `100.0`;
     - a SHORT with `sl=101`: a bar with `high=100.7` triggers (100.7 + 0.4 ≥ 101) and the exit fills at `101.0`; with `high=100.5` it does not trigger;
     - a SHORT with `tp=99`: a bar with `low=98.7` does not trigger (98.7 + 0.4 > 99); with `low=98.5` it triggers and fills at `99.0`;
     - a LONG with `sl=95` and a bar with `low=94.9` exits at `95.0`;
     - with `spread=0` the same scenarios give the fills and triggers of today's code.
- **Success criteria:** Existing paper tests are untouched and still pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/backtest_test/engine/test_paper_broker_spread.py -q` exits 0 with `passed`. The venue command's `passed` count equals the baseline.

<!-- Updated: Validation Session 1 - description states the ask-side model -->
### T8.2 Backtest plumbing for `spread`
- **Goal:** The API accepts a constant spread in price units.
- **Target files and symbols:**
  - `RunBacktestCommand.spread: float = Field(default=0.0, ge=0, description="Constant spread in price units; ask = bid + spread, so BUY entries and SHORT exits fill at ask")`
  - `BacktestCommandService.run` config key `"spread"`
  - `BacktestConfig.spread: float = 0.0`
  - `_config_from_dict` with `spread=payload.get("spread", 0.0)`
  - `BacktestSandbox.create_broker(..., spread: float = 0.0)`, which passes it to `PaperBroker`
  - `run_single`, which passes `spread=config.spread`
- **Steps:**
  1. Apply each of the edits above.
  2. Regenerate the snapshot with `BASELINE_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/baseline/test_openapi_snapshot.py -q`.
- **Success criteria:** The only OpenAPI change is `RunBacktestCommand.spread`.
- **Verify:** `uv run python -c "import json,subprocess;old=json.loads(subprocess.check_output(['git','show','HEAD:tests/baseline/openapi_app_snapshot.json']));new=json.load(open('tests/baseline/openapi_app_snapshot.json',encoding='utf-8'));del new['components']['schemas']['RunBacktestCommand']['properties']['spread'];print(old==new)"` prints `True`.

<!-- Updated: Validation Session 1 - ratchet in the gate -->
### T8.3 Gate and ship
- **Goal:** `spread` is in prod.
- **Target files and symbols:** git
- **Steps:**
  1. Run the gate (`just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet` and the venue command).
  2. `git add -A src tests plans/261009-0858-exness-venue-lean-sync-refactor`
  3. `git commit -m "feat(backtest): model a constant bid/ask spread in paper broker fills"`
  4. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
- **Success criteria:** Green.
- **Verify:** The gate meets the Phase 04 T4.6 pass conditions and the ratchet exits 0. `gh run watch` exits 0, and the CI log `=== Verdict:` line contains `, 0 failures)`.

<!-- Updated: Validation Session 1 - provider-agnostic backfill at half the rate budget -->
<!-- Updated: Validation Session 3 - BTCUSD minimums derived from the recorded session calendar -->
### T8.4 Backfill Exness history in prod
- **Goal:** Enough Exness bars for backtests: M1 for 90 days and H1 for 730 days, on 3 instruments.
- **Target files and symbols:** `scripts/backfill/policy_bars.py` on the VPS
- **Steps:**
  1. Run for each `S` in XAUUSD, EURUSD and BTCUSD, one instrument per ssh call to stay under the 10-minute command limit:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     python scripts/backfill/policy_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 90 --rate-fraction 0.5
     python scripts/backfill/policy_bars.py --symbol XAUUSD:EXNESS --interval 1h --days 730 --rate-fraction 0.5
     EOF
     ```
     Substitute `S` for XAUUSD on the other instruments. The script refuses to run (exit 3) if `EXNESS_LIVE_TRADING` is true.
- **Success criteria:** The bar counts are plausible for each calendar.
  2. Compute the BTCUSD minimums from its recorded calendar (80% of the open 1m slots in the last 90 days and of the open 1h slots in the last 730 days), with the same remote pattern:
     ```bash
     python -c "from datetime import datetime,timedelta,timezone;from pocketquant.engine.market_data.sync_policy import EXNESS_CALENDARS as C;c=C['BTCUSD'];n=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0);print(int(0.8*sum(c.is_open(n-timedelta(minutes=i)) for i in range(90*1440))),int(0.8*sum(c.is_open(n-timedelta(hours=i)) for i in range(730*24))))"
     ```
     It prints two integers, `<btc_min_1m> <btc_min_1h>`.
- **Verify:** On each output line, `total_bars` meets these minimums:
  - 1m: EURUSD and XAUUSD ≥ 60000, BTCUSD ≥ `<btc_min_1m>` from step 2
  - 1h: EURUSD and XAUUSD ≥ 8000, BTCUSD ≥ `<btc_min_1h>` from step 2

### T8.5 Backtests of both strategies on Exness bars
- **Goal:** D3 holds.
- **Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`, `GET /api/v1/backtest/{run_id}/trades?limit=1`
- **Steps:**
  1. For each `S` in XAUUSD, EURUSD and BTCUSD, post two runs, using `SPREAD_S` = the journal's median spread for S:
     - `{"strategy_id":"hitnrun2","symbol":"S:EXNESS","interval":"1m","start_date":"<now-30d ISO, minute precision>","end_date":"<now ISO>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
     - `{"strategy_id":"engulfing","symbol":"S:EXNESS","interval":"1h","start_date":"<now-365d>","end_date":"<now>","initial_capital":10000,"slippage_bps":0,"commission_bps":0,"spread":SPREAD_S}`
  2. Record each `request_id`. Poll `GET /api/v1/backtest/{id}` every 60 s (at most 30 times per run) until `status` is not `started`.
  3. Write `exness-backtest-results.md` with one table row per run: strategy, symbol, run_id, status, trade count (from `/trades`), total return and max drawdown.
- **Success criteria:** All 6 runs are `finished`, and each strategy has at least one run with trades.
- **Verify:** Each `GET /api/v1/backtest/{id}` contains `"status":"finished"`. For each strategy, at least one `GET .../trades?limit=1` returns a non-empty JSON list (`python -c "import json,sys;print(len(json.load(sys.stdin))>0)"` prints `True`).

<!-- Updated: Validation Session 1 - paper subscriptions on :EXNESS replace the live round trip; no-deploy week -->
<!-- Updated: Validation Session 3 - the paper week runs without spread by design -->
### T8.6 Start the paper week
- **Goal:** Both strategies run on PaperBroker on `:EXNESS` symbols, starting on a Tuesday, Wednesday or Thursday so the 7 days include a weekend close and reopen, with no deploy during the week.
- **Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, `GET /api/v1/subscriptions/`, `reports/user-preconditions.md`, `reports/exness-paper-week.md`
- **Steps:**
  1. Ask the user verbatim: "May I start a 7-day paper observation on XAUUSD:EXNESS (hitnrun2, 1m) and EURUSD:EXNESS (engulfing, 1h), and do you confirm there will be no production deploy during those 7 days?" Append `paper week: approved, no-deploy until <start + 7 days, ISO>` or `paper week: declined` to `user-preconditions.md`. On `declined`, STOP.
  2. Using the remote pattern, create the two subscriptions (no broker field exists; the engine uses PaperBroker):
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m"}'
     curl -s -X POST http://localhost:41921/api/v1/strategies/engulfing/subscriptions -H "Content-Type: application/json" -d '{"symbol":"EURUSD:EXNESS","interval":"1h"}'
     ```
     Record the returned `id`s, then `POST /api/v1/subscriptions/<id>/start` for each.
  3. Record the container start: `ssh -i "$KEY" "$HOST" "docker inspect -f '{{.State.StartedAt}}' pocketquant-app"`. Write `week_start_utc: <now ISO>`, `container_started_at: <value>` and both subscription ids at the top of `exness-paper-week.md`.
  4. Do not change how the live PaperBroker is built. It comes from `default_broker_config` without `spread`, so paper fills carry no spread (ask = bid); the week validates data, calendar and quotes, not P&L. Plumbing `spread` into the live broker is out of scope for this plan.
- **Success criteria:** Both subscriptions run, and the week's baseline is recorded.
- **Verify:** `grep -c "paper week: approved" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `1`. After 30 s, `curl -s http://localhost:41921/api/v1/subscriptions/` (remote pattern) piped to `python -c "import json,sys;d=json.load(sys.stdin);ids={'<id1>','<id2>'};print(sum(1 for s in d if s['id'] in ids and s['actual_state']=='running'))"` prints `2`.

<!-- Updated: Validation Session 1 - daily checks with proven log coverage instead of one week-long log count -->
### T8.7 Daily observation with proven log coverage
- **Goal:** Each day's counters are trustworthy: the container was not restarted and the logs reach back the full window.
- **Target files and symbols:** container logs, `reports/exness-paper-week.md`
- **Steps:**
  1. Once per day for 7 days (at least one run on the Monday after the weekend reopen), run:
     ```bash
     ssh -i "$KEY" "$HOST" 'S=$(docker inspect -f "{{.State.StartedAt}}" pocketquant-app); F=$(docker logs --timestamps --since 25h pocketquant-app 2>&1 | head -1 | cut -d" " -f1); CB=$(docker logs --since 25h pocketquant-app 2>&1 | grep -c exness_ws.circuit_breaker_open); RC=$(docker logs --since 25h pocketquant-app 2>&1 | grep -c exness_ws.reconnecting); echo "$S $F $CB $RC"'
     ```
  2. Append one row `| <date UTC> | <S> | <F> | <CB> | <RC> |` to the daily table in `exness-paper-week.md`.
  3. If `S` differs from `container_started_at`, or the first log line `F` is later than 24 hours ago, the day has no coverage: STOP and report to the user (a deploy or restart happened, or logs rotated away).
- **Success criteria:** Seven rows, each with unchanged `S` and full 24-hour coverage.
- **Verify:** For each run, `uv run python -c "import sys,datetime as d;f=d.datetime.fromisoformat(sys.argv[2][:19]).replace(tzinfo=d.UTC);print(sys.argv[1]==sys.argv[3] and f<=d.datetime.now(d.UTC)-d.timedelta(hours=24))" <S> <F> <container_started_at>` prints `True`. The `RC` value has no pass condition; record it only.

<!-- Updated: Validation Session 1 - integrity proven from stored bars via the API; week metrics from covered daily rows -->
### T8.8 Close the paper week
- **Goal:** Calendar and staleness behaved correctly across the weekend: zero circuit-breaker trips and zero integrity issues for the FX symbols.
- **Target files and symbols:** `POST /api/v1/market-data/integrity/check`, `reports/exness-paper-week.md`
- **Steps:**
  1. After the seventh daily row, run with the remote pattern for each `(S, I)` in `(XAUUSD:EXNESS, 1m)`, `(XAUUSD:EXNESS, 1h)`, `(EURUSD:EXNESS, 1m)` and `(EURUSD:EXNESS, 1h)`:
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/market-data/integrity/check -H "Content-Type: application/json" -d '{"symbol":"S","interval":"I","days_back":7}'
     ```
  2. Re-run the T8.6 subscriptions check.
  3. Write the four integrity results, the sum of the daily `CB` values, the sum of `RC`, and the `exness-backtest-results.md` summary to `exness-paper-week.md`.
  4. Ask the user whether to keep the two paper subscriptions running or stop them. Run `POST /api/v1/subscriptions/<id>/stop` if they say stop.
- **Success criteria:** Zero circuit-breaker trips and zero FX integrity issues, with both strategies still running.
- **Verify:** Each step 1 response piped to `python -c "import json,sys;d=json.load(sys.stdin);print(d['missing_count']==0 and d['misaligned_count']==0)"` prints `True`. The sum of the daily `CB` column is `0`. Step 2 prints `2`.

## Verification
T8.1 and T8.2 (spread, OpenAPI diff), T8.4 and T8.5 (D3), T8.6–T8.8 (paper week across a weekend).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any step that would place a live order, use `broker` `exness`, or set `EXNESS_LIVE_TRADING=true`.
- A deploy or restart during the observation week (T8.7 step 3).
- The paper week is declined, or a test failure stays unexplained.

## Risks
- **Swap costs are not modelled** (known, accepted in the advice). They are noted in the results report and not built.
- **Paper week fills ignore the spread** (known, accepted): the live PaperBroker is built from `default_broker_config` without `spread`; D3 covers spread through backtests.
- **No paper trade happens during the week** (M/L). That is not a failure; D3 covers trading behaviour through backtests, and the week validates data, calendar and quotes.
- **Log rotation hides events** (M/M). Mitigation: daily windows with a coverage proof, and integrity is checked from stored bars, not from logs.

## Security
No credentials are printed. Paper subscriptions never touch the Exness order endpoints, and the client refuses them anyway while live trading is off.

## Rollback
Stop the paper subscriptions with `POST /api/v1/subscriptions/<id>/stop`. Then `git revert` the spread merge commit. `spread` defaults to 0, so reverting is safe.

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
