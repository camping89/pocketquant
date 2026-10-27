---
phase: 8
title: "Validation: spread, backtests, paper week"
status: completed
priority: P1
effort: 4 short checks (2026-10-19 to 2026-10-26)
dependencies: [7]
---

# Phase 08: Validation (spread, backtests, paper week across a weekend)

<!-- Updated: 2026-10-13 develop reshape - develop paths (PaperBrokerAdapter, engine/backtest), no OpenAPI snapshot, develop gate and push -->
## Develop status
- Base branch: `develop` (`develop-sync` tracking `origin/develop`); ship with `git push origin develop-sync:develop`. There is no feature branch, no merge step and no `master` step.
- Develop has no `tests/baseline` (no OpenAPI snapshot and no venue command). The OpenAPI check in T8.2 compares the request model schema, and the gate is develop's gate.
- Remote pattern used below: `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app <command>"` (`KEY` and `HOST` as in Phase 06 T6.19). The app listens on `41921` inside the container (`deploy/compose.prod.yml:38`), and every route is under `/api/v1` (`Settings.api_prefix`, `core/config.py:51`).

## Progress 2026-10-19
- T8.1–T8.3 done. `PaperBrokerAdapter(spread=...)`, the backtest plumbing and `tests/core_test/infra/brokers/test_paper_broker_spread.py` shipped as `83fcd9d`. The finished-run `config_snapshot` (`engine/backtest/backtest_report_app_service.py`) also stores `spread`, on kongming's review, so a stored run says which spread produced it; the plan's file list missed this.
- Gate: broker tests 101 passed; the request schema minus `spread` is unchanged (`True`); no file under `src/pocketquant/app` changed; lint-imports `8 kept, 0 broken`; ruff and pyright 0 errors; `just test` shows only the 4 Windows `time.tzset` tests red; the ratchet exits 0 with no ceiling change.
- Released with the coordinator's approval: develop CI green, then `master` fast-forwarded to `83fcd9d` (this also deployed Phase 07's broker code, live trading off). Deploy verdict `HEALTHY (20/20 passed, 0 warnings, 0 failures)`.
- T8.4 done: every backfill call fetched bars; 1m `total_bars` about 129610 and 1h 17521 per symbol, above every minimum.
- T8.5 done: all 6 runs `finished`, each with trades (48 to 215). D3 holds. Results: `reports/exness-backtest-results.md`.
- 2026-10-19: the user replaced the 7-day week and its no-deploy freeze with five short checks (T8.7) and approved the two paper subscriptions. Row 0 ran and FAILED on integrity (EURUSD 1m rollover minutes, XAUUSD 1h US-holiday hours, both absent at the venue too); the subscriptions were not started. T8.6–T8.8 wait for the user's decision on those gaps.
- 2026-10-20: the user accepted venue-empty gaps (no `src/` change); C3 checks each gap against Exness. Row 0 re-ran and passed; T8.6 started both subscriptions at 2026-10-20T03:21:46Z.
- 2026-10-23: the user moved the US DST check (old row 4 on 2026-11-02, C5 `3600 True`) out of scope into its own plan, `261023-0056-exness-us-dst-session-shift`. This phase now ends after row 3.

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
Make D3 true and validate Exness end to end without live money: CFD backtests model the spread (ask = bid + spread), and both strategies run on the paper broker on `:EXNESS` symbols across a live XAUUSD daily break and a weekend close and reopen (T8.7 schedule). The 2026-11-01 US DST change is out of scope (see Out of scope). No live order is placed in this phase; the Exness broker stays off.

