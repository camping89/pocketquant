=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry, backtest gate, paper reconcile"
description: "Backtest Triple Screen with a 1m entry screen on XAUUSD:EXNESS over 12 months, gate each set on net profit_factor >= 1.2 and total_trades >= 100, paper-test only passing sets for 14 days, reconcile against the backtest and close with a pass/fail verdict per set."
status: pending
priority: P2
effort: "about 2d work + 14 days paper observation"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, exness, evidence]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m evidence for that question and nothing else. Track A backtests Triple Screen with a 1m entry screen; it needs no code. A backtest gate decides per set. Only passing sets get a 14-day paper subscription, which reconciles with the backtest and has no profit threshold. The plan ends with a written pass/fail verdict per set. Live trading stays disarmed for the whole plan.

The plan is written for a downstream executor model. Every phase carries tasks with Goal, Target files, Steps, Success criteria and a mechanical Verify, and ends with the same Failure Protocol block.

## Sources (read when a phase cites them)

- Fixed task brief: `reports/evidence-packet.md`.
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`; interview record `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and recipes reused: `plans/261101-0843-stf-to-mtf-foundation/plan.md` (Ops recipe), `phase-15-release-d2.md` (KEY, PRODPY, HEADER, LIVECHK), `phase-16-backtests-and-paper-start.md` (coverage check, run script, run table, 1800 s ask, paper create); its report `reports/phase-16-backtests-and-paper-start.md` (amended coverage rule, run times 20-273 s for 5m-and-up sets).
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Code rules: `CLAUDE.md`, `docs/code-standards.md` (Quality Gate, Comment Policy). Deploy: `docs/deployment.md`.
- Out of scope, context only: `plans/handoffs/exness-only-runtime-undone-items-20261031-1302.md`.

## Owner decisions (interview 2026-11-09, asked in Vietnamese, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

Confirmed assumptions (owner accepted all with the preview):

| # | Assumption |
|---|---|
| A1 | Track A runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`. |
| A2 | Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s. |
| A5 | Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id` because the paper account is pooled. |
| A6 | The three existing Triple Screen paper subscriptions keep running and are not touched. |

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check (`src/pocketquant/engine/strategy/strategy_command_service.py:94-99`) and the SPA strip flag; a sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions; archiving other plans; a second shifted backtest window.

## Design verdicts (planner; do not re-decide in a phase)

- **Set.** A set is one strategy on one interval list: `triple_screen:1m,5m,15m` and `triple_screen:1m,15m,1h` (A1: two runs each). A set passes when at least one of its runs passes the gate. Why: the subscription unique index is `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:128-133`), so one set can hold only one paper subscription. Its paper subscription uses the parameters of the passing run with the highest `profit_factor`.
- **Gate.** A run passes when `status=finished`, `metrics.profit_factor >= 1.2` and `metrics.total_trades >= 100`. `profit_factor` is already net of commission since `f37060aa` ("fix(metrics): compute profit factor and win rate net of commission"). The VERDICT snippet (Ops) prints the lines; nobody computes a verdict by hand.
- **Window.** Every run uses `2025-11-09T00:00:00` to `2026-11-08T23:59:00` UTC on `XAUUSD:EXNESS`. The stored 1m history starts 2025-10-21 (`reports/phase-16-backtests-and-paper-start.md` of the MTF plan, Task 16.1 output).
- **Costs.** No run sends `spread`, `commission_bps` or `slippage_bps`. `_config_from_dict` takes the spread from the symbol spec when the run sends none (`src/pocketquant/engine/backtest/backtest_execution_service.py:32-47`), and the sandbox broker uses the spec's per-contract commission (`src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:80-97`). Gold's seed is `commission_per_contract=0.035`, `spread=0.08`, `multiplier=1.0` (`scripts/seed_exness_symbols.py:36-48`). The default `slippage_bps=0.5` (`src/pocketquant/engine/backtest/backtest_command_service.py:25`) applies to every run alike.
- **Paper evidence for errors.** Trader logs are the only record of `strategy_on_bar_error` (`strategy_app_service.py:623`) and `strategy.entry_skipped reason=stale` (`:630-647`). The trader keeps at most 3 x 10 MB of json-file logs (`deploy/compose.prod.yml:16-20`, inherited by `trader` at `:109-110`) and a deploy recreates the container, so Phase 07 scans the logs about every 24 h and flags any interval it could not see as a gap.
- **Paper spread.** `BrokerFactory.create` passes no `spread` to the paper broker (`src/pocketquant/core/infra/brokers/broker_factory.py:49-57`; default `spread=0.0`, `paper_broker_adapter.py:68`), while the backtest adds the seeded 0.08. The A5 columns hold no P&L, so this is recorded, not reconciled.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one fresh worker per phase. File order is execution order.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`, Git Bash. Every Verify is one self-contained command run from there. The shell keeps no variables between commands.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md`. Each phase writes its own report and ends it with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git rev-parse HEAD` equals `git rev-parse origin/develop` (from Phase 02 on); (3) the previous phase report exists and its last line is `Result: PASS`; (4) any phase-specific lines. A resumed phase may show its own task files as uncommitted, and `HEAD` may be ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: edit nothing, spawn no `kongming`, run `rm -f .cache/ssh/vps_key`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Record the answer in English.
- **Stop-and-ask points (fixed):** a backtest run whose `elapsed_s` exceeds `1800` (before the next run, Phase 02); any destructive prod action or any change outside the confirmed scope.
- **Run windows.** A backtest starts only when WINDOW prints `window_ok=yes`. WINDOW: `uv run python -c "import datetime as d; n=d.datetime.now(d.UTC); m=n.hour*60+n.minute; print('window_ok=' + ('no' if m>=1410 or m<20 or 150<=m<200 else 'yes'))"` (blocks 23:30-00:20Z and 02:30-03:20Z, around the 00:00Z and 03:00Z repair and backfill jobs). On `window_ok=no`, exit `NOT_YET` with `Resume ... after 00:20Z` or `03:20Z`.
- **Search** uses `git grep` (`rg` is not installed in Git Bash).
- **Evidence**: no fake or synthetic data in prod or in any recorded result. Test fixtures in `tests/` are built bars, as in the existing Triple Screen tests; they are never evidence.
- **Prod writes** are only: the four backtest runs (Phase 02), and one paper subscription create and start per passing set (Phase 06). Everything else on prod is read-only.

## Ops recipe (phases inline what they need)

- KEY: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`. SSH `<cmd>`: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit. Check: `test ! -e .cache/ssh/vps_key && echo key-removed` prints `key-removed`.
- Compose on the VPS: `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`; services `api`, `worker`, `trader`, `web`.
- **PRODPY**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -o ServerAliveInterval=60 -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py <args>'`. `<args>` is empty unless a task names them. **HEADER** (first lines of every script that reads Mongo): `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]`. Scripts never print a secret.
- **LIVECHK**: write `.cache/live.py` with `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'`. Pass: exactly `trader_live=False`.
- **EXISTING** (A6, PRODPY with HEADER plus):
```python
OLD = ["5m,15m,1h", "15m,1h,4h", "1h,4h,1d"]
rows = list(db.subscriptions.find({"strategy_code": "triple_screen", "symbol": "XAUUSD:EXNESS", "intervals_key": {"$in": OLD}}))
print(f"existing={len(rows)} running={sum(1 for r in rows if r['desired_state'] == 'running' and r['actual_state'] == 'running')}")
```
  Pass: `existing=3 running=3`.
