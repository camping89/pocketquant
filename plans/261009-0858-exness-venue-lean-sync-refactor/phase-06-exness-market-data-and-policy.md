---
phase: 6
title: "Exness market data and quotes"
status: in-progress
priority: P1
effort: 7d
dependencies: [5]
---

# Phase 06: Exness market data and quotes

<!-- Updated: 2026-10-13 develop reshape - suffix routing, calendar port, sync jobs, spike facts, new 429 rule -->
## Develop status
- Base branch: `develop` (worktree `D:/w/_me/algotrading/pq-develop`; the local branch `develop-sync` is renamed `develop` at the phase commit and tracks `origin/develop`). Work ships with `git push origin develop`, which runs tests only. Since `9b547ca` only a `master` push builds and deploys, so prod is reached by the fast-forward release `git push origin develop:master` (branch model in `docs/deployment.md`). The release and its deploy are approved (coordinator, 2026-10-19).
- Develop's design wins over the old master plan: there is no `sync_policy.py`, `sync_runner.py`, `SyncPolicy`, `MarketCalendar` or `tests/baseline/`. Exness plugs into the existing pieces: a suffix (`:EXNESS`) routed by `RoutingDataProviderAdapter` and `RoutingRealtimeQuoteAdapter`, a calendar behind `ITradingCalendarPort`, and the unchanged sync jobs in `engine/market_data/app_services/sync_jobs.py` (1m REST every minute plus cascade, 1d/1w by REST in `sync_backfill`, integrity, repair, data lag).
- The spike is done (`docs/journals/2026-10-13-exness-api-spike.md`, fixtures in `tests/core_test/infra/exness/fixtures/`). Its facts are inputs here and replace every earlier assumption about hosts, names, limits and the WS.

## Progress 2026-10-16 (stopped at stop-and-ask, nothing committed)
- T6.1–T6.17 are implemented and their Verify steps pass in the working tree of `develop-sync` (base `7b68c82`). T6.18 steps 1–4 pass: lint-imports keeps 8 contracts, ruff check and pyright report 0 errors, and `just test` fails only the 4 known Windows `time.tzset` tests.
- Deviations: `ExnessSessionCalendarAdapter.session_open(d)` is UTC midnight (the D1 candle open; the first open instant would make integrity expect a Sunday 22:01:30 bar that never exists), and `sessions()` counts a date only when it has an open second inside `[start, end]`. The T6.7 grep now uses `--include='*.py'` because pytest writes matching `.pyc` files. `test_provider_routing.py::test_exactly_the_registered_providers_have_defaults` also pins the provider set and now includes `exness`.
- Decisions that were escalated on 2026-10-16:
  - T6.18 step 5 fails: `tiny_share 0.4876 > 0.48`, `delegations 85 > 77`. The base sat exactly at the ceiling, and most new tiny functions are plan-mandated API or port members, so it cannot pass without padding.
  - W1 is verified Sunday-aligned: a read-only prod call returned W1 candles at Sunday 00:00Z for XAUUSD, EURUSD and BTCUSD.
  - DST: a review cites Exness docs saying sessions shift one hour when US DST ends on 2026-11-01 (unverified; the page returned HTTP 403).
- Review follow-ups: quiet the `websockets` logger in `core/common/logging/setup.py` (it logs the handshake headers, including the API key, at DEBUG); reject an empty idempotency key on order ops (Phase 07); EURUSD tickless rollover minutes will show as integrity misses.

## User decisions 2026-10-19 (binding; resume from here)
- Ratchet: the user said "we can be flexible for this, no need hard rule, also keep in mind we need to be KISS and clean". Do not pad or contort code to pass the counter. Keep the code KISS and clean, then raise `[tool.code-metrics]` to the measured values in its own commit and state the new ceiling in the phase report.
- W1: build Sunday-aligned weeks now, in this phase (option b): a Sunday-aligned 1w `bar_start` in `ExnessSessionCalendarAdapter`, a Sunday-aligned W1 cutoff in `ExnessAdapter`, and an Exness-specific 24/7 calendar for `BTCUSD:EXNESS` so it no longer uses the shared Monday-grid `CRYPTO_24_7` calendar. Exness 1w bars must store and pass integrity.
- DST: model the Exness sessions in `America/New_York` time now, so the UTC session hours follow the US DST change (2026-11-01) without a code change. Cover both sides of the change in tests.
- Key in logs: apply the `websockets` logger fix in `core/common/logging/setup.py` in this phase.
- After these, finish T6.18 and T6.19 as written.
- 2026-10-19 (coordinator): fix the pre-existing `check_integrity` in-progress-bar bug in this phase in its own commit, and release to prod by fast-forwarding `master` after green develop CI.

## Progress 2026-10-19
- Rebased onto `origin/develop` (`9b547ca`, master-only deploys); the code base for diffs is now `bc3cd69` (`.cache/phase06-base`).
- W1: `exness_bar_start` (UTC grid, weeks open Sunday 00:00Z) backs `ExnessSessionCalendarAdapter.bar_start` and the `ExnessAdapter` in-progress cutoff. `CALENDAR_EXNESS_CRYPTO` (`EXNESS_CRYPTO`, built from `conditions_BTCUSD.json` `trade_sessions`) replaces `CRYPTO_24_7` for `BTCUSD:EXNESS` in the seed. Its 1d is REST-only (from `sync_backfill`), as the Goal says, because `cascade_tfs` cascades 1d for `CRYPTO_24_7` alone.
- DST: the recorded UTC tables are shifted by the EDT offset at the recording date into New York wall-clock weeks and converted back to UTC per week, so 2026-11-01 moves every edge one hour later in UTC. Tests cover both sides of 2026-11-01 and of 2027-03-14.
- `periods_per_year` now counts bar opens in a Sunday-to-Sunday reference week × 52 (FX and XAU 1d 312, 1w 52; crypto 1d 364). The old open-seconds division gave about 260 and 37.
- `websockets` logger set to WARNING in `core/common/logging/setup.py`, with a test that fails without it.
- `check_integrity` (shared engine) dropped expected instants at or after the calendar's in-progress bar: before, every calendar (CME, `CRYPTO_24_7`, Exness) reported today's unfinished D1 bar, and CME's 02:00 4h bar, as missing on every run.
- Gate: lint-imports 8 kept; ruff and pyright 0 errors; `just test` shows only the 4 Windows `time.tzset` tests red (Docker Desktop had to be started first). The ratchet measures `tiny_share 0.4877` and `delegations 87`; the ceiling is raised to those values in its own commit per the user's decision (this overrides the T6.18 "never raise the ceiling" remedy).

