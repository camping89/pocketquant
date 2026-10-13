# Revalidation of Phases 08 and 09 against develop 4b3a77a

Read-only check in D:/w/_me/algotrading/pq-develop. Everything below was read from the worktree unless marked (inference).

## Verdicts

| Item | Verdict |
|---|---|
| P08 Context Links | STALE (class, file names, packages, line numbers) |
| P08 T8.1 PaperBroker spread | NEEDS RESHAPE |
| P08 T8.2 backtest plumbing | NEEDS RESHAPE (3 files moved, BacktestConfig is a domain dataclass, tests/baseline absent) |
| P08 T8.3 gate and ship | NEEDS RESHAPE (branch policy, 3-zone CI, ratchet artifacts missing) |
| P08 T8.4 backfill | NEEDS RESHAPE (future-phase artifacts; symbol seeding and asset-class routing missing) |
| P08 T8.5 backtests | STILL VALID |
| P08 T8.6 start paper week | NEEDS RESHAPE (line cite, no-deploy wording for two branches) |
| P08 T8.7 daily observation | STILL VALID (log event names are Phase 06 artifacts) |
| P08 T8.8 close week | STILL VALID |
| P09 T9.1 system-architecture | NEEDS RESHAPE (anchors shifted; doc already has routing and calendar content; suffix-only routing text conflicts with develop) |
| P09 T9.2 deployment, scripts, README | NEEDS RESHAPE |
| P09 T9.3 code-standards | NEEDS RESHAPE (17 H2, no sync-policy section yet) |
| P09 T9.4 ship | NEEDS RESHAPE (master-only) |
| D3, D6, D7, Test matrix, Dependencies | NEEDS RESHAPE (see section 4) |
| Paper-week metric | STILL VALID |

## 1. Phase 08

