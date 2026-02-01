# Singleton Pattern & Lifecycle Management

## Database Singleton Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LIFECYCLE                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  STARTUP (lifespan context manager)                             │
│                                                                  │
│  @asynccontextmanager                                           │
│  async def lifespan(app: FastAPI):                              │
│      # 1. Connect singletons                                    │
│      await Database.connect(settings)  ──────┐                  │
│      await Cache.connect(settings)           │                  │
│                                              ▼                  │
│      # Class-level state initialized ─────────────────────┐     │
│      # Database._client = AsyncMongoClient   │            │     │
│      # Database._database = client["mydb"]   │            │     │
│                                              │            │     │
│      yield  # ← App runs here ───────────────┼────────────┤     │
│                                              │            │     │
│      # 2. Disconnect singletons              │            │     │
│      await Database.disconnect()  ◄──────────┘            │     │
│      await Cache.disconnect()                             │     │
│                                                           │     │
└───────────────────────────────────────────────────────────┼─────┘
                                                            │
                                                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  RUNTIME (requests use singleton)                               │
│                                                                  │
│  class SyncSymbolHandler:                                       │
│      async def handle(self, request):                           │
│          # Use singleton - no instantiation!                    │
│          collection = Database.get_collection("ohlcv")          │
│          await collection.insert_many(bars)                     │
│                                                                  │
│  # All requests share same connection pool                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Database Class Structure

```python
# src/infrastructure/persistence/mongodb.py

class Database:
    """Singleton database connection manager."""

    # Class-level state (shared across all "instances")
    _client: AsyncMongoClient | None = None
    _database: AsyncDatabase | None = None

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        """Initialize connection pool at startup."""
        cls._client = AsyncMongoClient(
            settings.mongodb_uri,
            minPoolSize=5,
            maxPoolSize=100,
        )
        cls._database = cls._client[settings.mongodb_database]
        logger.info("database.connected", uri=settings.mongodb_uri)

    @classmethod
    def get_database(cls) -> AsyncDatabase:
        """Get database instance."""
        if cls._database is None:
            raise RuntimeError("Database not connected")
        return cls._database

    @classmethod
    def get_collection(cls, name: str) -> AsyncCollection:
        """Get collection by name."""
        return cls.get_database()[name]

    @classmethod
    async def disconnect(cls) -> None:
        """Close connection pool at shutdown."""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._database = None
            logger.info("database.disconnected")
```

## C# Comparison

```
┌──────────────────────────────────┬──────────────────────────────────┐
│           C# (DI Container)      │        Python (Class State)       │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Registration                 │  # No registration needed         │
│  services.AddSingleton<          │  # Class itself holds state       │
│    IDatabase,                    │                                   │
│    Database                      │  class Database:                  │
│  >(sp => new Database(           │      _client: Client | None = None│
│    connectionString              │      _database: DB | None = None  │
│  ));                             │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Initialization               │  # Explicit initialization        │
│  // Happens lazily on first      │  # Called in lifespan             │
│  // injection                    │                                   │
│  public class Database {         │  @classmethod                     │
│    public Database(string conn)  │  async def connect(cls, settings):│
│    {                             │      cls._client = Client(...)    │
│      _client = new Client(conn); │      cls._database = ...          │
│    }                             │                                   │
│  }                               │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Usage (injected)             │  # Usage (class method)           │
│  public class Handler {          │  class Handler:                   │
│    private readonly IDatabase    │      async def handle(self):      │
│      _db;                        │          coll = Database          │
│                                  │              .get_collection("x") │
│    public Handler(IDatabase db)  │          await coll.find(...)     │
│    {                             │                                   │
│      _db = db;                   │  # No injection needed            │
│    }                             │  # Direct class method call       │
│  }                               │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Cleanup                      │  # Cleanup                        │
│  public class Database           │  @classmethod                     │
│    : IAsyncDisposable            │  async def disconnect(cls):       │
│  {                               │      if cls._client:              │
│    public async ValueTask        │          cls._client.close()      │
│      DisposeAsync()              │          cls._client = None       │
│    {                             │                                   │
│      await _client.CloseAsync(); │                                   │
│    }                             │                                   │
│  }                               │                                   │
│                                  │                                   │
└──────────────────────────────────┴──────────────────────────────────┘
```

## Why @classmethod Instead of Instance Methods?