## Context Links
- Spike journal `docs/journals/2026-10-13-exness-api-spike.md`: `rest_host: access_point`, `ws_subprotocol: exness-ws-protocol`, `ticks_subscribe_mode: add`, `instrument_names: XAUUSD=XAUUSD, EURUSD=EURUSD, BTCUSD=BTCUSD`, the limits table, the session table, and the 429-below-published-rate finding. `fixtures/summary.json` holds the same keys (`rest_host`, `ws_host`, `ws_subprotocol`, `ticks_subscribe_mode`, `instrument_names`, `history_age_days`, `max_candles_per_request`).
- Confirmed API host: the `U2 api host:` line of `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md` (`api.exness.com`).
- Spike code to promote: `scripts/exness_spike.py` — `load_secret_key` :98, `body_hash` :113, `sign_headers` :117, `ServerClock` :148, `validate_base_url(url, api_host)` :159, `allowed_access_point` :173, `ws_url` :194, `min_request_interval` :373, `history_age_days` :380, `max_candles` :387, and the 429 retry in `Session.get` :294-317. Its tests are in `tests/scripts/test_exness_spike.py`.
- Routing: `provider_id_for` and `DATA_PROVIDER_DEFAULTS` (`src/pocketquant/core/domain/market_data/provider_routing_domain_service.py:49`, :43). Both routers are built in `src/pocketquant/app/di/adapters.py` (`get_data_provider` :44, `get_realtime_quote_provider` :62); `tests/app_test/unit/test_data_provider_registration.py` fails unless both routers register exactly the keys of `DATA_PROVIDER_DEFAULTS`. The REST router has no fallback (`routing_data_provider_adapter.py:35-59`); the realtime router gathers every child's `run_forever` (`routing_realtime_quote_adapter.py:95-97`), so a child that raises there stops every feed.
- Ports: `IDataProviderPort` (`src/pocketquant/core/domain/market_data/data_provider_port.py:15`), `IRealtimeQuoteProviderPort` (`realtime_quote_provider_port.py:15`, runtime-checkable Protocol, read-only `last_tick_at`), `ITradingCalendarPort` (`trading_calendar_port.py:23`, 11 abstract members).
- Shapes to mirror: `BinanceAdapter.fetch_ohlcv` (`src/pocketquant/core/infra/binance/binance_adapter.py:51`, drops the in-progress bar with `get_bar_start(now, interval)` at :82-83); `BinanceWebSocketAdapter.run_forever` (`binance_websocket_adapter.py:97`, watchdog :237, backoff :224); `aggtrade_to_quote_dict` (`binance_mappers.py:72`); the quote callback `QuoteAppService.on_quote_update` (`src/pocketquant/engine/market_data/app_services/quote_app_service.py:40`) reads `symbol`, `last_price`, `timestamp`, `bid`, `ask`, `volume`.
- Calendars: `TradingCalendarFactory` (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:21`, registry `_calendars` :27, unseeded default :47-61); calendar ids in `src/pocketquant/core/domain/symbol/value_objects.py:20-21`; `DEFAULT_CALENDAR_BY_ASSET_CLASS` :69 and `DEFAULT_SPEC_BY_ASSET_CLASS` :75; `AssetClass` (`src/pocketquant/core/domain/shared/enums.py:49`); `Continuous24x7Calendar.bar_start` delegates to `get_bar_start` (`continuous_24x7_calendar.py:59-62`). `cascade_tfs` derives 1d only for `CRYPTO_24_7` (`engine/market_data/app_services/cascade_aggregator.py:49-61`).
- Sync: `sync_1m` (`sync_jobs.py:451`) fetches 100 1m bars per tracked symbol and skips a symbol whose calendar is closed (`_sync_by_intervals` :148, gate :192-194); `sync_backfill` fetches 5000 bars of every `SYNC_INTERVALS` entry (:71-79, :757-758). `fetch_with_retry` retries only empty or misaligned answers (`engine/market_data/sync_internals/provider_fetch.py:32`); `SyncService.sync_one` turns an exception into an `error` response (`engine/market_data/sync_service.py:55`, :135).
- Seeding: `scripts/seed_index_futures.py` (dry run by default, `--apply`, `SymbolRepository.upsert` + `TrackedSymbolRepository.upsert`); `Symbol.create` takes an explicit `calendar_id` (`src/pocketquant/core/domain/symbol/entities.py:72-92`).
- Health: `register_health_checks` passes the provider map `{"binance": ..., "tradingview": ...}` and the credentialed set (`src/pocketquant/app/main_extensions.py:310-325`) to `check_market_data_providers` (`core/infra/market_data/provider_health_check.py:38`).
- Symbol cascade delete: `TrackedSymbolsService.remove` (`src/pocketquant/engine/market_data/tracked_symbols_service.py:141`, collections :102-112, cache keys :160-164).
- `Settings` is `src/pocketquant/core/config.py:37`; the OKX block ends at `okx_demo_mode` (:113).
- Spec facts (OpenAPI 1.0.2, `.cache/exness-spec/exness_api.yaml`, git-ignored): errors are `{"code", "error_message"}`; a 429 carries `REQUEST_RATE_LIMIT`; candles take `timeframe` (`M1 … H4, D1, W1, MN`), `price_type` (default `bid`), `from` and `count` (negative reads backward; `count=-1000` returns 1000 candles ending at `from`); deals history pages with `from`, `cursor` (from `next_cursor`) and `limit` ≤ 200 and returns `{items: [{event_time, deal}], has_more, next_cursor}`; WS handshakes are signed as GET over the path; subscribe messages are `{"id", "subscribe": {"event": "ticks", "instruments": [...]}}` and are acknowledged with `{"id", "code"}`.

## Goal
`XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` are seeded and tracked, sync through develop's existing jobs (1m REST every minute plus the intraday cascade; 1d and 1w by REST in `sync_backfill`), stream live ticks over the Exness WS, and are gated by session calendars recorded by the spike. Routing is by suffix only: `"exness"` is one entry in `DATA_PROVIDER_DEFAULTS` and one in each DI router. `ExnessClient` is the single path to Exness endpoints: it discovers the per-account access point once per process and sends every later call there, spaces requests by the strictest published rate with headroom, retries a 429 on data calls at most 3 times, never retries a 429 on an order call, and refuses every order call while `EXNESS_LIVE_TRADING` is false (the default). The phase ends when D1 holds in prod.

## Files to Create or Modify
- Create in `src/pocketquant/core/infra/exness/`: `__init__.py`, `exness_signer.py`, `exness_mappers.py`, `exness_client.py`, `exness_stream.py`, `exness_adapter.py` (`ExnessAdapter`, the `IDataProviderPort`) and `exness_quote_adapter.py` (`ExnessQuoteAdapter`).
- Create: `src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py`, `scripts/seed_exness_symbols.py`, `scripts/backfill/provider_bars.py`.
- Create tests: `tests/core_test/infra/exness/{__init__,test_exness_signer,test_exness_mappers,test_exness_client,test_exness_stream,test_exness_adapter,test_exness_quote_adapter}.py`, `tests/core_test/infra/calendars/test_exness_session_calendar_adapter.py`, `tests/scripts/test_seed_exness_symbols.py`, `tests/scripts/test_provider_bars.py`.
- Modify:
  - `src/pocketquant/core/config.py` (Exness settings)
  - `src/pocketquant/core/domain/shared/enums.py` (`AssetClass.CFD`), `src/pocketquant/core/domain/symbol/value_objects.py` (calendar ids and CFD defaults), `src/pocketquant/core/domain/market_data/provider_routing_domain_service.py` (`"exness"` default)
  - `src/pocketquant/core/infra/calendars/trading_calendar_factory.py` (register the Exness calendars)
  - `src/pocketquant/app/di/adapters.py` (`ExnessClient`, both routers), `src/pocketquant/app/main_extensions.py` (health map)
  - `scripts/exness_spike.py` (import the promoted code), `tests/scripts/test_exness_spike.py` (moved cases)
  - Tests that pin `:EXNESS` as unregistered: `tests/core_test/unit/domain/market_data/test_provider_routing.py:57-58`, `tests/core_test/infra/calendars/test_trading_calendar_factory_unseeded_default.py:49-50`, `tests/core_test/infra/persistence/test_symbol_repository_touch.py:87-89`; switch them to an unregistered suffix such as `XAUUSD:MT5`.

## Tasks

### T6.1 Sync and record the base
- **Goal:** Start from the current develop and record the base commit for later diffs.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch develop-sync && git pull --ff-only && mkdir -p .cache && git rev-parse HEAD > .cache/phase06-base`
- **Success criteria:** `develop-sync` equals `origin/develop`.
- **Verify:** `git status -sb | head -1` prints `## develop-sync...origin/develop` with no `ahead` or `behind`.

### T6.2 Exness settings fields
- **Goal:** `Settings` carries the Exness connection, the global live switch and the backfill rate fraction. Every field is optional and the switch defaults to off.
- **Target files and symbols:** `src/pocketquant/core/config.py` → `Settings`
- **Steps:**
  1. Below `okx_demo_mode` (:113), add `exness_api_base_url: str | None = None`, `exness_account_id: str | None = None`, `exness_api_key: SecretStr | None = None`, `exness_secret_key: SecretStr | None = None`, `exness_live_trading: bool = False` and `exness_rate_fraction: float = Field(default=1.0, gt=0, le=1)` (share of the request rate one process may use; the deep backfill lowers it).
- **Success criteria:** `Settings` loads unchanged when no `EXNESS_*` variable is set, and live trading is off.
- **Verify:** `uv run python -c "from tests.core_test.infra.market_data.conftest import build_settings;s=build_settings();print(s.exness_api_key is None, s.exness_live_trading, s.exness_rate_fraction)"` prints `True False 1.0`.

### T6.3 Promote the signer into `src/`
- **Goal:** One signer module, reused by the client and the spike (DRY).
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_signer.py` (`load_secret_key`, `body_hash`, `sign_headers`, `ServerClock`); `scripts/exness_spike.py`; `tests/core_test/infra/exness/test_exness_signer.py`
- **Steps:**
  1. Create empty `src/pocketquant/core/infra/exness/__init__.py` and `tests/core_test/infra/exness/__init__.py`.
  2. Move `_b64url_nopad`, `load_secret_key`, `body_hash`, `sign_headers` and `ServerClock` from `scripts/exness_spike.py` into `exness_signer.py` verbatim. The spike imports them from `pocketquant.core.infra.exness.exness_signer`.
  3. Move the cases that exercise those names from `tests/scripts/test_exness_spike.py` (`test_body_hash_of_empty_body_matches_spec_example`, `test_sign_headers_produces_verifiable_unpadded_signature`, the four `test_load_secret_key_*` cases and `test_server_clock_tracks_offset_from_date_header`) into `test_exness_signer.py`, importing from the new module.
- **Success criteria:** No signing code remains in `scripts/`.
- **Verify:** `grep -c "def sign_headers\|def load_secret_key" scripts/exness_spike.py` prints `0`. `uv run python -m pytest tests/core_test/infra/exness/test_exness_signer.py tests/scripts/test_exness_spike.py -q` exits 0.

### T6.4 `exness_mappers.py`
- **Goal:** Pure conversions in one place; the adapter owns all CFD semantics and instrument naming.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_mappers.py`:
  - `INTERVAL_TO_EXNESS: dict[Interval, str]` = 1m `M1`, 5m `M5`, 15m `M15`, 1h `H1`, 4h `H4`, 1d `D1`, 1w `W1` (every member of `SYNC_INTERVALS`)
  - `EXNESS_INSTRUMENTS: dict[str, str] = {"XAUUSD:EXNESS": "XAUUSD", "EURUSD:EXNESS": "EURUSD", "BTCUSD:EXNESS": "BTCUSD"}`, keyed by the full composite symbol (the spike recorded that the names equal the codes, with no suffix)
  - `instrument_name(symbol: str) -> str | None`, `composite_for(instrument: str) -> str | None`
  - `candle_to_bar(candle: dict, symbol: str, interval: Interval) -> Bar`
  - `tick_to_quote_dict(tick: dict, symbol: str) -> dict`
  - `units_to_lots(quantity: Decimal, *, contract_size, volume_min, volume_step, volume_max, max_lots: Decimal | None) -> Decimal | None`, `lots_to_units(lots: Decimal, contract_size: Decimal) -> float`, `format_price(price: float, point_digits: int) -> str`
- **Steps:**
  1. `instrument_name` returns `EXNESS_INSTRUMENTS.get(symbol.upper())`; `composite_for` returns the key whose value equals `instrument`, else None.
  2. `candle_to_bar` maps `datetime.fromisoformat(candle["time"])` converted to UTC, the OHLC floats, `volume=float(candle["volume"])` and `tick_count=int(candle["volume"])`, with `symbol=symbol.upper()` and `interval=interval`.
  3. `tick_to_quote_dict` returns the key set of `aggtrade_to_quote_dict`: `symbol`, `timestamp` (parsed from the ISO `timestamp`, UTC), `last_price=float(bid)`, `volume=None`, `bid`, `ask`, and `None` for `change`, `change_percent`, `open_price`, `high_price`, `low_price` and `prev_close`.
  4. `units_to_lots`: `raw = quantity / contract_size`; `cap = min(volume_max, max_lots if max_lots is not None else volume_min)`; return None when `raw < volume_min`, else `volume_min + floor((min(raw, cap) - volume_min) / volume_step) * volume_step`. Use `Decimal` throughout.
  5. `lots_to_units` returns `float(lots * contract_size)`; `format_price` returns `f"{price:.{point_digits}f}"`.
- **Success criteria:** No float rounding in the lot maths; the table is the only place instrument names live.
- **Verify:** no verification needed; T6.5 covers this module.

### T6.5 Mapper tests
- **Goal:** Pin the conversions against the recorded fixtures.
- **Target files and symbols:** `tests/core_test/infra/exness/test_exness_mappers.py`
- **Steps:**
  1. `candle_to_bar` on the first candle of `fixtures/candles_XAUUSD_M1.json` (`["candles"][0]`) gives `symbol "XAUUSD:EXNESS"`, a UTC-aware datetime and `tick_count == int(volume)`.
  2. `tick_to_quote_dict` on the first frame of `fixtures/ticks_sample.json` that carries `instrument` gives `last_price == bid`.
  3. `{f"{c}:EXNESS": n for c, n in summary["instrument_names"].items()} == EXNESS_INSTRUMENTS` with `summary = json.load(open(fixtures/summary.json))`; `instrument_name("xauusd:exness") == "XAUUSD"`; `instrument_name("XAUUSD:BINANCE") is None`; `composite_for("XAUUSD") == "XAUUSD:EXNESS"`.
  4. `units_to_lots` with `contract_size` 100, `volume_min` 0.01, step 0.01, `volume_max` 200 (the recorded XAUUSD conditions) and `max_lots` None: quantity 0.5 → None; 1 → `Decimal("0.01")`; 7.9 → `Decimal("0.01")`. With `max_lots=Decimal("0.05")`, 7.9 → `Decimal("0.05")`.
  5. `lots_to_units(Decimal("0.01"), Decimal("100")) == 1.0` and `format_price(2345.678912, 3) == "2345.679"`.
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness/test_exness_mappers.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - access point for every call after discovery, request pacing, 429 retry on data calls -->
### T6.6 `exness_client.py`
- **Goal:** One signed REST client and the only path to Exness endpoints. It validates its base URL, fails closed, discovers the access point once per process and sends every later call there, spaces requests by the strictest published rate with headroom, retries transport errors with the same idempotency key, retries a 429 on data calls at most 3 times, never retries a 429 on an order call, and refuses order calls while live trading is off.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_client.py`:
  - `EXNESS_API_HOST = "api.exness.com"` (the `U2 api host:` line); `validate_base_url`, `allowed_access_point`, `ws_url`, `min_request_interval`, `history_age_days` and `max_candles`, moved verbatim from the spike (the spike imports them from here)
  - `class ExnessApiError(Exception)` with `status`, `code` and `message`
  - `_ENDPOINTS: dict[str, tuple[str, str]]`, `_ORDER_OPS = frozenset({"openPosition", "closePosition"})`, `_PRIORITY_OPS = _ORDER_OPS | {"getOperationStatus"}`, `_RATE_LIMIT_RETRIES = 3`
  - `class _RequestPacer` with `async wait(*, priority: bool)`
  - `class ExnessClient(settings: Settings)` with `is_configured`, `async access_point() -> str`, `async call(op, *, path_params=None, params=None, json_body=None, idempotency_key="") -> dict`, cached `async limits()`, `async instruments() -> list[str]` and `async conditions(instrument) -> dict` (1 h), `async deals_window_days() -> int`, `sign_ws_headers(path) -> dict[str, str]`, `async ws_url(path) -> str` and `async close()`
- **Steps:**
  1. `_ENDPOINTS` maps `getAccessPoint` (`GET /v1/trading/access-point`), `getLimits`, `getAccountDetails`, `getAvailableInstrumentList`, `getInstrumentCondition`, `getCandleHistory`, `getTradingStateSnapshot`, `getDealsHistory`, `getOperationStatus` (`GET /v1/trading/accounts/{account_id}/operations/{operation_id}`), `openPosition` (`POST /v1/trading/accounts/{account_id}/positions`) and `closePosition` (`DELETE .../positions/{position_id}`) to `(method, path template)`, copying the paths from `fixtures/limits.json` (`methods[].path`) and the spike. Callers use `call("<operationId>", ...)`; there is no method per endpoint.
  2. `__init__` computes `is_configured` once and fails closed: inside one `try/except ValueError`, require the four `exness_*` connection settings, run `validate_base_url(url, EXNESS_API_HOST)` and `load_secret_key(exness_secret_key.get_secret_value())`. On failure set it False and log a warning `exness.not_configured` with the failing setting name only, never a value. It makes no request.
  3. `access_point()` returns the in-memory host when set. Otherwise it sends `getAccessPoint` (query `account_id`) to the base URL, takes `allowed_access_point(body["access_point"])` (the API returns a full https URL; the function returns the host), stores it and returns it. Any error propagates and stores nothing, so the next call tries again. There is no fallback to the base host, because the spike showed it answers account routes with a bare 404. There is no Redis cache, TTL or refresh; a host change is picked up on the next process start.
  4. `call`, in this order:
     - not configured → raise `ExnessApiError(0, "NOT_CONFIGURED", "exness settings missing or invalid")`;
     - `op in _ORDER_OPS and not settings.exness_live_trading` → raise `ExnessApiError(0, "LIVE_TRADING_DISABLED", "EXNESS_LIVE_TRADING is false")` before any pacing or network use;
     - `op != "getAccessPoint"` → the URL is `https://{await self.access_point()}{path}`; `getAccessPoint` alone uses the base URL;
     - `await self._pacer.wait(priority=op in _PRIORITY_OPS)`;
     - format the path with `account_id` and `path_params`, build the query with `urlencode(params)`, request the literal `f"{path}?{query}"`, serialize a JSON body with `json.dumps(body, separators=(",", ":")).encode()` sent as `content=` with `Content-Type: application/json`, and sign with `sign_headers(..., timestamp_ms=self._clock.now_ms())` (the signed path excludes the host); update the clock from the `date` header.
  5. Transport retries: on `httpx.TransportError`, retry at most twice (3 attempts) with the same `idempotency_key`, re-signed with a fresh timestamp, sleeping `2 ** attempt` seconds; then raise `ExnessApiError(0, "TRANSPORT", ...)`.
  6. 429 (`REQUEST_RATE_LIMIT`; the spike saw it below the published rate):
     - `op in _ORDER_OPS`: never retried. Log a warning `exness.rate_limited` with `op` and raise `ExnessApiError(429, "REQUEST_RATE_LIMIT", ...)` at once; the broker rejects the order and reconciles (Phase 07).
     - Any other op (candles, history, configuration, snapshot, operation status): retry at most `_RATE_LIMIT_RETRIES` times, each through the pacer and re-signed, sleeping `int(Retry-After)` when the header is a number, else `2 ** attempt` (1, 2, 4 s), and log a warning `exness.rate_limited_retry` with `op` and `attempt` before each retry. When the last retry is still 429, log `exness.rate_limited` and raise the same error.
  7. Other non-2xx: `body = resp.json()` when it parses, else `{}`; raise `ExnessApiError(status, code=str(body.get("error_message") or f"HTTP_{status}"), message=str(body.get("code", "")))`. Never log headers, the key or signed bodies.
  8. `_RequestPacer(min_interval_s, clock=time.monotonic, sleep=asyncio.sleep)`: requests leave at least `min_interval_s` apart, one at a time; a priority waiter goes before every waiting non-priority one. The client builds it lazily with `min_request_interval(await self.limits()) / settings.exness_rate_fraction` (0.6 s with the recorded limits: the strictest rate is 2 per second, plus 20 % headroom), and uses 1.0 s for the `getAccessPoint` and `getLimits` calls made before the limits are known.
  9. `deals_window_days()` returns `history_age_days(await self.limits()) - 1` (the API rejects a window of exactly `history_age_days`). `ws_url(path)` builds `wss://{await self.access_point()}{path}` with the spike's `ws_url`. `close()` closes the HTTP client.
  10. Every function stays ≤ 60 lines.
- **Success criteria:** Requests are signed exactly as sent, every account call goes to the access point, and no order request can leave the process while live trading is off.
- **Verify:** no verification needed; T6.7 covers this module.

<!-- Updated: 2026-10-13 develop reshape - access point routing for every op, pacing, 429 data retries and order no-retry -->
### T6.7 Client tests
- **Goal:** Pin signing, routing, error mapping, secret hygiene, the live gate, URL validation, pacing, transport retries and the 429 rule.
- **Target files and symbols:** `tests/core_test/infra/exness/test_exness_client.py`
- **Steps:**
  1. Use an `httpx.MockTransport` that records every request and answers `getAccessPoint` with `{"access_point": "https://ap-1.exness.com"}` and `getLimits` with `fixtures/limits.json`. Inject it by monkeypatching `ExnessClient._http`. Build Settings with `build_settings().model_copy(update={...})` holding a generated 128-hex secret key, `exness_api_base_url="https://api.exness.com"` and `exness_live_trading` set per test. Patch `asyncio.sleep` in the module with an `AsyncMock` that records delays.
  2. Routing: `call("getCandleHistory", params={"instrument": "XAUUSD", "timeframe": "M1", "from": "2026-10-13T09:00:00+00:00", "count": -5})` sends one discovery request to `api.exness.com` and then every request (limits, candles) to `ap-1.exness.com`; a second call sends no new discovery request; the decoded `EXN-DATA.path` equals `request.url.raw_path` and holds no host; `EXN-IDEMPOTENCY-KEY == ""` on GET.
  3. Discovery: an `access_point` of `https://exness.com.evil.test` makes `access_point()` raise `ValueError` and stores nothing (the next call sends a new discovery request); a discovery answering 404 raises `ExnessApiError` with `status == 404`.
  4. Errors: a 400 with body `{"code": 1001, "error_message": "REQUEST_INVALID_COUNT"}` raises `ExnessApiError` with `code == "REQUEST_INVALID_COUNT"`.
  5. Secret hygiene: under `structlog.testing.capture_logs()`, no captured event contains the API key string.
  6. Fail closed: `is_configured` is False when `exness_api_key` is None, when the base URL is `http://api.exness.com` or another host, and when the secret key is a PEM string; `call` then raises `NOT_CONFIGURED` and the transport recorded 0 requests.
  7. Live gate: with `exness_live_trading=False`, `call("openPosition", json_body={...}, idempotency_key="order-00001")` and `call("closePosition", path_params={"position_id": "1"}, idempotency_key="order-00002")` raise `LIVE_TRADING_DISABLED`, and the transport recorded 0 requests.
  8. Transport retries: with `exness_live_trading=True`, an `httpx.ConnectError` followed by 202 makes `call("openPosition", ...)` succeed; both attempts carry the same `EXN-IDEMPOTENCY-KEY`, and the second carries `body_hash == body_hash(request.content)`.
  9. 429 on data calls: a transport answering 429 twice and then 200 makes `call("getCandleHistory", ...)` return the 200 body after 3 candle requests, with recorded sleeps `[1, 2]` and two `exness.rate_limited_retry` events; a transport answering 429 four times raises `ExnessApiError(status=429, code="REQUEST_RATE_LIMIT")` after exactly 4 candle requests (1 + 3 retries) with sleeps `[1, 2, 4]`; a 429 carrying `Retry-After: 3` sleeps `3` before its retry.
  10. 429 on order calls: with `exness_live_trading=True`, a transport answering 429 makes `call("openPosition", ...)` raise `REQUEST_RATE_LIMIT` after exactly 1 order request; no `exness.rate_limited_retry` event is captured and no sleep was recorded for it.
  11. Pacer: with a fake clock and `min_interval_s=0.6`, three waits record start times at least 0.6 s apart; with one non-priority waiter queued, a priority waiter that arrives later goes first. With `exness_rate_fraction=0.5` the client's pacer interval is `1.2` for the recorded limits.
  12. `deals_window_days()` returns `29` for the recorded limits.
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness/test_exness_client.py -q` exits 0. `grep -rn --include='*.py' "trading/accounts/{account_id}/positions" src | wc -l` prints `2` (the two `_ENDPOINTS` entries, nowhere else).

### T6.8 `exness_stream.py`
- **Goal:** One reconnecting signed WS stream on the access point, shaped like `BinanceWebSocketAdapter`: backoff 1 s → 30 s and a circuit breaker after 10 consecutive failures that pauses for 300 s. A handler exception never kills the stream.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_stream.py` → `class ExnessStream` with `__init__(client: ExnessClient, path: str, on_message: Callable[[dict], Awaitable[None]], on_connect: Callable[[], Awaitable[None]], stale_after_s: float | None)`, `async run_forever()`, `async send(message: dict)`, `is_connected() -> bool`, `async close()` and attribute `last_frame_at`.
- **Steps:**
  1. Connect with `websockets.connect(await client.ws_url(path), additional_headers=client.sign_ws_headers(path), subprotocols=[Subprotocol("exness-ws-protocol")], ping_interval=20, ping_timeout=10, close_timeout=5)`. The subprotocol is the spike's `ws_subprotocol` (`_SUBPROTOCOL` module constant); the host is the access point (`ws_host: access_point`).
  2. After connecting, reset the backoff and failure count and `await on_connect()`. For each frame, `json.loads`, update `last_frame_at` and `await on_message(frame)` inside `try/except Exception`, logging a warning `exness_ws.handler_failed` and continuing. An invalid JSON frame is logged as a warning `exness_ws.invalid_json` and skipped.
  3. On any disconnect or connection exception (including `ExnessApiError` or `ValueError` from `ws_url`, which resolves the access point): log `exness_ws.reconnecting` with `delay` at INFO, sleep the backoff and double it up to 30 s. After 10 consecutive failures, log an error `exness_ws.circuit_breaker_open` and sleep 300 s before the next attempt. `run_forever` never raises except `CancelledError`, because the realtime router gathers every child.
  4. When `stale_after_s` is set, a sibling watchdog task closes the socket if `last_frame_at` is older than `stale_after_s` (copy the Binance watchdog shape, `binance_websocket_adapter.py:237`).
- **Success criteria:** Reconnect and backoff are deterministic and testable.
- **Verify:** no verification needed; T6.9 covers this module.

### T6.9 WS stream tests
- **Goal:** Pin the reconnect behaviour and handler isolation.
- **Target files and symbols:** `tests/core_test/infra/exness/test_exness_stream.py`
- **Steps:**
  1. Monkeypatch `websockets.connect` in the module to a fake that fails N times, then yields scripted frames and closes. Patch `asyncio.sleep` in the module with an `AsyncMock` that records delays. The client stub's `ws_url` is an `AsyncMock` returning `wss://ap-1.exness.com/<path>`.
  2. After 3 failures the recorded delays are `[1, 2, 4]`, and `on_connect` runs after the first success.
  3. 10 consecutive failures record one sleep of `300`.
  4. The handshake headers include `EXN-SIGN`, the signed path equals the stream path, and the subprotocol list is `["exness-ws-protocol"]`.
  5. An `on_message` that raises on the first frame still receives the second frame, and one `exness_ws.handler_failed` event is captured.
  6. A `ws_url` that raises `ExnessApiError` counts as a failure and is retried with backoff; `run_forever` does not raise.
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness/test_exness_stream.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - IDataProviderPort adapter; a 429 is retried inside the client -->
### T6.10 `exness_adapter.py`
- **Goal:** `IDataProviderPort` over native bid candles, paginated by `max_candles_per_request`, with the in-progress candle dropped.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_adapter.py` → `class ExnessAdapter(IDataProviderPort)` with `__init__(client: ExnessClient)`, `fetch_ohlcv(symbol, interval, n_bars=1000)`, `search_symbols(query) -> []` and `close()` (no-op; the client's lifetime belongs to DI).
- **Steps:**
  1. `name = instrument_name(symbol)`; when None, log a warning `exness.unknown_instrument` with `symbol` and return `[]`.
  2. `page = max_candles(await client.limits())` (1000 recorded).
  3. Loop while `remaining > 0`:
     - `await client.call("getCandleHistory", params={"instrument": name, "timeframe": INTERVAL_TO_EXNESS[interval], "price_type": "bid", "from": cursor, "count": -min(remaining, page)})`, where `cursor` starts at the current UTC time in ISO seconds precision;
     - map each candle with `candle_to_bar`;
     - drop bars whose datetime is `>= get_bar_start(now, interval)` (the in-progress bar; the spike showed every series on the UTC grid, so the same cutoff as `BinanceAdapter` applies);
     - drop bars whose datetime is already collected, and prepend the rest;
     - stop when the page returned fewer candles than requested; otherwise move `cursor` to the oldest returned candle time.
  4. Log `exness.fetch_completed` at DEBUG with `symbol` and `bars_fetched` (a per-minute event). Return the bars ascending, trimmed to the last `n_bars`.
  5. Do not catch `ExnessApiError`. The client already retried a 429; anything it raises propagates, `SyncService.sync_one` reports it as an `error`, and the next scheduled run fetches again.
- **Success criteria:** Same contract as `BinanceAdapter.fetch_ohlcv`.
- **Verify:** no verification needed; T6.11 covers this module.

### T6.11 Data adapter tests
- **Goal:** Pin pagination, in-progress filtering and error propagation.
- **Target files and symbols:** `tests/core_test/infra/exness/test_exness_adapter.py`
- **Steps:**
  1. Use a fake client (`AsyncMock`) with `limits()` returning `fixtures/limits.json` with `max_candles_per_request` patched to 100, and `call("getCandleHistory", ...)` returning slices of `fixtures/candles_XAUUSD_M1.json`.
  2. `fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 250)` makes 3 candle calls with counts `-100`, `-100` and `-50`, each with `instrument == "XAUUSD"` and `price_type == "bid"`, and returns ascending, unique datetimes.
  3. A candle whose open time equals `get_bar_start(now, Interval.MINUTE_1)` is excluded.
  4. `fetch_ohlcv("ZZZ:EXNESS", Interval.MINUTE_1, 10)` returns `[]` without calling the client.
  5. A fake client whose `call` raises `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")` makes `fetch_ohlcv` raise that error after exactly one `call` (the adapter adds no retry of its own).
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness/test_exness_adapter.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - subscribe mode add from the spike; idles when unconfigured -->
### T6.12 `exness_quote_adapter.py`
- **Goal:** `IRealtimeQuoteProviderPort` over WS ticks, using the same callback dict as Binance, never sending an unknown instrument, and idle when Exness is not configured.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/exness_quote_adapter.py` → `class ExnessQuoteAdapter` with `last_tick_at` (read-only property), `connect()`, `disconnect()`, `subscribe(symbol, callback) -> str`, `unsubscribe(symbol)`, `run_forever()`, `is_connected()`, `subscription_count` and `subscriptions`.
- **Steps:**
  1. `self._subscriptions: dict[str, tuple[str, Callable]]` maps the composite symbol to `(instrument name, callback)`; `self._rejected: set[str]`.
  2. `subscribe`: `composite = symbol.upper()`, `name = instrument_name(composite)`. If `name is None` or `name not in await client.instruments()`, then on the first time only add `composite` to `_rejected` and log a warning `exness_ws.unknown_instrument`; return `composite` without storing or sending anything. Otherwise store the entry and, if the stream is connected, send `{"id": f"sub-{name}", "subscribe": {"event": "ticks", "instruments": [name]}}`. The spike recorded `ticks_subscribe_mode: add`, so a later subscribe adds to the earlier ones.
  3. `unsubscribe` removes the entry locally; frames for instruments not stored are ignored.
  4. `run_forever`: when `not client.is_configured`, log `exness_ws.disabled` once at INFO and wait on an `asyncio.Event` that is never set (the router gathers this coroutine, so it must neither return early nor raise). Otherwise run `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/ticks", on_message=self._on_frame, on_connect=self._resubscribe_all, stale_after_s=None)`. Ticks pause in closed markets, so there is no stale watchdog. `_resubscribe_all` sends one message with every stored name when there is at least one.
  5. `_on_frame`: a frame with `id` and `code` is a subscribe acknowledgement and is logged at DEBUG. A frame with `instrument`, `bid` and `ask` finds the composite symbol from the stored names, builds `tick_to_quote_dict`, sets `last_tick_at`, and calls the callback (awaiting it when it is a coroutine) inside `try/except Exception` with a warning `exness_ws.callback_failed`. A frame carrying `MARKET_TRADE_DISABLED` or `trading_disabled` logs a warning `exness_ws.trading_disabled`; any other error frame logs `exness_ws.error_frame`.
  6. `connect()` is a no-op, because the connection happens inside `run_forever`. `disconnect()` closes the stream.
