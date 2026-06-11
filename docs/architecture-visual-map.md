# Architecture Visual Map

Visual reference for codebase navigation. DDD three-tier structure (top-level, concepts, shared); single Python package with subpackages + Node SPA `pocketquant-web`; command/query services + route modules + 2 SSE streams.

## 1. ASCII Layer Relation Map

```
  ┌──────────────────────────┐
  │     External Clients     │
  │   (REST API / WebSocket) │
  └────────────┬─────────────┘
               │
  ┌────────────┴─────────────────────────────────┐
  │         FastAPI + Middleware Stack            │
  │  CorrelationId → RateLimit → Idempotency     │
  └────────────┬─────────────────────────────────┘
               │
  ╔════════════╧═════════════════════════════════════════════╗
  ║  ROUTES + SERVICES  Command/Query Services              ║
  ║  Routes delegate to services (no business logic)        ║
  ║  Services orchestrate adapters + domain                 ║
  ║  + 2 SSE streams: /bars/stream/{symbol}, /quotes/stream ║
  ╚════════════╤═════════════════════════════════════════════╝
               │
  ┌────────────┴────────────┐
  │  Services (Command/     │
  │   Query Orchestration)  │
  └────────────┬────────────┘
               │
    ┌──────────┼──────────────────────┐
    │          │                      │
    ▼          ▼                      ▼
  ╔═══════════════╗  ╔═══════════════╗  ╔═══════════════════╗
  ║  APPLICATION  ║  ║    DOMAIN     ║  ║    ADAPTERS       ║
  ║ (Orchestrate) ║  ║ (Pure Logic)  ║  ║  (External I/O)   ║
  ║               ║  ║               ║  ║                   ║
  ║ BacktestApp   ║  ║ TOP-LEVEL:    ║  ║ Brokers           ║
  ║ GridOptimize  ║  ║  Bar  Symbol  ║  ║  PaperBroker      ║
  ║ HistReplay    ║  ║  OrderAgg     ║  ║  OKXBroker        ║
  ║ BarApp        ║  ║  PositionAgg  ║  ║ Data Providers    ║
  ║ QuoteApp      ║  ║  SyncStatus   ║  ║ BinanceClient(REST)║
  ║ StrategyApp   ║  ║  BacktestRes  ║  ║ BinanceWebSocket  ║
  ║ OrderApp      ║  ║               ║  ║ Scheduling        ║
  ║ PositionApp   ║  ║ CONCEPTS:     ║  ║  APScheduler      ║
  ║ YamlLoader    ║  ║  Quote (VO)   ║  ║ HTTP Client       ║
  ╚═══════╤═══════╝  ║  Risk (Sizer) ║  ║  (Retry/Backoff) ║
          │          ║  Strategy     ║  ╚═════════╤═════════╝
          │          ║   IStrategy   ║            │
          │          ║   HitNRun2    ║            │
          │          ║               ║            │
          │          ║ SHARED:       ║            │
          │          ║  DomainEvent  ║            │
          │          ║  Interval     ║            │
          │          ║  ValueObjects ║            │
          │          ╚═══════╤═══════╝            │
          │                  │                    │
          └──────────────────┼────────────────────┘
                             │
  ╔══════════════════════════╧════════════════════════════╗
  ║  PERSISTENCE  (core/persistence/)                     ║
  ║  Database(MongoDB)  Cache(Redis)  13 Repositories    ║
  ║  Bar · Order · Position · Backtest* · Optimization    ║
  ║  Symbol · SyncStatus · Subscription · TrackedSymbol   ║
  ║  JobHistory (*: backtest_order, backtest_trade)      ║
  ╚══════════╤══════════════════╤═════════════════════════╝
             │                  │
             ▼                  ▼
       MongoDB:$MONGO_PORT   Redis:$REDIS_PORT

  ╔══════════════════════════════════════════════════════╗
  ║  COMMON  (core/common/)  Cross-Cutting, ALL layers  ║
  ║  EventBus · Middleware(3) · Health(3)              ║
  ║  Logging(structlog) · UUID7 · Constants · Tracing   ║
  ╚══════════════════════════════════════════════════════╝

  DEPENDENCY DIRECTION (strict, unidirectional):
    Features ──► Application ──► Domain ◄── Adapters
                                   ▲
                              Persistence
  Domain has ZERO I/O imports (enforced by AST test)
```

## 2. Strategy Control Plane / Data Plane (Kubernetes-style)

