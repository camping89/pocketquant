# Structured Logging with Structlog

## Logging Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOG STATEMENT                                 │
│                                                                  │
│  logger.info(                                                   │
│      "order_filled",          ← Event name                      │
│      order_id="123",          ← Structured data                 │
│      symbol="AAPL",                                             │
│      filled_price=150.0                                         │
│  )                                                              │
│                                                                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PROCESSOR PIPELINE                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 1. merge_contextvars                                    │    │
│  │    Add request-scoped context (correlation_id)          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 2. add_log_level                                        │    │
│  │    Add "level": "info"                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 3. add_logger_name                                      │    │
│  │    Add "logger": "src.features.trading.order_manager"   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 4. TimeStamper(fmt="iso")                               │    │
│  │    Add "timestamp": "2025-02-01T12:34:56.789Z"          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 5. add_correlation_id (custom)                          │    │
│  │    Add "correlation_id": "550e8400-e29b-41d4..."        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 6. add_app_context (custom)                             │    │
│  │    Add "service": "pocketquant"                         │    │
│  │    Add "version": "1.0.0"                               │    │
│  │    Add "environment": "production"                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 7. JSONRenderer() or ConsoleRenderer()                  │    │
│  │    Format final output                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FINAL OUTPUT                                  │
│                                                                  │
│  JSON (production):                                             │
│  {                                                              │
│    "event": "order_filled",                                     │
│    "order_id": "123",                                           │
│    "symbol": "AAPL",                                            │
│    "filled_price": 150.0,                                       │
│    "level": "info",                                             │
│    "logger": "src.features.trading.order_manager",              │
│    "timestamp": "2025-02-01T12:34:56.789Z",                     │
│    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",    │
│    "service": "pocketquant",                                    │
│    "version": "1.0.0",                                          │
│    "environment": "production"                                  │
│  }                                                              │
│                                                                  │
│  Console (development):                                         │
│  2025-02-01 12:34:56 [info] order_filled                       │
│      order_id=123 symbol=AAPL filled_price=150.0               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Logger Setup

```python
# src/common/logging/setup.py

def add_correlation_id(logger, method_name, event_dict):
    """Add correlation ID from context."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_app_context(logger, method_name, event_dict):
    """Add application metadata."""
    settings = get_settings()
    event_dict["service"] = settings.app_name.lower().replace(" ", "-")
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structured logging."""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_correlation_id,
        add_app_context,
    ]

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

## C# Serilog Comparison

```
┌──────────────────────────────────┬──────────────────────────────────┐
│           C# Serilog             │        Python Structlog          │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Configuration                │  # Configuration                  │
│  Log.Logger = new                │  structlog.configure(             │
│    LoggerConfiguration()         │      processors=[...],            │
│    .Enrich.WithProperty(         │      wrapper_class=...,           │
│      "Service", "MyApp"          │  )                                │
│    )                             │                                   │
│    .WriteTo.Console(             │  # Processor adds enrichment     │
│      outputTemplate: "..."       │  def add_app_context(l, m, e):   │
│    )                             │      e["service"] = "myapp"       │
│    .WriteTo.File("log.json")     │      return e                     │
│    .CreateLogger();              │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Logging                      │  # Logging                        │
│  _logger.Information(            │  logger.info(                     │
│    "Order filled for {Symbol}    │      "order_filled",              │
│     at {Price}",                 │      symbol="AAPL",               │
│    symbol,                       │      filled_price=150.0           │
│    price                         │  )                                │
│  );                              │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Scoped context               │  # Context variables              │
│  using (LogContext.PushProperty( │  from contextvars import          │
│    "CorrelationId", id           │      ContextVar                   │
│  ))                              │                                   │
│  {                               │  correlation_id: ContextVar =     │
│    // Logs include correlation   │      ContextVar("correlation_id") │
│  }                               │                                   │
│                                  │  correlation_id.set("abc-123")    │
│                                  │  # All logs include correlation   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Output (JSON)                │  # Output (JSON)                  │
│  {                               │  {                                │
│    "@t": "2025-02-01...",        │    "timestamp": "2025-02-01...",  │
│    "@m": "Order filled...",      │    "event": "order_filled",       │
│    "Symbol": "AAPL",             │    "symbol": "AAPL",              │
│    "Price": 150.0                │    "filled_price": 150.0          │
│  }                               │  }                                │
│                                  │                                   │
└──────────────────────────────────┴──────────────────────────────────┘
```

## Usage Patterns

### Basic Logging

```python
from src.common.logging import get_logger

