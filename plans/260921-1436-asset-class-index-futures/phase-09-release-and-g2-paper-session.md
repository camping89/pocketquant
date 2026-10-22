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
User choices (2026-10-22): `engulfing` on 15m, futures paper balance 200,000 USD, leverage 25
(raised from 20 at release: at ES 7,719.75 leverage 20 caps at 1.04 contracts, and above
8,000 every signal sizes to zero; 25 caps at 1.30 and zeroes only above ~10,000).

## Constraints

- Ops recipe, credential rules and `gh` token rule as in Phase 10.
- Release is a fast-forward `git push origin develop:master` (it deploys). Confirm the commit
  range with the user immediately before pushing.
- Prod values change only in `../pocketquant-config/vps/default/.env`, pushed there before the
  release, so the deploy materializes them.
- No further deploy until both measurements finish; a deploy restarts the 24-run count.

## Tasks

### Task 1 — Config and release

- Add `PAPER_FUTURES_INITIAL_BALANCE=200000` and `PAPER_FUTURES_LEVERAGE=25` to the prod
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

## Progress

- 2026-10-22 Task 1 done: `pocketquant-config` 27c423a5 adds the two keys; `develop:master`
  fast-forward b30ea30c..1c72ddf0, CI run 39805449134 green, container healthy,
  `StartedAt` 2026-10-22T15:34:21Z. In-container `Settings`: futures balance 200000.0,
  leverage 25.0; `paper_initial_balance` stays 100000.0 on prod.
- 2026-10-22 Task 2 done: subscription `01a16440-fdc8-745c-8a9e-7c2b6223de0d` (engulfing, 15m,
  paper) created 15:35:43Z, started, `actual_state=running`.
- Task 3 pending. Row 11: 24 runs from 16:00Z, measurable after 2026-10-23T15:05Z. G2: the
  session 2026-10-22T22:00Z to 2026-10-23T21:00Z, measurable after 21:05Z. Do not deploy before.

- 2026-10-22 23:45 +07, moving `sync_verify_cascade` off :00 checked (7 days of `job_history`,
  read-only, no change made). The :00 `sync_1m` finishes its futures 13-20 s later (ES 17.0 s,
  NQ 26.3 s, YM 17.9 s vs 3.8 / 6.4 / 8.8 s at other minutes), because the verify holds the
  scraper lock. Zero-insert syncs are fewer at :00 and more at :01 (ES 8.2 % vs 3.5 %, NQ 5.0 %
  vs 1.1 %, YM 18 % vs 11.4 %, n of about 100 per symbol at :01): the bar shifts one minute, it
  is not lost. Separate finding: every day at 04:00Z, when `sync_integrity` also starts, the
  verify takes 147-284 s and `sync_1m` runs once in six minutes for every symbol, crypto
  included. Which job holds it is not yet traced.

## Success criteria

- Row 11 has 24 runs with ES `divergence_count=0` in every comparing run, or a diagnosed miss.
- Row 13 has at least one closed paper ES trade whose USD PnL matches the formula, or a
  recorded no-trade session.

## Risks and rollback

- The release deploys prod. Rollback: push the previous `master` sha back
  (`git push --force-with-lease origin <prev>:master` after confirmation) and remove the two
  `.env` keys.
- The paper subscription trades no real money. Remove it with the subscription DELETE route
  once G2 is recorded (user decision 2026-10-22: delete).
