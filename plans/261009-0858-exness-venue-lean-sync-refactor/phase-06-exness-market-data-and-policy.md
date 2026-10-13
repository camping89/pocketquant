---
phase: 6
title: "Exness market data, quotes and policy"
status: pending
priority: P1
effort: 7d
dependencies: [5]
---

# Phase 06: Exness market data, quotes and policy

## Context Links
- Advice §2.5 (the files in `core/infra/exness/`), §2.7 and §3 (do not generate a client from the YAML).
- Spike journal `docs/journals/*-exness-api-spike.md`: its `access_point`, `ws_subprotocol`, `ticks_subscribe_mode` and `instrument_names` lines and the `summary.json` fields `access_point_resolved` and `ws_host` are inputs here. Redacted fixtures are in `tests/core_test/infra/exness/fixtures/`. The confirmed API host is the `U2 api host:` line of `plans/261009-0858-exness-venue-lean-sync-refactor/reports/user-preconditions.md`.
- Spike signer to promote: `scripts/exness_spike.py` (`load_secret_key`, `body_hash`, `sign_headers`, `ServerClock`, `validate_base_url`, `allowed_access_point`, `ws_url`).
- Access point (exness-api.com docs, Access Point / Host Discovery): signed `GET /v1/trading/access-point?account_id={id}` on the base host returns `{"access_point": "ap-….trading.exness.com", "account_id": …}`. The host is per account, rarely changes, and the docs give no TTL. Trading calls go to the access point; the docs' examples keep configuration, market data and history on the base host.
- Ports: `src/pocketquant/core/domain/market_data/interfaces.py` (`IDataProvider` :18, `IRealtimeQuoteProvider` :40). The quote callback contract is `src/pocketquant/app/market_data/app_services/quote_app_service.py:35` (`on_quote_update`), which reads `symbol`, `last_price`, `timestamp`, `bid`, `ask` and `volume`.
- Shapes to mirror: Binance REST `src/pocketquant/core/infra/binance/binance_client.py:50` (excludes the in-progress bar) and Binance WS `binance_websocket_client.py:97` (`run_forever`, watchdog and backoff).
- Registry: `SyncPolicies`, `binance_policy` and `MarketCalendar` in `src/pocketquant/engine/market_data/sync_policy.py`; built by `AdaptersProvider.get_sync_policies` in `src/pocketquant/app/di/adapters.py` (Phases 03–04). `Settings` is `src/pocketquant/core/config.py:30`; the OKX block ends at `okx_demo_mode` (:63).
- Spec facts (OpenAPI 1.0.2):
  - operation ids: `getLimits`, `getAccountDetails`, `getAvailableInstrumentList`, `getInstrumentCondition`, `getCandleHistory`, `getTradingStateSnapshot`, `getDealsHistory`, `getOperationStatus`, `openPosition` (POST `/v1/trading/accounts/{account_id}/positions`), `closePosition` (DELETE `.../positions/{position_id}`);
  - errors are `{"code": <int>, "error_message": "<STABLE_NAME>"}`; a 429 carries `REQUEST_RATE_LIMIT`, which the spec calls non-retryable automatically and asks clients to budget from `/limits`;
  - `/limits` returns `{"limits": {"rest": {"global_account_rate": {limit, window_seconds}, "methods": [{api_operation_id, rate_limit: {limit, window_seconds}, limits}]}, "websocket": {...}}}`;
  - idempotency keys are 5–128 chars of `A-Z a-z 0-9 . _ - ~`; reusing a key with the same payload returns the original `operation_id` without executing again;
  - candles take `from` + `count` (negative goes backward), `price_type=bid` is the default, the response is `candles[{time, open, high, low, close, volume}]` ascending; ticks are `{instrument, bid, ask, timestamp}` at most 1 per 500 ms; WS handshakes are signed as GET with path equality; subscribe messages are `{"id", "subscribe": {"event": "ticks", "instruments": [...]}}`.

<!-- Updated: Validation Session 1 - EXNESS policy carries its providers; no router; live trading switch off by default -->
## Goal
`XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` sync through the shared runner with the Exness `SyncPolicy`: native M1–D1 polled every minute, no cascade, session calendars from the spike, live ticks over WS, and a time cap so Exness can never delay Binance `sync_1m`. The policy carries `ExnessDataProvider` and `ExnessQuoteProvider`; `policy_for` resolves `:EXNESS` to them and `:BINANCE` to Binance only. The client is the single path to Exness endpoints and refuses every order operation while `EXNESS_LIVE_TRADING` is false (the default). The per-account access point is resolved once per process, in memory, and used for trading operations (and the WS when the spike showed it is required); there is no Redis cache, refresh job or re-resolve in this plan. The phase ends when D1 holds in prod.

## Files to Create or Modify
- Create in `src/pocketquant/core/infra/exness/`: `__init__.py`, `signer.py`, `mappers.py`, `client.py`, `websocket.py`, `data_provider.py` and `quote_provider.py`.
- Create: `scripts/backfill/policy_bars.py`.
- Create tests: `tests/core_test/infra/exness/{__init__,test_signer,test_mappers,test_client,test_websocket,test_data_provider,test_quote_provider}.py` and `tests/scripts/test_policy_bars.py`.
- Modify:
  - `src/pocketquant/core/config.py` (Exness settings)
  - `scripts/exness_spike.py` (import the promoted signer), `tests/scripts/test_exness_spike.py` (signer cases move to `test_signer.py`)
  - `src/pocketquant/engine/market_data/sync_policy.py` (`EXNESS_CALENDARS`, `exness_policy`)
  - `src/pocketquant/app/di/adapters.py` (`build_sync_policies`, `get_exness_client`, `get_sync_policies`)
  - `tests/engine_test/market_data/test_sync_policy.py`, `tests/app_test/unit/di/test_di_data_provider.py`, `tests/app_test/integration/test_di_resolution_characterization.py`

## Tasks

### T6.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c feat/exness-market-data`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `feat/exness-market-data`.

