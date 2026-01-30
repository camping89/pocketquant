# Code Review: TradingView WebSocket Provider

**File:** `src/infrastructure/tradingview/websocket.py`
**Date:** 2026-01-28
**Reviewer:** code-reviewer agent
**Lines of Code:** 260

---

## Scope

- **Files reviewed:** `src/infrastructure/tradingview/websocket.py`, `src/features/market_data/quote/handler.py`
- **Focus:** Connection reliability, memory leaks, race conditions, error handling, security, performance, code quality
- **Related usage:** Quote service handlers (market_data/quote/handler.py)

---

## Overall Assessment

**Code quality:** Good overall structure with async/await patterns. Clean message parsing and protocol handling.

**Critical gaps:** Race conditions in connection state, memory leak potential with callbacks, incomplete error handling during reconnect, type safety issues.

**Positive aspects:** Clean separation of concerns, exponential backoff logic, structured logging, protocol encapsulation.

---

## Critical Issues

### 1. Race Condition: Connection State + Subscriptions (Lines 211-218)

**Location:** `run_forever()` method, reconnection loop

**Issue:**
```python
# Line 211-218
if self._ws is None:
    await self.connect()

    # RACE: If concurrent subscribe() called here, subscriptions dict mutated during iteration
    for symbol_key in list(self._subscriptions.keys()):
        params = [self._session_id, symbol_key]
        await self._send_message("quote_add_symbols", params)
```

**Problem:** No lock protecting `_subscriptions` dict during concurrent subscribe/unsubscribe operations and reconnection resubscription loop. Can cause:
- Dict mutation during iteration (RuntimeError)
- Partial resubscriptions
- Lost subscriptions during race window

**Recommended fix:**
```python
import asyncio

class TradingViewWebSocketProvider:
    def __init__(self, auth_token: str | None = None):
        # ... existing code ...
        self._subscription_lock = asyncio.Lock()  # Add lock

    async def subscribe(self, symbol: str, exchange: str, callback: Callable) -> str:
        async with self._subscription_lock:  # Protect dict mutation
            if self._ws is None:
                raise RuntimeError("WebSocket not connected. Call connect() first.")

            symbol_key = f"{exchange}:{symbol}".upper()
            self._subscriptions[symbol_key] = callback
            await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
            logger.info("tradingview_ws.subscribed", symbol=symbol_key)
            return symbol_key

    async def unsubscribe(self, symbol: str, exchange: str) -> None:
        async with self._subscription_lock:  # Protect dict mutation
            # ... existing unsubscribe code ...

    async def run_forever(self) -> None:
        self._running = True

        while self._running:
            try:
                if self._ws is None:
                    await self.connect()

                    # Atomically snapshot subscriptions under lock
                    async with self._subscription_lock:
                        symbols_to_resubscribe = list(self._subscriptions.keys())

                    for symbol_key in symbols_to_resubscribe:
                        await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
                # ... rest of code ...
```

**Impact:** HIGH - Can cause subscription loss, data gaps, or runtime crashes in production

---

### 2. Memory Leak: Callback References Not Cleared (Lines 71, 186-198)

**Location:** `_subscriptions` dict and callback execution

**Issue:**
```python
# Line 71: Callbacks stored indefinitely
self._subscriptions: dict[str, Callable] = {}

# Line 186-198: Exception in callback doesn't remove subscription
callback = self._subscriptions.get(symbol_key)
if callback:
    try:
        if inspect.iscoroutinefunction(callback):
            await callback(quote_update)
        else:
            callback(quote_update)
    except Exception as e:
        logger.error("tradingview_ws.callback_failed", ...)
        # Callback NOT removed, will retry forever even if broken
```

**Problem:**
1. No cleanup of dead callbacks (object lifecycle not managed)
2. Failed callbacks remain in dict, processing every message
3. If callback holds references to large objects, memory accumulates
4. No automatic unsubscribe on persistent callback failure

