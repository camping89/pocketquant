---
title: "Exness go-live with real money"
description: "Close the remaining go-live blockers on develop (admin auth, broker per subscription, one Exness adapter per process, access-point re-resolve), ship with live trading off, then run gated live minimum-lot round trips, a short observation and the 2026-11-02 DST check before declaring Exness live."
status: pending
priority: P1
effort: 1.5d code + calendar to 2026-11-02
branch: develop
tags: [exness, go-live, auth, broker, live-trading]
blockedBy: []
blocks: []
created: 2026-10-19
---

# Exness go-live

## Overview
The Exness broker exists and is switched off (`EXNESS_LIVE_TRADING`, `core/config.py:121`). This plan closes the remaining go-live blockers with the smallest change each, ships them with live trading still off, and then turns on real money in user-gated steps. Sources: `D:/w/_me/algotrading/plans/reports/kongming-261019-1957-exness-session-wrap-up-advice.md` §2–§4 and "Out of scope: go-live plan" in `plans/261009-0858-exness-venue-lean-sync-refactor/plan.md`.

The flag must be true for any live order, because `ExnessClient.call` refuses `openPosition`/`closePosition` while it is false (`core/infra/exness/exness_client.py:265-266`). The round trip in Phase 05 therefore turns the flag on. In this plan, "go live" (Phase 06) means that Exness subscriptions run unattended after the round trip, the observation and the DST check have passed. D4 covers whether the flag stays on between those steps.

## Prerequisites (not planned here)
- **E1: adapter races B1–B3 fixed.** The fix is in progress on branch `fix/exness-broker-races` in `D:/w/_me/algotrading/pq-broker-fix` and must be merged to `develop` with its replay test before Phase 04. This plan never edits `core/infra/brokers/exness/exness_broker_adapter.py` or its tests, so it cannot conflict with that branch.
- **E2: paper validation closed in prod.** Use kongming §3's schedule; its last check is Mon 2026-10-26: `CB==0`, for `XAUUSD:EXNESS` and `EURUSD:EXNESS` misaligned 0 and every gap venue-empty (C3 `PASS`; a `FAIL` gets one `integrity/repair` and a re-run, still `FAIL` fails), `sync_1m` p95 < 60 s, and both paper subscriptions running.

## Phases
| # | Phase | Effort | Depends on | Status |
|---|---|---|---|---|
| 01 | [Admin-token auth on every mutation route (B5)](./phase-01-admin-token-auth.md) | 0.5d | — | Pending |
| 02 | [Broker per subscription, one Exness adapter per process (B6, B9)](./phase-02-subscription-broker-selection.md) | 0.5d | — | Pending |
| 03 | [Re-resolve the access point on transport failure or 421 (B8)](./phase-03-access-point-re-resolve.md) | 2h | — | Pending |
| 04 | [Ship with live off; set `ADMIN_TOKEN` and the loss cap (B7)](./phase-04-ship-with-live-off.md) | 2h + CI | 01–03, E1, E2, D1, D2, D5 | Pending |
| 05 | [Live minimum-lot round trip per strategy](./phase-05-live-round-trip.md) | ~2h attention, 1–5d calendar | 04, D3, D4 | Pending |
| 06 | [Live observation, DST check, go-live](./phase-06-observation-dst-go-live.md) | ~1h attention, to ≥ 2026-11-02 | 05 | Pending |

## Dependencies
- Phases 01–03 are code on `develop` in `D:/w/_me/algotrading/pq-develop`. Each one ships with `git push origin develop`, which runs tests and does not deploy. Their files do not overlap except `docs/deployment.md` (01 and 03), so run them in order 01 → 02 → 03.
- Phase 04 contains the plan's only code push to `master`, and a push to `master` deploys prod (`docs/deployment.md`). That push also carries E1.
- Phases 05 and 06 change no code. They consist of prod config changes, prod API calls and observation.

