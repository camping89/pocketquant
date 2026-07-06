# Code Standards & Patterns

Kiến trúc: Clean Architecture + DDD + Dishka. Type checker: Pyright.

Tài liệu này tập trung vào các pattern và quy ước kiến trúc. Về các lệnh khởi động và lệnh test hiện hành, xem [README](../../README.md).

## Clean Architecture Rules

### Dependency Direction (MANDATORY)
```
Features (routes, commands, queries, handlers)
  ↓ imports
Application (orchestrators: StrategyAppService, BacktestAppService, etc.)
  ↓ imports
Domain (aggregates, value objects, events)
  ↑ imports ← Adapters (brokers, providers, persistence in core.*)

CRITICAL: No reverse dependencies.
- Domain NEVER imports from Application, Features, or Adapters
- Enforced via test_domain_purity.py (AST check)
```

### Layer Responsibilities

| Layer | Trách nhiệm | I/O |
|-------|---|---|
| **Domain** | Business rules, validation, events | NONE (zero I/O) |
| **Services** | Orchestrators, command/query services, điều phối | Gọi adapters |
| **Routes** | Định tuyến HTTP, parse request, format response | Gọi services |
| **Adapters** | DB, brokers, providers, scheduling, HTTP | Toàn bộ I/O ngoài |
| **Common** | EventBus, middleware, tiện ích | Cross-cutting concerns |

## Architecture Patterns

### 0. Route Layer Rules

Routes là handler HTTP mỏng. Toàn bộ business logic nằm trong services.

| Component | Location | Trách nhiệm |
|-----------|----------|---|
| **Route** | `src/pocketquant/app/routes/{feature}.py` | Parse request → build Command/Query → gọi service → trả DTO |
| **Command Service** | `src/pocketquant/{pkg}/{feature}_command_service.py` | Thay đổi state: validate, persist, publish events |
| **Query Service** | `src/pocketquant/{pkg}/{feature}_query_service.py` | Chỉ đọc: fetch, serialize, trả DTO |

**Route signature pattern:**
```python
from dishka.integrations.fastapi import FromDishka, DishkaRoute

@router.post("/path", status_code=201, route_class=DishkaRoute)
async def endpoint_name(
    body: RequestBody,
    cmd_svc: FromDishka[SomeCommandService],
) -> dict:
    return await cmd_svc.method(SomeCommand(...))
```

**Quy tắc chính:**
- Không bao giờ try/catch trong routes hay services (exception propagate → global handler)
- Dùng `FromDishka[ServiceType]`, không bao giờ dùng `Depends()`
- Pydantic tự động validate input
- Trả status code tường minh: `201` (created), `204` (no content), `404` (not found)

### 1. Route + Service Layer Architecture

Routes là lớp HTTP mỏng. Services cung cấp business logic qua pattern 5 bước: Fetch → Validate → Persist → Invalidate Cache → Publish Events.

**Cấu trúc:**
```
routes/{feature}.py                    # HTTP handlers
{pkg}/{feature}_command_service.py    # Write logic
{pkg}/{feature}_query_service.py      # Read logic (cached)
core/domain/{entity}/                  # Pure logic (no I/O)
core/infra/persistence/repositories/   # Data access
```

**Ví dụ:** Route → BacktestCommandService → BarRepository + PerformanceCalculatorDomainService (domain, pure).

**Quy tắc chính:**
1. Routes: parse, inject service, delegate, respond (không business logic)
2. Services: một method cho mỗi command/query, nhận Pydantic model, trả DTO
3. Dùng `FromDishka[ServiceClass]` cho DI (không bao giờ dùng `Depends()`)
4. KHÔNG try/catch trong routes/services (propagate tới global handler)
5. Service method publish domain event cho mọi thay đổi state

### 2. Application Layer (Orchestrators & State Machines)

Các service có state, điều phối domain + adapters. Có thể gọi Adapters (khác với Domain). Được gọi bởi service method, thường là singleton.

**Ví dụ:** StrategyAppService (market events → signals → orders), BarAppService (tick aggregation), OrderAppService (state machine), PositionAppService (P&L tracking).

**Quy tắc:** Có thể import Domain + Adapters. Stateless (không decorator). Khởi tạo trong lifespan, inject bởi DI.

### 3. Dependency Injection (Dishka)

dishka phân giải dependency theo type hint. Routes inject qua `FromDishka[ServiceType]`. Provider trong `src/pocketquant/app/di/` được khởi tạo theo thứ tự: CoreProvider → PersistenceProvider → InfrastructureProvider → Services/AppServices. Setup trong lifespan qua `setup_dishka(app, container)`.

### 4. Repository Pattern (Instance-Based Data Access)

Toàn bộ data access qua instance method trong `src/pocketquant/core/infra/persistence/repositories/`. Tất cả repository kế thừa từ `BaseRepository`, dùng helper `_collection(name)`, inject `Database` qua constructor. Domain entity serialize qua `to_mongo()` / `from_mongo()`. Không có thư mục schemas/. Lợi ích: testable, pure domain, single source of truth.

