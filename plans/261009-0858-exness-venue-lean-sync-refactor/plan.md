---
title: "Exness venue behind existing ports + lean sync refactor"
description: "On develop: add Exness market data and quotes through suffix routing (XAUUSD:EXNESS), build the Exness broker switched off, and validate on paper, after collapsing DI, routes and wrappers and adding a code-metric ratchet."
status: pending
priority: P1
effort: 7w
branch: develop
tags: [exness, market-data, suffix-routing, refactor, broker, standards]
blockedBy: []
blocks: []
created: 2026-10-09
---

# Exness venue + lean sync refactor

<!-- Updated: Validation Session 1 - broker off, suffix routing, ratchet, paper validation -->
## Overview
The ports `IDataProviderPort`, `IRealtimeQuoteProviderPort`, `IBrokerPort` and `IStrategyService` stay the seams. A read-only Exness spike runs first, entirely in `scripts/`. The composite-symbol suffix names the data provider (`BTCUSDT:BINANCE`, `XAUUSD:EXNESS`, `ES1!:TRADINGVIEW`), and develop's `RoutingDataProviderAdapter` and `RoutingRealtimeQuoteAdapter` route by it; develop's sync jobs, trading calendar port and data lag stay. DI, routes and scalar wrappers are collapsed, the coding standard is rewritten, and the code metric becomes a CI ratchet. Exness then plugs in as one more suffix-routed provider for data and quotes. The broker stays a per-strategy setting (`config.broker`). The Exness broker is built and tested with recorded fixtures but stays off behind `EXNESS_LIVE_TRADING=false`; no live order is placed. Validation uses a `PaperBrokerAdapter` spread, backtests and a paper week across a weekend. Binance, OKX, the paper broker, `hitnrun2` and `engulfing` stay. MT5 is only documented, nothing is built for MCP, and the deployment topology does not change.

## Goals
- G1: Exness is a venue next to Binance and OKX for market data and quotes, with the same strategies, risk checks and position tracking and no SPA change. The Exness broker is built and tested but switched off until a later go-live plan.
- G2: Adding a provider means one adapter package, one `DATA_PROVIDER_DEFAULTS` entry, one entry in each DI router (`app/di/adapters.py`), a calendar registered in `TradingCalendarFactory`, and seeded `symbols`. Routing is strictly by the data-provider suffix; an unknown suffix raises `UnknownDataProviderError`.
- G3: The team follows a lean standard enforced by ruff, 8 import-linter contracts and a code-metric ratchet (`[tool.code-metrics]`).

## Phases
Phases 01–05 first ran on a July 2026 snapshot of the code (`backup/master-20261012`). `develop` has a different market-data design (provider routing, trading calendar port), so Phases 02–05 were redone on develop as integration steps 1–4 and Phases 06–09 were rewritten for develop (`reports/revise-phases-06-09-for-develop.md`).

| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 01 | [Exness read-only spike](./phase-01-exness-read-only-spike.md) | 2d | Completed 2026-10-13 (A-v feasible; fixtures and journal on develop) |
| 02 | [Characterization tests and metric baseline](./phase-02-characterization-and-metric-baseline.md) | 2d | Done on develop (integration steps 2, 4) |
| 03 | [Sync policy registry, shared runner and suffix routing](./phase-03-sync-policy-shared-runner.md) | 5d | Superseded: suffix routing via resolver swap (integration step 2) |
| 04 | [Collapse DI, routes and scalar wrappers](./phase-04-collapse-di-routes-wrappers.md) | 3d | Done on develop (integration step 3) |
| 05 | [Lean coding standard and metric ratchet](./phase-05-lean-standard-and-metric-gate.md) | 2d | Done on develop (integration step 4) |
| 06 | [Exness market data and quotes](./phase-06-exness-market-data-and-policy.md) | 7d | Completed 2026-10-19 (prod on master `7c3ca77`, D1 holds) |
| 07 | [Exness broker behind the live-trading switch (off)](./phase-07-exness-broker-off-by-default.md) | 6d | Completed 2026-10-19 on develop (live trading off; go-live blockers listed in the phase) |
| 08 | [Validation: spread, backtests, paper week](./phase-08-validation-spread-backtests-paper-week.md) | 7d + weekend | Pending |
| 09 | [Architecture, deployment, standard and MT5 docs](./phase-09-docs-architecture-deployment-mt5.md) | 1d | Pending |

