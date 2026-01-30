# TradingView WebSocket Provider - Test Analysis Report

**Date:** 2026-01-28
**Module:** `src/infrastructure/tradingview/websocket.py`
**Analysis Type:** Coverage Gap & Test Requirements

---

## Executive Summary

**CRITICAL ISSUE:** TradingView WebSocket provider has **ZERO test coverage** (0%). Module provides critical real-time data streaming functionality but lacks any unit, integration, or end-to-end tests.

**Current State:**
- Existing test suite: 23 tests, all passing
- Infrastructure module coverage: 0%
- WebSocket module lines: 259 (all uncovered)
- Overall project coverage: 7%

---

## Test Execution Results

### Command Executed
```bash
pytest -v --tb=short
pytest --cov=src/infrastructure --cov-report=term-missing
```

### Results Summary
- **Total Tests Run:** 23
- **Passed:** 23 (100%)
- **Failed:** 0
- **Skipped:** 0
- **Coverage (infrastructure):** 0% (562 statements, 562 missed)

### Test Output
```
============================= test session starts =============================
tests/unit/common/test_event_bus.py::test_event_bus_* ............... PASSED
tests/unit/common/test_mediator.py::test_mediator_* ................. PASSED
tests/unit/domain/test_domain_purity.py::test_domain_* .............. PASSED
tests/unit/domain/test_value_objects.py::Test* ...................... PASSED

============================== 23 passed in 0.06s ========================
```

---

## Coverage Analysis

### Current Coverage by Module

| Module | Statements | Missing | Coverage | Status |
|--------|-----------|---------|----------|--------|
| websocket.py | 154 | 154 | **0%** | ❌ CRITICAL |
| provider.py | 59 | 59 | **0%** | ❌ CRITICAL |
| base.py | 9 | 9 | **0%** | ❌ CRITICAL |
| **Total Infrastructure** | **562** | **562** | **0%** | ❌ CRITICAL |

### Line-by-Line Gaps in websocket.py

**Uncovered Functions (by line ranges):**

1. **Lines 34-37:** `_generate_session_id()` - Session ID generation
2. **Lines 40-42:** `_create_message()` - Message encoding
3. **Lines 45-63:** `_parse_messages()` - Message parsing logic
4. **Lines 66-75:** `TradingViewWebSocketProvider.__init__()` - Initialization
5. **Lines 76-91:** `connect()` - Connection establishment
6. **Lines 93-100:** `disconnect()` - Connection cleanup
7. **Lines 102-109:** `_send_message()` - Raw message transmission
8. **Lines 111-124:** `subscribe()` - Symbol subscription
9. **Lines 126-140:** `unsubscribe()` - Symbol unsubscription
10. **Lines 142-153:** `_handle_message()` - Message routing
11. **Lines 155-198:** `_handle_quote_update()` - Quote processing (incl. callbacks)
12. **Lines 200-205:** `_send_heartbeat()` - Keep-alive mechanism
13. **Lines 207-252:** `run_forever()` - Main event loop + reconnection logic
14. **Lines 254-259:** `is_connected()` & `subscription_count` property - State queries

---

## Critical Missing Test Coverage

### 1. Utility Functions (Helper Logic)

**`_generate_session_id(prefix: str = "qs")`**
- Expected behavior: Generates unique session IDs with format `{prefix}_{12 random chars}`
- Missing tests:
  - ✗ Session ID format validation (prefix + 12 char suffix)
  - ✗ Randomness & uniqueness across multiple calls
  - ✗ Custom prefix support

**`_create_message(method: str, params: list) → str`**
- Expected behavior: Creates TradingView protocol message with format `~m~{length}~m~{json}`
- Missing tests:
  - ✗ Correct message framing with length calculation
  - ✗ JSON serialization of params
  - ✗ Edge cases: empty params, special characters, large payloads
  - ✗ Protocol compliance validation

**`_parse_messages(raw_data: str) → list[dict]`**
- Expected behavior: Extracts JSON messages from TradingView frame format
- Missing tests:
  - ✗ Single message parsing
  - ✗ Multiple messages in single raw_data
  - ✗ Heartbeat filtering (`~h~`)
  - ✗ Malformed JSON handling (should skip silently)
  - ✗ Empty/whitespace-only frames
  - ✗ Protocol compliance (frame delimiters `~m~`)

### 2. Connection & Lifecycle Management

