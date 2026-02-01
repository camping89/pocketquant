# Pytest Testing Guide for C# Developers

## Quick Comparison

| C# (xUnit/NUnit) | Python (Pytest) |
|------------------|-----------------|
| `[Fact]` | `def test_*():` |
| `[Theory]` | `@pytest.mark.parametrize` |
| `Assert.Equal(a, b)` | `assert a == b` |
| `[SetUp]` | `@pytest.fixture` |
| `Mock<T>` | `unittest.mock.Mock` |
| `async Task Test()` | `async def test_():` + `pytest-asyncio` |

## Basic Test Structure

### C# xUnit

```csharp
public class OrderTests {
    [Fact]
    public void CreateOrder_WithValidData_ReturnsOrder() {
        var order = new Order("AAPL", 100);
        Assert.Equal("AAPL", order.Symbol);
        Assert.Equal(100, order.Quantity);
    }
}
```

### Python Pytest

```python
# tests/test_order.py

def test_create_order_with_valid_data_returns_order():
    order = Order(symbol="AAPL", quantity=100)
    assert order.symbol == "AAPL"
    assert order.quantity == 100
```

## Assertions

```python
# Equality
assert result == expected
assert result != unexpected

# Truthiness
assert value is True
assert value is False
assert value is None
assert value is not None

# Collections
assert item in collection
assert len(collection) == 3
assert collection == [1, 2, 3]

# Exceptions
with pytest.raises(ValueError):
    parse_number("not a number")

with pytest.raises(ValueError, match="must be positive"):
    Order(quantity=-1)

# Approximate (for floats)
assert result == pytest.approx(3.14, rel=0.01)
```

## Fixtures (Setup/Teardown)

### C# Constructor Injection

```csharp
public class OrderTests : IDisposable {
    private readonly Database _db;

    public OrderTests() {
        _db = new Database();  // Setup
    }

    public void Dispose() {
        _db.Close();  // Teardown
    }
}
```

### Python Fixtures

```python
import pytest

@pytest.fixture
def database():
    """Setup and teardown database."""
    db = Database()
    db.connect()
    yield db  # Test runs here
    db.disconnect()  # Teardown


def test_save_order(database):  # Fixture injected by name
    order = Order(symbol="AAPL")
    database.save(order)
    assert database.get(order.id) == order
```

### Fixture Scopes

```python
@pytest.fixture(scope="function")  # Default - per test
def per_test_fixture():
    ...

@pytest.fixture(scope="class")  # Per test class
def per_class_fixture():
    ...

@pytest.fixture(scope="module")  # Per test file
def per_module_fixture():
    ...

@pytest.fixture(scope="session")  # Entire test run
def per_session_fixture():
    ...
```

## Async Tests

```python
import pytest

# Mark entire module as async
pytestmark = pytest.mark.asyncio

async def test_fetch_data():
    result = await api.fetch("AAPL")
    assert result.symbol == "AAPL"


@pytest.fixture
async def async_database():
    db = AsyncDatabase()
    await db.connect()
    yield db
    await db.disconnect()


async def test_save_async(async_database):
    await async_database.save(Order())
```

## Parameterized Tests

### C# Theory

```csharp
[Theory]
[InlineData("AAPL", 100, true)]
[InlineData("", 100, false)]
[InlineData("AAPL", -1, false)]
public void ValidateOrder_ReturnsExpected(
    string symbol, int qty, bool expected
) {
    var result = Order.Validate(symbol, qty);
    Assert.Equal(expected, result);
}
```

### Python Parametrize

```python
@pytest.mark.parametrize("symbol,quantity,expected", [
    ("AAPL", 100, True),
    ("", 100, False),
    ("AAPL", -1, False),
])
def test_validate_order_returns_expected(symbol, quantity, expected):
    result = Order.validate(symbol, quantity)
    assert result == expected
```

### Multiple Parameters

```python
@pytest.mark.parametrize("symbol", ["AAPL", "GOOGL", "MSFT"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_order_combinations(symbol, side):
    # Tests: AAPL+BUY, AAPL+SELL, GOOGL+BUY, GOOGL+SELL, etc.
    order = Order(symbol=symbol, side=side)
    assert order.is_valid()
```

## Mocking

### Basic Mock

```python
from unittest.mock import Mock, AsyncMock, patch

def test_handler_calls_repository():
    # Create mock
    repo = Mock()
    repo.save.return_value = True

    # Inject mock
    handler = OrderHandler(repository=repo)
    handler.handle(Order())

    # Verify
    repo.save.assert_called_once()
```

### Async Mock

```python
async def test_async_handler():
    repo = AsyncMock()
    repo.save.return_value = True

    handler = OrderHandler(repository=repo)
    await handler.handle(Order())

    repo.save.assert_awaited_once()
```

### Patching