<!-- Updated: Validation Session 1 - settings move here from the spike; no key path; live switch default false -->
### T6.2 Exness settings fields
- **Goal:** `Settings` carries Exness configuration and the global live switch. Every field is optional and the switch defaults to off.
- **Target files and symbols:** `src/pocketquant/core/config.py` → `Settings`
- **Steps:**
  1. Below `okx_demo_mode` (:63), add `exness_api_base_url: str | None = None`, `exness_account_id: str | None = None`, `exness_api_key: SecretStr | None = None`, `exness_secret_key: SecretStr | None = None` and `exness_live_trading: bool = False`.
- **Success criteria:** `Settings` loads unchanged when no `EXNESS_*` variable is set, and live trading is off.
- **Verify:** `uv run python -c "from pocketquant.core.config import Settings; s=Settings(_env_file=None, app_name='a', app_version='1', environment='development', mongodb_url='mongodb://localhost:27017', mongodb_database='x', mongodb_min_pool_size=1, mongodb_max_pool_size=2, redis_url='redis://localhost:6379/0', redis_cache_ttl=1, log_level='INFO', log_format='json'); print(s.exness_api_key is None, s.exness_live_trading)"` prints `True False`.

<!-- Updated: Validation Session 1 - signer promoted from scripts/ into src/ -->
### T6.3 Promote the signer into `src/`
- **Goal:** One signer module, reused by the client and the spike (DRY).
- **Target files and symbols:** `src/pocketquant/core/infra/exness/signer.py` (`load_secret_key`, `body_hash`, `sign_headers`, `ServerClock`); `scripts/exness_spike.py`; `tests/core_test/infra/exness/test_signer.py`
- **Steps:**
  1. Create empty `src/pocketquant/core/infra/exness/__init__.py` and `tests/core_test/infra/exness/__init__.py`.
  2. Move `load_secret_key`, `body_hash`, `sign_headers` and `ServerClock` from `scripts/exness_spike.py` into `signer.py` verbatim. In the spike, import them from `pocketquant.core.infra.exness.signer`. `validate_base_url` and `ws_url` move to `client.py` in T6.6, and the spike imports them from there.
  3. Move the signer, key-loading and clock cases (Phase 01 T1.5 steps 1, 2, 3 and 6) from `tests/scripts/test_exness_spike.py` into `tests/core_test/infra/exness/test_signer.py`, importing from `pocketquant.core.infra.exness.signer`. The URL and redaction cases stay in the spike test until T6.6 updates the URL import.
- **Success criteria:** No signing code remains in `scripts/`.
- **Verify:** `grep -c "def sign_headers\|def load_secret_key" scripts/exness_spike.py` prints `0`. `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_signer.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - case-preserving instrument map from the spike -->
### T6.4 `mappers.py`
- **Goal:** Pure conversions live in one place, and the adapter owns all CFD semantics and instrument naming.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/mappers.py`. Symbols:
  - `INTERVAL_TO_EXNESS: dict[Interval, str] = {1m:"M1", 5m:"M5", 15m:"M15", 1h:"H1", 4h:"H4", 1d:"D1", 1w:"W1"}`
  - `EXNESS_INSTRUMENTS: dict[str, str]`, the case-preserving map from composite code to Exness instrument name, copied from the journal line `instrument_names` (for example `{"XAUUSD": "XAUUSDm"}` on a Standard account)
  - `instrument_name(symbol: str) -> str | None` and `composite_for(instrument: str) -> str | None`
  - `candle_to_bar(candle: dict, symbol: str, interval: Interval) -> Bar`
  - `tick_to_quote_dict(tick: dict, symbol: str) -> dict`
  - `units_to_lots(quantity: Decimal, *, contract_size, volume_min, volume_step, volume_max, max_lots: Decimal | None) -> Decimal | None`
  - `lots_to_units(lots: Decimal, contract_size: Decimal) -> float`
  - `format_price(price: float, point_digits: int) -> str`
- **Steps:**
  1. `instrument_name` returns `EXNESS_INSTRUMENTS.get(split_composite(symbol)[0])` when `split_composite(symbol)[1] == "EXNESS"`, else None. `composite_for` returns `f"{code}:EXNESS"` for the code whose name equals `instrument`, else None.
  2. `candle_to_bar` maps `datetime` (from `datetime.fromisoformat(candle["time"])` converted to UTC), the OHLC floats, `volume=float(candle["volume"])` and `tick_count=int(candle["volume"])`, with `symbol=symbol.upper()`.
  3. `tick_to_quote_dict` returns the key set of `aggtrade_to_quote_dict`: `symbol`, `timestamp`, `last_price=float(bid)`, `volume=None`, `bid`, `ask`, and `None` for `change`, `change_percent`, `open_price`, `high_price`, `low_price` and `prev_close`.
  4. `units_to_lots`:
     - compute `raw = quantity / contract_size`;
     - set `cap = min(volume_max, max_lots if max_lots is not None else volume_min)`;
     - set `steps = floor((min(raw, cap) - volume_min) / volume_step)`;
     - return `None` when `raw < volume_min`, otherwise `volume_min + steps * volume_step`.
     Use `Decimal` throughout.
  5. `lots_to_units` returns `float(lots * contract_size)`. `format_price` returns `f"{price:.{point_digits}f}"`.
- **Success criteria:** No float rounding errors in the lot maths, and instrument names keep their case.
- **Verify:** no verification needed; T6.5 covers this module.

