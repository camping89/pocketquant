# Dishka Dependency Injection Library Research Report

**Date:** 2026-03-13
**Researcher:** Agent
**Status:** Complete

---

## Executive Summary

Dishka is a lightweight, modern Python dependency injection (DI) framework designed for async-first applications. It emphasizes **clean code** with zero decorators on business logic, **scope-based lifecycle management**, and **automatic constructor injection** via type hints. Ideal for FastAPI, it outperforms many alternatives while remaining minimal and predictable.

**Key Strengths:**
- Auto-resolves constructor dependencies via type hints (no manual wiring)
- Flexible scope management (APP, REQUEST, custom scopes)
- Full async/await support with generator cleanup
- FastAPI integration with middleware-based scope management
- Validation of dependency graph at container creation time
- Framework-agnostic (adaptable to aiohttp, FastStream, etc.)

---

## 1. Core Concepts

### 1.1 Dependency
An object required by another object to function. Example: `Service` needs `Client` → `Client` is the dependency.

### 1.2 Container
The root object that manages dependency retrieval and lifecycle. Key behaviors:
- **Not a factory itself** — delegates creation to providers
- **Caches instances** within their scope until scope exit
- **Accessed via** `.get(Type)` (sync) or `await .get(Type)` (async)
- **Context manager** for nested scope management: `with container() as request_container:`

**Lifecycle:**
```python
# APP scope (root)
container = make_async_container(provider1, provider2)

# REQUEST scope (per-request, nested)
async with container() as request_container:
    service = await request_container.get(Service)
    # Cleanup on exit: finalization in reverse creation order

# Explicit cleanup required
await container.close()
```

### 1.3 Scope
Defines a dependency's **lifespan** within the container hierarchy.

**Standard Hierarchy:** `APP` → `REQUEST` → `ACTION` → `STEP`

**Key Rules:**
- Dependencies are **lazy** — created only when first requested
- **Same scope reuse** — requesting same dependency twice returns cached instance
- **Parent access** — child scopes can access parent-scope objects, but NOT vice versa
- **Scope exit** — clears cache, triggers finalization (reverse creation order)

**Most Common Scopes:**

| Scope | Lifespan | Use Case | Example |
|-------|----------|----------|---------|
| `APP` | Application startup → shutdown | Singletons, config, DB pools | Database connection, config loader |
| `REQUEST` | Per HTTP request | Request-specific state, user context | Request ID, user, session data |
| `SESSION` | WebSocket connection lifetime | Persistent connection state | WebSocket session, stream |

### 1.4 Provider
Configuration object containing **decorated factory methods** that construct dependencies.

**Decorators:**
- `@provide` — factory method (sync or async)
- `alias` — retrieve by different type hint
- `from_context` — manually-supplied context data
- `@decorate` — modify pre-existing dependency

**Two Definition Approaches:**

```python
# Approach 1: Instance-based
provider = Provider(scope=Scope.APP)
provider.provide(get_connection)
provider.provide(DAO)

# Approach 2: Class-based (recommended)
class MyProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_connection(self) -> AsyncIterator[Connection]:
        conn = await create_conn()
        yield conn
        await conn.close()

    @provide(scope=Scope.REQUEST)
    def get_service(self, conn: Connection) -> Service:
        return Service(conn)
```

### 1.5 Dependency Resolution Process

**Flow:**
1. **Call** `container.get(Type)` or `await container.get(Type)`
2. **Look up** registered providers for factories matching `Type`
3. **Resolve dependencies** recursively (topological sort)
4. **Respect scopes** — reuse cached parent-scope deps, create child-scope deps fresh
5. **Cache** result within scope until scope exit
6. **Return** instance

**Scope Enforcement:**
- APP-scoped object **cannot depend on** REQUEST-scoped object (would extend dependency lifetime improperly)
- REQUEST-scoped **can depend on** APP-scoped (parent access allowed)

---

## 2. FastAPI Integration

### 2.1 Setup

**Install:**
```bash
pip install dishka[fastapi]
```

**Basic Setup:**
```python
from fastapi import FastAPI
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka

# 1. Define providers
provider = MyProvider()

# 2. Create container
container = make_async_container(provider)

# 3. Create FastAPI app
app = FastAPI()

# 4. Wire dishka into FastAPI
setup_dishka(container, app)
```

### 2.2 Dependency Injection in Routes

