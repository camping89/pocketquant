# Advice: the next plan is a 1m strategy-evidence plan, not go-live

Date: 2026-11-09. Branch `develop` at `00272823`. Advisory only: nothing in the repo or on prod changed. One read-only Mongo query ran in the prod `api` container (subscriptions, trades, positions, safeguards); the SSH key copy was deleted afterwards. The preview was shown inline (Mermaid) and confirmed by the owner with every marked assumption.

## Tóm tắt tiếng Việt

- Thư mục `plans/` chỉ còn một plan `pending` (go-live), và nó treo vì chưa có chiến lược có lãi, không phải vì thiếu code. Hai plan đã `completed` (parallel-runtime, MTF) chưa được chuyển vào `archive/`.
- Plan tiếp theo đã chốt: **lấy bằng chứng 1m**. Nhánh A chạy ngay, không sửa code: backtest 12 tháng Triple Screen vào lệnh 1m (`1m,5m,15m`, `1m,15m,1h`). Nhánh B có code: hồi sinh hitnrun2 theo hợp đồng đa khung, thêm bộ lọc phí. Cửa quyết định là backtest: PF ròng sau phí >= 1,2 và >= 100 lệnh. Bộ đậu chạy paper 2 tuần chỉ để đối soát. Kết thúc bằng kết luận đậu/rớt từng bộ. Go-live và hai lỗi runtime nằm ngoài plan.
- Điểm cần biết trước khi code hitnrun2: code cũ đặt TP tối thiểu 2% giá vào lệnh (khoảng 80 USD/oz với vàng hiện nay), nên bộ lọc "bỏ lệnh khi TP < 0,15 USD/oz" sẽ không bao giờ kích hoạt với tham số mặc định. Tôi đề xuất viết bộ lọc theo bội số chi phí so với cả TP và SL, và xem lại mức 2% cho một chiến lược 1m.
- Việc nên làm trong plan: chạy nhánh A trước (có số liệu trong một buổi), code nhánh B sau; đọc chi phí từ `ContractSpec` của symbol; không sửa Triple Screen; không bật live.

## Verdict

The right next unit of work is the one the interview converged on: a 1m strategy-evidence plan with a hard backtest gate. The go-live plan cannot move until a strategy clears some gate, and the folder holds nothing else that is open. The plan is sound as framed because its gate is net of cost and it stops on a fail. Two honest cautions. First, the evidence so far points against 1m on gold: every 12-month Triple Screen backtest is net negative, the 5m paper set paid 344 in commission on 61 gross in one week, and the only 1m record (hitnrun2, 30 days) lost 0.25% before any commission. Expect the gate to fail for most sets; that is a useful result, not a wasted plan. Second, the hitnrun2 cost filter as literally stated is a no-op with the old defaults (see "What you should do", item 4), so the plan has to define it in a form that can actually skip an entry.

## What you should do