Declarative control via Mongo; reconcile loop converges engine state.

```
Control plane (intent)              Data plane (live engine)
 Mongo: subscription                 RAM: StrategyAppService
  ├─ desired_state: running            ├─ _strategies[sub_id] with is_running
  └─ actual_state: stopped      ◀─────  ├─ _brokers[sub_id]
                                        └─ _configs[sub_id]
         ▲
         │ handlers write
         │ desired_state
      [API]
      /start
      /stop
      /add (desired=stopped)

[reconcile loop every 5s]
  ├─ read desired_state from Mongo
  ├─ compare vs live is_running (RAM)
  ├─ call start_strategy() / stop_strategy() if drift
  └─ write actual_state back to Mongo (only on change)
```

**Key insight:** Handlers are async-eventual (return before engine changes); reconcile loop
provides convergence guarantee. FE polls `actual_state` to observe catch-up. Clean separation
of control (Mongo) from data (RAM).

---

## 3. Domain Three-Tier Structure

```
  src/pocketquant/core/domain/
  │
  ├── TOP-LEVEL (collection-backed, to_mongo/from_mongo)
  │   ├── bar/            Bar entity, BarCompletedEvent✅, OHLCV VO, BarBuilder
  │   ├── order/          OrderAggregate, OrderStatus/Type/Side enums, 5 events
  │   ├── position/       PositionAggregate, PositionSide enum, PnL VO, 3 events
  │   ├── symbol/         Symbol entity (flattened from SymbolAggregate)
  │   ├── sync_status/    SyncStatus entity
  │   └── backtest/       BacktestResult, OptimizationResult entities
  │
  ├── concepts/ (non-persisted logic, no MongoDB collection)
  │   ├── quote/          QuoteTick VO, QuoteReceivedEvent✅
  │   ├── risk/           RiskConfig VO, RiskModel enum, PositionSizer service
  │   └── strategy/       IStrategy interface, Signal VO, Direction enum
  │                        HitNRun2 impl, SignalGeneratedEvent
  │
  └── shared/ (cross-cutting, used by all domain folders)
      ├── events.py       DomainEvent base class
      ├── enums.py        Interval enum (1m..1M)
      └── value_objects.py  Shared VOs (Price, Signal, etc)
```

## 4. Layer Map (Mermaid)

```mermaid
graph TB
    subgraph HTTP["HTTP Layer"]
        Routes["FastAPI Routes<br/><code>*/routes/*.py</code>"]
    end

    subgraph Services["Services Layer"]
        Commands["Commands/Queries<br/><code>*_command_service.py<br/>*_query_service.py</code>"]
        ServiceMethods["Service Methods<br/><code>async def method(cmd: CommandModel)</code>"]
    end

    subgraph APP["Application Layer — Orchestrators"]
        StrategyAppService["StrategyAppService"]
        OrderAppService["OrderAppService"]
        PositionAppService["PositionAppService"]
        QuoteAppService["QuoteAppService"]
        BarAppService["BarAppService"]
        BacktestAppService["BacktestAppService"]
    end

    subgraph DOMAIN["Domain Layer — Pure Logic, No I/O"]
        subgraph TOPLEVEL["Top-Level (collection-backed)"]
            BarEnt["Bar · Symbol · SyncStatus · BacktestResult · Subscription"]
            Aggregates["OrderAggregate · PositionAggregate"]
        end
        subgraph CONCEPTS["Concepts (non-persisted)"]
            QuoteVO["Quote (VO)"]
            RiskSvc["Risk (Sizer)"]
            StrategySvc["Strategy (IStrategy, HitNRun2)"]
        end
        subgraph SHARED["Shared"]
            SharedBase["DomainEvent · Interval · ValueObjects"]
        end
    end

    subgraph ADAPT["Adapter Layer — External I/O"]
        Brokers["Brokers (Paper, OKX)"]
        BinanceClient["BinanceClient (REST)"]
        BinanceWS["BinanceWebSocketClient (@aggTrade)"]
        Scheduler["JobScheduler (APScheduler)"]
    end

    subgraph PERSIST["Persistence Layer (Adapters)"]
        DB["Database (MongoDB)"]
        Cache["Cache (Redis)"]
        Repos["13 Repositories"]
    end

    Routes --> Commands --> ServiceMethods
    ServiceMethods --> APP
    APP --> DOMAIN
    APP --> ADAPT
    APP --> PERSIST
    Repos --> DB
```

