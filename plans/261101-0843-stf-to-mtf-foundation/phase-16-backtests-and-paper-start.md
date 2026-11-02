---
phase: 16
title: "Prod backtests, pick the live set, start one paper subscription"
status: completed
priority: P1
effort: "0.5d + backtest run time + three entry bars"
dependencies: [15]
---

# Phase 16: Prod backtests, pick the live set, start one paper subscription

<!-- Red team 2026-11-01: #15 -->
No open issue. plan.md D3 fixes six runs (it supersedes the synthesis's four). AGNOSTIC is the plan.md Conventions check "Strategy-agnostic UI".

## Goal

Six Triple Screen backtests on `XAUUSD:EXNESS` are recorded over fully covered data and are comparable, the owner picks the interval set, and one paper subscription with `entry_type=stop, exit_mode=strategy` runs on that set and writes a snapshot that changes across live bars.

## Context

- Inputs from earlier phases: `RunBacktestCommand.intervals` (Phase 08), create body `{symbol, intervals, parameters, broker}` and `intervals_key` in Mongo (Phase 06), `GET /api/v1/subscriptions/{id}/snapshot` returning the ring as a list of entries with `bar_start`, admin token required (Phase 11, D8).
- D3: interval sets `15m,1h,4h`, `1h,4h,1d`, `5m,15m,1h`, each with `entry_type=market, exit_mode=sl_tp` and `entry_type=stop, exit_mode=strategy`; six runs; the compare view keeps its cap of 3 (`web/src/routes/backtest_.compare.tsx:16`), so the runs are read in several compare views plus a metrics table. Name settings by their values, never "versions".
- D4: the paper subscription uses `entry_type=stop, exit_mode=strategy` on the set the owner picks, so the pending stop and the strategy EXIT are observed on prod.
- Range `2025-11-03..2026-10-30`; the stored `XAUUSD:EXNESS` 1m history starts 2025-10-21 (advice Prod checks). Triple Screen needs `macd_slow + macd_signal + 1 = 36` top-interval bars before its first decision (`phase-14-triple-screen.md`, Rules); the top interval is `4h`, `1d` and `1h` for the three sets. The context reads history before the run start from Mongo.
- <!-- Red team 2026-11-01: #14 --> Coverage: cascaded 5m-4h bars exist before the live window only where a backfill cascaded them (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:408-411`, `lookback_minutes=100`), so `inside > 0` cannot detect holes. The calendar-expected bar set of an interval is `{calendar.bar_start(m, interval) for m in calendar.trading_minutes(start, end)}`, the same formula the calendar uses for `periods_per_year` (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:217-236`). The XAUUSD calendar id is `CALENDAR_EXNESS_XAUUSD = "EXNESS_XAUUSD"` (`src/pocketquant/core/domain/symbol/value_objects.py:15`); `TradingCalendarFactory.get` needs no symbol lookup (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26-40`). A run over an interval below 99 % coverage would compare a shorter effective period, so the phase stops there.
- <!-- Red team 2026-11-01: #14 --> Cost: a backtest runs as an asyncio task in the api process, with no concurrency cap (`docs/system-architecture.md:21`; `src/pocketquant/app/routes/backtest.py:46-60`, whose comment warns a large run can starve live order persistence). The `5m,15m,1h` set has the most entry bars and context rollovers and the spike did not measure it, so it runs first, timed from the run's `started_at`/`completed_at` (`src/pocketquant/core/domain/backtest/entities.py:69-70`), with `free -m` after it. Runs go one at a time. Run status is `started`, `finished` or `failed` (`entities.py:23`); metrics keys `total_return`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, `win_rate`, `total_trades` (`web/src/api/backtest-api.ts:17-32`).
- <!-- Red team 2026-11-01: #14 --> Snapshot evidence: the warm-up replay fills the in-memory ring and the first live write includes those entries, so only entries whose `bar_start` is after `paper_started_at` count as live.
- Mutations need `X-Admin-Token` (`src/pocketquant/app/middleware/admin_auth_middleware.py:16-30`); scripts read it from `get_settings().admin_token` (`src/pocketquant/core/config.py:85`) inside the container and never print it. The api listens on `41921` (`deploy/compose.prod.yml:78`). Create returns `id` (`src/pocketquant/engine/strategy/strategy_command_service.py:82-89`); start returns JSON (`src/pocketquant/app/routes/strategy.py:70-76`).
- Prod SPA: `https://pocketquant.xyz/` (`docs/deployment.md:54`).

**Ops lines.** KEY, SSH, PRODPY, HEADER, ADMINGET and the key cleanup are those of `phase-15-release-d2.md` (Context, Ops lines). PRODPY-ARG `<args>` = the PRODPY command with ` <args>` appended after `python /tmp/f.py` and `ssh -o ServerAliveInterval=60` on the second `ssh`.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-15-*.md`.
2. `grep -c "^d2_pushed_at=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-15-*.md` prints `1`.
3. AGNOSTIC prints `0`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 16 after <UTC time>
```

## Files

- Repo: none (the phase report only).
- Prod writes: six `backtest_runs` (Task 16.2); one subscription created and started (Task 16.5).

## Tasks

### Task 16.1 — Data coverage check against the calendar (read-only)

<!-- Red team 2026-11-01: #14 -->
**Goal:** every interval of the three sets covers at least 99 % of its calendar-expected bars in the range and has enough top-interval history before it.

**Target files and symbols:** prod `bars`; `TradingCalendarFactory.get`, `ITradingCalendarPort.trading_minutes`, `bar_start`.

**Steps:**
1. KEY. PRODPY with HEADER plus:
```python
from datetime import UTC, datetime
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
SYM = "XAUUSD:EXNESS"
START = datetime(2025, 11, 3, tzinfo=UTC)
END = datetime(2026, 10, 31, tzinfo=UTC)
first = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", 1)])
last = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", -1)])
print(f"first_1m={first['datetime'].date().isoformat()} bar_calendar={last.get('calendar_id')}")
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)
minutes = cal.trading_minutes(START, END)
worst = 100.0
for iv in ["5m", "15m", "1h", "4h", "1d"]:
    expected = {cal.bar_start(m, Interval(iv)) for m in minutes}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    covered = len(expected & stored)
    pct = 100.0 * covered / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    print(f"{iv} expected={len(expected)} covered={covered} pct={pct:.2f} extra={len(stored - expected)} before={before}")