**Recommended fix:**
```python
class TradingViewWebSocketProvider:
    def __init__(self, auth_token: str | None = None):
        # ... existing code ...
        self._callback_failures: dict[str, int] = {}  # Track failure count
        self._max_callback_failures = 3  # Threshold

    async def _handle_quote_update(self, params: list[Any]) -> None:
        # ... existing parsing code ...

        callback = self._subscriptions.get(symbol_key)
        if callback:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(quote_update)
                else:
                    callback(quote_update)

                # Reset failure count on success
                if symbol_key in self._callback_failures:
                    del self._callback_failures[symbol_key]

            except Exception as e:
                logger.error(
                    "tradingview_ws.callback_failed",
                    symbol=symbol_key,
                    error=str(e),
                    exc_info=True,  # Add traceback
                )

                # Track failures, auto-unsubscribe on threshold
                self._callback_failures[symbol_key] = (
                    self._callback_failures.get(symbol_key, 0) + 1
                )

                if self._callback_failures[symbol_key] >= self._max_callback_failures:
                    logger.error(
                        "tradingview_ws.callback_auto_unsubscribe",
                        symbol=symbol_key,
                        failure_count=self._callback_failures[symbol_key],
                    )
                    await self.unsubscribe(*symbol_key.split(":", 1))

    async def disconnect(self) -> None:
        self._running = False

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        # Clear all references to prevent memory leaks
        self._subscriptions.clear()
        self._callback_failures.clear()

        logger.info("tradingview_ws.disconnected")
```

**Impact:** HIGH - Memory accumulates over time, zombie callbacks waste CPU, can crash long-running services

---

### 3. Connection State Race: subscribe() vs disconnect() (Lines 111-124, 93-100)

**Location:** `subscribe()` and `disconnect()` methods

**Issue:**
```python
# Line 111-124: subscribe() checks connection but no lock
async def subscribe(self, symbol: str, exchange: str, callback: Callable) -> str:
    if self._ws is None:  # Check without lock
        raise RuntimeError("WebSocket not connected. Call connect() first.")

    # RACE: disconnect() can set _ws to None here
    symbol_key = f"{exchange}:{symbol}".upper()
    self._subscriptions[symbol_key] = callback
    await self._send_message("quote_add_symbols", ...)  # Can fail if disconnected mid-flight

# Line 93-100: disconnect() doesn't coordinate with subscribe()
async def disconnect(self) -> None:
    self._running = False

    if self._ws is not None:
        await self._ws.close()
        self._ws = None  # RACE: subscribe() can be between check and send
```

**Problem:** Classic TOCTOU (time-of-check-time-of-use) race condition:
1. subscribe() checks `_ws is not None`
2. Context switch, disconnect() sets `_ws = None`
3. subscribe() calls `_send_message()` → RuntimeError "WebSocket not connected"

**Recommended fix:**
```python
import asyncio

class TradingViewWebSocketProvider:
    def __init__(self, auth_token: str | None = None):
        # ... existing code ...
        self._connection_lock = asyncio.Lock()  # Add connection state lock

    async def connect(self) -> None:
        async with self._connection_lock:
            if self._ws is not None and self._ws.open:
                logger.warning("tradingview_ws.already_connected")
                return

            logger.info("tradingview_ws.connecting")
            # ... existing connect code ...

    async def disconnect(self) -> None:
        async with self._connection_lock:
            self._running = False

            if self._ws is not None:
                await self._ws.close()
                self._ws = None

            self._subscriptions.clear()

            logger.info("tradingview_ws.disconnected")

    async def subscribe(self, symbol: str, exchange: str, callback: Callable) -> str:
        async with self._connection_lock:
            if self._ws is None or not self._ws.open:
                raise RuntimeError("WebSocket not connected. Call connect() first.")

            symbol_key = f"{exchange}:{symbol}".upper()
            self._subscriptions[symbol_key] = callback
            await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
            logger.info("tradingview_ws.subscribed", symbol=symbol_key)
            return symbol_key
```

**Impact:** CRITICAL - Can cause runtime crashes, zombie subscriptions, data loss

---

## High Priority Findings

### 4. Type Safety: Missing Generic Type Parameters (Lines 12, 71)

**Location:** Import and `_subscriptions` dict

**Mypy errors:**
```
src\infrastructure\tradingview\websocket.py:12: error: Module "websockets.client" has no attribute "WebSocketClientProtocol"; maybe "ClientProtocol"?  [attr-defined]
src\infrastructure\tradingview\websocket.py:71: error: Missing type parameters for generic type "Callable"  [type-arg]
src\infrastructure\tradingview\websocket.py:219: error: Item "None" of "Any | None" has no attribute "__aiter__" (not async iterable)  [union-attr]
```

**Issues:**
1. Wrong import: `WebSocketClientProtocol` doesn't exist in `websockets.client`
2. Callback type not fully specified
3. Async iterator type check failure

