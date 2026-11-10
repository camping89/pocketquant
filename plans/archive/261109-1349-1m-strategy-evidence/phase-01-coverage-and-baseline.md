---
phase: 1
title: "Push the plan; no-look-ahead tests; spec, baseline and 1m coverage"
status: completed
priority: P2
effort: "0.5h"
dependencies: []
---

# Phase 01: Push the plan; no-look-ahead tests; spec, baseline and 1m coverage

## Goal

The plan is on `origin/develop`; the existing context tests prove the closed-bucket rule for a 1m entry; prod shows the gold spec Track A and B rely on, the A6 baseline of the three existing subscriptions, live disarmed, and 1m, 5m, 15m and 1h coverage good enough for the 12-month window.

## Context

- Window, sets and definitions: `plan.md` (Definitions).
- Coverage rule: Phase 16's amended rule, approved by the owner on 2026-11-02 (`plans/261101-0843-stf-to-mtf-foundation/phase-16-backtests-and-paper-start.md`, Task 16.1 amendment; report lines 72-79): expected = the buckets of the calendar minutes that have a stored 1m bar; each higher interval `pct >= 99.9`. For 1m itself that rule is always 100 %, so the 1m line reports `cal_pct` against the calendar. The Exness calendar has no holidays, and Phase 16 accepted `min_1m_cal_pct=98.33` with the missing minutes on venue holidays and early closes, so this phase passes 1m at `cal_pct >= 98.00` and lists every date missing over 60 minutes.
- The top interval needs 36 bars before the window start (`macd_slow + macd_signal + 1`, `triple_screen_strategy_service.py:83`): `15m` for `ts-1m-5m-15m`, `1h` for `ts-1m-15m-1h`.
- Calendar id `CALENDAR_EXNESS_XAUUSD` (`src/pocketquant/core/domain/symbol/value_objects.py:15`); `TradingCalendarFactory.get` needs no symbol lookup (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26-38`).
- No-look-ahead (`docs/governance/no-look-ahead-rules.md`): the engine tests already check a 1m entry against a 1h context (`tests/backtest_test/test_higher_timeframe_context.py:259,270,283,410`).
- Ops names (KEY, PRODPY, LIVECHK, SUBSCHECK, Push) are in `plan.md` Ops recipe.

## Entry gate

1. `git rev-parse --abbrev-ref HEAD` prints `develop`.
2. `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 01 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-01-coverage-and-baseline.md`.
- Commit: the plan directory and the two advice reports it cites.
- Prod writes: none.

## Tasks

### Task 01.1 — Commit and push the plan

**Goal:** the plan and its sources are on `origin/develop`, so later entry gates can compare `HEAD` with it.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/`, `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`.

**Steps:**
1. `git add plans/261109-1349-1m-strategy-evidence plans/reports/advise-261109-1309-next-plan.md plans/reports/advise-261109-1309-next-plan-state.md` (add nothing else; `.claude/` changes are not part of this plan).
2. `git commit -m "docs(plans): add the 1m strategy evidence plan"`.
3. Push `develop` (plan.md Ops recipe).

**Success criteria:** `HEAD` equals `origin/develop` and the plan files are tracked.

**Verify:** `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && git ls-files plans/261109-1349-1m-strategy-evidence/plan.md` prints `plans/261109-1349-1m-strategy-evidence/plan.md`.

### Task 01.2 — Context tests for a 1m entry (local, read-only)

**Goal:** the closed higher-timeframe rule holds for a 1m entry in live, warm-up and backtest before any 1m backtest is trusted.

**Target files and symbols:** `tests/backtest_test/test_higher_timeframe_context.py`.

**Steps:**
1. Make sure Docker runs (FULLSUITE first sentence in `plan.md`).
2. `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`; record the line.

**Success criteria:** every test in the file passes.

**Verify:** `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `passed` and contains neither `failed` nor `error`.

### Task 01.3 — Gold spec, live flag and the A6 baseline (read-only)

**Goal:** the seeded spec that A2 and A4 rely on is on prod, live is off, and the three existing subscriptions are recorded so later phases can prove they were not touched.

**Target files and symbols:** prod `symbols`, `subscriptions`; trader settings.

**Steps:**
1. KEY. LIVECHK; record its line.
2. PRODPY with HEADER plus:
```python
sym = db.symbols.find_one({"symbol": "XAUUSD:EXNESS"})
c = sym.get("contract_spec") or {}
print(f"spec commission_per_contract={c.get('commission_per_contract')} spread={c.get('spread')} multiplier={c.get('multiplier')} calendar_id={sym.get('calendar_id')}")
```
3. SUBSCHECK (plan.md); copy its three `existing_sub` lines into the report as plain lines.

**Success criteria:** live off; the spec matches the seed; three running paper subscriptions recorded.

**Verify:** LIVECHK prints exactly `trader_live=False`; the PRODPY output is exactly `spec commission_per_contract=0.035 spread=0.08 multiplier=1.0 calendar_id=EXNESS_XAUUSD`; `grep -c -E "^existing_sub id=\S+ intervals_key=(5m,15m,1h|15m,1h,4h|1h,4h,1d) state=running/running broker=paper " plans/261109-1349-1m-strategy-evidence/reports/phase-01-coverage-and-baseline.md` prints `3`.

### Task 01.4 — Coverage of 1m, 5m, 15m and 1h over the window (read-only)

**Goal:** the four Track A intervals (and the hitnrun2 1m entry) are covered over `2025-11-09..2026-11-09`, and each top interval has 36 bars before it.

**Target files and symbols:** prod `bars`; `TradingCalendarFactory.get`, `trading_minutes`, `bar_start`.

**Steps:**
1. PRODPY with HEADER plus:
```python
from collections import Counter
from datetime import UTC, datetime
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
SYM = "XAUUSD:EXNESS"
START = datetime(2025, 11, 9, tzinfo=UTC)
END = datetime(2026, 11, 9, tzinfo=UTC)
first = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", 1)])
last = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", -1)])
print(f"first_1m={first['datetime'].date().isoformat()} bar_calendar={last.get('calendar_id')}")
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)
minutes = cal.trading_minutes(START, END)
stored_1m = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find({"symbol": SYM, "interval": "1m", "datetime": {"$gte": START, "$lt": END}}, {"datetime": 1})}
have = [m for m in minutes if m in stored_1m]
missing = Counter(m.date().isoformat() for m in minutes if m not in stored_1m)
print("missing_1m_over_60=" + " ".join(f"{d}:{n}" for d, n in sorted(missing.items()) if n > 60))
print(f"1m calendar={len(minutes)} covered={len(have)} cal_pct={100.0 * len(have) / len(minutes):.2f}")
worst = 100.0
for iv in ["5m", "15m", "1h"]:
    expected = {cal.bar_start(m, Interval(iv)) for m in have}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    covered = len(expected & stored)
    pct = 100.0 * covered / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    print(f"{iv} expected={len(expected)} covered={covered} pct={pct:.2f} before={before}")
print(f"worst_pct={worst:.2f}")
```
2. Append the whole output to the report in a code block (these are not machine lines). `rm -f .cache/ssh/vps_key`.

**Success criteria:** `first_1m` is on or before `2025-11-09`; `bar_calendar=EXNESS_XAUUSD`; 1m `cal_pct >= 98.00`; every higher interval `pct >= 99.90`; `before >= 36` for `15m` and `1h`.

**Verify:** the output's first line matches `^first_1m=(2025-(10-[0-9]{2}|11-0[1-9])) bar_calendar=EXNESS_XAUUSD$`; the `1m calendar=` line ends with `cal_pct=<n>` and `uv run python -c "print(<n> >= 98.0)"` prints `True`; the `15m` and `1h` lines show `before=` values `>= 36`; the last line is `worst_pct=<w>` and `uv run python -c "print(<w> >= 99.9)"` prints `True`.

## Rollback

`git revert <plan commit>` and push; nothing else changed.

## Report

`reports/phase-01-coverage-and-baseline.md`: entry-gate outputs; the commit sha; the Task 01.2 tail line; LIVECHK, the spec line and the three `existing_sub` lines; the Task 01.4 output; then `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.