print(f"worst_pct={worst:.2f}")
```
2. If `worst_pct` is below `99.00`, stop: the Verify fails (do not run any backtest). Record the per-interval lines.
3. If `before` is below `36` for a top interval (`4h`, `1d` or `1h`), [ASK] (intent) "start that set later so its top interval has 36 bars of history?" `Recommended: yes, start the set on the first date with 36 earlier top bars`, reason: earlier decisions would only skip. Record the start used per set.

**Success criteria:** `first_1m` is on or before `2025-11-03`; `bar_calendar=EXNESS_XAUUSD`; every interval's `pct` is at least 99; `before` for `4h`, `1d` and `1h` is at least 36, or the owner's answer is recorded.

**Verify:** the first output line is `first_1m=<date> bar_calendar=EXNESS_XAUUSD` with `<date> <= 2025-11-03`; the last line is `worst_pct=<n>` with `n >= 99.00`; the `1h`, `4h` and `1d` lines show `before=` values `>= 36` (or the report holds the owner's yes with the shifted start).

**Amended 2026-11-02 (owner answer `coverage_ask=yes` in the report).** The first run failed: stored 5m and 15m bars started 2026-09-23 and 2026-08-03, and the Exness calendar has no holidays, so sub-daily intervals cannot reach 99 % of calendar buckets. The owner approved a backup of the `XAUUSD:EXNESS` bars, one full-range `cascade_for_symbol` from 2025-10-21, and this pass rule: `expected` is the set of buckets of the calendar minutes that have a stored 1m bar; every interval's `pct` is at least 99.9 and the last line is `worst_pct=<n>` with `n >= 99.90`; each line also prints the calendar coverage as `cal_pct`, and the report lists the missing 1m dates (venue holidays and early closes). The `first_1m`, `bar_calendar` and `before` conditions are unchanged.

### Task 16.2 — Six backtests, one at a time, the `5m,15m,1h` set first

**Goal:** six finished runs, each followed by a memory reading; the costliest set is timed before the rest run.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`.

