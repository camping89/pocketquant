---
phase: 9
title: "Architecture, deployment, standard and MT5 docs"
status: completed
priority: P2
effort: 1d
dependencies: [8]
---

# Phase 09: Architecture, deployment, standard and MT5 docs

<!-- Updated: 2026-10-13 develop reshape - develop docs layout (English docs with docs/vi mirrors), suffix routing instead of a policy registry, push develop-sync to develop -->
## Develop status
- Base branch: `develop` (`develop-sync` tracking `origin/develop`); ship with `git push origin develop-sync:develop`. CI `paths-ignore` (`docs/**`, `plans/**`, `**/*.md`) skips the build and deploy for a docs-only push.
- On develop the docs are English and AS-IS only (`docs/README.md:3`: no changelog, no version banner, no change narrative). Each of `system-architecture.md`, `deployment.md`, `code-standards.md`, `project-overview-pdr.md` and `codebase-summary.md` has a Vietnamese mirror in `docs/vi/` that is updated in the same commit.
- Develop has no sync policy registry (`sync_policy.py`, `sync_runner.py`, `SyncPolicies` do not exist). Providers are routed by symbol suffix (`provider_id_for`, `DATA_PROVIDER_DEFAULTS`) through `RoutingDataProviderAdapter` and `RoutingRealtimeQuoteAdapter`, and the docs already describe that model. This phase adds Exness to the existing descriptions instead of writing a policy section.
- Already current on develop, so no step here touches them: `docs/README.md:12` (the code-standards row), `CLAUDE.md:23` (the code-standards pointer), the `code-standards.md#routes--services` link in `docs/project-overview-pdr.md:342` (it resolves to `## Routes & Services`, `code-standards.md:85`), and the async callout in `system-architecture.md:716`, which cites the real heading `## Async Suspension Points — "Await Is Preemption"` (`code-standards.md:158`). Phase 06 T6.16 and T6.17 already add the `seed_exness_symbols.py` and `backfill/provider_bars.py` lines to `scripts/README.md`.

## Context Links
- Advice §2.9. `docs/README.md:3` (AS-IS rule). Mermaid v11 for diagrams of 2+ parts.
- `docs/system-architecture.md`: the `core/infra/` tree (:300-320, `tradingview/` at :311-315), the infrastructure component table (:334-342), "Where Does X Live?" (:486, provider rows :502-508), "Symbol removal" (:573), "Real-Time Streaming" (:631; inbound items :634-635; "Trade emission" paragraph :643), "Broker & Middleware" (:655-657), "Dependency Injection (Dishka)" (:686; providers :690, background jobs :692, market-data routing :694, data lag :696), "Configuration" env list (:795), "Known Limitations" (:801), "Ops Context" external services (:814).
- `docs/deployment.md`: "Environment & Credentials" (:62, prod env table :85-97), "2-Year Bar Re-Sync" (:205), "Sync Gap Repair" (:219).
- `docs/code-standards.md` (15 H2): "Composite Symbol Format" (:134-144; the add-a-provider sentence is at :141), "Dependency Injection" (:104), "Configuration & Secrets" (:292).
- `docs/codebase-summary.md`: infrastructure list (:12), `core/infra` tree (:36), inbound streaming (:152-153).
- `README.md` line 3 (Binance-only description) and line 11 (the `core/` adapter list). `scripts/README.md` (no `exness_spike.py` line). `docs/project-overview-pdr.md:260` and `docs/vi/project-overview-pdr.md:260` (still "Max 200 LOC per file").
- What the code does after Phases 06–08 (source of every statement written here): Phase 06 (`core/infra/exness/`, `core/infra/calendars/exness_session_calendar_adapter.py`, `AssetClass.CFD`, `DATA_PROVIDER_DEFAULTS["exness"]`, the two DI routers, the health map, the seed and backfill scripts, the 429 rule), Phase 07 (`core/infra/brokers/exness/`, the `BrokerFactory` branch refused while `EXNESS_LIVE_TRADING` is false, async fill wiring, `on_order_rejected`, trade emission), Phase 08 (`spread` on `PaperBrokerAdapter` and the backtest API).