## Dependencies
- Phases run strictly in order, 01 → 09; no two phases run in parallel, so no file has two concurrent owners.
- Phase 01 waits on U1 and U2. OKX had no market data to migrate (`reports/user-preconditions.md`). Phase 08's paper week needs the user's approval and a no-deploy week.
- Work happens on `develop-sync` in `D:/w/_me/algotrading/pq-develop` and ships with `git push origin develop-sync:develop`. A push to `develop` runs tests only; `.github/workflows/cicd.yml` builds and deploys to prod only from `master` (branch model in `docs/deployment.md`). Deploys are approved.

<!-- Updated: Validation Session 1 - D2, D4, D6 and the week metric rewritten -->
## Success criteria (D1–D7)
- D1: `POST /api/v1/market-data/sync` with `{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"rest_backfill"}` returns `total_bars >= 1000`. The SSE bars stream for `XAUUSD%3AEXNESS` emits `"is_in_progress": true` within 60 s during market hours, the quote stream emits `"bid"`, and `BTCUSDT:BINANCE` keeps syncing.
- D2: `ExnessBrokerAdapter` passes fixture-based tests for: open with SL and rejection without SL; a clamped quantity normalized before order creation so fill → `OrderAppService` → `PositionAppService` opens a position; async fill and reject; reconciliation after a missed fill and after a restart; a daily loss cap computed from the recorded deals fixture. With `EXNESS_LIVE_TRADING=false` the app boots, `BrokerFactory` refuses `exness`, and no Exness order endpoint is ever called (mock-transport assertion plus grep, Phase 07 T7.9).
- D3: `hitnrun2` and `engulfing` backtests on Exness bars reach `finished` in `backtest_runs` with a non-empty trades list, with the spread modelled in `PaperBrokerAdapter` (ask = bid + spread).
- D4: `app/di` has 3 provider modules (`infrastructure.py`, `adapters.py`, `services.py`), and market-data routes live in 2 files (`routes/market_data.py`, `routes/market_data_quotes.py`). `scripts/code_metrics.py --ratchet` passes against `[tool.code-metrics]`; when necessary new code exceeds the ceiling, the ceiling is raised to the measured values in its own commit and reported, never met by padding code.
- D5: `docs/code-standards.md` is rewritten with no stale status claims, and `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`.
- D6: Binance, OKX and paper-broker tests keep passing with no OKX code edits, and the 4 existing `BrokerFactory(event_bus)` call sites stay unchanged. `just test`, ruff, pyright, lint-imports and the ratchet are green, and every CI deploy's `11-verify.sh` verdict reports `0 failures`.
- D7: `docs/system-architecture.md` shows the Exness adapters, suffix routing and MT5 as a future provider, and the "Composite Symbol Format" section of `docs/code-standards.md` lists the real add-a-provider touchpoints.
- Paper week: both strategies run on the paper broker on `:EXNESS` symbols for 7 days across a weekend close and reopen, with 0 `exness_ws.circuit_breaker_open` in log windows of proven coverage and 0 missing or misaligned bars from `integrity/check` for `XAUUSD:EXNESS` and `EURUSD:EXNESS`.

## Test matrix
| Level | Covers | Where |
|---|---|---|
| Unit | spike signer and redaction, mappers, lot math, session calendar, provider registration and suffix routing, client gate/budget/transport retry/429 retry (data) and rejection (orders), broker state machine and recovery, metric script, seed and backfill scripts | `tests/core_test/infra/exness/`, `tests/engine_test/`, `tests/scripts/` |
| Characterization | suffix routing swap, sync jobs, cascade, `BrokerFactory`, request-schema diff | `tests/app_test/integration/`, `tests/core_test/` |
| Integration | runner on real Mongo/Redis (testcontainers), clamp → fill → position, async fill wiring, live-off boot | `tests/app_test/integration/`, `tests/engine_test/` |
| End-to-end | prod sync, SSE and quotes, backtests, paper week | Phases 06 and 08 (VPS) |