**`TradingViewWebSocketProvider.__init__(auth_token: str | None = None)`**
- Expected behavior: Initialize provider with optional auth, set defaults
- Missing tests:
  - ✗ Default state initialization (running=False, reconnect_delay=1.0)
  - ✗ Auth token storage

**`connect() → None`**
- Expected behavior: Establish WebSocket connection, create session, configure fields
- Missing tests:
  - ✗ Successful connection to `wss://data.tradingview.com/socket.io/websocket`
  - ✗ Session ID generation & assignment
  - ✗ `quote_create_session` message sent
  - ✗ `quote_set_fields` message sent with QUOTE_FIELDS
  - ✗ Connection parameters (ping_interval=30, ping_timeout=10, close_timeout=5)
  - ✗ Reconnect delay reset to 1.0
  - ✗ Error handling: connection refused, timeout, DNS failure
  - ✗ Already connected state (should reinitialize)

**`disconnect() → None`**
- Expected behavior: Close connection, reset state, set running=False
- Missing tests:
  - ✗ WebSocket closure (`ws.close()`)
  - ✗ Running flag set to False
  - ✗ WS reference cleared (None)
  - ✗ Multiple disconnect calls (idempotent)
  - ✗ Disconnect when already disconnected

### 3. Subscription Management

**`subscribe(symbol: str, exchange: str, callback: Callable) → str`**
- Expected behavior: Register symbol subscription & send subscription message
- Missing tests:
  - ✗ Symbol key formatting (`{EXCHANGE}:{SYMBOL}` uppercase)
  - ✗ Callback registration in `_subscriptions` dict
  - ✗ `quote_add_symbols` message sent with correct params
  - ✗ Return value: symbol_key
  - ✗ Duplicate subscription handling (replace callback)
  - ✗ Error: subscribe without connection (RuntimeError)
  - ✗ Multiple concurrent subscriptions

**`unsubscribe(symbol: str, exchange: str) → None`**
- Expected behavior: Remove subscription & send unsubscribe message
- Missing tests:
  - ✗ Symbol key removal from dict
  - ✗ `quote_remove_symbols` message sent
  - ✗ Graceful handling: unsubscribe non-existent symbol
  - ✗ Idempotency (multiple unsubscribes)
  - ✗ Unsubscribe when disconnected (silent return)

### 4. Message Handling & Data Processing

**`_handle_message(message: dict) → None`**
- Expected behavior: Route messages by method type (qsd, quote_completed, error types)
- Missing tests:
  - ✗ Quote update routing (`method == "qsd"`)
  - ✗ Quote completed handling
  - ✗ Critical error logging
  - ✗ Protocol error logging
  - ✗ Unknown method type handling (silent)
  - ✗ Malformed message (missing `m` or `p` keys)

**`_handle_quote_update(params: list) → None`**
- Expected behavior: Extract quote data, invoke callbacks (sync + async)
- Missing tests:
  - ✗ Quote data extraction from params
  - ✗ Quote object creation with correct field mapping:
    - `lp` → `last_price`
    - `volume` → `volume`
    - `bid` → `bid`
    - `ask` → `ask`
    - `ch` → `change`
    - `chp` → `change_percent`
    - `open_price` → `open_price`
    - `high_price` → `high_price`
    - `low_price` → `low_price`
    - `prev_close_price` → `prev_close`
  - ✗ Timestamp generation (datetime.now(UTC))
  - ✗ Symbol key validation (must contain `:`)
  - ✗ Callback execution (sync function)
  - ✗ Callback execution (async function with await)
  - ✗ Callback exception handling (logged, not re-raised)
  - ✗ Wrong session ID filtering (params[0] != self._session_id)
  - ✗ Invalid params length (< 2)
  - ✗ Missing/empty quote data handling

### 5. Heartbeat & Keep-Alive

**`_send_heartbeat() → None`**
- Expected behavior: Send heartbeat frame (`~h~1`) to maintain connection
- Missing tests:
  - ✗ Heartbeat message format (`~h~1`)
  - ✗ Silent failure handling (exception logging only)
  - ✗ Behavior when not connected (skip)

### 6. Main Event Loop & Reconnection

