# Code Standards

Các quy tắc dưới đây là rules of thumb, không phải mandate: áp dụng khi chúng làm code dễ đọc hơn, bỏ qua khi chúng làm code tệ đi. Lệnh chạy và test nằm ở [README](../../README.md); thiết kế tổng thể nằm ở [system-architecture.md](./system-architecture.md).

## Principles

- **KISS:** chọn lời giải đơn giản nhất còn đúng. Không thêm layer, interface hay config cho nhu cầu chưa có.
- **DRY:** một khái niệm có một chỗ định nghĩa. Lặp lại hai lần là chấp nhận được; lần thứ ba thì gom lại.
- **Cân bằng:** không có god-function ôm cả luồng, cũng không có micro-helper chỉ bọc một lời gọi. Một hàm làm một việc có tên rõ ràng.
- **Dependency direction cố định:** `core ◁ engine ◁ app`. `core.domain` không import `core.infra` và không làm I/O (không pymongo, redis hay aiohttp; Pydantic được phép). Chỉ `app` import `fastapi`. import-linter enforce các luật này (xem [Quality Gate](#quality-gate)); `tests/core_test/unit/domain/test_domain_purity.py` kiểm tra thêm domain purity.
- **Backtest và live là hai driver trên một engine:** `engine.backtest` và `engine.live` không import lẫn nhau, và phần máy dùng chung (`engine.strategy`, `engine.execution`, `engine.market_data`) không import driver nào.

## When to Extract a Helper

- Extract khi tên của helper thêm ý nghĩa mà code inline không nói được, hoặc khi code đó được dùng lại ở ít nhất hai chỗ.
- Không extract chỉ để hàm ngắn đi. Một hàm 2 dòng chỉ `return self._x.y(...)` là pure delegation: người đọc phải nhảy file mà không học thêm gì. [Metric ratchet](#quality-gate) đếm các hàm này.
- Một flow nên đọc được trong một file khi có thể, và tối đa 3 file (cộng các leaf call như repository hay client).

## File and Function Size

- Khoảng 400 LOC mỗi file là soft guidance, không phải trigger để split. Split khi file chứa hai concern độc lập, không phải khi nó dài.
- Hàm nên giữ ≲ 60 dòng. Hàm dài hơn thường đang làm nhiều việc; tách theo bước có tên, không tách theo số dòng. `scripts/code_metrics.py --json` liệt kê mọi hàm dài hơn 60 dòng.

## Naming

Tên class và tên file mã hoá layer. Domain concept (entity, value object, enum) không có suffix — chúng chính là ngôn ngữ domain.

### File Naming

`snake_case`, đặt theo mục đích của module; suffix mã hoá layer và khớp với class chính bên trong:

```
app/routes/market_data.py            # market-data route functions
quote_app_service.py                 # QuoteAppService (application orchestrator)
bar_builder_domain_service.py        # BarBuilderDomainService (domain logic)
engulfing_strategy_service.py        # EngulfingStrategyService (strategy impl)
strategy_service_interface.py        # IStrategyService (strategy interface)
bar_repository.py                    # BarRepository (data access)
data_provider_port.py                # IDataProviderPort (infra boundary)
binance_adapter.py                   # BinanceAdapter (infra impl)
okx_broker_adapter.py                # OKXBrokerAdapter (source + type → separate adapter)
```

### Class Naming by Layer

| Layer | Pattern | Class Suffix | File | Ví dụ |
|-------|---------|--------|--------|--------|
| Entities | `{Name}` hoặc `{Name}Aggregate` | None / `Aggregate` | `entities.py` | `Bar`, `Symbol`, `OrderAggregate` |
| Events | `{Entity}{PastTense}Event` | `Event` | `events.py` | `OrderFilledEvent`, `BarCompletedEvent` |
| Enums / Value Objects | `{Concept}` | None | `.py` | `Interval`, `OrderSide`, `PnL`, `OHLCV` |
| **Domain Services** | `{Name}DomainService` | `DomainService` | `*_domain_service.py` | `PositionCalculatorDomainService`, `BarBuilderDomainService` |
| **Domain Strategy (Impl)** | `{Name}StrategyService` | `StrategyService` | `*_strategy_service.py` | `EngulfingStrategyService`, `HitNRun2StrategyService` |
| **Domain Strategy (Interface)** | `IStrategyService` | `IStrategyService` | `strategy_service_interface.py` | `IStrategyService` |
| Repositories | `{Entity}Repository` | `Repository` | `*_repository.py` | `BarRepository`, `OrderRepository` |
| **Infra Port (Interface)** | `I{Concept}Port` | `Port` | `*_port.py` (1 port/file) | `IBrokerPort`, `IDataProviderPort`, `IRealtimeQuoteProviderPort` |
| **Infra Adapter (Impl)** | `{Source}[{Type}]Adapter` | `Adapter` | `*_adapter.py` | `OKXBrokerAdapter`, `BinanceAdapter`, `PaperBrokerAdapter` |
| **Helper** | `{Name}Helper` | `Helper` | `*_helper.py` | (chỉ khi module helper thật sự cần) |
| **App Services** | `{Name}AppService` | `AppService` | `*_app_service.py` | `StrategyReconcileAppService`, `BacktestReportAppService` |
| Query / Command Models | `{Get\|List}{Entity}Query`, `{Action}{Entity}Command` | `Query` / `Command` | cạnh service nhận nó | `GetOHLCVQuery`, `SyncSymbolCommand`, `RunBacktestCommand` |
| CQRS Services | `{Domain}{Command\|Query}Service` | `Service` | `*_service.py` | `StrategyCommandService`, `BacktestQueryService` |
| DTOs | `{Name}Response` | `Response` | `.py` | `SyncResponse`, `QuoteResponse` |
| Routes | (functions) | — | `app/routes/{feature}.py` | `async def sync_symbol(...)` |
| Middleware | `{Name}Middleware` | `Middleware` | `*middleware.py` | `RateLimitMiddleware` |
| Errors | `{Name}Error` | `Error` | `.py` | `AppError`, `NotFoundError`, `DomainError` |
| DI Providers | `{Domain}Provider` | `Provider` | `app/di/{domain}.py` | `InfrastructureProvider`, `ServicesProvider` |
| Configs | `{Name}Config` | `Config` | `config.py` / `value_objects.py` | `BacktestConfig`, `RiskConfig` |
| Background Jobs | (functions) | — | `*_jobs.py` | `sync_1m()`, `sync_integrity()` |

### Naming Principles & Exemptions

1. **Tên class + file tự mã hoá layer/role.** Đọc `PositionCalculatorDomainService` hay `binance_adapter.py` là biết layer mà không cần nhìn thư mục.
2. **Không chồng hai doer-suffix chung chung (`-er`/`-or`) trong một tên.** Dùng gerund thay thế (`*TrackingHelper`, không phải `*TrackerHelper`). Danh từ nghiệp vụ tận cùng bằng `-er` (`Broker`) không phải doer-suffix, nên `BrokerAdapter` hợp lệ.
3. **Data class hoặc role đã có suffix chuẩn thì giữ nguyên.** Danh sách miễn trừ (không ép theo convention):

| Nhóm | Ví dụ |
|---|---|
| CQRS | `*CommandService`, `*QueryService` (request-scoped, không phải orchestrator) |
| Persistence | `*Repository` |
| DI / cross-cutting | `*Provider`, `*Middleware` |
| App handler | `RiskCheckHandler`, `event_handler` (decorator) |
| Infra factory/scheduler | `BrokerFactory`, `JobScheduler` |
| Infra sub-component (OKX) | `OkxMessageParser`, `OkxOrderMapper`, `OkxPositionMapper`, `OkxReconnectionHandler`, `OkxStateReconciler` |
| Data class | Entity, VO, enum, event, `*Command`/`*Query`/`*Response` |

## Routes & Services

- Route nằm trong `src/pocketquant/app/routes/`, dùng `route_class=DishkaRoute` và inject service bằng `FromDishka[...]`. Không bao giờ dùng `Depends()` cho service.
- Route mỏng: parse request, gọi một method của service, trả kết quả. Logic nghiệp vụ nằm trong service.
- Service method nhận scalar. Pydantic model chỉ được truyền khi nó là request body thật (`SyncSymbolCommand`, `AddTrackedSymbolCommand`, `RunBacktestCommand`) hoặc parameter object nhiều field tự mang validation (`GetOHLCVQuery`, `BackfillTrackedSymbolCommand`). Không bọc scalar của path hay query vào model.
- Không try/except trong route hay service để đổi exception thành response. Exception propagate tới global handler đăng ký bởi `register_exception_handlers` (`core/common/exceptions.py`, wire trong `app/main_extensions.py`): `NotFoundError` → 404, `DomainError` → 400, `AppError` → 500, body `{error: {code, message}}`. Chỉ catch exception cụ thể ở nơi code thật sự phục hồi (một job, một lần retry của adapter); không bao giờ `except:` trần.
- Thay đổi state thì publish domain event. Handler là method đánh dấu `@event_handler(...)` và được đăng ký bằng `registry.register_instance(service, event_bus)`.
- Datetime trả cho frontend luôn qua `to_utc_iso()` (`pocketquant.core.common.time`) để có hậu tố `Z` đúng. `.isoformat()` trần chỉ dùng nội bộ (log, cache key).

```python
@router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    return await cmd_svc.add_symbol(strategy_code, body.symbol, body.interval)
```

## Dependency Injection

- `src/pocketquant/app/di/` có đúng ba provider: `InfrastructureProvider` (Settings, EventBus, Database, Cache, repositories, calendars, scheduler, health), `AdaptersProvider` (routing data adapter và quote adapter, `BrokerFactory`) và `ServicesProvider` (app services, execution engine, các service mà route inject).
- `create_container(settings)` đưa `Settings` vào qua `from_context` và build với `STRICT_VALIDATION`: một type đăng ký hai lần sẽ lỗi lúc startup thay vì lần đăng ký sau âm thầm thắng. Mỗi type có đúng một provider.
- Mọi dependency đi vào qua constructor. Service cần cleanup dùng generator factory: mọi setup trước `yield`, cleanup trong `try/finally` (xem [Async](#async-suspension-points--await-is-preemption), pattern 5).

## Domain & Repositories

- Entity là Pydantic `BaseModel` tự serialize bằng `to_mongo()` / `@classmethod from_mongo()`. Không có thư mục schemas và không có subclass `Create`; factory là classmethod (`Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`). Value object và event là frozen dataclass.
- Aggregate phải xứng đáng với độ phức tạp của nó: chỉ dùng khi entity bảo vệ invariant, có lifecycle behaviour, sở hữu entity khác hoặc phát event. Một data record (`Bar`) hay model chỉ CRUD thì là entity thường.
- Strategy implement `IStrategyService` (`on_bar_completed` bắt buộc; `on_quote_received` và `on_order_filled` tuỳ chọn) và trả `Signal | None`. Chúng giữ thuần — không broker, không database; `StrategyAppService` thực thi signal.
- Mọi repository nằm trong `core.infra.persistence.repositories`; `engine` và `app` không có repository nào. Repository là instance class kế thừa `BaseRepository`, nhận `Database` qua constructor và dùng `_collection(name)`.

**Primary key: chỉ UUIDv7.** Mọi document mà code của chúng ta ghi đều có `_id` là UUIDv7 sinh bằng `generate_id()` (`core/common/uuid.py`); entity được persist khai báo `id: UUID`. Không hash key, không natural key, không Mongo ObjectId, không composite-string key. Uniqueness và idempotency đặt trên secondary unique index, không bao giờ trên `_id`. Ngoại lệ duy nhất là collection có `_id` do thư viện bên thứ ba ghi (`apscheduler_jobs` của APScheduler); không patch thư viện để ép uuid7.

```python
# ❌ hash / natural / objectid as primary key
_id = hashlib.sha256(f"{a}|{b}|{c}".encode()).hexdigest()[:16]
_id = symbol                       # composite string as id
id: str                            # persisted entity declaring str id
# (and: letting Mongo assign a default ObjectId)

# ✅ correct — every persisted entity
from pocketquant.core.common.uuid import UUID, generate_id
id: UUID = Field(default_factory=generate_id)
def to_mongo(self) -> dict: return {"_id": str(self.id), ...}
# uniqueness/idempotency → separate unique index, e.g.
await collection.create_index([("strategy_code", 1), ("symbol", 1), ("interval", 1)], unique=True)
```

## Composite Symbol Format

**Format:** `{CODE}:{PROVIDER}` (vd `BTCUSDT:BINANCE`, `ES1!:TRADINGVIEW`, `XAUUSD:EXNESS`)

- Một field bất biến `symbol: str` thay cho cặp `(code, exchange)` trên mọi entity: Bar, Order, Position, Symbol, SyncStatus, Subscription, TrackedSymbol.
- Suffix là id của data provider sinh ra bar của symbol, viết đầy đủ dạng `provider_id.upper()` — `BINANCE`, `TRADINGVIEW`, không bao giờ là mã rút gọn và không bao giờ là sàn. Routing đọc nó ở đúng một chỗ, `provider_id_for()` trong `core/domain/market_data/provider_routing_domain_service.py`; mọi chỗ khác coi `symbol` là mờ.
- Suffix không trỏ tới provider nào đã đăng ký thì fail rõ ràng (`UnknownDataProviderError`, một `ValueError`) — không bao giờ đoán hay route theo asset class.
- Symbol chưa seed nhận default của provider (`DATA_PROVIDER_DEFAULTS`: `asset_class` + `calendar_id`).
- Execution broker (paper, OKX, Exness) là setting của strategy (`StrategyConfig.broker`), không thuộc symbol. Tên instrument riêng của broker là việc của broker adapter: nó map từ composite symbol đầy đủ trong bảng riêng (`TRADINGVIEW_EXCHANGE_BY_CODE` trong `tradingview_mappers.py`; OKX ghép `instId` trong `okx_mapper.py`; Exness map trong `EXNESS_INSTRUMENTS` ở `exness_mappers.py`).
- Validation: `COMPOSITE_SYMBOL_RE` cho dữ liệu nội bộ, `COMPOSITE_SYMBOL_PATTERN` cho input HTTP (`core/domain/symbol/entities.py`).
- URL: `:` được encode thành `%3A` trong path segment (`/api/v1/bar/BTCUSDT%3ABINANCE`). JSON và database giữ nguyên `:`. Cache key dùng symbol nguyên vẹn: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`.

**Thêm một data provider** chạm đúng các chỗ sau:

1. Một adapter package `src/pocketquant/core/infra/<provider>/` hiện thực `IDataProviderPort` và, tùy chọn, `IRealtimeQuoteProviderPort`.
2. Các field `Settings` trong `src/pocketquant/core/config.py`.
3. Một entry `DATA_PROVIDER_DEFAULTS` (`core/domain/market_data/provider_routing_domain_service.py`) và một entry trong mỗi router ở `app/di/adapters.py` (`get_data_provider`, `get_realtime_quote_provider`); `tests/app_test/unit/test_data_provider_registration.py` bắt buộc ba chỗ này khớp nhau.
4. Một calendar đăng ký trong `TradingCalendarFactory` (`core/infra/calendars/trading_calendar_factory.py`) khi không có calendar nào sẵn có phù hợp, dựng từ các session đã ghi lại.
5. Một `ContractSpec` cho mỗi symbol, ghi bởi một seed script theo mẫu `scripts/seed_index_futures.py` (`symbols` và `tracked_symbols`).
6. Provider trong provider map của `/health` (`register_health_checks`, `app/main_extensions.py`).
7. Mọi collection hoặc Redis key mới có khóa theo symbol phải tham gia cascade xóa symbol (`TrackedSymbolsService`).
8. Broker là tùy chọn và tách riêng: một nhánh `BrokerFactory`, với bảng instrument riêng của broker có khóa là composite symbol đầy đủ.
9. Các dòng env trong `docs/deployment.md`, và adapter test dưới `tests/core_test/infra/<provider>/` chạy trên recorded fixture.

## Strategy IDs

Ba id không bao giờ được nhầm lẫn:

| ID | Ý nghĩa | Ví dụ |
|---|---|---|
| `strategy_code` | Tên template đăng ký trong `STRATEGY_REGISTRY`; chọn strategy class | `"hitnrun2"` |
| `subscription_id` | uuid7 của một binding `(strategy_code, symbol, interval)`; là key của instance in-memory, order, position và backtest doc | `"019ebe98-…"` |
| `template_id` | **Deprecated**, tên cũ của `strategy_code`; coi mọi tham chiếu là `strategy_code` | — |

Chốt chặn trùng lặp duy nhất cho subscription là unique compound index `ix_subscriptions_dedup_triple` trên `(strategy_code, symbol, interval)`. Index phân biệt hoa thường, nên `add_symbol` upper-case `symbol` trước khi lưu — bước chuẩn hoá đó là load-bearing (`tests/core_test/infra/persistence/test_subscription_repository.py::test_concurrent_add_same_triple_one_doc_one_error`).

## Async Suspension Points — "Await Is Preemption"

**Quy tắc một dòng:** mỗi `await` là một preemption point. Event loop có thể resume bất kỳ coroutine sẵn sàng nào tại đó, nên state mà coroutine khác đọc phải hợp lệ **trước** suspension point cho phép nó chạy.

| Construct | Suspension? | Ghi chú |
|---|---|---|
| `await coro()` | Có | Trường hợp hiển nhiên. |
| `await asyncio.sleep(0)` | Có | Yield tường minh, kể cả với 0. |
| `yield x` trong `async def` | **Có** | Dễ bỏ sót. Async generator và `@asynccontextmanager` dùng nó. |
| `async for x in iterable` | Có | Mỗi vòng gọi `await iterable.__anext__()`. |
| `async with cm:` | Có (vào và ra) | Gọi `await cm.__aenter__()` và `__aexit__()`. |
| `await asyncio.gather(...)` | Có | Các coroutine con xen kẽ nhau tại mỗi `await` của chúng. |
| `await container.get(X)` | Có nếu provider làm I/O | Factory `AsyncIterator` của Dishka giấu `await`. |
| Gán biến, `if`, số học | Không | Đồng bộ giữa hai `await`; dùng cho vùng atomic. |

**1. Publish-before-subscribe** — wire dependency TRƯỚC lời gọi khởi động worker (scheduler, queue consumer, websocket reader, background task). Khi lời gọi đó trả về, worker có thể dispatch ở `await` kế tiếp. `app/main.py` gọi `set_sync_container(container)` trước `await` đầu tiên vì lý do này: APScheduler lưu `next_run_time` qua các lần restart, nên một job đến hạn trong `misfire_grace_time` có thể dispatch trong một `container.get(...)` sớm và gặp module global chưa được set.

```python
# Anti-pattern (racy)
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),  # scheduler may start here
)
# the container global is set inside register_sync_jobs — too late

# Fix
set_sync_container(container)   # synchronous, wired FIRST
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),
)
```

**2. Initialize-before-first-await** — không bao giờ để lộ object dở dang cho task khác. Làm hết I/O, dựng object một lần, rồi mới publish.

**3. TOCTOU qua `await`** — một check trước `await` có thể đã cũ sau nó. Đẩy invariant xuống storage (`await db.try_debit(...)` với `WHERE balance >= amount`), giữ `asyncio.Lock` theo key qua `await`, hoặc đọc lại sau nó.

**4. Atomic block không có `await`** — giữa cặp đọc và ghi shared state không có suspension. `counters[key] += 1` là atomic giữa hai `await` trong CPython, không bao giờ atomic qua một `await`.

**5. `yield` trong `@asynccontextmanager` / factory `AsyncIterator` LÀ suspension point.** Mọi setup trước `yield`, cleanup trong `try/finally` sau nó.

```python
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    await svc.connect()          # all setup BEFORE yield
    try:
        yield svc
    finally:
        await svc.aclose()       # cleanup in finally — survives cancellation
```

**6. Cancellation rơi vào bất kỳ `await` nào.** Sau `task.cancel()`, `asyncio.CancelledError` có thể nổ ở `await` kế tiếp. Cặp ghi đi đôi phải nằm trong transaction, hoặc trong `try/finally` với hành động bù trừ.

**Symmetry check:** khi hai subsystem kề nhau wiring giống nhau (vd `init_backtest_tasks` và `register_sync_jobs`), so sánh thứ tự startup của chúng. Thứ tự lệch nhau gần như luôn là bug.

**Checklist trước mỗi `await`:**
- Lời gọi này có publish handle, đăng ký callback hay khởi động worker không? Nếu có, object đã khởi tạo xong chưa?
- Invariant nào đang ở trạng thái trung gian?
- Giá trị vừa đọc có thể bị coroutine khác sửa trước dòng kế tiếp dùng nó không?
- Nếu `CancelledError` rơi vào đây, cleanup có chạy không? Có cần `try/finally` hay `asyncio.shield` không?
- `async for` / `async with` / `gather` này có giấu thêm suspension point không?

## Comment Policy — Explain WHY, Not WHAT

Comment tốn LOC và rơi khỏi đồng bộ với code. Mặc định: không comment. Chỉ thêm khi code không thể tự nói lên chính nó. Áp dụng cho cả Python (`#`, `"""`) lẫn TS/JS (`//`, `/** */`).

### REMOVE / never write

- Comment lặp lại dòng code (`# increment counter`, `# validate creds` trên validation hiển nhiên)
- Banner / divider / count label (`# Trading (4)`, `# ---- setup ----`, `# Market data (16)`)
- Docstring lặp lại tên symbol (`"""Get bar."""` trên `get_bar`)
- Filler Arrange/Act/Assert marker vô nghĩa
- Ref plan/phase/finding — giải thích invariant, không phải nguồn gốc

### KEEP / write only for

- **WHY:** race, ràng buộc ordering/suspension, publish-before-subscribe, ghi chú await-preemption, invariant, trade-off
- **Hack / workaround** + quirk hệ ngoài (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` / `// @ts-expect-error` / `// eslint-disable` — luôn kèm lý do
- Cảnh báo về failure mode không hiển nhiên (`# benign — already dropped`)
- Docstring ghi lại params / contract / edge case / return semantics không hiển nhiên
- Test comment giải thích ý đồ scenario hoặc setup không hiển nhiên

### Examples

```python
# KEEP — load-bearing ordering note (see "Await Is Preemption")
# Wire the event bus before any handler can publish: container.get() awaits,
# so a subscriber resolved first would miss publish-before-subscribe events.

# REMOVE — restates the call
# Get the bar from the repository
bar = await repo.get(bar_id)
```

**Route docstrings:** docstring lặp tên trên FastAPI route bị gỡ dù OpenAPI summary có thể trống — chỉ docstring mang nội dung param/contract/edge-case mới được giữ.

**Docstrings:** Tối thiểu. Để type hint gánh phần nặng. Module-level: chỉ nêu mục đích ngắn khi không hiển nhiên.

## Testing

- Test bám theo package: `tests/core_test/`, `tests/engine_test/`, `tests/backtest_test/`, `tests/app_test/`, và `tests/scripts/` cho `scripts/`.
- Trước khi đổi cấu trúc một flow, pin hành vi hiện tại bằng test; refactor mà làm đổi kết quả test đó nghĩa là hành vi đã đổi.
- Integration test cần MongoDB hoặc Redis thật dùng `testcontainers` (`tests/app_test/conftest.py`), nên Docker phải đang chạy. Không mock database khi hành vi cần kiểm tra là query hay index.
- Không gì được phụ thuộc timezone của host: CI chạy suite dưới `UTC`, `Asia/Ho_Chi_Minh` và `America/Chicago`, và `just test-tz` làm điều tương tự ở local.
- Dùng pytest fixture và `monkeypatch` để mock. Cover service method, repository method và error path; không có coverage gate (`pytest --cov=src` có sẵn).

## Performance

- Không blocking I/O trên event loop. Dùng client async native; nếu buộc phải dùng thư viện sync, cô lập nó bằng `await loop.run_in_executor(...)`.
- Ghi theo lô (`BarRepository.insert_many`), không ghi từng bản trong vòng lặp.
- Invalidate cache theo pattern (`Cache.delete_pattern("bar:...:*")`), không đoán từng key.
- Bảo vệ shared in-memory state (ví dụ các bar builder) bằng `asyncio.Lock`.
- Type hint đầy đủ cho public function và class attribute; Pyright kiểm tra chúng.

## Quality Gate

Một thay đổi chỉ xong khi tất cả các check dưới đây pass. Ruff và Pyright phải báo 0 lỗi trong `src/` và trong mọi file bạn sửa; các file test cũ vẫn còn lint debt, nên `ruff check .` toàn repo chưa sạch.

| Check | Lệnh |
|---|---|
| Tests | `just test` |
| Lint | `uv run ruff check src <touched files>`; format file đã sửa bằng `uv run ruff format` |
| Type check | `uv run pyright src <touched files>` (cấu hình từ `pyrightconfig.json`) |
| Import contracts | `uv run lint-imports` → `Contracts: 8 kept, 0 broken.` |
| Metric ratchet | `uv run python scripts/code_metrics.py --ratchet` |

- CI job `tests` trong `.github/workflows/cicd.yml` chạy `lint-imports`, metric ratchet và `pytest` ở mỗi timezone leg. Ruff và Pyright không phải CI step; chạy chúng ở local.
- **Import contracts** (`[tool.importlinter]` trong `pyproject.toml`): layer `app → engine → core`, domain không phụ thuộc infra, hai driver backtest/live độc lập, phần máy dùng chung của engine không import driver, `fastapi` chỉ trong `app`, không `bson`, `pandas_market_calendars` chỉ trong `core.infra.calendars`, và `tvDatafeed` chỉ trong `core.infra.tradingview`.
- **Metric ratchet:** `scripts/code_metrics.py` đo `tiny_share` (tỉ lệ hàm có thân ≤ 2 statement) và `delegations` (hàm chỉ gồm một `return` hoặc expression gọi một attribute) trên `src/pocketquant`; định nghĩa chính xác nằm trong docstring của script. `--ratchet` so chúng với `max_tiny_share` và `max_delegations` trong `[tool.code-metrics]` của `pyproject.toml` và exit 1 khi metric nào vượt ceiling.
- Ceiling chỉ đi xuống. Hạ nó khi một thay đổi cải thiện metric; nâng nó là quyết định của user, không bao giờ là cách để làm CI xanh. Khi ratchet chặn một thay đổi, sửa bằng cách tái cấu trúc (ví dụ inline một wrapper mỏng) — không inline code chỉ để đẩy con số.
- Tiny share ≤ 30% và ≤ 20 delegations là aspiration, không phải gate.

## Configuration & Secrets

Không bao giờ hardcode. Dùng `.env` (local) và biến môi trường (prod). Không bao giờ commit `.env` hay secret. Định nghĩa trong `src/pocketquant/core/config.py::Settings` bằng Pydantic.

- Các key `EXNESS_*` chỉ nằm trong `pocketquant-config`. `EXNESS_SECRET_KEY` là secret key 128-hex trên một dòng; mọi giá trị `.env` là `KEY=VALUE` một dòng. Secret không bao giờ được log, và `EXNESS_LIVE_TRADING` giữ false ngoài một go-live plan.