### 5. Service Pattern (Business Logic)

Toàn bộ dependency qua constructor (do DI quản lý). Service có state được khởi tạo trong lifespan với try/finally để shutdown sạch. Ví dụ: `OrderAppService` gọi `await load_pending_orders()` trong lifespan trước khi bất kỳ handler nào dùng nó.

### 6. Provider Pattern (External Integrations)

Adapter cụ thể (vd `BinanceAdapter`) đứng sau một interface trong core (vd `IDataProviderPort`). Cô lập I/O ngoài, xử lý lỗi sạch, testable.

### 7. Event Handler Auto-Discovery Pattern

Dùng decorator `@event_handler` trên service method. Tự động đăng ký lúc startup qua `registry.register_instance(service, event_bus)`. Rõ ràng, scalable, type-safe.

### 8. Exception Handler Registration

Global exception handler tự động ánh xạ domain error sang HTTP response. Đăng ký lúc startup trong `src/pocketquant/app/main_extensions.py`:

```python
from pocketquant.core.common.exceptions import register_exception_handlers
from fastapi import Request
from fastapi.exceptions import RequestValidationError

register_exception_handlers(app, validation_error_cls=RequestValidationError)
```

**Ánh xạ tự động:**
- `NotFoundError` → 404 JSON `{error: {code, message}}`
- `DomainError` → 400 JSON `{error: {code, message}}`
- `AppError` (base) → 500 JSON `{error: {code, message}}`

Services KHÔNG bao giờ try/catch; exception propagate tới global handler.

### 8.5. Command/Query Service Pattern

Một service method cho mỗi command/query. Constructor nhận dependency (dishka tự wire). Method: nhận Pydantic Command/Query → fetch adapters → validate domain → persist → publish events → trả DTO.

**Template:**
```python
class SomeCommandService:
    def __init__(self, repo: SomeRepository):
        self.repo = repo

    async def handle(self, cmd: SomeCommand) -> dict:
        # Fetch + Validate
        if not await self.repo.exists(cmd.id):
            raise NotFoundError("NOT_FOUND")
        # Persist + Publish
        result = await self.repo.upsert({...})
        await EventBus.publish(SomeEvent(...))
        return result.to_dto()
```

**Worked Example: POST `/api/v1/strategies/{strategy_code}/subscriptions`**

Route:
```python
@strategy_router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    return await cmd_svc.add_symbol(AddSymbolCommand(...))
```

Service:
```python
async def add_symbol(self, cmd: AddSymbolCommand) -> dict:
    if not await self.tracked_symbol_repo.exists(cmd.symbol):
        raise NotFoundError("SYMBOL_NOT_TRACKED")
    sub = Subscription(id=generate_id(), strategy_code=cmd.strategy_id, ...)
    await self.subscription_repo.add(sub)
    return sub.to_dto()
```

Flow: Route → Service → Repository → MongoDB. Exception propagate tới global handler → 4xx/5xx JSON.

### 9. Service Extract-Method Pattern

Với các service method phức tạp vượt ~30 dòng với 8+ operation, tách thành private helper method. Method đơn giản (1-3 op) KHÔNG nên tách method.

**Hướng dẫn:** Tách khi method trở nên khó đọc. Mỗi helper làm MỘT operation logic. Tham chiếu: các sync service phức tạp có thể có 8 private helper (_fetch_bars, _persist_bars, _fail, _success, v.v.).

**Quy tắc chính:**
- Prefix `_` (private) để chỉ dùng nội bộ
- Giữ `handle()` như một checklist dễ đọc (không chi tiết logic)
- Mỗi helper: single-responsibility, async hoặc sync tùy nhu cầu
- Cải thiện testability: dễ test 8 helper tập trung hơn là một method khổng lồ

### 9.5. Integrity Repair Flow

Bar integrity repair: check → delete misaligned → resync gaps → verify.

**Quy trình 5 bước:**
1. **Check:** `check_integrity()` → liệt kê misaligned + missing bars
2. **Delete:** `bar_repo.delete_many_by_ids(misaligned_ids)`
3. **Resync:** `SyncSymbolCommand(..., skip_filter=True, n_bars=5000)` — bỏ qua filter để lấp gap
4. **Verify:** re-check integrity, ghi lại số `still_missing` + ranges
5. **Log:** cảnh báo nếu còn gap sau khi repair

**Vì sao skip_filter:** `filter_new_bars` truy vấn `bar_repo.find_datetimes` để chỉ loại các record có datetime đã tồn tại. Đúng cho các gap thưa. `skip_filter=True` vẫn hữu ích cho các repair flow muốn buộc re-upsert (vd để làm mới các giá trị OHLCV có thể đã dịch chuyển), bỏ qua cả existence check LẪN việc giảm wire-noise.

