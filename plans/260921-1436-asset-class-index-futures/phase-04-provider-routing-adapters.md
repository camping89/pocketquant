---
phase: 4
title: "Provider Routing Adapters and Settings"
status: pending
priority: P1
effort: "1d"
dependencies: [2]
---

## Context

(Advice Phase 3.) Today DI binds exactly one `IDataProviderPort` (`app/di/infrastructure.py:30-31`)
and one `IRealtimeQuoteProviderPort` (`app/di/market_data.py:34-36`). This phase
replaces both bindings with routing adapters that hold a `dict[provider_id, adapter]`
and resolve the provider list per symbol from the symbol's asset class plus optional
per-symbol overrides. Because the routing adapters implement the SAME ports,
`SyncService`, `fetch_with_retry`, `WsSubscriptionAppService`, `QuoteAppService` and
`TrackedSymbolBackfillService` need no edits — that is G4.

This phase ships with Binance as the ONLY registered provider, so the crypto path must
stay byte-for-byte unchanged.

## Tasks

### Task 1 — Provider settings

**Goal.** The provider map and per-symbol overrides are configuration, not code.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — `Settings` (lines 30-74).

**Steps.**
1. Add a `# Market-data provider routing` section after `enable_jobs` (line 57):
   ```python
   market_data_providers: dict[AssetClass, list[str]] = {
       AssetClass.CRYPTO_SPOT: ["binance"],
       AssetClass.CRYPTO_PERP: ["binance"],
       AssetClass.INDEX_FUTURE: ["tradingview"],
   }
   symbol_provider_overrides: dict[str, list[str]] = {}
   ```
2. Import `AssetClass` from `pocketquant.core.domain.shared.enums`. `core.config`
   importing `core.domain` is allowed by every import-linter contract; confirm with
   `uv run lint-imports`.
3. pydantic-settings parses a `dict`-typed field from a JSON string in the
   environment, so `MARKET_DATA_PROVIDERS={"index_future":["tradingview","binance"]}`
   works with no custom parser.
4. Document both field names (names only, never values) in `README.md` next to the
   existing env-var list, and in `docs/system-architecture.md` under `## Configuration`.

**Success criteria.** The settings load with defaults and accept a JSON override.

**Verify.** `MARKET_DATA_PROVIDERS='{"index_future":["tradingview","binance"]}' uv run python -c "
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import AssetClass
print(Settings().market_data_providers[AssetClass.INDEX_FUTURE])"` prints `['tradingview', 'binance']`.

---

### Task 2 — Pure provider-resolution function

**Goal.** One place decides which providers serve a symbol, shared by both routing
adapters.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/provider_routing_domain_service.py`.
- Symbol: `resolve_provider_ids`.

**Steps.**
1. Write a pure module-level function, following the precedent of
   `bar_builder_domain_service.py` (module of pure functions, no class):
   ```python
   def resolve_provider_ids(
       symbol: str,
       asset_class: AssetClass,
       provider_map: dict[AssetClass, list[str]],
       overrides: dict[str, list[str]],
   ) -> list[str]:
       """Ordered provider ids for a composite symbol: primary first, then fallbacks."""
   ```
2. Behaviour: an override keyed by the upper-cased composite symbol wins outright;
   otherwise return `provider_map.get(asset_class, [])`. Return a NEW list, never the
   stored one, so a caller cannot mutate settings.
3. Add no I/O and no logging — this is domain code covered by the purity AST test.

**Success criteria.** Overrides win, the map is the fallback, and an unmapped asset
class returns an empty list.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_provider_routing.py -q` exits 0 and prints `4 passed` (test written in Task 3).

---

### Task 3 — Provider-resolution tests

**Goal.** The routing rule is pinned before any adapter depends on it.

**Target files and symbols.**
- New file `tests/core_test/unit/domain/market_data/test_provider_routing.py`.

**Steps.**
1. Write 4 tests: `test_asset_class_map_is_used`,
   `test_symbol_override_beats_asset_class`,
   `test_override_lookup_is_case_insensitive` (pass `es1!:cme_mini`, expect the
   override registered under `ES1!:CME_MINI`),
   `test_unmapped_asset_class_returns_empty_list`.

**Success criteria.** 4 tests pass.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_provider_routing.py -q` exits 0 and prints `4 passed`.

---

### Task 4 — `RoutingDataProviderAdapter`

**Goal.** REST history is fetched from the symbol's primary provider, falling back to
the next on exception or empty result.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/market_data/` with `__init__.py`.
- New file `src/pocketquant/core/infra/market_data/routing_data_provider_adapter.py`.
- Symbol: `RoutingDataProviderAdapter`, implementing
  `pocketquant.core.domain.market_data.data_provider_port.IDataProviderPort`.