- **Success criteria:** It satisfies the Protocol structurally, unknown instruments never reach the socket, and an unconfigured client never stops the other feeds.
- **Verify:** no verification needed; T6.13 covers this module.

### T6.13 Quote adapter tests
- **Goal:** Pin the callback contract, validation, subscribe semantics and the idle path.
- **Target files and symbols:** `tests/core_test/infra/exness/test_exness_quote_adapter.py`
- **Steps:**
  1. `isinstance(ExnessQuoteAdapter(client_stub), IRealtimeQuoteProviderPort)` is True; `client_stub.instruments()` returns `fixtures/instruments.json["instruments"]`.
  2. After `subscribe("XAUUSD:EXNESS", cb)`, feeding `_on_frame` the first XAUUSD tick of `fixtures/ticks_sample.json` calls `cb` once with `symbol == "XAUUSD:EXNESS"` and `last_price == bid`; the acknowledgement frame `{"id": "spike-ticks-all", "code": 200}` calls nothing.
  3. A frame for an unsubscribed instrument does not call `cb`, and a `cb` that raises does not propagate.
  4. `subscribe("ZZZ:EXNESS", cb)` called three times with a connected fake stream sends no message, leaves `subscriptions` without the key, and captures exactly one `exness_ws.unknown_instrument` event.
  5. Subscribing XAUUSD then EURUSD on a connected fake stream sends two messages; the second holds only `["EURUSD"]`.
  6. An error frame logs `exness_ws.trading_disabled` and does not raise.
  7. With `client_stub.is_configured = False`, `run_forever()` is still pending after `asyncio.wait_for(..., 0.05)` times out, and no stream was built.