<!-- Updated: Validation Session 1 - docs describe an Exness broker that is off -->
## Goal
The docs describe the system as it is now (D7): Exness as a third suffix-routed data and quote provider (`:EXNESS`), its session calendars and CFD contract specs, the 429 rule, the Exness broker built but switched off behind `EXNESS_LIVE_TRADING`, the backtest `spread`, the new env keys and scripts, the real add-a-provider touchpoint list, and MT5 as a documented future provider that is not built. Every edit lands in the English doc and its `docs/vi` mirror.

## Files to Create or Modify
- Modify: `docs/system-architecture.md`, `docs/deployment.md`, `docs/code-standards.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, the same five files under `docs/vi/`, `README.md` and `scripts/README.md`.

## Tasks

<!-- Updated: 2026-10-13 develop reshape - extend the existing routing, DI and streaming sections; no policy section -->
### T9.1 Base and `system-architecture.md`
- **Goal:** D7 holds for the architecture reference.
- **Target files and symbols:** `docs/system-architecture.md`, `docs/vi/system-architecture.md`
- **Steps:**
  1. `git switch develop-sync && git pull --ff-only && git rev-parse HEAD > .cache/phase09-base`
  2. `core/infra/` tree (:300-320): add `exness/` (`exness_signer.py`, `exness_client.py`, `exness_mappers.py`, `exness_stream.py`, `exness_adapter.py`, `exness_quote_adapter.py`), `brokers/exness/exness_broker_adapter.py` and `calendars/exness_session_calendar_adapter.py`, with one-line comments in the existing style.
  3. Component table (:334-342): add rows for `ExnessClient` (signed REST: every call after `getAccessPoint` goes to the per-account access point; requests paced by the strictest published rate with headroom; a 429 on a data call is retried at most 3 times with backoff and logged, a 429 on an order call is never retried), `ExnessAdapter` (`IDataProviderPort` over native bid candles, paged by `max_candles_per_request`, in-progress candle dropped), `ExnessQuoteAdapter` (`IRealtimeQuoteProviderPort` over the ticks WS, bid as `last_price`) and `ExnessSessionCalendarAdapter` (`ITradingCalendarPort` from recorded `trade_sessions`, UTC).
  4. "Where Does X Live?" (:502-508): add `| Exness client, mappers, data and quote adapters | core/infra/exness/ |`, `| Exness broker (live trading off) | core/infra/brokers/exness/ |` and `| Exness session calendars | core/infra/calendars/exness_session_calendar_adapter.py |`.
  5. "Real-Time Streaming" inbound list (:634-635): add item 3, the Exness ticks WS (`ExnessQuoteAdapter` under `RoutingRealtimeQuoteAdapter`, subprotocol `exness-ws-protocol`, `subscribe` mode `add`, reconnect 1 s→30 s with a 10-failure circuit breaker), and item 4, the Exness events WS (per broker instance: transaction events, broker-side closes, snapshot reconciliation). In "Trade emission" (:643) add that `ExnessBrokerAdapter` forwards a `TradeClosedEvent` per close deal after the fill.
  6. "Broker & Middleware" (:655-657): add `ExnessBrokerAdapter` and its rules: market orders only, SL required, quantity normalized to the lot grid by `normalize_quantity` before the order is created (capped at the minimum lot unless `EXNESS_MAX_LOTS`), the daily loss cap from real deals (`close`, `swap_fee`, `admin_fee`, `dividend` and commissions; `balance` deposits and withdrawals excluded; fails closed), orders blocked until the trading snapshot is reconciled, a 429 on an order rejected and reconciled rather than retried, and async fill wiring only for brokers with `fills_async` (only Exness). State that `EXNESS_LIVE_TRADING` defaults to false, that `BrokerFactory` refuses `exness` and the client refuses order operations while it is false, and that no API selects a broker per subscription (`config.broker` stays `paper` for subscriptions). Add `PaperBrokerAdapter` `spread` (ask = bid + spread; BUY entries and SHORT exits at ask; SHORT SL/TP on the ask high/low; backtest-only, the live paper broker has none).
  7. "Dependency Injection" (:690, :694): the routers are over `{binance, tradingview, exness}`; `AdaptersProvider` adds `ExnessClient` and builds `BrokerFactory` with it. Routing adds `XAUUSD:EXNESS` → `exness`, and `exness` → CFD with the Exness FX calendar in the `DATA_PROVIDER_DEFAULTS` sentence. Background jobs (:692): `sync_1m` covers `:EXNESS` symbols through the same path, gated by their calendar.
  8. "Configuration" (:795): add `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_SECRET_KEY`, `EXNESS_LIVE_TRADING` (default false), `EXNESS_RATE_FRACTION`, `EXNESS_DAILY_LOSS_CAP` and `EXNESS_MAX_LOTS`. "Ops Context" (:814): add Exness (signed REST + WS market data and quotes; trading built but off).
  9. Add `## MT5 (future provider, not built)` before "Known Limitations" (:801): the same ports (`IDataProviderPort`, `IRealtimeQuoteProviderPort`, optional `IBrokerPort`), a suffix (`:MT5`, which the routing tests already pin as unregistered), a sketch (bars from `copy_rates_from`, quotes from `copy_ticks_from`, `order_send` behind `IBrokerPort`), the Windows host or Wine bridge (`mt5linux`/`mt5-remote`) deployment constraint, and the fact that Exness API keys apply to Exness-platform accounts, not MT5 accounts.
  10. "Symbol removal" (:573): if Phases 06–07 added any symbol-keyed collection or Redis key, add it to the list; otherwise leave the section unchanged.
  11. Apply the same changes to `docs/vi/system-architecture.md` (Vietnamese prose, English technical terms).