- **RUNBT** (Phase 02): PRODPY with `<args>` = `<key>` (new run) or `<key> <run_id>` (poll an existing run). Script:
```python
import json
import sys
import time
import urllib.request
from datetime import datetime

from pymongo import MongoClient

from pocketquant.core.config import get_settings

RUNS = {
    "A1": ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "A2": ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "stop", "exit_mode": "strategy"}),
    "A3": ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "A4": ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "stop", "exit_mode": "strategy"}),
}
START, END = "2025-11-09T00:00:00", "2026-11-08T23:59:00"
BASE = "http://localhost:41921/api/v1/backtest"
s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
key = sys.argv[1]
strategy, intervals, params = RUNS[key]
if len(sys.argv) > 2:
    run_id = sys.argv[2]
else:
    busy = [str(d["_id"]) for d in db.backtest_runs.find({"status": "started"}, {"_id": 1})]
    if busy:
        sys.exit(f"run={key} busy={','.join(busy)}")
    label = " ".join(f"{k}={v}" for k, v in params.items()) or "defaults"
    body = {
        "strategy_id": strategy, "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": START, "end_date": END, "parameters": params,
        "name": f"{strategy} {' '.join(intervals)} {label}",
    }
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": s.admin_token.get_secret_value()},
    )
    run_id = json.load(urllib.request.urlopen(req))["request_id"]
print(f"run={key} id={run_id}", flush=True)
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
    f"run={key} id={run_id} status={doc['status']} elapsed_s={int(elapsed)} trades={m.get('total_trades')} "
    f"return={m.get('total_return')} pf={m.get('profit_factor')} max_dd={m.get('max_drawdown')} "
    f"sharpe={m.get('sharpe_ratio')} win={m.get('win_rate')} commission={m.get('total_commission')} "
    f"error={doc.get('error_message')}"
)
```
  The route and response shape are from `src/pocketquant/app/routes/backtest.py:46-68` (`request_id`) and `src/pocketquant/core/domain/backtest/entities.py:63-80`; metric keys from `src/pocketquant/core/domain/trading/value_objects.py:174-192`.
- **VERDICT** (Phases 02 and 08): PRODPY with `<args>` = one `<set>=<run_id>,<run_id>` per set. Script (HEADER plus):
```python
import sys
for arg in sys.argv[1:]:
    name, ids = arg.split("=", 1)
    best = None
    for rid in ids.split(","):
        d = db.backtest_runs.find_one({"_id": rid}, {"status": 1, "metrics": 1})
        pf, n = d["metrics"]["profit_factor"], d["metrics"]["total_trades"]
        ok = d["status"] == "finished" and pf >= 1.2 and n >= 100
        print(f"gate: {name} run={rid} profit_factor={pf:.4f} total_trades={n} {'pass' if ok else 'fail'}")
        if ok and (best is None or pf > best[1]):
            best = (rid, pf, n)
    if best:
        print(f"verdict: {name} pass run={best[0]} profit_factor={best[1]:.4f} total_trades={best[2]}")
    else:
        print(f"verdict: {name} fail")
```
- Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; check `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. Never print a token. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`; wait `sleep 15` before looking up a run id.
- Prod logs are console format with ANSI colours: strip with `sed 's/\x1b\[[0-9;]*m//g'` before grepping `key=value`.

## Data flow

1. Backtest (Phase 02): RUNBT posts `RunBacktestCommand` to the api (`app/routes/backtest.py:46-60`) → `BacktestCommandService.run` validates with `check_strategy_inputs` and stores a `started` run → `BacktestExecutionService.run` reads the symbol's `ContractSpec` (`backtest_execution_service.py:101`) → `BacktestConfig` (spread from spec) and `StrategyConfig(contract_spec=...)` → sandbox paper broker (per-contract commission, spread) replays stored 1m bars, higher intervals from Mongo closed-bucket context → `backtest_runs.metrics` and `backtest_trades` (`run_id` = run id) → VERDICT reads `metrics` → `gate:` and `verdict:` lines in the phase report.
2. Paper (Phases 06, 07): create + start through the api → the trader's reconcile loop loads `StrategyConfig` with the symbol spec (`strategy_reconcile_app_service.py:154-178`) → pooled paper broker keyed by `(paper, spec)` (`strategy_app_service.py:962-982`) → `trades` (`run_id` = subscription id) and trader logs → RECON and SCAN → reconciliation table.
3. Verdict (Phase 08): `verdict:` lines + reconciliation → `final:` lines → plan closed and archived.

