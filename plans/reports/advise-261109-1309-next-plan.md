# Advice: the next plan is a 1m strategy-evidence plan, not go-live

Date: 2026-11-09. Branch `develop` at `00272823`. Advisory only: nothing in the repo or on prod changed. One read-only Mongo query ran in the prod `api` container (subscriptions, trades, positions, safeguards); the SSH key copy was deleted afterwards. The preview was shown inline (Mermaid) and confirmed by the owner with every marked assumption.

## Tóm tắt tiếng Việt

- Thư mục `plans/` chỉ còn một plan `pending` (go-live), và nó treo vì chưa có chiến lược có lãi, không phải vì thiếu code. Hai plan đã `completed` (parallel-runtime, MTF) chưa được chuyển vào `archive/`.
- Plan tiếp theo đã chốt: **lấy bằng chứng 1m**. Plan chạy ngay, không sửa code: backtest 12 tháng Triple Screen vào lệnh 1m (`1m,5m,15m`, `1m,15m,1h`). Cửa quyết định là backtest: PF ròng sau phí >= 1,2 và >= 100 lệnh. Bộ đậu chạy paper 2 tuần chỉ để đối soát. Kết thúc bằng kết luận đậu/rớt từng bộ. Go-live và hai lỗi runtime nằm ngoài plan.
- Việc nên làm trong plan: chạy backtest trước (có số liệu trong một buổi); không sửa Triple Screen; không bật live.

## Verdict

The right next unit of work is the one the interview converged on: a 1m strategy-evidence plan with a hard backtest gate. The go-live plan cannot move until a strategy clears some gate, and the folder holds nothing else that is open. The plan is sound as framed because its gate is net of cost and it stops on a fail. One honest caution: the evidence so far points against 1m on gold: every 12-month Triple Screen backtest is net negative, the 5m paper set paid 344 in commission on 61 gross in one week. Expect the gate to fail for most sets; that is a useful result, not a wasted plan.

## What you should do

1. Run the backtests in one session, with no code change. The backtest route accepts `1m` as the entry interval today (`check_strategy_inputs` only requires strictly ascending multiples; Triple Screen requires exactly three intervals). Four runs on `XAUUSD:EXNESS` over the latest 12 months (1m depth starts 2025-10-21): `1m,5m,15m` and `1m,15m,1h`, each as `stop/strategy` and `market/sl_tp`. Send no `spread` or commission so the symbol's seeded costs apply (0.035 per oz per side, spread 0.08). Run them one at a time and read `free -m` after each, as Phase 16 did. Expect 20 to 25 minutes per run (the 5m set took 234 to 273 s; 1m has five times the bars); the Phase 16 rule of an owner ask above 1800 s should carry over.
2. Record each run in the Phase 16 table format plus one column: net profit factor is already what `profit_factor` returns since `f37060aa`, so no recomputation is needed. Write the verdict line per set right under the table: `pass` only when `profit_factor >= 1.2` and `total_trades >= 100`.
3. Paper stage for passing sets only: one paper subscription per passing set, created like the current three (same pooled paper account), two weeks. Reconcile against the backtest with the four assumed columns the owner confirmed: trades per trading day, average commission per trade, exit-reason mix, and zero `strategy_on_bar_error` or stale-bar events. Read per-subscription trades by `trades.run_id`, not account equity, since the paper account is pooled.
4. Close the plan with a written verdict per set, set `status: completed`, and move it to `plans/archive/`.

## What you shouldn't do

- Do not change Triple Screen to make 1m work. The owner put that out of scope, and a tuned strategy on a fixed 12-month window is exactly the overfitting the deferred DSR/PBO todo warns about.
- Do not run two 1m backtests at once on prod. The route is uncapped by design and shares the live Mongo pool with the trader; the three paper subscriptions are still trading.
- Do not run the paper stage for a set that failed the gate "to see what happens". The owner's rule is that backtest decides; a failing set in paper adds trades to the pooled account and nothing to the verdict.
- Do not touch go-live Phase 11, `EXNESS_LIVE_TRADING`, the api `BROKER_DISABLED` check, or the strip flag in this plan. They are listed as non-goals.

## What could be better

Ranked by effort to impact.

1. Add a `1m` run of the existing `15m,1h,4h` set's parameters to the compare view only if it costs nothing: the compare page already takes run ids, so the five Phase 16 URLs extend to the new runs with no code.
2. Archive the two completed plans (`261028-0652`, `261101-0843`) in the same housekeeping commit that creates the new plan. Ten minutes, docs-only, no CI run. It is outside this plan's scope, so it is a suggestion, not a requirement.
3. Make the backtest gate reusable: write the verdict as a short Python snippet in the plan (read `backtest_runs.metrics`, print `pass|fail` with the two values) rather than by hand.
4. If a set passes, consider a second 12-month window shifted by six months before paper. This is the cheapest overfitting check available without the sweep harness. Not required by the confirmed gate; a trade-off the owner can take or leave.

## My take and how to get there

