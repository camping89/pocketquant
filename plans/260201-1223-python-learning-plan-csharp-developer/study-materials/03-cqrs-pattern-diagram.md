# CQRS Pattern in PocketQuant

## Request Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  POST /api/v1/market-data/sync                          │    │
│  │  Body: { "symbol": "AAPL", "exchange": "NASDAQ" }       │    │
│  └──────────────────────────┬──────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ROUTER (FastAPI)                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  @router.post("/sync")                                  │    │
│  │  async def sync(request: SyncRequest):                  │    │
│  │      command = SyncSymbolCommand(                       │    │
│  │          symbol=request.symbol,                         │    │
│  │          exchange=request.exchange                      │    │
│  │      )                                                  │    │
│  │      return await mediator.send(command)  ───────────┐ │    │
│  └──────────────────────────────────────────────────────┼─┘    │
└─────────────────────────────────────────────────────────┼───────┘
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MEDIATOR                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  class Mediator:                                        │    │
│  │      _handlers: dict[type, Handler] = {}                │    │
│  │                                                         │    │
│  │      async def send(self, request):                     │    │
│  │          handler = self._handlers[type(request)]  ←──┐ │    │
│  │          return await handler.handle(request)         │ │    │
│  │                                          │            │ │    │
│  │      def register(self, request_type, handler):       │ │    │
│  │          self._handlers[request_type] = handler  ─────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ type(request) = SyncSymbolCommand
                              │ handler = SyncSymbolHandler
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      HANDLER                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  class SyncSymbolHandler(Handler[SyncSymbolCommand,     │    │
│  │                                   SyncResult]):         │    │
│  │                                                         │    │
│  │      async def handle(self, request) -> SyncResult:     │    │
│  │          # 1. Fetch from provider                       │    │
│  │          bars = await provider.fetch(request.symbol)    │    │
│  │                                                         │    │
│  │          # 2. Execute domain logic                      │    │
│  │          validated = self._validate(bars)               │    │
│  │                                                         │    │
│  │          # 3. Persist to database                       │    │
│  │          await repository.save_many(validated)          │    │
│  │                                                         │    │
│  │          # 4. Publish events                            │    │
│  │          await event_bus.publish(DataSyncedEvent(...))  │    │
│  │                                                         │    │
│  │          # 5. Return DTO                                │    │
│  │          return SyncResult(symbol=..., bars_count=...)  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Handler Registration (main.py)