## Files to Create or Modify
- Modify: `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`, `src/pocketquant/engine/backtest/backtest_command_service.py`, `src/pocketquant/engine/backtest/backtest_dispatch.py`, `src/pocketquant/core/domain/backtest/config.py`, `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py`.
- Create: `tests/core_test/infra/brokers/test_paper_broker_spread.py`.
- Create reports: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtest-results.md`. Paper-run results live in the T8.7 results table.

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

<!-- Updated: 2026-10-19 short paper schedule (user decision) - five check dates instead of a 7-day week, no no-deploy freeze, each row records StartedAt; post-DST session check expects +1 h -->
### T8.6 Start the paper run
- **Goal:** Both strategies run on the paper broker on `:EXNESS` symbols and are checked on the four dates in T8.7. There is no no-deploy freeze: each row records the container `StartedAt`; a restart only shortens that row's log window and is not a failure. Integrity is judged from stored bars, so restarts do not affect it.
- **Approval:** recorded 2026-10-19 in `reports/user-preconditions.md` (`paper week: approved (short schedule), no freeze, ...`).
- **Setup (every check, repo root):** the key file has CRLF line endings, so use a normalized copy.
  ```bash
  mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key
  KEY=.cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
  ```
- **Steps:**
  1. Run C5 (T8.7); it must print `0 True` before 2026-11-01.
  2. Create the subscriptions (no broker field exists; the engine uses the paper broker), then start each returned `id`:
     ```bash
     ssh -i "$KEY" "$HOST" 'sh -s' <<'EOF'
     q() { docker exec pocketquant-app curl -s "$@"; }
     q -X POST http://localhost:41921/api/v1/strategies/hitnrun2/subscriptions -H 'Content-Type: application/json' -d '{"symbol":"XAUUSD:EXNESS","interval":"1m"}'; echo
     q -X POST http://localhost:41921/api/v1/strategies/engulfing/subscriptions -H 'Content-Type: application/json' -d '{"symbol":"EURUSD:EXNESS","interval":"1h"}'; echo
     EOF
     ssh -i "$KEY" "$HOST" "docker exec pocketquant-app curl -s -X POST http://localhost:41921/api/v1/subscriptions/<id>/start"
     ```
  3. Write both ids and the start time (UTC ISO) into row 0 of the T8.7 results table, and replace `not started` with `started <ISO>` in `user-preconditions.md`.
  4. The live paper broker stays as built (`default_broker_config`, no `spread`): the run validates data, calendar and quotes, not P&L.
- **Verify:** `grep -c "paper week: approved" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `1`. After 30 s, C2 with `CHECKS=''` and `IDS='<id1> <id2>'` prints `running 2`.

