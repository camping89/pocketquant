---
phase: 5
title: "TradingView History Adapter, Seeding and Backfill"
status: pending
priority: P1
effort: "1.5d"
dependencies: [3, 4]
---

## Context

(Advice Phase 4.) The first futures data lands here. The scraper library is isolated
behind an internal client interface so it can be swapped without touching the adapter,
the mapper never trusts the library's DataFrame index for timestamps, and the bar cap
and credentials are configuration with no branching on the TradingView plan tier.

Two verified facts drive the design:
- `tvDatafeed`'s `__create_df` builds each bar timestamp with
  `datetime.datetime.fromtimestamp(float(xi[4]))` — NAIVE HOST-LOCAL time. The raw
  epoch is consumed inside the library and is not re-exposed on the DataFrame.
- The library is not on PyPI; it installs from
  `git+https://github.com/rongardF/tvdatafeed.git` and imports as `tvDatafeed`
  (capital D).

## Tasks

### Task 1 — Add the scraper dependency and TradingView settings

**Goal.** The library is installed and every entitlement knob is a setting.

**Target files and symbols.**
- `pyproject.toml` — `[project] dependencies`.
- `src/pocketquant/core/config.py` — `Settings`.

**Steps.**
1. Resolve the current upstream commit and PIN it. Do not depend on a moving
   branch: this is an unofficial scraper, and a silent upstream change is one of the
   named risks of this whole plan. Run
   `git ls-remote https://github.com/rongardF/tvdatafeed.git HEAD` and copy the
   40-character sha.
2. Add to `dependencies`, substituting that sha for `<SHA>`:
   `"tvdatafeed @ git+https://github.com/rongardF/tvdatafeed.git@<SHA>",`
   Record the sha and the date you resolved it in a comment on the line above, so a
   future reader can tell how stale the pin is.
3. Run `uv sync` and confirm the lock updates. If `uv sync` fails to resolve the
   dependency, STOP and follow the Failure Protocol — do NOT substitute a different
   package or fall back to an unpinned ref.
3. Add to `Settings`, under a `# TradingView (index futures data source)` comment:
   ```python
   tradingview_username: str | None = None
   tradingview_password: SecretStr | None = None
   tradingview_auth_token: SecretStr | None = None
   tradingview_max_bars: int = 5000
   tradingview_poll_seconds: int = 60
   tradingview_delayed_data: bool = True
   ```
   `SecretStr` is already imported at `core/config.py:6`.
4. `tradingview_poll_seconds` defaults to 60, not 10: with delayed CME data (the
   default on every plan until the non-professional add-on is bought) polling faster
   only increases ban risk.
5. Document the field NAMES in `README.md`. Put the VALUES only in
   `../pocketquant-config/vps/default/.env` (prod) and
   `../pocketquant-config/local/all-local.env` (dev). Never write a value into this
   repository, its tests, its docs or a commit message.

**Success criteria.** The library imports and the settings load with defaults.

**Verify.** `uv run python -c "import tvDatafeed; from pocketquant.core.config import Settings; print(hasattr(tvDatafeed,'TvDatafeed'), Settings().tradingview_max_bars)"` prints `True 5000`.

---

### Task 2 — Internal TradingView client interface

**Goal.** The scraper is behind one narrow seam, so replacing it is one new class.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/tradingview/` with `__init__.py`.
- New file `src/pocketquant/core/infra/tradingview/tradingview_client_interface.py`.
- Symbols: `RawBar`, `ITradingViewClient`.

**Steps.**
1. Define a frozen dataclass `RawBar` with fields
   `epoch_seconds: float`, `open: float`, `high: float`, `low: float`,
   `close: float`, `volume: float`. This is the seam's currency — an instant plus
   OHLCV, with no library types leaking through.
2. Define a `Protocol` named `ITradingViewClient` with:
   ```python
   async def fetch_bars(
       self, code: str, exchange: str, interval: Interval, n_bars: int, fut_contract: int | None
   ) -> list[RawBar]: ...
   def is_authenticated(self) -> bool: ...
   ```
3. Naming follows the repo precedent `strategy_service_interface.py` /
   `IStrategyService` (docs/code-standards.md, "Class Naming by Layer"). This is an
   infra-internal seam, not a domain port, so it stays in `core/infra`.

**Success criteria.** The module imports with no dependency on `tvDatafeed`.

**Verify.** `uv run python -c "
import sys
from pocketquant.core.infra.tradingview.tradingview_client_interface import ITradingViewClient, RawBar
print('tvDatafeed' not in sys.modules)"` prints `True`.

