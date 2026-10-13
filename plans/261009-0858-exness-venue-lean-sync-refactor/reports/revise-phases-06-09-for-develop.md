# Revise phases 06–09 for develop

Date: 2026-10-13 (Asia/Bangkok). Base: `develop-sync` at `origin/develop` (fast-forward up to date before the edits). Only plan files changed; no code changed.

## Inputs applied
- The user decisions in the brief: the suffix is the data-provider id; the broker is `config.broker` and has its own instrument table; deleting a symbol cascades; the new 429 rule; the spike facts; develop's design wins; the develop gate wording.
- Revalidate verdicts: `reports/revalidate-develop-phases-01-06-07.md` and `reports/revalidate-develop-phases-08-09.md`. Those reports were written before integration steps 2–4, so every anchor was re-checked against the current develop tree. Where a report and develop disagree, develop wins (for example `app/di/core.py` and `app/di/market_data.py` no longer exist; the routers are in `app/di/adapters.py`).

## Gate wording used in every phase
- `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`
- ruff and pyright report 0 errors in `src/` and in touched files; pre-existing test debt is accepted.
- `just test` shows no new failures; the 4 Windows `time.tzset` tests are pre-existing.
- `uv run python scripts/code_metrics.py --ratchet` exits 0.
- Ship is `git push origin develop-sync:develop`. There is no feature branch and no `master` step.

## Phase 06: Exness market data and quotes (was "Exness market data, quotes and policy")
- **Kept, with names, paths and anchors updated:**
  - T6.2 settings; adds `exness_rate_fraction`.
  - T6.3 signer.
  - T6.5 mapper tests, T6.7 client tests, T6.9 WS tests, T6.11 data adapter tests and T6.13 quote adapter tests.
  - T6.8 stream: subprotocol `exness-ws-protocol`.
- **Reshaped:**
  - T6.1: from "branch" to sync and record the base.
  - T6.4 mappers: `EXNESS_INSTRUMENTS` is keyed by the full composite symbol, instrument names equal the codes, and W1 is included.
  - T6.6 client:
    - every call after `getAccessPoint` goes to the access point (a full https URL);
    - requests are paced by the strictest published rate with headroom;
    - a 429 on a data call is retried 3 times with backoff and logged; a 429 on an order call is not retried;
    - the deals window is `history_age_days - 1`.
  - T6.10: from `data_provider.py` to `exness_adapter.py` implementing `IDataProviderPort`.
  - T6.12: from `quote_provider.py` to `exness_quote_adapter.py` implementing `IRealtimeQuoteProviderPort`, with subscribe mode `add`.
  - T6.14: from "policy and calendars" to `ExnessSessionCalendarAdapter` behind `ITradingCalendarPort`, registered in `TradingCalendarFactory`. BTCUSD uses `CRYPTO_24_7`.
  - T6.15: from "DI registers the policy" to:
    - `AssetClass.CFD` with its defaults;
    - `DATA_PROVIDER_DEFAULTS["exness"]`;
    - one entry in each router in `app/di/adapters.py`;
    - the `/health` provider map;
    - the 3 tests that pinned `:EXNESS` as unregistered switch to `XAUUSD:MT5`.
  - T6.17 (was T6.16): from `policy_bars.py` to `scripts/backfill/provider_bars.py` through `create_container`.
  - T6.18 (was T6.17): the develop gate.
  - T6.19 (was T6.18): push to develop, seed with a mongodump backup, then the D1 checks.
- **Added:** T6.16 `scripts/seed_exness_symbols.py`, modelled on `scripts/seed_index_futures.py`. It writes the `symbols` and `tracked_symbols` entries and a `ContractSpec` for each symbol.
- **Dropped:**
  - The `SyncPolicy` and `SyncPolicies` registry, `policy_for` and `build_sync_policies`. Their goal now lives in suffix routing (T6.15) and develop's existing `sync_1m` and `sync_backfill` jobs.
  - The 40 s `poll_time_cap_s`. Develop has no per-provider cap; this is recorded as a Risk.
  - The "re-validate T6.6 routing before Phase 06" flag. The spike facts settle it.

