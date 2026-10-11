# Code Standards

Các quy tắc dưới đây là rules of thumb, không phải mandate: áp dụng khi chúng làm code dễ đọc hơn, bỏ qua khi chúng làm code tệ đi. Lệnh chạy và test nằm ở [README](../README.md); kiến trúc tổng thể nằm ở [system-architecture.md](./system-architecture.md).

## Nguyên tắc

- **KISS:** chọn lời giải đơn giản nhất còn đúng. Không thêm layer, interface hay config cho nhu cầu chưa có.
- **DRY:** một khái niệm có một chỗ định nghĩa. Lặp lại hai lần là chấp nhận được; lần thứ ba thì gom lại.
- **Cân bằng:** không có god-function ôm cả luồng, cũng không có micro-helper chỉ bọc một lời gọi. Một hàm làm một việc có tên rõ ràng.
- Dependency direction cố định: `core ◁ engine ◁ backtest ◁ app`. Domain (`core.domain`) không import `core.infra`; chỉ `app` được import `fastapi`. `import-linter` enforce cả ba (xem [Quality gate](#quality-gate)).

## Khi nào extract helper

- Extract khi tên của helper thêm ý nghĩa mà code inline không nói được, hoặc khi code đó được dùng lại ở ít nhất hai chỗ.
- Không extract chỉ để hàm ngắn đi. Một hàm 2 dòng chỉ `return self._x.y(...)` là pure delegation; nó làm người đọc phải nhảy file mà không học thêm gì.
- Một flow nên đọc được trong một file khi có thể, và tối đa 3 file (cộng các leaf call như repository hay client). Ví dụ: sync flow đọc trong `sync_policy.py`, `sync_runner.py` và `sync_service.py`.

## Kích thước file và hàm

- Khoảng 400 LOC mỗi file là soft guidance, không phải trigger để split. Split khi file chứa hai concern độc lập, không phải khi nó dài.
- Hàm nên giữ ≲ 60 dòng. Hàm dài hơn thường đang làm nhiều việc; tách theo bước có tên, không tách theo số dòng.

## Đặt tên

Domain concept (entity, value object, enum, domain service) không có suffix — chúng chính là ngôn ngữ domain. Suffix chỉ dùng khi nó mang vai trò thật:

| Suffix | Vai trò | Ví dụ |
|---|---|---|
| `Repository` | Data access cho một collection | `BarRepository`, `OrderRepository` |
| `Service` | Logic nghiệp vụ mà route hoặc job gọi | `SyncService`, `StrategyCommandService` |
| `Event` | Domain event, `{Entity}{PastTense}Event` | `OrderFilledEvent`, `BarCompletedEvent` |
| `Error` | Exception | `AppError`, `NotFoundError`, `DomainError` |
| `Provider` | Dishka provider | `InfrastructureProvider`, `AdaptersProvider` |

- Các tên `AppService`, `CommandService` và `QueryService` hiện có được giữ nguyên, nhưng chúng không phải các role riêng biệt: tất cả đều là `Service`. Code mới không cần chọn giữa chúng.
- Interface của infra mang prefix `I` (`IBroker`, `IDataProvider`, `IRealtimeQuoteProvider`); implementation mang prefix nguồn (`BinanceClient`, `OKXBroker`, `PaperBroker`).

**File naming:** `snake_case` theo mục đích của module, khớp với class hoặc concern chính bên trong:

```
quote_app_service.py           # QuoteAppService
bar_builder.py                 # BarBuilder domain service
bar_repository.py              # BarRepository data access
binance_client.py              # BinanceClient (IDataProvider) cho REST API
binance_websocket_client.py    # BinanceWebSocketClient cho @aggTrade WebSocket
```

## Routes và services

- Route nằm trong `src/pocketquant/app/routes/`, khai báo `route_class=DishkaRoute` trên `APIRouter` và inject service bằng `FromDishka[...]`. Không bao giờ dùng `Depends()` cho service.
- Route mỏng: parse request, gọi một method của service, trả kết quả. Logic nghiệp vụ nằm trong service.
- Pydantic model chỉ dùng cho request body thật (`SyncSymbolCommand`, `RunBacktestCommand`, `AddSymbolCommand`). Path và query param dạng scalar được truyền thẳng vào service method, không bọc trong model.
- Không try/except trong route hay service để đổi exception thành response. Exception propagate tới global handler đăng ký trong `src/pocketquant/app/main_extensions.py`: `NotFoundError` → 404, `DomainError` → 400, `AppError` → 500, body dạng `{error: {code, message}}`.
- Datetime trả cho frontend luôn qua `to_utc_iso()` (`pocketquant.core.common.time`) để có hậu tố `Z` đúng; `.isoformat()` chỉ dùng nội bộ (log, cache key).

```python
@router.post("/sync", response_model=SyncResponse)
async def sync_symbol(
    cmd: SyncSymbolCommand,
    sync_service: FromDishka[SyncService],
) -> SyncResponse:
    return await sync_service.sync_one(cmd)
```

## Dependency Injection

- Có đúng 3 provider module trong `src/pocketquant/app/di/`: `infrastructure.py` (`InfrastructureProvider`: `Settings`, event bus, database, cache, repositories, scheduler), `adapters.py` (`AdaptersProvider`: `BrokerFactory` và `SyncPolicies` cùng các venue adapter bên trong), `services.py` (`ServicesProvider`: services).
- `Settings` vào container qua `from_context(provides=Settings, scope=Scope.APP)`; `create_container()` truyền nó trong `context`.
- Container dùng `validation_settings=STRICT_VALIDATION`: một type đăng ký hai lần là lỗi lúc build container. Mỗi type có đúng một provider.
- Service cần cleanup dùng generator factory (`yield`): mọi setup trước `yield`, cleanup trong `try/finally` (xem [Async](#async-await-là-preemption-point), mục 5).

## Repositories

- Mọi repository nằm trong `core.infra.persistence.repositories`; `engine`, `backtest` và `app` không có repository nào.
- Repository là instance class nhận `Database` qua constructor. Domain entity tự serialize bằng `to_mongo()` / `from_mongo()`; không có thư mục schemas riêng.

**Primary key: chỉ UUIDv7.** Mọi document mà code của chúng ta ghi đều có `_id` là UUIDv7 sinh bằng `generate_id()` (`core/common/uuid.py`). Không hash key, không natural key, không Mongo ObjectId, không composite-string key. Uniqueness và idempotency đặt trên secondary unique index, không bao giờ trên `_id`. Ngoại lệ duy nhất là collection do thư viện bên thứ ba sở hữu `_id` (ví dụ `apscheduler_jobs` của APScheduler `MongoDBJobStore`); không patch thư viện để ép uuid7.

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

## Sync policy pattern

Market-data sync chạy theo từng exchange qua một `SyncPolicy` (`src/pocketquant/engine/market_data/sync_policy.py`).

- **`SyncPolicy`** (frozen dataclass) mang mọi thứ khác nhau giữa các exchange: `exchange`, `data_provider` (`IDataProvider`), `quote_provider` (`IRealtimeQuoteProvider | None`), `poll_intervals`, `poll_n_bars`, `cascade`, `cascade_lookback_minutes`, `integrity_intervals`, `backfill_n_bars`, `poll_time_cap_s`, `history_days` và `calendars` (map từ symbol code sang `MarketCalendar`).
- **`SyncPolicies`** là registry, build một lần trong `AdaptersProvider.get_sync_policies` (`app/di/adapters.py`). Hiện registry có một policy, `binance_policy(...)`.
- **Lookup chỉ theo exchange suffix** qua `SyncPolicies.policy_for(symbol)`. Không có fallback: suffix không có policy trả `None`, log `market_data.unknown_exchange` một lần cho mỗi exchange, và caller bỏ qua symbol đó. `quote_providers()` trả quote provider của mọi policy cho WS feed.
- **`MarketCalendar`** mô tả các trading session theo tuần dưới dạng cặp phút-trong-tuần `[start, end)`; `None` nghĩa là luôn mở (`ALWAYS_OPEN`). `SyncPolicies.market_calendar(symbol)` trả calendar của symbol, mặc định `ALWAYS_OPEN`.
- **`sync_runner.py`** chứa các job APScheduler chạy cho mọi policy: `sync_1m` (poll REST các symbol đang mở phiên, giới hạn bởi `poll_time_cap_s`, rồi cascade 1m → 5m/15m/1h/4h/1d khi `cascade=True`), `sync_verify_cascade`, `sync_backfill`, `sync_integrity` và `sync_repair`. `register_sync_jobs()` đăng ký chúng bằng text reference để `MongoDBJobStore` serialize được.
- **`bar_integrity.py`** chứa `check_integrity`, `repair_integrity` và `verify_one_symbol`. Các check này calendar-aware: slot ngoài trading session không tính là gap.

## Composite symbol

**Format:** `{CODE}:{EXCHANGE}` (ví dụ `BTCUSDT:BINANCE`).

- Một field `symbol: str` bất biến thay cho cặp `(code, exchange)` trên mọi entity: `Bar`, `Order`, `Position`, `Symbol`, `SyncStatus`, `Subscription`, `TrackedSymbol`.
- Business logic coi exchange là postfix mờ và không tự tách `symbol`. Chỗ duy nhất tách là `split_composite(symbol) -> (code, exchange)` trong `core/domain/symbol/entities.py`; nó strip và upper-case trước khi tách. Dùng nó cho policy lookup và cho adapter cần code thuần (`BinanceClient`, `BinanceWebSocketClient`); không viết `.split(":")` mới.
- Validation: `COMPOSITE_SYMBOL_RE` cho dữ liệu nội bộ, `COMPOSITE_SYMBOL_PATTERN` (cho phép dấu chấm, mỗi phần tối đa 32 ký tự) cho input từ HTTP path và body.
- URL: `:` được encode thành `%3A` trong path segment (ví dụ `/api/v1/bar/BTCUSDT%3ABINANCE`). JSON và database giữ nguyên `:`.
- Cache key dùng symbol nguyên vẹn: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`.

```python
await bar_repo.find(symbol="BTCUSDT:BINANCE", interval="1d")
```

## Async: await là preemption point

**Quy tắc một dòng:** mọi `await` là một preemption point. Event loop có thể chạy bất kỳ coroutine nào khác tại đó, nên state mà coroutine khác đọc phải hợp lệ **trước** suspension point cho phép nó chạy.

Các construct là suspension point, kể cả những cái khó thấy:

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

**1. Publish-before-subscribe:** wire dependency TRƯỚC lời gọi khởi động worker (scheduler, queue consumer, websocket reader, background task). Sau khi lời gọi đó trả về, worker đã hiện diện với event loop và có thể dispatch ở `await` kế tiếp.

```python
# Anti-pattern (racy)
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),  # scheduler now LIVE
)
# set_sync_container() inside register_sync_jobs runs AFTER scheduler may dispatch

# Fix
set_sync_container(container)   # wire global FIRST
await register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),
)
```

Lý do nó gây lỗi: APScheduler lưu `next_run_time` qua các lần restart, và tick đầu tiên dispatch mọi job đến hạn trong `misfire_grace_time` (cấu hình theo job, ví dụ 120s cho `sync_1m`, 3600s cho job hằng ngày). Nếu global của module chưa được set, mọi job được dispatch sẽ `RuntimeError` ngay dòng đầu. `recover_orphan_jobs()` chạy lúc startup để dọn các job kẹt ở trạng thái `running`.

**2. Initialize-before-first-await:** không `await` khi một object dở dang đã lộ ra cho task khác. Dựng xong rồi mới publish.

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

**3. TOCTOU qua `await`:** race condition kinh điển, phiên bản async.

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

Quy tắc chung: đọc lại shared state sau mỗi `await`, giữ lock qua `await`, hoặc đẩy invariant xuống storage layer.

**4. Atomic block không có `await`:** giữa cặp đọc/ghi shared state, không có suspension.

```python
# Anti-pattern: lost increment
counter = counters[key]
await some_io()
counters[key] = counter + 1   # another coroutine may have done the same → lost update

