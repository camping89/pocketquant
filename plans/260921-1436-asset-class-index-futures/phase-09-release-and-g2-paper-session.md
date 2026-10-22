---
phase: 9
title: "Release, Re-measure Verify and Run the G2 Paper Session"
status: pending
priority: P2
effort: "2d elapsed, 1h active"
dependencies: [8]
---

## Context

Phase 8 lands on `develop`. This phase releases it to prod, sets the futures paper values,
starts one paper ES subscription, and measures rows 11 and 13 of `completion-report.md`.
User choices (2026-10-22): `engulfing` on 15m, futures paper balance 200,000 USD, leverage 20.

## Constraints

- Ops recipe, credential rules and `gh` token rule as in Phase 10.
- Release is a fast-forward `git push origin develop:master` (it deploys). Confirm the commit
  range with the user immediately before pushing.
- Prod values change only in `../pocketquant-config/vps/default/.env`, pushed there before the
  release, so the deploy materializes them.
- No further deploy until both measurements finish; a deploy restarts the 24-run count.

## Tasks

### Task 1 — Config and release

- Add `PAPER_FUTURES_INITIAL_BALANCE=200000` and `PAPER_FUTURES_LEVERAGE=20` to the prod
  `.env`; commit and push `pocketquant-config`. Print key names only.
- [ASK] release range, then `git push ... develop:master`; watch CI to green; confirm the
  container is healthy and record its `StartedAt`.

### Task 2 — Paper ES subscription

- `POST /api/v1/strategies/engulfing/subscriptions` for `ES1!:TRADINGVIEW`, `15m`, broker
  `paper` (body per `app/routes/strategy.py`). Record the subscription id.
- Confirm the reconcile loaded it and that its first signal, if any, sizes at least one
  contract (no `zero_position_size` for that id).

### Task 3 — Measure

- Row 11: from `StartedAt`, 24 consecutive hourly runs; pass is `divergence_count=0` for ES in
  every run that compared bars. Record `symbol_failed` (vendor "no series") runs separately;
  they compare nothing and do not break the run of zeros.
- Row 13 (G2): over one full CME session (22:00Z open to the 21:00Z close), record the trades
  the subscription closed and check each `pnl == (exit - entry) x 50 x contracts` (sign by
  side) less commission, in USD. If the session closes no trade, record that and extend by one
  session once.

## Success criteria

- Row 11 has 24 runs with ES `divergence_count=0` in every comparing run, or a diagnosed miss.
- Row 13 has at least one closed paper ES trade whose USD PnL matches the formula, or a
  recorded no-trade session.

## Risks and rollback

- The release deploys prod. Rollback: push the previous `master` sha back
  (`git push --force-with-lease origin <prev>:master` after confirmation) and remove the two
  `.env` keys.
- The paper subscription trades no real money. Remove it with the subscription DELETE route
  once G2 is recorded, unless the user wants it kept.
