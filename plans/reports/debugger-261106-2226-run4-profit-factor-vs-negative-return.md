# Run 4: profit factor above 1 with a negative return

## Verdict

Not an accounting bug. The metrics use two PnL bases:

- `profit_factor`, `win_rate`, `avg_win`, `avg_loss` (and the stats page: PF by direction, PnL histogram, streaks, wins/losses filter) read `Trade.pnl`, which is gross of commission.
- `total_return`, `cagr`, `max_drawdown`, the equity curve and Sharpe read the paper broker balance, which is net of every fill commission.

Run 4 made +228.62 gross and paid 552.53 commission, so it lost 323.91 net. Profit factor net of commission is 0.84, not 1.14. The equity ledger reconciles to the cent in all six runs.

## Evidence

### Code (read on `develop`, 2026-11-06)

- `core/domain/position/entities.py` `reduce_quantity`: `TradeClosedEvent.pnl = pnl_per_unit * quantity * multiplier` (price move only). Commission goes to a separate `commission` field (entry portion + exit commission).
- `core/infra/brokers/paper/paper_broker_adapter.py` `_execute_fill_with_commission`: `self._balance -= commission` on every fill; `_reduce_and_credit` adds the gross realized delta.
- `engine/backtest/backtest_report_app_service.py` `finalize`: `current_equity = broker.get_balance().available_balance` (net); the realized equity curve is recorded from the same balance in `on_trade`.
- `core/domain/trading/performance_calculator_domain_service.py` `build`: `gross_profit`/`gross_loss`, win/loss counts and averages come from `t.pnl` (gross); `total_return` comes from `current_equity` (net).
- `engine/backtest/backtest_stats_service.py`: `profit_factor_by_direction`, histogram and streaks use `t.pnl` (gross).

### Prod data (read-only PRODPY, 2026-11-06)

All six runs still exist. Config for each: capital 10000, `commission_bps=3.0`, `spread=0.0`, `slippage_bps=0.5`.

| Run | Trades | Stored PF | Recomputed PF gross | PF net | Sum gross PnL | Fill commission | Stored return × capital | Gross − fill commission | Win rate gross → net | Open lots |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8516 | 0.7945 | 0.7945 | 0.3689 | −967.58 | 3768.04 | −4735.62 | −4735.62 | 0.284 → 0.221 | 1 |
| 2 | 3585 | 0.7794 | 0.7794 | 0.4622 | −734.14 | 1857.91 | −2592.05 | −2592.05 | 0.228 → 0.171 | 1 |
| 3 | 2479 | 0.9315 | 0.9315 | 0.6007 | −202.31 | 1363.91 | −1566.22 | −1566.22 | 0.299 → 0.275 | 1 |
| 4 | 933 | 1.1421 | 1.1421 | 0.8408 | +228.62 | 552.53 | −323.91 | −323.91 | 0.250 → 0.214 | 1 |
| 5 | 707 | 0.8109 | 0.8109 | 0.6465 | −347.25 | 407.51 | −754.76 | −754.76 | 0.267 → 0.263 | 0 |
| 6 | 275 | 0.6856 | 0.6856 | 0.5919 | −360.91 | 160.04 | −520.95 | −520.95 | 0.204 → 0.189 | 0 |

- Stored PF equals PF recomputed from gross `backtest_trades.pnl` in every run, so PF covers the same trade set as the other metrics.
- `sum(gross pnl) − sum(fill commission in backtest_orders)` equals `total_return × capital` exactly in every run. In runs 1-4 the trade-level commission sum is 0.2-0.3 lower than the fill sum; that gap is the entry commission of the one lot still open at the end, which the balance has paid but no closed trade carries.
- Runs 1-3, 5, 6 have the same gap. It shows only in run 4 because run 4 is the only run whose gross result is positive.
- In run 4, 33 of 233 gross winners become losers after commission.

## Related finding (code only, not checked on prod)