**Steps.**
1. Constructor takes `providers: dict[str, IDataProviderPort]`, `settings: Settings`
   and `symbol_lookup: SymbolLookupHelper`.
2. Implement `fetch_ohlcv(symbol, interval, n_bars)`:
   - resolve the symbol record via `symbol_lookup.get(symbol)`; use
     `AssetClass.CRYPTO_SPOT` when it is missing (a brand-new symbol being synced for
     the first time);
   - call `resolve_provider_ids(...)`;
   - iterate the ids in order; skip an id with no registered adapter after logging one
     WARNING naming the id (guard with a `set` so it is one-shot per id);
   - call the adapter; on a non-empty result return it immediately;
   - on an exception or an empty list, log DEBUG `market_data.routing.fallback` with
     the symbol, the failed provider id and the next one, then continue;
   - after the last provider, return `[]`.
   Do not log per-attempt at INFO — `fetch_ohlcv` runs once per symbol per interval
   per minute.
3. Implement `search_symbols(query)` by delegating to the FIRST provider registered in
   `market_data_providers[AssetClass.CRYPTO_SPOT]`, and document that symbol search
   stays single-provider for now.
4. Implement `close()` by awaiting `close()` on every registered provider, collecting
   exceptions and re-raising the first one after all have been attempted.

**Success criteria.** A fake primary that raises falls through to a fake secondary
that returns bars.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_routing_data_provider_adapter.py -q` exits 0 and prints `6 passed` (tests written in Task 6).

---

### Task 5 — `RoutingRealtimeQuoteAdapter`

**Goal.** WS subscriptions are delegated to the one provider that owns each symbol.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/market_data/routing_realtime_quote_adapter.py`.
- Symbol: `RoutingRealtimeQuoteAdapter`, satisfying the 9-member
  `IRealtimeQuoteProviderPort` Protocol declared at
  `src/pocketquant/core/domain/market_data/realtime_quote_provider_port.py:15-58`:
  `last_tick_at`, `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`,
  `is_connected`, `subscription_count`, `subscriptions`.

**Steps.**
1. Constructor takes `providers: dict[str, IRealtimeQuoteProviderPort]`,
   `settings: Settings` and `symbol_lookup: SymbolLookupHelper`. Keep
   `self._owner: dict[str, str]` mapping composite symbol to the provider id that owns
   its subscription.
2. `subscribe(symbol, callback)`: resolve the ordered ids and use ONLY THE FIRST one.
   Do NOT fall back. Two realtime providers streaming the same symbol would
   double-count ticks in `BarBuilderDomainService`. Record the owner and return the
   child's subscription key.
3. `unsubscribe(symbol)`: look up the owner, delegate, and drop the owner entry.
4. `connect()` / `disconnect()`: `await` every child in turn; on `disconnect`, swallow
   and log each child's exception at WARNING so one bad child cannot block shutdown.
5. `run_forever()`: `await asyncio.gather(*(p.run_forever() for p in providers.values()))`.
   Let `CancelledError` propagate so lifespan teardown works.
6. `is_connected()`: True when at least one child is connected.
7. `subscription_count`: sum of the children's counts.
8. `subscriptions`: a merged dict built from every child, so
   `WsSubscriptionAppService._reconcile` (which reads `provider.subscriptions.keys()`
   at `ws_subscription_app_service.py:68`) sees the full desired set.
9. `last_tick_at`: implement as a property returning the maximum non-`None`
   `last_tick_at` across children, or `None`. The Protocol declares it as a plain
   attribute; a read-only property satisfies structural typing.

**Success criteria.** `isinstance(adapter, IRealtimeQuoteProviderPort)` is True (the
Protocol is `@runtime_checkable`).

**Verify.** `uv run python -c "
from pocketquant.core.domain.market_data.realtime_quote_provider_port import IRealtimeQuoteProviderPort
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import RoutingRealtimeQuoteAdapter
print(hasattr(RoutingRealtimeQuoteAdapter, 'run_forever'), issubclass(RoutingRealtimeQuoteAdapter, IRealtimeQuoteProviderPort) if hasattr(IRealtimeQuoteProviderPort, '_is_runtime_protocol') else 'n/a')"` prints a line starting with `True`.

---

### Task 6 — Routing adapter tests

**Goal.** Fallback, no-fallback-for-realtime and the merged subscription view are
pinned.

**Target files and symbols.**
- New package dir `tests/core_test/infra/market_data/`.
- New file `tests/core_test/infra/market_data/test_routing_data_provider_adapter.py`.
- New file `tests/core_test/infra/market_data/test_routing_realtime_quote_adapter.py`.

