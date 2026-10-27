# Phase 02 — Fill-path safety

## Defects

- `engine/execution/order_app_service.py` `submit`: the `except` calls `order.reject()` after `fill()` already ran. That raises `InvalidOrderTransitionError` (no FILLED or SUBMITTED key in `_VALID_TRANSITIONS`, `core/domain/order/entities.py`). The strategy is told "rejected" while the paper broker holds the position.
- `core/common/messaging/event_bus.py` `publish`: one raising handler stops the later handlers, and it iterates the live list.
- `engine/execution/position_app_service.py` `_on_order_filled`: no error boundary.

## Steps

1. In `submit`'s `except`, reject only when `order.status is PENDING`; otherwise log with `exc_info` and re-raise.
2. `publish` iterates `list(handlers)`; each handler runs in try/except, logs with `exc_info`, and the loop continues.
3. Check every caller that relied on `publish` raising.
4. Tests: a save that raises after a paper fill leaves the order FILLED with no reject; a raising handler does not stop the next one.

## Verify

`uv run pytest tests/engine_test tests/core_test/unit/common -q`, plus the gates in `plan.md`.
