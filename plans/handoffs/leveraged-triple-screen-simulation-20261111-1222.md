---
handoff-version: 1
generated: 2026-11-11T05:22:00Z
generator: ak-handoff@2.0.0
focus: "we will continue simulation in new orca session, after handoff, send the info to new orca tab and tag kongming to reanalyse"
workspace: D:/w/_me/algotrading/pocketquant
branch: develop
head: bcf0fd0a
---

# HANDOFF: simulate the passing Triple Screen set with 1:500 leverage and strategy-driven stop loss

## Mission and current status
Focus: "we will continue simulation in new orca session, after handoff, send the info to new orca tab and tag kongming to reanalyse".

**Owner goal for the new session:** simulate trading with 1:500 leverage, using the data this session produced. The stop loss follows the strategy (the `stop_lookback` swing extreme), not a predefined value. The owner said "future/index trading". The only market data and engine support in the repo today is `XAUUSD:EXNESS`, which is a gold CFD. Which instrument "future/index" means is an open question (see Open risks).

Done (this session, 2026-11-10..11):
- **Lower slippage.** Default slippage was lowered from 0.5 bp to 0.1 bp for backtests and paper (commit `481fafe3`, released to master, verified on prod: `paper_slippage_bps=0.1`).
- **Diagnosis.** Kongming advisors explained why the 1m sets lose:
  - On 1m the cost is about 12% of a median bar, and gold returns look like a random walk at 1m-1d.
  - Our Triple Screen takes its trigger and stop from the lowest bar instead of Elder's middle bar.
  - The window 2025-11-09..2026-11-08 is a round trip (+1.2% net).
- **hitnrun2 removed.** It is gone from code, tests, prod data, plans and agent memory (commits `e565915e`, `bcf0fd0a`; master `e565915e`). Prod registry is `triple_screen` only.
- **stop_lookback sweep.** 50 Triple Screen runs on prod; all finished. The only set that passes at every lookback is `15m,1h,4h` with `entry_type=stop` and `exit_mode=strategy`:
  - PF 1.234 / 1.256 / 1.358 / 1.424 / 1.456 at lookback 5 / 10 / 20 / 40 / 80.
- **Chosen run.** The owner picked lookback 80: run `01a1c41f-dee3-7070-b7ac-086fbb5dacfc`. 10 000 USD became 10 619.05 (+6.19%). Max end-of-day drawdown was -0.84%. 12 of 13 months were up. 489 trades, win 37.6%.
- **Daily table.** Written to a report (see Source pointers).

Remaining:
1. Kongming reanalysis of the lookback-80 result under 1:500 leverage with strategy-driven SL sizing (owner request).
2. A leveraged simulation. The engine's backtest path has no leverage or risk input today (see Decisions).
3. Out-of-sample validation of the chosen set (older 15m bars or forward paper). This is still undecided.

Urgency: normal. No process, worker or backtest is running.

## Scope and guardrails
Workspace: `D:/w/_me/algotrading/pocketquant` (single repo, branch `develop`; master = prod, releases deploy via CI).

In scope:
- Simulation and analysis on existing prod data: `bars`, `backtest_runs`, `backtest_trades`.
- Kongming reanalysis.
- A plan for any engine change needed for leverage.

Out of scope:
- Go-live and `EXNESS_LIVE_TRADING` (live trading stays disarmed).
- Changes to Triple Screen logic unless the owner approves.
- The three existing Triple Screen paper subscriptions.

Constraints:
- Read `CLAUDE.md` and every file in `docs/governance/` first.
- Questions to the owner go in Vietnamese with a leading `Recommended:` line. Reports, plans and code are in English.
- Commit and push `develop` freely. Every `develop:master` release needs an explicit owner yes.
- The owner chose spread 0.08 (not the measured 0.168) for gating.

Safety boundaries:
- Secrets live only in `../pocketquant-config/`. Never print or commit them.
- Back up before any prod data change.
- Prod backtests run on a 2-vCPU, 3.9 GB VPS shared with the live trader. At most two concurrent runs, as separate processes; one through the api route is the default. The old time-window rule (D8) no longer applies.

## Current state
Branch: develop
HEAD: bcf0fd0a (equals `origin/develop`); master `e565915e` (the only later commit on develop is docs).
Working tree: dirty only in agent memory and untracked reports.

Changed files:
- `.claude/agent-memory/advisor/MEMORY.md`
- `.claude/agent-memory/kongming/MEMORY.md`