```
┌─────────────────────────────────────────────────────────────────┐
│  INSTANCE METHODS (what you might expect)                       │
│                                                                  │
│  class Database:                                                │
│      def __init__(self, uri: str):                              │
│          self._client = AsyncMongoClient(uri)                   │
│                                                                  │
│  # Problem: Who creates the instance?                           │
│  # Problem: How do handlers get the same instance?              │
│                                                                  │
│  db1 = Database(uri)  # Instance 1                              │
│  db2 = Database(uri)  # Instance 2 - different connection!     │
│                                                                  │
│  # Need to pass instance everywhere:                            │
│  handler = Handler(db1)                                         │
│  other_handler = OtherHandler(db1)  # Must be same db1!        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  CLASS METHODS (PocketQuant pattern)                            │
│                                                                  │
│  class Database:                                                │
│      _client: Client | None = None  # Shared class state        │
│                                                                  │
│      @classmethod                                               │
│      async def connect(cls, settings):                          │
│          cls._client = AsyncMongoClient(...)                    │
│                                                                  │
│      @classmethod                                               │
│      def get_collection(cls, name: str):                        │
│          return cls._database[name]                             │
│                                                                  │
│  # No instance needed - call on class directly:                 │
│  await Database.connect(settings)                               │
│  collection = Database.get_collection("ohlcv")                  │
│                                                                  │
│  # Every call accesses same class-level state                   │
│  # No injection needed                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Context Manager Pattern

```python
# Alternative: Context manager for scoped lifecycle

@asynccontextmanager
async def get_database(settings: Settings):
    """Async context manager for database lifecycle."""
    await Database.connect(settings)
    try:
        yield Database.get_database()
    finally:
        await Database.disconnect()


# Usage in main.py
async with get_database(settings) as db:
    # db available here
    # Automatically disconnects on exit
```

## Lifespan vs C# IHostedService

```
┌──────────────────────────────────┬──────────────────────────────────┐
│      C# IHostedService           │      Python lifespan             │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  public class DbService          │  @asynccontextmanager             │
│    : IHostedService              │  async def lifespan(app):         │
│  {                               │      # Startup                    │
│    public async Task             │      await Database.connect()     │
│      StartAsync(ct)              │      await Cache.connect()        │
│    {                             │                                   │
│      await _db.ConnectAsync();   │      yield  # App runs            │
│    }                             │                                   │
│                                  │      # Shutdown                   │
│    public async Task             │      await Database.disconnect()  │
│      StopAsync(ct)               │      await Cache.disconnect()     │
│    {                             │                                   │
│      await _db.CloseAsync();     │                                   │
│    }                             │                                   │
│  }                               │                                   │
│                                  │                                   │
│  // Registration                 │  # Registration                   │
│  services.AddHostedService<      │  app = FastAPI(lifespan=lifespan) │
│    DbService                     │                                   │
│  >();                            │                                   │
│                                  │                                   │
└──────────────────────────────────┴──────────────────────────────────┘
```

## Understanding `yield` in Context Manager

```
┌─────────────────────────────────────────────────────────────────┐
│  EXECUTION FLOW                                                 │
│                                                                  │
│  @asynccontextmanager                                           │
│  async def lifespan(app):                                       │
│      print("1. Startup")         ← Runs first                   │
│      await Database.connect()                                   │
│                                                                  │
│      yield                       ← Pauses here                  │
│      # ↑ Control returns to caller                              │
│      # ↑ App runs, handles requests                             │
│      # ↑ Until shutdown signal received                         │
│                                                                  │
│      print("2. Shutdown")        ← Runs on exit                 │
│      await Database.disconnect()                                │
│                                                                  │
│                                                                  │
│  Timeline:                                                      │
│  ═════════════════════════════════════════════════════════════  │
│  [Startup]─────[yield]─────[App Running]─────[Shutdown Signal]  │
│       │           │              │                    │         │
│       │           │              │                    ▼         │
│       │           │              │            [After yield]     │
│       │           │              │                    │         │
│       ▼           ▼              ▼                    ▼         │
│   connect()   returns       requests          disconnect()      │
│                          processed here                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Anti-Patterns to Avoid

```python
# ❌ BAD: Connection at import time
# This runs when module is imported, not at startup!
db = AsyncMongoClient(os.getenv("MONGO_URL"))

# ❌ BAD: Global without lifecycle
class BadDatabase:
    client = AsyncMongoClient(url)  # Connects immediately!
    # No way to properly close

# ❌ BAD: Connection per request
async def get_data():
    client = AsyncMongoClient(url)  # New connection!
    try:
        return await client["db"]["coll"].find_one({})
    finally:
        await client.close()  # Wasted setup/teardown!

# ✅ GOOD: Singleton with explicit lifecycle
class Database:
    _client: AsyncMongoClient | None = None

    @classmethod
    async def connect(cls, settings):
        cls._client = AsyncMongoClient(settings.uri)

    @classmethod
    async def disconnect(cls):
        if cls._client:
            cls._client.close()
```

## File Location

```
src/
├── infrastructure/
│   └── persistence/
│       └── mongodb.py          # Database singleton (64 lines)
│
├── common/
│   └── cache/
│       └── redis_cache.py      # Cache singleton (similar pattern)
│
└── main.py                     # lifespan context manager
                                # Lines 88-233: startup/shutdown
```
