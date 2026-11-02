close_endpoint=DELETE /v1/trading/accounts/{account_id}/positions/{position_id}
close_body=none
pending_endpoint=POST /v1/trading/accounts/{account_id}/orders
pending_body=instrument, side, volume, type=stop, price, stop_loss_price, take_profit_price
cancel_endpoint=DELETE /v1/trading/accounts/{account_id}/orders/{order_id}
pending_order_id_field=order_id
link_field=order_id

# Phase 10 report: Exness close, pending stop and cancel

The Exness broker now closes a position by id, rests one pending stop per subscription, links the stop's fill back to its order by `deal.order_id`, and cancels a stop it tracks. Only `openPosition` and `placePendingOrder` are behind the live flag. A code review found gaps in how the adapter tracks a resting stop; they were fixed in this phase on kongming's advice. Live trading stays disarmed.

## Venue facts (Task 10.1)

Read from `.cache/exness_api.yaml` (saved 2026-11-01, 4503 lines) and the spike report "## Exness spec". No [ASK] was needed: all three ops and the order id field are in the spec.

- `closePosition` takes no body. `volume`, `price`, `deviation` and `close_by_position_id` are optional query parameters; with no `volume` the whole position closes (yaml lines 836-920).
- `NewStopOrderRequest` requires `instrument`, `side`, `type` (`stop`), `volume` and `price` (the trigger), with optional `stop_loss_price`, `take_profit_price` and `comment` (yaml lines 3376-3410).
- The placement ack (`AckResponse`) carries only `operation_id`, `client_request_id` and `status`, so the venue order id comes from the transaction event `payload.orders[].order_id` (`Order` schema, yaml lines 3068-3083).
- `Deal.order_id` is "Related order identifier, if the deal was created as a result of an order execution" (yaml lines 3230-3233), matching the spike note on line 1333.
- The snapshot `orders` list holds every active order, and an `sltp` order may have no `instrument` (yaml lines 1505, 1832-1836, 3072). Every position this broker opens carries an SL. So the snapshot check flags only `stop` and `limit` orders.

## Tests

- `tests/core_test/infra/exness/test_exness_client.py`: the fence test became `test_exposure_calls_are_refused_while_live_trading_is_off`, with two fenced cases (`openPosition`, `placePendingOrder`). Added `test_close_and_cancel_are_sent_while_live_trading_is_off` (two unfenced cases: `closePosition`, `cancelPendingOrder`), `test_close_and_pending_calls_use_the_order_lane` (3 cases) and `test_a_rate_limited_close_is_not_retried`. These 8 cases pass (A8). The file has 50 passed. `test_order_request_interval_uses_the_order_limits` passes unchanged.
- `tests/core_test/infra/brokers/exness/test_exness_pending_and_close.py` (new): 26 passed.
  - Task 10.3: the five planned close tests.
  - Task 10.4: the eight planned pending tests, plus `test_a_failed_cancel_keeps_the_stop_parked` and `test_a_parked_stop_is_not_unmapped_by_a_snapshot`.
  - Review fixes: `test_a_placement_event_before_the_ack_parks_the_stop`, `test_a_stop_parked_before_an_http_error_closes_the_gate`, `test_a_placement_event_after_an_http_error_closes_the_gate`, `test_a_fill_after_the_cancel_was_accepted_closes_the_gate`, `test_a_cancel_the_venue_refuses_later_blocks_the_instrument`, `test_a_close_the_venue_refuses_later_keeps_the_position`, `test_a_stop_gone_from_the_snapshot_is_released`, `test_a_stop_parked_after_the_snapshot_read_is_kept`, `test_parking_reruns_a_snapshot_that_waited_for_the_stop`, `test_a_placement_without_a_stop_order_is_dropped` and `test_a_manual_position_never_takes_a_subscription_row`.
- `test_exness_broker_adapter.py`:
  - The `:227` case now expects `market and stop orders only`.
  - `_FakeClient.call` answers the three new ops, and `_order` takes `stop_price`.
  - `test_fill_for_dropped_request_blocks_the_instrument` now checks that the gate closes at once and that the snapshot then blocks the instrument.
- `tests/core_test/infra/brokers/exness/conftest.py` (new, outside the planned file list, test-only): it holds the fresh-logger and watcher fixtures. Before, those were copied in the adapter test file and inline in `test_exness_open_path.py`; both copies were deleted. Without it the new tests that read captured logs failed when run after `tests/app_test`, because a logger cached by an earlier test ignores `capture_logs`. That order reproduced the 4 failures, and it passes after the fix (`314 passed`).
- Red before green: Task 10.2 ran `7 failed, 43 passed`; Tasks 10.3 and 10.4 ran `13 failed, 59 passed`.
- Task 10.4 Verify: `tests/core_test/infra/brokers/exness tests/engine_test` gave `297 passed` before the review fixes; the exness directory now gives `83 passed`.

## Review and advice

- A code-reviewer pass found that the adapter dropped its tracking of a resting stop:
  - when the venue accepted a cancel that could still fail or race a fill;
  - when an HTTP error came after the placement event;
  - when the venue state changed (filled while away, or cancelled in the Exness app).
- It also found that a snapshot could map an owner's manual position to a subscription's row, so an EXIT could close it.
- kongming advised a smaller design, now implemented:
  - An open deal this process cannot attribute (`exness.unattributed_open_deal`), a placed stop or limit it does not track (`exness.unattributed_pending_order`), and a refused close, cancel or dropped request (`exness.async_op_failed`) each close the order gate through a snapshot reconcile. The snapshot alone decides which instrument stays blocked.
  - A snapshot releases a parked stop it no longer lists, with a CANCELLED result. It checks only the stops parked before its read.
  - Positions mapped from our own fills claim their repo rows first.
  - A stop placement without a venue order id finishes CANCELLED.
- kongming's post-phase check: GO, with no blocking issue. The next risk it named is recovering a stop fill missed during a stream disconnect from the deals history, before live is armed. That gap is now a Limitations bullet.

## Docs (Task 10.5)

Verify printed `arch=5 deploy=2 pasted=0`. Both docs stay far under 800 lines.

Lines changed beyond the plan:
- The stale sentence "The Exness `close_position` is not built" was deleted from `docs/system-architecture.md`.
- The `Settings` comment in `src/pocketquant/core/config.py` now says the client refuses every call that opens exposure.
- Two Limitations bullets were added: a stop missing from the snapshot is reported cancelled, and a manual position on a traded instrument and side is ambiguous after a restart.
- The cancel-on-stop sentence now excludes a stop whose placement the stream has not confirmed.

## Close (Task 10.6)

- GATES: `Contracts: 6 kept, 0 broken.`; ratchet `exit=0`, with no metric ceiling change; `ruff check` `exit=0`.
- FULLSUITE: `4 failed, 1291 passed, 1 skipped, 55 warnings, 4 errors in 91.97s (0:01:31)`. The filtered FAILED/ERROR count prints `0`; the 4 failures and 4 errors are the known local tzset tests.

## Commits and CI

- `404a9d5028be466163f6d9d1485851defe103111` `feat(exness): close positions, rest and cancel pending stops`: code, tests, `docs/system-architecture.md`, `docs/deployment.md` (11 files). Pushed to `origin/develop`.
- CI run `41388201572` on that SHA: `completed success`.
- No metric ceiling change.

## Unresolved

- Recovering a stop fill missed during a stream disconnect, from the deals history by `order_id`, is not built. It is a Limitations bullet and must exist before live trading is armed.
- Whether a venue-triggered stop fill echoes the placement's `client_request_id` is unverified; the code links fills by `deal.order_id` only.

Result: PASS