- **Success criteria:** No statement contradicts the code, and the mirror matches.
- **Verify:**
  - `grep -cE "core/infra/exness|ExnessBrokerAdapter|EXNESS_LIVE_TRADING|exness-ws-protocol|copy_rates_from|XAUUSD:EXNESS" docs/system-architecture.md` is ≥ 6, and the same command on `docs/vi/system-architecture.md` is ≥ 6.
  - `grep -cE "sync_policy|SyncPolicies|sync_runner|policy_bars|Last Updated" docs/system-architecture.md docs/vi/system-architecture.md` prints `0` for each file.
  - Every store in `TrackedSymbolsService._symbol_data` (`engine/market_data/tracked_symbols_service.py:102-112`) is named in the doc: `uv run python -c "import re;t=open('docs/system-architecture.md',encoding='utf-8').read();s=open('src/pocketquant/engine/market_data/tracked_symbols_service.py',encoding='utf-8').read();i=s.find('self._symbol_data:');w=re.findall(r'\"(\w+)\":',s[i:s.find('}',i)]);print(len(w)>=9 and all(c in t for c in w))"` prints `True`.

<!-- Updated: 2026-10-13 develop reshape - env table, seed and backfill runbook, README, pdr -->
### T9.2 Deployment, scripts, README and overview docs
- **Goal:** Operators can configure Exness data, seed and backfill it, and know that trading is off.
- **Target files and symbols:** `docs/deployment.md` (env table :85-97; a `### Exness symbols and deep history` subsection under "2-Year Bar Re-Sync" :205), `scripts/README.md`, `README.md`, `docs/project-overview-pdr.md:260`, `docs/codebase-summary.md` (:12, :36, :152-153), and their `docs/vi` mirrors.
- **Steps:**
  1. `deployment.md` env table rows: `EXNESS_API_BASE_URL` (https on `api.exness.com`; serves `getAccessPoint` only), `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_SECRET_KEY` (the 128-hex secret exactly as Key Management shows it: 32-byte seed then 32-byte public key; PEM is rejected and the CI `.env` guard fails on multi-line values), `EXNESS_LIVE_TRADING` (default `false`; only a go-live plan changes it), `EXNESS_RATE_FRACTION` (default `1.0`), `EXNESS_DAILY_LOSS_CAP` and `EXNESS_MAX_LOTS` (unset means the minimum lot). Under the table, one note: the per-account access point is not an env var; `ExnessClient` resolves it from `getAccessPoint` once per process, in memory, as a full https URL. All values live in `pocketquant-config`.
  2. The new subsection: `docker exec pocketquant-app python scripts/seed_exness_symbols.py` (dry-run) and `--apply`, then `docker exec pocketquant-app python scripts/backfill/provider_bars.py --symbol <CODE>:<PROVIDER> --interval <tf> --days <n> --rate-fraction 0.5` (refuses while `EXNESS_LIVE_TRADING` is true; Exness M1 history reaches back one year), and that `DELETE /api/v1/market-data/tracked-symbols/{symbol}` removes an Exness symbol with all its data.
  3. `scripts/README.md`: one line for `exness_spike.py` (read-only diagnostics against the Exness API; writes fixtures and a summary, places no order).
  4. `README.md` line 3: mention Exness (signed REST/WS market data and quotes for CFDs) and TradingView next to Binance. Line 11: add `exness` and `tradingview` to the `core/` adapter list.
  5. `docs/project-overview-pdr.md:260`: replace `Max 200 LOC per file (exceptions documented)` with `File and function size: see code-standards.md "File and Function Size"`; the same in `docs/vi/project-overview-pdr.md:260`.
  6. `docs/codebase-summary.md`: add Exness REST/WS to the infrastructure list (:12), `exness/` to the tree (:36) and the Exness ticks WS to inbound streaming (:152-153).
  7. Apply steps 1, 2 and 6 to the `docs/vi` mirrors.