## Blocker map
| Id | Blocker | Where it is closed |
|---|---|---|
| B4 | Account size versus `max_exposure_percent`: one minimum lot needs about 41.8k / 11.2k / 8.3k USD at the default 10% (XAUUSD / EURUSD / BTCUSD; spike prices, `docs/journals/2026-10-13-exness-api-spike.md:80`), or about 4.2k / 1.1k / 0.83k at 100% | User decision D1 |
| B5 | `verify_admin_token` guards 4 of 17 mutation routes and is skipped when the token is unset; prod has `ENVIRONMENT=production` and no `ADMIN_TOKEN` | Phase 01, Phase 04 |
| B6 | No way to choose `exness`: `StrategyConfig.broker` defaults to `"paper"` (`core/domain/strategy/value_objects.py:84`), and reconcile never sets it (`engine/live/strategy_reconcile_app_service.py:167-173`). `Settings.default_broker` (`core/config.py:135`) has no reader in `src`, and `BrokerFactory.get_available_types` (`core/infra/brokers/broker_factory.py:103-105`) has only a test caller. Both are dead code and are deleted under the CLAUDE.md rule | Phase 02 |
| B7 | `EXNESS_DAILY_LOSS_CAP` is unset in prod, so every order is rejected (`exness_broker_adapter.py:239-240`). The minimum-lot rule is already in code: with `EXNESS_MAX_LOTS` unset, the cap is `volume_min` (`core/infra/exness/exness_mappers.py:93`) | Phase 04 (config only) |
| B8 | The access point is resolved once per process and never cleared (`exness_client.py:238-246`) | Phase 03 |
| B9 | **New, found while planning.** The broker pool is keyed by `(broker_type, contract_spec)` (`engine/strategy/strategy_app_service.py:465`), and the seeded Exness symbols have different specs (`scripts/seed_exness_symbols.py:57,63,69`), so each instrument gets its own `ExnessBrokerAdapter` with its own events WS. Every instance maps every account position (`exness_broker_adapter.py:405-446`), so one venue close is published once per instance (`:488-490`, duplicate `OrderFilledEvent` and `TradeClosedEvent`), and an open placed by one instance is flagged `exness.unknown_request_fill` by the others, which blocks that instrument (`:482-487`) | Phase 02 |

## User decisions
Each decision is needed before the phase named in the "Before" column. The plan does not pick an option.

| Id | Before | Question | Options |
|---|---|---|---|
| D1 (B4) | P04 | How does one minimum lot fit under the sizer? The sizer caps notional at `balance × max_exposure_percent` (`core/domain/risk/services/position_calculator_domain_service.py:43-45`). Live subscriptions always use the default `RiskConfig()` at 10% (`strategy_reconcile_app_service.py:167-173`), and the floor scales with price | **A** Fund the account above the 10% floor for each live instrument; no code. **B** Add an optional per-subscription `max_exposure_percent` on the same create body as `broker` (Phase 02, conditional step 7), which brings the floor to about 4.2k / 1.1k / 0.83k at 1.0. Size stays capped at one minimum lot either way. **C** Go live first only on the cheapest instrument (BTCUSD, then EURUSD), with A or B; the paper-validated pairs are XAUUSD for `hitnrun2` and EURUSD for `engulfing`. **D** Raise the global default `MAX_EXPOSURE_PERCENT`; this also changes every paper subscription and backtest |
| D2 (B7) | P04 | `EXNESS_DAILY_LOSS_CAP` value, in account currency (USD) | Any positive number. The cap counts realized profit of `close/swap_fee/admin_fee/dividend` deals minus every deal's commission, and its day starts at UTC midnight (07:00 Bangkok), not at the Exness rollover (`exness_broker_adapter.py:261-272`). A cap below one minimum-lot stop-loss loss halts opens for the rest of the UTC day after the first full loss. Exits are never blocked |
| D3 | P05 | How is "a live round trip per strategy" produced? | **A** Each strategy's first natural live trade is the round trip; no code, but the timing is not controlled (`engulfing` on 1h may take days; the paper run's trade count is the estimate). **B** A one-off operator script opens one minimum lot with SL and closes it through `ExnessBrokerAdapter`. It is new code in `scripts/`, it does not exercise the strategy path, and it must run while no `exness` subscription exists, or the app's own adapter flags the fill as unknown and blocks that instrument |
| D4 | P05 | Flag between the round trip and go-live | **A** The flag stays true; `exness` subscriptions are stopped between steps (`desired_state=stopped`; the adapter stays connected, so venue SL/TP closes are still recorded). **B** The flag goes back to false. Every `exness` subscription then fails to load every 5 s (`reconcile.load_failed` at ERROR, `strategy_reconcile_app_service.py:138-181`, `reconcile_interval_seconds` 5.0) unless it is deleted, so delete them (deleting keeps their orders, positions and trades rows; `strategy_command_service.py:99-107`) and recreate them later |
| D5 | P04 | The SPA is served on `WEB_PORT=80` (prod `.env`); no TLS terminator is visible in `deploy/compose.prod.yml` | **A** Accept that the token travels in clear for now. **B** Put TLS in front before go-live; that is a topology change and is outside this plan. If TLS already terminates outside the VPS, D5 does not apply |