**Pattern 1: Using `@inject` decorator + `FromDishka[]` type hints**
```python
from dishka import FromDishka
from dishka.integrations.fastapi import inject

@app.get("/users")
@inject
async def get_users(service: FromDishka[UserService]) -> list:
    return await service.list_users()
```

**Pattern 2: Using `DishkaRoute` (automatic injection)**
```python
from dishka.integrations.fastapi import DishkaRoute

app.router.route_class = DishkaRoute

@app.get("/users")
async def get_users(service: FromDishka[UserService]) -> list:
    return await service.list_users()
```

### 2.3 Request-Scoped Dependencies

FastAPI integration automatically manages `REQUEST` scope per HTTP request via middleware.

**Access `Request` object in providers:**
```python
class ApiProvider(Provider):
    @provide(scope=Scope.REQUEST)
    async def get_user_context(self, request: Request) -> UserContext:
        user_id = request.headers.get("X-User-ID")
        return UserContext(user_id=user_id)
```

**Lifespan Setup (Recommended):**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with container:
        yield
    # Shutdown
    await container.close()

app = FastAPI(lifespan=lifespan)
setup_dishka(container, app)
```

### 2.4 WebSocket Support

**SESSION scope** for persistent WebSocket connections:

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, service: FromDishka[WsService]):
    # Inject SESSION-scope deps only
    await service.handle(ws)
```

**Accessing REQUEST-scope in WebSocket context:**
```python
async def handle_connection(ws: WebSocket):
    # Manual nested scope for REQUEST-scope access
    async with container() as request_container:
        request_service = await request_container.get(RequestService)
        await request_service.process(ws)
```

---

## 3. Scopes: APP vs REQUEST

### 3.1 APP Scope

**Characteristics:**
- Created at app startup
- Persists for application lifetime
- Single instance shared across all requests
- Cleanup on app shutdown

**Use For:**
- Database connection pools
- Config/settings objects
- External API clients
- Logger instances
- Cached computed data

**Example:**
```python
class Config(Scope.APP):
    api_url: str
    db_uri: str

class DatabasePool(Scope.APP):
    def __init__(self, config: Config):
        self.config = config
        # Pool lifetime = app lifetime
```

### 3.2 REQUEST Scope

**Characteristics:**
- Created per HTTP request
- Discarded after request completes
- Fresh instance per request (no cross-request pollution)
- Automatic cleanup on scope exit

**Use For:**
- Request ID/correlation ID
- Authenticated user info
- Request-specific state
- Temporary caches
- Event aggregators

**Example:**
```python
@provide(scope=Scope.REQUEST)
async def get_request_context(request: Request) -> RequestContext:
    user_id = request.headers.get("X-User-ID")
    req_id = str(uuid4())
    return RequestContext(user_id=user_id, request_id=req_id)

class RequestHandler(Scope.REQUEST):
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx  # Fresh per request
```

### 3.3 Scope Violation Errors

**❌ Invalid (APP depends on REQUEST):**
```python
@provide(scope=Scope.APP)
def singleton_service(user_context: UserContext):  # UserContext is REQUEST
    # ERROR: CycleDependenciesError or GraphMissingFactoryError
    pass
```

**✅ Valid (REQUEST depends on APP):**
```python
@provide(scope=Scope.REQUEST)
def request_handler(pool: DatabasePool, ctx: UserContext):
    # OK: DatabasePool is APP, UserContext is REQUEST
    return RequestHandler(pool, ctx)
```

---

## 4. Provider Patterns

### 4.1 Simple Factory (Sync)
```python
class SimpleProvider(Provider):
    @provide(scope=Scope.APP)
    def get_config(self) -> Config:
        return Config(db_url="sqlite:///db.sqlite")
```

### 4.2 Async Factory with Cleanup
```python
class AsyncProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_connection(self) -> AsyncIterator[Connection]:
        conn = await create_connection()
        yield conn  # Resource is available
        await conn.close()  # Cleanup on scope exit
```

### 4.3 Parameterized Provider
```python
class ParameterizedProvider(Provider):
    def __init__(self, api_url: str):
        super().__init__()
        self.api_url = api_url

    @provide(scope=Scope.APP)
    def get_api_client(self) -> ApiClient:
        return ApiClient(url=self.api_url)

# Usage
provider = ParameterizedProvider(api_url="https://api.example.com")
container = make_async_container(provider)
```