1. Run Track A first, in one session, before writing any code. The backtest route accepts `1m` as the entry interval today (`check_strategy_inputs` only requires strictly ascending multiples; Triple Screen requires exactly three intervals). Four runs on `XAUUSD:EXNESS` over the latest 12 months (1m depth starts 2025-10-21): `1m,5m,15m` and `1m,15m,1h`, each as `stop/strategy` and `market/sl_tp`. Send no `spread` or commission so the symbol's seeded costs apply (0.035 per oz per side, spread 0.08). Run them one at a time and read `free -m` after each, as Phase 16 did. Expect 20 to 25 minutes per run (the 5m set took 234 to 273 s; 1m has five times the bars); the Phase 16 rule of an owner ask above 1800 s should carry over.
2. Record each run in the Phase 16 table format plus one column: net profit factor is already what `profit_factor` returns since `f37060aa`, so no recomputation is needed. Write the verdict line per set right under the table: `pass` only when `profit_factor >= 1.2` and `total_trades >= 100`.
3. Only then start Track B. Recover `hitnrun2_strategy_service.py` from `f3bb9e64^` and rewrite it to the current contract: `StrategyConfig.intervals = ["1m"]`, `on_bar_completed(bar)` with no `bar["context"]` reads, `restore_direction`, and the `Signal` fields Triple Screen uses. Keep its three lookbacks and `direction` as parameters. Tests go next to `tests/core_test/unit/domain/strategy/test_triple_screen.py` and `tests/backtest_test/engine/test_triple_screen_backtest.py`, following their shape.
4. Define the cost filter so it can fire. Fact from the old code: `tp = max(60-bar extreme, close * (1 + min_profit_pct))` with `min_profit_pct = 0.02`, so the TP distance is at least 2% of price (about 80 USD/oz at today's gold), and `sl = max(480-bar extreme, close * (1 - max_loss_pct))` with 1%. A rule "skip when TP distance < 0.15 USD/oz" therefore never triggers with the defaults. Two changes make it real, and both stay inside the owner's decision: read the round-trip cost from `config.contract_spec` (`commission_per_contract * 2 + spread`; the field exists on `StrategyConfig`), and compare it against the smaller of TP distance and SL distance through one parameter `min_cost_multiple` (default 3 is my suggestion: an entry whose nearer exit is under three round-trip costs is noise). Decide separately whether `min_profit_pct = 0.02` belongs in a 1m strategy at all; on gold it means a position held for days, which is not what "1m" usually means. Lowering it is a parameter change, not a code change, so the backtest can test both.
5. Release Track B through the normal path: `develop` CI green, then `develop:master` as an explicit ask, then the same 12-month backtest and the same verdict line.
6. Paper stage for passing sets only: one paper subscription per passing set, created like the current three (same pooled paper account), two weeks. Reconcile against the backtest with the four assumed columns the owner confirmed: trades per trading day, average commission per trade, exit-reason mix, and zero `strategy_on_bar_error` or stale-bar events. Read per-subscription trades by `trades.run_id`, not account equity, since the paper account is pooled.
7. Close the plan with a written verdict per set, set `status: completed`, and move it to `plans/archive/`.

## What you shouldn't do

- Do not start Track B before Track A has numbers. If both Triple Screen 1m sets fail the gate by a wide margin because of cost per trade, that tells you what the hitnrun2 filter must defeat before you write it.
- Do not change Triple Screen to make 1m work. The owner put that out of scope, and a tuned strategy on a fixed 12-month window is exactly the overfitting the deferred DSR/PBO todo warns about.
- Do not hard-code `0.15` anywhere. The number comes from `scripts/seed_exness_symbols.py` through the symbol's `ContractSpec`; a constant would silently go stale when the seed changes.
- Do not run two 1m backtests at once on prod. The route is uncapped by design and shares the live Mongo pool with the trader; the three paper subscriptions are still trading.
- Do not run the paper stage for a set that failed the gate "to see what happens". The owner's rule is that backtest decides; a failing set in paper adds trades to the pooled account and nothing to the verdict.
- Do not touch go-live Phase 11, `EXNESS_LIVE_TRADING`, the api `BROKER_DISABLED` check, or the strip flag in this plan. They are listed as non-goals.
- Do not re-create hitnrun2 as a single-timeframe special case in the engine. The STF code paths were deleted on purpose; the new class lives on the same contract as Triple Screen with `intervals = ["1m"]`.

## What could be better

Ranked by effort to impact.

1. Add a `1m` run of the existing `15m,1h,4h` set's parameters to the compare view only if it costs nothing: the compare page already takes run ids, so the five Phase 16 URLs extend to the new runs with no code.
2. Archive the two completed plans (`261028-0652`, `261101-0843`) in the same housekeeping commit that creates the new plan. Ten minutes, docs-only, no CI run. It is outside this plan's scope, so it is a suggestion, not a requirement.
3. Make the backtest gate reusable: write the verdict as a short Python snippet in the plan (read `backtest_runs.metrics`, print `pass|fail` with the two values) rather than by hand, so Track B uses the same code as Track A.
4. If a set passes, consider a second 12-month window shifted by six months before paper. This is the cheapest overfitting check available without the sweep harness. Not required by the confirmed gate; a trade-off the owner can take or leave.

## My take and how to get there

Run Track A tomorrow morning (outside the 00:00Z and 03:00Z repair and backfill windows, as the D16 runs did), four runs, about two hours wall time, and write the table and verdict lines the same day. Then decide the hitnrun2 filter form with the Track A numbers in hand, write it in a day with tests, release, backtest, verdict. Paper only what passes, two weeks, reconcile, close. If nothing passes, the plan still closes with a written "1m does not work on gold at these costs" and a number behind it, which ends the 1m question for the go-live plan.

Route: create `plans/261109-1349-1m-strategy-evidence/` (the session's naming base) with two phases for Track A (runs and verdicts), three for Track B (revive and filter, release, runs and verdicts), one for paper reconcile, one for close. Phase files carry the PRODPY recipe from the MTF plan and the Phase 16 run script.

## Benefits

- Answers the question the go-live plan is parked on, with the owner's own gate and cost-inclusive numbers.
- Track A needs no code and no deploy, so the first evidence lands within a day.
- The hitnrun2 revival reuses tested logic and the current contract; no engine special case.
- A fail is a clean stop with a record, so the next plan does not reopen the same question.

## Trade-offs

- A single 12-month window and a fixed threshold is a weak guard against overfitting; the sweep harness and DSR/PBO stay deferred by the owner's choice. The second-window check in "What could be better" is the cheap mitigation.
- The paper stage has no profit threshold, so a passing set can lose in paper and still "pass". The owner chose this: paper reconciles, backtest decides. Cost if wrong: two weeks before the discrepancy is visible in the reconciliation.
- Two weeks of calendar wait contradicts the owner's usual preference for existing evidence over waits. The owner chose it knowingly; the reconciliation columns make the wait produce something.
- Reviving hitnrun2 costs a code change and a release for a strategy whose only prior record is a small loss before commission. The cost filter may not be enough; the gate will say.
- The recommendation stops being right if Track A shows one Triple Screen 1m set passing comfortably: then the owner may prefer to skip Track B and go straight to paper on that set, which is a scope cut only the owner can make. Switching away costs nothing but the hitnrun2 work not yet started.

## Unverified

- That `StrategyConfig.contract_spec` is populated from the symbol's seeded spec in both the backtest and the trader paths (where I looked: `core/domain/strategy/value_objects.py:42` defines the field with `LINEAR_SPEC` default; `broker_factory.py:41-45` reads the spec for the paper broker; I did not trace who sets it on `StrategyConfig`). What confirms it: a grep for `contract_spec=` in `engine/backtest/backtest_execution_service.py` and `engine/live/strategy_reconcile_app_service.py`, or a unit test that asserts the strategy sees `commission_per_contract=0.035` for `XAUUSD:EXNESS`.
- The 20 to 25 minute estimate per 1m backtest (where I looked: Phase 16 elapsed times for the 5m set; bar count ratio). What confirms it: the first Track A run's `started_at`/`completed_at`.
- Why hitnrun2 showed an 84.6% win rate and a net loss on 1m in October (where I looked: the archived `exness-backtest-results.md` table only). I did not read its trades; the Track B backtest with net metrics will show the per-trade distribution.
- The exact `1m` bar coverage percentage for the 12-month window (where I looked: Phase 16 reported `pct >= 99.9` for its 5m-and-up sets and `first_1m=2025-10-21`; the Task 16.1 coverage check should be rerun for `1m`).

## Work checklist

- [ ] Create `plans/261109-1349-1m-strategy-evidence/` with `plan.md` (owner decisions D1 to D5 from the interview, the gate, the non-goals) and phase files.
- [ ] Track A, Phase 1: 1m coverage check for `XAUUSD:EXNESS` over the latest 12 months (Task 16.1 script with `1m` added).
- [ ] Track A, Phase 1: four backtests, one at a time, `free -m` after each, owner ask if a run exceeds 1800 s; table in Phase 16 format; verdict line per set (`profit_factor >= 1.2 and total_trades >= 100`).
- [ ] Track B, Phase 2: recover hitnrun2 from `f3bb9e64^`, rewrite to `intervals=["1m"]` on the current contract, add `min_cost_multiple` reading `config.contract_spec`, unit tests and a backtest-path test; verify the spec reaches the strategy (Unverified item 1).
- [ ] Track B, Phase 3: `develop` CI green; `develop:master` release as an explicit ask; post-deploy checks per `docs/deployment.md`.
- [ ] Track B, Phase 4: 12-month backtests of hitnrun2 with the default and one lower `min_profit_pct`; table and verdict lines.
- [ ] Phase 5: one paper subscription per passing set; two weeks; reconciliation record (trades per day, commission per trade, exit-reason mix, error count) against the backtest.
- [ ] Phase 6: written verdict per set, `status: completed`, move to `plans/archive/`.
- [ ] Optional, same housekeeping commit: archive `261028-0652-exness-only-parallel-runtime` and `261101-0843-stf-to-mtf-foundation`.

## Success metrics

- The plan's backtest table has one row per run with `profit_factor` and `total_trades`, and one verdict line per set; `grep -c "^verdict:" <report>` equals the number of sets.
- Every run finished: `backtest_runs` documents for the new ids have `status=finished` and `elapsed` recorded; no run left `started`.
- Track B: `uv run python -m pytest tests/core_test/unit/domain/strategy tests/backtest_test/engine -q` passes with the new tests; `STRATEGY_REGISTRY` keys include `hitnrun2`; import-linter contracts still `kept`.
- A unit test proves the cost filter skips an entry whose nearer exit distance is under `min_cost_multiple` round-trip costs, and takes it otherwise.
- For each passing set, a paper subscription exists for at least 14 days and the reconciliation record has all four columns filled from `trades.run_id`.
- At close: `test -d plans/archive/261109-1349-1m-strategy-evidence` succeeds and its `plan.md` has `status: completed`.

## Handoff brief

```text
Objective: Produce the 1m strategy evidence the go-live plan is waiting on: 12-month XAUUSD:EXNESS backtests of Triple Screen with a 1m entry screen (1m,5m,15m and 1m,15m,1h; stop/strategy and market/sl_tp) and of a revived hitnrun2 with a cost filter, gate each set on net profit_factor >= 1.2 and total_trades >= 100, run a 2-week paper reconciliation for passing sets only, and close with a written verdict per set.
Done means: a backtest table with profit_factor and total_trades for every run and one pass/fail verdict line per set; hitnrun2 on master with intervals=["1m"], a min_cost_multiple filter reading config.contract_spec, unit and backtest-path tests passing, CI green; one paper subscription per passing set run for at least 14 days with a reconciliation record (trades per day, commission per trade, exit-reason mix, error count) against its backtest; the plan status: completed and moved to plans/archive/.
Out of scope: go-live Phases 11 and 12; EXNESS_LIVE_TRADING; the api BROKER_DISABLED check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions (leave them running).
Constraints: live stays disarmed; develop:master is an explicit ask every time; backtests run one at a time on prod outside 00:00Z and 03:00Z, with an owner ask when a run exceeds 1800 s; no look-ahead (closed higher-timeframe buckets only); costs come from the symbol's ContractSpec, never a literal 0.15; English in plans, code and commits; no fake or synthetic data; prod is read-only except the planned subscription creates; delete .cache/ssh/vps_key at the end of every session.
Stop and ask only if: a backtest run fails or exceeds 1800 s; the strategy does not receive the symbol's contract_spec and fixing it needs an engine change; a release to master is due; a destructive action (deleting prod data, force-push) would be needed; a change outside the confirmed scope seems required.
```
