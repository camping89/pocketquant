# Code review — cleanup commits d101f09c..44e8bc47

Status: findings fixed in the follow-up fix commit on `develop`.

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | Medium | Boot closed paper mirror rows (`is_closed=True`, exit = entry). `get_trades` reads closed rows, so each showed as a fake zero-P&L trade. | Boot deletes the open rows of paper subscriptions (`PositionRepository.delete_open_by_subscription`). |
| 2 | Medium | Boot closed rows of subscriptions missing from the venue set (e.g. Exness rows whose subscription lookup failed), while the venue snapshot still held the position → `_held_unmapped` blocked entries. | Only paper subscription rows are touched; every other row stays open. |
| 3 | Medium | `OrderAppService`: a failed `_order_repo.save` after a fill skipped the `OrderFilledEvent` publish (submit and `on_order_update`), so the mirror missed the fill. | `_save_after_fill` logs `order_save_failed` and never raises. |
| 4 | Low | `drop_positions` could race a queued `_fire_synthetic_exit`; the exit fill then opened an opposite ghost position. | The exit returns when the position is no longer the held one. |
| 5 | Low | The `sync_1m` cascade ran in `finally`, so a shutdown cancel still cascaded every symbol. | Only `Exception` is caught; a cancel skips the cascade. |
| note | Low | Unload left the mirror RAM entry and the open row. | `PositionAppService.drop` on paper unload. |

Tests: `tests/engine_test/test_paper_position_lifecycle.py`, `tests/engine_test/test_order_fill_save_failure.py`, `tests/app_test/unit/market_data/test_sync_jobs_tracked.py::test_a_cancelled_sync_skips_the_cascade`. Each new test fails without its fix.