### T8.7 Check schedule
<!-- Updated: 2026-10-23 DST check moved to its own plan (user decision) - row 4 removed -->
- **Goal:** Cover what the week was for: a live XAUUSD daily break and a weekend close and reopen.
<!-- Updated: 2026-10-21 C3 timing - start at second 20+, one 60 s re-check for a just-closed minute (measurement timing only, pass rule unchanged) -->
<!-- Updated: 2026-10-20 venue-empty gaps pass (user decision) - C3 checks each gap at Exness; missing counts are recorded only -->
- **Commands** (after the T8.6 setup; C1, C2 and C5 tested in prod 2026-10-19, C3 on 2026-10-20):
  - **C1 log counters** since the previous row's check time. Prints `S= F= CB= RC= RL=`. If `S` is later than `SINCE`, the counters start at the restart; if `F` is later than both, logs rotated. Record either case; neither is a failure.
    ```bash
    SINCE=<previous row's "checked at", UTC ISO>
    ssh -i "$KEY" "$HOST" "SINCE=$SINCE sh -s" <<'EOF'
    L=$(docker logs --timestamps --since "$SINCE" pocketquant-app 2>&1)
    echo "S=$(docker inspect -f '{{.State.StartedAt}}' pocketquant-app) F=$(echo "$L" | head -1 | cut -d' ' -f1) CB=$(echo "$L" | grep -c exness_ws.circuit_breaker_open) RC=$(echo "$L" | grep -c exness_ws.reconnecting) RL=$(echo "$L" | grep -c exness.rate_limited_retry)"
    EOF
    ```
  - **C2 integrity, `sync_1m` and subscriptions.** `CHECKS` is a space-separated list of `SYMBOL/INTERVAL/DAYS_BACK`.
    ```bash
    CHECKS='<per row>'; WINDOW=<24h|7d>; IDS='<id1> <id2>'
    ssh -i "$KEY" "$HOST" "CHECKS='$CHECKS' WINDOW=$WINDOW IDS='$IDS' sh -s" <<'EOF'
    q() { docker exec pocketquant-app curl -s "$@"; }
    py() { docker exec -i pocketquant-app python -c "$1"; }
    for c in $CHECKS; do
      set -- $(echo "$c" | tr / ' ')
      q -X POST http://localhost:41921/api/v1/market-data/integrity/check -H 'Content-Type: application/json' -d "{\"symbol\":\"$1\",\"interval\":\"$2\",\"days_back\":$3}" \
        | py "import json,sys;d=json.load(sys.stdin);print('$1 $2 $3d missing', d['missing_count'], 'misaligned', d['misaligned_count'], d['gap_ranges'][:5])"
    done
    q "http://localhost:41921/api/v1/system/jobs/sync_1m/stats?window=$WINDOW" | py "import json,sys;d=json.load(sys.stdin);print('sync_1m p95_ms', d['p95_ms'], d['by_status'])"
    q http://localhost:41921/api/v1/subscriptions/ | py "import json,sys;ids=set('$IDS'.split());print('running', sum(1 for s in json.load(sys.stdin) if s['id'] in ids and s['actual_state']=='running'))"
    EOF
    ```
  - **C3 integrity with a venue check.** Runs the integrity check for each `CHECKS` item, then reads each `gap_ranges` entry forward from Exness (`getCandleHistory`, positive `count` reads forward from `from` inclusive; candle field `time`). A range is venue-empty when no candle has `time <= range_end`. Prints `PASS` when `misaligned 0` and every range is venue-empty. C3 replaces C2's integrity loop, so run C2 with `CHECKS=''`. Start C3 at UTC second 20 or later: `sync_1m` fires at second 2 and takes up to about 15 s, so an earlier check can see the just-closed minute as missing. `check()` sends `X-Admin-Token` from the app settings (tested in prod 2026-10-23).
    ```bash
    CHECKS='<per row>'
    ssh -i "$KEY" "$HOST" "CHECKS='$CHECKS' docker exec -i -e CHECKS pocketquant-app python -" <<'EOF'
    import asyncio, json, os, urllib.request, datetime as d
    from pocketquant.core.config import get_settings
    from pocketquant.core.infra.exness.exness_client import ExnessClient
    TF = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D1"}
    SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    TOKEN = get_settings().admin_token.get_secret_value()  # admin auth guards every POST since the go-live deploy
    def check(sym, iv, days):
        req = urllib.request.Request("http://localhost:41921/api/v1/market-data/integrity/check",
            data=json.dumps({"symbol": sym, "interval": iv, "days_back": days}).encode(),
            headers={"Content-Type": "application/json", "X-Admin-Token": TOKEN})
        return json.load(urllib.request.urlopen(req))
    async def main():
        c = ExnessClient(get_settings())
        try:
            for item in os.environ["CHECKS"].split():
                sym, iv, days = item.split("/")
                r = check(sym, iv, int(days))
                out = []
                for start, end in r["gap_ranges"]:
                    s, e = d.datetime.fromisoformat(start), d.datetime.fromisoformat(end)
                    n = min(1000, int((e - s).total_seconds() // SEC[iv]) + 1)
                    body = await c.call("getCandleHistory", params={"instrument": sym.split(":")[0],
                        "timeframe": TF[iv], "price_type": "bid", "from": s.isoformat(), "count": n})
                    have = [k["time"] for k in body.get("candles", []) if d.datetime.fromisoformat(k["time"]) <= e]
                    out.append((start[:16], end[:16], "venue_empty" if not have else "VENUE_HAS " + str(have[:3])))
                ok = r["misaligned_count"] == 0 and all(o[2] == "venue_empty" for o in out)
                print(sym, iv, days + "d", "missing", r["missing_count"], "misaligned", r["misaligned_count"],
                      "PASS" if ok else "FAIL", out[:8])
        finally:
            await c.close()
    asyncio.run(main())
    EOF
    ```
  - **C5 sessions.** Compares the live `trade_sessions` with the calendar constants as merged UTC open segments. The constants were recorded under EDT and the adapter holds them in `America/New_York`, so from 2026-11-01 the expectation is the constants shifted +1 h (checked against `ExnessSessionCalendarAdapter.is_open` for the weeks of 2026-10-19 and 2026-11-02: unshifted matches before DST, +1 h matches after, unshifted fails after). Prints `<shift> <bool>`; every row here runs before 2026-11-01, so it must print `0 True`. The post-DST `3600 True` check is in the DST plan.
    ```bash
    ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
    import asyncio
    import datetime as d
    from pocketquant.core.config import get_settings
    from pocketquant.core.infra.exness.exness_client import ExnessClient
    from pocketquant.core.infra.calendars.exness_session_calendar_adapter import _EURUSD_SESSIONS, _XAUUSD_SESSIONS, _shifted, _week_offset
    def spans(sessions, shift):  # merged open [start, end) seconds from Monday 00:00 UTC
        pieces = sorted(p for s in sessions if s["trade_mode"] == "enabled"
                        for p in _shifted(_week_offset(s["week_start_time"]), _week_offset(s["week_end_time"]) + 1, shift))
        merged = []
        for a, b in pieces:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged
    async def main():
        c = ExnessClient(get_settings())
        try:
            return [(await c.conditions(n))["trade_sessions"] for n in ("XAUUSD", "EURUSD")]
        finally:
            await c.close()
    shift = 3600 if d.datetime.now(d.UTC).date() >= d.date(2026, 11, 1) else 0  # EDT-recorded constants move 1 h later under EST
    live = asyncio.run(main())
    print(shift, [spans(t, 0) for t in live] == [spans(c, shift) for c in (_XAUUSD_SESSIONS, _EURUSD_SESSIONS)])
    EOF
    ```
