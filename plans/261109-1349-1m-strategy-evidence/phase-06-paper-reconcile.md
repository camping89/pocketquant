---
phase: 6
title: "Paper for passing sets: create, 14 days of checks, reconcile"
status: pending
priority: P2
effort: "1h work + 14 calendar days (resumes daily)"
dependencies: [2, 5]
---

# Phase 06: Paper for passing sets: create, 14 days of checks, reconcile

## Goal

Every set with `verdict: pass` runs as one paper subscription for at least 14 days, its trader errors and stale-bar skips are counted every day without a gap, and a reconciliation record holds the four A5 columns for paper and for its backtest run. With no passing set, the phase records that and creates nothing.

## Context

- D4: only passing sets go to paper; paper has no profit threshold and only reconciles. A failing set never goes to paper.
- One subscription per set: the unique index `ix_subscriptions_dedup_intervals` (`subscription_repository.py:129-133`). The new sets' interval keys (`1m,5m,15m`, `1m,15m,1h`, `1m`) differ from the three existing ones, so no collision with A6.
- Create body `{symbol, intervals, parameters, broker}` (`src/pocketquant/app/routes/strategy.py:16-20,55-65`) returns `id` (`src/pocketquant/engine/strategy/strategy_command_service.py:26-35`); a new subscription starts `stopped` until `POST /api/v1/subscriptions/{id}/start` (`strategy.py:90-96`). Mutations need `X-Admin-Token`. Paper subscriptions share one pooled paper broker, so results are read per subscription from `trades.run_id` (A5).
- A5 columns and sources: trades per trading day (trades / trading days, plan.md Definitions); average commission per trade (`commission` field); exit-reason mix (`exit_reason` counts); zero `strategy_on_bar_error` (`strategy_app_service.py:623`, logs `strategy_id=<sid>`) and zero stale skips (`strategy.entry_skipped` with `reason=stale` and `subscription_id=<sid>`, `strategy_app_service.py:633-649`). Backtest trades: `backtest_trades` with `run_id = <backtest run id>`.
- Trader logs rotate at 3 x 10 MB and a deploy replaces the container (`deploy/compose.prod.yml:16-20`), so each daily check reads the slice since the previous check and proves the retained log reaches back to it.
- Known differences (R7): the pooled paper balance sizes positions differently from a 10 000 backtest, so commission per trade can differ; paper fills carry no spread while the backtest charges 0.08 (plan.md Facts). Both are recorded next to the `recon:` lines, not judged.
- Error and stale counts are recorded next to the verdict and never change it (plan.md D9).
- Ops names: plan.md Ops recipe.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-05-track-b-backtests.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `1`.
3. On a resume with `paper=` lines in this phase's report, run `uv run python -c "import re,datetime as d; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md',encoding='utf-8').read(); u=re.findall(r'^daycheck .* until=(\S+)',t,re.M); n=d.datetime.now(d.UTC); last=d.datetime.fromisoformat(u[-1].replace('Z','+00:00')) if u else None; print('due=' + ('yes' if last is None or n-last >= d.timedelta(hours=20) else 'no') + ' next=' + ((last+d.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%MZ') if last else 'now'))"`. Pass: the output starts with `due=yes`. On `due=no` end with `NOT_YET: waiting for the next daily check` and the printed `next=` time as the resume time.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 06 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md`; local scratch `.cache/f.py`, `.cache/trader.log`, `.cache/subs.txt`.
- Prod writes: one subscription created and started per passing set (0-3); after the owner's yes, those subscriptions stopped.

## Tasks

### Task 06.1 — Paper plan from the verdicts

**Goal:** one `paper_plan` line per passing set, naming the backtest run whose parameters go to paper, or `paper_plan=none`.

**Target files and symbols:** `reports/phase-02-*.md`, `reports/phase-05-*.md`.

**Steps:**
1. `grep -h "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`.
2. If no line contains ` pass `, record `paper_plan=none`, skip Tasks 06.2-06.6, and end the report with `Result: PASS`.
3. For each `verdict: <set> pass` line, take the runs with `gate=pass`. If exactly one, record `paper_plan=<set> run=<label> id=<backtest run id>` (id from that run's `run=` line). If both runs of the set pass, [ASK] (intent) "both runs of <set> passed; the index allows one paper subscription for the set; which parameters go to paper?" `Recommended: <the run with the higher profit_factor>`, reason: the backtest is the deciding evidence (D4). Record the answer, then the `paper_plan=` line.
4. Parameters per run: `r1`/`r3` `{"entry_type": "market", "exit_mode": "sl_tp"}`; `r2`/`r4` `{"entry_type": "stop", "exit_mode": "strategy"}`; `r5` `{"min_profit_pct": 0.02}`; `r6` `{"min_profit_pct": <min_profit_low>}` (plan.md BTRUN). Strategy and intervals: `ts-1m-5m-15m` = `triple_screen` `["1m","5m","15m"]`; `ts-1m-15m-1h` = `triple_screen` `["1m","15m","1h"]`; `hitnrun2-1m` = `hitnrun2` `["1m"]`.

**Success criteria:** the number of `paper_plan=<set>` lines equals the number of passing verdict lines, or one `paper_plan=none` line exists when none passed.

**Verify:** `uv run python -c "import re; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md',encoding='utf-8').read()+open('plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md',encoding='utf-8').read(); p=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md',encoding='utf-8').read(); n=len(re.findall(r'^verdict: \S+ pass ', t, re.M)); m=len(re.findall(r'^paper_plan=(?!none)\S+ run=r[1-6] id=\S+$', p, re.M)); z=len(re.findall(r'^paper_plan=none$', p, re.M)); print('paper_plan_ok=' + str((n > 0 and m == n and z == 0) or (n == 0 and m == 0 and z == 1)))"` prints `paper_plan_ok=True`.

### Task 06.2 — Create and start one paper subscription per passing set

**Goal:** each `paper_plan` set runs on paper with its run's parameters; live stays off; A6 holds.

**Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, prod `subscriptions`.

**Steps:**
1. KEY. LIVECHK; it must print `trader_live=False`.
2. For each `paper_plan=` line without a `paper=<set>` line yet: write `.cache/f.py` as HEADER plus the script below with `<CODE>`, `<INTERVALS>` and `<PARAMS>` replaced from Task 06.1 step 4 (Python literals). Record `paper_started_at=<set> <output of date -u +%Y-%m-%dT%H:%M:%SZ>` just before running it with PRODPY. The script reuses an existing document on a resume.
```python
import json
import time
import urllib.request
CODE = "<CODE>"
INTERVALS = <INTERVALS>
PARAMS = <PARAMS>
API = "http://localhost:41921/api/v1"
token = s.admin_token.get_secret_value()

def post(path, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    return json.load(urllib.request.urlopen(req))

found = db.subscriptions.find_one({"strategy_code": CODE, "symbol": "XAUUSD:EXNESS", "intervals_key": ",".join(INTERVALS)})
sid = found["_id"] if found else post(f"/strategies/{CODE}/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": INTERVALS, "parameters": PARAMS, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
time.sleep(60)
d = db.subscriptions.find_one({"_id": sid})
print(f"paper_sub={sid}")
print(f"state={d['desired_state']}/{d['actual_state']} broker={d['broker']} strategy={d['strategy_code']} intervals_key={d['intervals_key']} parameters={json.dumps(d['parameters'], sort_keys=True)}")
```
3. Record `paper=<set> sub=<paper_sub id> run=<backtest run id> started_at=<the recorded ISO>` and the `state=` line as `paper_state=<set> <state line>`. If the state shows `running/stopped`, wait 60 s and re-read with PRODPY (HEADER plus `d = db.subscriptions.find_one({"_id": "<sid>"}); print(d["desired_state"] + "/" + d["actual_state"])`) up to 5 times.
4. SUBSCHECK to `.cache/subs.txt`; SUBSDIFF. FREE as `free_after_paper_start=<Mem: line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** one running paper subscription per `paper_plan` set with the planned parameters; the three existing subscriptions unchanged.

**Verify:** `grep -c -E "^paper=\S+ sub=\S+ run=\S+ started_at=\S+$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md; grep -c -E "^paper_plan=(ts-|hitnrun2-)" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md` prints the same number twice; `grep "^paper_state=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md | grep -c -v "state=running/running broker=paper"` prints `0`; SUBSDIFF prints `subs_unchanged`.

### Task 06.3 — Daily error and stale check (resumable)

**Goal:** a contiguous daily count of `strategy_on_bar_error` and stale skips per new subscription, from start to the reconciliation.

**Target files and symbols:** trader container logs.

**Steps:**
1. `SINCE` = the latest `daycheck` `until=` value in the report, or, with none, the earliest `started_at=` of the `paper=` lines. `NOW` = `date -u +%Y-%m-%dT%H:%M:%SZ`.
2. KEY. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <SINCE> --until <NOW> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`.
3. OLDEST: SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --timestamps trader 2>&1 | head -1` piped locally to `grep -o -E "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1`.
4. For each `paper=` subscription `<sid>`: `grep "strategy_on_bar_error" .cache/trader.log | grep -c "strategy_id=<sid>"` and `grep "strategy.entry_skipped" .cache/trader.log | grep "reason=stale" | grep -c "subscription_id=<sid>"`.
5. Record per subscription `daycheck set=<set> since=<SINCE> until=<NOW> oldest_log=<OLDEST> on_bar_error=<n> stale=<n>`. `rm -f .cache/ssh/vps_key`.
6. If `NOW` is earlier than the latest `started_at` + 14 days, end with `NOT_YET: paper window running` and `Resume: ... --from 06 after <NOW + 24 h>`.

**Success criteria:** each check's retained log reaches back to its `SINCE`, so no slice is missed.

**Verify:** for the check just written, `test "$(printf '%s\n%s\n' "<OLDEST>" "<SINCE without the trailing Z>" | sort | head -1)" = "<OLDEST>" && echo covered` prints `covered`.

### Task 06.4 — Reconciliation after 14 days

**Goal:** the four A5 columns for each paper subscription and its backtest run.

**Target files and symbols:** prod `trades`, `backtest_trades`, `bars`; the `daycheck` lines.

**Steps:**
1. Run Task 06.3 once more (its final slice), then for each `paper=` line run PRODPY-ARG `<set> <backtest run id> <sub id> <started_at>` with HEADER plus:
```python
import json
import sys
from collections import Counter
from datetime import UTC, datetime
SET, RUN, SID = sys.argv[1], sys.argv[2], sys.argv[3]
SINCE = datetime.fromisoformat(sys.argv[4].replace("Z", "+00:00"))
NOW = datetime.now(UTC)
START, END = datetime(2025, 11, 9, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)

def days(a, b):
    q = {"symbol": "XAUUSD:EXNESS", "interval": "1m", "datetime": {"$gte": a, "$lt": b}}
    return len({d["datetime"].date() for d in db.bars.find(q, {"datetime": 1})})

def row(source, trades, n_days):
    n = len(trades)
    comm = sum(t.get("commission") or 0.0 for t in trades) / n if n else 0.0
    mix = Counter(str(t.get("exit_reason")) for t in trades)
    print(f"recon: {SET} source={source} trades={n} days={n_days} trades_per_day={n / n_days:.2f} avg_commission={comm:.4f} exit_mix={json.dumps(dict(sorted(mix.items())))}")

row("backtest", list(db.backtest_trades.find({"run_id": RUN}, {"commission": 1, "exit_reason": 1})), days(START, END))
row("paper", list(db.trades.find({"run_id": SID}, {"commission": 1, "exit_reason": 1})), days(SINCE, NOW))
print(f"paper_days={SET} {(NOW - SINCE).days}")
```
2. Append the three lines per set. Then add, per set, `recon: <set> source=paper on_bar_error=<sum of its daycheck on_bar_error> stale=<sum of its daycheck stale> expected=0`. A non-zero sum is recorded as a discrepancy; it does not change the set's verdict (D4).
3. Write a short table per set: `| column | backtest | paper |` with rows trades per trading day, average commission per trade, exit-reason mix, on_bar_error/stale (backtest `n/a`).

**Success criteria:** per paper set, two `source=` rows with values, one error line, and at least 14 paper days.

**Verify:** for each `paper=<set>` line, `grep -c -E "^recon: <set> source=(backtest|paper) trades=[0-9]+ days=[1-9][0-9]* trades_per_day=\S+ avg_commission=\S+ exit_mix=\{.*\}$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md` prints `2`, `grep -c -E "^recon: <set> source=paper on_bar_error=[0-9]+ stale=[0-9]+ expected=0$" ...` prints `1`, and the `paper_days=<set> <n>` line has `n >= 14`.

### Task 06.5 — [ASK] stop the new paper subscriptions

**Goal:** the 2-week runs end with the owner's decision; the three existing subscriptions keep running (A6).

**Target files and symbols:** `POST /api/v1/subscriptions/{id}/stop`.

**Steps:**
1. Ask in Vietnamese (intent): "The 14-day paper reconciliation for <sets> is recorded. Stop these new paper subscriptions (the three older ones keep running)?" Lead with `Recommended: yes`, reason: D4 sets a 2-week run, and a running set keeps adding trades to the pooled paper account. Record `stop_ask=<reply>`.
2. On yes: KEY; for each new `<sid>`, PRODPY with HEADER plus a POST to `/subscriptions/<sid>/stop` with the admin token (same `post` helper as Task 06.2), `time.sleep(60)`, then print `stopped=<sid> state=<desired>/<actual>`. SUBSCHECK; SUBSDIFF. `rm -f .cache/ssh/vps_key`. On any other answer record `kept_running=<sets>`.

**Success criteria:** the owner's answer is recorded; on yes, each new subscription is `stopped/stopped`; A6 holds.

**Verify:** on yes, `grep -c -E "^stopped=\S+ state=stopped/stopped$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md` equals the number of `paper=` lines and SUBSDIFF prints `subs_unchanged`; otherwise `grep -c "^kept_running=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconcile.md` prints `1`.

### Task 06.6 — Live still off

**Goal:** the paper stage never armed live.

**Target files and symbols:** trader settings.

**Steps:**
1. KEY. LIVECHK. `rm -f .cache/ssh/vps_key`.

**Success criteria:** live off.

**Verify:** LIVECHK prints exactly `trader_live=False`.

## Rollback

Each step is an [ASK]. Stop a new subscription (`POST /api/v1/subscriptions/<sid>/stop`), wait for `actual_state=stopped`, then `DELETE /api/v1/subscriptions/<sid>` from a PRODPY script with the token header. Never touch the three existing subscriptions.

## Report

`reports/phase-06-paper-reconcile.md`: entry-gate outputs; the verdict lines read; `paper_plan=` lines and any [ASK] answer; LIVECHK; `paper_started_at=`, `paper=`, `paper_state=` lines; `free_after_paper_start=`; SUBSDIFF outputs; every `daycheck` line with its Verify; the `recon:` and `paper_days=` lines and tables; `stop_ask=` and `stopped=`/`kept_running=`; the final LIVECHK; then `Result: PASS`.

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

