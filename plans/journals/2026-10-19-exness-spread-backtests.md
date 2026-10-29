# Exness Backtests With a Modelled Spread

**Date**: 2026-10-19
**Severity**: Low
**Component**: `core/infra/brokers/paper/paper_broker_adapter.py`, `engine/backtest/`
**Status**: Resolved for backtests (prod on master `83fcd9d`); the paper week is pending user approval

---

## What Happened

Exness candles are bid prices. A backtest that fills every order at the bid makes shorts look better than they are, because a real short pays the ask on exit. `PaperBrokerAdapter` now takes a constant `spread` in price units. A MARKET BUY, which is a long entry or a short cover, fills at bid + spread. A SHORT's SL and TP trigger when the ask high or ask low (bar + spread) reaches the level. The long side, limit fills and the synthetic exit price are unchanged. The default `0.0` leaves every existing result identical. `POST /api/v1/backtest/run` accepts an optional `spread`; no route file changed.

In prod, a deep backfill loaded about 129,600 1m bars and 17,520 1h bars per Exness symbol. Six backtests then ran with each symbol's median spread from the spike journal: `hitnrun2` on 1m over 30 days and `engulfing` on 1h over 365 days, for XAUUSD, EURUSD and BTCUSD. All six finished with trades (48 to 215 each). Results: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/exness-backtest-results.md`.

---

## Decisions Recorded

- The finished-run `config_snapshot` now stores `spread`. The plan saved it only in the `started` record, and the record written at the end overwrote that. A stored run must say which spread produced it.
- The live paper broker stays without a spread, by plan decision. The paper week validates data, calendar and quotes, not P&L.
- The release fast-forwarded `master` with the coordinator's approval. This also deployed Phase 07's Exness broker code, with live trading still off.

---

## Lessons

- Open shorts are still marked to the bid close, so their unrealized equity and max drawdown are overstated by `spread × quantity` while open. Realized P&L is correct. Read short-heavy drawdowns with that in mind.
- A 90-day 1m Exness backfill takes 12 to 13 minutes at half the request rate. That is more than a 10-minute foreground command allows, so run it as a background job.
- In a shell `while read` loop, `ssh` reads the loop's stdin and ends the loop after one pass. Use `ssh -n`.
