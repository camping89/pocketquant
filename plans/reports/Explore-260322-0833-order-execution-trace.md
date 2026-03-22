# Complete Order Execution Path Trace — PocketQuant Trading System

**Project:** /Users/admin/workspace/_me/pocketquant (4-package uv monorepo)  
**Date:** 2026-03-22  
**Scope:** Full execution path from user API call to broker fill and position update  

---

## PHASE 1: Strategy Loading

### Route Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/route.py`

```python
@router.post("/load")
async def load_strategy(
    body: LoadStrategyRequest,  # Parameters: path (str)
    mediator: FromDishka[Mediator],
) -> dict
```

**Flow:**
1. User sends: `POST /load` with `{"path": "path/to/strategy.yaml"}`
2. Route extracts `path` from request body
3. Calls `StrategyLoader.load(path)` → returns `StrategyConfig`
4. Sends `LoadStrategyCommand(config=config)` via mediator

**External I/O:**
- Reads YAML file from filesystem

---

### Command Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/handler.py`

```python
@handles(LoadStrategyCommand)
class LoadStrategyHandler(Handler[LoadStrategyCommand, str]):
    async def handle(self, request: LoadStrategyCommand) -> str:
        # Delegates to StrategyAppService
        return await self._strategy_app_service.load_strategy(config)
```

**Parameters:**
- `request.config`: StrategyConfig instance (parsed YAML)

---

### YAML Strategy Loader

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/yaml_strategy_loader.py`

```python
class StrategyLoader:
    @staticmethod
    def load(path: Path) -> StrategyConfig:
        # 1. Check file exists and has .yaml/.yml extension
        # 2. yaml.safe_load(f) → dict
        # 3. StrategyConfig.from_dict(data) → StrategyConfig instance
        # 4. config.validate() → list of errors
        # 5. Returns StrategyConfig
```

**External I/O:**
- File read: `open(path, encoding="utf-8")`
- YAML parse: `yaml.safe_load()`

---

### App Service: Load Strategy

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

```python
async def load_strategy(
    self,
    config: StrategyConfig,
    strategy_class: type[IStrategy] | None = None,
) -> str:
    # 1. Lock acquired (_lock)
    # 2. Check if strategy_id already loaded (raises if duplicate)
    # 3. Create/get broker: broker = await self._get_or_create_broker(config.broker)
    # 4. Create strategy instance: strategy = _DefaultStrategy(config)
    # 5. Store in dicts:
    #    - self._strategies[config.id] = strategy
    #    - self._brokers[config.id] = broker
    #    - self._configs[config.id] = config
    # 6. Return config.id
```

**Key State:**
- `_strategies: dict[str, IStrategy]` — keyed by strategy_id
- `_brokers: dict[str, IBroker]` — keyed by strategy_id
- `_configs: dict[str, StrategyConfig]` — keyed by strategy_id

**Return Value:** Strategy ID (string)

---

## PHASE 2: Strategy Start

### Route Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/start/route.py`

```python
@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: str,
    mediator: FromDishka[Mediator],
) -> dict:
    await mediator.send(StartStrategyCommand(strategy_id=strategy_id))
    return {"strategy_id": strategy_id, "status": "started"}
```

**Parameters:**
- `strategy_id`: loaded strategy identifier

---

### Command Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/start/handler.py`

```python
@handles(StartStrategyCommand)
class StartStrategyHandler(Handler[StartStrategyCommand, bool]):
    async def handle(self, request: StartStrategyCommand) -> bool:
        await self._strategy_app_service.start_strategy(request.strategy_id)
        return True
```

---

### App Service: Start Strategy

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

```python
async def start_strategy(self, strategy_id: str) -> None:
    # 1. Lock acquired
    # 2. Retrieve strategy: strategy = self._strategies[strategy_id]
    # 3. If not running: await strategy.on_start()
    # 4. Get broker: broker = self._brokers[strategy_id]
    # 5. If not connected: await broker.connect()
```

**Broker Connection (OKX):**

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py`

```python
async def connect(self) -> None:
    from okx import Account, Trade
    flag = "1" if self._demo else "0"
    self._trade_api = Trade.TradeAPI(api_key, api_secret, passphrase, flag=flag)
    self._account_api = Account.AccountAPI(api_key, api_secret, passphrase, flag=flag)
    self._connected = True