- **Success criteria:** No stale claims remain and the links are valid.
- **Verify:**
  - `grep -cE "EXNESS_LIVE_TRADING|EXNESS_DAILY_LOSS_CAP" docs/deployment.md docs/vi/deployment.md` is ≥ 2 for each file.
  - `grep -c "provider_bars.py" docs/deployment.md` is ≥ 1.
  - `grep -c "200 LOC" docs/project-overview-pdr.md docs/vi/project-overview-pdr.md` prints `0` for each file.
  - `grep -c "Exness" README.md` is ≥ 1.
  - `grep -cE "exness_spike.py|seed_exness_symbols.py|provider_bars.py" scripts/README.md` prints `3`.

<!-- Updated: 2026-10-13 develop reshape - touchpoints extend Composite Symbol Format; 15 H2 stay 15 -->
### T9.3 `code-standards.md` provider touchpoints and secrets rule
- **Goal:** The standard lists the real places a new data provider touches, now that Exness exists, and states the Exness secrets rule.
- **Target files and symbols:** `docs/code-standards.md` "Composite Symbol Format" (:134-144) and "Configuration & Secrets" (:292), and `docs/vi/code-standards.md`
- **Steps:**
  1. Add `XAUUSD:EXNESS` to the format examples (:136).
  2. Replace the sentence "registering a provider means adding it to both routing adapters in `app/di/` and to that table" (:141) with a checklist "Adding a data provider", exactly these touchpoints as they exist in the code:
     1. adapter package `src/pocketquant/core/infra/<provider>/` (`IDataProviderPort`, optional `IRealtimeQuoteProviderPort`);
     2. `Settings` fields in `src/pocketquant/core/config.py`;
     3. one `DATA_PROVIDER_DEFAULTS` entry (`core/domain/market_data/provider_routing_domain_service.py`) and one entry in each router in `app/di/adapters.py` (`get_data_provider`, `get_realtime_quote_provider`); `tests/app_test/unit/test_data_provider_registration.py` enforces that the three match;
     4. a calendar registered in `TradingCalendarFactory` (`core/infra/calendars/trading_calendar_factory.py`) when no existing one fits, built from recorded sessions;
     5. a `ContractSpec` per symbol, written by a seed script modelled on `scripts/seed_index_futures.py` (`symbols` and `tracked_symbols`);
     6. the provider in the `/health` provider map (`register_health_checks`, `app/main_extensions.py`);
     7. any new symbol-keyed collection or Redis key joins the symbol-removal cascade (`TrackedSymbolsService`);
     8. a broker is optional and separate: a `BrokerFactory` branch, with the broker's own instrument table keyed by the full composite symbol;
     9. env rows in `docs/deployment.md`, and adapter tests under `tests/core_test/infra/<provider>/` against recorded fixtures.
  3. Add to "Configuration & Secrets": `EXNESS_*` keys live only in `pocketquant-config`, `EXNESS_SECRET_KEY` is a single-line 128-hex secret key, `.env` values are single-line `KEY=VALUE`, secrets are never logged, and `EXNESS_LIVE_TRADING` stays false outside a go-live plan.
  4. Apply the same changes to `docs/vi/code-standards.md`. Add no H2, banner or history.