**`run_forever() → None`**
- Expected behavior: Infinite read loop with auto-reconnect on failure
- Missing tests:
  - ✗ Loop starts with `running=True`
  - ✗ Auto-connect if `_ws is None`
  - ✗ Re-subscribe existing symbols on reconnect
  - ✗ Message streaming from WebSocket
  - ✗ Heartbeat response handling (skip, send response)
  - ✗ Message parsing & routing
  - ✗ Break loop when `running=False`
  - ✗ ConnectionClosed exception handling:
    - Log warning with code/reason
    - Set `_ws = None`
    - Sleep with exponential backoff
    - Double reconnect_delay (cap at 60s)
  - ✗ Generic exception handling:
    - Log error
    - Set `_ws = None`
    - Sleep with exponential backoff
  - ✗ Long-running stability (doesn't hang)

### 7. State Queries

**`is_connected() → bool`**
- Expected behavior: Return True if `_ws` exists and socket is open
- Missing tests:
  - ✗ Connected state (True when `_ws.open`)
  - ✗ Disconnected state (False when `_ws is None`)
  - ✗ Closed but non-None socket (False)

**`subscription_count → int`**
- Expected behavior: Return count of active subscriptions
- Missing tests:
  - ✗ Returns length of `_subscriptions` dict
  - ✗ Increases after subscribe()
  - ✗ Decreases after unsubscribe()

---

## Error Scenarios NOT Covered

### Network Errors
- ✗ Connection timeout
- ✗ Connection refused
- ✗ DNS resolution failure
- ✗ SSL/TLS certificate validation
- ✗ Abrupt connection close (no close frame)
- ✗ Network interruption mid-message

### Protocol Errors
- ✗ Invalid frame format
- ✗ Truncated JSON message
- ✗ Missing required fields in quote update
- ✗ Out-of-order heartbeat/data frames
- ✗ Server sends invalid session ID

### Callback Errors
- ✗ Sync callback raises exception
- ✗ Async callback raises exception
- ✗ Callback never completes (timeout scenario)
- ✗ Callback modifies subscription dict during iteration

### Edge Cases
- ✗ Subscribe to same symbol twice (should replace callback)
- ✗ Unsubscribe while message is being processed
- ✗ Disconnect while reconnecting
- ✗ Very large payloads (protocol limits)
- ✗ High-frequency message bursts
- ✗ Reconnect delay exponential backoff exhaustion (cap at 60s)

---

## Test Infrastructure Assessment

### Available Testing Tools
- ✅ **pytest** v9.0.2
- ✅ **pytest-asyncio** v1.3.0 (async test support)
- ✅ **pytest-cov** v7.0.0 (coverage reporting)
- ⚠️ **Mock/Patch:** Standard library `unittest.mock` (not imported yet)
- ⚠️ **WebSocket Mock:** Need `pytest-asyncio` fixtures + mock websockets

### Existing Test Patterns
1. **Async test support:** Configured with `asyncio_mode = "auto"` in `pyproject.toml`
2. **Fixtures:** `conftest.py` has Settings, Mediator, EventBus fixtures
3. **Test structure:** `tests/unit/{domain,common,features}/test_*.py`

### Required Test Dependencies
- `pytest-mock` or `unittest.mock` (built-in)
- `websockets` mock/patching strategy (consider `unittest.mock.AsyncMock`)
- Potential: `pytest-asyncio-timeout` for timeout testing

---

## Recommended Test Suite Structure

### Phase 1: Unit Tests (High Priority)
```
tests/unit/infrastructure/tradingview/
├── test_websocket_helpers.py          # _parse_messages, _create_message, _generate_session_id
├── test_websocket_connection.py       # connect, disconnect, is_connected
├── test_websocket_subscriptions.py    # subscribe, unsubscribe, subscription_count
├── test_websocket_messaging.py        # _send_message, _handle_message, _handle_quote_update
├── test_websocket_callbacks.py        # Sync & async callback execution
├── test_websocket_events.py           # Heartbeat, reconnection logic
└── test_websocket_integration.py      # Full run_forever() cycle
```

### Phase 2: Integration Tests (Medium Priority)
```
tests/integration/tradingview/
├── test_websocket_real_connection.py  # Against actual TradingView (requires credentials)
└── test_websocket_with_quote_handler.py  # Integration with QuoteServiceState
```

### Phase 3: End-to-End Tests (Lower Priority)
```
tests/e2e/
└── test_quote_streaming.py            # Full data flow: WebSocket → Cache → Bar Manager
```

---

## Coverage Goals & Success Criteria

### Minimum Viable Coverage
- **Target:** 80% coverage for `websocket.py` (min 123/154 lines)
- **Critical paths:** Connection, subscription, message handling, reconnection
- **Error scenarios:** At least 3 tests per major function

### Comprehensive Coverage (Recommended)
- **Target:** 95% coverage for `websocket.py` (min 146/154 lines)
- **All code paths:** Including error handlers, edge cases, state combinations
- **Callback variations:** Both sync & async, exception handling

### Success Criteria Checklist
- [ ] All 154 lines in websocket.py covered
- [ ] 50+ individual test cases
- [ ] Error scenarios tested (network, protocol, callback failures)
- [ ] Async operations properly validated
- [ ] Reconnection logic verified with timing
- [ ] All callbacks (sync/async) tested
- [ ] Integration with quote handler validated
- [ ] CI/CD pipeline passing

---

## Implementation Recommendations

### High-Priority Tests (Write First)
1. **Message parsing** (`_parse_messages`) - Complex regex logic, easy to test
2. **Message creation** (`_create_message`) - Deterministic, protocol-critical
3. **Session ID generation** (`_generate_session_id`) - Format validation
4. **Quote data extraction** (`_handle_quote_update`) - Field mapping is critical
5. **Subscription lifecycle** (`subscribe`/`unsubscribe`) - State management

### Medium-Priority Tests
6. Connection establishment & teardown
7. Reconnection logic with exponential backoff
8. Callback execution (sync & async)
9. Heartbeat mechanism

### Lower-Priority Tests (Consider Later)
10. End-to-end integration with QuoteServiceState
11. Real TradingView connection (requires credentials, slow)
12. Performance/load testing (high-frequency messages)

---

## Risk Assessment

### Critical Risks (No Tests)
- ✗ WebSocket connection may fail silently without proper error handling validation
- ✗ Reconnection logic untested; could enter infinite loops or incorrect backoff
- ✗ Callback exceptions could crash the main event loop (if not properly caught)
- ✗ Message parsing bugs could silently drop valid quotes
- ✗ Session state corruption undetectable without integration tests

### Data Quality Risks
- ✗ No validation of quote field mappings (could persist incorrect data)
- ✗ Timestamp generation not mocked; tests would have timing dependencies
- ✗ No tests for handling missing/null values in quote updates

### Operational Risks
- ✗ Backoff delay logic could exceed 60s max (untested)
- ✗ Memory leaks in long-running loops (untested)
- ✗ Subscription dict not thread-safe if accessed outside async context

---

## Questions for Product/Architecture Team

1. **Auth Token Usage:** The `__init__` accepts `auth_token` parameter but it's never used in the code. Is this intended? Should it be passed to WebSocket URL or headers?

2. **Error Recovery Strategy:** Should the provider attempt infinite reconnects, or should it have a maximum retry limit before giving up?

3. **Callback Timeout:** Should async callbacks have a timeout? Current code will wait indefinitely.

4. **Message Ordering:** Are quote updates guaranteed to be in-order? Any need for sequence number validation?

5. **Session Persistence:** If session ID becomes invalid during runtime, should we detect and reinitialize?

6. **Subscription Limits:** Is there a maximum number of symbols that can be subscribed? Any rate limiting?

---

## Next Steps

1. **Create test fixtures** for mocking WebSocket connections
2. **Write unit tests** for helper functions (message parsing/creation)
3. **Write unit tests** for message handling logic
4. **Implement mock WebSocket provider** for connection/subscription tests
5. **Write integration tests** with actual QuoteServiceState usage
6. **Measure coverage** and identify remaining gaps
7. **Document test patterns** for future contributors
8. **Set up CI/CD checks** to enforce minimum coverage (80%+)

---

## Summary

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Coverage | 0% | 80%+ | ❌ CRITICAL |
| Tests | 0 | 50+ | ❌ CRITICAL |
| Error scenarios | 0% | 80%+ | ❌ CRITICAL |
| Integration tests | 0 | 5+ | ❌ CRITICAL |
| Documentation | Missing | Complete | ⚠️ NEEDED |

**Conclusion:** TradingView WebSocket provider is production-critical but untested. Creating comprehensive test suite is **URGENT** before expanding feature usage. Recommend starting with Phase 1 unit tests (estimated 3-4 days work, 50+ test cases).
