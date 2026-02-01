# Python Type Hints for C# Developers

## Quick Reference

| C# Type | Python Type | Notes |
|---------|-------------|-------|
| `string` | `str` | |
| `int` | `int` | Unbounded (no overflow) |
| `float`, `double` | `float` | 64-bit |
| `bool` | `bool` | |
| `void` | `None` | Return type |
| `object` | `object` or `Any` | |
| `string?` | `str \| None` | Union with None |
| `List<T>` | `list[T]` | Lowercase in 3.9+ |
| `Dictionary<K,V>` | `dict[K, V]` | |
| `HashSet<T>` | `set[T]` | |
| `Tuple<A,B>` | `tuple[A, B]` | |
| `Task<T>` | `Coroutine[Any, Any, T]` | Usually just `async def -> T` |
| `Func<T,R>` | `Callable[[T], R]` | |
| `Action<T>` | `Callable[[T], None]` | |

## Type Annotation Syntax

### Variables

```python
# C#: string name = "John";
name: str = "John"

# C#: int? count = null;
count: int | None = None

# C#: List<string> names = new();
names: list[str] = []

# C#: Dictionary<string, int> scores = new();
scores: dict[str, int] = {}
```

### Functions

```python
# C#: public string Greet(string name) => $"Hello {name}";
def greet(name: str) -> str:
    return f"Hello {name}"

# C#: public async Task<User> GetUser(int id)
async def get_user(user_id: int) -> User:
    ...

# C#: public void Process(List<int> items)
def process(items: list[int]) -> None:
    ...
```

### Optional Parameters

```python
# C#: public void Fetch(string symbol, int limit = 100)
def fetch(symbol: str, limit: int = 100) -> None:
    ...

# C#: public void Save(User user, bool? notify = null)
def save(user: User, notify: bool | None = None) -> None:
    ...
```

## Generics

### Generic Class

```csharp
// C#
public class Handler<TRequest, TResponse> {
    public virtual Task<TResponse> Handle(TRequest request);
}
```

```python
# Python
from typing import TypeVar, Generic

TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")

class Handler(Generic[TRequest, TResponse]):
    async def handle(self, request: TRequest) -> TResponse:
        ...
```

### Generic Function

```csharp
// C#
public T First<T>(List<T> items) => items[0];
```

```python
# Python
T = TypeVar("T")

def first(items: list[T]) -> T:
    return items[0]
```

### Bounded Generics

```csharp
// C#
public class Repository<T> where T : Entity { }
```

```python
# Python
T = TypeVar("T", bound=Entity)

class Repository(Generic[T]):
    ...
```

## Union Types

```python
# C#: string | int (not directly supported, use object)
# Python 3.10+ union syntax:
value: str | int = "hello"
value = 42  # Also valid

# Nullable (same as C# string?)
name: str | None = None

# Multiple types
result: str | int | float | None = None
```

## Callable Types

```python
from typing import Callable, Awaitable

# C#: Func<string, int>
parser: Callable[[str], int]

# C#: Func<string, int, bool>
validator: Callable[[str, int], bool]

# C#: Action<string>
logger: Callable[[str], None]

# C#: Func<string, Task<int>>
async_parser: Callable[[str], Awaitable[int]]
```

## Type Aliases

```python
# Simple alias
UserId = str
OrderId = str

# Complex alias
EventHandler = Callable[[DomainEvent], Awaitable[None]]
SymbolMap = dict[str, list[Quote]]

# Usage
def subscribe(handler: EventHandler) -> None:
    ...

def get_quotes() -> SymbolMap:
    ...
```

## Dataclasses with Types

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

@dataclass
class Order:
    # Required fields (no default)
    symbol: str
    quantity: int
    price: float

    # Optional field
    note: str | None = None

    # Default factory for mutable/computed defaults
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)

    # Class variable (not instance field)
    MAX_QUANTITY: int = field(default=10000, init=False)