**Recommended fix:**
```python
# Line 12: Fix import
from websockets.asyncio.client import ClientConnection  # Correct import for websockets 12+

# OR for older websockets:
from websockets.legacy.client import WebSocketClientProtocol

# Line 71: Add full type annotation
from collections.abc import Callable, Awaitable

class TradingViewWebSocketProvider:
    def __init__(self, auth_token: str | None = None):
        self._auth_token = auth_token
        self._ws: ClientConnection | None = None  # Fixed type
        self._session_id: str = ""
        # Specify callback signature fully
        self._subscriptions: dict[str, Callable[[dict[str, Any]], Awaitable[None] | None]] = {}
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

# Line 115: Update callback type hint
async def subscribe(
    self,
    symbol: str,
    exchange: str,
    callback: Callable[[dict[str, Any]], Awaitable[None] | None],  # Explicit sync/async union
) -> str:
    # ... existing code ...

# Line 219: Add type guard
if self._ws is not None:
    async for raw_data in self._ws:  # Type checker knows _ws is not None here
        # ... existing code ...
```

**Impact:** HIGH - Type safety broken, IDE autocomplete fails, runtime errors not caught

---

### 5. Error Handling: Reconnect Doesn't Clear Stale State (Lines 228-253)

**Location:** `run_forever()` exception handlers

**Issue:**
```python
# Line 228-253: Reconnect loop doesn't reset session state
except websockets.ConnectionClosed as e:
    logger.warning("tradingview_ws.connection_closed", ...)
    self._ws = None  # Only clears WebSocket

    if self._running:
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(...)
        # PROBLEM: _session_id from old connection still exists
        # Next connect() generates NEW session_id but old one never cleaned

except Exception as e:
    logger.error("tradingview_ws.error", error=str(e))
    # PROBLEM: No traceback logged, hard to debug
    # PROBLEM: Generic exception too broad
```

**Problems:**
1. Session ID not cleared on disconnect → confusion in logs
2. No traceback in error logs → debugging difficult
3. Generic `Exception` too broad → masks specific errors
4. Subscriptions resubscribed blindly without validation

**Recommended fix:**
```python
async def run_forever(self) -> None:
    self._running = True

    while self._running:
        try:
            if self._ws is None:
                await self.connect()

                # Resubscribe with error handling
                async with self._subscription_lock:
                    symbols_to_resubscribe = list(self._subscriptions.keys())

                for symbol_key in symbols_to_resubscribe:
                    try:
                        await self._send_message("quote_add_symbols", [self._session_id, symbol_key])
                    except Exception as e:
                        logger.error(
                            "tradingview_ws.resubscribe_failed",
                            symbol=symbol_key,
                            error=str(e),
                            exc_info=True,
                        )

            if self._ws is not None:
                async for raw_data in self._ws:
                    # ... existing message handling ...

        except websockets.ConnectionClosed as e:
            logger.warning(
                "tradingview_ws.connection_closed",
                code=e.code,
                reason=e.reason,
                session_id=self._session_id,  # Log session for correlation
            )
            self._ws = None
            self._session_id = ""  # Clear session ID

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay,
                )

        except asyncio.CancelledError:
            # Handle graceful shutdown
            logger.info("tradingview_ws.cancelled")
            await self.disconnect()
            raise

        except OSError as e:
            # Network errors (connection refused, timeout, DNS failure)
            logger.error(
                "tradingview_ws.network_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            self._ws = None
            self._session_id = ""

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay,
                )

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(
                "tradingview_ws.unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,  # Include full traceback
            )
            self._ws = None
            self._session_id = ""

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay,
                )
```

**Impact:** HIGH - Connection failures hard to diagnose, stale state causes confusion, generic exceptions hide root cause

---

### 6. Security: Auth Token Not Used (Lines 67-68, 76-91)

**Location:** Constructor and `connect()` method

**Issue:**
```python
# Line 67-68: Auth token stored but never used
def __init__(self, auth_token: str | None = None):
    self._auth_token = auth_token  # Stored but never referenced

# Line 76-91: Connection doesn't use auth
async def connect(self) -> None:
    logger.info("tradingview_ws.connecting")

    self._ws = await websockets.connect(
        WS_URL,  # No auth token in URL or headers
        ping_interval=30,
        ping_timeout=10,
        close_timeout=5,
    )
    # No authentication message sent
```