---

### Task 3 — `TvDatafeedClient`

**Goal.** The synchronous, thread-based library runs off the event loop and yields
epoch-bearing raw bars.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tvdatafeed_client.py`.
- Symbol: `TvDatafeedClient`.

**Steps.**
1. Constructor takes `settings: Settings`. Build the underlying client lazily on the
   first call, inside `asyncio.to_thread`, because login performs blocking network I/O.
2. Login: when `tradingview_username` and `tradingview_password` are both set, call
   `TvDatafeed(username=..., password=...)`. On any exception, log one WARNING
   `provider.tradingview.auth` with `status="degraded"` and the exception type (NEVER
   the credentials), then fall back to `TvDatafeed()` (the library's anonymous mode).
   The process must never crash on a login failure.
3. `is_authenticated()` returns whether the logged-in construction succeeded.
4. `fetch_bars(...)` runs
   `await asyncio.to_thread(self._tv.get_hist, symbol=code, exchange=exchange, interval=<mapped>, n_bars=n_bars, fut_contract=fut_contract)`.
5. Convert the returned DataFrame to `list[RawBar]`. For the epoch, DO NOT read the
   index value as if it were UTC. Recover the original epoch:
   ```python
   idx = row_timestamp.to_pydatetime()
   epoch = idx.timestamp() if idx.tzinfo is None else idx.astimezone(UTC).timestamp()
   ```
   A naive datetime's `.timestamp()` interprets it in the host zone — which is exactly
   the zone the library used to build it — so the round trip recovers the true epoch on
   ANY host, not only under `TZ=UTC`. This is what lets the CI timezone matrix from
   Phase 1 Task 12 pass.
6. Return `None`/empty safely: `get_hist` returns `None` when its regex match fails.
   Treat that as an empty list and log one DEBUG.
7. Log at DEBUG only — this runs once per symbol per interval per cron tick.

**Success criteria.** The client returns `RawBar`s whose `epoch_seconds` are
host-zone independent.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q` exits 0 (tests written in Task 5).

---

### Task 4 — TradingView mappers

**Goal.** Composite symbols, intervals and raw bars translate in exactly one place.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_mappers.py`.
- Symbols: `INTERVAL_TO_TRADINGVIEW`, `split_futures_symbol`, `raw_bar_to_bar`.

**Steps.**
1. `split_futures_symbol(composite: str) -> tuple[str, str, int | None]`:
   split on `:` (the composite format is `{CODE}:{EXCHANGE}`); when the code ends with
   `1!`, strip the suffix and return `fut_contract=1`; otherwise return the code
   unchanged and `fut_contract=None`. So `ES1!:CME_MINI` becomes
   `("ES", "CME_MINI", 1)`.
2. `INTERVAL_TO_TRADINGVIEW`: a `dict[Interval, tvDatafeed.Interval]` covering all
   seven members. Verify the exact enum member names against the installed package
   before writing them (step 5 below) — the expected names are `in_1_minute`,
   `in_5_minute`, `in_15_minute`, `in_1_hour`, `in_4_hour`, `in_daily`, `in_weekly`.
   Import `tvDatafeed.Interval` under an alias so it does not shadow the domain
   `Interval`.
3. `raw_bar_to_bar(raw: RawBar, symbol: str, interval: Interval) -> Bar` builds
   `datetime=datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)` and copies OHLCV.
   Set `tick_count=0`. Never construct a naive datetime here — `Bar`'s validator from
   Phase 1 Task 7 rejects it.
4. Keep the mapper module free of any network call, exactly like
   `core/infra/binance/binance_mappers.py`.
5. Before writing the interval map, print the real member names and fix the map to
   match: run the Verify command below.

**Success criteria.** All seven domain intervals map to a real `tvDatafeed.Interval`
member.

**Verify.** `uv run python -c "
import tvDatafeed
from pocketquant.core.infra.tradingview.tradingview_mappers import INTERVAL_TO_TRADINGVIEW
from pocketquant.core.domain.shared.enums import Interval
print(len(INTERVAL_TO_TRADINGVIEW) == len(list(Interval)), all(isinstance(v, tvDatafeed.Interval) for v in INTERVAL_TO_TRADINGVIEW.values()))"` prints `True True`.

---

### Task 5 — Offline mapper tests with a host-zone matrix

**Goal.** The naive-local-time trap is provably closed.