**Usage:** Background job `sync_repair` (mỗi 12h) hoặc endpoint `/api/v1/market-data/integrity/repair`. `repair_integrity()` trả về `dict` gồm deleted count, gaps_resynced, still_missing, still_missing_ranges.

### 10. Schema Consolidation (Use Base Classes)

Loại bỏ các subclass Create rỗng dư thừa. Dùng trực tiếp base class cho các thao tác repository.

**Quy tắc:** Một định nghĩa schema cho mỗi domain concept (OHLCV, Symbol, Order, v.v.). Không có Create subclass.

**Consolidation:**
- Không có thư mục schemas — repository dùng trực tiếp domain entity
- Mọi entity có `to_mongo()` / `from_mongo()` cho persistence MongoDB
- Factory method: `Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`

**Lợi ích:** Một schema (bảo trì dễ hơn), type hint đơn giản hơn, không trùng lặp.

### 11. Strategy Implementation Pattern

Triển khai interface `IStrategyService`. Triển khai `on_bar_completed(bar)` (bắt buộc), tùy chọn `on_quote_received(tick)`, `on_order_filled(order, fill_price)`. Trả `Signal | None`. Giữ pure logic, không broker/database (StrategyAppService quản lý execution). Lifecycle: `on_start()` → `on_bar_completed()` / `on_quote_received()` / `on_order_filled()` → `on_stop()`.

### 12. Domain Layer Patterns (Pydantic BaseModel + MongoDB Persistence)

Domain entity dùng **Pydantic BaseModel** (không phải dataclass) với MongoDB persistence tích hợp sẵn:
- **Entities (5):** `Bar`, `OrderAggregate`, `PositionAggregate`, `Symbol` (flattened), `SyncStatus`
- **Pattern:** Mỗi aggregate có `to_mongo()` → dict và `@classmethod from_mongo(doc)` → entity
- **Lợi ích:** Validation, serialization, schema evolution qua Pydantic
- **Value Objects:** Frozen qua `field(frozen=True)` hoặc `@dataclass(frozen=True)`
- **Events:** `@dataclass(frozen=True, eq=False)` với `__eq__` tùy chỉnh theo event_id
- **Quy tắc:** Dùng `generate_id()` (UUID7), VO/event bất biến, mọi aggregate extend BaseModel
- **Cache Keys:** `build_bar_cache_key()`
- **Collections:** `COLLECTION_BARS`

### 12.5. DDD Classification Guide (When to Use an Aggregate)

**Khi nào dùng Aggregate:**
- Entity có **invariants** cần bảo vệ (vd state machine của `OrderAggregate`)
- Entity có **lifecycle behavior** (vd `PositionAggregate` open → scale → close)
- Entity **sở hữu entity khác** trong một consistency boundary
- Entity **phát domain event** từ các business operation

**Khi nào KHÔNG dùng Aggregate:**
- Entity là **data record** (vd `Bar` — chỉ là dữ liệu OHLCV, chỉ serialization)
- Class là **event factory** không có state (anti-pattern)
- Class **không bao giờ được khởi tạo** trên thực tế
- Behavior là **CRUD-only** — dùng plain entity hoặc model

**Quy tắc dự án:**
1. Aggregate phải xứng đáng với độ phức tạp của nó — không invariant, không aggregate.
2. Event có thể tạo trực tiếp ở nơi cần — không cần wrapper aggregate.
3. Value object giữ dạng frozen dataclass — đơn giản, bất biến, không persistence.
4. DTO nằm ở application layer — chúng là infrastructure, không phải domain.

### 12.6. Primary Key Rule — UUIDv7 Only (MANDATORY)

**Mọi document được persist mà ta kiểm soát PHẢI dùng `_id` UUIDv7.** Không hash key, không natural key, không Mongo ObjectId, không composite-string key.

**Quy tắc:**
1. Sinh mọi id qua `generate_id()` (trả về `UUID`) từ `core/common/uuid.py`. Domain entity khai báo `id: UUID`; serialize với `"_id": str(self.id)` trong `to_mongo()`. Không bao giờ khai báo `id: str` cho entity được persist.
2. **Không bao giờ** derive `_id` từ business data (không `sha256(...)`, không composite-symbol-as-id, không slug).
3. **Không bao giờ** dựa vào ObjectId mặc định của Mongo — luôn set `_id` tường minh bằng uuid7.
4. **Uniqueness và idempotency thuộc về secondary unique index, không bao giờ trên `_id`.** Nếu một bộ ba `(strategy_code, symbol, interval)` phải unique, hãy enforce bằng unique compound index — không phải bằng cách biến nó thành primary key.

**Ngoại lệ duy nhất được phép — collection do thư viện third-party sở hữu.** Các collection có `_id` do thư viện ngoài ghi (vd MongoDBJobStore của APScheduler → `apscheduler_jobs`) được miễn. Ta **không** patch hay fork thư viện để ép uuid7. Ngoại lệ này CHỈ áp dụng cho collection ta không tạo ra; mọi collection do code của ta ghi đều tuân quy tắc không ngoại lệ.

