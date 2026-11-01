# Phase 06 report: subscription contract

A subscription now stores an ordered `intervals` list, strategy `parameters` checked by `check_strategy_inputs`, and a scalar `intervals_key` under the unique index `ix_subscriptions_dedup_intervals`. `PATCH /subscriptions/{id}` edits a stopped, flat subscription. The template endpoint serves `DEFAULTS`. The reconcile loop reloads an edited instance that is not running.

## Entry gate

`dirty=0 synced=yes`; Phase 05 report ends `Result: PASS`; registry length `0`; `docker-ok`.

## Test-first red outputs

- 06.1: `ImportError: cannot import name 'check_strategy_inputs'` at collection; the subscription domain file alone ran `8 failed, 1 passed`.
- 06.2: `6 failed, 6 passed` in `test_subscription_repository.py`.
- 06.3: `27 failed, 11 passed` across `test_strategy_service.py`, `test_strategy_subscriptions_api.py` and `test_admin_token_guard.py`.
- 06.4: `2 failed, 91 passed`. The two failures were `test_an_edited_stopped_subscription_reloads_its_config` and `test_degrees_of_freedom_count_the_declared_defaults`. `test_a_running_subscription_is_never_reloaded` passed before the change, as expected, because reconcile skipped every loaded instance.

## Verify outputs

- 06.1: `156 passed, 1 warning`.
- 06.2: `12 passed, 2 warnings`.
- 06.3: `readers=0 tests=505 passed, 1 skipped, 52 warnings in 98.76s`.
- 06.4: `doc=0 tests=93 passed, 1 warning`.

## Test sites changed

- 31 `interval=` keywords in `StrategyConfig(` and `Subscription(` calls were rewritten across 21 test files by one AST pass: `[x]` for `StrategyConfig`, `(x,)` for `Subscription`, and `[i.value for i in sub.intervals]` where a config was built from a subscription.
- 3 more sites were edited by hand: the `_sub` helper and the round-trip test in `test_subscription_desired_actual_state.py`, and `_make_sub` in `test_subscription_repository.py`.
- No test writes a raw `subscriptions` document, so no raw document changed.
- 9 `svc.load(...)` calls in `test_strategy_reconcile_service.py` now pass the subscription.

## Additions beyond the listed tests

- `test_edit_refuses_when_the_subscription_started_meanwhile` covers the `update_config` result `0` mapping to `SUBSCRIPTION_RUNNING`. The phase asks for that mapping but names no test for it.

## CLOSE

- GATES: `Contracts: 6 kept, 0 broken.`; ruff `All checks passed!`; ratchet exit 0 after the raise below. The first ruff run failed with two `I001` import-order errors in test files edited here. `ruff check --fix` repaired them on kongming's advice.
- FULLSUITE: `4 failed, 1200 passed, 1 skipped, 55 warnings, 4 errors in 120.67s (0:02:00)`; unexpected count `0`.
- CI: run `41324586952` on `184a9215` printed `completed success`. The jobs `web`, `tests (UTC)`, `tests (Asia/Ho_Chi_Minh)` and `tests (America/Chicago)` all succeeded.

## Ratchet raise

- `uv run python scripts/code_metrics.py --ratchet` failed with `tiny_share 0.4813 > 0.4811` and `delegations 74 > 73`.
- The delegation came from the new PATCH route, which has the same one-line shape as every route. The tiny share rose with the small helpers `_invalid`, `_running` and `_sub_dict`.
- kongming advised raising the ceilings and inlining no helper. `max_tiny_share` went from 0.4811 to 0.4813 and `max_delegations` from 73 to 74, in their own commit `0987a014` `chore(metrics): raise the code metric ceiling`.

## Commits

`0987a014` `chore(metrics): raise the code metric ceiling` and `184a9215` `feat(subscription): ordered intervals and strategy parameters`. Both are on `origin/develop`.

## Handover to Phase 07 (kongming go/no-go: GO)

- `check_strategy_inputs` matches a parameter's type against its default's type. A `None` default would reject every value, and a `tuple` default would reject JSON lists. `DEFAULTS` must use concrete scalar or list values.
- Reconcile compares the loaded config's `(intervals, parameters)` with the document. A strategy that writes merged defaults back into `self.config.parameters` would make the two differ forever, so a stopped instance would reload on every tick. Strategies must read `config.parameters` and never change it.
- The edit exposure check filters `OrderRepository.find_pending()`, which returns at most 500 orders system-wide. kongming accepted this for a single-user system.
- The web create dialog still posts `interval` and will get 422 until Phase 13.

Result: PASS
