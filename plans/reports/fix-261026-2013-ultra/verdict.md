# Verifier verdict (kongming)

Winner: A (= candidate 3). margin=low, unanimous=no, confidence medium.

| | Cause | Blast | Minimal | Verif | Total |
|---|---|---|---|---|---|
| A (3) | 19 | 15 | 13 | 19 | 66 |
| B (5) | 15 | 19 | 19 | 17 | 70 |
| C (1) | 18 | 14 | 11 | 16 | 59 |
| D (2) | 16 | 17 | 15 | 17 | 65 |
| E (4) | 19 | 14 | 13 | 15 | 61 |

B has the highest sum but fails the strict hard constraint (live 1m strategies can still be closed by their own signal bar); D has the same gap. A wins under the strict reading.

Q2 (signal bar no longer closes its own entry, in backtests too) changes backtest results and needs user approval. If declined, A drops cleanly to B: remove the `fresh` snapshot, the `submitted_at >= occurred_at` skip and the replay `occurred_at=bar_time` line.

Corrections to apply to A:
1. Import `INTERVAL_SECONDS` from `pocketquant.core.common.constants` (string-keyed); `core.domain.shared` does not re-export it.
2. `BacktestAppService.run` does not force-close positions; run `uv run pytest -q tests/backtest_test` and, if an entry on the last bar now stays open, extend the fixture by one bar rather than relaxing assertions.

ultra: picked=3/5 margin=low unanimous=no rejected_all=no