Run the backtests tomorrow morning (outside the 00:00Z and 03:00Z repair and backfill windows, as the D16 runs did), four runs, about two hours wall time, and write the table and verdict lines the same day. Paper only what passes, two weeks, reconcile, close. If nothing passes, the plan still closes with a written "1m does not work on gold at these costs" and a number behind it, which ends the 1m question for the go-live plan.

Route: create `plans/261109-1349-1m-strategy-evidence/` (the session's naming base) with two phases for the runs and verdicts, one for paper reconcile, one for close. Phase files carry the PRODPY recipe from the MTF plan and the Phase 16 run script.

## Benefits

- Answers the question the go-live plan is parked on, with the owner's own gate and cost-inclusive numbers.
- The backtests need no code and no deploy, so the first evidence lands within a day.
- A fail is a clean stop with a record, so the next plan does not reopen the same question.

## Trade-offs

- A single 12-month window and a fixed threshold is a weak guard against overfitting; the sweep harness and DSR/PBO stay deferred by the owner's choice. The second-window check in "What could be better" is the cheap mitigation.
- The paper stage has no profit threshold, so a passing set can lose in paper and still "pass". The owner chose this: paper reconciles, backtest decides. Cost if wrong: two weeks before the discrepancy is visible in the reconciliation.
- Two weeks of calendar wait contradicts the owner's usual preference for existing evidence over waits. The owner chose it knowingly; the reconciliation columns make the wait produce something.
- The recommendation stops being right if one Triple Screen 1m set passes comfortably: then the owner may prefer to go straight to paper on that set, which is a scope cut only the owner can make.

## Unverified

- The 20 to 25 minute estimate per 1m backtest (where I looked: Phase 16 elapsed times for the 5m set; bar count ratio). What confirms it: the first run's `started_at`/`completed_at`.
- The exact `1m` bar coverage percentage for the 12-month window (where I looked: Phase 16 reported `pct >= 99.9` for its 5m-and-up sets and `first_1m=2025-10-21`; the Task 16.1 coverage check should be rerun for `1m`).

## Work checklist

- [ ] Create `plans/261109-1349-1m-strategy-evidence/` with `plan.md` (owner decisions D1 to D5 from the interview, the gate, the non-goals) and phase files.
- [ ] Phase 1: 1m coverage check for `XAUUSD:EXNESS` over the latest 12 months (Task 16.1 script with `1m` added).
- [ ] Phase 1: four backtests, one at a time, `free -m` after each, owner ask if a run exceeds 1800 s; table in Phase 16 format; verdict line per set (`profit_factor >= 1.2 and total_trades >= 100`).
- [ ] Phase 5: one paper subscription per passing set; two weeks; reconciliation record (trades per day, commission per trade, exit-reason mix, error count) against the backtest.
- [ ] Phase 6: written verdict per set, `status: completed`, move to `plans/archive/`.
- [ ] Optional, same housekeeping commit: archive `261028-0652-exness-only-parallel-runtime` and `261101-0843-stf-to-mtf-foundation`.

## Success metrics

- The plan's backtest table has one row per run with `profit_factor` and `total_trades`, and one verdict line per set; `grep -c "^verdict:" <report>` equals the number of sets.
- Every run finished: `backtest_runs` documents for the new ids have `status=finished` and `elapsed` recorded; no run left `started`.
- For each passing set, a paper subscription exists for at least 14 days and the reconciliation record has all four columns filled from `trades.run_id`.
- At close: `test -d plans/archive/261109-1349-1m-strategy-evidence` succeeds and its `plan.md` has `status: completed`.

## Handoff brief

```text
Objective: Produce the 1m strategy evidence the go-live plan is waiting on: 12-month XAUUSD:EXNESS backtests of Triple Screen with a 1m entry screen (1m,5m,15m and 1m,15m,1h; stop/strategy and market/sl_tp), gate each set on net profit_factor >= 1.2 and total_trades >= 100, run a 2-week paper reconciliation for passing sets only, and close with a written verdict per set.
Done means: a backtest table with profit_factor and total_trades for every run and one pass/fail verdict line per set; one paper subscription per passing set run for at least 14 days with a reconciliation record (trades per day, commission per trade, exit-reason mix, error count) against its backtest; the plan status: completed and moved to plans/archive/.
Out of scope: go-live Phases 11 and 12; EXNESS_LIVE_TRADING; the api BROKER_DISABLED check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions (leave them running).
Constraints: live stays disarmed; develop:master is an explicit ask every time; backtests run one at a time on prod outside 00:00Z and 03:00Z, with an owner ask when a run exceeds 1800 s; no look-ahead (closed higher-timeframe buckets only); costs come from the symbol's ContractSpec, never a literal 0.15; English in plans, code and commits; no fake or synthetic data; prod is read-only except the planned subscription creates; delete .cache/ssh/vps_key at the end of every session.
Stop and ask only if: a backtest run fails or exceeds 1800 s; the strategy does not receive the symbol's contract_spec and fixing it needs an engine change; a release to master is due; a destructive action (deleting prod data, force-push) would be needed; a change outside the confirmed scope seems required.
```