## Phases

| # | Phase | Prod writes | Depends on | Status |
|---|---|---|---|---|
| 01 | [Push the plan; 1m coverage check](./phase-01-plan-push-and-coverage.md) | none (read-only) | — | Pending |
| 02 | [Track A: four Triple Screen 1m backtests, table, two verdicts](./phase-02-track-a-backtests.md) | 4 backtest runs | 01 | Pending |
| 06 | [Paper subscriptions for passing sets only](./phase-06-paper-start.md) | 0-2 subscriptions | 02 | Pending |
| 07 | [14-day paper observation and reconciliation](./phase-07-paper-reconcile.md) | none (read-only) | 06 | Pending |
| 08 | [Verdict per set, close and archive](./phase-08-close-and-archive.md) | none | 07 | Pending |

Track A (01-02) needs no code. No two phases run in parallel, and Phase 08 is the only phase that edits `plan.md` (through `ak plan`).

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run recorded with `profit_factor` and `total_trades` | Phase 08 report table has 4 run rows; every run id has `status=finished` |
| AC2 | One verdict line per set | `grep -c "^verdict: " plans/archive/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md` prints `2` |
| AC5 | One paper subscription per passing set, at least 14 days, reconciled | Phase 07: `recon:` lines for both sides of each passing set; each paper subscription `running/running` at `started_at + 14 days` or later |
| AC6 | A6 holds | EXISTING prints `existing=3 running=3` in Phases 06 and 07 |
| AC7 | Live stays disarmed | LIVECHK prints `trader_live=False` in Phase 06 |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` and its `plan.md` has `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| End to end | Four prod backtests; paper subscriptions for passing sets; reconciliation | Phases 02, 06, 07 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run is slow (estimate 20-25 min, unverified) and shares the live Mongo pool with three trading paper subscriptions (`app/routes/backtest.py:46-47`) | M x M | One run at a time; RUNBT refuses to start while any run is `started`; WINDOW; `free -m` after each run; [ASK] after a run above 1800 s |
| R2 | 1m coverage of the window is below the rule | L x H | Phase 01 stops on a miss; no backfill or cascade without an owner yes |
| R5 | Trader log rotation or a redeploy hides errors during paper | M x M | Daily SCAN with a gap flag; gaps are reported in the reconciliation |
| R6 | Paper account is pooled with the three existing subscriptions | H x L | Per-subscription trades by `trades.run_id` (A5); no equity read |
| R7 | One 12-month window overfits | M x M | Accepted by the owner (D4; DSR/PBO deferred); stated in the close report |
| R8 | Live 1m entries skipped as stale (`_STALE_AFTER_S["1m"]=10`, `strategy_app_service.py:53`) | M x L | Counted in the stale column; not fixed in this plan |
| R9 | Expected outcome: most or all sets fail (every 12-month Triple Screen run so far was net negative) | H x L | A fail is a valid close: Phases 06-07 handle zero passing sets |

## Rollback

- Phases 01, 07, 08: read-only on prod; a doc commit is reverted with `git revert`.
- Phase 02: backtest runs only add `backtest_runs`/`backtest_orders`/`backtest_trades` documents; they stay (the owner can delete them in the UI).
- Phase 06: [ASK] each step: stop the new subscription (`POST /api/v1/subscriptions/<id>/stop`), wait for `actual_state=stopped`, then `DELETE /api/v1/subscriptions/<id>`. The three existing subscriptions are never touched.

## Backwards compatibility

No code, schema, index, route or config change. Existing subscriptions, runs and the three paper subscriptions are untouched.

## Unresolved

1. "Set" with two runs: this plan passes a set when either run passes and paper-tests the higher-`profit_factor` passing run, because the unique index allows one subscription per set. The owner may read D4 differently.
2. A non-zero error or stale count, or a log gap, is recorded beside the verdict and does not flip it (D4: the backtest decides). The owner may want otherwise.
3. The new paper subscriptions keep running after the close; stopping them is a prod write the plan does not own.

## Failure Protocol (copied verbatim into every phase file)

```markdown
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
```

=== FILE: phase-01-plan-push-and-coverage.md ===
---
phase: 1
title: "Push the plan; 1m coverage check"
status: pending
priority: P2
effort: 1h
dependencies: []
---

# Phase 01: Push the plan; 1m coverage check

## Goal

The plan and its sources are on `origin/develop`, the plan is in the `ak` plan store, and the 12-month window has the 1m, 5m, 15m and 1h coverage the Track A sets need.

## Context