```

## Abstract Base Classes

```csharp
// C#
public abstract class Service {
    public abstract Task<Result> Execute();
    public virtual void Log() { }  // Optional override
}
```

```python
# Python
from abc import ABC, abstractmethod

class Service(ABC):
    @abstractmethod
    async def execute(self) -> Result:
        """Must be implemented by subclass."""
        ...

    def log(self) -> None:
        """Optional override."""
        pass
```

## Protocol (Structural Typing)

```python
from typing import Protocol

# C#: interface IRepository<T>
class Repository(Protocol[T]):
    async def get(self, id: str) -> T | None: ...
    async def save(self, entity: T) -> None: ...

# Any class with these methods satisfies the protocol
# No explicit "implements" needed (duck typing)
class UserRepository:
    async def get(self, id: str) -> User | None:
        ...
    async def save(self, entity: User) -> None:
        ...

# This works - structural compatibility
def use_repo(repo: Repository[User]) -> None:
    ...

use_repo(UserRepository())  # ✓ Valid
```

## Literal Types

```python
from typing import Literal

# C#: enum Side { Buy, Sell }
Side = Literal["BUY", "SELL"]

def place_order(symbol: str, side: Side, quantity: int) -> None:
    ...

place_order("AAPL", "BUY", 100)   # ✓ Valid
place_order("AAPL", "HOLD", 100)  # ✗ Type error
```

## Type Guards

```python
from typing import TypeGuard

def is_string_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def process(items: list[object]) -> None:
    if is_string_list(items):
        # Type narrowed to list[str]
        for s in items:
            print(s.upper())  # ✓ s is str
```

## Common Patterns in PocketQuant

### Handler Pattern

```python
# src/common/mediator/handler.py

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")

class Handler(ABC, Generic[TRequest, TResponse]):
    @abstractmethod
    async def handle(self, request: TRequest) -> TResponse:
        ...
```

### Event Handler Type

```python
# src/common/messaging/event_handler.py

from typing import Callable, Awaitable, TypeVar

T = TypeVar("T", bound=DomainEvent)

# Async handler
EventHandler = Callable[[T], Awaitable[None]]

# Sync or async handler
EventHandlerAny = Callable[[T], Awaitable[None] | None]
```

### Repository Pattern

```python
# Generic repository with type hints

from typing import Generic, TypeVar

T = TypeVar("T", bound=Entity)

class Repository(Generic[T]):
    async def get_by_id(self, id: str) -> T | None:
        ...

    async def save(self, entity: T) -> None:
        ...

    async def find_all(self) -> list[T]:
        ...
```

## Pyright vs MyPy

PocketQuant uses **Pyright** (via Pylance in VS Code).

```bash
# Check types
pyright src/

# Strict mode in pyproject.toml
[tool.pyright]
typeCheckingMode = "strict"
```

| Feature | Pyright | MyPy |
|---------|---------|------|
| Speed | Fast | Slower |
| IDE | Pylance (VS Code) | Separate |
| Strictness | Configurable | Configurable |
| Generic inference | Better | Good |

## Common Type Errors & Fixes

### Error: Missing return type

```python
# ❌ Error: Function is missing return type annotation
def greet(name):
    return f"Hello {name}"

# ✅ Fix: Add return type
def greet(name: str) -> str:
    return f"Hello {name}"
```

### Error: Incompatible types

```python
# ❌ Error: Cannot assign None to str
name: str = None

# ✅ Fix: Use union type
name: str | None = None
```

### Error: Missing type for list

```python
# ❌ Error: Need type argument for list
items: list = []

# ✅ Fix: Specify element type
items: list[str] = []
```

### Error: Mutable default argument

```python
# ❌ Error: Mutable default (shared across calls!)
def append(item: str, items: list[str] = []) -> list[str]:
    items.append(item)
    return items

# ✅ Fix: Use None default with factory
def append(item: str, items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```