**Target files and symbols.**
- New package dir `tests/core_test/infra/tradingview/`.
- New file `tests/core_test/infra/tradingview/test_tradingview_mappers.py`.
- New fixture file `tests/core_test/infra/tradingview/fixtures/es_1h_raw.json`.

**Steps.**
1. Build the fixture as a JSON list of 6 objects, each with keys
   `epoch_seconds`, `open`, `high`, `low`, `close`, `volume`. Use real ES 1h values
   with epochs spanning the 2026-03-08 DST transition. STORE THE EPOCHS, never a
   formatted datetime string — a stored local-time string would itself be
   zone-dependent and the fixture would be useless.
2. Write 6 tests:
   - `test_split_es_futures_symbol`: `split_futures_symbol("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)`.
   - `test_split_non_futures_symbol`: `split_futures_symbol("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)`.
   - `test_interval_map_is_total`: every `Interval` member has an entry.
   - `test_raw_bar_to_bar_is_utc_aware`: the produced `Bar.datetime.tzinfo` is `UTC`.
   - `test_raw_bar_epoch_round_trip`: `bar.datetime.timestamp() == raw.epoch_seconds`
     for all 6 fixture rows.
   - `test_naive_local_datetime_recovers_the_same_epoch`: for each fixture epoch,
     build `naive = datetime.fromtimestamp(epoch)` (host-local, mirroring the library),
     then assert `naive.timestamp() == epoch`. Run this test's module under the CI
     timezone matrix.
3. Add no network access and no `tvDatafeed` import to the test module other than for
   the interval-map assertion.

**Success criteria.** 6 tests pass under UTC AND under a non-UTC zone.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q && TZ=America/Chicago uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q` exits 0 and each run prints `6 passed`.

---

### Task 6 — `TradingViewAdapter` (the history port)

**Goal.** A provider that satisfies `IDataProviderPort`, clamps to the configured bar
cap, and never returns an in-progress bar.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_adapter.py`.
- Symbol: `TradingViewAdapter(IDataProviderPort)`.

**Steps.**
1. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_factory: TradingCalendarFactory`.
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - `n_bars = min(n_bars, settings.tradingview_max_bars)`;
   - `code, exchange, fut_contract = split_futures_symbol(symbol)`;
   - `raws = await client.fetch_bars(code, exchange, interval, n_bars, fut_contract)`;
   - map each through `raw_bar_to_bar`;
   - resolve `calendar = await calendar_factory.for_symbol(symbol)` and DROP any bar
     whose `datetime >= calendar.bar_start(datetime.now(UTC), interval)` — that is the
     in-progress bar. Log the dropped count at DEBUG, mirroring
     `binance_adapter.py`'s `binance.in_progress_bar_filtered`;
   - return the list ascending by `datetime`.
3. `search_symbols(query)` returns `[]` and logs one DEBUG. Symbol search stays a
   Binance capability; the routing adapter already delegates search to the crypto
   primary (Phase 4 Task 4 step 3).
4. `close()` is a no-op coroutine.
5. Log one INFO `tradingview.fetch_completed` per call with symbol, interval and bar
   count — one-shot per symbol per interval per cron tick, which is within the
   CLAUDE.md log-frequency rule. Never log the raw payload above DEBUG.

**Success criteria.** The adapter clamps `n_bars` and drops the in-progress bar.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q` exits 0 and prints `5 passed` (tests written in Task 7).

---

### Task 7 — Adapter tests against a fake client

**Goal.** Adapter behaviour is pinned with no network access.

**Target files and symbols.**
- New file `tests/core_test/infra/tradingview/test_tradingview_adapter.py`.

**Steps.**
1. Build a `FakeTradingViewClient` implementing `ITradingViewClient` from the JSON
   fixture.
2. Write 5 tests: `test_n_bars_is_clamped_to_max_bars`,
   `test_futures_symbol_is_split_with_fut_contract_1`,
   `test_in_progress_bar_is_dropped`,
   `test_returned_bars_are_utc_aware_and_ascending`,
   `test_empty_client_result_returns_empty_list`.
3. `test_in_progress_bar_is_dropped` must freeze "now" by injecting a stub calendar
   whose `bar_start` returns a fixed instant, so the test does not depend on the clock.

**Success criteria.** 5 tests pass with no network access.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q` exits 0 and prints `5 passed`.

---

### Task 8 — Register TradingView in DI

**Goal.** `INDEX_FUTURE` symbols route to TradingView; crypto still routes to Binance.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` — `get_data_provider` (edited in
  Phase 4 Task 7).