**Problems:**
1. Auth token parameter exists but unused → misleading API
2. TradingView may require auth for premium data → feature incomplete
3. No documentation explaining when auth is needed
4. If auth added later, all callers must change

**Recommended fix:**
```python
async def connect(self) -> None:
    logger.info("tradingview_ws.connecting")

    extra_headers = {}
    if self._auth_token:
        # TradingView WebSocket auth header (verify actual protocol)
        extra_headers["Authorization"] = f"Bearer {self._auth_token}"

    self._ws = await websockets.connect(
        WS_URL,
        ping_interval=30,
        ping_timeout=10,
        close_timeout=5,
        extra_headers=extra_headers if extra_headers else None,
    )

    self._session_id = _generate_session_id("qs")
    await self._send_message("quote_create_session", [self._session_id])

    # Send auth message if token provided (TradingView protocol-specific)
    if self._auth_token:
        await self._send_message("set_auth_token", [self._auth_token])

    await self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS])

    logger.info("tradingview_ws.connected", session_id=self._session_id, authenticated=bool(self._auth_token))
    self._reconnect_delay = 1.0
```

**Alternative:** If auth truly not needed, remove parameter:
```python
def __init__(self):
    # Remove auth_token parameter entirely
    self._ws: ClientConnection | None = None
    self._session_id: str = ""
    self._subscriptions: dict[str, Callable] = {}
    self._running = False
    self._reconnect_delay = 1.0
    self._max_reconnect_delay = 60.0
```

**Impact:** MEDIUM - Misleading API, potential feature incompleteness, security implications if auth required

---

## Medium Priority Improvements

### 7. Performance: Message Parsing Overhead (Lines 45-63)

**Location:** `_parse_messages()` function

**Issue:**
```python
# Line 45-63: Regex split + JSON parse every message
def _parse_messages(raw_data: str) -> list[dict[str, Any]]:
    messages = []

    pattern = r"~m~\d+~m~"
    parts = re.split(pattern, raw_data)  # Regex compilation on every call

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("~h~"):  # Heartbeat check after split
            continue
        try:
            data = json.loads(part)
            messages.append(data)
        except json.JSONDecodeError:
            pass  # Silently ignores invalid JSON
```

**Problems:**
1. Regex compiled on every call (inefficient)
2. Heartbeat messages split but discarded (wasted work)
3. JSON decode errors silently ignored (no logging)
4. Unnecessary string strip() for every part

**Recommended fix:**
```python
import re
from functools import lru_cache

# Compile regex once at module level
_MESSAGE_PATTERN = re.compile(r"~m~\d+~m~")

def _parse_messages(raw_data: str) -> list[dict[str, Any]]:
    """Parse TradingView WebSocket messages from raw data.

    Protocol format: ~m~<length>~m~<json>
    Heartbeats: ~h~<number>
    """
    messages = []

    # Filter heartbeats before splitting (more efficient)
    if raw_data.startswith("~h~"):
        return messages

    parts = _MESSAGE_PATTERN.split(raw_data)

    for part in parts:
        if not part or part.startswith("~h~"):
            continue

        try:
            data = json.loads(part.strip())
            messages.append(data)
        except json.JSONDecodeError as e:
            # Log parse errors for debugging
            logger.debug(
                "tradingview_ws.parse_error",
                raw_part=part[:100],  # Truncate for logging
                error=str(e),
            )

    return messages
```

**Impact:** MEDIUM - Repeated regex compilation wastes CPU, silent errors hide protocol issues

---

### 8. Connection Reliability: No Connection Validation After connect() (Lines 76-91)

**Location:** `connect()` method

**Issue:**
```python
# Line 76-91: Connection assumed successful after websockets.connect()
async def connect(self) -> None:
    logger.info("tradingview_ws.connecting")

    self._ws = await websockets.connect(...)  # Can succeed but server rejects

    self._session_id = _generate_session_id("qs")
    await self._send_message("quote_create_session", [self._session_id])
    await self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS])

    logger.info("tradingview_ws.connected", session_id=self._session_id)
    # No validation that server accepted session
```

**Problem:** TradingView server may reject session creation (rate limit, invalid auth, maintenance). No validation of server response.