- **Success criteria:** The checklist matches the code, and the H2 count is unchanged.
- **Verify:** `grep -c "test_data_provider_registration" docs/code-standards.md docs/vi/code-standards.md` is ≥ 1 for each file. `grep -c "EXNESS_LIVE_TRADING" docs/code-standards.md` is ≥ 1. `grep -c "^## " docs/code-standards.md docs/vi/code-standards.md` prints `15` for each file. `grep -cE "Current Status|Last Updated|Version:" docs/code-standards.md` prints `0`.

<!-- Updated: 2026-10-13 develop reshape - push develop-sync to develop; CI skips docs-only pushes -->
### T9.4 Ship
- **Goal:** The docs are on develop. CI `paths-ignore` skips the build and deploy for docs-only changes.
- **Target files and symbols:** git
- **Steps:**
  1. `git add docs README.md scripts/README.md plans/261009-0858-exness-venue-lean-sync-refactor` (this also commits the Phase 08 reports written after T8.3)
  2. `git diff --cached --name-only | grep -vE '^(docs/|plans/|README.md$|scripts/README.md$)'` must print nothing.
  3. `git commit -m "docs: describe exness provider, broker switch and mt5 future provider"`
  4. `git push origin develop-sync:develop`
- **Success criteria:** The commit is on `origin/develop` and no deploy ran for it.
- **Verify:** Step 2 prints nothing. `git log origin/develop -1 --format=%s` prints `docs: describe exness provider, broker switch and mt5 future provider`. `gh run list --branch develop --limit 5 --json headSha --jq ".[].headSha" | grep -c $(git rev-parse HEAD)` prints `0`.

## Verification
T9.1–T9.3 greps, plus T9.4.

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- A doc change would describe live Exness trading as enabled, or document a broker selection mechanism that does not exist.
- A docs edit would require a code change (record it for the user instead).
- The code after Phases 06–08 differs from a statement this phase prescribes (for example a different calendar id or asset class); describe the code, and ask before changing the plan's wording.

## Risks
- **The docs drift into change narrative.** Mitigation: the greps for banned words, and the AS-IS rule in `docs/README.md:3`.
- **The `docs/vi` mirror drifts from the English doc** (M/L). Mitigation: every task edits both, and the greps run on both.

## Rollback
`git revert` the docs commit and push it with `git push origin develop-sync:develop`.

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

## Completion notes (2026-10-19)
All T9.1-T9.3 Verify commands met their pass conditions. Three statements prescribed above differ from the code. Following Stop-and-ask, the docs describe the code, and the task wording above is unchanged pending the user's decision:
- T9.1 step 5, "`subscribe` mode `add`": the ticks subscribe frame has no mode field (`exness_quote_adapter.py` `_send_subscribe`). A later subscribe adds to the earlier ones, and that is what the docs say.
- T9.2 step 2, "Exness M1 history reaches back one year": no source in code, fixtures or the spike journal (`history_age_days` = 30 applies to deals and orders history). The docs say that a window older than the history Exness keeps fails with the Exness error code and exit 1 (`provider_bars.py`).
- T9.1 step 6, commissions counted only for `close`/`swap_fee`/`admin_fee`/`dividend`: the code subtracts the commission of every deal except `balance` (`exness_broker_adapter.py` `_realized_today`). The docs describe the code.
- Added from the code: an unset `EXNESS_DAILY_LOSS_CAP` rejects every Exness order, and the WS breaker pauses for 5 minutes.
- Already out of date in `docs/vi` before this phase and left as it was: the vi "Where Does X Live?" has no TradingView rows, and the vi "Dependencies" omits `pandas_market_calendars` and `tvdatafeed`. `docs/system-architecture.md` is 876 lines; it was already 841.