- **Success criteria:** All tests pass.
- **Verify:** `uv run python -m pytest tests/core_test/infra/exness/test_exness_quote_adapter.py -q` exits 0.

<!-- Updated: 2026-10-13 develop reshape - replaces the SyncPolicy and MarketCalendar task with a calendar behind ITradingCalendarPort -->
### T6.14 Exness session calendars
- **Goal:** Sync gating, integrity, repair and data lag know when each Exness instrument trades, through develop's calendar port, with the sessions recorded by the spike.
- **Target files and symbols:**
  - `src/pocketquant/core/domain/symbol/value_objects.py`: `CALENDAR_EXNESS_FX = "EXNESS_FX"` and `CALENDAR_EXNESS_XAUUSD = "EXNESS_XAUUSD"` next to :20-21
  - `src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py` → `class ExnessSessionCalendarAdapter(ITradingCalendarPort)` with `__init__(calendar_id: str, week_sessions: list[dict[str, str]])`, module constants `_EURUSD_SESSIONS`, `_XAUUSD_SESSIONS` and `EXNESS_CALENDARS: tuple[ExnessSessionCalendarAdapter, ...]`
  - `TradingCalendarFactory.__init__` (`trading_calendar_factory.py:27`)
- **Steps:**
  1. `_EURUSD_SESSIONS` and `_XAUUSD_SESSIONS` hold the `trade_sessions` lists copied verbatim from `tests/core_test/infra/exness/fixtures/conditions_EURUSD.json` and `conditions_XAUUSD.json`, with a comment giving the recording date (2026-10-13). `EXNESS_CALENDARS` holds those two plus `ExnessSessionCalendarAdapter(CALENDAR_EXNESS_CRYPTO, _BTCUSD_SESSIONS)` (24x7, from `conditions_BTCUSD.json`; Exness weeks open on Sunday, so BTCUSD does not share `CALENDAR_CRYPTO_24_7`). Sessions are held in `America/New_York` (2026-10-19 decision).
  2. The constructor parses each `week_start_time`/`week_end_time` (`"Mon, 20:57:59"`, UTC) into seconds from Monday 00:00, keeps only `enabled` entries, and merges adjacent ones (an end of `…:59` followed by a start at the next second is one segment; the spike showed 22:01:59/22:02:00 and 22:04:59/22:05:00 are split points, not gaps). `trading_disabled` entries are closures.
  3. Port members, all in UTC (`tz` is `ZoneInfo("UTC")`):
     - `is_open(instant)`: the instant's week offset falls inside a merged segment (end inclusive to the second);
     - `trading_minutes(start, end)`: every minute `m` in `[start, end)` whose `[m, m + 60 s)` overlaps a segment (so 22:00 counts when trading resumes at 22:00:30, and 20:57 counts when it stops at 20:57:59);
     - `bar_start(instant, interval)`: `get_bar_start(instant, interval)`, because the spike recorded every Exness series on the UTC grid (D1 at 00:00Z, H4 at 08:00Z);
     - `session_date(instant)`: `instant.date()` (matches the UTC-midnight D1 candles); `session_open(d)`/`session_close(d)`: the first and last open instant of that UTC day; `sessions(start, end)`: every UTC date in range with at least one open minute; `previous_close(instant)`: `instant` when open, else the end of the latest segment before it;
     - `periods_per_year(interval)`: open seconds per week × 52 / `INTERVAL_SECONDS[interval]`.
  4. In `TradingCalendarFactory.__init__`, add every member of `EXNESS_CALENDARS` to the `_calendars` tuple next to `CmeGlobexCalendarAdapter()`.
  5. `tests/core_test/infra/calendars/test_exness_session_calendar_adapter.py`:
     - the two session constants equal the fixtures' `trade_sessions`;
     - XAUUSD: Tue 2026-10-13 09:28Z open; 20:58:00Z and 21:30Z closed; 22:00:30Z open; Sat 2026-10-17 12:00Z closed; Sun 2026-10-18 22:01:30Z open; Fri 2026-10-16 20:57:59Z open and 20:58:00Z closed;
     - EURUSD: Tue 21:30Z open (no daily break); Fri 2026-10-16 20:58:59Z open and 20:59:00Z closed; Sun 2026-10-18 21:05:00Z open;
     - every candle time in `fixtures/candles_XAUUSD_M1.json` and `fixtures/candles_EURUSD_M1.json` is in `trading_minutes` of its calendar over the fixture window (the recorded bars never fall in a closure);
     - `bar_start` equals `get_bar_start` for every `SYNC_INTERVALS` member; `previous_close(Sat 12:00Z)` for XAUUSD is Fri 20:57:59Z;
     - `TradingCalendarFactory(MagicMock()).get("EXNESS_FX").calendar_id == "EXNESS_FX"` and the same for `EXNESS_XAUUSD`.