<!-- Updated: Validation Session 1 - U2 rewritten; U3 moved to the go-live plan -->
## User preconditions (the plan gates on these and never performs them)
- U1: The Developer Portal link inside the Exness Personal Area resolves to `exness-api.com`.
- U2: A scoped API key exists (one account; no IP allowlist, by user decision). `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` and `EXNESS_SECRET_KEY` (the 128-hex secret exactly as Key Management shows it, never PEM) are in `pocketquant-config/vps/default/.env`, committed and pushed to `pocketquant-config` master. The user states the API host, which becomes the URL allowlist.
- Stop and ask the user if: a change would enable live Exness trading, set `EXNESS_LIVE_TRADING=true` or send an Exness order request; the `:OKX` → `:BINANCE` prod data migration would run without a backup and the user's approval; a change would delete Binance or OKX code; the deployment topology would change; Exness limits make policy A-v infeasible; a test failure stays unexplained; U1 fails.

<!-- Updated: Validation Session 1 - new section per decision 3 -->
## Out of scope: go-live plan
A later plan owns going live. Its preconditions are: admin-token auth on every mutation route (fail-closed in production, with the SPA sending the token); a broker selection mechanism; the U3 risk cap (`EXNESS_DAILY_LOSS_CAP` set, `EXNESS_MAX_LOTS` unset so orders use the minimum lot); a live minimum-lot round trip per strategy with SL; a live-week observation; and only then `EXNESS_LIVE_TRADING=true`. It also owns persistence and refresh of the per-account access point (Redis cache, scheduled refresh, re-resolve on connect failure or 421) once Exness publishes the access-point contract.

## Validation Log
### Session 1 (2026-10-10)
- Questions asked: 6. Decisions are binding and recorded in `reports/validation-decisions.md`.
- Decision 1: apply the red team in full (15 findings plus the Medium fixes); live-money fixes apply to the broker code that is built; no live order.
- Decision 2: the metric gate is a ratchet frozen after Phase 05 and re-measured after the Exness phases; the ≤30% / ≤20 targets are an aspiration only.
- Decision 3: build `ExnessBroker` with recorded-fixture tests behind `EXNESS_LIVE_TRADING` (default false); no broker field or API change; auth, selection, U3 and live steps move to the go-live plan; D2 rewritten.
- Decision 4: route strictly by exchange suffix through `policy_for`, with each policy carrying its providers; no router module, no fallback, one split helper.
- Decision 5: correct `:OKX` market-data symbols to `:BINANCE` through a backed-up, user-approved migration; OKX stays broker-only with no data policy.
- Verification results: red-team fact checks found Security 13 verified / 3 failed (`config.py:98`, the deals shape, the admin-token claim in the original symbol-tracking step), Assumptions 2 failed citations (`config.py:98`, `paper_broker.py:671`), Failure modes 6 code behaviours confirmed. In this session every new path, symbol and line citation (over 40) and 12 spec facts were re-grepped against the repo and OpenAPI 1.0.2; none is left `[UNVERIFIED]`. `ak plan validate` prints `[OK]`.

### Session 1 follow-up (2026-10-10)
- Async fill wiring is Exness only: `IBroker.fills_async` defaults to `False` and only `ExnessBroker` sets it, so PaperBroker and OKX stay byte-identical with no OKX test change (P07 T7.2, T7.3, T7.4; P09 T9.1).
- `hitnrun2` resets on every path where a signal never fills (no broker, risk rejection, zero size, below the broker minimum, REJECTED, CANCELLED, and an exception after the signal), with paper tests for the risk-rejection and zero-size paths (P07 T7.3).
- A 429 is never retried automatically, for any call. Orders become REJECTED and block new orders until a snapshot reconcile; data calls surface the error and the next scheduled run retries. `Retry-After` is not used. Transport-error retries with the same idempotency key stay (P06 T6.6, T6.7, T6.10, T6.11 and Risks; P07 T7.4, T7.6). Superseded by the 2026-10-13 429 decision below.
- The daily loss cap also counts `dividend` deals and every deal's `commission` (as a cost), still excluding `balance` deposits and withdrawals; the deals-fixture expectations are updated (P07 T7.4, T7.6, Security; P09 T9.1).
- The 40-second Exness `poll_time_cap_s` stays (P06 T6.14).