**Recommended fix:**
```python
async def connect(self) -> None:
    logger.info("tradingview_ws.connecting")

    self._ws = await websockets.connect(
        WS_URL,
        ping_interval=30,
        ping_timeout=10,
        close_timeout=5,
    )

    self._session_id = _generate_session_id("qs")
    await self._send_message("quote_create_session", [self._session_id])
    await self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS])

    # Wait for confirmation (with timeout)
    try:
        confirmation_received = False
        start_time = asyncio.get_event_loop().time()
        timeout = 5.0  # 5 second timeout

        async for raw_data in self._ws:
            messages = _parse_messages(raw_data)
            for msg in messages:
                method = msg.get("m")
                if method == "quote_completed":
                    confirmation_received = True
                    break
                elif method in ("critical_error", "protocol_error"):
                    raise ConnectionError(f"TradingView rejected connection: {msg}")

            if confirmation_received:
                break

            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError("TradingView connection confirmation timeout")

        if not confirmation_received:
            raise ConnectionError("Connection closed before confirmation")

    except asyncio.TimeoutError:
        await self._ws.close()
        self._ws = None
        raise ConnectionError("TradingView connection timeout") from None

    logger.info("tradingview_ws.connected", session_id=self._session_id)
    self._reconnect_delay = 1.0
```

**Alternative (simpler):** Add timeout to first message exchange:
```python
async def connect(self) -> None:
    logger.info("tradingview_ws.connecting")

    try:
        self._ws = await asyncio.wait_for(
            websockets.connect(
                WS_URL,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            ),
            timeout=10.0,  # 10 second connection timeout
        )
    except asyncio.TimeoutError:
        raise ConnectionError("TradingView connection timeout") from None

    self._session_id = _generate_session_id("qs")

    try:
        await asyncio.wait_for(
            self._send_message("quote_create_session", [self._session_id]),
            timeout=5.0,
        )
        await asyncio.wait_for(
            self._send_message("quote_set_fields", [self._session_id, *QUOTE_FIELDS]),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        await self._ws.close()
        self._ws = None
        raise ConnectionError("TradingView session creation timeout") from None

    logger.info("tradingview_ws.connected", session_id=self._session_id)
    self._reconnect_delay = 1.0
```

**Impact:** MEDIUM - Connection can appear successful but be unusable, leading to subscription failures

---

### 9. Error Handling: Callback Failure Propagation (Lines 186-198)

**Location:** `_handle_quote_update()` callback execution

**Issue:**
```python
# Line 186-198: Callback exception caught but not tracked
callback = self._subscriptions.get(symbol_key)
if callback:
    try:
        if inspect.iscoroutinefunction(callback):
            await callback(quote_update)
        else:
            callback(quote_update)
    except Exception as e:
        logger.error(
            "tradingview_ws.callback_failed",
            symbol=symbol_key,
            error=str(e),
        )
        # Exception swallowed, no way for caller to know callback failed
```

**Problem:** Callbacks fail silently from caller's perspective. No metrics, no dead-letter queue, no retry mechanism.