```

**External I/O:**
- OKX SDK initialization (python-okx package)

---

### Event Handler Registration

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-api/src/pocketquant/api/main.py`

In lifespan `startup`:
```python
await register_handlers(container)  # CQRS handlers
registry = get_event_registry()
registry.register_instance(self, self._event_bus)  # Subscribes to events
```

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/common/messaging/event_registry.py`

```python
def register_instance(self, instance: object, event_bus: EventBus) -> int:
    # Scan instance for methods with @event_handler decorator
    # For each method with _event_types attribute:
    #   event_bus.subscribe(event_type, method)
    # Returns count of registered handlers
```

**StrategyAppService has two handlers:**
1. `@event_handler(BarCompletedEvent)` → `_on_bar_completed()`
2. `@event_handler(QuoteReceivedEvent)` → `_on_quote_received()`

**Subscriptions Made:**
- EventBus.subscribe(BarCompletedEvent, strategy_app_service._on_bar_completed)
- EventBus.subscribe(QuoteReceivedEvent, strategy_app_service._on_quote_received)
- EventBus.subscribe(OrderFilledEvent, position_app_service._on_order_filled)

---

## PHASE 3: Market Data → Bar Completion

### Tick Ingestion

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py`

```python
async def on_quote_update(self, quote_data: dict[str, Any]) -> None:
    # 1. Parse: symbol_key = quote_data.get("symbol_key")  # e.g., "OKX:BTC"
    # 2. Extract: exchange, symbol = symbol_key.split(":", 1)
    # 3. Create Quote object from quote_data fields
    # 4. Cache latest quote: await self._cache.set(cache_key, quote.to_cache_dict(), ttl)
    # 5. Create QuoteTick: tick = QuoteTick(symbol, exchange, timestamp, price, volume)
    # 6. Process tick: await self.bar_manager.add_tick(tick)
```

**External I/O:**
- Redis write: Cache.set() → CACHE_KEY_QUOTE_LATEST

**Parameters:**
- `quote_data`: Dictionary with fields: symbol_key, last_price, bid, ask, volume, timestamp, etc.

---

### Bar Building

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py`

```python
async def add_tick(self, tick: QuoteTick) -> None:
    symbol_key = f"{tick.exchange}:{tick.symbol}".upper()
    # Loop over all configured intervals (1m, 5m, 1h, 1d)
    for interval in self._intervals:
        await self._process_tick_for_interval(tick, symbol_key, interval)

async def _process_tick_for_interval(
    self,
    tick: QuoteTick,
    symbol_key: str,
    interval: Interval,
) -> None:
    # 1. Get current bar: current_bar = self._bars[symbol_key].get(interval)
    # 2. Calculate bar_start: bar_start = get_bar_start(tick.timestamp, interval)
    # 3. If bar is None: Create new BarBuilder
    # 4. Else if bar is complete (tick.timestamp past bar_start):
    #    - await self._save_completed_bar(current_bar)  ← PUBLISHES BarCompletedEvent
    #    - Create new BarBuilder
    # 5. Add tick to current bar: current_bar.add_tick(price, volume, timestamp)
    # 6. Cache current bar: await self._cache_current_bar(symbol_key, interval, bar)
```

**State Maintained:**
- `_bars: dict[str, dict[Interval, BarBuilder]]` — nested per symbol/interval

---

### Bar Completed Event Publishing

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py`

```python
async def _save_completed_bar(self, bar: BarBuilder) -> None:
    # 1. Create domain Bar entity
    domain_bar = Bar(
        symbol=bar.symbol,
        exchange=bar.exchange,
        interval=bar.interval,
        datetime=bar.bar_start,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        tick_count=bar.tick_count,
    )
    
    # 2. Persist to MongoDB
    await self._bar_repo.upsert_bar(domain_bar)
    
    # 3. Create and publish event
    event = BarCompletedEvent(
        symbol=bar.symbol,
        exchange=bar.exchange,
        interval=bar.interval.value,
        bar_start=bar.bar_start,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        tick_count=bar.tick_count,
    )
    await self._event_bus.publish(event)
    
    # 4. Clear Redis cache for this bar
    cache_key = build_bar_cache_key(...)
    await self._cache.delete_pattern(f"{cache_key}:*")
```

