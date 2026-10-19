---
phase: 5
title: "Live minimum-lot round trip per strategy"
status: pending
priority: P1
effort: ~2h attention, 1-5d calendar
dependencies: [4]
---

# Phase 05: Live minimum-lot round trip per strategy

## Context
- Strategies and pairs come from the paper validation: `hitnrun2` on `XAUUSD:EXNESS` 1m and `engulfing` on `EURUSD:EXNESS` 1h, unless D1-C changes the instrument. Both strategies attach an SL (`hitnrun2_strategy_service.py:151`, `engulfing_strategy_service.py:170`).
- With `EXNESS_MAX_LOTS` unset, every order is exactly `volume_min` (`exness_mappers.py:93`). Below the D1 floor no order is created, and `exness.order_rejected_presubmit reason=below_min_lot` is logged.
- `remove_symbol` deletes only the subscription document; its orders, positions and trades rows stay (`strategy_command_service.py:99-107`).
- The loss-cap arithmetic (`_realized_today`, `exness_broker_adapter.py:261-272`) assumes `profit.amount` excludes commission. Every test uses synthetic `close` deals, so the sign and netting on a real close deal are unverified (kongming §2 "Process preconditions").
- Entry conditions: Phase 04 is done, U1 holds, and D3 and D4 are answered.

## Files
- No repo file. Outside the repo: `pocketquant-config/vps/default/.env` (gated). Only if D3 = B: `scripts/exness_round_trip.py` plus a test in `tests/scripts/`, shipped to `develop`/`master` through the Phase 04 gates.

## Steps
1. Check the floor. From the container, run a read-only snippet with `ExnessClient(get_settings())`: `getTradingStateSnapshot` gives `account_state.balance`, and `conditions(<instrument>)` gives `volume_min` and `contract_size`. Compute `floor = volume_min × contract_size × current price / max_exposure_percent` per instrument. Pass: balance > floor for every live instrument (margin buffer per D1).
2. **[Stop-and-ask]** Set `EXNESS_LIVE_TRADING=true` in `pocketquant-config` and redeploy with `gh workflow run cicd.yml --ref master`. Verify that the settings one-liner from Phase 04 prints `True` first. No `exness` subscription exists yet, so no adapter is built and no order can be sent. While the flag is true, the deep backfill script refuses to run (exit 3; `docs/deployment.md:239`).
3. Baseline: record `account_state.balance` and the deals since UTC midnight (`getDealsHistory`, `from=<UTC midnight ISO>`, `limit=200`), read-only.
4. **[Stop-and-ask]** For each strategy:
   - stop the paper validation subscription on the same triple, then `DELETE /api/v1/subscriptions/{id}` with the token (its rows stay);
   - `POST /api/v1/strategies/{code}/subscriptions` with `{"symbol": ..., "interval": ..., "broker": "exness"}`, then `POST /api/v1/subscriptions/{id}/start`;
   - check `GET /api/v1/subscriptions/` shows `broker: "exness"` and `actual_state: "running"` within 30 s;
   - check the logs hold exactly one `exness.broker_connected` and one `exness.snapshot_reconciled` (AC3).
   
   With D3 = B, run the script (gated) before any `exness` subscription exists, then do this step.
5. Wait for each strategy's entry and exit (D3 = A). Per round trip, check:
   - log `exness.order_submitted` with `volume == volume_min`, then `exness.order_filled`;
   - one `orders` row FILLED with `sl_price` set;
   - one `positions` row opened and later closed;
   - the SL is visible on the position in the Exness terminal (user);
   - exactly one `trades` row for the subscription with `pnl` and `commission` set.
6. Commission check (AC6): read the deals and the balance again. With `P = Σ profit.amount` (over close, swap_fee, admin_fee and dividend) and `C = Σ |commission|` (every non-balance deal) since the baseline:
   - if `balance_after − balance_before == P − C` (±0.01), profit is gross of commission and the code is right;
   - if it equals `P` alone, the cap double-counts commission. **Stop and report.** The fix belongs to the adapter, after E1.
   - Record the numbers in `reports/round-trip.md`.
7. Apply D4: under A, stop the `exness` subscriptions (flag stays true); under B, flip the flag (gated) and delete the subscriptions. Skip this step when going straight into the Phase 06 observation.

## Validation
- For each strategy: one FILLED entry and one exit at `volume_min` with SL; one `trades` row; no duplicate rows.
- The equality in step 6 holds.
- None of these events appear: `exness.position_unmapped`, `exness.unknown_request_fill`, `exness.operation_unresolved`, `exness.position_missing_close_deal`, `exness.event_handler_failed`.

## Risk
- The venue rejects for margin (`TRADING_RULE_INSUFFICIENT_MARGIN` → CANCELLED, and the strategy is told) (M/L). Fund per D1.
- A gap or slippage through the SL loses more than the planned risk (M/M). Size is one minimum lot, and the daily cap stops new opens.
- No signal for days under D3 = A (H/L). Use the paper trade frequency as the estimate, or switch to D3 = B (gated).
- A deploy mid-trade restarts the adapter (L/M). Restart reconciliation is tested (previous plan, P07 T7.6 step 13); avoid `master` pushes while a position is open.

## Rollback
Use the soft-to-hard order in `plan.md` "Rollback": stop the subscription, close the position in the Exness terminal, then set the flag to false and redeploy.
