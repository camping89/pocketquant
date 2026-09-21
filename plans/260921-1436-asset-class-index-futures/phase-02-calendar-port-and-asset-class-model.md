---
phase: 2
title: "Trading Calendar Port and Asset-Class Domain Model"
status: pending
priority: P1
effort: "2d"
dependencies: [1]
---

## Context

(Advice Phase 1.) This phase introduces the vocabulary the rest of the plan depends
on: an `AssetClass` enum, a `ContractSpec` value object, and an `ITradingCalendarPort`
with two implementations — `Continuous24x7Calendar` (crypto, reproduces today's
numbers exactly) and a CME Globex equity calendar wrapping `pandas_market_calendars`.
Nothing is wired into the pipeline yet; that is Phase 3. The symbol record gains
`asset_class`, `calendar_id` and `contract_spec`, and the composite regex is widened
to accept `!`.

The trading schedule is stored alongside the asset class as a `calendar_id`
REFERENCE on the symbol record. The schedule RULES stay in code behind the port,
because CME holidays and early closes change yearly and a Mongo copy would have to be
hand-synchronised with CME notices.

## Tasks

### Task 1 — Add `pandas_market_calendars` as a dependency

**Goal.** The CME calendar library is installed and locked.

**Target files and symbols.**
- `pyproject.toml` — the `[project] dependencies` list (currently ends with `"dishka>=1.9.1",`).

**Steps.**
1. Add `"pandas-market-calendars>=5.4.0",` to the `dependencies` list, in the same
   block as `pandas`.
2. Run `uv sync`.
3. Do NOT add it to `dev` — it is a runtime dependency of `core/infra`.

**Success criteria.** The module imports and exposes the CME Globex equity alias.

**Verify.** `uv run python -c "import pandas_market_calendars as m; c=m.get_calendar('CME Globex Equity'); print(type(c).__name__, c.tz)"` prints `CMEGlobexEquitiesExchangeCalendar America/Chicago`.

---

### Task 2 — Add the `AssetClass` enum

**Goal.** A closed set of asset classes exists in the domain.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py` — add `class AssetClass(str, Enum)`
  below the existing `Interval` enum.

**Steps.**
1. Add:
   ```python
   class AssetClass(str, Enum):
       CRYPTO_SPOT = "crypto_spot"
       CRYPTO_PERP = "crypto_perp"
       INDEX_FUTURE = "index_future"
   ```
2. Leave `Interval.periods_per_year` and `Interval.periods_per_year_for` in place for
   now; Phase 3 Task 9 moves ownership of annualization onto the calendar.

**Success criteria.** The enum imports and has exactly three members.

**Verify.** `uv run python -c "from pocketquant.core.domain.shared.enums import AssetClass; print(len(list(AssetClass)), AssetClass.INDEX_FUTURE.value)"` prints `3 index_future`.

---

### Task 3 — Add the `ContractSpec` value object and the asset-class defaults

**Goal.** Contract units are data, not a hardcoded assumption of `price * quantity`.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/symbol/value_objects.py`.
- Symbols: `ContractSpec`, `LINEAR_SPEC`, `DEFAULT_CALENDAR_BY_ASSET_CLASS`,
  `DEFAULT_SPEC_BY_ASSET_CLASS`, `CALENDAR_CRYPTO_24_7`, `CALENDAR_CME_GLOBEX_EQUITY`.

**Steps.**
1. Create the file with a frozen dataclass:
   ```python
   @dataclass(frozen=True)
   class ContractSpec:
       multiplier: float = 1.0          # account currency per 1.0 of price move, per contract
       tick_size: float = 0.0           # 0.0 = no tick rounding
       lot_step: float | None = None    # None = fractional size allowed; 1.0 = integer contracts
       currency: str = "USD"
       commission_per_contract: float | None = None  # None = use the percentage model
   ```
2. Add `to_mongo()` returning a plain dict of the five fields and a
   `from_mongo(doc: dict | None) -> ContractSpec` classmethod that returns
   `LINEAR_SPEC` when the document is missing or empty.
3. Define the calendar-id constants as module-level strings:
   `CALENDAR_CRYPTO_24_7 = "CRYPTO_24_7"` and
   `CALENDAR_CME_GLOBEX_EQUITY = "CME_GLOBEX_EQUITY"`.