**External I/O:**
- MongoDB write: `bar_repository.upsert_bar()`
- EventBus publish: `event_bus.publish(BarCompletedEvent)`
- Redis delete: `cache.delete_pattern()`

**Event Emitted:** `BarCompletedEvent`

---

### Event Bus Publishing

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/common/messaging/event_bus.py`

```python
async def publish(self, event: DomainEvent) -> None:
    # 1. Get handlers: handlers = self._handlers.get(type(event), [])
    # 2. For each handler in handlers (FIFO order):
    #    - result = handler(event)
    #    - if iscoroutine(result): await result
    # 3. Append event to history: self._history.append(event)
```

**For BarCompletedEvent:**
- Calls: `strategy_app_service._on_bar_completed(event)` (async)

---

## PHASE 4: Strategy Signal → Order Creation

### Bar Event Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

```python
@event_handler(BarCompletedEvent)
async def _on_bar_completed(self, event: BarCompletedEvent) -> None:
    # 1. Find matching strategies
    strategies = self._find_strategies(
        event.symbol, event.exchange, event.interval, trigger="bar"
    )
    
    # 2. For each matching strategy:
    for strategy in strategies:
        try:
            bar = {
                "symbol": event.symbol,
                "exchange": event.exchange,
                "interval": event.interval,
                "open": event.open,
                "high": event.high,
                "low": event.low,
                "close": event.close,
                "volume": event.volume,
                "timestamp": event.bar_start,
            }
            
            # 3. Call strategy.on_bar(bar)
            signal = await strategy.on_bar(bar)
            
            # 4. If signal returned: process it
            if signal:
                await self._process_signal(strategy, signal, event.close)
```

**Parameters:**
- `strategy`: IStrategy instance
- `bar`: dict with OHLCV data
- `signal`: Signal | None (returned from strategy.on_bar())

**Signal Structure:**
- `direction`: Direction.LONG | Direction.SHORT
- `symbol`: str
- `exchange`: str
- `entry_price`: float | None
- `stop_loss_price`: float | None

---

### Signal Processing & Risk Validation

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

```python
async def _process_signal(
    self, strategy: IStrategy, signal: Signal, current_price: float
) -> None:
    # 1. Get broker for this strategy
    broker = self._brokers.get(strategy.id)
    
    # 2. Get account balance
    balance = await broker.get_balance()  # ← BROKER REST API CALL
    
    # 3. Get current position
    position = self._position_app_service.get(strategy.id)
    
    # 4. Risk validation
    valid, reason = self._risk_check_handler.validate(
        signal, balance, position, strategy.config.risk
    )
    if not valid:
        logger.info("signal_rejected_by_risk", reason=reason)
        return
    
    # 5. Calculate position size
    stop_loss = signal.stop_loss_price or (
        current_price * (1 - strategy.config.orders.stop_loss.distance_percent)
        if signal.direction == Direction.LONG
        else current_price * (1 + strategy.config.orders.stop_loss.distance_percent)
    )
    
    size = PositionSizer.calculate_size(
        balance.available_balance,
        current_price,
        stop_loss,
        strategy.config.risk,
    )
    
    if size <= 0:
        logger.info("zero_position_size")
        return
    
    # 6. Create order
    order = self._create_order(strategy, signal, size, current_price)
    
    # 7. Submit order
    result = await self._order_app_service.submit(order, broker)
```

**External I/O:**
- OKX REST API: `broker.get_balance()`

---

### Order Creation

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/strategy_app_service.py`