## Acceptance criteria
- AC1: In prod, every POST/PUT/PATCH/DELETE under `/api/v1` returns 401 without a valid `X-Admin-Token`; every GET, including both SSE streams, works without it; and with the token unset under `ENVIRONMENT=production`, mutations return 503. The SPA's start, stop, add, delete, backtest, verdict, rename and integrity actions work after the token is entered once.
- AC2: `POST /api/v1/strategies/{code}/subscriptions` accepts `"broker": "exness"` only while `EXNESS_LIVE_TRADING` is true (otherwise 400 `BROKER_DISABLED`). `GET /api/v1/subscriptions/` shows `broker` for every subscription, and existing subscriptions read as `paper`.
- AC3: Two `exness` subscriptions on different instruments share one `ExnessBrokerAdapter` (unit test); in prod, `exness.broker_connected` appears once per process start.
- AC4: After a 421 or a transport failure, the next Exness call resolves the access point again (unit test).
- AC5: Prod runs with `ADMIN_TOKEN` and `EXNESS_DAILY_LOSS_CAP` set and `EXNESS_MAX_LOTS` unset, and the CI verdict reports `0 failures`.
- AC6: For each live strategy, one minimum-lot entry with SL and its exit are recorded once each in `orders`, `positions` and `trades`. The account balance delta equals what `_realized_today()` computes for those deals within 0.01, which settles whether a close deal's `profit` is gross of commission.
- AC7: On Mon 2026-11-02 the DST check passes (Phase 06), and the user declares go-live.

## User preconditions
- U1: The account is funded per D1, and the user states the balance before Phase 05.
- U2: The user approves each stop-and-ask gate below at the time it is reached. An approval given in advance for a later gate does not count.

## Stop-and-ask gates
Stop and ask the user before any of these:
- editing `pocketquant-config` (`ADMIN_TOKEN`, `EXNESS_DAILY_LOSS_CAP`, `EXNESS_LIVE_TRADING`) or redeploying prod;
- pushing to `master`;
- setting `EXNESS_LIVE_TRADING=true`, setting `EXNESS_MAX_LOTS`, or raising the loss cap;
- creating, starting or deleting an `exness` subscription, deleting a paper validation subscription, or placing any live order (including a D3-B script run);
- holding open `exness` positions over a weekend (Phase 06 step 2);
- declaring go-live.

Stop and report (no improvised fix) when:
- AC6's commission equality fails;
- any of `exness.position_unmapped`, `exness.unknown_request_fill`, `exness.operation_unresolved`, `exness.position_missing_close_deal` or `exness.event_handler_failed` appears;
- a `trades` row is duplicated or missing against the venue's deals;
- the ratchet would need a higher ceiling;
- a test failure stays unexplained;
- a change would touch `exness_broker_adapter.py` (E1 owns it).

## Test matrix
| Level | Covers | Where |
|---|---|---|
| Unit | method-aware guard and fail-closed branch; SPA client header and 401 retry; subscription `broker` round trip and the old-document default; create-time flag check; one pooled adapter for non-paper types; access-point reset on 421 and transport failure | `tests/app_test/integration/test_admin_token_guard.py`, `web/src/api/api-client.test.ts`, `tests/engine_test/test_strategy_service.py`, `tests/engine_test/test_subscription_broker_selection.py`, `tests/core_test/infra/exness/test_exness_client.py` |
| Integration | every mutation route carries the guard; create with `broker`; existing API tests stay green under `ENVIRONMENT=development` | `tests/app_test/integration/` |
| End-to-end (prod) | 401/503/GET checks; live round trip; commission equality; observation; DST check | Phases 04–06 |

## Rollback
- Code (01–03): revert the commit on `develop` and fast-forward it to `master` (gated). Before reverting Phase 02 in prod, stop every `exness` subscription and flatten its positions, because the old code reads every subscription as `paper` and would stop tracking the venue position.
- Live (05–06), from softest to hardest:
  1. `POST /subscriptions/{id}/stop` with the token. The strategy stops signalling, and the adapter stays connected, so a venue SL/TP close is still recorded.
  2. Close the position in the Exness terminal. The adapter records the close as a broker-side close (`exness_broker_adapter.py:488-505`).
  3. Set `EXNESS_LIVE_TRADING=false` and redeploy. Order calls are refused, with the D4-B side effects.

## Failure protocol
If a Validation step misses its pass condition, stop the phase. Spawn `kongming` with the phase, the steps run, the exact command and output, and the failed condition. Apply its advice and re-run. If `kongming` cannot be spawned, stop and report to the user.

## Unresolved questions
- Should the SPA get a broker selector? This plan keeps selection API-only (curl with the token), and the subscriptions list only gains the `broker` field.
- The SL is not part of the snapshot position shape the adapter reads (`{position_id, direction, instrument, volume, open_price}`, per phase-07 of the previous plan). Phase 05 confirms the SL in the Exness terminal, which is a user step.
- Kongming counted 5 guarded and 12 open mutation routes. A re-count on `2613dc9` finds 4 guarded and 13 open: `routes/market_data.py:65,79,93,112,123`, `routes/strategy.py:56,69,93,102,141` and `routes/backtest.py:52,83,94`. Phase 01 guards all of them, so the difference does not change the work.
