# Phase 13 report: Generic subscription UI

## Entry gate

- EG (1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG (2) `HEAD` = `origin/develop` = `8d68fea21a872c54ebe7853a65ba9e06bec68104`.
- EG (3) `reports/phase-12-backtest-ui.md` ends with `Result: PASS`.
- Gate 2: the literal command fails in Git Bash (`fatal: ... Invalid content of \{\}`): `git grep -E` rejects `\{`. The equivalent `git grep -n -E "/[{]sub_id[}]/(close|cancel|snapshot|orders)" -- src/pocketquant/app/routes` finds 4 routes (`strategy.py:108,117,144,152`), so the gate passes (`>= 4`).
- Gate 3: `1`. Gate 4: `2`. Gate 5: `ok`.

## Response keys copied (Task 13.1)

From `StrategyQueryService.list_symbols`, `get_orders`, `get_trades`, `StrategyAppService._bar_record`, `manual_action`, `_record_snapshot` and `SubscriptionRepository.clear_action`:

- List row: `id, strategy_code, symbol, intervals, parameters, created_at, desired_state, actual_state, is_running, broker, position, snapshot, manual_action, manual_action_outcome`.
- `position`: `direction, entry_price, quantity, sl_price, tp_price, unrealized_pnl`.
- `manual_action_outcome`: `{action, outcome, at}` (`at` is a datetime, serialized as an ISO string).
- Snapshot entry: `bar_start, interval, readings, decision, outcome, pending`; `pending = {side, price} | null`; a manual-action record has `interval: null`, `readings: []`, `decision: {action: "manual_<action>", reason: "owner request"}`.
- `/orders` row: `id, side, order_type, status, quantity, price, stop_price, sl_price, tp_price, filled_price, created_at, updated_at`.
- `/trades` row: `id, direction, entry_price, exit_price, entry_time, exit_time, pnl, quantity`.

No key differs from the phase file.

## Verify outputs

- Task 13.1: `exit=0` (api-client tests 8 passed); bare subscription fetch count `0` (after Task 13.4 deleted `use-open-position.ts`).
- Task 13.2: `exit=0` (29 tests passed).
- Task 13.3: `new-subscription-dialog.tsx` gone; `NewSubscriptionDialog` count `0`.
- Task 13.4: `tsc -b` `exit=0`; `sub.interval` / `useOpenPosition` count `0`; lint `0 errors` (6 warnings, all in files this phase does not touch).

## Gates

- AGNOSTIC: `0`.
- GATES: `Contracts: 6 kept, 0 broken.`; ratchet exit 0; ruff exit 0; `tsc -b` exit 0; lint `0 errors`; vitest 11 files, 105 tests passed.
- FULLSUITE: `4 failed, 1326 passed, 1 skipped, 63 warnings, 4 errors in 130.96s (0:02:10)`; unexpected failure count `0`.

## Review

A code-reviewer pass found one High and two Medium defects, all fixed before the owner's look:

- The drawer's Close / Cancel confirm rendered inside `.drawer`, whose `transform` makes it the containing block of the fixed overlay, so the dialog scrolled with the drawer. It now renders as a sibling of the drawer.
- Delete was enabled while a subscription was starting. It now needs both states stopped, like Edit.
- A confirm dialog stayed armed after its precondition lapsed (position closed, pending filled, action queued, subscription started). It now closes.
- Low fixes: the action mutation stays pending until the row refetch lands; Escape with a confirm open closes only the confirm; Space opens a row; a new row action clears older row errors; a LIVE choice falls back to paper when the live flag turns off.

Not changed: ParamsEditor keeps a typed value for a `null`, list or object default as a string (the phase's "else the string" rule; raw JSON covers it). Follow-up outside this phase's file list: `GET /api/v1/subscriptions/{sub_id}/positions` and `StrategyQueryService.get_positions` have no web caller now that `use-open-position.ts` is gone.

After the fixes: `tsc -b` exit 0; lint `0 errors`; vitest 105 passed.

## Owner look (Task 13.5)

The owner checked `/strategies` and `/backtest` locally and replied:

UI OK

FULLSUITE above ran before the review fixes. Those fixes touched only `web/src`, which pytest does not exercise, so the result stands for the committed tree.

Kongming checkpoint: go after `UI OK`; no real-money or contract defect to block on. It recommended deleting the now-unused positions read as its own `refactor(api)` commit (route, `get_positions`, and its entry in `tests/app_test/integration/test_admin_token_guard.py`), outside this phase's file list.

## Commit and CI

- Commit `fb0d72c0` `feat(web): generic multi-timeframe subscription view with manual close and cancel`, pushed to `develop`.
- CI run `41397009432`: `completed success fb0d72c0ecb3127deac7d3fa31d3db284ee3b17b`, equal to `git rev-parse HEAD`.
- No metric-ceiling commit was needed.

## Task 13.5 Verify

`grep -c "^UI OK$"` prints `1`; CI `completed success` on HEAD.

## Follow-up (outside this phase)

- Delete the unused `GET /api/v1/subscriptions/{sub_id}/positions` route, `StrategyQueryService.get_positions` and its guard-test entry in its own commit before Phase 14, if the owner agrees.

Result: PASS