```python
def _create_order(
    self,
    strategy: IStrategy,
    signal: Signal,
    size: float,
    current_price: float,
) -> OrderAggregate:
    # 1. Map direction to side
    side = OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL
    
    # 2. Determine order type
    order_type = (
        OrderType.MARKET if strategy.config.orders.entry_type == "market" 
        else OrderType.LIMIT
    )
    
    # 3. Set price based on order type
    price = signal.entry_price if order_type == OrderType.LIMIT else current_price
    
    # 4. Create order aggregate
    return OrderAggregate.create(
        strategy_id=strategy.id,
        symbol=signal.symbol,
        exchange=signal.exchange,
        side=side,
        order_type=order_type,
        quantity=size,
        price=price,
    )
```

**Returns:** OrderAggregate instance

---

### Order Aggregate Creation

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/domain/order/entities.py`

```python
@classmethod
def create(
    cls,
    strategy_id: str,
    symbol: str,
    exchange: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: float,
    price: float | None = None,
    stop_price: float | None = None,
) -> OrderAggregate:
    # 1. Validate inputs
    # 2. Generate unique ID: id = generate_id_str()
    # 3. Return OrderAggregate instance with:
    #    - status: OrderStatus.PENDING
    #    - created_at: UTC now
    #    - updated_at: UTC now
    #    - _events: []
    return cls(
        id=generate_id_str(),
        strategy_id=strategy_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
    )
```

**Order Fields:**
- `id`: str (UUID)
- `strategy_id`: str
- `symbol`: str
- `exchange`: str
- `side`: OrderSide.BUY | OrderSide.SELL
- `order_type`: OrderType.MARKET | OrderType.LIMIT
- `quantity`: float
- `price`: float | None
- `stop_price`: float | None
- `status`: OrderStatus.PENDING
- `filled_quantity`: 0.0
- `filled_price`: None
- `broker_order_id`: None
- `created_at`: datetime (UTC)
- `updated_at`: datetime (UTC)

---

## PHASE 5: Order Submission to Broker

### Order App Service Submit

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/order_app_service.py`

```python
async def submit(self, order: OrderAggregate, broker: IBroker) -> OrderResult:
    # 1. Lock acquired
    # 2. Store pending order
    self._pending[order.id] = order
    
    # 3. Persist initial order state to MongoDB
    await self._order_repo.save(order)
    
    try:
        # 4. Submit to broker
        result = await broker.submit_order(order)
        
        async with self._lock:
            if result.is_success:
                # 5. Store broker order ID mapping
                self._broker_map[order.id] = result.broker_order_id
                order.broker_order_id = result.broker_order_id
                
                # 6. If immediately filled (market orders)
                if result.status == OrderStatus.FILLED:
                    order.fill(result.filled_quantity, result.filled_price or 0.0)
                    self._orders[order.id] = order
                    self._pending.pop(order.id, None)
                    await self._order_repo.save(order)
                    
                    # 7. Publish fill event
                    await self._event_bus.publish(
                        OrderFilledEvent(
                            order_id=order.id,
                            strategy_id=order.strategy_id,
                            symbol=order.symbol,
                            exchange=order.exchange,
                            side=order.side,
                            filled_quantity=result.filled_quantity,
                            filled_price=result.filled_price or 0.0,
                        )
                    )
                else:
                    # 8. Order submitted but not filled
                    order.submit(result.broker_order_id)
                    await self._order_repo.save(order)
        
        return result
    except Exception as e:
        async with self._lock:
            order.reject(str(e))
            await self._order_repo.save(order)
            self._pending.pop(order.id, None)
        return OrderResult(
            order_id=order.id,
            broker_order_id="",
            status=OrderStatus.REJECTED,
            error_message=str(e),
        )
```

**External I/O:**
- MongoDB write: `order_repo.save(order)` (initial)
- Broker REST API: `broker.submit_order(order)`
- MongoDB write: `order_repo.save(order)` (after fill or submission)
- EventBus publish: `event_bus.publish(OrderFilledEvent)` (if filled)

**Return Value:** OrderResult

---