### 4.4 Protocol-Based (Interface Abstraction)
```python
from typing import Protocol

class RepositoryProtocol(Protocol):
    async def get(self, id: int) -> Model: ...

class PostgresRepository(RepositoryProtocol):
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    async def get(self, id: int) -> Model:
        # Query logic
        pass

class DataProvider(Provider):
    @provide(scope=Scope.APP, provides=RepositoryProtocol)
    def get_repository(self, pool: ConnectionPool) -> RepositoryProtocol:
        return PostgresRepository(pool)
```

### 4.5 Alias (Multiple Names for Same Object)
```python
class AliasProvider(Provider):
    @provide(scope=Scope.APP)
    def get_logger(self) -> Logger:
        return Logger()

    @provide(scope=Scope.APP)
    def logger_alias(self, logger: Logger) -> Logger:  # Alias
        return logger

# Both work:
logger1 = await container.get(Logger)
logger2 = await container.get(Logger)  # Same instance
```

### 4.6 From Context (External Data)
```python
class ContextProvider(Provider):
    @from_context
    def get_request_user(self) -> User:
        # Supplied externally, not created here
        pass

# Usage:
async with container(context={User: user_instance}) as request_container:
    service = await request_container.get(Service)
```

---

## 5. Constructor Injection

### 5.1 Core Pattern: Type Hints Auto-Wiring

**Key Feature:** Dishka **auto-resolves** dependencies via `__init__` type hints. **No manual decorator needed on business logic.**

```python
# ✅ Clean business logic (no DI markers)
class UserService:
    def __init__(self, repository: UserRepository, logger: Logger):
        self.repository = repository
        self.logger = logger

    async def get_user(self, id: int) -> User:
        user = await self.repository.get(id)
        self.logger.info(f"Fetched user {id}")
        return user

# Provider just lists the class
class ServiceProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_user_service(self, repo: UserRepository, logger: Logger) -> UserService:
        return UserService(repo, logger)

    # Or even simpler:
    # Just add the class (auto-resolves via __init__ inspection)
    provider.provide(UserService)
```

### 5.2 Automatic Inspection Process

When `@provide` is applied to a class:
1. Dishka inspects the `__init__` signature
2. Reads all parameter type hints
3. Resolves each type from the container
4. Passes resolved instances to `__init__`
5. Caches result for scope duration

### 5.3 Nested Dependencies (Transitive Closure)

```python
class Database:
    async def connect(self) -> None:
        pass

class UserRepository:
    def __init__(self, db: Database):
        self.db = db

class UserService:
    def __init__(self, repo: UserRepository, logger: Logger):
        self.repo = repo
        self.logger = logger

# Single provider declaration:
provider.provide(Database, scope=Scope.APP)
provider.provide(UserRepository, scope=Scope.REQUEST)
provider.provide(UserService, scope=Scope.REQUEST)

# Dishka resolves the chain automatically:
# UserService → UserRepository → Database
```

### 5.4 Handling Multiple Implementations

```python
# Protocol
class CacheBackend(Protocol):
    async def get(self, key: str) -> Any: ...

# Implementations
class RedisCache:
    async def get(self, key: str) -> Any:
        pass

class MemoryCache:
    async def get(self, key: str) -> Any:
        pass

# Provider with explicit interface
class CacheProvider(Provider):
    @provide(scope=Scope.APP, provides=CacheBackend)
    def get_cache(self) -> CacheBackend:
        return RedisCache()  # Swap implementation here

# Consumer (knows nothing about choice)
class CachedService:
    def __init__(self, cache: CacheBackend):
        self.cache = cache  # Depends on interface, not implementation
```

---

## 6. Async Support

### 6.1 Async Factories

```python
class AsyncProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_http_client(self) -> AsyncIterator[AsyncHttpClient]:
        client = AsyncHttpClient()
        await client.connect()
        yield client
        await client.close()

    @provide(scope=Scope.REQUEST)
    async def get_service(self, client: AsyncHttpClient) -> Service:
        # Sync or async, automatically awaited
        return Service(client)
```

### 6.2 Container Types

**For async apps:**
```python
container = make_async_container(provider)

# Usage:
service = await container.get(Service)

async with container() as nested:
    service = await nested.get(Service)
```

**For sync apps (discouraged for new code):**
```python
container = make_container(provider)  # Synchronous

service = container.get(Service)  # No await
```

### 6.3 Generator Cleanup Pattern

```python
@provide(scope=Scope.APP)
async def get_db_connection(config: Config) -> AsyncIterator[Connection]:
    """
    yield pattern ensures cleanup on scope exit.
    """
    conn = await create_async_connection(config.db_url)
    try:
        yield conn  # Available during scope
    finally:
        await conn.close()  # Runs on scope exit
```

