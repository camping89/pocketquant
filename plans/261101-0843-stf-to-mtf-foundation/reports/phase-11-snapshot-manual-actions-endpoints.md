# Phase 11 report: snapshot ring, manual actions, read endpoints

Every decided bar now adds a generic record to a 20-entry ring per subscription. While the trader holds the lease, it writes each live bar's ring to `strategy:snapshot:{subscription_id}` with a 7-day TTL. `POST /subscriptions/{id}/close|cancel` stores one manual action. The lease holder's reconcile tick attempts it, clears it, and records the outcome on the row and in the ring. The API serves the snapshot, the recent orders and an enriched subscription list. Five subscription reads now need the admin token. Live trading stays disarmed.

## Tests

- `tests/engine_test/test_strategy_snapshot.py` (new): 8 passed. It covers the seven-day write, the 20-entry ring, the outcomes (`sent`, `skipped:inflight`, `rejected:zero position size`, `skipped:stop_unchanged`, `skipped:nothing_open`), `pending` as `{side, price}`, no write without the lease, warm-up records kept in memory only, a failed write that never blocks the bar, and unload dropping the ring.
- `tests/engine_test/test_manual_action.py` (new): 10 passed. It covers the nine planned tests plus `test_close_with_only_a_stop_cancels_it`, which tests the spec rule "accepted when the stop was cancelled".
- `tests/core_test/infra/persistence/test_subscription_repository.py`: the three new action tests pass.
- `tests/core_test/infra/persistence/test_live_order_repository.py` (new): 1 passed.
- `tests/engine_test/test_strategy_reconcile_service.py`: three new tests pass, and the clear-with-outcome test runs as two parametrized cases. The file gained an autouse `_fresh_logger` fixture (see the Verify notes below).
- `tests/engine_test/test_strategy_service.py`: `test_list_symbols_adds_position_snapshot_and_action` and `test_get_orders_maps_orders` pass; the `_query_svc` helper gained `order_repo` and `cache`.
- `tests/app_test/integration/test_strategy_subscriptions_api.py`: `test_close_returns_202_then_409_while_pending`, `test_cancel_on_a_missing_subscription_is_404`, `test_snapshot_is_an_empty_list_before_any_bar` and `test_orders_limit_is_bounded` pass.
- `tests/app_test/integration/test_admin_token_guard.py`: 7 passed. That includes the three new read-guard tests and the two tests whose open read moved to `GET {prefix}/strategies/`.
- The six touched persistence, engine and app files: 84 passed together.

## Spec deviation

- The plan's "zero-balance signal gives `rejected:zero position size`" cannot happen. The risk check rejects a zero balance first with `Insufficient balance`. The test reaches `rejected:zero position size` with a stop at the close, which leaves no price risk; a comment in the test says so.

## Outcome choices the spec left open

- A re-published bar returns no outcome and adds no record. A strategy that raises records `skipped:strategy_error`.
- An EXIT with no position but a pending stop records `sent` when the cancel succeeds and `rejected:cancel_failed` when it fails. An entry whose pending-stop cancel fails records `rejected:pending cancel failed`.

## Guard

- Mutation guard count: `20`.
- Guarded reads: `{prefix}/subscriptions/`, `{prefix}/subscriptions/{sub_id}/positions`, `/trades`, `/snapshot` and `/orders`.
- The web still sends the token only on mutations. Phase 13 Task 13.1 adds it on these reads. Nothing deploys from `develop` (the `cicd.yml` build and deploy jobs run only on `master`).

## Gates

- `lint-imports`: `Contracts: 6 kept, 0 broken.`
- `ruff check src tests scripts`: exit 0.
- Strategy-agnostic grep: `0`.
- Metric ceiling: `max_delegations` was raised from 74 to 75 in its own commit. The new `get_subscription_orders` route is a pure delegation, which is the standard route shape in this codebase.
- FULLSUITE tail: `4 failed, 1326 passed, 1 skipped, 63 warnings, 4 errors in 140.64s (0:02:20)`. The extra-failure count is `0`.

## Verify notes

- The first FULLSUITE run printed `5 failed`. The extra failure was `test_an_action_without_an_instance_is_cleared_with_a_warning`: the warning was emitted, but `capture_logs` did not see it. kongming confirmed the cause from the structlog source and reproduced it. `setup_logging` caches the logger on first use, and the app tests reconfigure structlog before the engine tests run. The fix is the repo's usual pattern: an autouse fixture that rebinds the reconcile module logger. The rerun passed.
- kongming's end-of-phase review returned GO with no must-fix defects. It flagged four risks to watch:
  - `manual_action` takes no engine lock, so a venue bar's stop cancel can race it. The outcome heals itself and the owner retries. Watch for this in the Phase 16 and 17 paper runs.
  - A venue ring records `sent` when the task spawns, so a later in-task rejection never reaches the ring, and `pending` lags one bar on Exness.
  - The catch-all `rejected:{e}` stores exception text in the ring.
  - The subscription list now reads Redis through `mget`, so a Redis outage turns the list into a 500.

## Commits and CI

- `c6400df9` feat(strategy): snapshot ring, manual close and cancel, guarded subscription reads
- `85fcb1c0` chore(metrics): raise the code metric ceiling
- CI run `41391737485` on `85fcb1c017986c0a0a05980705267fc0e5130b59`: `completed success`.

Result: PASS
