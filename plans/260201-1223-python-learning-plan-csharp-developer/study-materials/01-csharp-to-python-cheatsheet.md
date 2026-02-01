# C# to Python Quick Reference Cheatsheet

> For senior C# developers learning Python through PocketQuant codebase

## Syntax Mapping

| C# | Python | Example |
|----|--------|---------|
| `public class Foo` | `class Foo:` | No access modifiers |
| `private readonly` | `_field` | Prefix underscore convention |
| `async Task<T>` | `async def foo() -> T` | Return type annotation |
| `await Task.Delay(1000)` | `await asyncio.sleep(1)` | Seconds, not ms |
| `var x = new List<int>()` | `x: list[int] = []` | Type hints optional |
| `record Foo(int X)` | `@dataclass class Foo:` | See below |
| `Foo?.Bar ?? default` | `foo.bar if foo else default` | No null-coalescing |
| `nameof(Property)` | `"property"` | No nameof() |
| `throw new Exception()` | `raise Exception()` | raise, not throw |
| `try { } catch { }` | `try: except:` | except, not catch |
| `using (var x = ...)` | `with x as ...:` | Context managers |
| `async using` | `async with` | Async context manager |
| `lock (obj)` | `async with lock:` | asyncio.Lock() |

## Records vs Dataclasses

```csharp
// C# Record
public record SyncCommand(string Symbol, string Exchange);
```

```python
# Python Dataclass
@dataclass
class SyncCommand:
    symbol: str
    exchange: str
```

**Frozen (Immutable):**
```python
@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
```

## Async Patterns

### Task vs Coroutine

```csharp
// C# - returns Task<T>
public async Task<string> FetchAsync() {
    await Task.Delay(100);
    return "data";
}
```

```python
# Python - returns Coroutine (awaitable)
async def fetch() -> str:
    await asyncio.sleep(0.1)
    return "data"
```

### Parallel Execution

```csharp
// C# - parallel tasks
var results = await Task.WhenAll(task1, task2, task3);
```

```python
# Python - gather coroutines
results = await asyncio.gather(coro1, coro2, coro3)
```

### Lock Pattern

```csharp
// C#
private readonly SemaphoreSlim _lock = new(1, 1);
await _lock.WaitAsync();
try { /* work */ }
finally { _lock.Release(); }
```

```python
# Python
self._lock = asyncio.Lock()
async with self._lock:
    # work - auto-released
```

## Dependency Injection

### C# Container

```csharp
services.AddSingleton<IDatabase, Database>();
services.AddScoped<IHandler, Handler>();
```

### Python Manual DI

```python
# Constructor injection
class Handler:
    def __init__(self, database: Database):
        self._db = database

# Singleton pattern (class-level state)
class Database:
    _instance: "Database | None" = None

    @classmethod
    def get_instance(cls) -> "Database":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

## Generics

### C# Generic Interface

```csharp
public interface IHandler<TRequest, TResponse> {
    Task<TResponse> Handle(TRequest request);
}
```

### Python Generic Class

```python
from typing import Generic, TypeVar

TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")

class Handler(ABC, Generic[TRequest, TResponse]):
    @abstractmethod
    async def handle(self, request: TRequest) -> TResponse: ...
```

## LINQ vs Comprehensions

```csharp
// C# LINQ
var names = users.Where(u => u.Active).Select(u => u.Name).ToList();
var lookup = users.ToDictionary(u => u.Id, u => u);
var first = users.FirstOrDefault(u => u.Id == id);
```

```python
# Python comprehensions
names = [u.name for u in users if u.active]
lookup = {u.id: u for u in users}
first = next((u for u in users if u.id == id), None)
```

## Null Handling

```csharp
// C# nullable
string? name = null;
var len = name?.Length ?? 0;
ArgumentNullException.ThrowIfNull(name);
```

```python
# Python None
name: str | None = None
length = len(name) if name else 0
if name is None:
    raise ValueError("name is required")
```

## String Formatting

```csharp
// C# interpolation
$"User {name} has {count} items"
```

```python
# Python f-string (same!)
f"User {name} has {count} items"
```

## Type Annotations

```csharp
public Dictionary<string, List<int>> Data { get; set; }
```

```python
data: dict[str, list[int]]  # Python 3.9+
```

## Common Gotchas

| Issue | C# Behavior | Python Behavior |
|-------|-------------|-----------------|
| Mutable default | Not an issue | `def f(x=[])` SHARED! |
| == vs is | == for equality | `is` for identity, `==` for equality |
| Integer division | 5/2 = 2 | 5/2 = 2.5, use 5//2 for int |
| String immutable | Yes | Yes |
| List copy | `.ToList()` | `list(x)` or `x.copy()` |
| Property | `{ get; set; }` | `@property` decorator |

## File Structure

```
# C# namespace = Python package
# MyApp.Features.Users → src/features/users/

src/
├── common/           # Shared utilities
│   ├── mediator/     # CQRS infrastructure
│   └── logging/      # Structured logging
├── domain/           # Pure business logic
│   ├── order/        # Order aggregate
│   └── shared/       # Value objects, events
├── features/         # Vertical slices
│   └── market_data/  # Commands, queries, handlers
└── infrastructure/   # External dependencies
    └── persistence/  # Database access
```