**Lý do:** một kiểu id duy nhất xuyên suốt mọi code ta sở hữu. Dự đoán được, có thứ tự theo thời gian, không có special case cần nhớ, không có representation drift — mà không bị coupling với internal storage của third-party.

**Anti-patterns (đều bị cấm):**
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

**Format:** `{CODE}:{EXCHANGE}` (vd `BTCUSDT:BINANCE`, `AAPL:NYSE`)

**Quy tắc:**
- Một field bất biến duy nhất `symbol: str` thay thế các cặp `(code: str, exchange: str)` xuyên suốt domain entity
- Exchange là postfix mờ — business logic không bao giờ tách `symbol` thành các phần
- URL-encoded: `:` serialize thành `%3A` trong path segment (vd `/api/v1/bar/BTCUSDT%3ABINANCE`)
- JSON/database: giữ nguyên `:` thô (không encode bên trong payload)
- Cache key: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`, v.v.
- Entity bị ảnh hưởng: Bar, Order, Position, Symbol, SyncStatus, Subscription, TrackedSymbol

**Ví dụ Repository Usage:**
```python
# composite symbol (single field, no separate exchange param)
await bar_repo.find(symbol="BTCUSDT:BINANCE", interval="1d")
```

## Strategy ID Disambiguation

**PHÂN BIỆT QUAN TRỌNG:** Ba ID không bao giờ được nhầm lẫn.

| ID | Type | Ý nghĩa | Ví dụ | Persistence | Ghi chú |
|---|---|---|---|---|---|
| `strategy_code` | string | Tên template đăng ký trong `STRATEGY_REGISTRY` | `"hitnrun2"` | Class name (immutable) | Xác định class strategy nào để khởi tạo. Dùng để tra class và load từ persistent subscription. |
| `subscription_id` | string (uuid7) | ID của một binding (strategy_code, symbol, interval) | `"019ebe98-209c-71f2-af3d-981810e2d783"` | MongoDB `subscriptions._id` (immutable after creation) | uuid7 ngẫu nhiên qua `generate_id()`. Tính unique của bộ ba được enforce bởi unique compound index `ix_subscriptions_dedup_triple`, không phải bởi id. Key cho in-memory strategy instance, order, position, backtest result doc. |
| `template_id` | **DEPRECATED** | Tên cũ của path param từng giữ strategy_code | từng là `"hitnrun2"` trong URL | — | Không dùng. Dùng `strategy_code`; coi mọi tham chiếu legacy `template_id` là `strategy_code`. |

**Field Renames (Live Refactor):**
- MongoDB `strategy_subscriptions` → `subscriptions` (tên collection)
- Subscription doc: `strategy_id: "{code}"` → `strategy_code: "{code}"` (tên field + semantics)
- Order doc: `strategy_id: "{subscription_id}"` → `subscription_id: "{subscription_id}"` (tên field + semantics)
- Position doc: `strategy_id: "{subscription_id}"` → `subscription_id: "{subscription_id}"` (tên field + semantics)
- Backtest doc: `strategy_id: "{code}"` → `strategy_code: "{code}"`; giữ nguyên `subscription_id`

**Repository Method Renames:**
- `SubscriptionRepository.list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`
- `OrderRepository.find_by_strategy(strategy_id)` → `find_by_subscription(subscription_id)`
- `PositionRepository.get_by_strategy(strategy_id)` → `get_by_subscription(subscription_id)`
- `BacktestRepository.list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`

**HTTP Route Semantics (Post-Refactor):**
- `POST /strategies/{strategy_code}/subscriptions` — tạo subscription cho template này
- `POST /subscriptions/{sub_id}/start` — start subscription instance này
- `GET /subscriptions/?strategy_code=X` — lọc subscription theo template (tùy chọn)

**Dedup Invariant (CRITICAL):**
Subscription id là uuid7 ngẫu nhiên — chúng không nói gì về bộ ba. Guard chống trùng duy nhất là unique compound index:
```python
await collection.create_index(
    [("strategy_code", 1), ("symbol", 1), ("interval", 1)],
    unique=True, name="ix_subscriptions_dedup_triple",
)
```
`symbol` được normalize (`.upper()`) trong `add_symbol` trước khi lưu — index là case-sensitive, nên việc normalize đó là load-bearing.
Concurrency test: `tests/core_test/infra/persistence/test_subscription_repository.py:test_concurrent_add_same_triple_one_doc_one_error`

## Code Organization Guidelines

### File Naming

Dùng kebab-case với tên mô tả mục đích (suffix trong tên file mã hóa layer):

```
quote_routes.py                      # QuoteRoute functions (API HTTP handlers)
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

Tên class + file tự mã hóa layer/role. Suffix theo bảng dưới. Domain concepts (entities, VOs, enums) không có suffix — chúng là ngôn ngữ miền.