4. Define `LINEAR_SPEC = ContractSpec()`.
5. Define the two default maps keyed by `AssetClass`:
   - `DEFAULT_CALENDAR_BY_ASSET_CLASS`: both crypto members map to
     `CALENDAR_CRYPTO_24_7`; `INDEX_FUTURE` maps to `CALENDAR_CME_GLOBEX_EQUITY`.
   - `DEFAULT_SPEC_BY_ASSET_CLASS`: both crypto members map to `LINEAR_SPEC`;
     `INDEX_FUTURE` maps to `ContractSpec(multiplier=1.0, tick_size=0.25, lot_step=1.0, currency="USD")`
     — the per-symbol multipliers are set at seed time, not here.
6. Export all of the above from `src/pocketquant/core/domain/symbol/__init__.py`.

**Success criteria.** The value object is importable, frozen, and round-trips through
`to_mongo`/`from_mongo`.

**Verify.** `uv run python -c "from pocketquant.core.domain.symbol import ContractSpec; s=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0); print(ContractSpec.from_mongo(s.to_mongo()) == s)"` prints `True`.

---

### Task 4 — Define `ITradingCalendarPort`

**Goal.** One interface that every session-dependent computation takes as a parameter.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/trading_calendar_port.py`.
- Symbol: `ITradingCalendarPort`.

**Steps.**
1. Create an `ABC` named `ITradingCalendarPort` with these members, all abstract
   except `calendar_id` which is an abstract property:
   ```python
   @property
   def calendar_id(self) -> str: ...
   @property
   def tz(self) -> ZoneInfo: ...
   def is_open(self, instant: datetime) -> bool: ...
   def session_date(self, instant: datetime) -> date: ...
   def session_open(self, session_date: date) -> datetime: ...     # UTC instant
   def session_close(self, session_date: date) -> datetime: ...    # UTC instant
   def previous_close(self, instant: datetime) -> datetime: ...    # UTC instant
   def sessions(self, start: datetime, end: datetime) -> list[date]: ...
   def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]: ...
   def bar_start(self, instant: datetime, interval: Interval) -> datetime: ...
   def periods_per_year(self, interval: Interval) -> float: ...
   ```
2. Document in the class docstring: every `datetime` crossing this interface is a
   tz-aware UTC instant; `session_date` is the exchange-calendar day key; session
   boundaries are computed with `zoneinfo` and converted per instant, never with a
   fixed offset.
3. Add to every method docstring the exact contract:
   - `is_open(instant)` — True when `instant` falls inside a trading session.
   - `previous_close(instant)` — the most recent instant at which a bar could have
     closed. For a 24/7 calendar this is `instant` itself.
   - `trading_minutes(start, end)` — every minute-open instant in `[start, end)` that
     is a trading minute, ascending.
   - `bar_start(instant, interval)` — the open instant of the bar of `interval` that
     contains `instant`.
4. This file must not import anything from `pocketquant.core.infra` — the domain
   purity AST test at `tests/core_test/unit/domain/test_domain_purity.py` forbids it.

**Success criteria.** The port imports cleanly and the domain purity test still passes.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_domain_purity.py -q` exits 0.

---

### Task 5 — Implement `Continuous24x7Calendar`

**Goal.** Crypto's schedule is an ordinary calendar implementation, and it reproduces
today's numbers exactly.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/continuous_24x7_calendar.py`.
- Symbol: `Continuous24x7Calendar`.

**Steps.**
1. Implement `ITradingCalendarPort` with `calendar_id` returning
   `CALENDAR_CRYPTO_24_7` and `tz` returning `ZoneInfo("UTC")`.
2. `is_open` returns `True` always.
3. `session_date(instant)` returns `instant.astimezone(UTC).date()`.
4. `session_open(d)` returns `datetime(d.year, d.month, d.day, tzinfo=UTC)`;
   `session_close(d)` returns `session_open(d) + timedelta(days=1)`.
5. `previous_close(instant)` returns `instant` unchanged — this is what keeps
   `now - last_bar` freshness arithmetic byte-identical for crypto.
6. `sessions(start, end)` returns every calendar date in `[start.date(), end.date()]`.
7. `trading_minutes(start, end)` returns the dense grid
   `[start + i*timedelta(minutes=1) for i in range(int((end - start) // timedelta(minutes=1)))]`
   — exactly what `integrity_jobs.check_integrity` builds today.
8. `bar_start(instant, interval)` DELEGATES to the existing
   `pocketquant.core.domain.bar.services.bar_builder_domain_service.get_bar_start`.
   Do not re-implement the logic; this is the DRY guarantee that crypto alignment
   cannot drift.