- The plan directory and the two advice reports are untracked on `develop` at `00272823` (git status at plan time).
- Coverage rule from the MTF plan's Phase 16 (amended 2026-11-02 with the owner): for 5m and up, `expected` is the set of buckets of the calendar minutes that have a stored 1m bar, and every interval's `pct` must be at least 99.9. Its 2026-11-02 run printed `min_1m_cal_pct=98.33`; the missing 1m minutes were US holidays and early closes (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md`, "Task 16.1 re-run"). The Exness calendar has no holidays (same report, kongming counsel), so 1m is checked against the calendar with a floor of `98.00`.
- Triple Screen needs `macd_slow + macd_signal + 1 = 36` top-interval bars before its first decision (`plans/261101-0843-stf-to-mtf-foundation/phase-16-backtests-and-paper-start.md`, Context). The top intervals are `15m` and `1h`. The context reads history before the run start from Mongo.
- Calendar API: `TradingCalendarFactory.get` (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26`), `trading_minutes` and `bar_start` (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:217-230`), `CALENDAR_EXNESS_XAUUSD` (`src/pocketquant/core/domain/symbol/value_objects.py:15`).
- Plan store: `ak plan list --json` did not list `pocketquant/261109-1349` at plan time; `ak plan reindex --apply` re-projects plan folders into the store (`ak plan reindex --help`).

## Entry gate

1. Conventions EG (1). EG (2) and (3) do not apply to this phase.
2. `git rev-parse --abbrev-ref HEAD` prints `develop`.

On a miss, edit nothing and end with the `NOT_YET` block (plan.md Conventions) with `--from 01`.

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-01-plan-push-and-coverage.md`.
- Commit (already on disk): `plans/261109-1349-1m-strategy-evidence/`, `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`.
- Prod: read-only.

## Tasks

### Task 01.1 — Commit and push the plan

**Goal:** the plan and its two advice sources are on `origin/develop`.

**Target files and symbols:** the paths under Files.

**Steps:**
1. `git add plans/261109-1349-1m-strategy-evidence plans/reports/advise-261109-1309-next-plan.md plans/reports/advise-261109-1309-next-plan-state.md`.
2. `git commit -m "docs(plans): add the 1m strategy evidence plan"`.
3. Push `develop` (plan.md Ops). No CI runs (`plans/**` is in `paths-ignore`).

**Success criteria:** `HEAD` is pushed.

**Verify:** `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

### Task 01.2 — Register the plan in the plan store

**Goal:** Phase 08 can close the plan with `ak plan update`.

**Target files and symbols:** the local plan store.

**Steps:**
1. Run `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'`. If it prints `0`, run `ak plan reindex --apply --no-interactive`.

**Success criteria:** the plan id is listed.

**Verify:** `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'` prints `1`.

### Task 01.3 — Coverage check (read-only)

**Goal:** the window `2025-11-09..2026-11-09` has enough 1m, 5m, 15m and 1h bars and enough history before it.

**Target files and symbols:** prod `bars`.

**Steps:**
1. KEY. PRODPY with HEADER plus:
```python
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
cal_minutes = set(cal.trading_minutes(START, END))
q1 = {"symbol": SYM, "interval": "1m", "datetime": {"$gte": START, "$lt": END}}
stored_1m = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q1, {"datetime": 1})}
print(f"1m cal_expected={len(cal_minutes)} stored={len(stored_1m)} cal_pct={100.0 * len(cal_minutes & stored_1m) / len(cal_minutes):.2f}")
worst = 100.0
for iv in ["5m", "15m", "1h"]:
    expected = {cal.bar_start(m, Interval(iv)) for m in stored_1m}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    pct = 100.0 * len(expected & stored) / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    print(f"{iv} expected={len(expected)} covered={len(expected & stored)} pct={pct:.2f} before={before}")
print(f"worst_pct={worst:.2f}")
```
2. Append the output to the report. `rm -f .cache/ssh/vps_key`.
3. A miss is a failed Verify. Do not run a backfill, a cascade or any other prod write to fix it: that is outside the confirmed scope and needs the owner.

**Success criteria:** `first_1m` on or before `2025-11-09`; `bar_calendar=EXNESS_XAUUSD`; 1m `cal_pct >= 98.00`; every 5m, 15m, 1h `pct >= 99.90`; `before >= 36` for 15m and 1h.

**Verify:** the output's first line is `first_1m=<date> bar_calendar=EXNESS_XAUUSD` with `<date> <= 2025-11-09`; the `1m` line has `cal_pct=` `>= 98.00`; the last line is `worst_pct=<n>` with `n >= 99.90`; the `15m` and `1h` lines show `before=` `>= 36`.

### Task 01.4 — Report

**Goal:** the phase is recorded.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/reports/phase-01-plan-push-and-coverage.md`.

**Steps:**
1. Write the entry-gate outputs, the pushed sha, the `ak plan list` count, the Task 01.3 output, then `Result: PASS` as the last line.
2. `git add` the report, commit `docs(plans): record the 1m coverage check`, push `develop`.

**Success criteria:** the report ends with `Result: PASS` and is pushed; the key is gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-01-plan-push-and-coverage.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-removed` prints `Result: PASS`, `pushed`, `key-removed`.

## Rollback

Read-only on prod. `git revert` the two doc commits if the plan is withdrawn.

## Report

`reports/phase-01-plan-push-and-coverage.md`: entry-gate outputs, pushed sha, plan-store count, coverage output, `Result: PASS`.

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

=== FILE: phase-02-track-a-backtests.md ===
---
phase: 2
title: "Track A: four Triple Screen 1m backtests, table, two verdicts"
status: pending
priority: P2
effort: "0.5d (about 2 h of run time, unverified)"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen 1m backtests, table, two verdicts

## Goal

Four finished Triple Screen runs with a 1m entry screen (A1), each followed by a memory reading, in one table, with one `verdict:` line per interval set.

## Context

- D2, A1: sets `1m,5m,15m` and `1m,15m,1h`, each with `entry_type=market, exit_mode=sl_tp` and `entry_type=stop, exit_mode=strategy`. These inputs pass validation today: `check_strategy_inputs` requires strictly ascending intervals that are multiples of the entry interval (`src/pocketquant/core/domain/strategy/services/__init__.py:27-73`), and Triple Screen requires exactly 3 intervals (`triple_screen_strategy_service.py:48-49`). Checked at plan time with `uv run python -c` for all four combinations.
- A2: RUNBT sends no cost fields; the symbol's spec applies (plan.md Design verdict "Costs").
- Run order: `A1` first, because `1m,5m,15m` with market entries is expected to trade most (inference from the MTF plan's Phase 16 run table, where `5m,15m,1h market sl_tp` had 8516 trades and the longest group of run times).
- Expected run time: 20-25 min per run (advice estimate from the 234-273 s of the 5m set and five times the bars; unverified). The first run's `elapsed_s` measures it.
- Run status is `started`, `finished` or `failed` (`src/pocketquant/core/domain/backtest/entities.py:23`).
- Do not change Triple Screen (non-goal).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-01-plan-push-and-coverage.md`.
2. WINDOW prints `window_ok=yes` (re-run before each run in Task 02.1).

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with the `NOT_YET` block with `--from 02`.

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md`.
- Prod writes: four `backtest_runs` (and their orders and trades).

## Tasks

### Task 02.1 — Four backtests, one at a time

**Goal:** `A1`-`A4` finished, each with a `free -m` line.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`; RUNBT (plan.md Ops).

**Steps:**
1. KEY. Write RUNBT to `.cache/f.py` unchanged (no placeholder to fill).
2. For `key` in `A1`, `A2`, `A3`, `A4`, in order:
   - Skip the key when the report already holds `run=<key> id=<id> status=finished`.
   - WINDOW; on `window_ok=no`, `rm -f .cache/ssh/vps_key` and exit `NOT_YET`.
   - When the report holds only `run=<key> id=<id>`, run PRODPY with `<args>` = `<key> <id>` (poll, no new run); otherwise PRODPY with `<args>` = `<key>`.
   - Append both printed lines to the report. A `busy=` exit, a `status=failed` line or a `status=started` line (3 h timeout) is a failed Verify.
   - SSH `free -m` and append its `Mem:` line as `free_after_run=<key> <line>`.
   - If `elapsed_s` is above `1800` and a later run remains in this phase, [ASK] (intent) "run <key> took <minutes> min; `free -m` after it: <line>; continue the next run, one at a time?" `Recommended: yes`, reason: runs never overlap and the paper subscriptions are paper only. Record `cost_ask=<key> <reply>`. A non-yes ends with `NOT_YET`.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four `status=finished` lines and four `free_after_run=` lines; every run above 1800 s that had a later run has a recorded `cost_ask=` yes.

**Verify:** `grep -c -E "^run=A[1-4] id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c "^free_after_run=A" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `4`.

### Task 02.2 — Run table

**Goal:** the four runs read side by side.

**Target files and symbols:** the phase report.

**Steps:**
1. Write the table `| # | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate | gate |` with one row per run, copied from the Task 02.1 lines; `gate` is filled from Task 02.3 (`pass` or `fail`). Rows start `| A1 | 1m 5m 15m | market | sl_tp |`, `| A2 | 1m 5m 15m | stop | strategy |`, `| A3 | 1m 15m 1h | market | sl_tp |`, `| A4 | 1m 15m 1h | stop | strategy |`.
2. Write two compare URLs (the compare view caps at 3 runs): `https://pocketquant.xyz/backtest/compare?runs=<A1>,<A2>` and `https://pocketquant.xyz/backtest/compare?runs=<A3>,<A4>`.

**Success criteria:** 4 rows and 2 URLs.

**Verify:** `grep -c -E "^\| A[1-4] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `2`.

### Task 02.3 — Gate and verdict lines

**Goal:** one `verdict:` line per Track A set, computed by VERDICT.

**Target files and symbols:** VERDICT (plan.md Ops); prod `backtest_runs` (read-only).

**Steps:**
1. KEY. PRODPY with VERDICT and `<args>` = `triple_screen:1m,5m,15m=<A1 id>,<A2 id> triple_screen:1m,15m,1h=<A3 id>,<A4 id>`.
2. Append the six printed lines (four `gate:` and two `verdict:`) under the table, unchanged. Fill the table's `gate` column from the `gate:` lines. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two verdict lines, each `pass` or `fail`.

**Verify:** `grep -c -E "^verdict: triple_screen:1m,(5m,15m|15m,1h) (pass run=\S+ profit_factor=\S+ total_trades=[0-9]+|fail)$" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2`.

### Task 02.4 — Report

**Goal:** the phase is recorded and pushed.

**Target files and symbols:** the phase report.

**Steps:**
1. Add the entry-gate outputs at the top and `Result: PASS` as the last line.
2. Commit `docs(plans): record the triple screen 1m backtests`; push `develop`.

**Success criteria:** report pushed; key removed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-removed` prints `Result: PASS`, `pushed`, `key-removed`.

## Rollback

The runs stay as records; the owner may delete them in the UI. No other prod change.

## Report

`reports/phase-02-track-a-backtests.md`: entry-gate outputs; eight run lines; four `free_after_run=` lines; any `cost_ask=`; the table; two compare URLs; four `gate:` and two `verdict:` lines; `Result: PASS`.

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

=== FILE: phase-06-paper-start.md ===
---
phase: 6
title: "Paper subscriptions for passing sets only"
status: pending
priority: P2
effort: 1h
dependencies: [2]
---

# Phase 06: Paper subscriptions for passing sets only

## Goal

Exactly one running paper subscription per passing set, with the parameters of that set's best passing run, and none for a failing set (D4). With no passing set, the phase records that and creates nothing.

## Context

- Passing sets are the `verdict: <set> pass run=<id> ...` lines in `reports/phase-02-track-a-backtests.md`.
- Create body `{symbol, intervals, parameters, broker}` (`src/pocketquant/app/routes/strategy.py:16-20,55-62`); create returns `id` and stores `desired_state="stopped"` (`src/pocketquant/engine/strategy/strategy_command_service.py:77-110`); start is `POST /api/v1/subscriptions/{id}/start` (`strategy.py:90`). Mutations need `X-Admin-Token` (`src/pocketquant/app/middleware/admin_auth_middleware.py:16-30`). The api listens on `41921`.
- Unique index `(strategy_code, symbol, intervals_key)` (`subscription_repository.py:128-133`): the new keys (`1m,5m,15m`, `1m,15m,1h`) cannot collide with the three existing keys.
- The new subscriptions share the pooled paper broker with the three existing ones (`strategy_app_service.py:962-982`); results per set are read by `trades.run_id` (A5).
- Live stays off: broker is `paper` only; LIVECHK confirms the trader flag.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-02-track-a-backtests.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2`.
3. KEY, then LIVECHK prints `trader_live=False`; EXISTING prints `existing=3 running=3`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with the `NOT_YET` block with `--from 06`.

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md`.
- Prod writes: one subscription create and start per passing set.

## Tasks

### Task 06.1 — List passing sets

**Goal:** the report names exactly the sets that may go to paper.

**Target files and symbols:** the Phase 02 and 05 reports.

**Steps:**
1. Run `grep -h -E "^verdict: \S+ pass run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` and copy each line into the report as `paper_set=<set> run=<id>`.
2. If it prints nothing, write `paper_sets=none`, skip Task 06.2, and go to Task 06.3.

**Success criteria:** one `paper_set=` line per passing verdict, or `paper_sets=none`.

**Verify:** `cat plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md | grep -c -E "^verdict: \S+ pass run="; grep -c "^paper_set=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md; grep -c "^paper_sets=none$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md` prints `N`, `N`, then `1` when `N` is `0` and `0` otherwise.

### Task 06.2 — Create and start one paper subscription per passing set

**Goal:** each passing set runs on paper with its best passing run's parameters.

**Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`; prod `subscriptions`, `backtest_runs` (read).

**Steps:**
1. For each `paper_set=<set> run=<id>` line, record `paper_started=<set> at=<UTC ISO now>` just before the run (keep the first value on a resume), then PRODPY with `<args>` = `<id>` and HEADER plus:
```python
import json
import sys
import time
import urllib.request
RUN = sys.argv[1]
API = "http://localhost:41921/api/v1"
token = s.admin_token.get_secret_value()

def post(path, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    return json.load(urllib.request.urlopen(req))

run = db.backtest_runs.find_one({"_id": RUN})
m = run["metrics"]
if not (run["status"] == "finished" and m["profit_factor"] >= 1.2 and m["total_trades"] >= 100):
    sys.exit(f"run {RUN} did not pass the gate")
code, intervals, params = run["strategy_code"], list(run["intervals"]), dict(run.get("parameters") or {})
key = ",".join(intervals)
found = db.subscriptions.find_one({"strategy_code": code, "symbol": "XAUUSD:EXNESS", "intervals_key": key})
sid = found["_id"] if found else post(f"/strategies/{code}/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": intervals, "parameters": params, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
d = {}
for _ in range(12):
    time.sleep(10)
    d = db.subscriptions.find_one({"_id": sid})
    if d["actual_state"] == "running":
        break
print(f"paper_sub={code}:{key} id={sid}")
print(f"paper_state={code}:{key} state={d['desired_state']}/{d['actual_state']} broker={d['broker']} parameters={json.dumps(d['parameters'], sort_keys=True)}")
```
2. Append both lines per set. Then SSH `free -m` as `free_after_paper_start=`. LIVECHK; EXISTING. `rm -f .cache/ssh/vps_key`.

**Success criteria:** one `paper_sub=` and one `paper_state=` line per `paper_set=` line; each state is `running/running` with `broker=paper`; the parameters equal the run's parameters; live off; A6 holds.

**Verify:** `grep -c "^paper_sub=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md` equals `grep -c "^paper_set=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md`; `grep "^paper_state=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md | grep -c -v " state=running/running broker=paper "` prints `0`; LIVECHK prints `trader_live=False`; EXISTING prints `existing=3 running=3`.

### Task 06.3 — Report

**Goal:** the phase is recorded and pushed.

**Target files and symbols:** the phase report.

**Steps:**
1. Write entry-gate outputs, the Task 06.1 and 06.2 lines (or `paper_sets=none`), then `Result: PASS`.
2. Commit `docs(plans): record the paper subscriptions for passing sets`; push `develop`.

**Success criteria:** report pushed; key removed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-removed` prints `Result: PASS`, `pushed`, `key-removed`.

## Rollback

[ASK] each step, per new subscription id only: `POST /api/v1/subscriptions/<id>/stop`, wait until `actual_state` is `stopped`, then `DELETE /api/v1/subscriptions/<id>` (from a PRODPY script with the token header). Never touch the three existing subscriptions.

## Report

`reports/phase-06-paper-start.md` (contents in Task 06.3).

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

=== FILE: phase-07-paper-reconcile.md ===
---
phase: 7
title: "14-day paper observation and reconciliation"
status: pending
priority: P2
effort: "14 days calendar; about 10 min per daily scan + 1h"
dependencies: [6]
---

# Phase 07: 14-day paper observation and reconciliation

## Goal

Each paper subscription from Phase 06 runs at least 14 days, its trader logs are scanned without unseen intervals where possible, and a reconciliation record holds the four A5 columns for the paper side and its backtest side. With no passing set, the phase records that and passes.

## Context

- A5 columns: trades per trading day; average commission per trade; exit-reason mix; `strategy_on_bar_error` and stale-bar counts (expected zero). Paper trades are read by `trades.run_id` = subscription id (pooled account); backtest trades by `backtest_trades.run_id` = run id. `Trade` carries `commission` and `exit_reason` (`src/pocketquant/core/domain/trading/value_objects.py:83-131`); exit reasons are `auto_sl`, `auto_tp`, `strategy_exit`, `manual_close` (`src/pocketquant/core/domain/brokers/events.py:16-23`).
- Trading day = a UTC date with at least one stored `XAUUSD:EXNESS` 1m bar in the window; the same rule on both sides.
- Log events: `strategy_on_bar_error strategy_id=<sid>` (`src/pocketquant/engine/strategy/strategy_app_service.py:623`); `strategy.entry_skipped reason=stale subscription_id=<sid>` (`:640-647`).
- Log retention: json-file, 3 x 10 MB for `trader` (`deploy/compose.prod.yml:16-20,109-110`), and a deploy recreates the container (`docs/deployment.md`, "Deploy"). A scan interval is seen fully when no trader container started after the interval began and the scan output is under 10 MB. Otherwise the interval is a gap: recorded, not a Verify failure.
- Paper fills carry no modelled spread (plan.md design verdict "Paper spread").
- This phase is resumable and exits `NOT_YET` between daily scans. Resume about every 24 h; a later resume is detected by the gap rule, not hidden.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-06-paper-start.md`.
2. The Phase 06 report holds `paper_sets=none` or at least one `paper_sub=` line.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with the `NOT_YET` block with `--from 07`.

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md`.
- Prod: read-only.

## Tasks

### Task 07.1 — No passing set

**Goal:** the empty case closes cleanly.

**Target files and symbols:** the Phase 06 report.

**Steps:**
1. If `reports/phase-06-paper-start.md` holds `paper_sets=none`, write `recon=none (no set passed the backtest gate)` in this report, skip Tasks 07.2-07.3 and go to Task 07.4.

**Success criteria:** the line exists exactly when no set passed.

**Verify:** `grep -c "^paper_sets=none$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md` equals `grep -c "^recon=none " plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md`.

### Task 07.2 — Daily log scan (resumable)

**Goal:** every day of the paper window is scanned for the two error kinds per subscription, with gaps flagged.

**Target files and symbols:** trader logs; trader container start time.

**Steps:**
1. `SINCE` = the `at=` of the last `scan ` line in this report, or, for the first scan, the earliest `paper_started=` time in the Phase 06 report. `SIDS` = the `id=` values of the Phase 06 `paper_sub=` lines, space-separated.
2. KEY, then run this one Bash command after replacing `<SINCE>` and `<SIDS>`:
```bash
SINCE="<SINCE>"; SIDS="<SIDS>"; NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r')
ssh -i .cache/ssh/vps_key "$HOST" "cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --no-color --since $SINCE trader 2>&1" | sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log
STARTED=$(ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env ps -q trader | xargs docker inspect -f "{{.State.StartedAt}}"' | tr '\n' ' ')
BYTES=$(wc -c < .cache/trader.log)
GAP=$(uv run python -c "import sys, datetime as d; f=lambda x: d.datetime.fromisoformat(x[:19]); since=f(sys.argv[1]); print('yes' if int(sys.argv[2]) >= 10000000 or any(f(x) > since for x in sys.argv[3:]) else 'no')" "$SINCE" "$BYTES" $STARTED)
for SID in $SIDS; do
  E=$(grep "strategy_on_bar_error" .cache/trader.log | grep -c "strategy_id=$SID")
  S=$(grep "strategy.entry_skipped" .cache/trader.log | grep "reason=stale" | grep -c "subscription_id=$SID")
  echo "scan at=$NOW since=$SINCE sid=$SID on_bar_error=$E stale=$S bytes=$BYTES gap=$GAP"
done
```
3. Append every printed line to the report; `rm -f .cache/ssh/vps_key`.
4. If now is earlier than the latest `paper_started=` time plus 14 days, commit the report (`docs(plans): record a paper log scan`), push `develop`, and end with the `NOT_YET` block with `--from 07 after <now + 24 h>`.

**Success criteria:** one `scan ` line per subscription per run; the last scan is at or after the latest start plus 14 days.

**Verify:** the last command printed one line per id in `SIDS`, each matching `^scan at=\S+ since=\S+ sid=\S+ on_bar_error=[0-9]+ stale=[0-9]+ bytes=[0-9]+ gap=(yes|no)$`.

### Task 07.3 — Reconciliation record

**Goal:** the four A5 columns for both sides of each paper set.

**Target files and symbols:** prod `trades`, `backtest_trades`, `backtest_runs`, `bars`, `subscriptions` (read-only).

**Steps:**
1. Run only when now is at or after the latest `paper_started=` time plus 14 days and the last scan in Task 07.2 ran at or after that time.
2. KEY. For each Phase 06 set (`paper_sub=<set> id=<sid>`, its `paper_started=<set> at=<T0>`, and its `paper_set=<set> run=<run_id>`), PRODPY with `<args>` = `<set> <sid> <T0> <run_id>` and HEADER plus:
```python
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
SET, SID, RUN = sys.argv[1], sys.argv[2], sys.argv[4]
T0 = datetime.fromisoformat(sys.argv[3].replace("Z", "+00:00"))
T1 = T0 + timedelta(days=14)
SYM = "XAUUSD:EXNESS"

def days(a, b):
    q = {"symbol": SYM, "interval": "1m", "datetime": {"$gte": a, "$lt": b}}
    return len({d["datetime"].date() for d in db.bars.find(q, {"datetime": 1})})

def row(side, trades, n_days):
    n = len(trades)
    com = sum(t["commission"] for t in trades)
    mix = dict(sorted(Counter(str(t.get("exit_reason")) for t in trades).items()))
    print(f"recon: {SET} side={side} trades={n} trading_days={n_days} trades_per_day={n / n_days:.2f} "
          f"avg_commission={(com / n) if n else 0.0:.4f} exit_mix={json.dumps(mix, sort_keys=True)}")

cfg = db.backtest_runs.find_one({"_id": RUN})["config_snapshot"]
b0 = datetime.fromisoformat(cfg["start_date"].replace("Z", "+00:00"))
b1 = datetime.fromisoformat(cfg["end_date"].replace("Z", "+00:00"))
row("backtest", list(db.backtest_trades.find({"run_id": RUN})), days(b0, b1))
row("paper", list(db.trades.find({"run_id": SID, "exit_time": {"$gte": T0, "$lt": T1}})), days(T0, T1))
sub = db.subscriptions.find_one({"_id": SID})
print(f"recon: {SET} paper_state={sub['desired_state']}/{sub['actual_state']} ran_days={(datetime.now(UTC) - T0).days}")
```
3. Sum the Task 07.2 lines per `sid` locally and append `recon: <set> on_bar_error=<sum> stale=<sum> scans=<count> log_gaps=<count of gap=yes>` for each set.
4. EXISTING (A6). `rm -f .cache/ssh/vps_key`.
5. Write the table `| set | side | trades | trading_days | trades_per_day | avg_commission | exit_mix | on_bar_error | stale | log_gaps |`, two rows per set (the error columns are `-` on the backtest row), copied from the `recon:` lines.

**Success criteria:** per set, two side lines, a state line `running/running` with `ran_days >= 14`, and an error line; EXISTING `existing=3 running=3`.

**Verify:** `grep -c -E "^recon: \S+ side=(backtest|paper) trades=" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md` equals 2 x `grep -c "^paper_sub=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md`; `grep -E "^recon: \S+ paper_state=" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md | grep -c -v -E "paper_state=running/running ran_days=(1[4-9]|[2-9][0-9])$"` prints `0`; EXISTING prints `existing=3 running=3`.

### Task 07.4 — Report

**Goal:** the phase is recorded and pushed.

**Target files and symbols:** the phase report.

**Steps:**
1. Add entry-gate outputs at the top and `Result: PASS` as the last line.
2. Commit `docs(plans): record the paper reconciliation`; push `develop`.

**Success criteria:** report pushed; key removed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-removed` prints `Result: PASS`, `pushed`, `key-removed`.

## Rollback

Read-only on prod. Nothing to roll back.

## Report

`reports/phase-07-paper-reconcile.md`: entry-gate outputs; every `scan` line; the `recon:` lines; the reconciliation table; the EXISTING line; `Result: PASS` (or `recon=none ...` then `Result: PASS`).

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

=== FILE: phase-08-close-and-archive.md ===
---
phase: 8
title: "Verdict per set, close and archive"
status: pending
priority: P2
effort: 1h
dependencies: [7]
---

# Phase 08: Verdict per set, close and archive

## Goal

One close report holds every run, one `verdict:` line per set and one `final:` line per set; the plan is `status: completed` and lives in `plans/archive/`.

## Context

- D4: the backtest gate decides; paper only reconciles. A `final:` line therefore repeats the gate verdict and adds the paper record beside it; an error count or a gap never flips it (plan.md Unresolved 2).
- D5: go-live is out of scope. If no set passes, the close report states "1m does not pass the gate on XAUUSD:EXNESS at the seeded costs" with the numbers behind it.
- Plan close: `ak plan update <id> --status completed` rewrites `plan.md` front matter (`ak plan update --help`); `ak plan archive <id>` marks it archived in the store (`ak plan archive --help`). Earlier plans were archived by moving the folder to `plans/archive/` (commit `00272823`).
- Docs impact: none. The plan changes no code, setup, command, route, config or architecture.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-07-paper-reconcile.md`.

On a miss, edit nothing and end with the `NOT_YET` block with `--from 08`.

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md`.
- Modify: `plans/261109-1349-1m-strategy-evidence/plan.md` front matter through `ak plan update` only.
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.

## Tasks

### Task 08.1 — Close report

**Goal:** all evidence in one file.

**Target files and symbols:** the Phase 02 and 07 reports; VERDICT.

**Steps:**
1. Copy the Phase 02 table into the close table with 4 rows (`A1`-`A4`), keeping the window, the costs line ("seeded spec: commission 0.035 per oz per side, spread 0.08; slippage 0.5 bps") and the run ids.
2. KEY. PRODPY with VERDICT and `<args>` = `triple_screen:1m,5m,15m=<A1>,<A2> triple_screen:1m,15m,1h=<A3>,<A4>`. Append the printed lines unchanged. They must equal the `verdict:` lines of Phase 02 (a re-read of the same stored metrics). `rm -f .cache/ssh/vps_key`.
3. Copy the Phase 07 reconciliation table (or `recon=none ...`).
4. Write one line per set: `final: <set> verdict=<pass|fail> paper=<reconciled|not_run> on_bar_error=<n|-> stale=<n|-> log_gaps=<n|->`, taking the numbers from the Phase 07 `recon:` error lines.
5. Write one sentence of limits: one 12-month window, fixed threshold, no DSR/PBO (owner choice); paper fills carry no modelled spread.

**Success criteria:** 4 table rows, 2 `verdict:` lines, 2 `final:` lines.

**Verify:** `grep -c -E "^\| A[1-4] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md; grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md; grep -c -E "^final: \S+ verdict=(pass|fail) paper=(reconciled|not_run) " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md; diff <(grep -h "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md) <(grep "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md) && echo same` prints `4`, `2`, `2`, `same`.

### Task 08.2 — Close and archive the plan

**Goal:** `status: completed` and the folder in `plans/archive/`.

**Target files and symbols:** `plan.md` front matter; the plan folder.

**Steps:**
1. Write `Result: PASS` as the close report's last line.
2. `ak plan --help`, then `ak plan update pocketquant/261109-1349 --status completed --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence && git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`.
4. `ak plan archive pocketquant/261109-1349 --no-interactive`.
5. Commit `docs(plans): close and archive the 1m strategy evidence plan`; push `develop` (Markdown only, no CI).

**Success criteria:** archived folder exists with `status: completed`; HEAD pushed.

**Verify:** `test -d plans/archive/261109-1349-1m-strategy-evidence && echo archived; grep -c "^status: completed$" plans/archive/261109-1349-1m-strategy-evidence/plan.md; test ! -e plans/261109-1349-1m-strategy-evidence && echo moved; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-removed` prints `archived`, `1`, `moved`, `pushed`, `key-removed`.

## Rollback

`ak plan update pocketquant/261109-1349 --status in-progress --no-interactive`, then `git mv` the folder back and commit. Prod is untouched by this phase. The new paper subscriptions keep running; stopping them is the owner's call (plan.md Unresolved 4).

## Report

`reports/phase-08-close-and-archive.md` (written in Task 08.1; moved with the folder in Task 08.2).

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