- **Pass (every row):**
  1. `misaligned 0` on every C3 line.
  2. Every `gap_ranges` entry is venue-empty: C3 prints `PASS` on every line.
  3. On a C3 `FAIL` whose only `VENUE_HAS` range ends within 2 minutes of the check, re-run C3 once after 60 s first; a `PASS` then passes. Otherwise, run `POST /api/v1/market-data/integrity/repair` once for that symbol and interval, then re-run C3. Still `FAIL` → the row fails.
  4. `sync_1m p95_ms < 60000`, `CB=0`, `running 2` (from the row where T8.6 ran).
  5. Recorded only: `missing` counts, the venue-empty ranges, `RC`, `RL` and `by_status`.
- **Schedule** (Bangkok = UTC+7):

| # | When (Bangkok / UTC) | Why | Run |
|---|---|---|---|
| 0 | Mon 2026-10-19 21:10 / 14:10Z | backfilled weekends, baseline | C3 `XAUUSD:EXNESS/1m/7 EURUSD:EXNESS/1m/7 XAUUSD:EXNESS/1h/90 EURUSD:EXNESS/1h/90`; C2 `CHECKS=''`, `WINDOW=24h`; C1 with `SINCE` 24 h earlier; C5; then T8.6 |
| 1 | Tue 2026-10-20 05:30 / Mon 22:30Z | after the XAUUSD break (20:58:00–22:00:29Z) | C1; C3 `XAUUSD:EXNESS/1m/1 EURUSD:EXNESS/1m/1`; C2 `CHECKS=''`, `WINDOW=24h` |
| 2 | Sat 2026-10-24 10:00 / 03:00Z | Friday close; ticks WS idle | C1; C3 `XAUUSD:EXNESS/1m/4 EURUSD:EXNESS/1m/4`; C2 `CHECKS=''`, `WINDOW=7d` |
| 3 | Mon 2026-10-26 10:00 / 03:00Z | Sunday reopen (EUR 21:05Z, XAU 22:01:30Z) | C1; C3 `XAUUSD:EXNESS/1m/3 EURUSD:EXNESS/1m/3 XAUUSD:EXNESS/1h/7 EURUSD:EXNESS/1h/7`; C2 `CHECKS=''`, `WINDOW=7d` |

- **Results:**