| Layer | Pattern | Class Suffix | File Suffix | Ví dụ |
|-------|---------|--------|--------|--------|
| Entities | `{Name}` hoặc `{Name}Aggregate` | None / `Aggregate` | `.py` | `Bar`, `Symbol`, `OrderAggregate` |
| Events | `{Entity}{PastTense}Event` | `Event` | `.py` | `OrderFilledEvent`, `BarCompletedEvent` |
| Enums | `{Concept}` | None | `.py` | `Interval`, `OrderType`, `OrderSide` |
| Value Objects | `{Concept}` | None | `.py` | `PnL`, `OHLCV`, `BarRange` |
| **Domain Services** | `{Name}DomainService` | `DomainService` | `*_domain_service.py` | `PositionCalculatorDomainService`, `BarBuilderDomainService`, `PerformanceCalculatorDomainService` |
| **Domain Strategy (Impl)** | `{Name}StrategyService` | `StrategyService` | `*_strategy_service.py` | `EngulfingStrategyService`, `HitNRun2StrategyService` |
| **Domain Strategy (Interface)** | `IStrategyService` | `IStrategyService` | `strategy_service_interface.py` | `IStrategyService` |
| Repositories | `{Entity}Repository` | `Repository` | `*_repository.py` | `BarRepository`, `OrderRepository` |
| **Infra Port (Interface)** | `I{Concept}Port` | `Port` | `*_port.py` (1 port/file) | `IBrokerPort`, `IBrokerFactoryPort`, `IDataProviderPort`, `IRealtimeQuoteProviderPort` |
| **Infra Adapter (Impl)** | `{Source}[{Type}]Adapter` | `Adapter` | `*_adapter.py` | `OKXBrokerAdapter`, `BinanceAdapter`, `PaperBrokerAdapter`, `OKXWebSocketAdapter` |
| **Helper** | `{Name}Helper` | `Helper` | `*_helper.py` | (utility pattern; follow naming rule when used) |
| **App Services** | `{Name}AppService` | `AppService` | `*_app_service.py` | `StrategyReconcileAppService`, `BacktestSandboxAppService`, `WsSubscriptionAppService`, `BacktestReportAppService` |
| Query Models | `{Get\|List}{Entity}Query` | `Query` | `*_query.py` | `GetOHLCVQuery`, `ListOrdersQuery` |
| Command Models | `{Action}{Entity}Command` | `Command` | `*_command.py` | `SyncSymbolCommand`, `StartStrategyCommand` |
| CQRS Services | `{Domain}{Command\|Query}Service` | `Service` | `*_service.py` | `StrategyCommandService`, `BacktestQueryService` |
| DTOs | `{Name}Response` | `Response` | `.py` | `SyncResponse`, `QuoteResponse` |
| Routes | (functions) | — | `*_routes.py` | `async def sync_symbol(...)` |
| Middleware | `{Name}Middleware` | `Middleware` | `*_middleware.py` | `RateLimitMiddleware` |
| Errors | `{Name}Error` | `Error` | `.py` | `AppError`, `NotFoundError`, `DomainError` |
| DI Providers | `{Domain}Provider` | `Provider` | `*_provider.py` | `CoreProvider`, `ExecutionProvider` |
| Configs | `{Name}Config` | `Config` | `*_config.py` | `BacktestConfig`, `RiskConfig` |
| Background Jobs | (functions) | — | `*_jobs.py` | `sync_1m()`, `sync_integrity()` |

### Naming Principles & Exemptions

**Ba nguyên tắc cốt lõi:**

1. **Tên class + file tự mã hóa layer/role.** Đọc `PositionCalculatorDomainService` hoặc `binance_adapter.py` biết ngay layer không cần xem folder.

2. **Không stack 2 doer-suffix generic (`-er`/`-or`) trong 1 tên.** Nếu bị dính (vd một class vừa mang `-Tracker` vừa `-Helper` → `*TrackerHelper`), dùng gerund: `*TrackingHelper`. **Ngoại lệ:** danh từ nghiệp vụ kết `-er` (vd `Broker`) không tính là doer-suffix → `BrokerAdapter` hợp lệ.

3. **Data class + role đã có suffix chuẩn → giữ nguyên.** Exempt list bên dưới.

**Exempt list** (giữ suffix hiện tại, KHÔNG ép convention):

| Nhóm | Ví dụ |
|---|---|
| CQRS | `*CommandService`, `*QueryService` (app layer, request-scoped ≠ orchestrator) |
| Persistence | `*Repository` |
| DI / cross-cutting | `*Provider`, `*Middleware` |
| App handler | `RiskCheckHandler`, `event_handler` (decorator) |
| Infra factory/scheduler | `BrokerFactory`, `JobScheduler` |
| Infra sub-component (OKX) | `OkxMessageParser`, `OkxOrderMapper`, `OkxPositionMapper`, `OkxReconnectionHandler`, `OkxStateReconciler`, `BrokerFactory`, `JobScheduler` |
| Data class | Entity, VO, enum, event, `*Command`/`*Query`/`*Response` |