**Steps.**
1. Add `"tradingview": TradingViewAdapter(client=TvDatafeedClient(settings=settings), settings=settings, calendar_factory=calendar_factory)`
   to the `providers` dict, and add `calendar_factory: TradingCalendarFactory` to the
   provider method signature so Dishka injects it.
2. Change nothing else. The asset-class map in `Settings` already points
   `INDEX_FUTURE` at `["tradingview"]`.
3. Confirm the `providers` dict is the ONLY place in `src/` that names the string
   `"tradingview"` outside `core/infra/tradingview/` and `core/config.py`.

**Success criteria.** The container resolves and one adapter entry was the whole change.

**Verify.** `uv run pytest tests/app_test/integration/ -q && test "$(grep -rln '"tradingview"' src/ | grep -vc -e '^src/pocketquant/app/di/' -e '^src/pocketquant/core/config.py' -e '^src/pocketquant/core/infra/tradingview/')" = "0"` exits 0.

---

### Task 9 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist in both `symbols`
and `tracked_symbols` with the right asset class, calendar and contract spec.

**Target files and symbols.**
- New file `scripts/seed_index_futures.py`.
- Collections: `symbols`, `tracked_symbols`.
- Repositories: `SymbolRepository.upsert`, `TrackedSymbolRepository.upsert`.

**Steps.**
1. Follow `scripts/README.md` conventions: environment-only configuration, dry-run by
   default, `--apply` to write.
2. Define the three records inline:
   | symbol | name | multiplier | tick_size | lot_step |
   |---|---|---|---|---|
   | `ES1!:CME_MINI` | E-mini S&P 500 continuous | 50.0 | 0.25 | 1.0 |
   | `NQ1!:CME_MINI` | E-mini Nasdaq-100 continuous | 20.0 | 0.25 | 1.0 |
   | `YM1!:CBOT_MINI` | E-mini Dow continuous | 5.0 | 1.0 | 1.0 |
   All three get `asset_class=AssetClass.INDEX_FUTURE`,
   `calendar_id="CME_GLOBEX_EQUITY"`, `currency="USD"`.
3. Use `SymbolRepository.upsert` (the full `$set` form) — this is the deliberate
   metadata write, unlike the sync path which now uses `touch`.
4. Use `TrackedSymbolRepository.upsert` with `seeded_from="script"`.
5. Print each symbol and its resulting `asset_class`/`calendar_id`.
6. Add a line for the script to `scripts/README.md`.

**Success criteria.** All three symbols validate through the widened regexes and are
persisted with `asset_class=index_future`.

**Verify.** `uv run python -c "
from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_RE, COMPOSITE_SYMBOL_PATTERN
syms = ['ES1!:CME_MINI','NQ1!:CME_MINI','YM1!:CBOT_MINI']
print(all(COMPOSITE_SYMBOL_RE.match(s) and COMPOSITE_SYMBOL_PATTERN.match(s) for s in syms))"` prints `True`.

---

### Task 10 — Initial backfill to the configured cap

**Goal.** Each futures symbol has history at every timeframe up to the bar cap, and
the cron accumulates from there.