Untracked files:
- `.claude/agent-memory/advisor/project-1m-evidence-direction.md`
- `.claude/agent-memory/advisor/user-language-and-gates.md`
- `.claude/agent-memory/kongming/project_ak_plan_reindex_dry_run_default.md`
- `.claude/agent-memory/kongming/project_gold_window_round_trip_and_timeframe_edge.md`
- `.claude/agent-memory/kongming/project_triple_screen_canonical_gap_and_old_run_costs.md`
- `plans/handoffs/1m-strategy-evidence-closed-20261110-0848.md`
- `plans/reports/backtest-261110-1150-slippage-0-1bp-rerun.md`
- `plans/reports/backtest-261111-0025-triple-screen-stop-lookback-sweep.md`
- `plans/reports/backtest-261111-1155-triple-screen-15m-lb80-daily-equity.md`
- `plans/reports/kongming-261110-0915-1m-strategy-failure-diagnosis.md`
- `plans/reports/kongming-261110-1218-gold-timeframe-edge.md`
- `plans/reports/kongming-261110-1218-triple-screen-canonical-gap.md`
- `plans/reports/synthesis-261110-1232-why-valid-strategies-lose.md`

Intentional local modifications: yes. Reports and memory are uncommitted on purpose; committing them is the owner's call.

Local gitignored extracts: `.cache/sweep_rows.txt` (50 rows: set, mode, lookback, metrics, run id) and `.cache/daily_rows.txt` (lookback-80 daily trades and end-of-day equity). `.cache/backups/hitnrun2-prod-backup-261110.json` is the pre-delete backup and is still present.

## Decisions and rationale
- **Slippage 0.1 bp** (about 0.04 USD/oz at 4000, "3-5 pips"). Reason: the owner's fills are 3-5 pips. Rejected: an absolute pip-based slippage field. Owner, 2026-11-10.
- **Spread 0.08 for gating.** Owner decision 2026-11-11. Rejected: 0.168.
- **hitnrun2 deleted entirely**, including plan text. Reason: it was a test strategy, and Kongming B showed it fades the 4-hour break with no edge. Rejected: keeping it as history. Docker logs (6 lines) were left to rotate. Git history is not rewritten.
- **Chosen config: `15m,1h,4h`, stop/strategy, `stop_lookback=80`.** Owner, 2026-11-11.
- **Sizing today** (`src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py:44-46`):
  - `size = min(balance*2%/|entry-SL|, balance*10%*leverage/price)`.
  - Leverage is 1.0 in backtests (no leverage or risk field exists under `engine/backtest/`). So the 10% cap always binds: about 0.23 oz, about 8 USD median risk per trade, about 4% of Elder's 2% rule.
  - The cap dates from commit `0f4edd92` (2026-01-31). No recorded reason exists.
  - Implication: at 1:500 the cap becomes 50x balance, and the 2% rule over the strategy SL decides size. That matches the owner's "SL follows the strategy".

## Work performed
- **Slippage reruns.** Four 1m Triple Screen runs at 0.1 bp. PF rose 0.66-0.75 to 0.81-0.89; all still fail.
- **Kongming advisors** (Fable), four reports. Findings:
  - No look-ahead or fill defect.
  - Two pessimistic engine rules, bounded:
    - When SL and TP touch in the same bar, SL wins.
    - A stop entry is assumed stopped on its fill bar (this hurts stop entries on bars of 15m and longer).
  - A canonical-Triple-Screen sketch found a lead: 1h/4h with tide exit, PF 1.48. It needs code.
- **Sweep on prod.**
  - 27 runs went through the api route and 19 through two parallel lanes. Each lane run was a separate Python process in the api container, using `create_container()`, `BacktestCommandService.run` and `BacktestExecutionService.execute_and_persist`.
  - The scripts were deleted afterwards. Their pattern: write the script to `.cache/`, scp it to the VPS, `docker compose cp` it into `api`, then `exec -T api python`.
- **Daily equity.** Built from the lookback-80 run's `equity_curve` (2557 points, 297 days) and `backtest_trades`.
- **Stop-loss risk per trade, lookback 80:**
  - Distance from entry to SL: median 34.17 USD/oz, range 2.97-408.86.
  - Risk: median 8.13 USD, p90 19.95, max 80.15.
  - Quantity: 0.18-0.27 oz.
  - 144 SL exits averaged -5.09. 345 strategy exits averaged +3.87, worst -28.11.