### Module Size

Giữ mỗi file dưới 200 LOC để quản lý context tối ưu:

- Nếu file vượt 200 LOC, tách thành các module tập trung
- Dùng composition (import và delegate) thay vì inheritance
- Trích các utility function ra module riêng
- Tạo service class chuyên biệt cho logic phức tạp

**Ngoại lệ đã biết (được biện minh bởi độ phức tạp):**
- `core/infra/brokers/paper/paper_broker_adapter.py` (~850 LOC — 4 fill path + futures/margin accounting + SL/TP synthetic exits)
- `engine/market_data/app_services/sync_jobs.py` (~730 LOC — multi-interval backfill + integrity jobs)

### Import Organization

**Ví dụ (Features layer - Pydantic allowed):**
```python
# 1. Standard library
import asyncio
from datetime import datetime
from typing import Optional, List

# 2. Third-party
from pydantic import BaseModel  # OK in Features/Config layers
import structlog

# 3. Local
from pocketquant.core.common.database import Database
from pocketquant.core.common.logging import get_logger
from pocketquant.app.features.market_data.base.models import OHLCV
```

**Ví dụ (Domain layer - Stdlib dataclasses only):**
```python
# 1. Standard library
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, ClassVar

# 2. Local (no third-party, no I/O)
from pocketquant.core.domain.shared.domain_event import DomainEvent
from pocketquant.core.common.uuid import generate_id

# NOTE: No pydantic, pymongo, redis, aiohttp imports in domain/
```

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

## Type Hints

Dùng full type hint trên mọi public API: function, class attribute, kiểu phức tạp. Công cụ: `pyright` để type check (scope từ `pyrightconfig.json`).

## Error Handling

**Try-Except:** Bắt exception cụ thể, không bao giờ `except` trần. Dùng structured logging kèm context.

**Propagation:** Routes bắt/trả 4xx-5xx, Services bắt/log/trả error dict, Repositories propagate.

## Testing Standards

Tối thiểu 80% code coverage (service method, repository method, error path, integration point):

```bash
pytest --cov=src --cov-report=term-missing
pytest tests/test_market_data.py::test_sync --pdb  # Run + debug
```

Dùng pytest fixture + monkeypatch để mock:

```python
@pytest.fixture
async def mock_database(monkeypatch):
    mock_db = AsyncMock()
    monkeypatch.setattr("src.common.database.Database._database", mock_db)
    return mock_db
```

## Code Quality Tools

### Linting (ruff)

```bash
ruff check .              # Lint check
ruff check . --fix        # Auto-fix issues
```

**Rule được enforce:**
- Unused import (không import tên class cũ như `BinanceAdapter`, `IStrategyService`, `PaperBrokerAdapter`)
- Undefined name
- Syntax error
- Duplicate code
- Complexity metric

### Formatting (ruff)

```bash
ruff format .             # Auto-format code
```

### Type Checking (Pyright)

Ta dùng **Pyright** (qua Pylance trong VSCode), không phải mypy:
- **Nhanh hơn 3-5x** so với mypy trên codebase lớn
- **Tích hợp VSCode native** qua extension Pylance
- **Type inference tốt hơn** cho các pattern phức tạp
- **Hỗ trợ Pydantic v2 native** (không cần plugin)

```bash
pyright                                 # Type check (scopes from pyrightconfig.json)
pyright src/pocketquant/engine/backtest/  # Check specific module
```

## Performance Considerations

### Blocking I/O

Chạy blocking operation trong thread pool để tránh block event loop:

```python
# Good: native async I/O (Binance via BinanceAdapter/aiohttp)
bars = await self.provider.fetch_ohlcv(symbol, interval, n_bars)

# Bad: blocking call on the event loop
bars = some_sync_client.get_bars(symbol)  # Blocks!
# If a sync lib is unavoidable, isolate it:
#   await loop.run_in_executor(self.executor, sync_fn, symbol)
```

### Bulk Operations

Dùng bulk upsert thay vì insert từng cái:

```python
# Good: Single bulk operation
await BarRepository.upsert_many(records)  # One round trip to DB

# Bad: Loop of individual inserts
for record in records:
    await BarRepository.insert_one(record)  # N round trips!
```

### Cache Invalidation

Dùng xóa theo pattern để đảm bảo tính đúng (thay vì xóa chọn lọc):

```python
# Good: Pattern-based deletion (simple, correct)
await Cache.delete_pattern("bar:AAPL:*")

# Bad: Selective deletion (easy to miss keys)
await Cache.delete(f"bar:AAPL:NYSE:1d:100")
```

### Concurrency

Dùng asyncio.Lock cho shared state:

```python
# Good: Lock protects bar builder state
async with self._lock:
    self._bar_builders[interval].update_ohlc(tick)

# Bad: No protection against race conditions
self._bar_builders[interval].update_ohlc(tick)
```

### Async Suspension Points — "Await Is Preemption"