9. `periods_per_year(interval)` returns the value from the existing
   `_PERIODS_PER_YEAR` map in `core/domain/shared/enums.py`. Import the module-private
   map directly, or expose it via a module-level function in `enums.py` and call that.

**Success criteria.** Every method matches today's behaviour for crypto.

**Verify.** `uv run python -c "
from datetime import UTC, datetime
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
c = Continuous24x7Calendar()
print(c.periods_per_year(Interval.MINUTE_1), c.bar_start(datetime(2026,6,3,14,37,tzinfo=UTC), Interval.WEEK_1).isoformat())"` prints `525600 2026-06-01T00:00:00+00:00`.

---

### Task 6 — Implement the CME Globex equity calendar adapter

**Goal.** ES/NQ/YM session boundaries are correct, including DST, holidays and early
closes, and every boundary is a UTC instant.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/calendars/` with `__init__.py`.
- New file `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`.
- Symbol: `CmeGlobexCalendarAdapter`.

**Steps.**
1. Implement `ITradingCalendarPort`. `calendar_id` returns
   `CALENDAR_CME_GLOBEX_EQUITY`; `tz` returns `ZoneInfo("America/Chicago")`.
2. In `__init__`, hold `self._cal = pandas_market_calendars.get_calendar("CME Globex Equity")`.
3. Implement a private `_schedule(start_date, end_date)` that calls
   `self._cal.schedule(start_date=..., end_date=...)` and returns the resulting
   DataFrame. Wrap it in `functools.lru_cache(maxsize=64)` keyed on the two dates so
   repeated cron calls do not rebuild the schedule.
4. `session_open(d)` returns the `market_open` value for session date `d`, converted
   with `.tz_convert("UTC").to_pydatetime()`. `session_close(d)` does the same with
   `market_close`. Both raise `KeyError` with a clear message when `d` is not a
   trading session.
5. `is_open(instant)` returns True when `instant` lies in
   `[session_open(d), session_close(d))` for the session date derived from `instant`.
   Use `self._cal.open_at_time(schedule, instant)` if it is available; otherwise do
   the interval test yourself against the schedule rows covering
   `instant.date() - 1 day` through `instant.date() + 1 day`.
6. `session_date(instant)` returns the session date `d` whose
   `[session_open(d), session_close(d))` window contains `instant`. When the instant
   falls in the daily maintenance halt, return the session date of the NEXT session
   open — document that choice in the docstring.
7. `previous_close(instant)` returns `min(instant, session_close(d))` for the session
   containing or most recently preceding `instant`.
8. `sessions(start, end)` returns the schedule index dates as `date` objects.
9. `trading_minutes(start, end)` returns, for each session in range, every minute-open
   instant in `[max(start, session_open), min(end, session_close))`.
10. `bar_start(instant, interval)`:
    - `DAY_1` → `session_open(session_date(instant))`.
    - `WEEK_1` → `session_open` of the first session of the ISO week containing
      `session_date(instant)`.
    - intraday → `session_open(d) + k * interval_seconds` where `k` is the largest
      integer keeping the result `<= instant`, clipped to the session. Use
      `INTERVAL_SECONDS` from `core/domain/shared/value_objects.py`.
11. `periods_per_year(interval)` is computed deterministically from a FIXED reference
    window, the calendar year 2025-01-01 to 2025-12-31, and cached with
    `functools.lru_cache`:
    - `DAY_1` → number of sessions in the window.
    - `WEEK_1` → sessions / 5.
    - intraday → total trading minutes in the window / (interval seconds / 60).
    Document that the window is fixed so the value is reproducible across runs.
12. Never construct a session boundary by adding a fixed offset. Always build the
    exchange-local wall time and call `.astimezone(UTC)`, or let the library's
    tz-aware timestamps do it.

**Success criteria.** All port methods return tz-aware UTC instants and the DST cases
below hold.

**Verify.** `uv run python -c "
from datetime import date
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
c = CmeGlobexCalendarAdapter()
print(c.session_open(date(2026,3,9)).isoformat(), c.session_open(date(2026,11,2)).isoformat())"` prints `2026-03-08T22:00:00+00:00 2026-11-01T23:00:00+00:00`.

---

### Task 7 — Calendar test suite including the DST and holiday cases

**Goal.** The six session edge cases the audit named are covered by tests.

