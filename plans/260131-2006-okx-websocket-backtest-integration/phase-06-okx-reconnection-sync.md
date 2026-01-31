# Phase 06: OKX Reconnection & Sync

## Context Links

- Parent: [plan.md](./plan.md)
- Depends on: [phase-05-okx-message-parsing-callbacks.md](./phase-05-okx-message-parsing-callbacks.md)
- Research: [researcher-01-okx-websocket-api.md](./research/researcher-01-okx-websocket-api.md)
- Existing: `src/infrastructure/brokers/okx/okx_broker.py` (REST API methods)

## Overview

| Field | Value |
|-------|-------|
| Priority | P2 - High |
| Status | pending |
| Estimate | 3h |

Guaranteed delivery via exponential backoff reconnection and REST API sync on reconnect.

## Key Insights

1. **No sequence IDs** - OKX private channels use timestamp, not seqId
2. **REST sync required** - Fetch open orders + positions after reconnect
3. **Exponential backoff** - 1s, 2s, 4s, 8s... max 30s
4. **State reconciliation** - Compare WS snapshot with local state
5. **Message buffering** - Queue messages during reconnect phase

## Requirements

### Functional
- Detect disconnect (socket error or ping timeout)
- Exponential backoff reconnection (1s → 30s max)
- After reconnect: fetch open orders via REST
- After reconnect: fetch positions via REST
- Compare REST state with local state, process differences
- Re-subscribe to channels after reconnect
- Resume normal message processing

### Non-Functional
- Reconnect within 30 seconds of disconnect
- No duplicate callbacks after reconnect
- No missed fills after reconnect

## Architecture

```
Disconnect Detected
    │
    ├─ OkxReconnectionHandler.start_reconnect()
    │   ├─ Set reconnecting = True
    │   ├─ Clear WebSocket state
    │   └─ Start backoff loop
    │
    ├─ Backoff Loop
    │   ├─ Wait delay (1s, 2s, 4s... max 30s)
    │   ├─ Attempt connect()
    │   ├─ On success: break
    │   └─ On failure: increase delay
    │
    ├─ Post-Reconnect Sync
    │   ├─ Fetch open orders via REST
    │   ├─ Fetch positions via REST
    │   ├─ Compare with local state
    │   ├─ Process any missed fills
    │   └─ Update seen_terminal_orders set
    │
    └─ Resume
        ├─ Re-subscribe to channels
        ├─ Set reconnecting = False
        └─ Resume message loop
```

### Reconnection State Machine

```
           ┌─────────────────────────────────────────────┐
           │                                             │
           ▼                                             │
    ┌─────────────┐    disconnect    ┌─────────────┐    │
    │  CONNECTED  │ ───────────────► │ RECONNECTING│    │
    └─────────────┘                  └──────┬──────┘    │
           ▲                                │           │
           │                          backoff loop      │
           │                                │           │
           │         success         ┌──────▼──────┐    │
           └─────────────────────────│   SYNCING   │    │
                                     └──────┬──────┘    │
                                            │           │
                                      sync complete     │
                                            │           │
                                            └───────────┘
```

### REST Sync Endpoints

```python
# Open orders
GET /api/v5/trade/orders-pending?instType=SWAP

# All positions
GET /api/v5/account/positions?instType=SWAP
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/infrastructure/brokers/okx/websocket/okx-reconnection-handler.py` | Backoff + sync | ~120 |
| `src/infrastructure/brokers/okx/websocket/okx-state-reconciler.py` | State comparison | ~80 |

### Modify
| File | Change |
|------|--------|
| `src/infrastructure/brokers/okx/websocket/okx-websocket-client.py` | Add reconnection hooks |
| `src/infrastructure/brokers/okx/okx_broker.py` | Integrate reconnection handler |

## Implementation Steps

1. **Create OkxReconnectionHandler**
   ```python
   class OkxReconnectionHandler:
       def __init__(
           self,
           ws_client: OkxWebSocketClient,
           rest_client: OkxBroker,  # For REST calls
           initial_delay: float = 1.0,
           max_delay: float = 30.0,
           multiplier: float = 2.0,
       ):
           self._ws_client = ws_client
           self._rest_client = rest_client
           self._initial_delay = initial_delay
           self._max_delay = max_delay
           self._multiplier = multiplier
           self._reconnecting = False

       async def handle_disconnect(self) -> None:
           """Start reconnection process."""
           if self._reconnecting:
               return
           self._reconnecting = True

           delay = self._initial_delay
           while True:
               logger.info("okx_reconnect_attempt", delay=delay)
               await asyncio.sleep(delay)

               try:
                   await self._ws_client.connect()
                   await self._sync_state()
                   await self._ws_client.subscribe([
                       {"channel": "orders", "instType": "SWAP"},
                       {"channel": "positions", "instType": "SWAP"}
                   ])
                   self._reconnecting = False
                   logger.info("okx_reconnect_success")
                   return
               except Exception as e:
                   logger.warning("okx_reconnect_failed", error=str(e))
                   delay = min(delay * self._multiplier, self._max_delay)

       async def _sync_state(self) -> None:
           """Fetch REST state and reconcile."""
           reconciler = OkxStateReconciler(self._rest_client)
           await reconciler.sync()
   ```