## 5. Request Flow — POST /strategies/{strategy_code}/subscriptions

```mermaid
sequenceDiagram
    participant Client
    participant Route as route.py
    participant Dishka as DishkaRoute
    participant Service as StrategyCommandService
    participant Engine as StrategyAppService
    participant Broker as BrokerFactory

    Client->>Route: POST /strategies/{code}/subscriptions {symbol, interval}
    Route->>Dishka: resolve FromDishka[StrategyCommandService]
    Dishka-->>Route: service singleton
    Route->>Service: add_symbol(command)
    Service->>Service: STRATEGY_REGISTRY[strategy_code]
    Service->>Engine: load_strategy(StrategyConfig, strategy_class)
    Engine->>Broker: create_broker(config)
    Broker-->>Engine: PaperBroker instance
    Engine-->>Service: subscription_id
    Service-->>Route: SubscriptionDTO{subscription_id, status}
    Route-->>Client: {subscription_id, status: "created"}
```

## 6. DI Resolution Graph

```mermaid
graph LR
    subgraph CoreProvider
        Settings
        EventBus
    end

    subgraph PersistenceProvider
        Database
        Cache
        BarRepo["BarRepository"]
        OrderRepo["OrderRepository"]
        PositionRepo["PositionRepository"]
        SubRepo["SubscriptionRepository"]
        SymbolRepo["SymbolRepository"]
        SyncRepo["SyncStatusRepository"]
        OptRepo["OptimizationRepository"]
    end

    subgraph InfrastructureProvider
        JobScheduler
        DataProvider["BinanceClient (IDataProvider)"]
        BrokerFactory
        HealthCoord["HealthCoordinator"]
    end

    subgraph MarketDataProvider
        BarAppService
        QuoteAppService
    end

    subgraph ExecutionProvider
        OrderAppService
        PositionAppService
        StrategyAppService
    end

    Settings --> Database
    Settings --> Cache
    Settings --> JobScheduler
    Settings --> DataProvider
    Settings --> QuoteAppService
    Settings --> StrategyAppService

    Database --> BarRepo
    Database --> OrderRepo
    Database --> PositionRepo
    Database --> SubRepo
    Database --> SymbolRepo
    Database --> SyncRepo
    Database --> OptRepo

    Cache --> BarAppService
    BarRepo --> BarAppService
    Settings --> BarAppService
    Cache --> QuoteAppService
    BarAppService --> QuoteAppService

    EventBus --> OrderAppService
    OrderRepo --> OrderAppService

    EventBus --> PositionAppService
    PositionRepo --> PositionAppService

    EventBus --> StrategyAppService
    BrokerFactory --> StrategyAppService
    OrderAppService --> StrategyAppService
    PositionAppService --> StrategyAppService
```

## 7. Real-Time Data Flow — WebSocket to Strategy

```mermaid
flowchart LR
    BN["Binance<br/>@aggTrade WS"] -->|JSON frames| BWS["BinanceWebSocketClient<br/>(parse)"]
    BWS -->|QuoteTick| QS["QuoteAppService"]
    QS -->|tick| Redis["Redis<br/>(latest quote, 60s TTL)"]
    QS -->|tick| BM["BarAppService"]
    BM -->|build bar| BM
    BM -->|bar complete| Mongo["MongoDB bars"]
    BM -->|BarCompletedEvent| EB["EventBus"]
    QS -->|QuoteReceivedEvent| EB
    EB -->|on_bar| SE["StrategyAppService"]
    SE -->|signal| Risk["PositionSizer"]
    Risk -->|sized order| SE
    SE -->|submit order| Broker["IBroker<br/>(Paper/OKX)"]
    Broker -->|fill| OM["OrderAppService"]
    OM -->|OrderFilledEvent| EB
    EB -->|on_fill| PT["PositionAppService"]
    PT -->|save| Mongo
```

## 8. C4 System Context (Level 1)

```
    ┌──────────┐          ┌──────────────────────────────┐
    │  Trader  │─────────>│       PocketQuant            │
    │  (User)  │  REST    │  Algorithmic Trading Platform │
    │          │<─────────│  DDD + Clean Architecture    │
    └──────────┘  JSON    └──────┬───────┬───────┬───────┘
                                 │       │       │
                    ┌────────────┘       │       └────────────┐
                    v                    v                    v
           ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
           │   Binance    │    │     OKX      │    │  Webhook     │
           │ Data Provider│    │   Exchange   │    │  Consumers   │
           │ REST + WS    │    │  REST + WS   │    │  HTTP POST   │
           └──────────────┘    └──────────────┘    └──────────────┘
```

