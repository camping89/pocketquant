# Phase 06 — Dead live-execution surface and risk check

- Delete `/trading/*` (route, `orders_positions_service.py`, the four `.bru` files, tests) and the `OrderAppService` / `PositionAppService` methods only it used.
- Delete `PUT /tracked-symbols/{symbol}` and its no-op service and repository method.
- Delete `DELETE /strategies/{code}` and the repository methods left without a caller.
- Delete the `PositionOpenedEvent` publish (no subscriber).
- `risk_check.py`: delete the no-op branch and dead methods, reject when `total_equity <= 0`, reject EXIT and FLAT signals.

Verify: gates + engine and app tests.