2. **Create OkxStateReconciler**
   ```python
   class OkxStateReconciler:
       def __init__(self, broker: OkxBroker):
           self._broker = broker

       async def sync(self) -> None:
           """Fetch REST state and process differences."""
           # Fetch current state from REST
           orders = await self._fetch_open_orders()
           positions = await self._broker.get_positions()

           # Update seen terminal orders (prevent re-processing)
           await self._update_terminal_orders()

           # Process any orders that filled while disconnected
           await self._process_missed_fills(orders)

           logger.info("okx_state_synced", orders=len(orders), positions=len(positions))

       async def _fetch_open_orders(self) -> list[dict]:
           """Fetch pending orders via REST."""
           loop = asyncio.get_event_loop()
           response = await loop.run_in_executor(
               None,
               lambda: self._broker._trade_api.get_order_list(instType="SWAP")
           )
           if response.get("code") != "0":
               return []
           return response.get("data", [])

       async def _update_terminal_orders(self) -> None:
           """Fetch recent order history to update dedup set."""
           loop = asyncio.get_event_loop()
           response = await loop.run_in_executor(
               None,
               lambda: self._broker._trade_api.get_orders_history(instType="SWAP", limit="100")
           )
           if response.get("code") != "0":
               return

           for order in response.get("data", []):
               if order.get("state") in ("filled", "canceled", "mmp_canceled"):
                   self._broker._seen_terminal_orders.add(order["ordId"])

       async def _process_missed_fills(self, open_orders: list[dict]) -> None:
           """Compare with expected orders, detect fills."""
           # Orders we expected to be open but aren't = filled or canceled
           # This would require tracking submitted orders locally
           pass  # Simplified: rely on REST history update
   ```

3. **Update OkxWebSocketClient with reconnection hook**
   ```python
   class OkxWebSocketClient:
       def __init__(self, ..., on_disconnect: Callable | None = None):
           ...
           self._on_disconnect = on_disconnect

       async def _message_loop(self) -> None:
           try:
               async for msg in self._ws:
                   yield json.loads(msg)
           except websockets.ConnectionClosed:
               if self._on_disconnect:
                   asyncio.create_task(self._on_disconnect())
   ```

4. **Update OkxBroker integration**
   ```python
   class OkxBroker:
       async def _ws_listener(self) -> None:
           reconnection_handler = OkxReconnectionHandler(
               ws_client=self._ws_client,
               rest_client=self,
           )

           self._ws_client = OkxWebSocketClient(
               ...,
               on_disconnect=reconnection_handler.handle_disconnect
           )

           await self._ws_client.connect()
           await self._ws_client.subscribe([...])

           async for message in self._ws_client:
               await self._handle_ws_message(message)
   ```

5. **Add ping/pong timeout detection**
   ```python
   async def _heartbeat_loop(self) -> None:
       while self._connected:
           await asyncio.sleep(25)  # Send ping before 30s timeout
           try:
               await asyncio.wait_for(
                   self._ws.ping(),
                   timeout=5.0
               )
           except asyncio.TimeoutError:
               logger.warning("okx_ping_timeout")
               await self._on_disconnect()
               return
   ```

## Todo List

- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-reconnection-handler.py`
- [ ] Create `src/infrastructure/brokers/okx/websocket/okx-state-reconciler.py`
- [ ] Update OkxWebSocketClient with on_disconnect callback
- [ ] Implement heartbeat with ping timeout detection
- [ ] Update OkxBroker to wire reconnection handler
- [ ] Unit test: backoff delays correct (1, 2, 4, 8...)
- [ ] Integration test: simulate disconnect, verify reconnect
- [ ] Integration test: verify REST sync fetches orders

## Success Criteria

- [ ] Auto-reconnect within 30 seconds of disconnect
- [ ] Exponential backoff observed in logs
- [ ] REST sync fetches open orders after reconnect
- [ ] REST sync fetches positions after reconnect
- [ ] No duplicate fill callbacks after reconnect
- [ ] Ping timeout triggers reconnection

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| REST API rate limited during sync | Low | Medium | Single sync call per reconnect |
| Infinite reconnect loop | Low | High | Max attempts limit or circuit breaker |
| State mismatch after sync | Medium | High | Log all diffs, alert on anomalies |
| Messages lost during reconnect | Medium | Medium | REST sync covers gap |

## Security Considerations

- REST calls use same credentials as WebSocket
- No new credential handling needed
- Log connection events but not auth details

## Next Steps

After this phase:
- OKX WebSocket feature complete
- Full integration testing with live demo account
- Document operational procedures (monitoring, alerts)
