---
phase: 9
title: "Architecture, deployment, standard and MT5 docs"
status: pending
priority: P2
effort: 1d
dependencies: [8]
---

# Phase 09: Architecture, deployment, standard and MT5 docs

## Context Links
- Advice §2.9. `CLAUDE.md` docs rules: Vietnamese prose, English technical terms, AS-IS only, no banners or change narrative, Mermaid v11 for 2+ parts.
- `docs/system-architecture.md` sections: "Where Does X Live?" (:455), "Real-Time Streaming" (:553), "Broker & Middleware" (:573), "Dependency Injection (Dishka)" (:604). Stale rows: "Dishka DI container (6 providers)" (:472), "Background sync job registration" (:483) and the "6 providers" sentence (:606).
- `docs/deployment.md` "Environment & Credentials" (:62, the prod env table). `scripts/README.md`. `README.md` line 3 (Binance-only wording) and line 11 (the `core/` adapter list). `docs/project-overview-pdr.md:260` ("Max 200 LOC per file"). `docs/README.md:12` (code-standards row).
- `docs/code-standards.md` §8 `## Sync policy pattern` and §14 `## Configuration & Secrets`, written AS-IS in Phase 05 before Exness existed.

<!-- Updated: Validation Session 1 - docs describe the policy registry (no router) and an Exness broker that is off -->
## Goal
The docs describe the system as it is now (D7): the Exness adapters, the `SyncPolicies` registry that resolves providers strictly by exchange suffix, the shared runner, 3 DI providers, the Exness broker built but switched off behind `EXNESS_LIVE_TRADING`, the new env keys, the real add-a-provider touchpoint list, and MT5 as a documented future provider that is not built.

## Files to Create or Modify
- Modify: `docs/system-architecture.md`, `docs/deployment.md`, `docs/code-standards.md`, `scripts/README.md`, `README.md`, `docs/project-overview-pdr.md` and `docs/README.md`.

## Tasks

