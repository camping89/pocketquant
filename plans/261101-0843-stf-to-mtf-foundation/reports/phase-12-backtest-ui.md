# Phase 12 report: backtest UI intervals, defaults, labels

The backtest form now posts an ordered `intervals` list from a chip control and prefills its parameters from the strategy's declared defaults. The run header, compare legend, metrics diff header and rail list item show the intervals and the sorted `key=value` parameters. The rail filter lists every active interval and is labelled as an entry-interval filter. Commit `b9b7384f` is on `develop`; CI run `41393433164` concluded `success` on that sha.

## Entry gate

- EG (1): `git status --porcelain -- src web deploy tests scripts docs .github` printed nothing.
- EG (2): `HEAD` and `origin/develop` were both `18f7b366`.
- EG (3): `reports/phase-11-snapshot-manual-actions-endpoints.md` ends with `Result: PASS`.
- Phase 08 grep printed `4`; Phase 06 grep printed `2`; `npx tsc -b` printed `exit=0`.

## Verify outputs

- Task 12.1: the test ran red first (`exit=1`, module missing), then `exit=0`; the `INTERVAL_SECONDS|intervalsError` grep printed `0`.
- Task 12.2: no own Verify; covered by the Task 12.3 `tsc -b`.
- Task 12.3: `exit=0` then `0`.
- Task 12.4: `0` then `1`.
- AGNOSTIC: `0`.

## Gates

- `uv run lint-imports`: `Contracts: 6 kept, 0 broken.`
- `uv run python scripts/code_metrics.py --ratchet`: exit 0. No metric-ceiling commit.
- `uv run ruff check src tests scripts`: `All checks passed!`
- Web: `npx tsc -b` exit 0; `npm run lint` `0 errors, 6 warnings` (all in files this phase did not touch); `npx vitest run` 10 files and 75 tests passed.
- FULLSUITE: `4 failed, 1326 passed, 1 skipped, 63 warnings, 4 errors in 147.85s`; the filtered failure count printed `0`.

## Advisory review

- `kongming` gave GO before commit and found no correctness bug.
- Noted, not changed: a failed defaults request leaves the previous strategy's JSON in the textarea, and the backend 422 then surfaces it. Switching strategies A to B to A re-applies A's defaults, as the phase step specifies.
- Not exercised live: the strategy registry is empty until Phase 14, so the prefill and the chip-to-422 path are type-checked only. Check the prefill by hand once Triple Screen is registered.

## Close

- Commit: `b9b7384f feat(web): run backtests on multiple intervals with strategy defaults`.
- CI: run `41393433164`, `completed success b9b7384f700c30e66253e0d917f2575ab0a796c5`, equal to `git rev-parse HEAD`.

Result: PASS
