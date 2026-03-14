# Architecture Visual Map

**Last Updated:** 2026-03-14 | **Purpose:** Living visual reference for codebase navigation

## 1. Layer Map — What Lives Where

```mermaid
graph TB
    subgraph HTTP["HTTP Layer"]
        Routes["FastAPI Routes<br/><code>src/features/*/route.py</code>"]
    end

    subgraph CQRS["CQRS Layer"]
        Commands["Commands/Queries<br/><code>src/features/*/command.py|query.py</code>"]
        Mediator["Mediator<br/><code>src/common/mediator/</code>"]
        Handlers["27 Handlers<br/><code>src/features/*/handler.py</code>"]
    end

    subgraph APP["Application Layer — Orchestrators"]
        StrategyAppService["StrategyAppService<br/><code>src/application/strategy/</code>"]
        OrderAppService["OrderAppService<br/><code>src/application/trading/</code>"]
        PositionAppService["PositionAppService<br/><code>src/application/trading/</code>"]
        QuoteAppService["QuoteAppService<br/><code>src/application/market_data/</code>"]
        BarAppService["BarAppService<br/><code>src/application/market_data/</code>"]
        BacktestAppService["BacktestAppService<br/><code>src/application/backtesting/</code>"]
    end

    subgraph DOMAIN["Domain Layer — Pure Logic, No I/O"]
        Aggregates["Aggregates<br/>Order, Position, OHLCV, Quote"]
        ValueObjects["Value Objects<br/>Symbol, Interval, Price"]
        DomainEvents["Domain Events<br/>OrderFilled, BarCompleted"]
        Strategies["IStrategy<br/>MACrossover, etc."]
    end

    subgraph INFRA["Infrastructure Layer — External I/O"]
        Brokers["Brokers<br/>PaperBroker, OKXBroker"]
        TVClient["TradingViewClient<br/>(data source)"]
        TVWebSocket["TradingViewWebSocket<br/>(real-time feed)"]
        Scheduler["JobScheduler<br/>(APScheduler)"]
    end

    subgraph PERSIST["Persistence Layer"]
        DB["Database<br/>(MongoDB)"]
        Cache["Cache<br/>(Redis)"]
        Repos["7 Repositories<br/>OHLCV, Order, Position, ..."]
    end

    subgraph DI["DI Wiring — src/di/"]
        CoreP["CoreProvider"]
        PersistP["PersistenceProvider"]
        InfraP["InfrastructureProvider"]
        MktP["MarketDataProvider"]
        TradingP["TradingProvider"]
        HandlerP["HandlerProvider"]
    end

    Routes --> Commands --> Mediator --> Handlers
    Handlers --> APP
    APP --> DOMAIN
    APP --> INFRA
    APP --> PERSIST
    INFRA --> DB
    INFRA --> Cache
    Repos --> DB

    DI -.->|"wires"| APP
    DI -.->|"wires"| INFRA
    DI -.->|"wires"| PERSIST
    DI -.->|"wires"| Handlers
```

## 2. Request Flow — POST /strategies/load

```mermaid
sequenceDiagram
    participant Client
    participant Route as route.py
    participant Dishka as DishkaRoute
    participant Med as Mediator
    participant Handler as LoadStrategyHandler
    participant Engine as StrategyAppService
    participant Broker as BrokerFactory

    Client->>Route: POST /strategies/load {path: "ma.yaml"}
    Route->>Dishka: resolve FromDishka[Mediator]
    Dishka-->>Route: Mediator singleton
    Route->>Route: StrategyLoader.load(path)
    Route->>Med: send(LoadStrategyCommand)
    Med->>Med: lookup handler by type
    Med->>Handler: handle(command)
    Handler->>Engine: load_strategy(config)
    Engine->>Broker: create_broker(config)
    Broker-->>Engine: PaperBroker instance
    Engine-->>Handler: strategy_id
    Handler-->>Med: strategy_id
    Med-->>Route: strategy_id
    Route-->>Client: {strategy_id, status: "loaded"}
```