**Target files and symbols.**
- New file `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py`.
- New file `tests/core_test/infra/calendars/test_cme_globex_calendar.py`.

**Steps.**
1. In the 24/7 test module, write 6 tests:
   `test_is_open_always_true`, `test_session_date_is_utc_date`,
   `test_bar_start_matches_get_bar_start` (parametrized over all 7 intervals),
   `test_previous_close_is_identity`, `test_trading_minutes_is_dense`,
   `test_periods_per_year_matches_interval_enum` (parametrized over all 7 intervals,
   asserting equality with `Interval.periods_per_year`).
2. In the CME test module, write 8 tests:
   - `test_spring_forward_session_open`: `session_open(date(2026,3,9))` equals
     `datetime(2026,3,8,22,0,tzinfo=UTC)`.
   - `test_fall_back_session_open`: `session_open(date(2026,11,2))` equals
     `datetime(2026,11,1,23,0,tzinfo=UTC)`.
   - `test_sunday_reopen`: `is_open` is False at Sunday 2026-06-07 20:00 UTC and True
     at Sunday 2026-06-07 23:00 UTC (17:00 CT = 22:00 UTC in June — assert against
     `session_open(date(2026,6,8))` rather than a literal so the test states intent).
   - `test_weekend_closed`: `is_open` is False for Saturday 2026-06-06 12:00 UTC.
   - `test_daily_halt_closed`: `is_open` is False 30 minutes after
     `session_close(date(2026,6,10))`.
   - `test_holiday_is_not_a_session`: `date(2026,12,25)` is absent from
     `sessions(datetime(2026,12,20,tzinfo=UTC), datetime(2026,12,31,tzinfo=UTC))`.
   - `test_juneteenth_early_close`: for `date(2026,6,19)`, assert
     `session_close(d) - session_open(d) < timedelta(hours=23)`.
   - `test_session_spans_utc_midnight`: for `date(2026,6,10)`, assert
     `session_open(d).date() != session_close(d).date()`.
3. Every test must construct expectations with `tzinfo=UTC`, never naive.

**Success criteria.** 14 tests pass, and they pass under a non-UTC host zone too.

**Verify.** `TZ=Asia/Ho_Chi_Minh uv run pytest tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py tests/core_test/infra/calendars/test_cme_globex_calendar.py -q` exits 0 and prints `14 passed`.

---

### Task 8 — Build the `TradingCalendarFactory` and the cached symbol lookup

**Goal.** Any caller holding a composite symbol string can obtain that symbol's
calendar without doing a database read per bar.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/repositories/symbol_repository.py` — add
  `find_by_symbol(composite: str) -> Symbol | None`.
- New file `src/pocketquant/core/infra/persistence/symbol_lookup_helper.py` —
  `SymbolLookupHelper`.
- New file `src/pocketquant/core/infra/calendars/trading_calendar_factory.py` —
  `TradingCalendarFactory`.

**Steps.**
1. In `SymbolRepository`, add:
   ```python
   async def find_by_symbol(self, symbol: str) -> Symbol | None:
       doc = await self._collection().find_one({"symbol": symbol.upper()})
       return Symbol.from_mongo(doc) if doc else None
   ```
2. Create `SymbolLookupHelper` holding a `SymbolRepository` and a module-level
   `TTLCache(maxsize=500, ttl=60)` from `cachetools` (already a dependency). Expose
   `async def get(self, composite: str) -> Symbol | None` that checks the cache first,
   reads through on a miss, and caches both hits and misses. Log nothing above DEBUG —
   this is a per-bar hot path.
3. Create `TradingCalendarFactory` holding a `SymbolLookupHelper`. Instantiate one
   `Continuous24x7Calendar` and one `CmeGlobexCalendarAdapter` in `__init__` and store
   them in a `dict[str, ITradingCalendarPort]` keyed by `calendar_id`.
4. Expose `def get(self, calendar_id: str | None) -> ITradingCalendarPort` returning
   the 24/7 calendar when `calendar_id` is None or unknown, and logging one WARNING
   naming the unknown id (one-shot per id, not per call — guard with a `set`).
5. Expose `async def for_symbol(self, composite: str) -> ITradingCalendarPort` that
   looks the symbol up and returns `self.get(symbol.calendar_id if symbol else None)`.
6. Register both in DI as `Scope.APP` in
   `src/pocketquant/app/di/persistence.py` (for `SymbolLookupHelper`) and
   `src/pocketquant/app/di/infrastructure.py` (for `TradingCalendarFactory`). Read
   those files first and follow the existing `provide(...)` style.

**Success criteria.** `TradingCalendarFactory.get("CRYPTO_24_7")` and
`get("CME_GLOBEX_EQUITY")` return the right implementations, and an unknown id falls
back to 24/7.

**Verify.** `uv run pytest tests/app_test/integration/test_app_standalone_runtime.py -q` exits 0 (proves DI still resolves the whole graph).

---

### Task 9 — Extend `Symbol` with `asset_class`, `calendar_id` and `contract_spec`

**Goal.** The asset class and its schedule reference are persisted on the symbol
record, replacing the free-string `asset_type`.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py` — `Symbol` fields (line 38),
  `Symbol.create` (lines 62-70), `to_mongo` (lines 78-87), `from_mongo` (lines 89-99),
  `COMPOSITE_SYMBOL_RE` (line 19), `COMPOSITE_SYMBOL_PATTERN` (line 24).