`engine/live/live_metrics_query_service.py` builds live/paper metrics from `current_equity = baseline + sum(t.pnl)` and an equity curve that adds `t.pnl`. For paper subscriptions `t.pnl` comes from the same `TradeClosedEvent`, so live metrics ignore commission entirely: return and drawdown there are gross, unlike backtests. Whether Exness live `Trade.pnl` is gross or net of broker commission was not checked.

## Proposed fix (not applied)

Recommended: one net basis everywhere a metric is computed.

1. In `PerformanceCalculatorDomainService.build`, compute PF, win/loss counts, `avg_win`, `avg_loss` from `t.pnl - t.commission`.
2. Apply the same net value in `backtest_stats_service.py` (PF by direction, histogram, streaks) and in the trade repository wins/losses filter (needs a `$expr` or a stored net field).
3. In `live_metrics_query_service.py`, subtract `t.commission` in `current_equity` and `_equity_curve`.
4. Keep `Trade.pnl` gross in storage; the trades table already shows commission next to it. Optionally show a net column.
5. Test: a two-trade fixture where gross PF > 1 and net PF < 1; assert PF < 1 and that `sum(net) == final_equity − initial` with no open lots.

Stored `metrics` on existing runs keep the old gross values until the runs are re-run or a one-off recompute writes them (back up `backtest_runs` first).

Alternative: keep gross PF and label it "gross of commission" in the UI and reports. Cheaper, but PF and win rate would still disagree with return, which is what caused this question.

## How Binance does it (checked 2026-11-06, official Binance docs)

- Per trade and per position, PnL is gross and the fee is a separate field. `GET /fapi/v1/userTrades` returns `realizedPnl` and `commission` side by side. The wallet formula keeps them apart: Wallet Balance = Net Transfer + Realized Profit + Net Funding Fee − Commission.
- Account and performance figures are net. Futures PNL Analysis is the change in wallet balance, so fees and funding are already in it. Copy-trading "Realized Profit = Total Realized PNL for Positions − Total Fees", and ROI, MDD and Sharpe are built from that net PnL.
- Binance publishes no profit factor. Its copy-trading win rate is "profitable closed positions / total positions", and the docs do not say whether "profitable" is before or after fees.

Owner decision: follow Binance. Keep `Trade.pnl` gross with commission beside it; compute every performance metric (PF, win rate, avg win/loss, return, drawdown, Sharpe, stats page, live metrics) net of commission. Recompute stored metrics of existing runs after the change, with a backup first.

