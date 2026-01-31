# Phase 05: OKX Message Parsing & Callbacks

## Context Links

- Parent: [plan.md](./plan.md)
- Depends on: [phase-04-okx-websocket-client.md](./phase-04-okx-websocket-client.md)
- Research: [researcher-01-okx-websocket-api.md](./research/researcher-01-okx-websocket-api.md)
- Existing: `src/infrastructure/brokers/models.py` (OrderResult model)

## Overview

| Field | Value |
|-------|-------|
| Priority | P2 - High |
| Status | pending |
| Estimate | 2h |

Parse OKX WebSocket messages and map to domain models, trigger broker callbacks.

## Key Insights

1. **State mapping** - OKX states differ from domain OrderStatus
2. **Deduplication** - Process only FIRST filled/canceled per ordId
3. **tradeId linking** - Connects orders to positions for reconciliation
4. **Terminal states** - `filled`, `canceled`, `mmp_canceled` are final

## Requirements

### Functional
- Parse orders channel messages → OrderResult
- Parse positions channel messages → PositionUpdate
- Map OKX order states to domain OrderStatus
- Deduplicate terminal state messages (filled, canceled)
- Trigger `_notify_callbacks()` on OrderResult
- Emit PositionUpdatedEvent for position changes

### Non-Functional
- Message parsing <1ms
- Callbacks invoked within 10ms of message receipt

## Architecture

```
WebSocket Message
    │
    ├─ OkxMessageParser.parse(msg)
    │   ├─ Detect channel (orders, positions)
    │   ├─ Extract data array
    │   └─ Map to domain models
    │
    ├─ Orders Channel
    │   ├─ OkxOrderMapper.to_order_result(data)
    │   ├─ Deduplication check (seen_order_ids)
    │   └─ OkxBroker._notify_callbacks(result)
    │
    └─ Positions Channel
        ├─ OkxPositionMapper.to_position_update(data)
        └─ EventBus.publish(PositionUpdatedEvent)
```

### OKX Order State Mapping

| OKX State | Domain OrderStatus | Notes |
|-----------|-------------------|-------|
| `live` | SUBMITTED | Order accepted, awaiting fill |
| `partially_filled` | PARTIALLY_FILLED | Partial execution |
| `filled` | FILLED | Terminal - fully executed |
| `canceled` | CANCELLED | Terminal - user or system |
| `mmp_canceled` | CANCELLED | Terminal - market maker protection |

### Message Structures

```python
# Orders channel message
{
    "arg": {"channel": "orders", "instType": "SWAP"},
    "data": [{
        "instId": "BTC-USDT-SWAP",
        "ordId": "312269865356374016",
        "clOrdId": "client-order-id",  # Our order.id
        "state": "filled",
        "px": "45000.5",               # Order price
        "sz": "1",                     # Order size
        "accFillSz": "1",              # Accumulated fill size
        "avgPx": "45000.3",            # Average fill price
        "fillPx": "45000.3",           # This fill price
        "fillSz": "1",                 # This fill size
        "tradeId": "123456789",        # Trade ID for reconciliation
        "side": "buy",
        "ordType": "limit",
        "uTime": "1234567890000"       # Update timestamp (ms)
    }]
}

# Positions channel message
{
    "arg": {"channel": "positions", "instType": "SWAP"},
    "data": [{
        "instId": "BTC-USDT-SWAP",
        "posId": "pos-123",
        "posSide": "long",
        "pos": "10",                   # Position size
        "avgPx": "44000",              # Average entry price
        "upl": "1500.5",               # Unrealized PnL
        "lever": "5",                  # Leverage
        "markPx": "45500",             # Mark price
        "tradeId": "123456789",        # Latest trade
        "uTime": "1234567890000"
    }]
}
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/infrastructure/brokers/okx/websocket/okx-message-parser.py` | Channel routing | ~60 |
| `src/infrastructure/brokers/okx/websocket/okx-order-mapper.py` | Order state mapping | ~80 |
| `src/infrastructure/brokers/okx/websocket/okx-position-mapper.py` | Position mapping | ~60 |
| `src/domain/position/position-event.py` | PositionUpdatedEvent | ~25 |

### Modify
| File | Change |
|------|--------|
| `src/infrastructure/brokers/okx/okx_broker.py` | Add `_handle_ws_message()`, dedup set |

## Implementation Steps