**Execution order on exit:** Reverse creation order (LIFO cleanup stack).

---

## 7. Best Practices

### 7.1 ✅ Recommended Patterns

**1. Constructor Injection (Interface-Based)**
```python
# Interface
class Repository(Protocol):
    async def get(self, id: int) -> Model: ...

# Implementation
class PostgresRepository(Repository):
    def __init__(self, pool: ConnectionPool):
        self.pool = pool

# Service (depends on interface, not impl)
class Service:
    def __init__(self, repo: Repository):
        self.repo = repo

# Container
provider.provide(Repository, provides=PostgresRepository)
```

**Why:** Swappable implementations, testable with mocks.

---

**2. Organize Providers by Domain**
```python
class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_connection(self) -> AsyncIterator[Connection]:
        ...

class ServiceProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_user_service(self, conn: Connection) -> UserService:
        ...

class ApiProvider(Provider):
    @provide(scope=Scope.APP)
    def get_http_client(self) -> HttpClient:
        ...

# Combine
container = make_async_container(
    DatabaseProvider(),
    ServiceProvider(),
    ApiProvider()
)
```

**Why:** Separation of concerns, easier to locate factories.

---

**3. Use Components for Multi-Tenant or Multi-Implementation Scenarios**
```python
class MultiDatabaseProvider(Provider):
    @provide(scope=Scope.APP, component="primary")
    async def get_primary_db(self) -> Connection:
        return await connect("postgres://primary")

    @provide(scope=Scope.APP, component="analytics")
    async def get_analytics_db(self) -> Connection:
        return await connect("postgres://analytics")

# Usage:
@provide(scope=Scope.REQUEST)
def get_service(
    primary: Annotated[Connection, FromComponent("primary")],
    analytics: Annotated[Connection, FromComponent("analytics")]
) -> Service:
    return Service(primary, analytics)
```

**Why:** Logical isolation, explicit cross-component dependencies.

---

**4. Scope Awareness in Design**
```python
# DO NOT (violates scope rules):
@provide(scope=Scope.APP)
class AppService:
    def __init__(self, user_context: UserContext):  # REQUEST scope ❌
        pass

# DO (respects scope hierarchy):
@provide(scope=Scope.REQUEST)
class RequestService:
    def __init__(self, pool: ConnectionPool, user: UserContext):
        # Both accessible: APP (pool) and REQUEST (user) ✅
        pass
```

---

**5. Clean Lifespan Management**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with container:  # APP scope
        yield
    # Cleanup (reverse creation order)

app = FastAPI(lifespan=lifespan)
setup_dishka(container, app)
```

---

### 7.2 ❌ Anti-Patterns to Avoid

**1. Service Locator (Container in Business Logic)**
```python
# ❌ WRONG: Business logic knows about container
class UserService:
    def __init__(self, container: Container):
        self.container = container

    async def fetch_user(self, id: int) -> User:
        repo = await self.container.get(Repository)  # Service locator
        return await repo.get(id)

# ✅ RIGHT: Inject dependencies explicitly
class UserService:
    def __init__(self, repo: Repository):
        self.repo = repo

    async def fetch_user(self, id: int) -> User:
        return await self.repo.get(id)
```

**Why:** Hides true dependencies, breaks testability, couples to framework.

---

**2. Static/Global Container**
```python
# ❌ WRONG
_container: Container = None

def set_container(c: Container):
    global _container
    _container = c

def get_service() -> Service:
    return _container.get(Service)  # Global state

# ✅ RIGHT: Use DI to inject container scope
app.state.container = container
# Access via app instance or request context
```

**Why:** Global state is untestable, thread-unsafe, non-reentrant.

---

**3. Scope Violations**
```python
# ❌ WRONG: Storing REQUEST-scope in APP-scope variable
request_users: list = []

@provide(scope=Scope.REQUEST)
def get_user_list() -> list:
    return request_users  # Shared across requests ❌

# ✅ RIGHT: Return fresh per request
@provide(scope=Scope.REQUEST)
def get_user_list() -> list:
    return []  # Fresh per request ✅
```

**Why:** Data pollution across requests, hard-to-debug bugs.

---

**4. Control Freak (Manual Instantiation in Providers)**
```python
# ❌ WRONG: Factory manually creates downstream deps
@provide(scope=Scope.REQUEST)
def get_service() -> Service:
    repo = UserRepository(db=Database())  # Manual! ❌
    return Service(repo)