**Steps.**
1. In the REST test module, write 6 tests with `unittest.mock.AsyncMock` fakes:
   `test_primary_result_returned`, `test_exception_falls_through_to_secondary`,
   `test_empty_result_falls_through_to_secondary`,
   `test_all_providers_exhausted_returns_empty_list`,
   `test_unknown_provider_id_is_skipped`,
   `test_symbol_override_selects_the_overridden_provider_first`.
2. In the realtime test module, write 4 tests:
   `test_subscribe_uses_only_the_first_provider`,
   `test_unsubscribe_reaches_the_owning_provider`,
   `test_subscriptions_merges_children`,
   `test_last_tick_at_is_the_max_across_children`.
3. In `test_symbol_override_selects_the_overridden_provider_first`, assert with
   `git diff --stat` reasoning in a comment that the override needed no change in
   `engine/` or `app/` — this is the G4 evidence.

**Success criteria.** 10 tests pass.

**Verify.** `uv run pytest tests/core_test/infra/market_data/ -q` exits 0 and prints `10 passed`.

---

### Task 7 — Bind the routing adapters in DI, Binance only

**Goal.** The container hands every consumer a routing adapter, with Binance as the
sole registered provider.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` — `InfrastructureProvider.get_data_provider`
  (lines 29-31).
- `src/pocketquant/app/di/market_data.py` — `MarketDataProvider.get_realtime_quote_provider`
  (lines 34-36).

**Steps.**
1. In `infrastructure.py`, change `get_data_provider` to build the map and wrap it:
   ```python
   @provide(scope=Scope.APP)
   def get_data_provider(
       self, settings: Settings, symbol_lookup: SymbolLookupHelper
   ) -> IDataProviderPort:
       return RoutingDataProviderAdapter(
           providers={"binance": BinanceAdapter(settings=settings)},
           settings=settings,
           symbol_lookup=symbol_lookup,
       )
   ```
2. In `market_data.py`, do the same for the realtime port with
   `{"binance": BinanceWebSocketAdapter()}`. Keep the existing
   `# type: ignore[return-value]` comment style for the Protocol return.
3. Do NOT register a TradingView provider here — Phase 5 adds it.
4. Verify no other file constructs `BinanceAdapter` or `BinanceWebSocketAdapter`
   outside DI and tests.

**Success criteria.** The whole DI graph still resolves and no consumer changed.

**Verify.** `uv run pytest tests/app_test/integration/ -q && test "$(grep -rln 'BinanceAdapter(\|BinanceWebSocketAdapter(' src/ | grep -vc '^src/pocketquant/app/di/')" = "0"` exits 0.

---

### Task 8 — Phase gate: crypto unchanged through the routing layer

**Goal.** Prove the routing layer is transparent before TradingView enters.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite plus ruff, `pyright src` and the import contracts.
2. Deploy to the VPS and observe one `sync_1m` cycle. Compare `synced_count` and
   `bars_inserted` in `job_history` against the pre-deploy run at the same minute of
   the previous hour.
3. Confirm the WS quote feed still delivers ticks: `GET /api/v1/market-data/quotes/BTCUSDT%3ABINANCE`
   returns a timestamp within the last 60 seconds.

**Success criteria.** Identical counts and a live quote.

**Verify.** `uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run lint-imports` exits 0.

## Todo

- [ ] Task 1 — Provider settings
- [ ] Task 2 — Pure provider-resolution function
- [ ] Task 3 — Provider-resolution tests
- [ ] Task 4 — `RoutingDataProviderAdapter`
- [ ] Task 5 — `RoutingRealtimeQuoteAdapter`
- [ ] Task 6 — Routing adapter tests
- [ ] Task 7 — Bind the routing adapters in DI, Binance only
- [ ] Task 8 — Phase gate: crypto unchanged through the routing layer

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Routing adapter breaks the `IRealtimeQuoteProviderPort` structural match and DI fails at startup | Medium | High | Task 5's Verify plus Task 7's integration-test run |
| `symbol_lookup` read on the WS subscribe path adds latency to reconcile | Low | Low | 60s TTL cache; reconcile runs every 5s over a handful of symbols |
| A new symbol has no `symbols` document yet, so routing defaults to crypto | Medium | Low | Task 4 step 2 documents the default explicitly; seeding in Phase 5 writes the record before the first sync |
| Settings JSON key casing does not match the enum values | Medium | Medium | Task 1's Verify uses the lower-case enum value `index_future` |

**Rollback.** Revert Task 7 alone to restore the direct Binance bindings; the routing
adapters stay in the tree unused and harmless.

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