**Quy tắc một dòng:** mỗi `await` là một preemption point. Event loop có thể resume bất kỳ coroutine sẵn sàng nào tại đây. State mà một coroutine khác đọc phải hợp lệ **trước** suspension point cho phép nó chạy.

Lối tắt tư duy: `await` ≈ `Thread.yield()`. Nếu bạn không tin một giá trị qua `Thread.yield()` trong chương trình threaded, đừng tin nó qua một `await`.

**Điều gì tính là suspension point (kể cả những cái không hiển nhiên):**

| Construct | Suspension? | Notes |
|---|---|---|
| `await coro()` | Yes | The obvious one. |
| `await asyncio.sleep(0)` | Yes | Explicit yield even with 0. |
| `yield x` inside `async def` | **Yes** | Easy to miss. Async generators + `@asynccontextmanager` use this. |
| `async for x in iterable` | Yes | Calls `await iterable.__anext__()` each loop. |
| `async with cm:` | Yes (entry & exit) | Calls `await cm.__aenter__()` and `__aexit__()`. |
| `await asyncio.gather(...)` | Yes | Children interleave between each other's awaits. |
| `await container.get(X)` | Yes if provider does I/O | Dishka `AsyncIterator` factories hide awaits. |
| Plain assignment, `if`, arithmetic | No | Synchronous between awaits — use this for atomic regions. |

**Sáu sub-pattern để áp dụng.** Cùng root cause, khác hình dạng:

**1. Publish-before-subscribe** — wire dependency TRƯỚC lời gọi khởi động worker (scheduler, queue consumer, websocket reader, background task). Sau khi lời gọi trả về, worker trở nên quan sát được với event loop và có thể dispatch tại `await` kế tiếp.

```python
# Anti-pattern (racy)
register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),  # scheduler now LIVE
)
# set_sync_container() inside register_sync_jobs runs AFTER scheduler may dispatch

# Fix
set_sync_container(container)   # wire global FIRST
register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),
)
```

Vì sao nó cắn: APScheduler persist `next_run_time` qua các lần restart. Tick đầu tiên dispatch bất cứ thứ gì đến hạn trong `misfire_grace_time` (thiết lập per-job, vd 120s cho sync_1m, 3600s cho daily job). Nếu module-level global chưa được set → `RuntimeError` ở dòng đầu tiên của mọi job được dispatch. Orphan recovery chạy lúc startup qua `recover_orphan_jobs()` để bắt job kẹt ở trạng thái `running` (crash resilience).

**2. Initialize-before-first-await** — không bao giờ `await` trên thứ phơi bày object nửa vời cho task khác. Dựng đầy đủ, rồi mới publish.

```python
# Anti-pattern
async def make_session():
    sess = Session()
    REGISTRY[sess.id] = sess          # published
    sess.user = await load_user()     # other tasks see sess with no user

# Fix
async def make_session():
    user = await load_user()           # all I/O first
    sess = Session(user=user)          # construct atomically
    REGISTRY[sess.id] = sess           # publish fully-formed
```

**3. TOCTOU across `await`** — race condition kinh điển, phiên bản async.

```python
# Anti-pattern
if user.balance >= amount:        # CHECK
    await db.debit(user, amount)  # USE — balance may have changed → double-spend

# Fix A: storage-layer atomicity (preferred)
result = await db.try_debit(user, amount)  # WHERE balance >= amount

# Fix B: per-key async lock
async with user_locks[user.id]:
    if user.balance >= amount:
        await db.debit(user, amount)
```

Quy tắc chung: re-read shared state sau mỗi `await`, giữ lock xuyên `await`, hoặc đẩy invariant xuống storage layer.

**4. Atomic block phải không có `await`** — giữa cặp read/write của shared state, không suspension.

```python
# Anti-pattern: lost increment
counter = counters[key]
await some_io()
counters[key] = counter + 1   # another coroutine may have done the same → lost update

# Fix: atomic between awaits
counters[key] = counters[key] + 1
await some_io()
```

`dict[key] += 1` là atomic trong CPython giữa các await (vùng single bytecode dưới GIL). **Không** atomic xuyên `await`.

**5. `yield` trong `@asynccontextmanager` / `AsyncIterator` factory LÀ một suspension point.** Toàn bộ setup trước `yield`, cleanup trong `try/finally` sau đó.

```python
# Anti-pattern (Dishka factory)
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    GLOBAL_HANDLE = svc          # published before initialized
    yield svc                    # caller now has svc and may use it
    await svc.connect()          # NEVER runs at the right time

# Fix
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    await svc.connect()          # all setup BEFORE yield
    try:
        yield svc
    finally:
        await svc.aclose()       # cleanup in finally — survives cancellation
```

**6. Cancellation rơi vào bất kỳ `await` nào.** `asyncio.CancelledError` có thể được raise tại `await` kế tiếp sau `task.cancel()`. Cleanup không nằm trong `try/finally` có thể không chạy.