### OKX Broker: Order Submission

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_broker.py`

```python
async def submit_order(self, order: OrderAggregate) -> OrderResult:
    # 1. Check connection
    if not self._connected or not self._trade_api:
        return OrderResult(
            order_id=order.id,
            broker_order_id="",
            status=OrderStatus.REJECTED,
            error_message="Broker not connected",
        )
    
    try:
        # 2. Map order to OKX parameters
        params = map_order_to_okx_params(order, self._inst_suffix)
        
        # 3. Call OKX SDK place_order in thread pool (blocking SDK)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._trade_api.place_order(**params)
        )
        
        # 4. Parse response
        if response.get("code") != "0":
            error_msg = response.get("msg", "Unknown error")
            return OrderResult(
                order_id=order.id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                error_message=error_msg,
            )
        
        # 5. Extract order data
        data = response.get("data", [{}])[0]
        broker_order_id = data.get("ordId", "")
        state = data.get("sCode", "0")  # "0" = success
        
        status = OrderStatus.SUBMITTED if state == "0" else OrderStatus.REJECTED
        
        result = OrderResult(
            order_id=order.id,
            broker_order_id=broker_order_id,
            status=status,
            submitted_at=datetime.now(UTC),
        )
        
        # 6. Notify callbacks
        await self._notify_callbacks(result)
        
        return result
    
    except Exception as e:
        logger.error("okx_order_submit_failed", order_id=order.id, error=str(e))
        return OrderResult(
            order_id=order.id,
            broker_order_id="",
            status=OrderStatus.REJECTED,
            error_message=str(e),
        )
```

**External I/O:**
- OKX REST API: `self._trade_api.place_order(**params)`

**Parameters mapped to OKX:**

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/brokers/okx/okx_mapper.py`

```python
def map_order_to_okx_params(order: OrderAggregate, inst_suffix: str = "USDT") -> dict:
    params = {
        "instId": f"{order.symbol}-{inst_suffix}",  # e.g., "BTC-USDT"
        "tdMode": "cash",  # spot trading
        "side": map_order_side_to_okx(order.side),  # "buy" or "sell"
        "ordType": map_order_type_to_okx(order.order_type),  # "market" or "limit"
        "sz": str(order.quantity),  # position size
        "clOrdId": order.id,  # client order ID (for tracking)
    }
    if order.order_type == OrderType.LIMIT and order.price:
        params["px"] = str(order.price)
    if order.order_type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET):
        if order.stop_price:
            params["triggerPx"] = str(order.stop_price)
        if order.price:
            params["orderPx"] = str(order.price)
    return params
```

**OKX Response Structure:**
```json
{
  "code": "0",  // "0" = success
  "msg": "",
  "data": [
    {
      "ordId": "1234567890",  // OKX order ID
      "clOrdId": "internal-uuid",  // Maps back to our order.id
      "sCode": "0"  // "0" = success/live, other = rejected
    }
  ]
}
```

**Return Value:** OrderResult with broker_order_id

---

## PHASE 6: Order Fill & Position Update

### Order Fill Event Handling

When an order is filled (either immediately or via WebSocket callback), `OrderFilledEvent` is published.

**Event Structure:**

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/domain/order/events.py`

```python
@dataclass(frozen=True, eq=False)
class OrderFilledEvent(DomainEvent):
    order_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    exchange: str = ""
    side: OrderSide = OrderSide.BUY
    filled_quantity: float = 0.0
    filled_price: float = 0.0
```

---

### Position App Service: Order Filled Handler

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/app_services/position_app_service.py`

```python
@event_handler(OrderFilledEvent)
async def _on_order_filled(self, event: OrderFilledEvent) -> None:
    async with self._lock:
        position = self._positions.get(event.strategy_id)
        
        if position is None:
            # NEW POSITION: Create fresh position
            side = PositionSide.LONG if event.side == OrderSide.BUY else PositionSide.SHORT
            
            position = PositionAggregate.open(
                strategy_id=event.strategy_id,
                symbol=event.symbol,
                exchange=event.exchange,
                side=side,
                entry_price=event.filled_price,
                quantity=event.filled_quantity,
            )
            
            self._positions[event.strategy_id] = position
            
            # 1. Persist new position
            await self._position_repo.save(position)
            
            # 2. Publish position opened event
            await self._event_bus.publish(
                PositionOpenedEvent(
                    position_id=position.id,
                    strategy_id=event.strategy_id,
                    symbol=event.symbol,
                    exchange=event.exchange,
                    side=side,
                    entry_price=event.filled_price,
                    quantity=event.filled_quantity,
                )
            )
        else:
            # EXISTING POSITION: Modify based on side
            is_same_side = (
                event.side == OrderSide.BUY and position.side == PositionSide.LONG
            ) or (event.side == OrderSide.SELL and position.side == PositionSide.SHORT)
            
            if is_same_side:
                # ADDING to position
                position.add_quantity(event.filled_quantity, event.filled_price)
                await self._position_repo.save(position)
            else:
                # REDUCING position
                position.reduce_quantity(event.filled_quantity, event.filled_price)
                await self._position_repo.save(position)
                
                if position.is_closed:
                    del self._positions[event.strategy_id]
```