**Target files and symbols.**
- Endpoint `POST /api/v1/market-data/tracked-symbols/{symbol}/backfill`
  (`src/pocketquant/app/routes/tracked_symbols.py:82-108`).
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py` —
  `BackfillTrackedSymbolCommand.resolved_mode` (lines 77-80).

**Steps.**
1. In `resolved_mode`, return `"direct"` for `DAY_1` when the symbol's calendar is not
   the 24/7 one. The simplest correct place is the service: in
   `TrackedSymbolBackfillService.run`, after resolving the calendar, override
   `mode = "direct"` when `cmd.interval is Interval.DAY_1 and calendar.calendar_id != CALENDAR_CRYPTO_24_7`.
   Add a comment: cascading a futures daily bar across UTC midnight produces a bar
   that never matches the vendor chart.
2. Run the backfill for each of the three symbols at 1m, 5m, 15m, 1h, 4h, 1d, 1w with
   `n` equal to `tradingview_max_bars`. The route caps `n` at 5000
   (`tracked_symbols.py:90`), which matches the default cap.
3. Record the resulting bar counts per symbol and interval.

**Success criteria.** `bars` count for `ES1!:CME_MINI` at 1m equals
`min(tradingview_max_bars, available)`, and 1d bars open at 17:00 America/Chicago.

**Verify.** `curl -s "http://localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1d?limit=3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['count'], [b['datetime'] for b in d['data']])"` prints a count of `3` and three datetimes ending in `22:00:00Z` or `23:00:00Z`.

---

### Task 11 — End-to-end futures sync test

**Goal.** One automated test drives a futures symbol through the whole pipeline with a
stubbed provider.

**Target files and symbols.**
- New file `tests/app_test/integration/test_futures_sync_end_to_end.py`.

**Steps.**
1. Build the app through `tests/app_test/integration/app_factory.py` against the
   testcontainer Mongo and Redis.
2. Seed `ES1!:CME_MINI` directly through `SymbolRepository.upsert` and
   `TrackedSymbolRepository.upsert` with the CME calendar and the ES spec.
3. Register a stub `IDataProviderPort` in the container that returns session-aligned
   1h bars for a known CME session (for example 2026-06-10, whose session opens at
   `session_open(date(2026,6,10))`).
4. Run `SyncService.sync_one` for 1h and assert: zero bars are dropped as misaligned;
   the persisted bars carry `calendar_id="CME_GLOBEX_EQUITY"`; a 1d sync persists a
   bar whose `session_date` equals `2026-06-10`.
5. Run `check_integrity` for 1m over a window containing a weekend and assert
   `missing_count == 0`.
6. Run `emit_no_progress` with a closed instant and assert no WARNING is emitted
   (use `caplog`).

**Success criteria.** 4 tests pass.

**Verify.** `uv run pytest tests/app_test/integration/test_futures_sync_end_to_end.py -q` exits 0 and prints `4 passed`.

---

### Task 12 — Phase gate: one live week

**Goal.** Prove G1 and the quiet-weekend property on real data.

**Target files and symbols.** None (verification only).

**Steps.**
1. Deploy and let the cron run for one full week including a weekend.
2. Query the logs for `misaligned_bars_dropped`, `integrity.issues_found`,
   `no_progress`, `stuck_threshold_crossed` and `partial_aggregate` scoped to
   `ES1!:CME_MINI`. The count must be zero for each.
3. Point `sync_verify_cascade` at `ES1!:CME_MINI` for 24 consecutive runs and confirm
   `divergent_fraction = 0.0`.
4. During a live session, confirm G1.
5. Record all numbers in the phase completion note.

**Success criteria.** Zero anomaly events, zero cascade divergence, G1 met.

**Verify.** `curl -s "http://localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1m?limit=1" | python3 -c "
import sys, json, datetime as d
b = json.load(sys.stdin)['data'][0]
age = (d.datetime.now(d.UTC) - d.datetime.fromisoformat(b['datetime'].replace('Z','+00:00'))).total_seconds()
print('FRESH' if age <= 720 else f'STALE {age}')"` prints `FRESH` while a CME session is open.

## Todo

- [ ] Task 1 — Add the scraper dependency and TradingView settings
- [ ] Task 2 — Internal TradingView client interface
- [ ] Task 3 — `TvDatafeedClient`
- [ ] Task 4 — TradingView mappers
- [ ] Task 5 — Offline mapper tests with a host-zone matrix
- [ ] Task 6 — `TradingViewAdapter` (the history port)
- [ ] Task 7 — Adapter tests against a fake client
- [ ] Task 8 — Register TradingView in DI
- [ ] Task 9 — Seed the three futures symbols
- [ ] Task 10 — Initial backfill to the configured cap
- [ ] Task 11 — End-to-end futures sync test
- [ ] Task 12 — Phase gate: one live week

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The scraper's login breaks (open issues Dec 2025, Mar 2026) | High over time | Medium | Task 3 degrades to anonymous mode with a WARNING and never crashes; `ITradingViewClient` makes a replacement one class |
| `tvDatafeed.Interval` member names differ from the assumed map | Medium | High — every fetch raises | Task 4 step 5 and its Verify assert against the installed package |
| The DataFrame index is tz-aware on some library version | Low | Medium | Task 3 step 5 branches on `tzinfo` |
| The git dependency breaks the Docker build (no `git` in the runtime stage) | Medium | High — image fails to build | `git` IS installed in the builder stage (`deploy/Dockerfile:9-11`) and `uv sync` runs there; the runtime stage only copies `.venv`. Verify the image builds before deploying. |
| TradingView rate-limits or bans the account | Medium | Medium | `tradingview_poll_seconds` defaults to 60; history fetches are once per cron tick |

**Rollback.** Remove the `"tradingview"` entry from the DI `providers` dict (Task 8) —
the three futures symbols then get an empty provider list and sync becomes a no-op,
while crypto is untouched. Deleting the seeded symbols is a `tracked_symbols` delete
through the admin route.

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