```python
# Anti-pattern: money disappears if cancelled between debit and credit
async def transfer():
    await db.debit(src, amount)
    await network.notify()        # cancellation here → credit never runs
    await db.credit(dst, amount)

# Fix: transactional storage (preferred)
async with db.transaction():
    await db.debit(src, amount)
    await db.credit(dst, amount)

# Or: try/finally + compensating action
async def transfer():
    debited = False
    try:
        await db.debit(src, amount)
        debited = True
        await db.credit(dst, amount)
    except (asyncio.CancelledError, Exception):
        if debited:
            await db.credit(src, amount)  # compensate
        raise
```

**Symmetry check:** khi hai subsystem kề nhau làm wiring tương tự (vd `backtest_jobs` và `sync_jobs`), diff trình tự startup của chúng. Ordering bất đối xứng gần như luôn là bug.

**Pre-`await` checklist.** Trước mỗi `await`, tự hỏi:
- Nó có publish một handle / register một callback / khởi động một worker không? Nếu có, object đã được khởi tạo đầy đủ chưa?
- Ta đang để invariant nào ở trạng thái trung gian?
- Ta vừa đọc một giá trị mà một coroutine khác có thể sửa trước khi dòng kế tiếp dùng nó?
- Nếu `CancelledError` rơi vào đây, cleanup có chạy không? Cái này có nên nằm trong `try/finally` hay `asyncio.shield`?
- `async for` / `async with` / `gather` này có che giấu nhiều suspension point hơn ta đang nghĩ không?

**Worked-example reference:** `plans/reports/debugger-260524-1324-sync-jobs-container-race.md`

## Configuration & Secrets

Không bao giờ hardcode. Dùng `.env` (local) và environment variable (prod). Không bao giờ commit `.env` hay secret. Định nghĩa trong `src/pocketquant/core/config.py::Settings` với Pydantic.



## Clean Architecture Rules (MANDATORY)

| Layer | Rules |
|-------|-------|
| **Domain** | ❌ No I/O imports (pymongo, redis, aiohttp) ✅ Pydantic BaseModel with to_mongo/from_mongo ✅ Validation in __post_init__ ✅ Pure logic only |
| **Services** | ❌ No decorators ✅ Orchestrate domain + adapters ✅ Stateful services ✅ Called by routes |
| **Routes** | ❌ No business logic ✅ Thin HTTP handlers ✅ Inject services via FromDishka ✅ Call service methods |
| **Adapters** | ❌ Never imported by Domain ✅ Brokers, persistence, scheduling ✅ All external I/O |

## Datetime Serialization (API Responses)

Khi serialize `datetime` sang JSON cho frontend tiêu thụ, **luôn dùng `to_utc_iso()`**:

```python
from pocketquant.core.common.time import to_utc_iso

# Good: consistent UTC, JavaScript-safe
"next_run": to_utc_iso(job.next_run_time)   # → "2026-04-14T01:43:57Z" or None

# Bad: malformed if datetime has tz offset (e.g. +07:00Z)
"next_run": dt.isoformat() + "Z"

# Bad: missing Z suffix, JS parses as local time
"next_run": dt.isoformat()
```

**Dùng nội bộ** (logging, cache key): `.isoformat()` trần là được.

## Deprecated Patterns (DO NOT USE)

- Business logic trong features/ → chuyển sang Application layer
- Gọi DB trực tiếp ngoài persistence/ → dùng repository pattern
- Pydantic BaseModel trong domain/ → dùng stdlib dataclass (domain phải zero I/O)
- Mệnh đề `except:` trần → bắt exception cụ thể
- Synchronous blocking I/O trong code async → dùng ThreadPoolExecutor
- UUID4 cho ID → dùng UUID7 (time-ordered, thân thiện B-tree)
- Wiring DI thủ công → dùng Dishka provider
- Gọi trực tiếp Database.get_collection() ngoài persistence/ → dùng BaseRepository._collection()
- Class schema viết tay → dùng domain entity với to_mongo/from_mongo

## Import Contracts (Dependency Boundaries)

Enforce qua `import-linter` trong `pyproject.toml`. Bề mặt phổ biến:

| From | To | Via |
|------|----|----|
| Routes | Command/Query Service | `FromDishka[ServiceType]` |
| Services | Repository | Constructor DI |
| Services | Exceptions | `raise NotFoundError`, `raise DomainError` |
| Routes | Exception Handler | Global registration |
| Repositories | MongoDB | `Database.get_collection()` |

Không reverse dep (routes ← services, services ← repositories). Domain không bao giờ import từ Adapters/Application/Features.

## Quality Checklist

- [ ] Có đủ type hint | [ ] Không lỗi syntax (ruff check passes)
- [ ] Code đã format (ruff format) | [ ] Type checking passes (pyright)
- [ ] Tests pass (pytest) | [ ] Coverage ≥80%
- [ ] Không blocking I/O trong async | [ ] Đã test error path
- [ ] Dùng environment variable | [ ] Không secret trong code/config