### Session 2 (2026-10-11)
- Credentials: `EXNESS_SECRET_KEY` replaces `EXNESS_PRIVATE_KEY` and holds the 128-hex secret exactly as Key Management shows it (seed then public key); `load_secret_key` checks the public half. No IP allowlist (user decision). Base URL `https://api.exness.com` (Key Management "Main").
- Access point: P01 T1.4 resolves `/v1/trading/access-point` first and records `access_point_resolved` and `ws_host`. P06 caches the per-account host in Redis, preloads it at startup, refreshes it hourly (`exness_access_point_refresh`, logs `exness.access_point_changed`), and re-resolves once on a connect failure or 421 (T6.6–T6.9, T6.15, T6.18). P09 T9.2 documents it. Superseded by Session 3: reduced to an in-memory per-process resolve.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01-exness-read-only-spike.md, phase-02-characterization-and-metric-baseline.md, phase-03-sync-policy-shared-runner.md, phase-04-collapse-di-routes-wrappers.md, phase-05-lean-standard-and-metric-gate.md, phase-06-exness-market-data-and-policy.md, phase-07-exness-broker-off-by-default.md, phase-08-validation-spread-backtests-paper-week.md, phase-09-docs-architecture-deployment-mt5.md.
- Decision deltas checked: 33 (5 decisions, 15 findings, 13 Medium fixes). Phase files renamed: 07 (`...-broker-off-by-default`) and 08 (`...-paper-week`); Phase 02 tasks renumbered after dropping the OKX test (venue baseline is now T2.6, gate T2.7).
- Terms checked: `venue_router`, `DataProviderRouter`, `QuoteProviderRouter`, `CreateSubscriptionBody.broker`, `broker":"exness"`, `0.30`, `≤ 20`/`<= 20`, `EXNESS_PRIVATE_KEY_PATH`, `/tmp/`, `/api/v1/system/jobs` (list route), `19 checks`, `config.py:98`, `paper_broker.py:671`, `T2.6`, live round trip, `exness.order_filled` live checks, `U3`, plus `fills_async`, `live_source`, `rate_budget_per_minute`, `FX_WEEKEND`, `exness_bars.py`, `metric-decision`, `--soft`, old phase file names and old Phase 01 task numbers.
- Reconciled stale references: every operative hit of those terms was rewritten or removed. Remaining hits are intentional: this log, the Red Team table and update markers; the real route `/api/v1/system/jobs/{job_id}/runs`; `T2.6` as the renumbered venue baseline; `exness.order_filled` as a broker log event exercised by tests only; `U3` and the round trip inside "Out of scope: go-live plan"; `≤20` only as the aspiration in decision 2 and the standard.
- Follow-up sweep: rechecked `non-paper`, `broker_type != "paper"`, `retry`/`retries`, `Retry-After`, `window_seconds`, `hammer`, `close/fee`, `_PNL_DEAL_TYPES`, `commission`, `dividend`, `fills_async` and `OKX now`. Remaining hits are intended: `fills_async` returns as the Exness-only flag (it supersedes the earlier removal of that term), transport retries with the same key, the `Retry-After` header used only in a test to prove it is ignored, and the new loss-cap wording.
- Unresolved contradictions: 0.