## 9. C4 Container (Level 2)

```
    ┌──────────┐
    │  Trader  │
    └────┬─────┘
         │ HTTP/JSON
         v
┌────────────────────────────────────────────────────────────┐
│                 PocketQuant Platform                        │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          FastAPI Web Server (Uvicorn)                 │  │
│  │  Port 8765 · /api/v1/* · Middleware · Dishka DI      │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                          │                                  │
│     ┌────────────────────┼────────────────────┐             │
│     v                    v                    v             │
│  ┌─────────┐      ┌──────────┐      ┌────────────────┐    │
│  │ Services│      │ Domain   │      │ Background     │    │
│  │ Handlers│─────>│ Engine   │      │ Jobs           │    │
│  │ (37)    │      │ (Pure)   │      │ (APScheduler)  │    │
│  └─────────┘      └──────────┘      └────────────────┘    │
│       │                                     │              │
│       v                                     v              │
│  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐         │
│  │ App     │ │ Broker  │ │ Event  │ │ Data     │         │
│  │Services │ │ Layer   │ │ Bus    │ │ Sync     │         │
│  │ (8 svc) │ │Paper/OKX│ │(in-mem)│ │ Jobs     │         │
│  └─────────┘ └─────────┘ └────────┘ └──────────┘         │
└──────────┬──────────────────────┬─────────────────────────┘
           │                      │
           v                      v
    ┌──────────────┐       ┌──────────────┐
    │   MongoDB    │       │    Redis     │
    │  $MONGO_PORT │       │ $REDIS_PORT  │
    │ 7 collections│       │  TTL cache   │
    │ bars,orders  │       │ quote,bar    │
    │ positions,...│       │ idempot,rate │
    └──────────────┘       └──────────────┘
```

## 10. DI Container Wiring Order

```
  CoreProvider ──> PersistenceProvider ──> InfrastructureProvider
       │                                         │
       v                                         v
  MarketDataProvider ──> ExecutionProvider ──> HandlerProvider

  Container creates all services + registers with routes
```

## 11. Event Flow

```
  Service ──publish──> EventBus ──notify──> Subscribers
                         │
       ┌─────────────────┼─────────────────┐
       v                 v                 v
  BarCompleted      QuoteReceived     OrderFilled
  │                 │                 │
  v                 v                 v
  StrategyApp       BarApp            PositionApp
  .on_bar()         .process_tick()   ._on_fill()
```

> **Naming glossary, file-navigation ("I need to…"), bounded-context table, ubiquitous-language** moved to text homes:
> - Class-naming by layer → [code-standards.md](./code-standards.md) → "Class Naming by Layer"
> - File navigation ("where does X live") → [system-architecture.md](./system-architecture.md) → "Where Does X Live?"
> - Bounded contexts + ubiquitous language → [system-architecture.md](./system-architecture.md)

## 12. Context Map (Bounded-Context Relationships)

```
                                    ┌──────────────┐
                                    │  Backtest    │
                                    │ (replays MD) │
                                    └──────┬───────┘
                                           │ consumes Bar
                                           ▼
┌──────────────┐   BarCompletedEvent ┌──────────────┐    SignalGeneratedEvent  ┌──────────────┐
│ Market Data  │────────────────────▶│  Strategy    │─────────────────────────▶│   Trading    │
│   (Bar)      │                     │  (IStrategy) │                          │ (OrderAgg,   │
└──────┬───────┘                     └──────┬───────┘                          │  PositionAgg)│
       │ Quote (DTO/Redis)                  │ Symbol lookup                    └──────┬───────┘
       │                                    ▼                                          │
       │                            ┌──────────────┐         RiskConfig                │
       │                            │   Symbol     │◀─────────────────────────────────┤
       │                            │   (entity)   │                                   │
       │                            └──────────────┘         ┌──────────────┐          │
       │                                                     │     Risk     │◀─────────┘
       │                                                     │ (PositionSizer)         (pre-trade check)
       │                                                     └──────────────┘
       ▼
   (no upstream)
```

Relationship types (Customer/Supplier, Shared Kernel, Conformist) and the ubiquitous-language glossary live in [system-architecture.md](./system-architecture.md) → "Bounded Contexts" + "Ubiquitous Language".