| # | Checked at (UTC) | `S` (StartedAt) | `F` | CB | RC | RL | Integrity missing/misaligned | `sync_1m` p95 ms (by_status) | Running | C5 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2026-10-19T14:08Z | 2026-10-19T02:17:57Z | 2026-10-19T02:18:10Z | 0 | 8 | 41 | XAU 1m 7d 0/0; **EUR 1m 7d 12/0**; **XAU 1h 90d 2/0**; EUR 1h 90d 0/0 | 11728 (completed 1382, failed 2) | not started | `0 True` | **FAIL** |
| 0 re-run | 2026-10-20T03:20Z | 2026-10-19T02:17:57Z | 2026-10-19T16:30:09Z (rotated) | 0 | 11 | 30 | C3 all `PASS`, misaligned 0; missing XAU 1m 7d 0, EUR 1m 7d 13 (5 venue-empty ranges), XAU 1h 90d 2 (1 venue-empty range), EUR 1h 90d 0 | 12297 (completed 1382) | `running 2` at 03:22:33Z: hitnrun2 XAUUSD 1m `01a15754-39ed-73e3-921e-df085eb4a786`, engulfing EURUSD 1h `01a15754-3ab5-7258-b46b-ad98e1f3471f`, started 03:21:46Z | `0 True` | **PASS** |
| 1 | 2026-10-20T22:33Z | 2026-10-19T02:17:57Z (no restart) | 2026-10-20T12:32:06Z (rotated) | 0 | 4 | 4 | C3 at 22:34:02Z: XAU 1m 1d 1/0 `FAIL`, gap 22:33–22:33Z `VENUE_HAS 22:33:00` (the minute closed 2 s before the check; not yet synced); EUR 1m 1d 5/0 `PASS`, 21:00–21:04Z venue-empty. Repair not run (read-only check). Read-only C3 re-run at 22:34:44Z: XAU 1m 1d 0/0 `PASS`; EUR 1m 1d 5/0 `PASS` (same venue-empty range) | 12573 (completed 1400, running 1) | `running 2` | `0 True` | **PASS** on the re-run; ran late on Wed 2026-10-21 (rescheduled from Tue 2026-10-20 05:30 Bangkok, after the 20:58–22:00Z XAUUSD daily break) |
| 2 | 2026-10-24T03:03Z | 2026-10-22T15:34:21Z (restarted by a deploy after row 1; counters start there) | 2026-10-23T11:40:09Z (rotated) | 0 | 10 | 3 | C3 at 03:04:20Z: XAU 1m 4d 0/0 `PASS`; EUR 1m 4d 10/0 `PASS`, venue-empty 10-20 21:00–21:04Z and 10-22 21:00–21:04Z. C3 sent `X-Admin-Token` (admin auth guards POST since the go-live deploy; without it the check returns 401) | 11858 (completed 9742, failed 2) | `running 2` | not run | **PASS** |
| 3 | 2026-10-26T03:03Z | 2026-10-22T15:34:21Z (no restart since row 2) | 2026-10-25T19:34:06Z (rotated; the window still covers the Sunday reopen, EUR 21:05Z and XAU 22:01:30Z) | 0 | 0 | 49 | C3 at 03:03:27Z: XAU 1m 3d 0/0, EUR 1m 3d 0/0, XAU 1h 7d 0/0, EUR 1h 7d 0/0, all `PASS`, no gap ranges | 11906 (completed 9745) | `running 2` | not run | **PASS** |

Summary (T8.8, 2026-10-26): rows 0 (on its re-run), 1, 2 and 3 passed. Over rows 0 re-run to 3: `CB` 0, `RC` 25, `RL` 86. The highest `sync_1m` p95 was 12573 ms (row 1). Log rotation left the Saturday idle hours of 2026-10-24 03:03Z to 2026-10-25 19:34Z without log coverage; integrity over that span is judged from stored bars. Backtests: `reports/exness-backtest-results.md`. T8.8 step 2: the user chose stop; both subscriptions were stopped on 2026-10-26 (`stopped` confirmed). Phase 08 completed 2026-10-26.

