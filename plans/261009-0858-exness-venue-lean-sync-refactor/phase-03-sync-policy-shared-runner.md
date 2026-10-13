---
phase: 3
title: "Sync policy registry, shared runner and suffix routing (Binance)"
status: superseded
priority: P1
effort: 5d
dependencies: [2]
---

# Phase 03: Sync policy registry, shared runner and suffix routing (Binance as proving provider)

## Context Links
- Advice §2.2, §2.3 (fold `sync_internals`) and §3 (keep the Binance cascade as a policy flag).
- Current code: `engine/market_data/app_services/sync_jobs.py` (729 LOC), `engine/market_data/app_services/integrity_jobs.py` (137), `engine/market_data/sync_service.py` (181; `__init__` :34 takes `provider: IDataProvider`, `sync_one` :48, `sync_bulk` :130, `_fail` :173), `engine/market_data/sync_internals/{anomaly_log,bar_alignment,bar_filters,provider_fetch,responses}.py` and `engine/market_data/sync_dtos.py`.
- Provider injection points today (all replaced by the policy registry in this phase):
  - `src/pocketquant/app/di/infrastructure.py:30` `get_data_provider` → `BinanceClient`
  - `src/pocketquant/app/di/market_data.py:22` `provide(SyncService)`, `:31` `get_realtime_quote_provider` → `BinanceWebSocketClient`, `:36-56` `QuoteAppService` and `WsSubscriptionManager` factories
  - `src/pocketquant/app/di/services.py:27` `provide(TrackedSymbolBackfillService)` (`engine/market_data/tracked_symbols_backfill.py:88` takes `provider`)
  - `src/pocketquant/app/market_data/app_services/quote_app_service.py:26,102` and `ws_subscription_manager.py:35,66,76,91`
  - `src/pocketquant/app/main_extensions.py:214` (`stop_quote_feed` resolves `IRealtimeQuoteProvider`) and `sync_jobs.py:522` (`sync_verify_cascade` resolves `IDataProvider`)
- Composite-symbol split copies: `src/pocketquant/core/infra/binance/binance_client.py:62` and `binance_websocket_client.py:83`. `COMPOSITE_SYMBOL_RE` lives in `src/pocketquant/core/domain/symbol/entities.py:19` and `COMPOSITE_SYMBOL_PATTERN` at :24.
- `:OKX` market data today: `binance_client.py:62` drops the suffix, so a tracked `X:OKX` is silently fetched from Binance.
- Unique indexes that decide migration collisions: `bars` (symbol, interval, datetime) `bar_repository.py:287`; `sync_status` (symbol, interval) `sync_status_repository.py:99`; `symbols` (symbol) `symbol_repository.py:44`; `tracked_symbols` (symbol) `tracked_symbol_repository.py:59`; `subscriptions` (strategy_code, symbol, interval) `subscription_repository.py:99`.
- Prod backup pattern: `docs/deployment.md:205` (`mongodump` inside `pocketquant-mongodb`), restore at `docs/deployment.md:130`.
- Jobs store: `src/pocketquant/core/infra/scheduling/scheduler.py:61-63` (`MongoDBJobStore`, collection `apscheduler_jobs`). The only job routes are `GET /api/v1/system/jobs/{job_id}/runs` and `/{job_id}/stats` (`app/routes/system_jobs.py:30,50`); there is no list route.
- Wiring: `src/pocketquant/app/main.py:31-33,51` (`set_sync_container`), `src/pocketquant/app/main_extensions.py:178` (`register_sync_jobs` import), `src/pocketquant/app/routes/integrity.py:9`.
- Test patch targets that must keep working: `pocketquant.engine.market_data.sync_service.fetch_with_retry|filter_new_bars|drop_misaligned_bars`, `sync_service.asyncio` (previously `provider_fetch.asyncio`), and the module attributes `_container` and `cascade_for_symbol` on the runner module.

<!-- Updated: Validation Session 1 - policy carries its providers; routing strictly by suffix; no router module; :OKX migration -->
## Goal
One `SyncPolicy` per exchange, held in a `SyncPolicies` registry that DI builds. Each policy carries its own data provider and quote provider, and `policy_for(symbol)` resolves a composite symbol strictly by its exchange suffix. `SyncService`, `QuoteAppService`, `WsSubscriptionManager`, `TrackedSymbolBackfillService` and the runner resolve providers only through the policy. There is no router module and no fallback to another exchange; an unknown suffix logs once and is skipped. One shared runner executes `fetch → align → persist → cascade? → integrity → repair`. The Binance policy reproduces today's behaviour exactly, which the Phase 02 characterization test proves. `:OKX` market-data symbols are migrated to `:BINANCE` under backup and user approval before the deploy, and OKX keeps no data policy.

File hops against G2, counted honestly. Manual sync: `routes/market_data_sync.py` (merged into `routes/market_data.py` in Phase 04) → `sync_service.py` → `sync_policy.py`. Scheduled sync: `sync_runner.py` → `sync_policy.py` → `sync_service.py`. Both flows read in 3 files; the port implementation (`binance_client.py`), the repository and, for integrity and cascade, `bar_integrity.py` and `cascade_aggregator.py` are leaf calls behind named functions.

## Files to Create or Modify
- Create: `src/pocketquant/engine/market_data/sync_policy.py`, `src/pocketquant/engine/market_data/sync_runner.py`, `src/pocketquant/engine/market_data/bar_integrity.py`, `scripts/migrate_okx_market_data.py`
- Create tests: `tests/engine_test/market_data/test_sync_policy.py`, `tests/app_test/unit/market_data/test_ws_subscription_manager_policies.py`, `tests/scripts/test_migrate_okx_market_data.py`
- Modify:
  - `src/pocketquant/core/domain/symbol/entities.py` (add `split_composite`)
  - `src/pocketquant/core/infra/binance/binance_client.py`, `src/pocketquant/core/infra/binance/binance_websocket_client.py` (use `split_composite`; nothing else)
  - `src/pocketquant/engine/market_data/sync_service.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`
  - `src/pocketquant/app/market_data/app_services/quote_app_service.py`, `src/pocketquant/app/market_data/app_services/ws_subscription_manager.py`
  - `src/pocketquant/app/di/infrastructure.py`, `src/pocketquant/app/di/market_data.py`
  - `src/pocketquant/app/main.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/routes/integrity.py`
  - `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` (the docstring line that names `sync_jobs.sync_1m`) and `src/pocketquant/core/infra/persistence/repositories/job_history_repository.py` (the module docstring line that names `sync_jobs._run_sync`)