- **Success criteria:** The calendars implement every port member and agree with the recorded bars.
- **Verify:** `uv run python -m pytest tests/core_test/infra/calendars -q` exits 0. `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.` (no `pandas_market_calendars` use).

<!-- Updated: 2026-10-13 develop reshape - replaces the SyncPolicies DI task: one defaults entry plus one entry in each router -->
### T6.15 Register `exness` as a data provider
- **Goal:** `:EXNESS` symbols route to the Exness adapters through the existing routers, and an unseeded `:EXNESS` symbol is a CFD on the FX calendar. With no Exness env the behaviour for Binance and TradingView is unchanged, and building the client makes no Exness request.
- **Target files and symbols:**
  - `AssetClass.CFD = "cfd"` (`src/pocketquant/core/domain/shared/enums.py:49-58`)
  - `DEFAULT_CALENDAR_BY_ASSET_CLASS[AssetClass.CFD] = CALENDAR_EXNESS_FX` and `DEFAULT_SPEC_BY_ASSET_CLASS[AssetClass.CFD] = LINEAR_SPEC` (`value_objects.py:69-83`)
  - `DATA_PROVIDER_DEFAULTS["exness"] = DataProviderDefaults(AssetClass.CFD, CALENDAR_EXNESS_FX)` (`provider_routing_domain_service.py:43-46`)
  - `AdaptersProvider.get_exness_client(self, settings) -> AsyncIterator[ExnessClient]` (APP scope, generator in the shape of `InfrastructureProvider.get_cache`, `app/di/infrastructure.py:67-72`: build `ExnessClient(settings)`, yield it, then `await close()`), plus `"exness": ExnessAdapter(exness_client)` in `get_data_provider` (:44) and `"exness": ExnessQuoteAdapter(exness_client)` in `get_realtime_quote_provider` (:62), each method gaining an `exness_client: ExnessClient` parameter
  - `register_health_checks` (`app/main_extensions.py:310-325`)