# Fix: atomic between awaits
counters[key] = counters[key] + 1
await some_io()
```

`dict[key] += 1` là atomic giữa hai `await` trong CPython, nhưng **không** atomic qua một `await`.

**5. `yield` trong `@asynccontextmanager` / factory `AsyncIterator` LÀ suspension point.** Mọi setup trước `yield`, cleanup trong `try/finally` sau nó.

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

**6. Cancellation rơi vào bất kỳ `await` nào.** Sau `task.cancel()`, `asyncio.CancelledError` có thể nổ ở `await` kế tiếp; cleanup không nằm trong `try/finally` có thể không chạy.

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
```

**Symmetry check:** khi hai subsystem kề nhau wiring giống nhau (ví dụ `backtest_jobs` và `sync_jobs`), so sánh thứ tự startup của chúng. Thứ tự lệch nhau gần như luôn là bug.

**Checklist trước mỗi `await`:**
- Lời gọi này có publish handle, đăng ký callback hay khởi động worker không? Nếu có, object đã khởi tạo xong chưa?
- Invariant nào đang ở trạng thái trung gian?
- Giá trị vừa đọc có thể bị coroutine khác sửa trước dòng kế tiếp dùng nó không?
- Nếu `CancelledError` rơi vào đây, cleanup có chạy không? Có cần `try/finally` hay `asyncio.shield` không?
- `async for` / `async with` / `gather` này có giấu thêm suspension point không?