<!-- Updated: Validation Session 1 - instrument map tests -->
### T6.5 Mapper tests
- **Goal:** Pin the conversions against the fixtures.
- **Target files and symbols:** `tests/core_test/infra/exness/test_mappers.py`
- **Steps:**
  1. `candle_to_bar` on the first candle of `fixtures/candles_XAUUSD_M1.json` gives `symbol "XAUUSD:EXNESS"`, a UTC-aware datetime, and `tick_count == int(volume)`.
  2. `tick_to_quote_dict` on the first data frame of `fixtures/ticks_sample.json` gives `last_price == bid`.
  3. `EXNESS_INSTRUMENTS == json.load(open(fixtures/summary.json))["instrument_names"]`; `instrument_name("xauusd:exness") == EXNESS_INSTRUMENTS["XAUUSD"]`; `instrument_name("XAUUSD:BINANCE") is None`; `composite_for(EXNESS_INSTRUMENTS["XAUUSD"]) == "XAUUSD:EXNESS"`.
  4. `units_to_lots`, with `contract_size` 100, `volume_min` 0.01, `step` 0.01, `volume_max` 200 and `max_lots` None: quantity 0.5 → `None`; quantity 1 → `Decimal("0.01")`; quantity 7.9 → `Decimal("0.01")` (clamped to the minimum lot). With `max_lots=Decimal("0.05")`, quantity 7.9 → `Decimal("0.05")`.
  5. `lots_to_units(Decimal("0.01"), Decimal("100")) == 1.0` and `format_price(2345.678912, 2) == "2345.68"`.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_mappers.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - endpoint table (no per-endpoint wrappers), URL allowlist, fail-closed is_configured, live gate, per-operation budgets with order priority, transport retries with the same key -->
