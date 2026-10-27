# Phase 04 — Backend dead-code deletion

- Commit (a): the OKX stack (`core/infra/brokers/okx/`, factory branch, settings, DI keys, `python-okx`, its tests), `core/common/idempotency/`, `tracked_symbol_seeder.py`, the `spa_fallback` mount, `scripts/recompute_backtest_costs.py`, and untrack `scripts/rubric/output/`.
- Commit (b): the backend rows of the merged review's "confirmed dead" table; the tick trigger and YAML-era strategy config; `core/domain/quote/`; `SignalGeneratedEvent`; `core/infra/http_client/`; `backtest_strategy_loader.py`; dead `JobScheduler` methods; `EventBus` test-only helpers; the paper LIMIT/pending path; and the tests and layout pins that only exercise them. Lower the ratchet ceilings.
- Keep `migrate_symbol_asset_class.py` (not yet run in prod).

Verify: gates in `plan.md` + full pytest.