## Comment Policy — Explain WHY, Not WHAT

Comments cost LOC and rot out of sync with code. Default: no comment. Add one only when the code cannot speak for itself. Applies to Python (`#`, `"""`) and TS/JS (`//`, `/** */`) alike.

### REMOVE / never write

- Comments restating the line (`# increment counter`, `# validate creds` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`, `# Market data (16)`)
- Docstrings echoing the symbol name (`"""Get bar."""` on `get_bar`)
- Filler Arrange/Act/Assert markers that add nothing
- Plan/phase/finding refs — explain the invariant, not the origin

### KEEP / write only for

- **WHY:** races, ordering/suspension constraints, publish-before-subscribe, await-preemption notes, invariants, trade-offs
- **Hacks / workarounds** + external-system quirks (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` / `// @ts-expect-error` / `// eslint-disable` — always with their reason
- Warnings about non-obvious failure modes (`# benign — already dropped`)
- Docstrings documenting params / contracts / edge cases / non-obvious return semantics
- Test comments explaining scenario intent or non-obvious setup

### Examples

```python
# KEEP — load-bearing ordering note (see "Await Is Preemption")
# Wire the event bus before any handler can publish: container.get() awaits,
# so a subscriber resolved first would miss publish-before-subscribe events.

# REMOVE — restates the call
# Get the bar from the repository
bar = await repo.get(bar_id)
```

**Route docstrings:** name-echo docstrings on FastAPI routes are removed even though OpenAPI summaries may blank — only docstrings carrying param/contract/edge-case content survive.

**Docstrings:** Minimal. Let type hints carry the heavy lifting. Module-level: brief purpose statement only when non-obvious.

## Testing

- **Characterization test trước refactor:** trước khi đổi cấu trúc một flow, pin hành vi hiện tại bằng test (ví dụ `tests/app_test/integration/test_di_resolution_characterization.py` pin DI graph). Refactor xong mà test đó đổi kết quả nghĩa là hành vi đã đổi.
- **Snapshot baseline** trong `tests/baseline/`: `openapi_app_snapshot.json` và `route_inventory_app_snapshot.json` pin public API. Một thay đổi API có chủ đích thì regenerate bằng `BASELINE_UPDATE=1` khi chạy test snapshot tương ứng, rồi review diff của file snapshot trong cùng commit. Không bao giờ set `BASELINE_UPDATE` chỉ để làm test xanh.
- **testcontainers:** test integration cần MongoDB hoặc Redis thật dùng `testcontainers` (`MongoDbContainer`, `RedisContainer`), xem `tests/app_test/conftest.py`. Không mock database khi hành vi cần kiểm tra nằm ở query hay index.
- Cấu trúc test bám theo package: `tests/core_test/`, `tests/engine_test/`, `tests/backtest_test/`, `tests/app_test/`, `tests/scripts/`.

## Quality gate

Một thay đổi chỉ xong khi tất cả các lệnh sau xanh; CI job `tests` trong `.github/workflows/cicd.yml` chạy lại import contracts, metric ratchet và pytest:

| Check | Lệnh |
|---|---|
| Tests | `just test` |
| Lint | `uv run ruff check` |
| Type check | `uv run pyright` (scope trong `pyrightconfig.json`) |
| Import contracts | `uv run lint-imports` → `Contracts: 3 kept, 0 broken.` |
| Metric ratchet | `uv run python scripts/code_metrics.py --ratchet` |

- **3 import-linter contracts** (`[tool.importlinter]` trong `pyproject.toml`): layered `app → backtest → engine → core`, `core.domain` không import `core.infra`, và `fastapi` chỉ có trong `app`.
- **Metric ratchet:** `scripts/code_metrics.py` đo `tiny_share` (tỉ lệ hàm có thân ≤ 2 statement) và `delegations` (hàm chỉ gồm một `return`/expression gọi một attribute); định nghĩa chính xác nằm trong docstring của script. `--ratchet` so với ceiling `max_tiny_share` và `max_delegations` trong `[tool.code-metrics]` của `pyproject.toml` và exit 1 nếu metric nào vượt.
- Ceiling chỉ đi xuống. Nâng ceiling là quyết định của user, không bao giờ là cách để làm CI xanh. Khi ratchet chặn một thay đổi, sửa bằng cách tái cấu trúc (ví dụ inline wrapper mỏng), không inline code chỉ để đẩy con số.
- Tiny share ≤ 30% và delegations ≤ 20 là aspiration, không phải gate.

## Configuration & Secrets

Never hardcode. Use `.env` (local) and environment variables (prod). Never commit `.env` or secrets. Define in `src/pocketquant/core/config.py::Settings` with Pydantic.