## Phase 07: Exness broker behind the live-trading switch (off)
- **Kept, with develop paths and lines:**
  - T7.1 settings.
  - T7.2 hooks on `IBrokerPort` and `IStrategyService`.
  - T7.3 engine wiring (`engine/strategy`, `engine/execution`).
  - T7.6 tests against `tests/core_test/infra/exness/fixtures/`.
  - T7.7 clamp → fill → position, on the real-Mongo `db` fixture.
- **Reshaped:**
  - T7.4/T7.5: `core/infra/brokers/exness/exness_broker_adapter.py` (`ExnessBrokerAdapter`).
    - It implements the trade subscription and emits `TradeClosedEvent` after the fill, as develop's `IBrokerPort` requires.
    - Deals are read as `items[].deal` and paged by `next_cursor`, with the window clamped to `deals_window_days()`.
    - A 429 on an order is rejected and sets `_needs_snapshot`. Deals, snapshot and status reads rely on the client's 3 retries.
  - T7.8: `BrokerFactory` gains keyword-only optional dependencies, built by an explicit DI provider. The 4 existing `BrokerFactory(event_bus)` test call sites stay untouched.
  - T7.9: uses the `settings` fixture and `create_container(settings)`, and runs `test_app_standalone_runtime.py` instead of the absent `tests/baseline/test_app_boot_smoke.py`.
  - T7.10: the develop gate.
  - T7.11: compares against `reports/metrics-develop-ratchet.json` and `[tool.code-metrics]` (0.48 / 77).
  - T7.12: push to develop.
- **Dropped:** none.
- **Added:** none. Trade emission sits inside T7.5 and T7.6.

## Phase 08: Validation: spread, backtests, paper week
- **Kept:** T8.5 backtests (the trades check now reads `total` from the paged response). T8.7 daily observation (adds an `RL` column counting `exness.rate_limited_retry`, recorded only).
- **Reshaped:**
  - T8.1: `PaperBrokerAdapter` at develop lines; the test file is under `tests/core_test/infra/brokers/`.
  - T8.2: develop backtest paths. With no OpenAPI snapshot, the check compares `RunBacktestCommand.model_json_schema()` before and after, plus no diff under `app/`.
  - T8.3: the develop gate and push.
  - T8.4: `provider_bars.py`. The BTCUSD minimums are fixed numbers from `CRYPTO_24_7`: 103680 and 14016.
  - T8.6:
    - subscriptions run on the paper broker because `config.broker` defaults to paper;
    - the no-deploy question covers pushes to develop and master and manual workflow runs;
    - adds a session re-read against the calendar constants, repeated after the 2026-11-01 DST change.
  - T8.8: adds the `sync_1m` `p95_ms` < 60000 check from `/api/v1/system/jobs/sync_1m/stats`.
- **Dropped:** the `tests/baseline/openapi_app_snapshot.json` regeneration (no such file on develop); its goal moves to the T8.2 schema diff.
- **Added:** none as separate tasks.

## Phase 09: Architecture, deployment, standard and MT5 docs
- **Reshaped (all four tasks):**
  - Docs are English, each with a `docs/vi` mirror updated in the same task.
  - T9.1 extends the existing tree, component table, "Where Does X Live?", streaming, broker and DI routing text. It adds an MT5 H2 and checks that the symbol-removal list covers `TrackedSymbolsService._symbol_data`.
  - T9.2: env rows, a seed and backfill runbook under "2-Year Bar Re-Sync", the `exness_spike.py` line, README, the pdr 200-LOC line and `codebase-summary.md`.
  - T9.3: the add-a-provider checklist replaces the one-line rule in "Composite Symbol Format". The H2 count stays 15.
  - T9.4: push to develop; CI `paths-ignore` skips the deploy.