- `src/pocketquant/engine/market_data/symbols_service.py` — line 20.
- `web/src/types/market-data.ts` — `SymbolInfo.asset_type` (line 26).

**Steps.**
1. Replace the field `asset_type: str | None = None` with three fields:
   ```python
   asset_class: AssetClass = AssetClass.CRYPTO_SPOT
   calendar_id: str = CALENDAR_CRYPTO_24_7
   contract_spec: ContractSpec = LINEAR_SPEC
   ```
   Add `model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)`
   — `ContractSpec` is a frozen dataclass, which pydantic v2 handles natively.
2. Change `Symbol.create` to accept `asset_class`, `calendar_id` and `contract_spec`
   keyword arguments, and drop `asset_type`. `calendar_id` defaults to `None` and,
   when not supplied, is DERIVED from `asset_class` through a module-level
   `_DEFAULT_CALENDAR_FOR: dict[AssetClass, str]` mapping (`CRYPTO_SPOT` and
   `CRYPTO_PERP` to `CALENDAR_CRYPTO_24_7`, `INDEX_FUTURE` to
   `CALENDAR_CME_GLOBEX_EQUITY`). Deriving it means the two fields cannot silently
   disagree; an explicit `calendar_id` still wins, for the case where a venue needs a
   non-default calendar for the same asset class. Add a test asserting that
   `Symbol.create("ES1!:CME_MINI", asset_class=AssetClass.INDEX_FUTURE).calendar_id`
   equals `CALENDAR_CME_GLOBEX_EQUITY` with no `calendar_id` argument passed.
3. Update `to_mongo` to write `asset_class` (the `.value`), `calendar_id`, and
   `contract_spec` (via `self.contract_spec.to_mongo()`); remove the `asset_type` key.
4. Update `from_mongo` to read the three new keys, with
   `AssetClass(doc.get("asset_class", "crypto_spot"))`,
   `doc.get("calendar_id", CALENDAR_CRYPTO_24_7)` and
   `ContractSpec.from_mongo(doc.get("contract_spec"))`.
5. Widen BOTH regexes to accept `!`:
   - `COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9_!-]+:[A-Z0-9_-]+$")`
   - `COMPOSITE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._!-]{1,32}:[A-Z0-9._-]{1,32}$")`
   Both are required: `COMPOSITE_SYMBOL_RE` gates the `Symbol` entity validator,
   while `COMPOSITE_SYMBOL_PATTERN` gates the HTTP path validator
   (`app/common/symbol_validation.py:23`) and the two tracked-symbol command
   validators (`engine/market_data/tracked_symbols_service.py:35` and
   `engine/market_data/tracked_symbols_backfill.py:65`). Missing either one blocks
   the Phase 5 seeding.
   Place `!` before the closing `-` inside the character class so it is not read as a
   range.
6. In `symbols_service.py` line 20, replace `"asset_type": s.asset_type,` with
   `"asset_class": s.asset_class.value,` and add `"calendar_id": s.calendar_id,`.
7. In `web/src/types/market-data.ts`, rename the `SymbolInfo` field `asset_type` to
   `asset_class` and add `calendar_id: string`. Grep the SPA for other `asset_type`
   uses — on 2026-09-21 that type declaration was the only one.

**Success criteria.** `ES1!:CME_MINI` validates through both regexes, and a symbol
round-trips through `to_mongo`/`from_mongo` with its spec intact.