**External I/O:**
- MongoDB write: `position_repo.save(position)`
- EventBus publish: `event_bus.publish(PositionOpenedEvent)`

---

### Position Aggregate

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/domain/position/entities.py`

```python
@classmethod
def open(
    cls,
    strategy_id: str,
    symbol: str,
    exchange: str,
    side: PositionSide,
    entry_price: float,
    quantity: float,
) -> PositionAggregate:
    return cls(
        id=generate_id_str(),
        strategy_id=strategy_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=entry_price,
        pnl=0.0,
        pnl_percent=0.0,
        is_closed=False,
        opened_at=datetime.now(UTC),
        closed_at=None,
    )
```

**Position Fields:**
- `id`: str (UUID)
- `strategy_id`: str
- `symbol`: str
- `exchange`: str
- `side`: PositionSide.LONG | PositionSide.SHORT
- `quantity`: float
- `entry_price`: float
- `current_price`: float
- `pnl`: float (unrealized P&L)
- `pnl_percent`: float
- `is_closed`: bool
- `opened_at`: datetime
- `closed_at`: datetime | None

---

## PHASE 7: Persistence

### Order Repository

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/persistence/order_repository.py`

```python
class OrderRepository(BaseRepository):
    _collection_name = "orders"  # COLLECTION_ORDERS
    
    async def save(self, order: OrderAggregate) -> None:
        collection = self._collection()
        await collection.replace_one(
            {"_id": order.id},
            order.to_mongo(),  # Serializes to BSON
            upsert=True
        )
    
    async def find_by_strategy(self, strategy_id: str, limit: int = 1000) -> list:
        cursor = collection.find({"strategy_id": strategy_id}).limit(limit)
        return [OrderAggregate.from_mongo(doc) async for doc in cursor]
    
    async def find_pending(self, limit: int = 500) -> list:
        cursor = collection.find(
            {"status": {"$in": ["pending", "submitted", "partially_filled"]}}
        ).limit(limit)
        return [OrderAggregate.from_mongo(doc) async for doc in cursor]
```

**MongoDB Collection:** `orders`

**Indexes Created:**
- `strategy_id` (ix_orders_strategy_id)
- `status` (ix_orders_status)
- `symbol + exchange` (ix_orders_symbol_exchange)

---

### Position Repository

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-trading/src/pocketquant/trading/persistence/position_repository.py`

```python
class PositionRepository(BaseRepository):
    _collection_name = "positions"  # COLLECTION_POSITIONS
    
    async def save(self, position: PositionAggregate) -> None:
        collection = self._collection()
        await collection.replace_one(
            {"_id": position.id},
            position.to_mongo(),
            upsert=True
        )
    
    async def get_by_strategy(self, strategy_id: str) -> PositionAggregate | None:
        doc = await collection.find_one({
            "strategy_id": strategy_id,
            "is_closed": False
        })
        return PositionAggregate.from_mongo(doc) if doc else None
    
    async def find_open(self, limit: int = 200) -> list:
        cursor = collection.find({"is_closed": False}).limit(limit)
        return [PositionAggregate.from_mongo(doc) async for doc in cursor]