**Steps:**
1. Write `.cache/f.py` (HEADER not needed):
```python
import json
import sys
import time
import urllib.request
from datetime import datetime

from pocketquant.core.config import get_settings

RUNS = [
    (["5m", "15m", "1h"], "market", "sl_tp"),
    (["5m", "15m", "1h"], "stop", "strategy"),
    (["15m", "1h", "4h"], "market", "sl_tp"),
    (["15m", "1h", "4h"], "stop", "strategy"),
    (["1h", "4h", "1d"], "market", "sl_tp"),
    (["1h", "4h", "1d"], "stop", "strategy"),
]
START = "2025-11-03T00:00:00"
BASE = "http://localhost:41921/api/v1/backtest"
n = int(sys.argv[1])
intervals, entry_type, exit_mode = RUNS[n - 1]
if len(sys.argv) > 2:
    run_id = sys.argv[2]
else:
    body = {
        "strategy_id": "triple_screen", "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": START, "end_date": "2026-10-30T23:59:00",
        "parameters": {"entry_type": entry_type, "exit_mode": exit_mode},
        "name": f"triple_screen {' '.join(intervals)} entry_type={entry_type} exit_mode={exit_mode}",
    }
    token = get_settings().admin_token.get_secret_value()
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    run_id = json.load(urllib.request.urlopen(req))["request_id"]
print(f"run={n} id={run_id}", flush=True)
deadline = time.time() + 3 * 3600
doc = {"status": "started"}
while time.time() < deadline:
    doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
    if doc["status"] != "started":
        break
    time.sleep(30)
m = doc.get("metrics") or {}
elapsed = (datetime.fromisoformat(doc["completed_at"]) - datetime.fromisoformat(doc["started_at"])).total_seconds()
print(
    f"run={n} id={run_id} status={doc['status']} elapsed_s={int(elapsed)} trades={m.get('total_trades')} "
    f"return={m.get('total_return')} pf={m.get('profit_factor')} max_dd={m.get('max_drawdown')} "
    f"sharpe={m.get('sharpe_ratio')} win={m.get('win_rate')} error={doc.get('error_message')}"
)
```
   If Task 16.1 shifted a set's start, edit `START` for that set's runs only and record it.
2. For `n` in 1..6, in order: skip `n` when the report already holds `run=<n> ... status=finished`; when it holds only `run=<n> id=<id>`, run PRODPY-ARG `<n> <id>` (poll, no new run); else PRODPY-ARG `<n>`. Append both printed lines to the report. Then SSH `free -m` and append its `Mem:` line as `free_after_run=<n> <line>`. A `status=failed` or `status=started` (3 h timeout) line is a failed Verify.
3. <!-- Red team 2026-11-01: #14 --> After run 1 (and after run 2), if `elapsed_s` is above `1800`, [ASK] (intent) "run <n> (`5m,15m,1h`) took <minutes> min; `free -m` after it: <line>; continue the remaining runs one at a time?" `Recommended: yes`, reason: no subscription runs on prod yet, so a long run in the api process starves no live order; the other sets have fewer entry bars. A non-yes ends with `NOT_YET`; record the answer as `cost_ask=<n> <reply>`.

**Success criteria:** six `status=finished` lines and six `free_after_run=` lines; any run of the `5m,15m,1h` set above 1800 s has a recorded owner yes.

**Verify:** `grep -c -E "^run=[1-6] id=\S+ status=finished " plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md; grep -c "^free_after_run=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md` prints `6` then `6`.

### Task 16.3 — Metrics table and compare views

**Goal:** the six runs can be read side by side within the cap of 3.

**Target files and symbols:** the phase report.

**Steps:**
1. Write a table `| # | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate |` with one row per run (`| 1 | 5m 15m 1h | market | sl_tp | ...`), copied from the Task 16.2 lines.
2. Write five compare URLs, one per line, with the run ids of the numbered runs: `https://pocketquant.xyz/backtest/compare?runs=<1>,<2>`, `...?runs=<3>,<4>`, `...?runs=<5>,<6>` (each set, both settings), `...?runs=<1>,<3>,<5>` (`entry_type=market, exit_mode=sl_tp` across sets), `...?runs=<2>,<4>,<6>` (`entry_type=stop, exit_mode=strategy` across sets).

**Success criteria:** 6 table rows and 5 URLs.

**Verify:** `grep -c -E "^\| [1-6] \| " plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md` prints `6` then `5`.

### Task 16.4 — [ASK] the owner picks the interval set

**Goal:** the interval set for the paper subscription is the owner's choice.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Which interval set runs on paper with `entry_type=stop, exit_mode=strategy`?" with the table and the five URLs. `Recommended: <the set whose entry_type=stop, exit_mode=strategy run has the highest profit_factor among runs with at least 30 trades; if none has 30, the one with the most trades>`, reason: D4 observes the pending stop and the strategy EXIT, and this set has the best evidence for that setting.
2. Record `live_set=<intervals comma-joined>` with the owner's answer.

**Success criteria:** one `live_set=` line.

**Verify:** `grep -c -E "^live_set=(15m,1h,4h|1h,4h,1d|5m,15m,1h)$" plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md` prints `1`.

**Amended 2026-11-02 (owner answer `live_set_owner_answer=` in the report).** The owner put all three sets on paper, one subscription per set, each with `entry_type=stop, exit_mode=strategy`, without naming a primary. `live_set=15m,1h,4h` (the recommended set) is the primary that the Task 16.5-16.6 and Phase 17 contracts bind to. The answer is recorded in English as `live_set_owner_answer=`.

### Task 16.5 — Create and start the paper subscription

**Goal:** one paper Triple Screen subscription on `XAUUSD:EXNESS` runs on the picked set.

