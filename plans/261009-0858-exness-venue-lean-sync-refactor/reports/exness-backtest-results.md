# Exness backtest results (Phase 08 T8.5)

All six runs reached `finished` in prod with a non-empty trades list, so D3 holds: both strategies backtest on Exness bars with the spread modelled in `PaperBrokerAdapter` (ask = bid + spread).

## Setup
- Code: `83fcd9d` (`feat(backtest): model a constant bid/ask spread in paper broker fills`), released to prod by fast-forwarding `master`. The deploy verdict was `HEALTHY (20/20 passed, 0 warnings, 0 failures)`.
- Runs were posted on 2026-10-19 at 03:03 UTC with `initial_capital=10000`, `slippage_bps=0` and `commission_bps=0`. The spread is the median spread per symbol from the spike journal `docs/journals/2026-10-13-exness-api-spike.md`. Each run's stored `config_snapshot.spread` matches the posted value.
- Windows: `hitnrun2` on 1m from 2026-09-19T03:03Z to 2026-10-19T03:03Z (30 days); `engulfing` on 1h from 2025-10-19T03:03Z to 2026-10-19T03:03Z (365 days).
- Every run finished within two 60-second polls.

## Results

| Strategy | Symbol | Interval | Spread | Run id | Status | Trades | Total return | Max drawdown | Win rate |
|---|---|---|---|---|---|---|---|---|---|
| hitnrun2 | XAUUSD:EXNESS | 1m | 0.168 | `01a1521c-f880-7619-862a-0b68b2cd48c0` | finished | 201 | -0.253% | -0.456% | 84.6% |
| engulfing | XAUUSD:EXNESS | 1h | 0.168 | `01a1521c-fe04-771c-b347-ce55c3da1d56` | finished | 111 | +0.016% | -1.040% | 43.2% |
| hitnrun2 | EURUSD:EXNESS | 1m | 0.00006 | `01a1521d-0399-75a8-809e-02ea293ad80b` | finished | 48 | +0.204% | -0.010% | 62.5% |
| engulfing | EURUSD:EXNESS | 1h | 0.00006 | `01a1521d-0973-7092-b12e-909ac4b8c534` | finished | 150 | -0.141% | -0.367% | 42.0% |
| hitnrun2 | BTCUSD:EXNESS | 1m | 4.48 | `01a1521d-0fc3-75bc-81cb-b83e9d39d2fd` | finished | 215 | +2.027% | -0.155% | 86.5% |
| engulfing | BTCUSD:EXNESS | 1h | 4.48 | `01a1521d-1673-7522-ab72-5ff72a1266f3` | finished | 161 | -0.870% | -2.382% | 39.8% |

Trades is `total` from `GET /api/v1/backtest/{id}/trades?limit=1`; return, drawdown and win rate come from the run's `metrics`. Three runs ended with one open position (both XAUUSD runs and hitnrun2 EURUSD).

## Backfill used (T8.4)
`scripts/backfill/provider_bars.py` ran in the app container at `--rate-fraction 0.5`. Every call printed `fetched=<n>` with n > 0, which the script's code maps to exit 0.

| Symbol | 1m `total_bars` (90 days requested) | 1h `total_bars` (730 days requested) |
|---|---|---|
| XAUUSD:EXNESS | 129612 | 17521 |
| EURUSD:EXNESS | 129611 | 17521 |
| BTCUSD:EXNESS | 129612 | 17521 |

Each call fetched exactly `days × bars per day` (129600 and 17520). For the FX symbols this means the history reaches further back than 90 or 730 calendar days, because the provider returns exactly `n_bars` closed bars and weekend slots have no bars (inference from the Phase 06 fix `494d3ca`, not checked bar by bar). Each 1m call took 12 to 13 minutes, which is longer than the 10-minute command limit the phase assumed, so they ran as a background job.

## Known limitations
- Swap costs are not modelled (accepted in the advice).
- Open SHORT positions are marked to the bid close, so unrealized equity and max drawdown for shorts are overstated by `spread × quantity` while a short is open. Realized P&L uses the ask correctly.
- Pending BUY limit orders still cross on the bid low. Both strategies enter with MARKET orders by default, so this does not affect these runs.
- The live paper broker has no spread (`default_broker_config`), so paper-week fills are bid-only; spread is covered by these backtests.