- **Dropped steps (already current on develop):**
  - the policy-registry section;
  - the async callout rename (the cited heading exists at `code-standards.md:158`);
  - `docs/README.md:12`;
  - `CLAUDE.md:23`;
  - the pdr `#routes--services` link (it resolves to `## Routes & Services`);
  - the `migrate_okx_market_data.py` lines (OKX had nothing to migrate per `user-preconditions.md`);
  - the `scripts/README` lines for the seed and backfill scripts, which Phase 06 T6.16 and T6.17 add.

## plan.md
- Phase 06 row title: "Exness market data and quotes". Effort unchanged; rows 07–09 unchanged.
- The Session 1 follow-up 429 bullet is marked superseded.
- A new "Develop reshape (2026-10-13)" subsection holds the one 429 decision line and points to this report.
- Red-team row 6 states the new rule and the new task references.

## Anchors not verified
Each item below is labelled as unverified or as an inference.
- **Exness behaviour:** DST behaviour of `trade_sessions` (P06 Risks, P08 T8.6), W1 candle alignment, and the deals `next_cursor` field. `next_cursor` is in the spec, but the recorded `deals.json` has only `has_more` and `range`.
- **Commands not run:** the `mongodump` backup command form in T6.19, and the `ssh … docker exec -i pocketquant-app python -` heredoc form in T8.6.
- **Inferences, not tested:**
  - T6.17: building `create_container` in a script resolves only what the script requests and starts no scheduler. Dishka builds lazily; startup jobs are wired in `app/main.py`.
  - T6.19: the `/health` JSON nesting of the provider map. The verify step uses a substring check to tolerate it.
  - T9.4: `gh run list` shows no run for a docs-only push. This is inferred from `paths-ignore`.
- **Not executed:** the T9.1 `_symbol_data` doc check and the T8.2 schema-diff command were dry-run against current develop (both work as written). No other phase command was executed, because this task changes plan files only.

## Open questions for the user
1. **Design choices I made that the brief did not fix:**
   - `AssetClass.CFD` with calendar ids `EXNESS_FX` and `EXNESS_XAUUSD`.
   - `ContractSpec(multiplier=1, tick_size=10^-digits, lot_step=None)`. This is an inference from the sizing arithmetic: a grid `lot_step` would size every order to zero at a 10k account, while the broker adapter converts units to lots itself.
   - Treating snapshot and `getOperationStatus` reads as data calls for the 429 retry.
   - Honouring a numeric `Retry-After`, as the spike does.
2. **Stale plan.md items outside the brief's edit list**, left unchanged:
   - frontmatter `branch: master` and the description's "SyncPolicy registry";
   - Dependencies bullet 4 ("push to master");
   - D2 and D3 use the old names `ExnessBroker` and `PaperBroker.spread`;
   - D4, D5 ("3 kept"), D6 and D7 ("policy registry", "§8");
   - the Test matrix row with `tests/baseline` and "policy registry".

   Should a follow-up align them with develop?
3. **Phase file names:** `phase-06-exness-market-data-and-policy.md` keeps its name so links stay stable, although the title no longer says "policy". Rename it?

## Files changed
- `plans/261009-0858-exness-venue-lean-sync-refactor/phase-06-exness-market-data-and-policy.md`
- `plans/261009-0858-exness-venue-lean-sync-refactor/phase-07-exness-broker-off-by-default.md`
- `plans/261009-0858-exness-venue-lean-sync-refactor/phase-08-validation-spread-backtests-paper-week.md`
- `plans/261009-0858-exness-venue-lean-sync-refactor/phase-09-docs-architecture-deployment-mt5.md`
- `plans/261009-0858-exness-venue-lean-sync-refactor/plan.md`
- `plans/261009-0858-exness-venue-lean-sync-refactor/reports/revise-phases-06-09-for-develop.md`
