# Phase 01 report: coverage and baseline

Run 2026-11-09, about 13:40-13:50 UTC, branch `develop`.

## Entry gate

- `git rev-parse --abbrev-ref HEAD` printed `develop`.
- `git status --porcelain -- src web deploy tests scripts docs .github` printed nothing.

## Task 01.1: commit and push the plan

Plan commit `677a62d5` (`docs(plans): add the 1m strategy evidence plan`) is on `origin/develop`; the Verify printed `plans/261109-1349-1m-strategy-evidence/plan.md`. Only the plan directory and the two advice reports were added; the `.claude/` changes were left out.

## Task 01.2: context tests for a 1m entry

`tests/backtest_test/test_higher_timeframe_context.py` tail line: `11 passed, 2 warnings in 15.39s`.

## Task 01.3: gold spec, live flag and the existing subscriptions

trader_live=False
spec commission_per_contract=0.035 spread=0.08 multiplier=1.0 calendar_id=EXNESS_XAUUSD

existing_sub id=01a19bbf-0b3a-70e3-903e-f93e361acbf8 intervals_key=15m,1h,4h state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]
existing_sub id=01a19bbf-9788-7487-8c7e-9f110ed8c595 intervals_key=1h,4h,1d state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]
existing_sub id=01a19bc0-26ec-76ba-b83e-edeb84f021d4 intervals_key=5m,15m,1h state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]

## Task 01.4: coverage over 2025-11-09..2026-11-09

```text
first_1m=2025-10-21 bar_calendar=EXNESS_XAUUSD
missing_1m_over_60=2025-11-27:149 2025-11-28:177 2025-12-24:268 2025-12-25:1329 2026-01-01:1323 2026-01-19:151 2026-02-16:149 2026-04-02:120 2026-04-03:1258 2026-05-25:149 2026-06-19:238 2026-07-03:238 2026-09-07:151
1m calendar=358287 covered=352297 cal_pct=98.33
5m expected=70599 covered=70599 pct=100.00 before=3751
15m expected=23539 covered=23539 pct=100.00 before=1251
1h expected=5889 covered=5889 pct=100.00 before=11973
worst_pct=100.00
```

All conditions hold: `first_1m=2025-10-21` is before the window start; the bars carry `EXNESS_XAUUSD`; 1m `cal_pct=98.33` (at least 98.00, the same value Phase 16 accepted); 5m, 15m and 1h are each at 100.00 % (at least 99.90); `before` is 1251 for 15m and 11973 for 1h (at least 36). The dates missing over 60 minutes match US market holidays and early closes (Thanksgiving, Christmas, New Year, MLK Day, Presidents Day, Good Friday, Memorial Day, Juneteenth, the July 3 observance, Labor Day). That is an inference from the dates; this phase did not check it against a holiday source.

## Advisory checkpoint

`kongming` gave GO for Phase 02. Risk to watch there: an api restart during a run leaves a `started` backtest document that the BTRUN busy guard would treat as busy forever. Before `r1` the `started` count must be 0, and a run that stays `started` after an api restart goes to the owner instead of being waited on.

Result: PASS
