# Phase 07 report: written verdict per set, status completed, archive

## Entry gate

- EG(1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG(2) HEAD equals origin/develop: `synced`.
- EG(3) `reports/phase-06-paper-reconcile.md` last line: `Result: PASS`.

## Final verdicts

final: ts-1m-5m-15m fail backtest=r1:pf=0.6630988966404225,trades=36847,gate=fail;r2:pf=0.7462300711017726,trades=14943,gate=fail paper=not_run on_bar_error=n/a stale=n/a
final: ts-1m-15m-1h fail backtest=r3:pf=0.673485099307977,trades=27265,gate=fail;r4:pf=0.7098467853326118,trades=7798,gate=fail paper=not_run on_bar_error=n/a stale=n/a
final: hitnrun2-1m fail backtest=r5:pf=0.784388706700011,trades=344,gate=fail;r6:pf=0.8811049737211203,trades=668,gate=fail paper=not_run on_bar_error=n/a stale=n/a

Phase 06 wrote `paper_plan=none` and no `recon:` lines, so every paper value is `not_run` or `n/a`.

## Summary table

| set | runs (pf, trades, gate) | verdict | paper trades/day (bt vs paper) | avg commission (bt vs paper) | exit mix (bt vs paper) | errors/stale |
|---|---|---|---|---|---|---|
| ts-1m-5m-15m | r1 (0.6631, 36847, fail); r2 (0.7462, 14943, fail) | fail | n/a (not run) | n/a (not run) | n/a (not run) | n/a |
| ts-1m-15m-1h | r3 (0.6735, 27265, fail); r4 (0.7098, 7798, fail) | fail | n/a (not run) | n/a (not run) | n/a (not run) | n/a |
| hitnrun2-1m | r5 (0.7844, 344, fail); r6 (0.8811, 668, fail) | fail | n/a (not run) | n/a (not run) | n/a (not run) | n/a |

## Conclusion

No set passed. All six runs cleared 100 trades and failed on net profit_factor alone: Triple Screen 1m entry/5m/15m reached at best 0.7462 (r2), Triple Screen 1m/15m/1h at best 0.7098 (r4), and hitnrun2 on 1m at best 0.8811 (r6, `min_profit_pct=0.005`). 1m does not clear the gate (net profit_factor >= 1.2 and total_trades >= 100 over 12 months) on XAUUSD:EXNESS at the seeded costs. Inference, not measured: the Phase 02 and 05 advisory notes estimate a round-trip cost of about 0.04 USD per trade, which would make the hitnrun2 fail mainly a gross-edge problem rather than a cost problem.

Task 07.1 Verify: `final_ok=True`.

## Status completed (`ak` outputs)

- `ak --version`: `ak 2.19.0`.
- `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'`: `0`.
- `ak plan reindex`: listed `261109-1349-1m-strategy-evidence recognized` but stayed a dry run; the recheck still printed `0`, and `ak plan update 261109-1349-1m-strategy-evidence --status completed --verbose` failed with `Error: plan update: planstore: plan not found`. The Task 07.2 Verify printed `0`.
- Failure Protocol: kongming could not start on `claude-fable-5-2` (the API required Claude Code 2.1.290 or newer), so it ran on the `opus` model override. Its counsel: `ak plan reindex --help` says the command "Runs as a dry run unless --apply is given", so use `ak plan reindex --apply`.
- Recorded deviation: Tasks 07.2 and 07.3 use `ak plan reindex --apply` in place of `ak plan reindex`, because the plain command is a dry run in ak 2.19.0.
- `ak plan reindex --apply --verbose`: `261109-1349-1m-strategy-evidence recognized pocketquant/261109-1349`.
- `ak plan update pocketquant/261109-1349 --status completed --verbose`: `pocketquant/261109-1349 updated` (exit 0). `git diff` of `plan.md` showed only `status: in-progress` changed to `status: completed`.

Task 07.2 Verify: `grep -c "^status: completed$" plan.md` printed `1`.

## Archive

The directory moves to `plans/archive/261109-1349-1m-strategy-evidence/` with `git mv`. Then `ak plan reindex --apply` runs, and the commit `docs(plans): record the 1m strategy verdicts and archive the plan` is pushed to `develop`. No CI runs for `plans/**`.

Result: PASS