- Delete: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `.../app_services/integrity_jobs.py`, `src/pocketquant/engine/market_data/sync_dtos.py` and `src/pocketquant/engine/market_data/sync_internals/` (all 6 files)
- Modify tests (imports, patch targets and construction wiring only, no assertion changes except where a step says so):
  - `tests/app_test/integration/app_factory.py`
  - `tests/app_test/integration/test_sync_backfill_gap_fill.py`
  - `tests/app_test/integration/test_sync_pipeline_characterization.py` (import line and fixture wiring only)
  - `tests/app_test/integration/test_di_resolution_characterization.py` (the two provider assertions, see T3.9)
  - `tests/app_test/unit/di/test_di_data_provider.py`
  - `tests/app_test/market_data/test_integrity_jobs_repair_source.py`, `tests/app_test/market_data/test_sync_jobs_source_labels.py`
  - `tests/app_test/test_sync_jobs_phase.py`
  - `tests/app_test/unit/handlers/sync/conftest.py`, `.../sync/test_bar_filters.py`, `.../sync/test_provider_fetch.py`, `.../sync/test_no_progress_tracking.py` (:78)
  - `tests/app_test/unit/market_data/test_sync_jobs_catchup.py`, `tests/app_test/unit/market_data/test_sync_verify_cascade.py`, `tests/app_test/unit/market_data/test_quote_app_service.py` (:46)
  - `tests/engine_test/market_data/test_sync_service.py` (:84)

<!-- Updated: Execution 2026-10-11 - deviations recorded during cook; kongming counsel on each failed Verify -->
## Execution notes
- T3.1–T3.13 are done and the T3.13 gate is green: `just test` 685 passed, ruff clean, pyright 0 errors, 7 contracts kept, venue 79 (baseline 79), `tests/baseline` 9 passed, no function over 60 lines.
- T3.14: the prod inventory reports `total_okx_docs: 0`, so T3.15–T3.17 are skipped and `user-preconditions.md` records `OKX migration: nothing to migrate`.
- T3.18: c245ba9 is on master. CI run 38142141699 is green with verdict `HEALTHY (20/20 passed, 0 warnings, 0 failures)`. The first post-deploy `sync_1m` is `completed` (3 inserted, 300 fetched), the jobs check prints `True 0`, and all 3 prod tracked symbols are `:BINANCE`.
- Deviations from the task text, each needed to meet a stated Verify condition:
  - T3.5: the step 4 folds left `sync_one` at 93 lines. `sync_one` keeps the policy guard, the started log, the `syncing` status and the error path, and `_sync_with(provider, symbol, request)` runs fetch → persist → `_record_progress`. Calls run in the same order as before. `test_no_progress_tracking.py` used the reversed symbol `BINANCE:BTCUSDT`, which now has no policy; that test data was changed to `BTCUSDT:BINANCE`, with no assertion change.
  - T3.6/T3.7: `_verify_one_symbol` is renamed `verify_one_symbol`, because pyright `reportPrivateUsage` rejects the cross-module call from `sync_runner`.
  - T3.7: the `_run_recorded` body takes `doc_id`, because `_sync_symbols` records detail rows against it. `_cascade` and `_log_verify_summary` are split out, and the `register_sync_jobs` comment is condensed, to keep every function ≤ 60 lines.
  - T3.8: `asyncio.create_task` rejects a `gather` future, so `QuoteAppService.start` runs the gather inside `_run_quote_feeds()`. `WsSubscriptionManager._reconcile` maps each desired symbol to its policy's quote provider.
  - The `scheduler.py` docstring now names `sync_runner.py`. `test_sync_policy.py` rebinds `sync_policy.logger` per test (the same `cache_logger_on_first_use` isolation as `handlers/sync/conftest.py`).

## Tasks