**Target files and symbols:** `POST /api/v1/strategies/triple_screen/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, prod `subscriptions`.

**Steps:**
1. Record `paper_started_at=<UTC ISO now>` just before the run. PRODPY-ARG `<live_set>` with HEADER plus (it reuses an existing document on a resume):
```python
import json
import sys
import time
import urllib.request
INTERVALS = sys.argv[1].split(",")
API = "http://localhost:41921/api/v1"
token = s.admin_token.get_secret_value()

def post(path, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    return json.load(urllib.request.urlopen(req))

found = db.subscriptions.find_one(
    {"strategy_code": "triple_screen", "symbol": "XAUUSD:EXNESS", "intervals_key": ",".join(INTERVALS)}
)
sid = found["_id"] if found else post("/strategies/triple_screen/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": INTERVALS,
    "parameters": {"entry_type": "stop", "exit_mode": "strategy"}, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
time.sleep(30)
d = db.subscriptions.find_one({"_id": sid})
print(f"paper_sub_id={sid}")
print(f"state={d['desired_state']}/{d['actual_state']} broker={d['broker']} intervals_key={d['intervals_key']} parameters={json.dumps(d['parameters'], sort_keys=True)}")
```
2. Record both lines. On a resume that reuses the document, keep the first `paper_started_at`.

**Success criteria:** running, paper, the picked set, the D4 parameters.

**Verify:** the output's second line is `state=running/running broker=paper intervals_key=<live_set> parameters={"entry_type": "stop", "exit_mode": "strategy"}`.

**Amended 2026-11-02 (owner answer `live_set_owner_answer=` in the report).** The script runs once per set, primary first. The primary keeps the `paper_started_at=`, `paper_sub_id=` and `state=` lines. Each extra set records `extra_paper_sub=<set> id=<id> started_at=<ISO>` and `extra_state=<set> <state line>`, then one `free_after_paper_start=` line. The three subscriptions share one pooled paper broker and so one paper account balance; positions and resting stops stay per subscription.

### Task 16.6 — Snapshot ring after live entry bars

<!-- Red team 2026-11-01: #14, D8 -->
**Goal:** the trader writes a snapshot ring whose live entries change from bar to bar (A9).

**Target files and symbols:** `GET /api/v1/subscriptions/{id}/snapshot`.

**Steps:**
1. If now is earlier than `paper_started_at + 3 x <entry interval> + 2 min` (two full entry bars that start after the start instant), run `rm -f .cache/ssh/vps_key` and end with `NOT_YET: waiting for two live entry bars` and `Resume: ... --from 16 after <that time>`.
2. PRODPY-ARG `<paper_sub_id> <paper_started_at>` with HEADER, ADMINGET plus:
```python
import sys
from datetime import UTC, datetime
since = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
ring = admin_get(f"/subscriptions/{sys.argv[1]}/snapshot")
live = [e for e in ring if datetime.fromisoformat(str(e["bar_start"]).replace("Z", "+00:00")).replace(tzinfo=UTC) > since]
print(f"entries={len(ring)} live_entries={len(live)} live_distinct_bar_start={len({e['bar_start'] for e in live})}")
print(json.dumps(live[-1], sort_keys=True)[:400] if live else "no live entry")
```
3. Append both lines to the report; `rm -f .cache/ssh/vps_key`.

**Success criteria:** at least 2 distinct `bar_start` values among entries after `paper_started_at`.

**Verify:** the first output line matches `^entries=[0-9]+ live_entries=[0-9]+ live_distinct_bar_start=([2-9]|[1-9][0-9]+)$`.

**Amended 2026-11-02 (owner answer `live_set_owner_answer=` in the report).** The wait in step 1 is the latest of the three `started_at + 3 x <entry interval> + 2 min`. The primary keeps the lines above. Each extra set appends `extra_ring=<set> <first output line>`, and every `extra_ring=` line must also show `live_distinct_bar_start` of at least 2.

## Rollback

[ASK] each step. Stop the subscription (`POST /api/v1/subscriptions/<paper_sub_id>/stop`), wait until `actual_state` is `stopped`, then `DELETE /api/v1/subscriptions/<paper_sub_id>` (from a PRODPY script with the token header). The six backtest runs stay; the owner can delete them in the UI. Amended 2026-11-02: the rollback covers the two `extra_paper_sub=` ids the same way.

## Report

`reports/phase-16-backtests-and-paper-start.md`: entry-gate outputs; the Task 16.1 output (per-interval coverage and `worst_pct`) and any shifted start with the owner's answer; the twelve run lines, six `free_after_run=` lines and any `cost_ask=` answer; the metrics table and five compare URLs; `live_set=` with the owner's answer; `paper_started_at=`, `paper_sub_id=`, the state line; the ring lines; then `Result: PASS`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