# ✅ RIGHT: Let DI handle downstream resolution
@provide(scope=Scope.REQUEST)
def get_service(repo: UserRepository) -> Service:
    return Service(repo)  # DI supplies repo ✅
```

**Why:** Breaks dependency graph, misses caching/lifecycle.

---

**5. Mixing Multiple Components in One Provider**
```python
# ⚠️ OKAY but avoid if possible
class MultiProvider(Provider):
    @provide(component="users")
    def get_user_repo(self): ...

    @provide(component="orders")
    def get_order_repo(self): ...

# ✅ BETTER: Separate providers
class UserProvider(Provider):
    @provide(component="users")
    def get_user_repo(self): ...

class OrderProvider(Provider):
    @provide(component="orders")
    def get_order_repo(self): ...
```

**Why:** Clearer intent, easier to locate factories, reduced mental load.

---

## 8. Common Pitfalls & Troubleshooting

### 8.1 Circular Dependencies

**Symptom:** `CycleDependenciesError` at container creation.

**Cause:**
```python
class A:
    def __init__(self, b: B): pass

class B:
    def __init__(self, a: A): pass

provider.provide(A)
provider.provide(B)
# Container creation fails: A → B → A
```

**Solution 1: Refactor (Best)**
```python
class SharedLogic:
    def process(self): pass

class A:
    def __init__(self, logic: SharedLogic): pass

class B:
    def __init__(self, logic: SharedLogic): pass
```

**Solution 2: Two-Phase Initialization**
```python
class A:
    def __init__(self):
        self.b: Optional[B] = None

    def set_b(self, b: B):
        self.b = b

class AFactory(Provider):
    @provide(scope=Scope.APP)
    def get_a(self) -> A:
        a = A()
        b = B(a)
        a.set_b(b)
        return a
```

---

### 8.2 Missing Factory

**Symptom:** `GraphMissingFactoryError` at container creation or `.get()`.

**Cause:**
```python
class Service:
    def __init__(self, unknown_dep: UnknownType): pass

provider.provide(Service)
# No provider for UnknownType
```

**Solution:**
```python
provider.provide(UnknownType)  # Add missing factory
# OR
provider.provide(UnknownType, scope=Scope.APP)
```

---

### 8.3 Implicit Override Detected

**Symptom:** `ImplicitOverrideDetectedError` at container creation.

**Cause:**
```python
provider.provide(Service, factory=ServiceV1)
provider.provide(Service, factory=ServiceV2)  # Two factories, which wins?
```

**Solution:**
```python
# Explicit override
provider.provide(Service, factory=ServiceV1)
provider.provide(Service, factory=ServiceV2, override=True)

# OR use one
provider.provide(Service, factory=ServiceV1)
```

---

### 8.4 Cannot Use Protocol Error

**Symptom:** `CannotUseProtocolError` at container creation.

**Cause:**
```python
class RepositoryProtocol(Protocol):
    async def get(self) -> Model: ...

provider.provide(RepositoryProtocol)  # Protocols can't be instantiated ❌
```

**Solution:**
```python
class ConcreteRepository(RepositoryProtocol):
    async def get(self) -> Model: ...

provider.provide(ConcreteRepository, provides=RepositoryProtocol)
# Now depend on RepositoryProtocol (interface) ✅
```

---

### 8.5 Wrong Scope Assignment

**Symptom:** `GraphMissingFactoryError` or `CycleDependenciesError` on scope mismatch.

**Cause:**
```python
@provide(scope=Scope.APP)  # APP scope
class DatabasePool:
    pass

@provide(scope=Scope.REQUEST)
class Service:
    def __init__(self, pool: DatabasePool, user: UserContext):
        # UserContext is REQUEST scope ✅ OK (child depends on parent)
        # But if DatabasePool depended on UserContext:
        pass
```

**Check:**
- Parent scopes can depend on themselves
- Child scopes can depend on parent scopes
- Parent scopes **cannot** depend on child scopes

---

### 8.6 Validation Errors (Optional Disable)

**By default, dishka validates at container creation.** To disable:

```python
from dishka import ValidationSettings

settings = ValidationSettings(
    nothing_overridden=False,  # Allow implicit overrides
    implicit_override=False,
    nothing_decorated=False
)