### T3.1 Branch
- **Goal:** Isolate the refactor.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c refactor/sync-policy-runner`
- **Success criteria:** The branch is checked out.
- **Verify:** `git branch --show-current` prints `refactor/sync-policy-runner`.

<!-- Updated: Validation Session 1 - one composite-symbol split helper -->
### T3.2 One composite-symbol split helper
- **Goal:** Exactly one function splits `{code}:{exchange}`; the Binance copies call it.
- **Target files and symbols:** `src/pocketquant/core/domain/symbol/entities.py` → `split_composite(symbol: str) -> tuple[str, str]`; `binance_client.py:62`, `binance_websocket_client.py:83`
- **Steps:**
  1. Below `COMPOSITE_SYMBOL_PATTERN`, add:
     ```python
     def split_composite(symbol: str) -> tuple[str, str]:
         code, _, exchange = symbol.strip().upper().partition(":")
         return code, exchange
     ```
  2. In `binance_client.py:62` and `binance_websocket_client.py:83`, replace `code = symbol.split(":")[0] if ":" in symbol else symbol` with `code = split_composite(symbol)[0]` and import `split_composite` from `pocketquant.core.domain.symbol.entities`. `validate_symbol` already upper-cases, so the result is identical.
- **Success criteria:** No other split copy remains in `src`.
- **Verify:** `grep -rn 'split(":")' src | wc -l` prints `0`. The venue command from Phase 02 T2.6 passes with the same `passed` count as the `venue:` line of `reports/baseline-gate.txt`.

<!-- Updated: Validation Session 1 - registry carrying providers; session calendar; no live_source/rate_budget; one calendar accessor -->
### T3.3 `sync_policy.py`
- **Goal:** A declarative policy type that carries its providers, a session-based market calendar, the registry and the Binance policy factory.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_policy.py` → `MarketCalendar`, `ALWAYS_OPEN`, `SyncPolicy`, `SyncPolicies`, `binance_policy`
- **Steps:**
  1. Write this module (the code is load-bearing):
     ```python
     _WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

     def _week_minute(text: str, *, round_up: bool) -> int:
         day, clock = (part.strip() for part in text.split(","))
         hours, minutes, seconds = (int(x) for x in clock.split(":"))
         minute = _WEEKDAYS.index(day) * 1440 + hours * 60 + minutes
         return minute + 1 if round_up and seconds else minute

     @dataclass(frozen=True)
     class MarketCalendar:
         sessions: tuple[tuple[int, int], ...] | None = None

         @classmethod
         def from_week_sessions(cls, sessions: Sequence[Mapping[str, str]]) -> MarketCalendar:
             return cls(sessions=tuple(
                 (_week_minute(s["week_start_time"], round_up=False),
                  _week_minute(s["week_end_time"], round_up=True))
                 for s in sessions if s.get("trade_mode", "enabled") == "enabled"
             ))

         def is_open(self, ts: datetime) -> bool:
             if self.sessions is None:
                 return True
             utc = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
             minute = utc.weekday() * 1440 + utc.hour * 60 + utc.minute
             return any(
                 start <= minute < end if start <= end else (minute >= start or minute < end)
                 for start, end in self.sessions
             )

     ALWAYS_OPEN = MarketCalendar()

     @dataclass(frozen=True)
     class SyncPolicy:
         exchange: str
         data_provider: IDataProvider
         quote_provider: IRealtimeQuoteProvider | None
         poll_intervals: tuple[Interval, ...]
         poll_n_bars: int
         cascade: bool
         cascade_lookback_minutes: int
         integrity_intervals: tuple[Interval, ...]
         backfill_n_bars: int
         poll_time_cap_s: float | None = None
         history_days: Mapping[Interval, int | None] = field(default_factory=dict)
         calendars: Mapping[str, MarketCalendar] = field(default_factory=dict)

     class SyncPolicies:
         def __init__(self, policies: Iterable[SyncPolicy]) -> None:
             self._by_exchange = {p.exchange: p for p in policies}
             self._warned: set[str] = set()

         def __iter__(self) -> Iterator[SyncPolicy]:
             return iter(self._by_exchange.values())

         def policy_for(self, symbol: str) -> SyncPolicy | None:
             exchange = split_composite(symbol)[1]
             policy = self._by_exchange.get(exchange)
             if policy is None and exchange not in self._warned:
                 self._warned.add(exchange)
                 logger.warning("market_data.unknown_exchange", exchange=exchange, symbol=symbol.upper())
             return policy

         def market_calendar(self, symbol: str) -> MarketCalendar:
             policy = self.policy_for(symbol)
             if policy is None:
                 return ALWAYS_OPEN
             return policy.calendars.get(split_composite(symbol)[0], ALWAYS_OPEN)

         def quote_providers(self) -> list[IRealtimeQuoteProvider]:
             return [p.quote_provider for p in self if p.quote_provider is not None]
     ```
  2. Add `def binance_policy(data_provider: IDataProvider, quote_provider: IRealtimeQuoteProvider | None) -> SyncPolicy` returning `SyncPolicy(exchange="BINANCE", data_provider=data_provider, quote_provider=quote_provider, poll_intervals=(Interval.MINUTE_1,), poll_n_bars=100, cascade=True, cascade_lookback_minutes=100, integrity_intervals=(Interval.MINUTE_1, Interval.MINUTE_5, Interval.MINUTE_15, Interval.HOUR_1, Interval.HOUR_4, Interval.DAY_1, Interval.WEEK_1), backfill_n_bars=5000)`. Binance keeps `poll_time_cap_s=None`, empty `history_days` and empty `calendars` (always open).
  3. Imports: stdlib, `pocketquant.core.common.logging.get_logger`, `pocketquant.core.domain.market_data.interfaces`, `pocketquant.core.domain.shared.enums.Interval` and `pocketquant.core.domain.symbol.entities.split_composite`. Nothing from `core.infra`.
  4. `market_calendar` is the single calendar accessor; do not add a second one.
- **Success criteria:** Lookup is by suffix only, with no fallback.
- **Verify:** no verification needed; T3.4 covers this module.

<!-- Updated: Validation Session 1 - registry, unknown-suffix and session-calendar tests -->
### T3.4 Policy tests
- **Goal:** Pin the lookup, the Binance values and the calendar maths.
- **Target files and symbols:** `tests/engine_test/market_data/test_sync_policy.py`
- **Steps:**
  1. `split_composite(" btcusdt:binance ") == ("BTCUSDT", "BINANCE")` and `split_composite("BTCUSDT") == ("BTCUSDT", "")`.
  2. Build `policies = SyncPolicies([binance_policy(data_provider=fake_data, quote_provider=fake_quotes)])`. Assert `policies.policy_for("btcusdt:binance").data_provider is fake_data`, `policies.policy_for("BTCUSDT:OKX") is None` and `policies.policy_for("nocolon") is None`.
  3. Under `structlog.testing.capture_logs()`, call `policies.policy_for("A:OKX")` three times and `policies.policy_for("B:OKX")` once; exactly one captured event has `event == "market_data.unknown_exchange"` and `exchange == "OKX"`.
  4. Assert every `binance_policy` field equals the values in T3.3 step 2, and `policies.quote_providers() == [fake_quotes]`.
  5. Calendar from the spec example `[{"trade_mode":"enabled","week_start_time":"Mon, 00:00:00","week_end_time":"Fri, 23:59:59"}]`: Fri 23:59 UTC open, Sat 00:00 closed, Sun 12:00 closed, Mon 00:00 open. A daily break: sessions `Mon 00:00:00–Mon 21:59:59` and `Mon 23:00:00–Tue 21:59:59` give Mon 22:30 closed and Mon 23:00 open. A wrap session `Sun, 22:00:00`–`Mon, 01:00:00` gives Sun 23:00 open and Mon 00:30 open. A `trading_disabled` session is ignored. A naive datetime is treated as UTC.
  6. `ALWAYS_OPEN.is_open` is True on a Saturday, and `policies.market_calendar("BTCUSDT:BINANCE") is ALWAYS_OPEN`.