```
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION STARTUP                           │
│                                                                  │
│  # main.py - lifespan context manager                           │
│                                                                  │
│  async with lifespan(app):                                      │
│      # Create mediator                                          │
│      mediator = Mediator()                                      │
│                                                                  │
│      # Register handlers ─────────────────────────────────┐     │
│      mediator.register(                                   │     │
│          SyncSymbolCommand,        ← Request Type         │     │
│          SyncSymbolHandler(...)    ← Handler Instance     │     │
│      )                                                    │     │
│                                                           │     │
│      mediator.register(                                   │     │
│          GetOHLCVQuery,                                   │     │
│          GetOHLCVHandler(...)                             │     │
│      )                                                    │     │
│                                                           │     │
│      # Internal registry after registration:              │     │
│      # ┌────────────────────────────────────────────┐    │     │
│      # │ _handlers = {                              │    │     │
│      # │   SyncSymbolCommand: SyncSymbolHandler,    │◄───┘     │
│      # │   GetOHLCVQuery: GetOHLCVHandler,          │          │
│      # │   LoadStrategyCommand: LoadStrategyHandler │          │
│      # │ }                                          │          │
│      # └────────────────────────────────────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## C# MediatR vs Python Comparison

```
┌──────────────────────────────────┬──────────────────────────────────┐
│           C# MediatR             │        Python PocketQuant         │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Request                      │  # Command                        │
│  public record SyncCommand(      │  @dataclass                       │
│      string Symbol               │  class SyncSymbolCommand:         │
│  ) : IRequest<SyncResult>;       │      symbol: str                  │
│                                  │      exchange: str                │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Handler                      │  # Handler                        │
│  public class SyncHandler        │  class SyncSymbolHandler(         │
│    : IRequestHandler<            │      Handler[SyncSymbolCommand,   │
│        SyncCommand,              │              SyncResult]          │
│        SyncResult>               │  ):                               │
│  {                               │      async def handle(            │
│    public async Task<SyncResult> │          self,                    │
│      Handle(                     │          request: SyncSymbolCommand│
│        SyncCommand request,      │      ) -> SyncResult:             │
│        CancellationToken ct      │          ...                      │
│      ) { ... }                   │                                   │
│  }                               │                                   │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Registration (DI)            │  # Registration (manual)          │
│  services.AddMediatR(cfg =>      │  mediator.register(               │
│    cfg.RegisterServicesFrom      │      SyncSymbolCommand,           │
│      Assembly(...)               │      SyncSymbolHandler(...)       │
│  );                              │  )                                │
│                                  │                                   │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                   │
│  // Usage                        │  # Usage                          │
│  var result = await              │  result = await mediator.send(    │
│    _mediator.Send(               │      SyncSymbolCommand(           │
│      new SyncCommand("AAPL")     │          symbol="AAPL",           │
│    );                            │          exchange="NASDAQ"        │
│                                  │      )                            │
│                                  │  )                                │
│                                  │                                   │
└──────────────────────────────────┴──────────────────────────────────┘
```

## File Locations

```
src/
├── common/
│   └── mediator/
│       ├── __init__.py          # Re-exports
│       ├── mediator.py          # Mediator class (37 lines)
│       │   └── send(request)    # Routes to handler
│       │   └── register(type, handler)
│       └── handler.py           # Handler base class (17 lines)
│           └── Handler[TReq, TRes]
│
├── features/
│   └── market_data/
│       ├── sync/
│       │   ├── command.py       # SyncSymbolCommand
│       │   ├── dto.py           # SyncResult
│       │   └── handler.py       # SyncSymbolHandler
│       │
│       └── ohlcv/
│           ├── query.py         # GetOHLCVQuery
│           ├── dto.py           # OHLCVResult
│           └── handler.py       # GetOHLCVHandler
│
└── main.py                      # Handler registration (lines 119-123)
```

## Why CQRS?

```
┌─────────────────────────────────────────────────────────────────┐
│  WITHOUT CQRS (Direct Service Call)                             │
│                                                                  │
│  ❌ Tight coupling                                              │
│  ❌ Hard to test (need full service)                            │
│  ❌ Logic scattered                                             │
│                                                                  │
│  @router.post("/sync")                                          │
│  async def sync(request):                                       │
│      service = MarketDataService()  # Creates dependencies      │
│      data = await provider.fetch()  # Direct provider call      │
│      await db.insert(data)          # Direct DB call            │
│      await cache.invalidate()       # Direct cache call         │
│      await notify.send()            # Direct notification       │
│      return {"status": "ok"}        # Logic in route!           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  WITH CQRS (Mediator Pattern)                                   │
│                                                                  │
│  ✅ Loose coupling (route doesn't know handler internals)       │
│  ✅ Easy to test (mock mediator, test handler in isolation)     │
│  ✅ Single responsibility (handler does ONE thing)              │
│  ✅ Extensible (add handlers without changing routes)           │
│                                                                  │
│  @router.post("/sync")                                          │
│  async def sync(request):                                       │
│      command = SyncSymbolCommand(...)  # Just create command    │
│      return await mediator.send(command)  # Delegate!           │
│                                                                  │
│  # Handler encapsulates ALL the logic                           │
│  class SyncSymbolHandler:                                       │
│      async def handle(self, command):                           │
│          # All complexity hidden here                           │
│          # Testable in isolation                                │
│          # Single responsibility                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