- **Steps:**
  1. Apply the edits above. Update the `adapters.py` module docstring only where it lists the routers' providers.
  2. In `register_health_checks`, resolve `ExnessClient` and add `"exness": lambda: exness_client.is_configured` to the provider map, and `"exness"` to the credentialed set when `exness_client.is_configured`. An unconfigured Exness is then neither in use nor degraded.
  3. Switch the three tests that pin `:EXNESS` as unregistered (Files list) to `XAUUSD:MT5`; their assertions are otherwise unchanged. Extend `tests/core_test/unit/domain/market_data/test_provider_routing.py` with `provider_defaults_for("XAUUSD:EXNESS") == DataProviderDefaults(AssetClass.CFD, "EXNESS_FX")`.
  4. `tests/app_test/unit/test_data_provider_registration.py` stays as it is and must pass: both routers now register `{"binance", "tradingview", "exness"}`, equal to the keys of `DATA_PROVIDER_DEFAULTS`. Add one case there: with `build_settings()` (no Exness values) the resolved `ExnessClient.is_configured` is False and the mock transport saw no request.
- **Success criteria:** Adding Exness touched one defaults entry, one entry per router, a calendar registration and the health map; no consumer above the ports changed.
- **Verify:** `uv run python -m pytest tests/app_test/unit tests/core_test/unit/domain/market_data tests/core_test/infra/market_data tests/core_test/infra/calendars tests/core_test/infra/persistence/test_symbol_repository_touch.py tests/app_test/integration/test_market_data_routing_characterization.py -q` exits 0. `git diff --name-only $(cat .cache/phase06-base) -- src/pocketquant/engine/market_data/app_services/sync_jobs.py` prints nothing.