```

**MongoDB Collection:** `positions`

**Indexes Created:**
- `strategy_id` (ix_positions_strategy_id)
- `is_closed` (ix_positions_is_closed)
- `symbol + exchange` (ix_positions_symbol_exchange)

---

### Bar Repository

**File:** `/Users/admin/workspace/_me/pocketquant/packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py`

```python
async def upsert_bar(self, bar: Bar) -> None:
    collection = self._collection()
    await collection.replace_one(
        {
            "symbol": bar.symbol,
            "exchange": bar.exchange,
            "interval": bar.interval.value,
            "datetime": bar.datetime,
        },
        bar.to_mongo(),
        upsert=True,
    )
```

**MongoDB Collection:** `bars`

---

## Summary: Complete Execution Order

| Phase | Component | File | Function | Parameters | External I/O | Event Emitted |
|-------|-----------|------|----------|------------|--------------|---------------|
| **1** | Route | `strategy/load/route.py` | `load_strategy()` | path: str | File read, YAML parse | - |
| **1** | Handler | `strategy/load/handler.py` | `LoadStrategyHandler.handle()` | LoadStrategyCommand | - | - |
| **1** | Loader | `yaml_strategy_loader.py` | `StrategyLoader.load()` | path: Path | File I/O | - |
| **1** | AppService | `strategy_app_service.py` | `load_strategy()` | StrategyConfig | Broker creation | - |
| **2** | Route | `strategy/start/route.py` | `start_strategy()` | strategy_id: str | - | - |
| **2** | Handler | `strategy/start/handler.py` | `StartStrategyHandler.handle()` | StartStrategyCommand | - | - |
| **2** | AppService | `strategy_app_service.py` | `start_strategy()` | strategy_id: str | Broker.connect() → OKX | - |
| **2** | Registry | `event_registry.py` | `register_instance()` | instance, event_bus | - | - (subscriptions) |
| **3** | QuoteAppService | `quote_app_service.py` | `on_quote_update()` | quote_data: dict | Redis write, bar processing | - |
| **3** | BarAppService | `bar_app_service.py` | `add_tick()` | QuoteTick | - | - |
| **3** | BarAppService | `bar_app_service.py` | `_save_completed_bar()` | BarBuilder | MongoDB, Redis, EventBus | **BarCompletedEvent** |
| **4** | StrategyAppService | `strategy_app_service.py` | `_on_bar_completed()` | BarCompletedEvent | Strategy.on_bar() call | - |
| **4** | StrategyAppService | `strategy_app_service.py` | `_process_signal()` | Signal | OKX balance query | - |
| **4** | StrategyAppService | `strategy_app_service.py` | `_create_order()` | Signal | - | - |
| **4** | OrderAggregate | `order/entities.py` | `OrderAggregate.create()` | order params | UUID generation | - |
| **5** | OrderAppService | `order_app_service.py` | `submit()` | OrderAggregate, IBroker | MongoDB write, broker call | **OrderFilledEvent** (if immediate fill) |
| **5** | OKXBroker | `okx_broker.py` | `submit_order()` | OrderAggregate | OKX REST API (place_order) | - |
| **6** | PositionAppService | `position_app_service.py` | `_on_order_filled()` | OrderFilledEvent | MongoDB write, EventBus | **PositionOpenedEvent** |
| **6** | PositionAggregate | `position/entities.py` | `PositionAggregate.open()` | position params | UUID generation | - |
| **7** | OrderRepository | `order_repository.py` | `save()` | OrderAggregate | MongoDB upsert | - |
| **7** | PositionRepository | `position_repository.py` | `save()` | PositionAggregate | MongoDB upsert | - |

---

## Key Data Flows

### Request → Response Chain

```
POST /load → LoadStrategyRoute
  → LoadStrategyHandler.handle(LoadStrategyCommand)
    → StrategyAppService.load_strategy(StrategyConfig)
      → Broker creation (_get_or_create_broker)
      ← strategy_id (string)
    ← strategy_id
  ← {"strategy_id": "...", "status": "loaded"}

POST /{strategy_id}/start → StartStrategyRoute
  → StartStrategyHandler.handle(StartStrategyCommand)
    → StrategyAppService.start_strategy(strategy_id)
      → Broker.connect() [OKX REST API]
      → EventRegistry.register_instance(strategy_app_service, event_bus)
        [subscribes _on_bar_completed, _on_quote_received]
      ← void
    ← void
  ← {"strategy_id": "...", "status": "started"}