```python
from unittest.mock import patch

def test_with_patched_dependency():
    with patch("src.features.order.handler.Database") as mock_db:
        mock_db.get_collection.return_value = Mock()

        handler = OrderHandler()
        handler.handle(Order())

        mock_db.get_collection.assert_called_with("orders")


# Decorator style
@patch("src.features.order.handler.Database")
def test_with_decorator(mock_db):
    mock_db.get_collection.return_value = Mock()
    # ...
```

### Mock Assertions

```python
mock = Mock()

# Call tracking
mock.method("arg1", key="value")

mock.method.assert_called()
mock.method.assert_called_once()
mock.method.assert_called_with("arg1", key="value")
mock.method.assert_not_called()

# Call count
assert mock.method.call_count == 1

# Call args
args, kwargs = mock.method.call_args
assert args == ("arg1",)
assert kwargs == {"key": "value"}
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Fast, isolated tests
│   ├── test_order.py
│   └── test_handler.py
├── integration/             # Tests with real dependencies
│   ├── test_database.py
│   └── test_api.py
└── e2e/                     # End-to-end tests
    └── test_workflow.py
```

### conftest.py

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_order():
    """Shared fixture available to all tests."""
    return Order(symbol="AAPL", quantity=100, price=150.0)


@pytest.fixture
def mock_event_bus():
    return Mock(spec=EventBus)
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific file
pytest tests/unit/test_order.py

# Run specific test
pytest tests/unit/test_order.py::test_create_order

# Run with pattern
pytest -k "order"  # Tests containing "order"

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Show print statements
pytest -s

# Run async tests
pytest --asyncio-mode=auto

# Coverage
pytest --cov=src --cov-report=html
```

## Markers

```python
import pytest

@pytest.mark.slow
def test_large_dataset():
    ...

@pytest.mark.integration
def test_database_connection():
    ...

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    ...

@pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
def test_unix_specific():
    ...

@pytest.mark.xfail(reason="Known bug #123")
def test_known_failure():
    ...
```

```bash
# Run only slow tests
pytest -m slow

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

## Testing Patterns in PocketQuant

### Testing Handlers

```python
# tests/unit/features/test_sync_handler.py

import pytest
from unittest.mock import AsyncMock, Mock

@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.fetch.return_value = [Bar(...), Bar(...)]
    return provider

@pytest.fixture
def mock_repository():
    return AsyncMock()

@pytest.fixture
def handler(mock_provider, mock_repository):
    return SyncSymbolHandler(
        provider=mock_provider,
        repository=mock_repository,
    )


async def test_sync_fetches_from_provider(handler, mock_provider):
    command = SyncSymbolCommand(symbol="AAPL", exchange="NASDAQ")

    await handler.handle(command)

    mock_provider.fetch.assert_awaited_once_with("AAPL", "NASDAQ")


async def test_sync_saves_to_repository(handler, mock_repository):
    command = SyncSymbolCommand(symbol="AAPL", exchange="NASDAQ")

    await handler.handle(command)

    mock_repository.save_many.assert_awaited_once()
```

### Testing Domain Events

```python
async def test_order_fill_publishes_event():
    event_bus = Mock(spec=EventBus)
    event_bus.publish = AsyncMock()

    manager = OrderManager(event_bus=event_bus)
    await manager.on_fill(Order(id="123", price=150.0))

    event_bus.publish.assert_awaited_once()
    event = event_bus.publish.call_args[0][0]
    assert isinstance(event, OrderFilledEvent)
    assert event.order_id == "123"
```

### Testing with Database

```python
@pytest.fixture(scope="module")
async def test_db():
    """Use test database for integration tests."""
    settings = Settings(mongodb_database="test_db")
    await Database.connect(settings)
    yield Database.get_database()
    await Database.disconnect()


async def test_save_and_retrieve(test_db):
    repo = OrderRepository()

    order = Order(symbol="AAPL", quantity=100)
    await repo.save(order)

    retrieved = await repo.get_by_id(order.id)
    assert retrieved == order
```

## Common Gotchas

### 1. Fixture Not Found

```python
# ❌ Error: fixture 'database' not found
def test_something(database):  # Wrong fixture name
    ...

# ✅ Fix: Check conftest.py for fixture name
def test_something(db):  # Correct name from conftest
    ...
```

### 2. Async Test Not Awaited

```python
# ❌ Error: coroutine never awaited
def test_async():
    result = async_function()  # Missing await
    assert result == expected

# ✅ Fix: Use async def and await
async def test_async():
    result = await async_function()
    assert result == expected
```

### 3. Mock Return Value

```python
# ❌ Error: Mock returns Mock, not expected value
mock = Mock()
result = mock.method()  # Returns <Mock>

# ✅ Fix: Set return_value
mock.method.return_value = expected_value
result = mock.method()  # Returns expected_value
```