container = make_async_container(
    provider,
    validation_settings=settings
)
```

**Not recommended** — validation catches real errors early.

---

## 9. Comparison: Dishka vs Alternatives

| Feature | Dishka | FastAPI `Depends()` | dependency-injector |
|---------|--------|---------------------|-------------------|
| **Constructor injection** | ✅ Auto via type hints | ❌ Route markers only | ✅ Manual config |
| **Scope management** | ✅ Flexible (APP/REQUEST/custom) | ❌ Per-request only | ✅ Custom scopes |
| **Async support** | ✅ Full (factories, cleanup) | ✅ Basic | ✅ Full |
| **Validation** | ✅ Graph checked at startup | ❌ Lazy | ✅ Graph checked |
| **FastAPI integration** | ✅ Clean (middleware) | ✅ Native | ⚠️ Requires adapter |
| **Code markers** | ❌ None on business logic | ✅ `Depends()` everywhere | ⚠️ Config-heavy |
| **Performance** | ✅ Fast (no reflection overhead) | ✅ Fast | ⚠️ Slower (descriptor-heavy) |
| **Learning curve** | ✅ Simple | ✅ Simple | ⚠️ Steep |

---

## 10. Real-World Example: FastAPI Trading Platform

**Scenario:** PocketQuant-style trading app with WebSocket, market data, and user context.

```python
# ============ Providers ============

class ConfigProvider(Provider):
    @provide(scope=Scope.APP)
    def get_config(self) -> Config:
        return Config.from_env()

class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_db_pool(self, config: Config) -> AsyncIterator[AsyncPool]:
        pool = await create_pool(config.db_uri)
        yield pool
        await pool.close()

class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_market_data_client(self, config: Config) -> MarketDataClient:
        return MarketDataClient(config.market_data_api)

    @provide(scope=Scope.REQUEST)
    async def get_user_context(self, request: Request) -> UserContext:
        user_id = request.headers.get("X-User-ID")
        return UserContext(user_id=user_id)

    @provide(scope=Scope.REQUEST)
    async def get_quote_service(
        self,
        client: MarketDataClient,
        pool: AsyncPool
    ) -> QuoteService:
        return QuoteService(client, pool)

# ============ Main App ============

container = make_async_container(
    ConfigProvider(),
    DatabaseProvider(),
    ServiceProvider()
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with container:
        yield

app = FastAPI(lifespan=lifespan)
setup_dishka(container, app)

# ============ Routes ============

@app.get("/quotes/{symbol}")
@inject
async def get_quote(
    symbol: str,
    service: FromDishka[QuoteService]
) -> Quote:
    return await service.fetch_quote(symbol)

@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    async with container() as req_container:
        user: UserContext = await req_container.get(UserContext)
        service: QuoteService = await req_container.get(QuoteService)

        await ws.accept()
        async for quote in service.stream_quotes():
            if quote.user_id == user.user_id:
                await ws.send_json(quote.dict())
```

---

## Unresolved Questions

1. **Thread safety with concurrent scopes:** Does dishka provide built-in `lock_factory` for multi-threaded access to APP-scope objects? Documentation mentions it but lacks examples.

2. **Performance benchmarks:** How does dishka stack up against FastAPI's native `Depends()` under high load (10k+ requests/sec)?

3. **Debugging tools:** Are there dishka-specific debugging/visualization tools for large dependency graphs (50+ providers)?

4. **Migration path:** Official docs on migrating from `dependency-injector` or FastAPI `Depends()` to dishka?

---

## Sources

- [Dishka Documentation](https://dishka.readthedocs.io/en/stable/)
- [GitHub: reagento/dishka](https://github.com/reagento/dishka)
- [FastAPI Integration Documentation](https://dishka.readthedocs.io/en/stable/integrations/fastapi.html)
- [Key Concepts](https://dishka.readthedocs.io/en/stable/concepts.html)
- [Scope Management](https://dishka.readthedocs.io/en/stable/advanced/scopes.html)
- [Provider Reference](https://dishka.readthedocs.io/en/stable/provider/index.html)
- [Container Reference](https://dishka.readthedocs.io/en/stable/container/index.html)
- [Error Handling](https://dishka.readthedocs.io/en/stable/errors.html)
- [Components and Isolation](https://dishka.readthedocs.io/en/stable/advanced/components.html)
- [DI Anti-Patterns](https://lab.abilian.com/Tech/Architecture%20&%20Software%20Design/Dependency%20Inversion/DI%20anti-patterns/)
- [PyPI: dishka](https://pypi.org/project/dishka/)