1. **Create OkxMessageParser**
   ```python
   class OkxMessageParser:
       @staticmethod
       def parse(message: dict) -> tuple[str, list[dict]]:
           """Parse message, return (channel, data_items)."""
           arg = message.get("arg", {})
           channel = arg.get("channel", "")
           data = message.get("data", [])
           return channel, data

       @staticmethod
       def is_event(message: dict) -> bool:
           """Check if message is event (login, subscribe, error)."""
           return "event" in message
   ```

2. **Create OkxOrderMapper**
   ```python
   STATE_MAP = {
       "live": OrderStatus.SUBMITTED,
       "partially_filled": OrderStatus.PARTIALLY_FILLED,
       "filled": OrderStatus.FILLED,
       "canceled": OrderStatus.CANCELLED,
       "mmp_canceled": OrderStatus.CANCELLED,
   }

   class OkxOrderMapper:
       @staticmethod
       def to_order_result(data: dict) -> OrderResult:
           return OrderResult(
               order_id=data["clOrdId"],         # Our client order ID
               broker_order_id=data["ordId"],    # OKX order ID
               status=STATE_MAP.get(data["state"], OrderStatus.UNKNOWN),
               filled_quantity=float(data.get("accFillSz", 0)),
               filled_price=float(data.get("avgPx", 0)) or None,
               error_message=data.get("msg"),
           )

       @staticmethod
       def is_terminal(state: str) -> bool:
           return state in ("filled", "canceled", "mmp_canceled")
   ```

3. **Create OkxPositionMapper**
   ```python
   class OkxPositionMapper:
       @staticmethod
       def to_position_update(data: dict) -> PositionUpdate:
           return PositionUpdate(
               position_id=data["posId"],
               symbol=data["instId"].replace("-SWAP", ""),
               side="long" if float(data["pos"]) > 0 else "short",
               quantity=abs(float(data["pos"])),
               entry_price=float(data["avgPx"]),
               unrealized_pnl=float(data.get("upl", 0)),
               mark_price=float(data.get("markPx", 0)),
           )
   ```

4. **Create PositionUpdatedEvent**
   ```python
   @dataclass(frozen=True)
   class PositionUpdatedEvent(DomainEvent):
       position_id: str = ""
       symbol: str = ""
       side: str = ""
       quantity: float = 0.0
       entry_price: float = 0.0
       unrealized_pnl: float = 0.0
   ```

5. **Update OkxBroker with message handling**
   ```python
   class OkxBroker:
       def __init__(self, ...):
           ...
           self._seen_terminal_orders: set[str] = set()  # Deduplication

       async def _handle_ws_message(self, message: dict) -> None:
           if OkxMessageParser.is_event(message):
               return  # Handle events separately

           channel, data_items = OkxMessageParser.parse(message)

           if channel == "orders":
               for item in data_items:
                   await self._handle_order_update(item)
           elif channel == "positions":
               for item in data_items:
                   await self._handle_position_update(item)

       async def _handle_order_update(self, data: dict) -> None:
           ord_id = data["ordId"]
           state = data["state"]

           # Deduplicate terminal states
           if OkxOrderMapper.is_terminal(state):
               if ord_id in self._seen_terminal_orders:
                   return  # Already processed
               self._seen_terminal_orders.add(ord_id)

           result = OkxOrderMapper.to_order_result(data)
           await self._notify_callbacks(result)
   ```

## Todo List

- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-message-parser.py`
- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-order-mapper.py`
- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-position-mapper.py`
- [ ] Create `src/domain/position/position-event.py`
- [ ] Update OkxBroker with `_handle_ws_message()`
- [ ] Add deduplication set for terminal orders
- [ ] Unit test: state mapping covers all OKX states
- [ ] Unit test: deduplication prevents double-processing

## Success Criteria

- [ ] Orders channel messages trigger `_notify_callbacks()`
- [ ] Positions channel messages emit PositionUpdatedEvent
- [ ] Terminal states (filled, canceled) processed once only
- [ ] clOrdId correctly maps to our order_id
- [ ] Callbacks invoked within 500ms of WebSocket message

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Unknown order state from OKX | Low | Medium | Log warning, map to UNKNOWN |
| clOrdId mismatch (order not found) | Medium | Medium | Log warning, skip callback |
| Memory leak in seen_terminal_orders | Low | Low | Clear set periodically or use TTL cache |

## Security Considerations

- No credential handling in parsers
- Validate numeric fields before float conversion
- Log ordId but not sensitive order details

## Next Steps

After this phase:
- Phase 06: Implement reconnection with REST sync for guaranteed delivery