## 3. DI Resolution Graph — What Depends on What

```mermaid
graph LR
    subgraph CoreProvider
        Settings
        EventBus
        Mediator
    end

    subgraph PersistenceProvider
        Database
        Cache
        OHLCVRepo["OHLCVRepository"]
        OrderRepo["OrderRepository"]
        PositionRepo["PositionRepository"]
        BacktestRepo["BacktestRepository"]
        SymbolRepo["SymbolRepository"]
        SyncRepo["SyncStatusRepository"]
        OptRepo["OptimizationRepository"]
    end

    subgraph InfrastructureProvider
        JobScheduler
        TVProvider["TradingViewClient"]
        BrokerFactory
        RiskHandler["RiskCheckHandler"]
        HealthCoord["HealthCoordinator"]
    end

    subgraph MarketDataProvider
        BarAppService
        QuoteAppService
    end

    subgraph TradingProvider
        OrderAppService
        PositionAppService
        StrategyAppService
    end

    Settings --> Database
    Settings --> Cache
    Settings --> JobScheduler
    Settings --> TVProvider
    Settings --> QuoteAppService
    Settings --> StrategyAppService

    Database --> OHLCVRepo
    Database --> OrderRepo
    Database --> PositionRepo
    Database --> BacktestRepo
    Database --> SymbolRepo
    Database --> SyncRepo
    Database --> OptRepo

    Cache --> BarAppService
    OHLCVRepo --> BarAppService

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
    RiskHandler --> StrategyAppService
```

## 4. Real-Time Data Flow — WebSocket → Strategy

```mermaid
flowchart LR
    TV["TradingView<br/>WebSocket"] -->|binary frames| TVWS["TradingViewWebSocket<br/>(parse)"]
    TVWS -->|QuoteTick| QS["QuoteAppService"]
    QS -->|tick| Redis["Redis<br/>(latest quote)"]
    QS -->|tick| BM["BarAppService"]
    BM -->|build bar| BM
    BM -->|bar complete| Mongo["MongoDB<br/>(persist bar)"]
    BM -->|BarCompletedEvent| EB["EventBus"]
    QS -->|QuoteReceivedEvent| EB
    EB -->|on_bar| SE["StrategyAppService"]
    SE -->|signal| Risk["RiskCheckHandler"]
    Risk -->|approved| SE
    SE -->|submit order| Broker["IBroker<br/>(Paper/OKX)"]
    Broker -->|fill| OM["OrderAppService"]
    OM -->|OrderFilledEvent| EB
    EB -->|on_fill| PT["PositionAppService"]
    PT -->|save| Mongo
```

## 5. Naming Glossary

| Suffix | Layer | Purpose | Count |
|--------|-------|---------|-------|
| `AppService` | Application | Stateful orchestrator | 8 |
| `Client` | Infrastructure | External service caller | 2 |
| `Handler` | Features | CQRS command/query handler | 27 |
| `Repository` | Persistence | Data access | 7 |
| `Factory` | Infrastructure | Object creation | 1 |
| `Provider` | DI | Dishka dependency provider | 6 |

## 6. File Navigation Cheat Sheet

**"I need to..."**

| Task | Go to |
|------|-------|
| Add a new API endpoint | `src/features/{domain}/{operation}/route.py` |
| Add business logic for that endpoint | `src/features/{domain}/{operation}/handler.py` |
| Define the request shape | `src/features/{domain}/{operation}/command.py` or `query.py` |
| Wire the handler into DI | `src/di/handlers.py` |
| Add a new application service | `src/application/{domain}/` |
| Wire that service into DI | `src/di/{domain}_provider.py` |
| Add a new repository | `src/persistence/repositories/` + wire in `src/di/persistence.py` |
| Add a domain model | `src/domain/{domain}/` |
| Add a domain event | `src/domain/{domain}/{domain}_event.py` |
| Change startup/shutdown | `src/main.py` (lifespan) |
| Change DI container | `src/container.py` |
| Add middleware | `src/common/middleware/` + `src/main_extensions.py` |