## Verification
| Check | Outcome | When |
|---|---|---|
| Full test suite after hitnrun2 removal | 1352 passed. Only the 4 known Windows tz tests fail (`test_cron_trigger_timezone`, `test_utc_runtime_guard`). | 2026-11-10 |
| pyright on the strategy package | 0 errors | 2026-11-10 |
| develop CI `e565915e` | success (run 42764400426) | 2026-11-10 |
| master CI and deploy `e565915e` | success (run 42764715412) | 2026-11-10 |
| Prod registry | `triple_screen` only | 2026-11-10 |
| Prod hitnrun2 rows left | 0 | 2026-11-10 |
| Sweep completeness | 50 runs, `started_now=0` | 2026-11-11 |
| VPS temp scripts | removed (`vps_clean`) | 2026-11-11 |

Not run:
- No leveraged backtest exists. The engine cannot take leverage for backtests today.
- The 15m bar coverage before 2025-11 was not checked.
- The cause of market-mode trade counts collapsing at large lookback was not checked.

## Open risks and blockers
- **Question (owner).** Is "future/index" a new instrument (which symbol, which data provider), or the same XAUUSD CFD at 1:500? The repo has no index or futures data for this.
- **Blocker.** The backtest path has no leverage input. A leveraged engine run needs a code change (for example a `leverage` field on the backtest request passed into `RiskConfig`), which needs a plan and owner approval. Until then, a simulation can rescale the stored trades offline. Inference: with strategy-SL sizing at 2% risk, size = 200 / SL distance. This changes margin and equity, but not the trade list, because Triple Screen entries do not depend on balance. Verify that last claim before relying on it.
- **Risk.** 2% risk per trade with a median SL of 34 USD/oz means about 5.9 oz, about 26 000 USD notional per 10 000 USD. Losses and drawdowns scale about 25x against the stored run (inference). Margin calls at 1:500 and swap or financing costs for holds of about 15 hours are not modelled. Exness swap is unverified.
- **Risk.** The chosen set was picked after about 110 tries on one 12-month window. It is in-sample.
- **Question (owner).** Commit or discard the untracked reports and agent-memory files.

## Exact next actions
1. **First safe step**: read this file, `plans/reports/backtest-261111-0025-triple-screen-stop-lookback-sweep.md` and `plans/reports/backtest-261111-1155-triple-screen-15m-lb80-daily-equity.md`. Run `git status --short && git rev-parse HEAD origin/develop origin/master` to confirm Current state.
2. Spawn `kongming` (model fable) to reanalyse run `01a1c41f-dee3-7070-b7ac-086fbb5dacfc` under 1:500 leverage with strategy-SL sizing (2% risk over entry-to-SL). It should report:
   - equity path, drawdown and margin use;
   - worst day and worst streak;
   - the risk of ruin;
   - whether the result survives out-of-sample.
   It reads trades and equity read-only from prod (`backtest_trades` by `run_id`), using its own SSH key copy and deleting it when done.
3. Ask the owner (Vietnamese, `Recommended:` first) which instrument "future/index" means, and what risk per trade to use (2% Elder or another value).
4. If an engine change is approved, write a plan with `ak:plan` under `plans/{date}-{slug}/` that adds leverage and risk to the backtest request. Then rerun the chosen config.

## Source pointers
- `plans/reports/backtest-261111-0025-triple-screen-stop-lookback-sweep.md`: all 50 runs.
- `plans/reports/backtest-261111-1155-triple-screen-15m-lb80-daily-equity.md`: daily and monthly equity for 10 000 USD.
- `plans/reports/backtest-261110-1150-slippage-0-1bp-rerun.md`
- `plans/reports/kongming-261110-0915-1m-strategy-failure-diagnosis.md`, `kongming-261110-1218-gold-timeframe-edge.md`, `kongming-261110-1218-triple-screen-canonical-gap.md`, `synthesis-261110-1232-why-valid-strategies-lose.md`
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py`, `src/pocketquant/core/domain/risk/value_objects.py`, `src/pocketquant/core/config.py` (leverage settings)
- `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`
- `src/pocketquant/engine/backtest/` (command, execution, sandbox services); `src/pocketquant/app/routes/backtest.py`
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` (fills, spread, slippage)
- Prod access recipe: `plans/archive/261109-1349-1m-strategy-evidence/plan.md` lines 95-102 (KEY, PRODPY, HEADER). Collections: `bars`, `backtest_runs`, `backtest_trades`, `backtest_orders`, `symbols`.
- `CLAUDE.md`, `docs/governance/`, `docs/deployment.md`