### Session 3 (2026-10-11)
- Source: advisory pass `D:/w/_me/algotrading/plans/reports/advise-261011-1046-exness-plan-open-questions.md`. Questions asked: 2 (access point scope; plan-directory commit).
- Access point (Lean): `GET /v1/trading/access-point` is absent from OpenAPI 1.0.2 and only trading calls need it, which this plan never makes. `ExnessClient` resolves it once per process, in memory, and routes `_ACCESS_POINT_OPS` (and WS when `_WS_ON_ACCESS_POINT`) to it. The Redis cache, 7-day TTL, 421 re-resolve, hourly `exness_access_point_refresh` job, startup preload, their tests and the T6.18 Redis/job check are removed; `register_sync_jobs` is not touched. Persistence and refresh move to the go-live plan (P06 Goal, T6.6–T6.9, T6.15, T6.18, Risks, Security; P09 T9.2; Out of scope).
- Plan directory is committed whole in every ship step (P02 T2.7, P03 T3.18, P04 T4.7, P05 T5.5, P06 T6.18, P07 T7.12, P08 T8.3, P09 T9.4); CI ignores `plans/**`, so no deploy is triggered. P09 T9.4 also carries the Phase 08 reports written after T8.3.
- Editorial: P01 T1.1 drops the stale "VPS IP allowlisted" wording and skips its questions when `user-preconditions.md` is already complete (it is, so cook starts at T1.2); P03 Context Links cite `entities.py:19`/`:24`; P04 T4.3 drops the stale tracked-symbols comment; P05 T5.2 names its source headings; P08 T8.4 derives the BTCUSD minimums from `EXNESS_CALENDARS["BTCUSD"]`; P08 T8.6 and Risks state that the paper week runs without spread; P06 T6.7 step 9 moved above its success criteria.

### Verification Results (Session 3)
- Claims checked: 49 (about 40 in the advisory pass, 9 in this session). Verified: 49 | Failed: 0 | Unverified: 0 plan claims. Tier: Full (9 phases).
- Verified in this session: `sync_runner.py` is created by P03 at `src/pocketquant/engine/market_data/`; `get_cache` moves to `InfrastructureProvider` in `app/di/infrastructure.py` (P04 T4.2); `docs/code-standards.md` has 17 H2 headings with `## Comment Policy` at :428, the async H3 at :583 and `## Configuration & Secrets` at :733, none containing a T5.2 forbidden string; `COMPOSITE_SYMBOL_RE` at `entities.py:19` and `COMPOSITE_SYMBOL_PATTERN` at :24; the trailing tracked-symbols comment in `routes/market_data.py`; `default_broker_config` in `app/di/execution.py:65` has no `spread`; `cicd.yml` ignores `plans/**`; `plans/` is tracked; `user-preconditions.md` holds both `confirmed` lines and the host line.
- Verified in the advisory pass: the T2.3 baseline `794 / 661 / 315 (0.4766) / 63` reproduces with the T2.2 definition at `29f2f67`; dishka 1.9.1 exposes `STRICT_VALIDATION` and `from_context`; container names, `appuser`, `COPY scripts/ scripts/`, the `11-verify.sh` verdict line, every cited route, `RunBacktestCommand`, `IRealtimeQuoteProvider.subscribe`, `BrokerFactory`, `OrderResult`, `OrderCancelledEvent`, the 14 cited test files, the `cicd.yml` and `action.yml` anchors; prod runs `DEFAULT_BROKER=paper`, so the `:OKX` migration is correct for every collection.
- Real-world unknowns the spike settles (not plan defects): the direction of a negative candles `count`, the WS subprotocol, and whether the ticks WS needs the per-account host (`ws_host`). Follow-up: T1.11 had no check that the spike returned candles, so an empty or forward-read result could pass the feasibility gate; T1.4 step 13 now records `fetched_at` and T1.11 condition (f) stops on empty or stale XAUUSD candles, with a mechanical `True`/`False` command added to the T1.11 Verify.