### Context Links, stale items and develop truth
- src/pocketquant/core/infra/brokers/paper/paper_broker.py does not exist. Develop: paper_broker_adapter.py, class PaperBrokerAdapter(IBrokerPort) at :88.
- Lines in paper_broker_adapter.py (plan line in parentheses): __init__ :109 (:93); _apply_slippage :483 (:436); market fill `self._apply_slippage(base_price, order.side)` :227 in _handle_market (:199); limit fills :296 and :730 (:261, :617); _check_sl_tp :773-789, SHORT branch :783-787, logic unchanged (:654-669); synthetic exit `_apply_slippage(trigger_price, exit_side)` :797 (:678); OrderFilledEvent( :837 (:715).
- Constructor params on develop: initial_balance, slippage_percent, fill_delay_ms, currency, event_bus, commission_model, contract_spec. All callers use keywords (core/infra/brokers/broker_factory.py:43-51, engine/backtest/backtest_sandbox_app_service.py:119-129), so a last-position spread param is safe.
- The package src/pocketquant/backtest/ is gone (folded into engine):
  - RunBacktestCommand: src/pocketquant/engine/backtest/backtest_command_service.py:23. Fields: strategy_id, symbol, interval, start_date, end_date, initial_capital, slippage_bps, commission_bps, parameters, name. The config dict maps "strategy_code": cmd.strategy_id at :79.
  - _config_from_dict :47 and run_single :63 in engine/backtest/backtest_dispatch.py. The sandbox.create_broker(...) call is at :100-105.
  - BacktestConfig: src/pocketquant/core/domain/backtest/config.py:11 (a dataclass; plan cited backtest/models/backtest_config.py:9).
  - create_broker: engine/backtest/backtest_sandbox_app_service.py:112. It builds PaperBrokerAdapter directly, not through BrokerFactory.
- Run API still valid: POST /api/v1/backtest/run 202 (app/routes/backtest.py:57), body {"request_id"} (EnqueueBacktestResponse, engine/backtest/backtest_query_service.py:36-37), GET /{run_id} :79, GET /{run_id}/trades :125; status started|finished|failed (core/domain/backtest/entities.py:30). Collection backtest_runs: core/common/constants.py:16.
- Subscriptions: POST /api/v1/strategies/{code}/subscriptions app/routes/strategy.py:70 (plan :69); body becomes AddSymbolCommand(strategy_id, symbol, interval); list :106, start :113, stop :122; actual_state at core/domain/subscription/entities.py:48.
- Integrity: POST /api/v1/market-data/integrity/check in app/routes/integrity.py (included at app/routes/market_data.py:12). Body: symbol, interval, days_back (1..90). Returns missing_count and misaligned_count (engine/market_data/app_services/integrity_jobs.py:87,107). It already resolves the calendar through TradingCalendarFactory.for_symbol, so "calendar-aware since Phase 03" is already true on develop.
- Log cap: app container deploy/compose.prod.yml:60-64 (10m x 3), container name at :34 (plan said :56-60).
- SSE routes: GET /api/v1/market-data/bars/stream/{symbol} (app/routes/market_data_ohlcv.py:95), GET /api/v1/quotes/stream/{symbol} (app/routes/market_data_quotes.py:77).
- Not on develop (future-phase artifacts, expected): docs/journals/*-exness-api-spike.md, scripts/backfill/policy_bars.py (develop has scripts/backfill/binance_bars.py), scripts/code_metrics.py, any "exness" string in src, docs, deploy, tests, scripts.
- tests/baseline/ is not tracked (git ls-files tests/baseline is empty). pyproject.toml:147 comment cites tests/baseline/test_package_layout_contract.py, also absent (already stale on develop). The OpenAPI snapshot in T8.2 exists only if Phase 02 creates it on develop.
- Existing test locations: tests/backtest_test/engine/ (paper limit, order events, trade emission) and tests/core_test/infra/brokers/ (test_paper_broker_sl_tp_fill.py, paper_broker_commission_test.py, test_paper_broker_contract_spec.py, paper_broker_futures_accounting_test.py). The planned new test location is valid; test_paper_broker_sl_tp_fill.py is the existing SL/TP baseline.

### Per task
- T8.1: rename to PaperBrokerAdapter and paper_broker_adapter.py, use the new lines above. Step 1 "git switch master" needs the branch policy (section 3). The spread logic maps 1:1.
- T8.2: edit engine/backtest/backtest_command_service.py, engine/backtest/backtest_dispatch.py, core/domain/backtest/config.py (domain), engine/backtest/backtest_sandbox_app_service.py. spread on RunBacktestCommand is a public OpenAPI change. scripts/recompute_backtest_costs.py exists on develop; whether it needs spread is unchecked.
- T8.3: "just test" is single-zone (justfile:47-49). Develop also has "just test-tz" (justfile:53-62: UTC, Asia/Ho_Chi_Minh, America/Chicago). The CI tests job runs the same 3 zones plus lint-imports and pytest tests/ -q (cicd.yml:22-60). The verdict check stays valid: deploy/vps/11-verify.sh:263 prints "=== Verdict: $verdict ($passed/$total passed, $warned warnings, $failed failures) ===". Do not hard-code "19 checks" (docs say 19; the script has more check calls).
- T8.4: depends on Phase 06 policy_bars.py and sync_policy.EXNESS_CALENDARS. Develop calendars sit behind TradingCalendarFactory (core/infra/calendars/) and core/domain/market_data/trading_calendar_port.py; the BTCUSD-minimum command must use whatever calendar port serves Exness after the reshape. See Risks on symbol seeding.
- T8.5: unchanged.
- T8.6: default_broker_config is at app/di/execution.py:72-81 (keys initial_balance, slippage_bps, commission_bps, api_key, api_secret, passphrase, demo; no spread). The BrokerFactory paper branch reads slippage_bps, commission_bps, contract_spec (broker_factory.py:33-51). The "no spread in paper week" claim is correct. The no-deploy confirmation must name both branches.
- T8.7: exness_ws.circuit_breaker_open and exness_ws.reconnecting are Phase 06 events. Valid only while nothing deploys.
- T8.8: unchanged.

## 2. Phase 09 and docs

| Plan citation | Develop truth |
|---|---|
| system-architecture "Where Does X Live?" :455 | :486 |
| "Real-Time Streaming" :553 | :627 |
| "Broker and Middleware" :573 | :651 |
| "Dependency Injection (Dishka)" :604 | :682 |
| row "Dishka DI container (6 providers)" :472 | :511 |
| row "Background sync job registration" :483 | :522 |
| "6 providers" sentence :606 | :684 |
| async callout ~:630 | :710. Develop code-standards.md:610 is still the heading "Async Suspension Points - Await Is Preemption"; the step 7 rename only applies after Phase 05 |
| deployment.md "Environment and Credentials" :62 | :62 correct; env table rows :87-97 (already has TRADINGVIEW_* rows) |
| README.md line 3 Binance-only | line 3 correct |
| README.md line 11 adapter list | line 11 is the core/ line listing brokers, binance, scheduler, http (anchor correct; TradingView also missing) |
| project-overview-pdr.md:260 "Max 200 LOC per file" | :260 correct |
| project-overview-pdr.md:340 link #routes--services | :342 |
| docs/README.md:12 code-standards row ("file-size rules") | :12 correct |
| CLAUDE.md:21 code-standards pointer | now CLAUDE.md:23; still lists schema, testing, perf and cites the "Class Naming by Layer" and "Naming Principles" headings, which Phase 05 must keep or update |
| scripts/README.md | 23 lines; lists audit_bar_quality, migrate_symbol_asset_class, seed_index_futures, backfill/binance_bars; omits recompute_backtest_costs.py; its Conventions block says one-time migrations are not retained after execution |
| code-standards.md sections 8 and 14 | 17 H2 on develop. "Configuration and Secrets" H2 at :760. No "Sync policy pattern" heading. "6. Provider Pattern" :105, "9.5. Integrity Repair Flow" :189 |
| 11-verify.sh verdict | :263, matches |
| cicd.yml jobs | tests (3-zone matrix), build-app, build-web, cleanup-tags, deploy |

Per task:
- T9.1 NEEDS RESHAPE. Anchors shift by +31 to +78. The develop "Where Does X Live?" table already has rows for provider routing adapters (:505), TradingView, trading calendar port, CME Globex calendar and asset class, so Exness rows extend those. app/di/ holds container.py, core.py, execution.py, infrastructure.py, market_data.py, persistence.py, services.py, trading_services.py, backtest_worker.py; the doc list at :686 names CoreProvider, PersistenceProvider, InfrastructureProvider, MarketDataProvider, ExecutionProvider. The "3 providers" target is a Phase 04 outcome to re-derive for develop. The grep for sync_internals -> 0 holds only after Phase 03/04 (engine/market_data/sync_internals/ still exists).
- T9.2 NEEDS RESHAPE. Add Exness rows in the existing Var / Required / Notes table. A new Deep History Backfill section fits near "2-Year Bar Re-Sync" :205 and "Sync Gap Repair" :219. The step 2 line for migrate_okx_market_data.py conflicts with the scripts/README one-time-migration convention. Deploy wording in deployment.md:7,10,22,25,34,120,152 already names develop.
- T9.3 NEEDS RESHAPE. "Keep the H2 count at 14" is impossible (17 now, Phase 05 rewrites). The touchpoint list is written for a suffix registry; the real develop touchpoints are below.
- T9.4 NEEDS RESHAPE (branch policy).

### Existing docs on routing, calendars, add-a-provider (affect P09 and P05 doc tasks)
- docs/system-architecture.md:173 (symbol has asset_class, calendar_id, contract_spec), :505 (provider routing adapters), :686 (IDataProviderPort as RoutingDataProviderAdapter over binance and tradingview; realtime quote port as RoutingRealtimeQuoteAdapter), :688-690 (jobs and data-lag service), plus the calendar, TradingView and asset-class rows in "Where Does X Live?".
- No docs/ file has an add-a-provider procedure. scripts/README.md carries the seeding-order rule for non-crypto symbols.
- Real develop add-a-provider touchpoints (from source): Settings.market_data_providers and symbol_provider_overrides (core/config.py); resolve_provider_ids (core/domain/market_data/provider_routing_domain_service.py); SymbolProviderResolver (core/infra/market_data/symbol_provider_resolver.py); the two routing adapters (routing_data_provider_adapter.py, routing_realtime_quote_adapter.py); the provider health map for binance and tradingview in app/main_extensions.py:320-328 via provider_health_check.py; a calendar through TradingCalendarFactory; symbol seeding.
- Routing on develop is by asset_class plus overrides, not by exchange suffix. The plan text "policy_for resolves by exchange suffix only" conflicts with this and must be reconciled before Phase 09 prose is written.

## 3. CI deploy trigger and branch policy
- cicd.yml:3-10: on.push.branches [master, develop]; paths-ignore docs/**, plans/**, **/*.md, LICENSE; plus workflow_dispatch.
- Deploy job condition: github.ref is refs/heads/develop or refs/heads/master, or event is workflow_dispatch. REMOTE_ROOT is /opt/pocketquant, and both branches use the same get-vps-config action and VPS. The concurrency group "deploy" has cancel-in-progress, so a push to either branch cancels an in-flight deploy.
- docs/deployment.md:7,22 already say "git push origin develop (or master)" and "deploy runs on develop/master/workflow_dispatch". docs/project-overview-pdr.md:407 still says "master - Production-ready code" (stale under the new policy).
- Plan text to change to the branch policy:
  - plan.md frontmatter "branch: master"; Dependencies bullet 4 ("A push to master deploys to prod").
  - P08 T8.1 step 1 (git switch master and pull), T8.3 step 4, T8.6 step 1 question, T8.7 step 3, Stop-and-ask.
  - P09 T9.1 step 1, T9.4 step 3 (switch to master, ff-only merge, push origin master) and its Verify (git log origin/master -1).
  - D6 "every CI deploy 11-verify.sh verdict": say which branch runs count.
- Paper-week no-deploy: any non-docs push to master or develop, or a workflow_dispatch, recreates the container and breaks T8.7 coverage. Docs-only pushes (the T9.4 ship) are skipped by paths-ignore.
- (inference) Keeping master identical to develop means pushing the same commit to both branches; a non-docs commit then deploys twice, the second cancelling the first via the concurrency group.

## 4. plan.md items
- D3: replace PaperBroker.spread with PaperBrokerAdapter spread.
- D6: "just test" is single-zone; CI is 3 zones. State "green in all three zone legs (just test-tz)". The T2.6 venue baseline is a future artifact.
- D7: valid only after reconciling the registry design with the develop asset-class provider map; new text must extend existing routing docs.
- Paper-week metric: unchanged; event name from Phase 06.
- Test matrix: tests/app_test/integration/, tests/engine_test/, tests/scripts/ exist (tests/scripts holds only rubric). tests/baseline/ and tests/core_test/infra/exness/ are new.
- Dependencies: bullet 4 needs the branch policy.

## Risks
- Exness symbols need symbols documents (asset_class, calendar_id, contract_spec). Without them SymbolProviderResolver assumes CRYPTO_SPOT and routes to a crypto venue (module docstring in symbol_provider_resolver.py). Backtests also call symbol_lookup.contract_spec and calendar_factory.for_symbol (backtest_dispatch.py:77,117). No plan step seeds them; scripts/seed_index_futures.py is the pattern.
- BacktestConfig is domain code and RunBacktestCommand is an API contract.
- tests/baseline, scripts/code_metrics.py and policy_bars.py depend on earlier phases being re-planned for develop.

## Unresolved Questions
- Does the suffix-only policy_for registry replace the develop asset-class provider map or sit on top of it?
- Ship Phase 09 through develop only with master fast-forwarded afterwards, or push both?