- **Row 0 failure (2026-10-19), evidence:**
  - EURUSD 1m gaps: 2026-10-12 21:00 and 21:03, 2026-10-13 21:00–21:03, 2026-10-14 21:00–21:04, 2026-10-15 21:00 (12 minutes). Exness `getCandleHistory` (M1, bid) has no candle there either: 2026-10-14 goes 20:59 → 21:05; 2026-10-12 has 21:01, 21:02 and 21:04 but not 21:00 or 21:03. `_EURUSD_SESSIONS` marks Mon–Thu open all day, so the calendar expects these minutes.
  - XAUUSD 1h gap: 2026-09-07 19:00–20:00Z. Exness H1 has no candle there either (18:00 → 22:00); the next Monday, 2026-09-14, has 19:00 and 20:00. 2026-09-07 was the US Labor Day holiday; the calendar has no holidays.
  - Inference, not verified: EURUSD trades thinly or not at all in the 21:00–21:04Z rollover, and XAUUSD closed early for the holiday. The stored bars match the venue, so this is a calendar or pass-criterion question, not lost data.
  - `sync_1m` `failed 2`: two runs at 2026-10-19 00:18–00:22Z with `mongodb:27017: timed out`, before the 02:17:57Z restart. Recorded only.
  - Not done because of the failure: T8.6 step 2 (subscriptions not started) and rows 1–4. The user decides between a calendar change (code, outside this phase) and accepting known venue gaps in the integrity criterion; then row 0 is re-run.
  - Re-run 2026-10-20 under the venue-empty rule. EUR 1m venue-empty ranges: 10-13 21:00–21:03, 10-14 21:00–21:04, 10-15 21:00, 10-19 21:00–21:01 and 21:03Z. XAU 1h: 09-07 19:00–20:00Z. The safety check printed `True False` (configured, live trading off).
- **Rule:** a failing row is recorded with its output and the schedule stops; no code fix inside this phase.

### T8.8 Close the paper run
- **Goal:** Rows 0–3 pass.
- **Steps:**
  1. After row 3, add a one-line summary under the results table: rows passed, sums of `CB`, `RC` and `RL`, the highest `sync_1m` p95, and a pointer to `reports/exness-backtest-results.md`.
  2. Ask the user whether to keep the two paper subscriptions running or stop them; on stop, `POST /api/v1/subscriptions/<id>/stop` for each.
- **Success criteria:** Every row's verdict is PASS.
- **Verify:** The results table has a `PASS` row for each of rows 0–3.

## Verification
T8.1 and T8.2 (spread and the request schema diff), T8.4 and T8.5 (D3), T8.6–T8.8 (short paper schedule, rows 0–3 PASS).

## Out of scope
- The 2026-11-01 US DST session shift (old T8.7 row 4 and the C5 `3600 True` expectation): `../../261023-0056-exness-us-dst-session-shift/plan.md`. Closing this phase does not wait for it.

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any step that would place a live order, set `config.broker = "exness"`, or set `EXNESS_LIVE_TRADING=true`.
- A failing row in the T8.7 schedule.
- C5 prints `False` (the instrument sessions differ from the expected calendar).
- A test failure stays unexplained.

## Risks
- **Swap costs are not modelled** (known, accepted in the advice). They are noted in the results report and not built.
- **Paper week fills ignore the spread** (known, accepted): the live paper broker is built from `default_broker_config` without `spread`; D3 covers spread through backtests.
- **No paper trade happens during the week** (M/L). That is not a failure; D3 covers trading behaviour through backtests, and the week validates data, calendar and quotes.
- **Log rotation or a restart hides events** (M/M). No freeze: each row records `S` and `F`, so a short window is visible; integrity is checked from stored bars, not from logs.
- **Exness answers 429 below the published rate** (M/M). Data calls retry up to 3 times and log `exness.rate_limited_retry`; the deep backfill runs at half the request rate. The daily `RL` column shows how often it happens.
- **The calendar does not model venue gaps** (H/M, seen 2026-10-19): Exness emits no candle for a minute without ticks. EURUSD M1 misses random parts of 21:00–21:17Z on weekdays, and XAUUSD H1 has no 2026-09-07 19:00–20:00Z. Integrity counts them as missing. Rule: a gap passes when C3 confirms the venue has no candle there; a gap the venue can fill fails the row.

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