### Whole-Plan Consistency Sweep (Session 3)
- Files reread: plan.md and all nine phase files.
- Terms checked: `cache: Cache`, `refresh=True`, `refresh: bool`, `ACCESS_POINT_TTL`, `ACCESS_POINT_CACHE_KEY`, `exness:access_point`, `redis-cli`, `test_sync_runner_access_point`, `exness_access_point_refresh`, `access_point_changed`, `access_point_preload`, `421`, `IP allowlisted`, `sections 10 and 11`, `entities.py:18`, `120000`, `16000`, `PersistenceProvider.get_cache`.
- Remaining hits are intentional: the Session 2 log entry (marked superseded), this session's log, and the Session 3 update markers.
- `ak plan validate` prints `[OK]`. Unresolved contradictions: 0.

### Develop reshape (2026-10-13)
- Decision (429, replaces "never retry a 429"): Exness data calls (candles, quotes, history, configuration) retry a 429 at most 3 times with backoff and log each retry; order operations never retry a 429 and are rejected and reconciled (P06 T6.6, T6.7, T6.10, T6.11; P07 T7.4, T7.6). Phases 06–09 were reshaped for develop; see `reports/revise-phases-06-09-for-develop.md`.

## Red Team Review
### Session 2026-10-09/10
| # | Finding | Severity | Disposition | Applied To |
|---|---|---|---|---|
| 1 | Live trading reachable without auth | Critical | Accepted via decision 3 (off, no selection API, auth is a go-live precondition) | plan.md Out of scope; P07 T7.8, T7.9, Security |
| 2 | Clamp/fill quantity mismatch | Critical | Applied | P07 T7.2–T7.5, T7.7 |
| 3 | Loss cap reads the wrong deals shape | Critical | Applied; follow-up adds `dividend` and `commission` | P01 T1.4, T1.10; P07 T7.4, T7.6 |
| 4 | Key delivery (PEM leak, `_PATH`, push) | Critical | Applied | plan.md U2; P01 T1.1, T1.3, T1.4, T1.8; P06 T6.2, T6.6, T6.18; P09 T9.2 |
| 5 | Lost fills, orphans, restarts | High | Applied | P06 T6.6; P07 T7.4–T7.6 |
| 6 | Shared rate budget | High | Applied; per the 2026-10-13 decision a 429 on a data call is retried at most 3 times with backoff and logged, a 429 on an order is rejected and reconciled | P06 T6.6, T6.7, T6.10, T6.11, T6.17; P07 T7.4, T7.6; P08 T8.4, T8.7 |
| 7 | `hitnrun2` silent after a reject | High | Applied; follow-up extends it to risk rejection and zero size | P07 T7.2, T7.3 |
| 8 | Weekend-only calendar | High | Applied | P01 T1.11; P03 T3.3, T3.4, T3.6; P06 T6.14 |
| 9 | Sizer cannot reach the minimum lot | High | Applied (tests and docs only, live off) | P01 T1.4, T1.11; P07 T7.3, T7.4 |
| 10 | Lowercase instrument suffixes | High | Applied | P01 T1.4, T1.11; P06 T6.4, T6.5, T6.12 |
| 11 | Windows `/tmp` | High | Applied | P01 T1.8–T1.10; P02 T2.2, T2.3; P03 T3.12; P06 T6.17; P07 T7.10 |
| 12 | Week metrics from rotating logs | High | Applied | P08 T8.6–T8.8 |
| 13 | Metric not re-measured | High | Applied via decision 2 | P05 T5.4; P06 T6.17; P07 T7.10, T7.11; P08 T8.3 |
| 14 | `venue_router` layer | High | Replaced by decision 4 | P03 T3.2–T3.9; P06 T6.14, T6.15 |
| 15 | Jobs list route does not exist | Medium | Applied | P03 T3.18 |
| M | 13 Medium fixes: `account()` currency, fixture redaction and real-value scan, base URL allowlist, WS subscription validation, ticks subscribe mode, ask-side spread, spike kept in `scripts/`, OKX test dropped, standard §8 AS-IS, one deep-backfill path, `SyncPolicy` field cleanup, citations, D6 `0 failures` | Medium | Applied | P01; P02 T2.5–T2.7; P03 T3.3; P05 T5.2; P06 T6.3–T6.16; P07 T7.5; P08 T8.1, T8.2; P09 T9.3; plan.md D6 |
