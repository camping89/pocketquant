---
name: phase09-doubles-outside-files-list
description: Phase 09 Task 09.4 (2026-11-02) - engine contract change (every broker subscribes on_order_update; stop_strategy calls pending_stop) broke 4 test doubles not in the phase Files list; advised patching the doubles, not the engine
metadata:
  type: project
---

Phase 09 Task 09.4 (plan 261101-0843, 2026-11-02): 17 pre-existing engine tests failed only because
their doubles predate the new contract (`_FakeBroker` without `subscribe_order_updates`,
`_RecordingOrderService` without `on_order_update`/`pending_stop`, bare `AsyncMock()`/`MagicMock()`
order services whose `pending_stop()` returns a truthy mock). Advised GO on patching the four test
files minimally and NO on getattr guards in the engine.

**Why:** the doubles implement the contract the task changed; a plan Files list is a stateful
record, not a scope fence, and guards for fakes weaken production code. Exness rejects non-MARKET
orders (adapter `submit_order`), so the Exness cancel path is unreachable in this phase.

**How to apply:** when a later phase widens IBrokerPort or OrderAppService again, expect the same
doubles to break; record the Files-list deviation in the phase report rather than skipping tests.
A bare `AsyncMock()` order service needs `pending_stop = MagicMock(return_value=None)` or the engine
sees a coroutine as a pending order.