- **Success criteria:** The tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - SyncService resolves the provider through the policy -->
### T3.5 Fold `sync_internals` and `sync_dtos` into `sync_service.py`, provider through the policy
- **Goal:** A manual sync is readable in one file, the provider comes from the symbol's policy, and the existing test patch targets keep working.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_service.py`. It holds `SyncSymbolCommand`, `BulkSyncCommand`, `SyncResponse`, module functions `fetch_with_retry`, `filter_new_bars`, `drop_misaligned_bars` and `emit_no_progress`, constants `_BACKOFF_SECONDS`, `_TIME_BUDGET_SECONDS` and `_STUCK_STREAK_THRESHOLD`, and `class SyncService(policies: SyncPolicies, cache, bar_repository, symbol_repository, sync_status_repository)`.
- **Steps:**
  1. Move the three Pydantic models from `sync_dtos.py` into `sync_service.py` verbatim, with fields and descriptions unchanged, because the OpenAPI snapshot depends on them. Remove the re-export `__all__` comment.
  2. Move `fetch_with_retry` (from `provider_fetch.py`), `filter_new_bars` and `drop_misaligned_bars` (from `bar_filters.py`), and `emit_no_progress` with `_STUCK_STREAK_THRESHOLD` (from `anomaly_log.py`) into `sync_service.py` as module-level functions with the same names and bodies. Import `asyncio` and `time` at module level.
  3. Inline `has_aligned_bar` (from `bar_alignment.py`) into `fetch_with_retry` as `any(b.datetime is not None and is_bar_aligned(b.datetime, interval) for b in records)`.
  4. Inline `build_success` (from `responses.py`) into the success return of `SyncService.sync_one`. Fold the private one-call helpers `_persist_bars`, `_get_bar_stats`, `_mark_completed` and `_invalidate_cache` into their single call sites. Keep `_fail`, which has two callers.
  5. Replace the constructor parameter `provider: IDataProvider` with `policies: SyncPolicies` (stored as `self._policies`). At the top of `sync_one`, after `symbol = request.symbol.upper()`, add: `policy = self._policies.policy_for(symbol)`; when it is None, return `SyncResponse(symbol=symbol, interval=interval.value, status="error", message=f"no data provider for exchange {split_composite(symbol)[1]}", bars_synced=0)` without touching `sync_status`. Pass `policy.data_provider` to `fetch_with_retry`.
  6. If `sync_one` exceeds 60 lines, move the progress-bookkeeping branch (the `SyncProgressTracker.decide` through `emit_no_progress` block) into `async def _record_progress(self, symbol, interval, *, inserted, bars_fetched, filtered_misaligned, filtered_existing, attempts, latest_bar) -> None`.
  7. Keep `sync_bulk` as is.
  8. Delete `src/pocketquant/engine/market_data/sync_internals/` and `src/pocketquant/engine/market_data/sync_dtos.py`.
  9. In the test files listed under "Files to Create or Modify", replace imports from `...sync_internals.bar_filters`, `...sync_internals.provider_fetch` and `...sync_internals` with `pocketquant.engine.market_data.sync_service` (or `import ... sync_service as provider_fetch` where a module object is patched). In `tests/app_test/unit/handlers/sync/conftest.py`, rebind the logger only on `sync_service`.
  10. In `test_no_progress_tracking.py:78` and `tests/engine_test/market_data/test_sync_service.py:84`, replace `provider=provider` with `policies=SyncPolicies([binance_policy(data_provider=provider, quote_provider=None)])`; any `"provider": provider` key in the returned fixture dict stays.
- **Success criteria:** No reference to `sync_internals` or `sync_dtos` remains, and an unknown suffix returns an error response instead of raising.
- **Verify:** `grep -rn "sync_internals\|sync_dtos" src tests scripts | wc -l` prints `0`. `.venv/Scripts/python.exe -m pytest tests/app_test/unit/handlers tests/engine_test/market_data/test_sync_service.py tests/app_test/integration/test_sync_backfill_gap_fill.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - integrity routes take the calendar from the registry -->
### T3.6 `bar_integrity.py`
- **Goal:** Integrity checks, repair and cascade verification are calendar-aware and live in one module; slots outside trading sessions are ignored.
- **Target files and symbols:** `src/pocketquant/engine/market_data/bar_integrity.py`. Symbols: `_group_gaps`, `check_integrity(symbol, interval, bar_repo, days_back=7, calendar=ALWAYS_OPEN)`, `repair_integrity(symbol, interval, bar_repo, sync_service, *, source, days_back=7, calendar=ALWAYS_OPEN)`, `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `_diff_pct`, `compare_bar_fields` and `_verify_one_symbol`.
- **Steps:**
  1. Move `_group_gaps`, `check_integrity` and `repair_integrity` from `integrity_jobs.py` verbatim.
  2. In `check_integrity`, change only the expected-grid line to `expected = {t for t in (start + i * step for i in range(int((end - start) / step))) if calendar.is_open(t)}`. `repair_integrity` passes `calendar` through to both `check_integrity` calls.
  3. Move `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT`, `DIVERGENCE_ALERT_FRACTION`, `_diff_pct`, `compare_bar_fields` and `_verify_one_symbol` from `sync_jobs.py` verbatim.
  4. In `src/pocketquant/app/routes/integrity.py`, import from `bar_integrity`, add `policies: FromDishka[SyncPolicies]` to `integrity_check` and `integrity_repair`, and pass `calendar=policies.market_calendar(symbol)` to both calls. Dishka parameters do not appear in OpenAPI.
  5. In `test_integrity_jobs_repair_source.py` and `test_sync_verify_cascade.py`, change the imports to `pocketquant.engine.market_data.bar_integrity`.