Sources: [Account Trade List](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Account-Trade-List), [PNL Analysis FAQ](https://www.binance.com/en/support/faq/how-are-pnl-calculated-on-binance-futures-and-options-pnl-analysis-dbb171c4db1e4626863ec8bc545be46a), [Copy-trading indicators FAQ](https://www.binance.com/en/support/faq/portfolio-performance-indicators-in-binance-futures-copy-trading-54aa6d3b43bc4f6eb4a3a6e3aea40acd), [Wallet balance blog](https://www.binance.com/en/blog/futures/what-is-the-available-balance-margin-balance-and-total-balance-on-binance-futures-457299340443288694).

## Spread

The owner confirmed that XAUUSD on Exness has a small spread, not zero. `RunBacktestCommand.spread` defaults to `0.0`, and `web/src` never sends a spread, so every UI-launched backtest runs with zero spread.

### Exness costs (checked 2026-11-06)

Published by Exness (help centre and account-type pages, via search; direct fetch was blocked): Raw Spread charges 3.50 USD per lot per side on XAUUSD, spread "from 0.0". One lot is 100 oz, so that is 0.035 USD/oz per side. No official average Raw Spread gold spread was found; third-party figures range from about 0.04 to 0.15 USD/oz.

Measured on the prod Exness account through its API (`price_type=both` candles, `XAUUSD` conditions):

- Spread (ask − bid) over 2025-11-03..2026-10-30: H1 median 0.168, p10 0.112, p90 0.196, p99 0.255 USD/oz; M15 gives the same median. Monthly medians run from 0.112 (Nov-Jan) to 0.252 (Mar). The last 14 days of M1 are 0.168 almost every minute.
- Conditions: `contract_size=100`, `point_digits=3`, `swap_long=-496.4`, `swap_short=0`, and no `commission_settings` key.
- The account (real, created 2026-10-03) exposes no account type. It has no deals in the last 29 days, so commission per deal could not be observed. No prod `trades` row comes from a live Exness subscription; all 67 XAUUSD rows are paper.

Inference, not verified: a 0.168 spread with no commission settings looks like a Pro or Standard-type account, not Raw Spread.

Cost per round trip per oz at a gold price near 3900:

| Model | Commission | Spread | Total |
|---|---|---|---|
| Current backtests (3 bps, spread 0) | 2.34 | 0 | 2.34 |
| Prod account as measured | 0 (inferred) | 0.168 | 0.168 |
| Raw Spread as published | 0.07 | unmeasured, ~0.04-0.15 third-party | ~0.11-0.22 |

The current backtest cost is about 10-20× the real cost. Estimate, not a re-run: run 4 at the measured account cost would pay about 40 USD instead of 553 and end near +190 instead of −324.

The existing `ContractSpec.commission_per_contract` (per unit, per side; XAUUSD quantity is in oz with multiplier 1) already models a per-lot commission: 0.035 for Raw Spread, 0.0 for a no-commission account. Prod `symbols` has it as `None` for `XAUUSD:EXNESS`, so the 3 bps fallback applies.

Swap is not modelled in backtests. `swap_long=-496.4` points with 3 digits reads as about −0.50 USD/oz per night for longs (×3 on Wednesday); this unit reading is not verified.

## Not verified / caveats

- Whether 3 bps commission with zero spread models Exness XAUUSD costs. Exness account types price XAUUSD by spread or by per-lot commission; this was not checked here. Cost is the whole difference between a gross edge and a net loss in run 4, so the cost model decides that run's verdict.
- The read-only script `/tmp/pf.py` (no secrets) remains in the prod `api` container; the container user cannot delete it. It is gone on the next container recreate. The VPS copy and the local SSH key were removed.

## Unresolved questions

1. Which cost model should backtests use: the prod account as measured (spread 0.168, no commission) or Raw Spread (0.035/oz per side plus a raw spread)?
2. Where should the spread live: a per-symbol default in the contract spec, a run input in the UI, or both?
3. Is swap in scope now or later?

## Implementation (2026-11-07, uncommitted on `develop`)

Owner decisions: metrics follow Binance (net of commission); gold costs follow an Exness Raw Spread account (0.035 per oz per side); spread is a per-symbol default and a UI input with a hint; swap stays out.

- `Trade.net_pnl` (pnl − commission) drives profit factor, win rate, avg win/loss, the stats page, the wins/losses filter and live metrics equity. `Trade.pnl` stays gross in storage.
- `ContractSpec.spread` is the per-symbol typical spread. `RunBacktestCommand.spread` is optional; when omitted the run takes the symbol's spread. `GET /market-data/symbols` returns it.
- The run's config snapshot records `commission_per_contract`; the cost cards show it and a spread card.
- `scripts/seed_exness_symbols.py` sets XAUUSD `commission_per_contract=0.035`, `spread=0.08`.
- The backtest form has a spread input; blank uses the symbol default shown in the placeholder and hint.

Verification: focused tests pass; full suite `4 failed, 1351 passed, 1 skipped, 4 errors`, all in the known-red `test_utc_runtime_guard` / `test_cron_trigger_timezone`; ruff, import-linter (6 kept), metric ratchet, pyright on touched files (0 errors), `tsc -b`, eslint (0 errors), vitest (106 passed).

Pending prod steps, in order: release, `seed_exness_symbols.py --apply` (also switches live paper XAUUSD subscriptions to the per-contract fee once they reload), back up and recompute stored metrics of finished runs (`.cache/recompute_net.py`, dry run first).

## Release and prod changes (2026-11-07)

- Commits `f37060aa` (net metrics) and `1e47ca94` (spread and Raw Spread gold costs) are on `develop` and `master`. Develop CI and the master deploy (run 42338601824) are green; `api`, `worker`, `trader`, `web` came back healthy.
- Backups before writes: `.cache/backups/prod-symbols-and-run-metrics-261107.json` (all `symbols` docs and every run's metrics) and `.cache/backups/backtest_runs_metrics_261107-043648.json`.
- `seed_exness_symbols.py --apply`: XAUUSD:EXNESS now has `commission_per_contract=0.035`, `spread=0.08`; `GET /market-data/symbols` returns the spread.
- The 6 old runs now store PF, win rate, win/loss counts and averages net of commission (values in the Prod data table above).
- The three paper subscriptions still use 3 bps until the trader next restarts; the deploy restarted it before the seed.

## Re-runs with Raw Spread costs

Same range, symbol and parameters as the original six. The first re-run of set 1 started inside the api's 60 s symbol cache and ran with the old costs; it is renamed "old costs (3 bps, spread 0), duplicate" (`01a1b44b-c639-7315-b005-76887416ac3b`) and set 1 was run again.

| # | intervals | entry_type | exit_mode | run id | trades | total_return | PF (net) | max_drawdown | sharpe | win_rate | commission | old return | old PF (net) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m 15m 1h | market | sl_tp | 01a1b45b-1963-75ad-b1a0-168ae4ef5570 | 8608 | −0.1488 | 0.7537 | −0.1501 | −7.72 | 0.2766 | 125.81 | −0.4736 | 0.3689 |
| 2 | 5m 15m 1h | stop | strategy | 01a1b450-94b6-77dc-afab-29375c62d13c | 3662 | −0.0954 | 0.7475 | −0.0962 | −4.47 | 0.2206 | 55.03 | −0.2592 | 0.4622 |
| 3 | 15m 1h 4h | market | sl_tp | 01a1b455-be9d-741d-8130-33b4bbcc52ea | 2487 | −0.0338 | 0.8951 | −0.0464 | −1.68 | 0.2923 | 38.60 | −0.1566 | 0.6007 |
| 4 | 15m 1h 4h | stop | strategy | 01a1b457-ba7e-7703-bc50-06a6f08a78c9 | 941 | +0.0199 | 1.1184 | −0.0107 | +1.02 | 0.2476 | 15.04 | −0.0324 | 0.8408 |
| 5 | 1h 4h 1d | market | sl_tp | 01a1b459-6839-71b4-b38a-08cf59e1a7e8 | 705 | −0.0370 | 0.8029 | −0.0400 | −1.80 | 0.2652 | 11.01 | −0.0755 | 0.6465 |
| 6 | 1h 4h 1d | stop | strategy | 01a1b45a-1d1d-7459-a415-18a752780c52 | 276 | −0.0377 | 0.6764 | −0.0391 | −1.65 | 0.2029 | 4.26 | −0.0521 | 0.5919 |

Run 4's PF and return now agree. It is the only set that made money after costs. Trade counts moved slightly because the spread changes which stops trigger.

Compare views:

https://pocketquant.xyz/backtest/compare?runs=01a1b45b-1963-75ad-b1a0-168ae4ef5570,01a1b450-94b6-77dc-afab-29375c62d13c
https://pocketquant.xyz/backtest/compare?runs=01a1b455-be9d-741d-8130-33b4bbcc52ea,01a1b457-ba7e-7703-bc50-06a6f08a78c9
https://pocketquant.xyz/backtest/compare?runs=01a1b459-6839-71b4-b38a-08cf59e1a7e8,01a1b45a-1d1d-7459-a415-18a752780c52
https://pocketquant.xyz/backtest/compare?runs=01a19ba6-2f0e-73e6-9a2e-22ea60e177c7,01a1b457-ba7e-7703-bc50-06a6f08a78c9

Not checked: the new spread input and cost cards were not opened in a browser (the browser tool failed to connect); `tsc`, eslint and vitest pass.