**Recommended fix:** (Covered in Critical Issue #2, but add metrics)
```python
from collections import Counter

class TradingViewWebSocketProvider:
    def __init__(self):
        # ... existing code ...
        self._callback_errors = Counter()  # Track error counts

    async def _handle_quote_update(self, params: list[Any]) -> None:
        # ... existing parsing code ...

        callback = self._subscriptions.get(symbol_key)
        if callback:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(quote_update)
                else:
                    callback(quote_update)
            except Exception as e:
                self._callback_errors[symbol_key] += 1
                logger.error(
                    "tradingview_ws.callback_failed",
                    symbol=symbol_key,
                    error=str(e),
                    error_count=self._callback_errors[symbol_key],
                    exc_info=True,
                )

    def get_error_stats(self) -> dict[str, int]:
        """Get callback error statistics."""
        return dict(self._callback_errors)
```

**Impact:** MEDIUM - Callback failures invisible to monitoring, no alerting possible

---

### 10. Code Quality: Missing Module/Class Docstrings (Lines 1, 66)

**Location:** Module top and class definition

**Issue:**
```python
# Line 1: No module docstring
import asyncio
import inspect
# ... imports ...

# Line 66: No class docstring
class TradingViewWebSocketProvider:
    def __init__(self, auth_token: str | None = None):
```

**Problem:** No documentation explaining:
- What the WebSocket protocol is
- How to use the class
- Thread safety guarantees
- Lifecycle management

**Recommended fix:**
```python
"""TradingView WebSocket client for real-time quote streaming.

Protocol:
- Connection: wss://data.tradingview.com/socket.io/websocket
- Message format: ~m~<length>~m~<json>
- Heartbeat: ~h~<number>

Usage:
    provider = TradingViewWebSocketProvider()
    await provider.connect()

    await provider.subscribe(
        symbol="AAPL",
        exchange="NASDAQ",
        callback=lambda data: print(data),
    )

    await provider.run_forever()

Thread Safety:
- All methods are async and must be called from same event loop
- Subscriptions are NOT thread-safe (use locks for concurrent access)

Lifecycle:
- connect() → subscribe() → run_forever() → disconnect()
- Auto-reconnect on connection loss with exponential backoff
"""

class TradingViewWebSocketProvider:
    """WebSocket client for TradingView real-time quotes.

    Manages connection lifecycle, subscriptions, and message handling.
    Automatically reconnects on connection loss with exponential backoff.

    NOT thread-safe - all methods must be called from the same event loop.
    """

    def __init__(self, auth_token: str | None = None):
        """Initialize WebSocket provider.

        Args:
            auth_token: Optional TradingView authentication token (not currently used)
        """
```

**Impact:** LOW - Documentation gap, but code is relatively self-explanatory

---

## Low Priority Suggestions

### 11. Code Style: Heartbeat Logic Duplicated (Lines 200-205, 222-224)

**Location:** `_send_heartbeat()` and `run_forever()`

**Issue:**
```python
# Line 200-205: Dedicated heartbeat method
async def _send_heartbeat(self) -> None:
    if self._ws is not None:
        try:
            await self._ws.send("~h~1")
        except Exception as e:
            logger.debug("tradingview_ws.heartbeat_failed", error=str(e))

# Line 222-224: Inline heartbeat response
if "~h~" in raw_data:
    await self._send_heartbeat()
    continue
```

**Problem:** Two different heartbeat mechanisms (send vs respond). Confusing which is request vs response.

**Recommended fix:** Add clarifying comments:
```python
# Line 222-224: Respond to server heartbeat
if "~h~" in raw_data:
    # Server sent heartbeat, respond immediately
    await self._send_heartbeat()
    continue

async def _send_heartbeat(self) -> None:
    """Respond to server heartbeat request."""
    if self._ws is not None:
        try:
            await self._ws.send("~h~1")
        except Exception as e:
            logger.debug("tradingview_ws.heartbeat_failed", error=str(e))
```

**Impact:** LOW - Minor clarity improvement

---

### 12. Performance: is_connected() Property Could Be Cached (Lines 254-255)

**Location:** `is_connected()` method

**Issue:**
```python
def is_connected(self) -> bool:
    return self._ws is not None and self._ws.open
```

**Problem:** Checking `self._ws.open` may involve syscall (depending on websockets library implementation). Called frequently from external code.

**Recommended fix:**
```python
@property
def is_connected(self) -> bool:
    """Check if WebSocket connection is active."""
    return self._ws is not None and self._ws.open
```

**Impact:** LOW - Minor performance optimization, better API (property vs method)

---

### 13. Code Quality: Magic Number for Reconnect Delay (Lines 73-74, 237-241)

**Location:** Constructor and reconnect logic

**Issue:**
```python
# Line 73-74: Hardcoded values
self._reconnect_delay = 1.0
self._max_reconnect_delay = 60.0

# Line 237-241: Magic number 2 for backoff multiplier
self._reconnect_delay = min(
    self._reconnect_delay * 2,  # Why 2?
    self._max_reconnect_delay,
)
```

**Problem:** Backoff strategy hardcoded, not configurable, no documentation of why values chosen.

**Recommended fix:**
```python
# Module-level constants with documentation
INITIAL_RECONNECT_DELAY = 1.0  # Start with 1 second
MAX_RECONNECT_DELAY = 60.0  # Cap at 1 minute
RECONNECT_BACKOFF_MULTIPLIER = 2.0  # Exponential backoff

class TradingViewWebSocketProvider:
    def __init__(
        self,
        auth_token: str | None = None,
        initial_reconnect_delay: float = INITIAL_RECONNECT_DELAY,
        max_reconnect_delay: float = MAX_RECONNECT_DELAY,
        backoff_multiplier: float = RECONNECT_BACKOFF_MULTIPLIER,
    ):
        """Initialize WebSocket provider.

        Args:
            auth_token: Optional TradingView authentication token
            initial_reconnect_delay: Initial delay before reconnect (seconds)
            max_reconnect_delay: Maximum delay between reconnects (seconds)
            backoff_multiplier: Exponential backoff multiplier
        """
        self._auth_token = auth_token
        self._ws: ClientConnection | None = None
        self._session_id: str = ""
        self._subscriptions: dict[str, Callable] = {}
        self._running = False
        self._initial_reconnect_delay = initial_reconnect_delay
        self._reconnect_delay = initial_reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._backoff_multiplier = backoff_multiplier

    async def run_forever(self) -> None:
        # ... existing code ...

        if self._running:
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * self._backoff_multiplier,
                self._max_reconnect_delay,
            )

    async def connect(self) -> None:
        # ... existing code ...
        logger.info("tradingview_ws.connected", session_id=self._session_id)
        self._reconnect_delay = self._initial_reconnect_delay  # Reset on successful connect
```

**Impact:** LOW - Better configurability for testing, but current values are reasonable

---

## Positive Observations

1. **Clean async/await patterns** - All I/O operations properly async
2. **Structured logging** - Consistent use of context fields
3. **Exponential backoff** - Reconnect logic follows best practices
4. **Protocol encapsulation** - Message format well-isolated in helper functions
5. **Error tolerance** - JSON parse errors don't crash the connection
6. **Session management** - Clean session ID generation and lifecycle
7. **Callback flexibility** - Supports both sync and async callbacks

---

## Recommended Actions

### Immediate (Critical)

1. **Add locks for subscription dict access** (Issue #1)
   - Prevent race conditions between subscribe/unsubscribe/reconnect
   - Use `asyncio.Lock()` to protect `_subscriptions` mutations

2. **Implement callback lifecycle management** (Issue #2)
   - Track callback failures, auto-unsubscribe on threshold
   - Clear callbacks on disconnect to prevent memory leaks

3. **Fix connection state races** (Issue #3)
   - Add connection lock to coordinate subscribe/disconnect
   - Use TOCTOU-safe patterns

4. **Fix type annotations** (Issue #4)
   - Correct `WebSocketClientProtocol` import
   - Add full `Callable` type parameters
   - Pass mypy type checking

### High Priority

5. **Improve error handling in reconnect loop** (Issue #5)
   - Clear session ID on disconnect
   - Add tracebacks to error logs
   - Split generic Exception into specific types

6. **Implement or remove auth token** (Issue #6)
   - Either use auth token in connection protocol
   - Or remove parameter if not needed

7. **Add connection validation** (Issue #8)
   - Validate server accepted session creation
   - Add timeout to initial handshake

### Medium Priority

8. **Optimize message parsing** (Issue #7)
   - Move regex compilation to module level
   - Log JSON parse errors instead of silent ignore

9. **Add callback error metrics** (Issue #9)
   - Track error counts per symbol
   - Expose metrics via `get_error_stats()`

10. **Add documentation** (Issue #10)
    - Module and class docstrings
    - Protocol explanation
    - Usage examples

### Low Priority

11. Clarify heartbeat logic (Issue #11)
12. Convert `is_connected()` to property (Issue #12)
13. Extract reconnect config to constants (Issue #13)

---

## Metrics

- **Type Coverage:** Partial (3 mypy errors)
- **Linting Issues:** 0 (ruff passes)
- **Critical Issues:** 3 (race conditions, memory leaks, connection state)
- **High Priority:** 4 (type safety, error handling, security, connection validation)
- **Medium Priority:** 4 (performance, error propagation, connection reliability, docs)
- **Low Priority:** 3 (style, optimization, configurability)

---

## Unresolved Questions

1. **TradingView auth protocol** - Does TradingView WebSocket require authentication? If so, what's the protocol (header vs message)?
2. **Subscription limits** - Are there rate limits or max subscriptions per connection?
3. **Message ordering** - Does TradingView guarantee message ordering per symbol?
4. **Heartbeat interval** - Is `~h~1` response format correct? Should we send proactive heartbeats?
5. **Session expiry** - Do TradingView sessions expire? Should we proactively recreate sessions?
6. **Error messages** - What do `critical_error` and `protocol_error` messages contain? How should we handle them?
7. **Callback ownership** - Should this class own callback lifecycle, or should caller manage unsubscribe?

---

**Overall Recommendation:** Fix critical race conditions and memory leaks before production use. Connection reliability issues can cause data loss and silent failures. Type safety issues make debugging harder. Code is well-structured but needs defensive programming for production reliability.