<!-- Updated: Validation Session 1 - follow-up: no automatic retry on 429 for any call; Retry-After dropped -->
<!-- Updated: 2026-10-11 - per-account access point routing and re-resolve -->
<!-- Updated: Validation Session 3 - access point is an in-memory per-process resolve; no Redis cache, TTL, 421 handling or re-resolve -->
### T6.6 `client.py`
- **Goal:** One signed REST client and the only path to Exness endpoints. It validates its base URL, fails closed, budgets requests per operation from `/limits`, reserves capacity for order calls, retries transport errors with the same idempotency key, never retries a 429, and refuses order operations while live trading is off. It routes trading operations (and WS when required) to the per-account access point, resolved once per process and kept in memory.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/client.py`. Symbols:
  - `EXNESS_API_HOSTS: frozenset[str]` = `frozenset({"<U2 api host>"})`, copied from `user-preconditions.md`
  - `validate_base_url(url: str, allowed_hosts: frozenset[str] = EXNESS_API_HOSTS) -> str`, `allowed_access_point(value: str) -> str` and `ws_url(base_url: str, path: str) -> str`, moved from the spike (the spike now calls `validate_base_url(url, frozenset({api_host}))`)
  - `_ACCESS_POINT_OPS = frozenset({"getTradingStateSnapshot", "getOperationStatus", "openPosition", "closePosition"})`, `_WS_ON_ACCESS_POINT: bool` (True when the spike's `ws_host` is `access_point`)
  - `class ExnessApiError(Exception)` with `status`, `code` and `message`
  - `_ENDPOINTS: dict[str, tuple[str, str]]`, `_ORDER_OPS = frozenset({"openPosition", "closePosition"})`, `_PRIORITY_OPS = _ORDER_OPS | {"getOperationStatus"}`
  - `class _RateBudget` with `try_acquire(op: str, *, priority: bool) -> bool` and `async acquire(op, *, priority)`
  - `class ExnessClient(settings: Settings, *, rate_fraction: float = 1.0)` with property `is_configured`, `async access_point() -> str`, `async call(op, *, path_params=None, params=None, json_body=None, idempotency_key="") -> dict`, cached `async limits()`, `async instruments() -> list[str]` and `async conditions(instrument) -> dict` (1 h), `sign_ws_headers(path) -> dict[str, str]`, `ws_url(path) -> str` and `async close()`
- **Steps:**
  1. `_ENDPOINTS` maps each operation id from Context Links to `(method, path template)`; `getOperationStatus` is `GET /v1/trading/accounts/{account_id}/operations/{operation_id}` and `getAccessPoint` is `GET /v1/trading/access-point` (query `account_id`). No other method on the client names an endpoint; callers use `call("<operationId>", ...)`.
  2. `__init__` computes `is_configured` once and fails closed: inside one `try/except ValueError`, require all four `exness_*` connection settings, run `validate_base_url` and `load_secret_key(exness_secret_key.get_secret_value())`. On failure set it False and log `exness.not_configured` with the failing setting name only, never a value. `ws_url(path)` uses the validated base.
  3. `call`, in this order:
     - not configured → raise `ExnessApiError(0, "NOT_CONFIGURED", "exness settings missing or invalid")`;
     - `op in _ORDER_OPS and not settings.exness_live_trading` → raise `ExnessApiError(0, "LIVE_TRADING_DISABLED", "EXNESS_LIVE_TRADING is false")` before any budget or network use;
     - `await self._budget.acquire(op, priority=op in _PRIORITY_OPS)`;
     - format the path with `account_id` and `path_params`, build the query with `urlencode(params)`, request the literal `f"{path}?{query}"` (or `path` alone), serialize a JSON body with `json.dumps(body, separators=(",", ":")).encode()` sent as `content=` with `Content-Type: application/json`, and sign with `sign_headers(..., timestamp_ms=self._clock.now_ms())`; update the clock from `resp.headers["date"]` when present.
  4. Transport retries: on `httpx.TransportError`, retry at most twice (3 attempts in total) with the same `idempotency_key`, re-signed with a fresh timestamp, sleeping `2 ** attempt` seconds; after the last attempt raise `ExnessApiError(0, "TRANSPORT", ...)`.
  5. HTTP 429 is never retried, for any operation (the spec marks `REQUEST_RATE_LIMIT` non-retryable): log a warning `exness.rate_limited` with `op`, then raise `ExnessApiError(429, "REQUEST_RATE_LIMIT", ...)` immediately. The caller decides: the broker rejects the order and reconciles (Phase 07), and data calls fail for this run so the next scheduled run retries. `Retry-After` is not read.
  6. Errors: for any other non-2xx response, read `body = resp.json()` and raise `ExnessApiError(status, code=str(body.get("error_message") or body.get("code") or status), message=str(body.get("code", "")))`. Never log headers, the key or signed bodies.
  7. `_RateBudget(limits: dict, rate_fraction: float, clock=time.monotonic)`: a sliding-window deque for `limits["limits"]["rest"]["global_account_rate"]` and one per `methods[].api_operation_id` from its `rate_limit`. `reserve = max(1, global_limit // 5)`. A priority call may use the full global and per-operation limits; a non-priority call may use at most `int(limit * rate_fraction)` and never the last `reserve` global slots. `acquire` loops `while not self.try_acquire(...): await asyncio.sleep(0.05)`. The budget is built lazily from `limits()`, which itself bypasses the budget.
  8. `access_point()` returns the host used for `_ACCESS_POINT_OPS` (and for WS when `_WS_ON_ACCESS_POINT`). It returns the in-memory host when set; otherwise it runs `await call("getAccessPoint", params={"account_id": <account id>})` on the base URL, takes `allowed_access_point(body["access_point"])` (the field is a full https URL; `allowed_access_point` strips the scheme and returns the host), stores it in memory and returns it. A 404 means discovery is not offered for this account, so it stores and returns the base host. Any other `ExnessApiError` (and the `ValueError` from `allowed_access_point`) propagates and stores nothing, so the next call tries discovery again. There is no Redis cache, TTL, refresh or change log; a host change is picked up on the next process restart.
  9. Routing in `call`: an op in `_ACCESS_POINT_OPS` requests `https://{await self.access_point()}{path}` as an absolute URL (signing is unchanged, because the signed `path` excludes the host); every other op uses the base URL. `ws_url(path)` uses the in-memory access point when `_WS_ON_ACCESS_POINT` and a value is set, else the base.
  10. Every function stays ≤ 60 lines. Do not add one method per endpoint; that would only add delegations under the Phase 05 ratchet.
- **Success criteria:** Requests are signed exactly as sent, and no order request can leave the process while live trading is off.
- **Verify:** no verification needed; T6.7 covers this module.

<!-- Updated: Validation Session 1 - tests for live gate, URL allowlist, budgets, transport retries with same key -->
<!-- Updated: Validation Session 1 - follow-up: 429 is raised after exactly one request -->
### T6.7 Client tests
- **Goal:** Pin signing equality, error mapping, secret hygiene, the live gate, URL validation, budgets, transport retries and the no-retry rule for 429.
- **Target files and symbols:** `tests/core_test/infra/exness/test_client.py`
- **Steps:**
  1. Use `httpx.MockTransport` that records every request. Inject it by monkeypatching `ExnessClient._http` with `httpx.AsyncClient(transport=..., base_url="https://<U2 api host>")`. Use a Settings stub (`MagicMock(spec=Settings)`) holding a generated 128-hex secret key, `exness_api_base_url="https://<U2 api host>"`, and `exness_live_trading` set per test. Seed `_RateBudget` from `fixtures/limits.json`.
  2. Signing: the decoded `EXN-DATA.path` equals `request.url.raw_path` for `call("getCandleHistory", params={"instrument":"XAUUSD","from":"2026-01-01T00:00:00+00:00","count":-5})`; `EXN-IDEMPOTENCY-KEY == ""` on GET.
  3. Errors: a 400 with body `{"code": 1001, "error_message": "REQUEST_INVALID_COUNT"}` raises `ExnessApiError` with `code == "REQUEST_INVALID_COUNT"`.
  4. Secret hygiene: under `structlog.testing.capture_logs()`, no captured event contains the API key string.
  5. Fail closed: `is_configured` is False when `exness_api_key` is None, when the base URL is `http://<host>` or another host, and when the private key is a PEM string; `call` then raises `NOT_CONFIGURED` and the transport recorded 0 requests.
  6. Live gate: with `exness_live_trading=False`, `call("openPosition", json_body={...}, idempotency_key="order-00001")` and `call("closePosition", path_params={"position_id": "1"}, idempotency_key="order-00002")` raise `LIVE_TRADING_DISABLED`, and the transport recorded 0 requests.
  7. Retries: with `exness_live_trading=True`, an `httpx.ConnectError` followed by 202 makes `call("openPosition", ...)` succeed; both attempts carry the same `EXN-IDEMPOTENCY-KEY`, and the second carries `body_hash == body_hash(request.content)`. A transport answering 429 (with a `Retry-After: 2` header) raises `ExnessApiError` with `status == 429` and `code == "REQUEST_RATE_LIMIT"` for both `call("openPosition", ...)` and `call("getCandleHistory", ...)`; the transport recorded exactly 1 request per call, the patched `asyncio.sleep` was never awaited, and one `exness.rate_limited` event is captured per call.
  8. Budget: with a global limit of 5 and a fake clock, after 4 non-priority `try_acquire("getCandleHistory", priority=False)` calls the next non-priority call returns False while `try_acquire("openPosition", priority=True)` returns True; with `rate_fraction=0.5` and a per-operation limit of 10, the 6th non-priority call in the window returns False.
  9. Access point, with a transport answering `getAccessPoint` with `{"access_point": "ap-1.trading.exness.com"}`:
     - routing: `call("getTradingStateSnapshot")` makes 1 discovery request, then is sent to host `ap-1.trading.exness.com`; `call("getCandleHistory", ...)` is sent to the base host; a second `call("getTradingStateSnapshot")` makes no further discovery request; the decoded `EXN-DATA.path` has no host in either request;
     - rejection and fallback: discovery returning `{"access_point": "exness.com.evil.test"}` makes `access_point()` raise `ValueError`, and a later `access_point()` sends a new discovery request (nothing was stored); a discovery answering 404 makes `access_point()` return the base host.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_client.py -q` exits 0 with `passed`. `grep -rn "trading/accounts/{account_id}/positions" src | wc -l` prints `2` (the two `_ENDPOINTS` entries, nowhere else).

<!-- Updated: Validation Session 1 - handler exceptions never kill the stream -->
### T6.8 `websocket.py`
- **Goal:** One reconnecting signed WS stream, shaped like the OKX and Binance clients: backoff 1 s → 30 s and a circuit breaker after 10 consecutive failures that pauses for 300 s. A handler exception never kills the stream.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/websocket.py` → `class ExnessStream` with `__init__(client: ExnessClient, path: str, on_message: Callable[[dict], Awaitable[None]], on_connect: Callable[[], Awaitable[None]], stale_after_s: float | None)`, `async run_forever()`, `async send(message: dict)`, `is_connected() -> bool`, `async close()` and attribute `last_frame_at`.
- **Steps:**
  1. Connect with `websockets.connect(client.ws_url(path), additional_headers=client.sign_ws_headers(path), subprotocols=[...] or None, ping_interval=20, ping_timeout=10, close_timeout=5)`. The subprotocol value comes from the journal line `ws_subprotocol` and is a module constant `_SUBPROTOCOL` (`"exness-ws-protocol"` or `None`).
  2. After connecting, reset the backoff and failure count and `await on_connect()`. For each frame, `json.loads`, update `last_frame_at` and `await on_message(frame)` inside `try/except Exception`, logging a warning `exness_ws.handler_failed` and continuing. An invalid JSON frame is logged as a warning `exness_ws.invalid_json` and skipped.
  3. On any disconnect or connection exception: log `exness_ws.reconnecting` with `delay`, sleep the backoff, and double it up to a 30 s cap. After 10 consecutive failures, log an error `exness_ws.circuit_breaker_open` and sleep 300 s before the next attempt.
  4. When `stale_after_s` is set, a sibling watchdog task closes the socket if `last_frame_at` is older than `stale_after_s` (copy the Binance watchdog shape).
  5. Before each connect, `await client.access_point()` (a memory hit after the first time) so `client.ws_url(path)` sees the resolved host when `_WS_ON_ACCESS_POINT`. An `ExnessApiError` or `ValueError` from it counts as a connection failure and goes through step 3's backoff.
- **Success criteria:** Reconnect and backoff are deterministic and testable.
- **Verify:** no verification needed; T6.9 covers this module.

### T6.9 WS stream tests
- **Goal:** Pin the reconnect behaviour and handler isolation.
- **Target files and symbols:** `tests/core_test/infra/exness/test_websocket.py`
- **Steps:**
  1. Monkeypatch `websockets.connect` in the module to a fake that fails N times, then yields scripted frames and closes. Patch `asyncio.sleep` in the module with an `AsyncMock` that records delays. The client stub's `access_point` is an `AsyncMock` returning the base host.
  2. After 3 failures the recorded delays are `[1, 2, 4]`, and `on_connect` runs after the first success.
  3. 10 consecutive failures record one sleep of `300`.
  4. The handshake headers include `EXN-SIGN`, and the signed path equals the stream path.
  5. An `on_message` that raises on the first frame still receives the second frame, and one `exness_ws.handler_failed` event is captured.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_websocket.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - candles through call(), instrument name via the map -->
<!-- Updated: Validation Session 1 - follow-up: a 429 propagates; the next scheduled run retries -->
### T6.10 `data_provider.py`
- **Goal:** `IDataProvider` over native candles, paginated by `max_candles_per_request`, with the in-progress candle dropped.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/data_provider.py` → `class ExnessDataProvider(IDataProvider)` with `fetch_ohlcv(symbol, interval, n_bars=1000)`, `search_symbols(query) -> []` and `close()`.
- **Steps:**
  1. `name = instrument_name(symbol)`; when None, log a warning `exness.unknown_instrument` with `symbol` and return `[]`.
  2. `page` is the `max_candles_per_request` of method `getCandleHistory` from `await client.limits()`.
  3. Loop while `remaining > 0`:
     - `await client.call("getCandleHistory", params={"instrument": name, "timeframe": INTERVAL_TO_EXNESS[interval], "price_type": "bid", "from": cursor, "count": -min(remaining, page)})`, where `cursor` starts at the current UTC time in ISO seconds precision;
     - map each candle with `candle_to_bar`;
     - drop bars whose `datetime + INTERVAL_SECONDS[interval] > now`;
     - drop bars whose datetime is already collected;
     - prepend the rest;
     - stop when the page returned fewer candles than requested;
     - otherwise move `cursor` to the oldest returned candle time.
  4. Log `exness.fetch_completed` with `symbol` and `bars_fetched`. Return the bars ascending, trimmed to the last `n_bars`.
  5. Do not catch `ExnessApiError`. A 429 propagates: `fetch_with_retry` retries only empty or misaligned results, not exceptions, and `SyncService.sync_one` turns the exception into an `error` response, so the next scheduled run is the retry.
- **Success criteria:** Same contract as `BinanceClient.fetch_ohlcv`.
- **Verify:** no verification needed; T6.11 covers this module.

<!-- Updated: Validation Session 1 - follow-up: 429 propagation test -->
### T6.11 Data provider tests
- **Goal:** Pin pagination and in-progress filtering.
- **Target files and symbols:** `tests/core_test/infra/exness/test_data_provider.py`
- **Steps:**
  1. Use a fake client (`AsyncMock`) with `limits()` returning `fixtures/limits.json` with `max_candles_per_request` patched to 100, and `call("getCandleHistory", ...)` returning slices derived from `fixtures/candles_XAUUSD_M1.json`.
  2. `fetch_ohlcv("XAUUSD:EXNESS", Interval.MINUTE_1, 250)` makes 3 candle calls with counts `-100`, `-100` and `-50`, each with `instrument == EXNESS_INSTRUMENTS["XAUUSD"]`, and returns ascending, unique datetimes.
  3. A candle whose open time is `now - 30s` is excluded.
  4. `fetch_ohlcv("ZZZ:EXNESS", Interval.MINUTE_1, 10)` returns `[]` without calling the client.
  5. A fake client whose `call` raises `ExnessApiError(429, "REQUEST_RATE_LIMIT", "x")` makes `fetch_ohlcv` raise that error after exactly one `call`.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_data_provider.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - subscriptions validated against the cached instrument list; subscribe mode from the spike -->
### T6.12 `quote_provider.py`
- **Goal:** `IRealtimeQuoteProvider` over WS ticks, using the same callback dict as Binance, never sending an unknown instrument.
- **Target files and symbols:** `src/pocketquant/core/infra/exness/quote_provider.py` → `class ExnessQuoteProvider`. Members: `last_tick_at`, `connect()`, `disconnect()`, `subscribe(symbol, callback) -> str`, `unsubscribe(symbol)`, `run_forever()`, `is_connected()`, `subscription_count` and `subscriptions`.
- **Steps:**
  1. Module constant `_TICKS_SUBSCRIBE_MODE` = the journal's `ticks_subscribe_mode` (`"add"` or `"replace"`). `self._subscriptions: dict[str, tuple[str, Callable]]` maps the composite symbol to `(instrument name, callback)`; `self._rejected: set[str]`.
  2. `subscribe`: `composite = symbol.upper()`, `name = instrument_name(composite)`. If `name is None` or `name not in await client.instruments()`, then on the first time only add `composite` to `_rejected` and log a warning `exness_ws.unknown_instrument`; return `composite` without storing or sending anything. Otherwise store the entry and, if the stream is connected, send `{"id": f"sub-{name}", "subscribe": {"event": "ticks", "instruments": [name]}}` in `add` mode, or the same message with every stored name in `replace` mode.
  3. `unsubscribe` removes the entry locally; in `replace` mode with a connected stream it sends the remaining full list. Frames for instruments not stored are ignored.
  4. `run_forever` runs `ExnessStream(client, f"/v1/server-events/accounts/{account}/ws/ticks", on_message=self._on_frame, on_connect=self._resubscribe_all, stale_after_s=None)`. Ticks pause in closed markets, so there is no stale watchdog. `_resubscribe_all` sends one message with every stored name when there is at least one.
  5. `_on_frame`: when the frame has `instrument`, `bid` and `ask`, find the composite symbol from the stored names, build `tick_to_quote_dict`, set `last_tick_at`, and call the callback (awaiting it if it is a coroutine) inside `try/except Exception` with a warning `exness_ws.callback_failed`. A frame carrying `MARKET_TRADE_DISABLED` or `trading_disabled` logs a warning `exness_ws.trading_disabled`; any other error frame logs `exness_ws.error_frame`.
  6. `connect()` is a no-op, because the connection happens inside `run_forever`. `disconnect()` closes the stream.
- **Success criteria:** It satisfies the Protocol structurally, and unknown instruments never reach the socket.
- **Verify:** no verification needed; T6.13 covers this module.

<!-- Updated: Validation Session 1 - unknown-instrument and subscribe-mode tests -->
### T6.13 Quote provider tests
- **Goal:** Pin the callback contract, validation and subscribe semantics.
- **Target files and symbols:** `tests/core_test/infra/exness/test_quote_provider.py`
- **Steps:**
  1. `isinstance(ExnessQuoteProvider(client_stub), IRealtimeQuoteProvider)` is True; `client_stub.instruments()` returns the names from `fixtures/instruments.json`.
  2. After `subscribe("XAUUSD:EXNESS", cb)`, feeding `_on_frame` the first fixture tick for XAUUSD calls `cb` once with `symbol == "XAUUSD:EXNESS"` and `last_price == bid`.
  3. A frame for an unsubscribed instrument does not call `cb`, and a `cb` that raises does not propagate.
  4. `subscribe("ZZZ:EXNESS", cb)` called three times with a connected fake stream sends no message, leaves `subscriptions` without the key, and captures exactly one `exness_ws.unknown_instrument` event.
  5. With `_TICKS_SUBSCRIBE_MODE` patched to `"replace"`, subscribing XAUUSD then EURUSD on a connected fake stream sends a second message whose `instruments` holds both names; with `"add"` it holds only the EURUSD name.
  6. An error frame logs `exness_ws.trading_disabled` and does not raise.
- **Success criteria:** All tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/core_test/infra/exness/test_quote_provider.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - Exness policy factory with session calendars and time cap -->
### T6.14 Exness policy and calendars
- **Goal:** Exness is policy #2 with no new job code (A-v), with calendars built from the recorded `trade_sessions`.
- **Target files and symbols:** `src/pocketquant/engine/market_data/sync_policy.py` → `_EXNESS_SESSIONS`, `EXNESS_CALENDARS`, `exness_policy(data_provider, quote_provider) -> SyncPolicy`
- **Steps:**
  1. `_EXNESS_SESSIONS: dict[str, list[dict[str, str]]]` holds, for `XAUUSD`, `EURUSD` and `BTCUSD`, the `trade_sessions` list copied verbatim from `tests/core_test/infra/exness/fixtures/conditions_<I>.json`. `EXNESS_CALENDARS = {code: MarketCalendar.from_week_sessions(s) for code, s in _EXNESS_SESSIONS.items()}`.
  2. `exness_policy` returns `SyncPolicy(exchange="EXNESS", data_provider=data_provider, quote_provider=quote_provider, poll_intervals=(Interval.MINUTE_1, Interval.MINUTE_5, Interval.MINUTE_15, Interval.HOUR_1, Interval.HOUR_4, Interval.DAY_1), poll_n_bars=100, cascade=False, cascade_lookback_minutes=0, integrity_intervals=<same 6>, backfill_n_bars=5000, poll_time_cap_s=40.0, history_days={Interval.MINUTE_1: 365, Interval.MINUTE_5: 730, Interval.MINUTE_15: 1095, Interval.HOUR_1: None, Interval.HOUR_4: None, Interval.DAY_1: None}, calendars=EXNESS_CALENDARS)`. The 40 s cap keeps `sync_1m` (cron every minute, `max_instances=1`) from overrunning into the next Binance run.
  3. Extend `test_sync_policy.py`:
     - `_EXNESS_SESSIONS[I] == json.load(open(f"tests/core_test/infra/exness/fixtures/conditions_{I}.json"))["trade_sessions"]` for each `I` (adjust the key path to the fixture's layout if the conditions sit under a wrapper key, and say so in the test);
     - for each enabled session `(start, end)` of `EXNESS_CALENDARS["XAUUSD"].sessions`, a datetime at `start` is open, and a datetime at `end` is closed unless another session starts there;
     - `SyncPolicies([binance_policy(...), exness_policy(...)])`: `policy_for("XAUUSD:EXNESS").cascade is False`, `policy_for("XAUUSD:BINANCE").exchange == "BINANCE"`, `market_calendar("XAUUSD:EXNESS") is EXNESS_CALENDARS["XAUUSD"]`, and iteration order is BINANCE then EXNESS.
- **Success criteria:** The policy is declarative only; the calendar ignores slots outside sessions.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/engine_test/market_data/test_sync_policy.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - registry built by one function shared with scripts; no router -->
<!-- Updated: Validation Session 3 - no access point preload or refresh job; register_sync_jobs is untouched -->
### T6.15 DI registers the Exness policy
- **Goal:** Binance stays first; the Exness policy is added only when the client is configured. Building the client makes no Exness request.
- **Target files and symbols:** `src/pocketquant/app/di/adapters.py` → `build_sync_policies(settings: Settings, exness_client: ExnessClient) -> SyncPolicies`, `AdaptersProvider.get_exness_client(self, settings: Settings) -> AsyncIterator[ExnessClient]` (async generator in the shape of `InfrastructureProvider.get_cache` in `app/di/infrastructure.py` after Phase 04: builds `ExnessClient(settings)`, yields it, then awaits `close()`; no preload), `AdaptersProvider.get_sync_policies(self, settings, exness_client) -> SyncPolicies`
- **Steps:**
  1. `build_sync_policies` builds `[binance_policy(data_provider=BinanceClient(settings=settings), quote_provider=BinanceWebSocketClient())]`, appends `exness_policy(data_provider=ExnessDataProvider(exness_client), quote_provider=ExnessQuoteProvider(exness_client))` when `exness_client.is_configured`, and returns `SyncPolicies(...)`.
  2. `get_sync_policies` returns `build_sync_policies(settings, exness_client)`.
  3. Do not modify `src/pocketquant/engine/market_data/sync_runner.py`; `register_sync_jobs` never resolves `ExnessClient`, so the characterization fake containers need no new binding.
  4. `test_di_data_provider.py`: with unset Exness settings (`MagicMock(spec=Settings)` with the Exness attributes `None`), `[p.exchange for p in policies] == ["BINANCE"]` and the Binance assertions stay. With a configured stub client (`is_configured=True`), the list is `["BINANCE", "EXNESS"]`, and the EXNESS policy holds an `ExnessDataProvider` and an `ExnessQuoteProvider`.
  5. `test_di_resolution_characterization.py`: `ExnessClient` resolves without any Exness request, and `SyncPolicies` still resolves with `policy_for("BTCUSDT:BINANCE")` unchanged. The test settings carry no Exness values, so `policy_for("XAUUSD:EXNESS") is None`.
- **Success criteria:** With no Exness env the behaviour is identical for Binance.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/unit/di tests/app_test/integration/test_di_resolution_characterization.py tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 with `passed`. `git diff --name-only master -- src/pocketquant/engine/market_data/sync_runner.py` prints nothing.

<!-- Updated: Validation Session 1 - one provider-agnostic deep backfill path instead of an Exness-only script -->
### T6.16 Provider-agnostic deep backfill script
- **Goal:** Deep history beyond the 5000-bar request cap for any exchange with a policy, at a fraction of the rate budget, never alongside live trading.
- **Target files and symbols:** `scripts/backfill/policy_bars.py` → `parse_args`, `async run(cfg) -> int`, `main`; `tests/scripts/test_policy_bars.py`
- **Steps:**
  1. CLI: `--symbol` (composite), `--interval` (one of `1m 5m 15m 1h 4h 1d 1w`), `--days INT`, `--rate-fraction FLOAT` (default 0.5) and `--dry-run`.
  2. `settings = get_settings()`. If `settings.exness_live_trading` is true, print `refusing: EXNESS_LIVE_TRADING is true` and exit 3.
  3. `policies = build_sync_policies(settings, ExnessClient(settings, rate_fraction=cfg.rate_fraction))`; `policy = policies.policy_for(cfg.symbol)`. None → print `no policy for <exchange>` and exit 2. Reject `days` greater than `policy.history_days.get(interval)` when that value is set, with exit 2.
  4. `n_bars = days * 86400 // INTERVAL_SECONDS[interval]`; fetch with `await policy.data_provider.fetch_ohlcv(symbol, interval, n_bars)`. Unless `--dry-run`, connect `Database()` with `settings` and call `BarRepository(db).insert_many(chunk, source=SOURCE_REST_BACKFILL)` in chunks of 5000.
  5. Print exactly one line, `fetched=<n> inserted=<n> total_bars=<BarRepository.count(symbol, interval)>` (`total_bars=-1` on `--dry-run`). Exit 0, or 1 when fetched is 0.
  6. `scripts/backfill/binance_bars.py` stays as it is: it uses Binance's start/end klines window plus `--replace` and checkpoints, which the policy path does not need. `policy_bars.py` is the one path that works for every policy.
  7. `tests/scripts/test_policy_bars.py`: with `get_settings` monkeypatched to a stub with `exness_live_trading=True`, `main([...])` returns 3; with it false and `build_sync_policies` patched to a registry without EXNESS, `--symbol XAUUSD:EXNESS` returns 2.
- **Success criteria:** The script is safe to run in prod and works for any registered policy.
- **Verify:** `uv run python scripts/backfill/policy_bars.py --help` exits 0. `.venv/Scripts/python.exe -m pytest tests/scripts/test_policy_bars.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - Windows-safe metrics, ratchet in the gate, no router files -->
### T6.17 Phase gate
- **Goal:** Full green, with the metric ratchet holding.
- **Target files and symbols:** whole repo
- **Steps:**
  1. `just test 2>&1 | tail -n 3`
  2. `uv run ruff check`
  3. `uv run pyright`
  4. `uv run lint-imports`
  5. The venue command from Phase 02 T2.6.
  6. `.venv/Scripts/python.exe -m pytest tests/baseline -q`
  7. `uv run python scripts/code_metrics.py --ratchet`
  8. `uv run python scripts/code_metrics.py --out .cache/metrics.json`
- **Success criteria:** Green, the ratchet holds, and no function over 60 lines in `core/infra/exness/`.
- **Verify:**
  - Steps 1–4 meet the same pass conditions as Phase 04 T4.6.
  - Step 5's count equals the baseline.
  - Step 6 exits 0.
  - Step 7 exits 0. If it fails, follow the Failure Protocol; the expected remedy is to inline thin client or provider wrappers, never to raise the ceiling.
  - `uv run python -c "import json;d=json.load(open('.cache/metrics.json'));print([f for f in d['functions_over_60'] if 'exness' in f])"` prints `[]`.

<!-- Updated: Validation Session 1 - boolean-only is_configured check after deploy; admin-token wording corrected -->
### T6.18 Ship, track symbols and verify D1 in prod
- **Goal:** Exness bars and quotes flow in prod. Run this during FX market hours.
- **Target files and symbols:** git, VPS API
- **Steps:**
  1. `git add -A src tests scripts plans/261009-0858-exness-venue-lean-sync-refactor`
  2. `git commit -m "feat(exness): add candle data provider, tick quote provider and exness sync policy"`
  3. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
  4. Boolean-only configuration check: `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"from pocketquant.core.config import get_settings;from pocketquant.core.infra.exness.client import ExnessClient;s=get_settings();print(ExnessClient(s).is_configured, s.exness_live_trading)\""`.
  5. Add the tracked symbols. The route checks `X-Admin-Token` only when `ADMIN_TOKEN` is set (`src/pocketquant/app/middleware/admin_auth_middleware.py:25-31`); the command passes the container's `$ADMIN_TOKEN`, which may be empty, and never echoes it.
     ```bash
     ssh -i "$KEY" "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
     for s in XAUUSD EURUSD BTCUSD; do curl -s -X POST http://localhost:41921/api/v1/market-data/tracked-symbols -H "Content-Type: application/json" -H "X-Admin-Token: $ADMIN_TOKEN" -d "{\"symbol\":\"$s:EXNESS\"}"; echo; done
     EOF
     ```
  6. Run the manual sync with the same pattern:
     ```bash
     curl -s -X POST http://localhost:41921/api/v1/market-data/sync -H "Content-Type: application/json" -d '{"symbol":"XAUUSD:EXNESS","interval":"1m","n_bars":1000,"source":"rest_backfill"}'
     ```
  7. Check the bar stream with the same pattern: `timeout 70 curl -sN "http://localhost:41921/api/v1/market-data/bars/stream/XAUUSD%3AEXNESS?interval=1m" | grep -m1 -c '"is_in_progress": true'`.
  8. Check the quote stream with the same pattern: `timeout 30 curl -sN "http://localhost:41921/api/v1/quotes/stream/XAUUSD%3AEXNESS" | grep -m1 -c '"bid":'`.
  9. Wait 3 minutes, then check sync status with the same pattern: `curl -s "http://localhost:41921/api/v1/market-data/sync-status/XAUUSD%3AEXNESS?interval=1h"`.
- **Success criteria:** D1 holds, Binance keeps syncing, and live trading is off.
- **Verify:**
  - `gh run watch` exits 0, and the CI log `=== Verdict:` line contains `, 0 failures)`.
  - Step 4 prints `True False`.
  - Step 6's JSON has `"status":"completed"` and `total_bars >= 1000`, checked by piping it to `python -c "import json,sys;d=json.load(sys.stdin);print(d['status']=='completed' and d['total_bars']>=1000)"`, which prints `True`.
  - Step 7 prints `1`.
  - Step 8 prints `1`.
  - Step 9 contains `"status":"completed"`.
  - The same step 9 command for `BTCUSDT%3ABINANCE?interval=1m` also contains `"status":"completed"`.

## Verification
T6.3–T6.16 (unit, DI and characterization), T6.17 (gate and ratchet) and T6.18 (D1 in prod, live trading off).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any change that would enable live Exness trading, set `EXNESS_LIVE_TRADING=true`, or send an order request.
- Exness limits make policy A-v infeasible (for example the 18 candle requests per minute do not fit the `getCandleHistory` budget).
- Anything would need a new container, worker or deployment topology change.
- The ratchet would need a higher ceiling.
- A step would delete Binance or OKX code, or a test failure stays unexplained.

<!-- Updated: Validation Session 1 - follow-up: 429 surfaced, never retried -->
## Risks
- **Rate limits** (M/H): 3 instruments × 6 TF = 18 candle requests a minute, plus backfill and repair. Mitigation: per-operation and global budgets from `/limits`, a reserved slice for order calls, `rate_fraction` for the deep backfill, and the 40 s poll cap. A 429 is never retried automatically, as the spec requires; it is logged and surfaced, orders are rejected and reconciled, and data calls wait for the next scheduled run. If the limits make A-v infeasible, STOP and ask the user.
- **Closed-market noise**: the runner skips polling, and integrity skips the grid, outside the recorded sessions. `sync-status.is_stuck` may show true over the weekend; that flag is display-only.
- **Instrument naming** (M/M): a Standard account uses suffixed names (`XAUUSDm`). Mitigation: `EXNESS_INSTRUMENTS` keeps the exact names from the spike, and the quote provider validates against the cached instrument list.
- **No topology change**: the Exness WS runs inside the existing single process.
- **Access point moves** (L/L while live trading is off): the host rarely changes and the docs give no TTL. It is resolved once per process; a change is picked up on the next restart, which every deploy causes. Persistence and refresh belong to the go-live plan. If the spike shows discovery is unavailable (404), the base host is used for every call.

## Security
Key material is read from `Settings` only and is a single-line 128-hex secret key. `EXNESS_API_BASE_URL` must be https on the user-confirmed host, a discovered access point must pass `allowed_access_point` (an `exness.com` or `exness-api.com` subdomain) before it is stored or used, and `is_configured` fails closed. The client never logs headers, keys or signed bodies (T6.7). Order operations are refused in the client while `EXNESS_LIVE_TRADING` is false, before any network use, and T6.7 proves no request leaves.

## Rollback
First remove the Exness tracked symbols (`DELETE /api/v1/market-data/tracked-symbols/XAUUSD%3AEXNESS`, and the same for EURUSD and BTCUSD, with `X-Admin-Token: $ADMIN_TOKEN`). Then `git revert` the merge commit and push. Exness bars left in `bars` are harmless.

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