<!-- Updated: Validation Session 1 - registry flow, broker off, policy_bars row -->
<!-- Updated: Validation Session 1 - follow-up: Exness-only async wiring, loss-cap deal set, no 429 retry -->
### T9.1 Branch and `system-architecture.md`
- **Goal:** D7 holds.
- **Target files and symbols:** `docs/system-architecture.md`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c docs/exness-architecture`
  2. Add `## Market Data Sync Policy`: the `SyncPolicy` fields table, the Binance and Exness policy values, the rule that `policy_for` resolves by exchange suffix only (no fallback; an unknown suffix logs once and is skipped; `:OKX` has no data policy because OKX is a broker only), a Mermaid v11 `flowchart` of `APScheduler → sync_runner → SyncPolicies.policy_for → SyncPolicy.data_provider (BinanceClient | ExnessDataProvider) ← SyncService → BarRepository (+ cascade_aggregator when cascade)`, and the 3-file flow list (`routes/market_data.py → sync_service.py → sync_policy.py`; `sync_runner.py → sync_policy.py → sync_service.py`, with `bar_integrity.py` and `cascade_aggregator.py` as leaf calls).
  3. "Real-Time Streaming": add the Exness ticks WS (`ExnessQuoteProvider`, reached through the EXNESS policy's `quote_provider`; at most 1 tick per 500 ms; bid used as `last_price`; subscriptions validated against the instrument list) and the Exness events WS (`ExnessBroker`: fills, broker-side closes, snapshot reconciliation).
  4. "Broker & Middleware": add `ExnessBroker` and its rules: market orders only, SL required, lots computed inside the adapter (`contract_size`, `volume_step`, `volume_min` cap unless `EXNESS_MAX_LOTS`) with `normalize_quantity` before order creation, the daily loss cap, orders blocked until the trading snapshot is reconciled, and async fill wiring only for brokers that set `fills_async` (today only `ExnessBroker`; PaperBroker and OKX are not wired). The daily loss cap counts `close`, `swap_fee`, `admin_fee` and `dividend` deals plus commissions, and excludes `balance` deposits and withdrawals; a 429 from Exness is never retried automatically. State that `EXNESS_LIVE_TRADING` defaults to false, that `BrokerFactory` refuses `exness` and the client refuses order operations while it is false, and that no API selects a broker per subscription.
  5. "Dependency Injection": 3 providers (`InfrastructureProvider`, `AdaptersProvider`, `ServicesProvider`), `Settings` via `from_context`, `STRICT_VALIDATION`, and `build_sync_policies` in `app/di/adapters.py`. Replace the "6 providers" sentence at :606.
  6. "Where Does X Live?": fix the rows at :472 and :483, and add rows for `engine/market_data/sync_policy.py`, `sync_runner.py`, `bar_integrity.py`, `core/infra/exness/`, `scripts/backfill/policy_bars.py` and `scripts/code_metrics.py`.
  7. Add `## MT5 (future provider, not built)`: the same 3 ports, a policy sketch (bar source `copy_rates_from`, live source `copy_ticks_from`, `order_send` behind `IBroker`), the Windows host or Wine bridge (`mt5linux`/`mt5-remote`) deployment constraint, and the fact that Exness API keys apply to Exness-platform accounts, not MT5 accounts.
- **Success criteria:** No stale statements remain.
- **Verify:**
  - `grep -cE "SyncPolicies|sync_runner.py|core/infra/exness|copy_rates_from|ExnessBroker|EXNESS_LIVE_TRADING" docs/system-architecture.md` is ≥ 6.
  - `grep -cE "sync_jobs|sync_internals|6 providers|Last Updated" docs/system-architecture.md` prints `0`.

<!-- Updated: Validation Session 1 - env rows match the single-line key rule and the live switch; one backfill runbook -->
<!-- Updated: Validation Session 3 - access point note reduced to the in-memory per-process resolve -->
### T9.2 Deployment, scripts and README
- **Goal:** Operators can configure Exness data and know that trading is off.
- **Target files and symbols:** `docs/deployment.md` (the env table and a new runbook section `## Deep History Backfill`), `scripts/README.md`, `README.md`, `docs/project-overview-pdr.md:260` and `docs/README.md:12`.
- **Steps:**
  1. `deployment.md` env table rows: `EXNESS_API_BASE_URL` (https, on the host confirmed for this account), `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_SECRET_KEY` (the 128-hex secret exactly as Key Management shows it: 32-byte seed then 32-byte public key; PEM is rejected and the CI `.env` guard fails on multi-line values), `EXNESS_LIVE_TRADING` (default `false`; only a go-live plan changes it), `EXNESS_DAILY_LOSS_CAP` and `EXNESS_MAX_LOTS` (unset means the minimum lot); then one note under the table that the per-account access point is not an env var: `ExnessClient` resolves it from `GET /v1/trading/access-point` once per process, in memory, for trading calls. Add the runbook section with the `docker exec pocketquant-app python scripts/backfill/policy_bars.py --symbol <CODE>:<EXCHANGE> --interval <tf> --days <n> --rate-fraction 0.5` command from Phase 08 T8.4, and the `:OKX` migration script usage (`--inventory`, `--apply --approved`, backup first).
  2. `scripts/README.md`: one line each for `exness_spike.py` (read-only diagnostics), `backfill/policy_bars.py` (deep backfill for any policy), `code_metrics.py` (ratchet) and `migrate_okx_market_data.py`.
  3. `README.md` line 3: mention Exness (signed REST/WS market data and quotes) next to Binance. Line 11: add `exness` to the `core/` adapter list.
  4. `docs/project-overview-pdr.md:260`: replace `Max 200 LOC per file (exceptions documented)` with `File ~400 LOC soft guidance, functions ≲60 lines (xem code-standards.md)`.
  5. `docs/README.md:12` code-standards row: replace `file-size rules` with `rules of thumb, sync policy pattern, metric ratchet`.
- **Success criteria:** No stale claims remain and the links are valid.
- **Verify:**
  - `grep -cE "EXNESS_LIVE_TRADING|EXNESS_DAILY_LOSS_CAP" docs/deployment.md` is ≥ 2.
  - `grep -c "policy_bars.py" docs/deployment.md` is ≥ 1.
  - `grep -c "200 LOC" docs/project-overview-pdr.md` prints `0`.
  - `grep -c "Exness" README.md` is ≥ 1.
  - `grep -cE "code_metrics.py|policy_bars.py|migrate_okx_market_data.py|exness_spike.py" scripts/README.md` prints `4`.

<!-- Updated: Validation Session 1 - code-standards §8 gets the real add-a-provider touchpoint list; §14 gets the EXNESS_* rule -->
### T9.3 `code-standards.md` provider touchpoints and secrets rule
- **Goal:** The standard lists the real places a new provider touches, now that Exness exists, and states the Exness secrets rule.
- **Target files and symbols:** `docs/code-standards.md` §8 `## Sync policy pattern` and §14 `## Configuration & Secrets`
- **Steps:**
  1. Append to §8 a checklist "Thêm một provider" with exactly these touchpoints, as they exist in the code:
     1. adapter package `src/pocketquant/core/infra/<venue>/` (data provider for `IDataProvider`, quote provider for `IRealtimeQuoteProvider`, optional broker for `IBroker`);
     2. `Settings` fields in `src/pocketquant/core/config.py`;
     3. a policy factory in `src/pocketquant/engine/market_data/sync_policy.py` (intervals, cascade, `poll_time_cap_s`, `history_days`, calendars from recorded `trade_sessions`);
     4. one entry in `build_sync_policies` in `src/pocketquant/app/di/adapters.py`;
     5. optionally one `BrokerFactory` branch;
     6. instrument names and sessions taken from a read-only spike's fixtures;
     7. env rows in `docs/deployment.md`;
     8. adapter tests under `tests/core_test/infra/<venue>/` against recorded fixtures.
  2. Add to §14: `EXNESS_*` keys live only in `pocketquant-config`, `EXNESS_SECRET_KEY` is a single-line 128-hex secret key, `.env` values are single-line `KEY=VALUE`, secrets are never logged, and `EXNESS_LIVE_TRADING` stays false outside a go-live plan.
  3. Keep the H2 count at 14 and add no banner or history.
- **Success criteria:** §8 and §14 match the code.
- **Verify:** `grep -c "build_sync_policies" docs/code-standards.md` is ≥ 1. `grep -c "EXNESS_LIVE_TRADING" docs/code-standards.md` is ≥ 1. `grep -c "^## " docs/code-standards.md` prints `14`. `grep -cE "Current Status|Last Updated|Version:" docs/code-standards.md` prints `0`.

<!-- Updated: Validation Session 1 - code-standards included in the docs commit -->
### T9.4 Ship
- **Goal:** The docs are merged. CI `paths-ignore` skips the deploy for docs-only changes.
- **Target files and symbols:** git
- **Steps:**
  1. `git add docs README.md scripts/README.md plans/261009-0858-exness-venue-lean-sync-refactor` (this also commits the Phase 08 reports written after T8.3)
  2. `git commit -m "docs: describe exness adapters, sync policy registry and mt5 future provider"`
  3. Ask the user for approval, then `git switch master && git merge --ff-only docs/exness-architecture && git push origin master`.
- **Success criteria:** The commit is on master.
- **Verify:** `git log origin/master -1 --format=%s` prints `docs: describe exness adapters, sync policy registry and mt5 future provider`.

## Verification
T9.1–T9.3 greps, plus T9.4.

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- A doc change would describe live Exness trading as enabled, or document a broker selection mechanism that does not exist.
- A docs edit would require a code change (record it for the user instead).

## Risks
- **The docs drift into change narrative.** Mitigation: the greps for banned words, and the AS-IS rule in `CLAUDE.md`.

## Rollback
`git revert` the docs commit.

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