logger = get_logger(__name__)  # Use module name as logger name

# ✅ GOOD: Structured logging with key=value
logger.info("order_filled", order_id="123", symbol="AAPL", price=150.0)

logger.warning("low_balance", account_id="456", balance=100.0, threshold=500.0)

logger.error("order_failed", order_id="789", reason="Insufficient funds")
```

### With Exception

```python
try:
    await broker.submit(order)
except BrokerError as e:
    logger.exception(
        "broker_error",
        order_id=order.id,
        error_type=type(e).__name__,
    )
    raise
```

### Timing Operations

```python
from time import perf_counter

async def handle(self, request):
    start = perf_counter()

    result = await self._process(request)

    duration_ms = int((perf_counter() - start) * 1000)
    logger.info(
        "request_completed",
        request_type=type(request).__name__,
        duration_ms=duration_ms,
    )

    return result
```

## Anti-Patterns to Avoid

```python
# ❌ BAD: String interpolation (not searchable)
logger.info(f"Order {order_id} filled at {price}")

# ❌ BAD: Using print (not structured, not configurable)
print(f"Order filled: {order_id}")

# ❌ BAD: Concatenation (inefficient)
logger.info("Order " + order_id + " filled")

# ❌ BAD: No context (hard to debug)
logger.error("Something went wrong")

# ✅ GOOD: Structured with context
logger.info("order_filled", order_id=order_id, filled_price=price)

logger.error(
    "order_submission_failed",
    order_id=order_id,
    broker="alpaca",
    error_code="INSUFFICIENT_FUNDS",
    account_balance=balance,
)
```

## Log Levels Guide

```
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL      │  USE FOR                                         │
├─────────────┼───────────────────────────────────────────────────┤
│  DEBUG      │  Detailed diagnostic info (disabled in prod)     │
│             │  logger.debug("cache_lookup", key="AAPL:1d")      │
├─────────────┼───────────────────────────────────────────────────┤
│  INFO       │  Normal operations, business events              │
│             │  logger.info("order_filled", order_id="123")      │
├─────────────┼───────────────────────────────────────────────────┤
│  WARNING    │  Unexpected but handled situations               │
│             │  logger.warning("retry_attempt", attempt=3)       │
├─────────────┼───────────────────────────────────────────────────┤
│  ERROR      │  Failures that need attention                    │
│             │  logger.error("db_connection_failed", uri=uri)    │
├─────────────┼───────────────────────────────────────────────────┤
│  CRITICAL   │  System-wide failures, data loss risk            │
│             │  logger.critical("data_corruption_detected")      │
└─────────────┴───────────────────────────────────────────────────┘
```

## File Locations

```
src/
├── common/
│   └── logging/
│       ├── __init__.py          # Re-exports get_logger
│       └── setup.py             # Configuration (78 lines)
│           ├── add_correlation_id()
│           ├── add_app_context()
│           └── configure_logging()
│
└── features/
    └── */
        └── handlers/
            └── *.py             # Usage: logger.info("event", key=val)
```

## Correlation ID for Request Tracing

```python
# Middleware sets correlation ID for each request
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    # Get from header or generate new
    cid = request.headers.get("X-Correlation-ID", str(uuid4()))
    correlation_id.set(cid)

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid

    return response
```

```
Request Flow with Correlation ID:
═════════════════════════════════════════════════════════════════

Request → [Middleware sets cid] → Handler → Repository → Response
              │                      │           │
              ▼                      ▼           ▼
         Log: cid=abc          Log: cid=abc  Log: cid=abc

All logs from same request share correlation_id for tracing!
```