```

### Event → Handler Chain

```
BarCompletedEvent published by: EventBus.publish()
  → StrategyAppService._on_bar_completed(event)
    → strategy.on_bar(bar_dict) [user-defined]
      ← Signal | None
    → StrategyAppService._process_signal(signal)
      → Broker.get_balance() [OKX REST API]
      → StrategyAppService._create_order(signal)
        ← OrderAggregate
      → OrderAppService.submit(order, broker)
        → Broker.submit_order(order) [OKX REST API: place_order]
          ← OrderResult
        → if filled: EventBus.publish(OrderFilledEvent)
          → PositionAppService._on_order_filled(event)
            → PositionRepository.save(position) [MongoDB]
            → EventBus.publish(PositionOpenedEvent)
```

---

## External Systems & I/O Summary

| System | Type | Operation | File |
|--------|------|-----------|------|
| **Filesystem** | Read | Load YAML strategy file | `yaml_strategy_loader.py` |
| **OKX REST API** | Call | `trade_api.place_order(**params)` | `okx_broker.py` |
| **OKX REST API** | Call | `account_api.get_balance()` | `okx_broker.py` |
| **MongoDB** | Write | Order upsert (`orders` collection) | `order_repository.py` |
| **MongoDB** | Write | Position upsert (`positions` collection) | `position_repository.py` |
| **MongoDB** | Write | Bar upsert (`bars` collection) | `bar_repository.py` |
| **MongoDB** | Read | Query open positions | `position_repository.py` |
| **Redis** | Write | Cache latest quotes | `quote_app_service.py` |
| **Redis** | Write | Cache current bars | `bar_app_service.py` |
| **Redis** | Delete | Clear completed bar cache | `bar_app_service.py` |
| **In-Memory EventBus** | Publish | Domain events | `event_bus.py` |

---

## State Machines

### Order State Machine

```
PENDING
  ├─→ SUBMITTED
  │    ├─→ PARTIALLY_FILLED
  │    │    ├─→ FILLED ✓ [terminal]
  │    │    └─→ CANCELLED ✓ [terminal]
  │    ├─→ FILLED ✓ [terminal]
  │    └─→ CANCELLED ✓ [terminal]
  └─→ REJECTED ✓ [terminal]
```

**Transitions:**
- `order.submit(broker_order_id)` → PENDING → SUBMITTED
- `order.fill(quantity, price)` → → FILLED
- `order.partial_fill(quantity, price)` → → PARTIALLY_FILLED
- `order.cancel()` → → CANCELLED
- `order.reject(reason)` → → REJECTED

---

### Position State Machine

```
OPEN (is_closed=False)
  ├─→ add_quantity(qty, price) [adding to position]
  ├─→ reduce_quantity(qty, price) [reducing position]
  │    └─ If quantity becomes 0: CLOSED (is_closed=True) ✓ [terminal]
  └─→ close() [explicit close]
       → CLOSED (is_closed=True) ✓ [terminal]
```

---

## Key Invariants & Guarantees

1. **Ordering:** Events processed FIFO by EventBus; handlers called sequentially
2. **Atomicity:** OrderAppService.submit() locks during order state changes
3. **Durability:** All orders/positions written to MongoDB before event publication
4. **Idempotency:** Order repository uses upsert; duplicate saves are safe
5. **Consistency:** PositionAppService loads open positions on startup
6. **Isolation:** Per-strategy broker and position instances (no cross-talk)

---

## Unresolved Questions

1. **OKX WebSocket Updates:** How are order fills from OKX WebSocket integrated? (File: `okx_websocket_client.py` not traced)
2. **Callback Flow:** When does `OKXBroker._notify_callbacks(result)` trigger position updates?
3. **Partial Fills:** How does `OrderAggregate.partial_fill()` flow through the event system?
4. **Position P&L Updates:** When is `current_price` updated and P&L recalculated?
5. **Multiple Bars:** How does one tick process across 4 intervals (1m, 5m, 1h, 1d) simultaneously?
6. **Concurrent Strategies:** How do multiple strategies sharing the same symbol handle race conditions?