**Verify.** `uv run python -c "
from pocketquant.core.domain.symbol import Symbol, ContractSpec
from pocketquant.core.domain.shared.enums import AssetClass
s = Symbol.create('ES1!:CME_MINI', asset_class=AssetClass.INDEX_FUTURE, calendar_id='CME_GLOBEX_EQUITY', contract_spec=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0))
print(Symbol.from_mongo(s.to_mongo()).contract_spec.multiplier)"` prints `50.0`.

---

### Task 10 — Stop the sync pipeline from clobbering symbol metadata

**Goal.** A normal sync run never overwrites a seeded symbol's `asset_class`,
`calendar_id` or `contract_spec`.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/repositories/symbol_repository.py` —
  `upsert` (lines 15-32); add `touch`.
- `src/pocketquant/engine/market_data/sync_service.py` — `SyncService._persist_bars`
  (lines 149-154), which today calls `self._symbol_repo.upsert(Symbol.create(symbol=symbol))`.

**Steps.**
1. Read `SymbolRepository.upsert`: it sends `{"$set": doc}` with the whole document.
   `Symbol.create(symbol=symbol)` produces DEFAULT `asset_class`/`calendar_id`/
   `contract_spec`, so after this change every 1m sync of `ES1!:CME_MINI` would
   silently reset it to crypto. This must be fixed in this phase, before any futures
   symbol is seeded.
2. Add to `SymbolRepository`:
   ```python
   async def touch(self, symbol: str) -> None:
       """Ensure a symbol document exists without overwriting its metadata.

       The sync pipeline calls this on every run; a full $set would reset
       asset_class / calendar_id / contract_spec to their crypto defaults.
       """
       doc = Symbol.create(symbol=symbol).to_mongo()
       symbol_value = doc.pop("symbol")
       await self._collection().update_one(
           {"symbol": symbol_value},
           {"$setOnInsert": {**doc, "symbol": symbol_value}},
           upsert=True,
       )
   ```
3. In `SyncService._persist_bars`, replace
   `await self._symbol_repo.upsert(Symbol.create(symbol=symbol))` with
   `await self._symbol_repo.touch(symbol)`. Remove the now-unused `Symbol` import if
   nothing else in the module uses it.
4. Leave `upsert` in place — the migration and seeding scripts use it deliberately.

**Success criteria.** After a sync of an existing futures symbol, its `asset_class` in
Mongo is still `index_future`.

**Verify.** `uv run pytest tests/engine_test/market_data/test_sync_service.py tests/core_test/infra/persistence/test_bar_repository.py -q` exits 0.

---

### Task 11 — Add `session_date` and `calendar_id` to daily and weekly bars

**Goal.** Consumers get a stable session-day key while `datetime` keeps moving with DST.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar` fields, `to_mongo`, `from_mongo`.
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` —
  `ensure_indexes` (lines 284-290).

**Steps.**
1. Add to `Bar` two optional fields: `session_date: date | None = None` and
   `calendar_id: str | None = None`. Import `date` from `datetime`.
2. Write both in `to_mongo` and read both in `from_mongo`. `session_date` is stored as
   an ISO string (`"2026-06-10"`), not as a BSON date, so it cannot be mistaken for an
   instant; convert with `date.fromisoformat` on read.
3. In `BarRepository.ensure_indexes`, add a second, sparse index:
   ```python
   await collection.create_index(
       [("symbol", 1), ("interval", 1), ("session_date", 1)],
       name="ix_ohlcv_symbol_interval_session_date",
       sparse=True,
   )
   ```
   Keep the existing unique `(symbol, interval, datetime)` index exactly as it is.
4. Do NOT populate the fields yet — Phase 3 Task 6 populates them at the cascade and
   sync write path. This task only makes the shape available.

**Success criteria.** The new index exists and existing bars still load.

**Verify.** `uv run pytest tests/core_test/infra/persistence/test_bar_repository.py tests/core_test/unit/domain/bar/test_entities_audit_fields.py -q` exits 0.

---

### Task 12 — Migration script: stamp existing symbols

**Goal.** Every symbol already in Mongo carries an explicit asset class, calendar id
and contract spec.

**Target files and symbols.**
- New file `scripts/migrate_symbol_asset_class.py`.
- Collection: `symbols`.

**Steps.**
1. Follow the conventions in `scripts/README.md`: read `MONGODB_URL` from the
   environment, never from a CLI flag; default to dry-run; require `--apply` to write.
2. The script connects with `AsyncMongoClient`, then for every document in `symbols`
   that has no `asset_class` field, issues
   `{"$set": {"asset_class": "crypto_spot", "calendar_id": "CRYPTO_24_7", "contract_spec": {"multiplier": 1.0, "tick_size": 0.0, "lot_step": None, "currency": "USD", "commission_per_contract": None}}, "$unset": {"asset_type": ""}}`.
3. Print the matched and modified counts. Exit non-zero if any write fails.
4. Add a module docstring with the usage line
   `uv run python scripts/migrate_symbol_asset_class.py [--apply]`.
5. Add a one-line entry for the script in `scripts/README.md` under the existing list.

**Success criteria.** A dry run reports the count of documents that would change and
writes nothing.

**Verify.** `uv run python scripts/migrate_symbol_asset_class.py --help` exits 0 and its output contains `--apply`.

---

### Task 13 — Phase gate

**Goal.** Phase 2 is complete and the crypto path is untouched.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, ruff, `pyright src` and the import contracts.
2. Confirm `pandas_market_calendars` is imported only from
   `src/pocketquant/core/infra/calendars/` — grep for it across `src/`.

**Success criteria.** All checks pass and the library is confined to `core/infra`.

**Containment is enforced by a contract, not by a grep.** Add a ninth
import-linter contract to `pyproject.toml` (the file currently holds exactly 8,
and `include_external_packages = true` is already set, so an external forbidden
module works). Append, matching the existing contract style:

```toml
[[tool.importlinter.contracts]]
name = "pandas_market_calendars confined to core.infra"
type = "forbidden"
source_modules = [
    "pocketquant.app",
    "pocketquant.engine",
    "pocketquant.backtest",
    "pocketquant.core.domain",
]
forbidden_modules = ["pandas_market_calendars"]
```

Listing `core.domain` but not `core.infra` is what permits the CME adapter while
forbidding the library everywhere else. Update the contract count in `CLAUDE.md`
("import-linter enforced, 8 contracts") to 9 in Phase 7's docs task.

**Verify.** `uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run lint-imports` exits 0, and `uv run lint-imports` prints `Contracts: 9 kept, 0 broken`.

## Todo

- [ ] Task 1 — Add `pandas_market_calendars` as a dependency
- [ ] Task 2 — Add the `AssetClass` enum
- [ ] Task 3 — Add the `ContractSpec` value object and the asset-class defaults
- [ ] Task 4 — Define `ITradingCalendarPort`
- [ ] Task 5 — Implement `Continuous24x7Calendar`
- [ ] Task 6 — Implement the CME Globex equity calendar adapter
- [ ] Task 7 — Calendar test suite including the DST and holiday cases
- [ ] Task 8 — Build the `TradingCalendarFactory` and the cached symbol lookup
- [ ] Task 9 — Extend `Symbol` with `asset_class`, `calendar_id` and `contract_spec`
- [ ] Task 10 — Stop the sync pipeline from clobbering symbol metadata
- [ ] Task 11 — Add `session_date` and `calendar_id` to daily and weekly bars
- [ ] Task 12 — Migration script: stamp existing symbols
- [ ] Task 13 — Phase gate

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `pandas_market_calendars` session semantics differ from ES/NQ/YM reality | Medium | High — every futures bar mis-bucketed | Task 7's 8 CME tests assert concrete instants; the Phase 5 gate cross-checks against `sync_verify_cascade` |
| Only `COMPOSITE_SYMBOL_RE` widened, `COMPOSITE_SYMBOL_PATTERN` forgotten | Medium | High — Phase 5 seeding fails with HTTP 400 | Task 9 step 5 names all four call sites |
| `SyncService` clobbers seeded metadata | High if unfixed | High — futures symbols silently revert to crypto | Task 10 replaces `upsert` with `touch` before any futures symbol exists |
| `ContractSpec` as a frozen dataclass inside a pydantic model | Low | Medium | Task 3's Verify round-trips it |

**Rollback.** Tasks 1-8 add new modules only and can be dropped wholesale. Task 9 is
the only schema-shaping change; reverting it requires re-adding `asset_type` and
re-running the migration in reverse (`$rename` `asset_class` back). Task 11's index is
additive and can be dropped with `db.bars.dropIndex("ix_ohlcv_symbol_interval_session_date")`.

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