- **Success criteria:** For `ALWAYS_OPEN` the behaviour is identical.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/market_data/test_integrity_jobs_repair_source.py tests/app_test/unit/market_data/test_sync_verify_cascade.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - runner resolves SyncPolicies; per-policy time cap so one venue cannot delay another; no rate warning -->
### T3.7 `sync_runner.py`, the shared runner
- **Goal:** One module schedules and executes every provider's sync through its policy, keeping job ids, triggers, sources, history records and log event names. A slow venue cannot delay an earlier policy's `sync_1m` work.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_runner.py`. Symbols: `_MODULE = "pocketquant.engine.market_data.sync_runner"`, `CATCHUP_TARGETS`, `_container`, `set_container`, `_get_container`, `_ms_since`, `_tracked_policies`, `_run_recorded`, `_record_detail`, `_sync_symbols`, `_capped`, `sync_1m`, `sync_verify_cascade`, `sync_backfill`, `sync_integrity`, `sync_repair`, `enqueue_missed_catchups` and `register_sync_jobs`. Import `cascade_for_symbol` by name at module level, because tests monkeypatch it.
- **Steps:**
  1. `CATCHUP_TARGETS`, `set_container`, `_get_container`, `_ms_since`, `enqueue_missed_catchups` and `register_sync_jobs` are copied from `sync_jobs.py` with `_MODULE` updated. Keep the same 5 `add_cron_job` calls with identical kwargs, and the log `market_data.registered_sync_jobs` with `job_count=5`.
  2. `async def _tracked_policies(repo, policies: SyncPolicies) -> list[tuple[str, SyncPolicy]]` returns `(ts.symbol, policy)` for each tracked symbol whose `policies.policy_for(ts.symbol)` is not None. Unknown suffixes are skipped; the registry already logs them once.
  3. `async def _run_recorded(name, history_repo, body) -> None` is the single owner of the copied `record_start`, `record_finish` and failure blocks. `body` is a zero-arg coroutine function that returns `tuple[int, int] | None`. With totals, call `record_finish(status="completed", duration_ms, total_inserted, total_fetched)`. Without totals, call `record_finish(status="completed", duration_ms)`. On an exception, record `failed` with `error=str(exc)` and re-raise. Keep the same warning log names.
  4. `async def _record_detail(history_repo, doc_id, job_name, symbol, interval, *, result=None, error=None)` records one detail row. It covers both existing call shapes: success from `result`, error with zeros. Any exception is swallowed with the warning `job_history.record_detail_failed`.
  5. `async def _sync_symbols(job_name, targets, source, sync_service, history_repo, doc_id) -> tuple[int, int]` ports `_sync_by_intervals`. `targets` is `list[tuple[str, tuple[Interval, ...], int]]`, meaning (symbol, intervals, n_bars). Keep the same `started`, `skipped` (no tracked symbols), `symbol_failed` and `completed` logs, the iteration order (symbol, then interval), and the "raise first error at end" rule.
  6. `async def _capped(policy: SyncPolicy, coro) -> tuple[int, int]`: when `policy.poll_time_cap_s` is None, return `await coro`; otherwise `await asyncio.wait_for(coro, policy.poll_time_cap_s)`, and on `TimeoutError` log a warning `market_data.sync.poll_time_cap_hit` with `exchange` and `cap_s` and return `(0, 0)`.
  7. `sync_1m()` resolves exactly `JobHistoryRepository`, `SyncService`, `TrackedSymbolRepository`, `BarRepository` and `SyncPolicies`. Inside `_run_recorded("sync_1m", ...)`, iterate the policies in registry order. For each policy, build `targets = [(s, p.poll_intervals, p.poll_n_bars) for s in that policy's tracked symbols if policies.market_calendar(s).is_open(now)]`, run `_capped(p, _sync_symbols(..., SOURCE_REST_SYNC_1M, ...))`, then, when `p.cascade`, call `cascade_for_symbol(s, lookback_minutes=p.cascade_lookback_minutes, bar_repo=bar_repo)` for each of its symbols with the same `sync_1m.cascade_failed` and `sync_1m.cascade_summary` logs. Sum and return the totals. With only Binance registered this is the same call sequence as today.
  8. `sync_backfill()`: targets are `(s, p.integrity_intervals, p.backfill_n_bars)` with source `SOURCE_REST_BACKFILL`, no calendar filter, all policies in one `_sync_symbols` call (as today).
  9. `sync_integrity()` resolves `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository` and `SyncPolicies`. For each `(s, p)` and each `p.integrity_intervals`, it calls `check_integrity(s, interval, bar_repo, calendar=policies.market_calendar(s))` and emits the same `integrity.issues_found` warning.
  10. `sync_repair()` resolves those four plus `SyncService` and calls `repair_integrity(..., source=SOURCE_REST_REPAIR, calendar=policies.market_calendar(s))` with the same `integrity.repaired` log.
  11. `sync_verify_cascade()` resolves `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository` and `SyncPolicies`. It iterates only over symbols whose policy has `cascade=True`, using `symbol = s.upper()` and `provider=p.data_provider` for `_verify_one_symbol`. The skip, ok, `rest_empty`, `cascade_empty` and `divergence_alert` logs stay identical.
  12. Every function stays ≤ 60 lines.
- **Success criteria:** The Binance behaviour is unchanged.
- **Verify:** no verification needed; T3.10 covers this module.

<!-- Updated: Validation Session 1 - quotes, WS subscriptions and tracked backfill resolve through the policy -->
### T3.8 Quotes, WS subscriptions and tracked backfill through the policy
- **Goal:** Every remaining provider consumer resolves its provider from the symbol's policy, and an unknown suffix is skipped without a raise loop.
- **Target files and symbols:** `QuoteAppService.__init__` and `start` (`quote_app_service.py:21-33,95-103`), `WsSubscriptionManager.__init__` and `_reconcile` (`ws_subscription_manager.py:33-100`), `TrackedSymbolBackfillService.__init__`, `_direct` and `_cascade` (`tracked_symbols_backfill.py:86-160`), `stop_quote_feed` (`main_extensions.py:204-215`).
- **Steps:**
  1. `QuoteAppService(settings, cache, bar_manager, policies: SyncPolicies)`: store `self._policies`. `start()` creates `self.ws_task = asyncio.create_task(asyncio.gather(*(qp.run_forever() for qp in self._policies.quote_providers()), return_exceptions=True))`. Remove the `provider` attribute.
  2. `WsSubscriptionManager(policies: SyncPolicies, tracked_symbol_repo, quote_app_service, interval_s=5.0)`. In `_reconcile`:
     - `desired = {s for s in (ts.symbol.upper() for ts in tracked) if (p := self._policies.policy_for(s)) is not None and p.quote_provider is not None}`;
     - `current = {k for qp in self._policies.quote_providers() for k in qp.subscriptions}`;
     - subscribe through `self._policies.policy_for(symbol_key).quote_provider.subscribe(...)`; unsubscribe through the provider whose `subscriptions` holds the key.
     - Keep the delay, the log names and the per-symbol try/except.
  3. `TrackedSymbolBackfillService(policies: SyncPolicies, bar_repository)`. In `run`, resolve `policy = self._policies.policy_for(symbol)`; when None, log `backfill.unknown_exchange` and return `{"persisted_count": 0, "mode_used": mode}`. Pass `policy.data_provider` into `_direct` and `_cascade` (add a `provider` parameter to both).
  4. `stop_quote_feed`: replace `provider = await container.get(IRealtimeQuoteProvider)` and `await provider.disconnect()` with a loop over `(await container.get(SyncPolicies)).quote_providers()` that awaits `disconnect()` on each.
  5. Update `tests/app_test/unit/market_data/test_quote_app_service.py:46` to pass `policies=SyncPolicies([binance_policy(data_provider=MagicMock(), quote_provider=provider)])` instead of `provider=provider`.
  6. Write `tests/app_test/unit/market_data/test_ws_subscription_manager_policies.py`: with tracked `["BTCUSDT:BINANCE", "ETHUSDT:OKX"]` and a fake quote provider for BINANCE, three `_reconcile()` calls subscribe only `BTCUSDT:BINANCE` once, never call any provider for `ETHUSDT:OKX`, and `capture_logs()` holds exactly one `market_data.unknown_exchange` event.
- **Success criteria:** No consumer holds a provider of its own.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/unit/market_data/test_quote_app_service.py tests/app_test/unit/market_data/test_ws_subscription_manager_policies.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - one DI factory builds the registry -->
### T3.9 DI builds the policy registry
- **Goal:** DI provides `SyncPolicies` and no longer provides `IDataProvider` or `IRealtimeQuoteProvider` on their own.
- **Target files and symbols:** `src/pocketquant/app/di/infrastructure.py` (`get_data_provider` :30 becomes `get_sync_policies`), `src/pocketquant/app/di/market_data.py` (`get_realtime_quote_provider` :31 removed; `get_quote_service` and `get_ws_subscription_manager` take `policies: SyncPolicies`)
- **Steps:**
  1. In `infrastructure.py`, replace `get_data_provider` with `@provide(scope=Scope.APP) def get_sync_policies(self, settings: Settings) -> SyncPolicies` returning `SyncPolicies([binance_policy(data_provider=BinanceClient(settings=settings), quote_provider=BinanceWebSocketClient())])`. This keeps the same `BinanceWebSocketClient` instance for quotes and WS subscriptions (APP scope).
  2. In `market_data.py`, delete `get_realtime_quote_provider`; `get_quote_service(settings, cache, bar_manager, policies)` and `get_ws_subscription_manager(policies, tracked_symbol_repo, quote_app_service)` pass `policies`. `sync_service = provide(SyncService, ...)` and `services.py:27` stay, because dishka auto-wires the new `policies` parameter.
  3. `tests/app_test/unit/di/test_di_data_provider.py`: call `InfrastructureProvider().get_sync_policies(mock_settings)` and assert `policy_for("BTCUSDT:BINANCE").data_provider` is a `BinanceClient` and satisfies `IDataProvider`, and `.quote_provider` is a `BinanceWebSocketClient` that satisfies `IRealtimeQuoteProvider`.
  4. `tests/app_test/integration/test_di_resolution_characterization.py`: replace the `IDataProvider` and `IRealtimeQuoteProvider` assertions with: `SyncPolicies` resolves; its `policy_for("BTCUSDT:BINANCE")` has a `BinanceClient` data provider and a `BinanceWebSocketClient` quote provider; `policy_for("BTCUSDT:OKX") is None`. All other assertions stay.
- **Success criteria:** The registry is the only source of providers.
- **Verify:** `grep -rnE "def get_data_provider|def get_realtime_quote_provider|container\.get\((IDataProvider|IRealtimeQuoteProvider)\)" src | wc -l` prints `0`. `.venv/Scripts/python.exe -m pytest tests/app_test/unit/di tests/app_test/integration/test_di_resolution_characterization.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - characterization may change only its import line and fixture wiring -->
### T3.10 Rewire callers, delete job modules, migrate tests
- **Goal:** Nothing imports the old modules, and the characterization test passes with only its import line and fixture wiring edited.
- **Target files and symbols:** `app/main.py`, `app/main_extensions.py`, the test files listed above, and the deleted `sync_jobs.py` and `integrity_jobs.py`.
- **Steps:**
  1. `app/main.py`: `from pocketquant.engine.market_data.sync_runner import set_container as set_sync_container`.
  2. `app/main_extensions.py` `start_background_jobs`: `from pocketquant.engine.market_data.sync_runner import register_sync_jobs`. Update the docstring word `sync_jobs` to `sync_runner`.
  3. Test imports and wiring:
     - `test_sync_pipeline_characterization.py`: change the `register_sync_jobs` import line to `sync_runner`; build `policies = SyncPolicies([binance_policy(data_provider=fake, quote_provider=None)])`, pass `policies=policies` to `SyncService`, and map `SyncPolicies` (instead of `IDataProvider`) in `FakeContainer`. No assertion changes.
     - `test_sync_jobs_source_labels.py`: use `from pocketquant.engine.market_data import sync_runner as sync_jobs`, which keeps the monkeypatch lines identical; add `SyncPolicies` to its fake container map with a Binance policy over a `MagicMock` provider.
     - `test_sync_jobs_phase.py` and `test_sync_jobs_catchup.py`: import from `sync_runner`.
     - `app_factory.py`: change the `set_sync_container` import to `sync_runner`.
  4. Docstrings: in `cascade_aggregator.py` replace `sync_jobs.sync_1m` with `sync_runner.sync_1m`, and in `job_history_repository.py` replace `sync_jobs._run_sync` with `sync_runner._run_recorded`.
  5. Delete `src/pocketquant/engine/market_data/app_services/sync_jobs.py` and `.../app_services/integrity_jobs.py`.
- **Success criteria:** The old modules are gone and every test passes.
- **Verify:**
  - `grep -rn "app_services.sync_jobs\|app_services.integrity_jobs\|app_services import sync_jobs" src tests scripts | wc -l` prints `0`.
  - `test ! -e src/pocketquant/engine/market_data/sync_internals && test ! -e src/pocketquant/engine/market_data/app_services/sync_jobs.py && echo gone` prints `gone`.
  - `git diff master -- tests/app_test/integration/test_sync_pipeline_characterization.py | grep -E "^[-+] *assert" | wc -l` prints `0`.
  - `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py tests/app_test/market_data tests/app_test/unit tests/app_test/test_sync_jobs_phase.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - guarded :OKX → :BINANCE data migration script -->
### T3.11 `:OKX` market-data migration script
- **Goal:** One script inventories `:OKX` references and, only when explicitly approved, renames them to `:BINANCE` or drops the `:OKX` twin of an existing `:BINANCE` document.
- **Target files and symbols:** `scripts/migrate_okx_market_data.py` → `UNIQUE_KEYS`, `inventory(db) -> dict`, `apply(db) -> dict`, `main(argv: list[str] | None = None) -> int`; `tests/scripts/test_migrate_okx_market_data.py`
- **Steps:**
  1. Use synchronous `pymongo.MongoClient(os.environ["MONGODB_URL"])[os.environ["MONGODB_DATABASE"]]` (both are in the container env). The script must run when piped through stdin (`python - --inventory`).
  2. `UNIQUE_KEYS = {"bars": ("interval", "datetime"), "sync_status": ("interval",), "symbols": (), "tracked_symbols": (), "subscriptions": ("strategy_code", "interval")}`. Every other collection is rename-only.
  3. `inventory(db)`: for each name in `db.list_collection_names()` except `apscheduler_jobs` and names starting with `system.`, count `okx_docs = {"symbol": {"$regex": ":OKX$"}}` and `binance_docs = {"symbol": {"$regex": ":BINANCE$"}}`. For collections in `UNIQUE_KEYS`, count `collisions`: `:OKX` docs whose renamed key (`symbol` with `:OKX` replaced by `:BINANCE`, plus the listed fields) already exists, using one `$lookup` aggregation per distinct `:OKX` symbol. Return `{"collections": {name: {"okx_docs", "binance_docs", "collisions"}}, "total_okx_docs": n}` for collections with `okx_docs > 0` or `binance_docs > 0`.
  4. `apply(db)`: for each collection with `:OKX` docs and for each distinct `:OKX` symbol `S` with target `T`: in `UNIQUE_KEYS` collections, delete the colliding `:OKX` docs (the same `$lookup`, projecting `_id`), then `update_many({"symbol": S}, {"$set": {"symbol": T}})`. Return `{name: {"renamed": n, "dropped": m}}`.
  5. CLI: `--inventory` prints the inventory JSON. `--apply --approved` prints the apply JSON; `--apply` without `--approved` prints `refusing: --approved is required` and exits 2. Nested fields such as `job_history.details[].symbol` and Redis cache keys are out of scope and stay as historical records.
  6. Test with the session `mongo_container` fixture from `tests/conftest.py` and a fresh database name: seed `bars` with `X:OKX`/`X:BINANCE` twins for one datetime and an `X:OKX`-only datetime, plus one `tracked_symbols` `X:OKX`. Assert `inventory` reports `okx_docs == 2`, `collisions == 1` for `bars`; `main(["--apply"])` returns 2; after `apply`, `bars` has `dropped == 1`, `renamed == 1`, no `:OKX` docs remain, and `tracked_symbols` holds `X:BINANCE`.
- **Success criteria:** The script never writes without `--approved` and never violates a unique index.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_migrate_okx_market_data.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - Windows-safe metrics output -->
### T3.12 Size check of the refactored modules
- **Goal:** No god-functions in the new code.
- **Target files and symbols:** `scripts/code_metrics.py` output
- **Steps:**
  1. `uv run python scripts/code_metrics.py --out .cache/metrics.json`
- **Success criteria:** No function over 60 lines in `sync_service.py`, `sync_runner.py`, `bar_integrity.py` or `sync_policy.py`.
- **Verify:** `uv run python -c "import json;d=json.load(open('.cache/metrics.json'));bad=[f for f in d['functions_over_60'] if any(k in f for k in ('sync_service.py','sync_runner.py','bar_integrity.py','sync_policy.py'))];print(bad)"` prints `[]`.

### T3.13 Phase gate
- **Goal:** Full green, and the venue pass count is unchanged.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. Run the venue command from Phase 02 T2.6, `... -q 2>&1 | tail -n 1`.
  6. `.venv/Scripts/python.exe -m pytest tests/baseline -q` (OpenAPI and route snapshots, with no regeneration).
- **Success criteria:** Everything is green and identical.
- **Verify:**
  - Step 1 exits 0 with `passed` and no `failed`.
  - Step 2 prints `All checks passed!`.
  - Step 3 reports `0 errors`.
  - Step 4 shows `Contracts: 7 kept, 0 broken.`.
  - Step 5's `passed` count equals the number on the `venue:` line of `reports/baseline-gate.txt`.
  - Step 6 exits 0.

<!-- Updated: Validation Session 1 - read-only prod inventory before the strict-suffix deploy -->
### T3.14 Inventory `:OKX` references in prod (read-only)
- **Goal:** Know exactly what the migration would touch before anything is written.
- **Target files and symbols:** VPS container `pocketquant-app`, local `.cache/okx-inventory-before.json`
- **Steps:**
  1. Set `KEY` and `HOST` as in Phase 01 T1.8 step 1.
  2. `ssh -i "$KEY" "$HOST" "docker exec -i pocketquant-app python - --inventory" < scripts/migrate_okx_market_data.py > .cache/okx-inventory-before.json`
  3. If `total_okx_docs` is `0`, append `OKX migration: nothing to migrate` to `reports/user-preconditions.md` and skip T3.15–T3.17.
- **Success criteria:** The inventory is recorded locally.
- **Verify:** `uv run python -c "import json;d=json.load(open('.cache/okx-inventory-before.json'));print(isinstance(d['total_okx_docs'],int))"` prints `True`.

<!-- Updated: Validation Session 1 - mongodump backup before any write -->
### T3.15 Back up the affected collections
- **Goal:** A restorable copy of every collection the inventory lists exists before the migration runs.
- **Target files and symbols:** VPS `/opt/pocketquant/backups/`
- **Steps:**
  1. `STAMP=$(date -u +%Y%m%d%H%M)`. For each collection name `C` in `.cache/okx-inventory-before.json` → `collections` with `okx_docs > 0`, run:
     ```bash
     ssh -i "$KEY" "$HOST" "mkdir -p /opt/pocketquant/backups && docker exec pocketquant-mongodb sh -c 'mongodump --uri=\"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin\" --collection=C --archive --gzip' > /opt/pocketquant/backups/okx-migration-$STAMP-C.archive"
     ```
  2. `ssh -i "$KEY" "$HOST" "ls -l /opt/pocketquant/backups/okx-migration-$STAMP-*.archive"` and save the output to `.cache/okx-backups.txt`.
- **Success criteria:** One non-empty archive per affected collection.
- **Verify:** The number of lines in `.cache/okx-backups.txt` equals the number of collections with `okx_docs > 0`, and every size column (field 5) is greater than `100`: `awk '$5<=100' .cache/okx-backups.txt | wc -l` prints `0`.

<!-- Updated: Validation Session 1 - explicit user approval for the data migration -->
### T3.16 Stop and ask: approve the migration
- **Goal:** The migration runs only with the user's recorded approval.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`
- **Steps:**
  1. Show the user the per-collection `okx_docs`, `binance_docs` and `collisions` from `.cache/okx-inventory-before.json` and the archive list from `.cache/okx-backups.txt`. Ask verbatim: "Approve migrating these :OKX market-data documents to :BINANCE? Where a :BINANCE twin already exists, the :OKX document is deleted; every other :OKX document is renamed. The backups listed above restore the previous state."
  2. Append `OKX migration: approved` or `OKX migration: declined` to `user-preconditions.md`. On `declined`, STOP: shipping this phase would make the `:OKX` symbols unknown, so the user decides how to proceed.
- **Success criteria:** Approval is recorded.
- **Verify:** `grep -c "OKX migration: approved" plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` prints `1`.

<!-- Updated: Validation Session 1 - apply and verify counts -->
### T3.17 Apply the migration and verify counts
- **Goal:** No `:OKX` market-data document remains, and the `:BINANCE` counts add up.
- **Target files and symbols:** `.cache/okx-migration-apply.json`, `.cache/okx-inventory-after.json`
- **Steps:**
  1. `ssh -i "$KEY" "$HOST" "docker exec -i pocketquant-app python - --apply --approved" < scripts/migrate_okx_market_data.py > .cache/okx-migration-apply.json`
  2. `ssh -i "$KEY" "$HOST" "docker exec -i pocketquant-app python - --inventory" < scripts/migrate_okx_market_data.py > .cache/okx-inventory-after.json`
- **Success criteria:** Every `:OKX` document was renamed or dropped as approved.
- **Verify:** `uv run python -c "import json;b=json.load(open('.cache/okx-inventory-before.json'))['collections'];a=json.load(open('.cache/okx-inventory-after.json'));r=json.load(open('.cache/okx-migration-apply.json'));print(a['total_okx_docs']==0 and all(a['collections'].get(c,{}).get('binance_docs',0)==b[c]['binance_docs']+r.get(c,{}).get('renamed',0) for c in b))"` prints `True`.

<!-- Updated: Validation Session 1 - jobs verified through apscheduler_jobs and /runs, not a list route -->
### T3.18 Ship and verify jobs in prod
- **Goal:** The runner is live, and the persisted APScheduler jobs point at the new module.
- **Target files and symbols:** git, Mongo collection `apscheduler_jobs`, `GET /api/v1/system/jobs/{job_id}/runs`
- **Steps:**
  1. Stage with `git add -A src tests scripts plans/261009-0858-exness-venue-lean-sync-refactor` and check `git status --short` shows only files listed in this phase plus plan-directory status updates.
  2. `git commit -m "refactor(market-data): resolve providers through per-exchange SyncPolicy and run sync jobs from one shared runner"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
  4. Wait about 3 minutes after the deploy turns green, then run:
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     curl -s "http://localhost:41921/api/v1/system/jobs/sync_1m/runs?limit=1"
     EOF
     ```
  5. Check the persisted jobs:
     ```bash
     ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"import os;from pymongo import MongoClient;db=MongoClient(os.environ['MONGODB_URL'])[os.environ['MONGODB_DATABASE']];docs=list(db.apscheduler_jobs.find({},{'job_state':1}));ids={d['_id'] for d in docs};names={'sync_1m','sync_verify_cascade','sync_backfill','sync_integrity','sync_repair'};stale=sum(b'app_services.sync_jobs' in bytes(d['job_state']) or b'app_services.integrity_jobs' in bytes(d['job_state']) for d in docs);print(names<=ids, stale)\""
     ```
- **Success criteria:** `sync_1m` completes in prod, all 5 job ids are persisted, and no persisted job references the old module path. A one-time APScheduler log `Unable to restore job` for the old func refs is expected and harmless, because `replace_existing=True` re-registers each id.
- **Verify:**
  - `gh run watch` exits 0, and the CI log `=== Verdict:` line contains `, 0 failures)`.
  - The step 4 output contains `"status":"completed"`.
  - The step 5 output is `True 0`.

## Verification
T3.4–T3.10 (policy, consumer, DI and characterization tests), T3.11 (migration script), T3.12 (function size), T3.13 (gate plus unchanged snapshots and venue count), T3.17 (migration counts) and T3.18 (prod jobs).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- The `:OKX` → `:BINANCE` prod data migration: it never runs without the T3.15 backup and the T3.16 approval.
- A step would delete Binance or OKX code (this phase only edits two Binance split lines).
- A test failure stays unexplained.

## Risks
- **Silent behaviour drift**, such as a changed iteration order, source label or n_bars (likelihood M, impact H). Mitigation: T2.4 asserts the exact provider calls, sources and history fields; only its import line and fixture wiring may change, which T3.10 checks.
- **`:OKX` symbols stop syncing at deploy** (M/M). Mitigation: T3.14–T3.17 migrate them before the deploy; the old code fetches `:BINANCE` from Binance just as well, so there is no gap.
- **A migration collides with a unique index** (M/H). Mitigation: colliding `:OKX` twins are counted, shown to the user and dropped before the rename; backups exist per collection.
- **A slow venue delays `sync_1m`** (M/M; `max_instances=1` skips the next run). Mitigation: policies run in registry order, Binance first, and later policies carry `poll_time_cap_s`.
- **Stale persisted func refs in `apscheduler_jobs`** (L/M). Mitigation: APScheduler drops unrestorable jobs on load, and registration re-adds the same ids; T3.18 step 5 proves no stale ref remains.

## Rollback
`git revert` the merge commit and push. On the next boot the old module re-registers the same job ids with `replace_existing=True`. The data migration is not reverted by code: restore with `docker exec -i pocketquant-mongodb mongorestore --archive --gzip --drop < /opt/pocketquant/backups/okx-migration-<STAMP>-<C>.archive` per collection (`docs/deployment.md:130` pattern), and only if the user asks.

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