<!-- Updated: 2026-10-13 develop reshape - new: seed symbols with calendar and contract spec, modelled on seed_index_futures.py -->
### T6.16 Seed script for the Exness symbols
- **Goal:** The three symbols carry their real asset class, calendar and contract spec before the first sync, as `scripts/seed_index_futures.py` does for the futures.
- **Target files and symbols:** `scripts/seed_exness_symbols.py` → `SEEDS`, `_build`, `seed(apply)`, `main`; `tests/scripts/test_seed_exness_symbols.py`
- **Steps:**
  1. Copy the structure of `scripts/seed_index_futures.py` (dry run by default, `--apply`, `SymbolRepository.upsert` then `TrackedSymbolRepository.upsert` with `seeded_from="script"`, exit codes 0/1/2). `SEEDS`:
     - `XAUUSD:EXNESS`, "Gold vs US Dollar (Exness CFD)", `CALENDAR_EXNESS_XAUUSD`, `ContractSpec(multiplier=1.0, tick_size=0.001, lot_step=None, currency="USD")`
     - `EURUSD:EXNESS`, "Euro vs US Dollar (Exness CFD)", `CALENDAR_EXNESS_FX`, `ContractSpec(multiplier=1.0, tick_size=0.00001, lot_step=None, currency="USD")`
     - `BTCUSD:EXNESS`, "Bitcoin vs US Dollar (Exness CFD)", `CALENDAR_EXNESS_CRYPTO`, `ContractSpec(multiplier=1.0, tick_size=0.01, lot_step=None, currency="USD")`
     `_build` calls `Symbol.create(symbol=..., name=..., asset_class=AssetClass.CFD, calendar_id=..., contract_spec=...)`. Tick sizes are `10 ** -point_digits` from the recorded conditions (3, 5 and 2). Quantity is in units of the instrument (ounces, euros, bitcoin); `lot_step` stays None so `PositionCalculatorDomainService` (`core/domain/risk/services/position_calculator_domain_service.py:47-56`) keeps fractional sizes. With the recorded grid (0.01 lot = 1 oz, 1000 EUR, 0.01 BTC) and a 10 000 USD paper or backtest account, the exposure cap (`balance × 0.10 / price`) is about 0.24 oz of gold and about 894 EUR, both below one grid step, so a grid `lot_step` would size every XAUUSD and EURUSD signal to zero (arithmetic from the spike's prices; see its sizer section). The Exness broker owns the lot grid (Phase 07).
  2. The module docstring states the run order: `--apply` before the first `sync_1m` reaches these symbols, and no `POST /tracked-symbols` call is needed because the script writes `tracked_symbols` too.
  3. `tests/scripts/test_seed_exness_symbols.py`: each built `Symbol` has `asset_class == AssetClass.CFD` and the calendar above; the symbols are exactly the three keys of `EXNESS_INSTRUMENTS`; `seed(apply=False)` with `Database` patched writes nothing.
  4. Add one line for the script to `scripts/README.md` next to `seed_index_futures.py`.
- **Success criteria:** The seed is idempotent, dry-run by default, and agrees with the Exness instrument table.
- **Verify:** `uv run python -m pytest tests/scripts/test_seed_exness_symbols.py -q` exits 0. `uv run python scripts/seed_exness_symbols.py --help` exits 0.

<!-- Updated: 2026-10-13 develop reshape - provider-agnostic deep backfill through the DI container instead of a policy registry -->
### T6.17 Provider-agnostic deep backfill script
- **Goal:** Deep history beyond the 5000-bar request cap (`SyncSymbolCommand.n_bars`, `BackfillTrackedSymbolCommand.n`) for any routed provider, at a fraction of the Exness request rate, never alongside live trading. `scripts/backfill/binance_bars.py` stays as it is (start/end windows, `--replace`, checkpoints).
- **Target files and symbols:** `scripts/backfill/provider_bars.py` → `parse_args`, `async run(cfg) -> int`, `main`; `tests/scripts/test_provider_bars.py`
- **Steps:**
  1. CLI: `--symbol` (composite), `--interval` (one of `1m 5m 15m 1h 4h 1d 1w`), `--days INT`, `--rate-fraction FLOAT` (default 0.5) and `--dry-run`.
  2. `settings = get_settings()`. If `settings.exness_live_trading` is true, print `refusing: EXNESS_LIVE_TRADING is true` and exit 3.
  3. `container = create_container(settings.model_copy(update={"exness_rate_fraction": cfg.rate_fraction}))`; `provider = await container.get(IDataProviderPort)`. A suffix with no registered provider raises `UnknownDataProviderError`: print `no data provider for <symbol>` and exit 2. Close the container in `finally`. The script resolves only the data port and `BarRepository`, so no scheduler or job starts.
  4. `n_bars = days * 86400 // INTERVAL_SECONDS[interval]`; `bars = await provider.fetch_ohlcv(symbol, interval, n_bars)`. Unless `--dry-run`, `await (await container.get(BarRepository)).insert_many(chunk, source=SOURCE_REST_BACKFILL)` in chunks of 5000.
  5. Print exactly one line, `fetched=<n> inserted=<n> total_bars=<BarRepository.count(symbol, interval)>` (`total_bars=-1` on `--dry-run`). Exit 0, or 1 when fetched is 0. An Exness error (for example `REQUEST_INVALID_TIME_RANGE` for M1 older than one year) prints its `code` and exits 1.
  6. `tests/scripts/test_provider_bars.py`: with `get_settings` patched to settings with `exness_live_trading=True`, `main([...])` returns 3; with it false and `create_container` patched to a container whose data port raises `UnknownDataProviderError`, `--symbol XAUUSD:MT5` returns 2.
  7. Add one line for the script to `scripts/README.md`.
- **Success criteria:** The script is safe to run in prod and works for every registered provider.
- **Verify:** `uv run python scripts/backfill/provider_bars.py --help` exits 0. `uv run python -m pytest tests/scripts/test_provider_bars.py -q` exits 0.

### T6.18 Phase gate
- **Goal:** Develop's gate holds.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `uv run lint-imports`
  2. `uv run ruff check src $(git diff --name-only $(cat .cache/phase06-base) -- tests scripts)` and `uv run ruff format --check` on the same files
  3. `uv run pyright src $(git diff --name-only $(cat .cache/phase06-base) -- tests scripts)`
  4. `just test 2>&1 | tail -n 15`
  5. `uv run python scripts/code_metrics.py --ratchet`
  6. `uv run python scripts/code_metrics.py --out .cache/metrics-phase06.json`
- **Success criteria:** Green, the ratchet holds, and no function in `core/infra/exness/` or the Exness calendar is over 60 lines.
- **Verify:**
  - Step 1 prints `Contracts: 8 kept, 0 broken.`
  - Steps 2 and 3 report 0 errors in `src/` and in every touched file (pre-existing debt in untouched test files is accepted).
  - Step 4 shows no new failure: the only failures are the 4 pre-existing Windows `time.tzset` tests in `test_utc_runtime_guard.py` and `test_cron_trigger_timezone.py`.
  - Step 5 exits 0. If it fails, follow the Failure Protocol; the remedy is to restructure (for example inline a thin wrapper), never to raise the ceiling (superseded on 2026-10-19: raise it to the measured values in its own commit).
  - `uv run python -c "import json;d=json.load(open('.cache/metrics-phase06.json'));print([f for f in d['functions_over_60'] if 'exness' in f])"` prints `[]`.

<!-- Updated: 2026-10-13 develop reshape - push develop-sync to develop; seed before tracking; D1 checks -->
### T6.19 Ship, seed and verify D1 in prod
- **Goal:** Exness bars and quotes flow in prod and Binance keeps syncing. Run this during FX market hours (not between Friday 21:00 and Sunday 22:00 UTC).
- **Target files and symbols:** git, VPS, API
- **Steps:**
  1. `git add -A src tests scripts plans/261009-0858-exness-venue-lean-sync-refactor && git commit -m "feat(exness): add exness market data and quotes behind suffix routing"`
  2. `git branch -m develop-sync develop && git branch -u origin/develop`, then `git push origin develop` (tests only). Wait for the CI run whose `headSha` equals `git rev-parse HEAD` (`gh run list --branch develop --limit 1 --json databaseId,headSha`) and `gh run watch <databaseId> --exit-status`. Then release with `git push origin develop:master` (fast-forward; builds and deploys) and watch the master run the same way.
  3. From the repo root set `KEY=../pocketquant-config/vps/default/id_rsa` and `HOST="$(cat ../pocketquant-config/vps/default/host)"`. Boolean-only configuration check: `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings;from pocketquant.core.infra.exness.exness_client import ExnessClient;s=get_settings();print(ExnessClient(s).is_configured, s.exness_live_trading)\""`.
  4. Seed: `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python scripts/seed_exness_symbols.py"` (dry run), then the same with `--apply`. Back up `symbols` and `tracked_symbols` first, as integration step 2 did for the futures seed (`mongodump --archive` into `/opt/pocketquant/backups/pre-exness-seed-<collection>-<date>.archive`).
  5. Manual sync (remote pattern `ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF' … EOF`): `curl -s -X POST http://localhost:41921/api/v1/market-data/sync -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"rest_backfill"}'`.
  6. Bar stream, same pattern: `timeout 70 curl -sN "http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m" | grep -m1 -c '"is_in_progress": true'`.
  7. Quote stream, same pattern: `timeout 30 curl -sN "http://localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS" | grep -m1 -c '"bid":'`.
  8. Wait 3 minutes, then: `curl -s "http://localhost:41921/api/v1/market-data/sync-status/XAUUSD%3AEXNESS?interval=1m"` and the same for `BTCUSDT%3ABINANCE`; and `curl -s http://localhost:41921/health`.
- **Success criteria:** D1 holds, Binance keeps syncing, the seeded symbols carry their calendars, and live trading is off.
- **Verify:**
  - `gh run watch <databaseId> --exit-status` exits 0, and `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.
  - Step 3 prints `True False`.
  - Step 4's `--apply` prints `Seeded 3 symbol(s) into symbols + tracked_symbols.`
  - Step 5's JSON piped to `python -c "import json,sys;d=json.load(sys.stdin);print(d['status']=='completed' and d['total_bars']>=1000)"` prints `True`.
  - Steps 6 and 7 each print `1`.
  - Both step 8 sync-status bodies contain `"status":"completed"`. The `/health` body (route `app/main_extensions.py:420`) piped to `python -c "import json,sys;d=json.dumps(json.load(sys.stdin));print('\"XAUUSD:EXNESS\": {\"provider\": \"exness\", \"calendar_id\": \"EXNESS_XAUUSD\"' in d and '\"exness\": {\"authenticated\": true' in d)"` prints `True` (key order follows `provider_health_check.py:62-71`).

## Verification
T6.3–T6.17 (unit, script and routing tests), T6.18 (develop gate and ratchet) and T6.19 (D1 in prod, live trading off).

## Stop-and-ask
- Any change that would enable live Exness trading, set `EXNESS_LIVE_TRADING=true`, or send an order request.
- The prod 1m sync of the three Exness symbols needs more than about 20 `getCandleHistory` requests a minute, or 429 retries appear on most `sync_1m` runs after D1.
- Anything would need a new container, worker or deployment topology change.
- The ratchet would need a higher ceiling.
- A step would delete Binance, OKX or TradingView code, or a test failure stays unexplained.
- Exness documents, or a re-read of `getInstrumentCondition` shows, that `trade_sessions` moved (for example at the US daylight-saving change on 2026-11-01).

## Risks
- **429 below the published rate** (M/M): the spike hit one at 0.6 s spacing. Mitigation: the pacer spaces requests by the strictest published rate plus 20 % headroom, data calls retry a 429 up to 3 times with 1/2/4 s backoff and log every retry, and order calls never retry. The deep backfill runs in a second process at `--rate-fraction 0.5`; the two processes do not share a pacer, so their combined rate can exceed the limit and the retries absorb it (inference).
- **A slow Exness delays other symbols in `sync_1m`** (M/M): develop syncs tracked symbols one after another and has no per-provider time cap. One Exness fetch is one paced request (≤ 10 s HTTP timeout) plus at most 7 s of 429 backoff. If `sync_1m` overruns its minute, APScheduler skips a run (`max_instances=1`) and the next run's 100-bar fetch heals the gap; data lag reports `stuck` only after 5 minutes without a 1m sync.
- **Session drift** (M/M): the calendars are constants recorded on 2026-10-13. Whether Exness shifts `trade_sessions` at the US daylight-saving change is unverified. A drift shows up as integrity misses at the session edges (Phase 08 T8.8) and as a mismatch in the Phase 08 session re-read.
- **W1 alignment**: verified Sunday 00:00Z by a read-only prod call (2026-10-16); every Exness calendar uses Sunday-aligned 1w bars. If `sync_integrity` still reports misaligned `1w` bars for `:EXNESS`, STOP and ask.
- **Closed-market noise**: `sync_1m` skips a closed symbol, integrity uses the calendar, and data lag reports `closed`. Weekend `sync-status` rows may look stale; that flag is display-only.
- **No topology change**: the Exness WS runs inside the existing single process.
- **Symbol deletion**: `DELETE /api/v1/market-data/tracked-symbols/{symbol}` already removes the `symbols` document, bars, sync status and every other symbol-keyed collection and cache key (`tracked_symbols_service.py:102-112`, :160-164). This phase adds no collection or Redis key keyed by symbol (the access point lives in memory); any later one must join that cascade.

## Security
Key material is read from `Settings` only and is a single-line 128-hex secret key. `EXNESS_API_BASE_URL` must be https on `api.exness.com`, a discovered access point must pass `allowed_access_point` (an `exness.com` or `exness-api.com` subdomain, plain https, no port, path or query) before it is stored or used, and `is_configured` fails closed. The client never logs headers, keys or signed bodies (T6.7). Order operations are refused in the client while `EXNESS_LIVE_TRADING` is false, before any network use, and T6.7 proves no request leaves.

## Rollback
First remove the Exness symbols with `DELETE /api/v1/market-data/tracked-symbols/XAUUSD%3AEXNESS` (and the same for EURUSD and BTCUSD) with `X-Admin-Token: $ADMIN_TOKEN`; the cascade deletes their `symbols` documents, bars and cache keys. Then `git revert` the phase commits on `develop`, push, and fast-forward `master` again to deploy the revert. Restore the T6.19 backups only if the seed itself has to be undone without the cascade.

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
