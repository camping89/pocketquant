=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry"
description: "Backtest Triple Screen with a 1m entry screen over 12 months of XAUUSD:EXNESS, gate each set on net profit factor and trade count, paper-reconcile only the passing sets for 14 days, and close with a written verdict per set."
status: pending
priority: P2
effort: "about 3d work + 14 days paper observation"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, xauusd, exness]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m evidence by the owner's own gate. Track A backtests Triple Screen with a 1m entry screen, with no code change. Each set passes or fails on its 12-month backtest. Only passing sets run on paper for 14 days, and paper only reconciles. The plan ends with a written verdict per set. Live trading stays disarmed throughout.

The plan is written for a downstream executor model. Every task has Goal, Target files and symbols, Steps, Success criteria and a mechanical Verify. Every phase file ends with the same Failure Protocol block.

## Sources

- Fixed brief: `plans/261109-1349-1m-strategy-evidence/reports/evidence-packet.md`.
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`. Interview record: `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and recipes: `plans/261101-0843-stf-to-mtf-foundation/plan.md` (Conventions, Ops recipe), `phase-15-release-d2.md` (LIVECHK, release, rollback), `phase-16-backtests-and-paper-start.md` (coverage check Task 16.1, run script Task 16.2, table format Task 16.3, paper create Task 16.5) and its report `reports/phase-16-backtests-and-paper-start.md` (coverage amendment, run times 20-273 s).
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Rules: `CLAUDE.md`, `docs/code-standards.md`, `docs/deployment.md`.

## Owner decisions (2026-11-09, asked in Vietnamese, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

Accepted assumptions: A1 Track A runs 4 backtests, each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`. A2 costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s. A5 paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events; per-subscription trades are read by `trades.run_id` because the paper account is pooled. A6 the three existing Triple Screen paper subscriptions keep running and are not touched.

## Planning rules fixed here (do not re-decide in a phase)

- **Set.** A set is one strategy on one interval list: `triple_screen:1m,5m,15m`, `triple_screen:1m,15m,1h` (A1, two runs each). Two sets, so two verdict lines. Reason: A1 and D2 name the interval lists as the sets, and the subscription unique index on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-131`) allows exactly one paper subscription per set.
- **Gate per set.** A set passes when at least one of its runs has `profit_factor >= 1.2` and `total_trades >= 100`. The deciding run is the passing run with the highest `profit_factor`, or, when none passes, the run with the highest `profit_factor`. The paper subscription of a passing set uses the deciding run's parameters, and its reconciliation compares against the deciding run. The VERDICT snippet below applies this rule mechanically.
- **Window.** Every backtest uses `2025-11-09T00:00:00` to `2026-11-08T23:59:00` UTC: the latest 12 full months before the plan date, the same for every run so verdicts compare. Stored 1m `XAUUSD:EXNESS` bars start 2025-10-21 (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md:72`).
- **`profit_factor` is already net of commission** (`src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:197-217`, fixed in `f37060aa`), capped at 100 when there is no loss (`:145-148`). No recomputation.
- **Paper reconciliation is a record, not a gate (D4).** The final verdict of a set is its backtest verdict. The reconciliation is written beside it.

## Data flows

- **Track A (Phases 01-02).** Prod `bars` (1m, 5m, 15m, 1h) and the `symbols` document of `XAUUSD:EXNESS` feed `POST /api/v1/backtest/run` (`src/pocketquant/app/routes/backtest.py:48-60`). `BacktestExecutionService.run` reads the symbol spec (`src/pocketquant/engine/backtest/backtest_execution_service.py:101-102`), sets the run spread from it when the body sends none (`:43`) and passes it to the strategy and the broker (`:111-130`). The run writes `backtest_runs`, `backtest_orders`, `backtest_trades`. BTRUN prints one result line per run into the phase report; VERDICT turns those lines into one `verdict:` line per set.
- **Paper (Phase 06).** A paper subscription per passing set is created through `POST /api/v1/strategies/{code}/subscriptions` and started through `POST /api/v1/subscriptions/{id}/start` (`src/pocketquant/app/routes/strategy.py:55-63,90`). The trader's reconcile loop loads it with the symbol spec; closed paper trades land in `trades` with `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:37-39`); `strategy_on_bar_error` (`strategy_app_service.py:623`) and `strategy.entry_skipped reason=stale` (`:633-647`) land in the trader log. The reconciliation reads both and the deciding backtest run's `backtest_trades`.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one phase at a time. No two phases run in parallel, so no file is owned by two phases at once.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`, Git Bash. Every Verify is one self-contained command run from there. The shell keeps no variables between commands.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md` (R below). Each phase writes its own report and ends it with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git rev-parse HEAD` equals `git rev-parse origin/develop` after `git fetch -q origin`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) any phase-specific lines. A resumed phase may show its own task files as uncommitted and `HEAD` ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Fixed [ASK] points: starting a backtest after any run of this plan took more than 1800 s; any destructive prod action; any change outside the confirmed scope.
- **Search** uses `git grep` (`rg` is not installed in Git Bash).
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` prints `All checks passed!`. If only the ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the phase report; never pad or split code to satisfy it.
- **FULLSUITE <out>**: `docker ps > /dev/null 2>&1 || { "/c/Program Files/Docker/Docker/Docker Desktop.exe" & sleep 20; docker ps > /dev/null && echo docker-ok; }`; then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | sed -E 's/ - .*//' | sort -u > <out>; wc -l < <out>`. About 100 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references, no plan or phase ids); push `develop` with the Ops recipe; then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`. Commits that touch only `**/*.md` or `plans/**` trigger no CI (`.github/workflows/cicd.yml:4-10`).
- **Code** follows `CLAUDE.md`: no docstrings (WHY goes in a `#` comment above the code), short code, a flow reads in one file, no new class, flag, parameter or config key without a real caller, repositories only in core, fastapi only in app, UUIDv7 ids, log levels by frequency.
- **Plan store.** The plan id is `pocketquant/261109-1349`. Run `ak plan --help` before any `ak plan` mutation. Each phase ends with `ak plan phase close pocketquant/261109-1349 <N> --no-interactive`. Phase files hold no checkboxes.
- **Secrets** never go on a command line, into the repo or into a report. Prod Mongo reads and admin calls run as a Python script inside the `api` container (PRODPY).
- **Failure Protocol**: each phase file carries the literal block below. A failed Verify stops the phase and goes to `kongming`; a `NOT_YET` exit does not.

## Ops recipe (phases reference these by name)

- **KEY**: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit.
- **SSH `<cmd>`**: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`.
- **COMPOSE `<args>`** (inside SSH): `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`; services `api`, `worker`, `trader`, `web`.
- **FREE**: SSH `free -m | grep Mem:`.
- **PRODPY `<args>`**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -o ServerAliveInterval=60 -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py <args>'`. With no `<args>`, drop the placeholder.
- **HEADER** (first lines of every PRODPY script that reads Mongo): `import json` / `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]`. Scripts never print a secret.
- **SUBS** (lines after HEADER; prints every subscription, sorted):
```python
for d in db.subscriptions.find({}).sort("intervals_key", 1):
    print(f"sub {d['strategy_code']} {d['intervals_key']} {d['desired_state']}/{d['actual_state']} {d['broker']} {json.dumps(d.get('parameters'), sort_keys=True)}")
```
- **LIVECHK**: write `.cache/live.py` with the two lines `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'`. It runs in `trader`, never through PRODPY, because compose pins the flag off only for api and worker (`deploy/compose.prod.yml` comment above the api service).
- **WINDOWCHK**: `uv run python -c "import datetime as d; n=d.datetime.now(d.UTC); m=n.hour*60+n.minute; b=any(min((m-w)%1440,(w-m)%1440)<=45 for w in (0,180)); print('window=' + ('blocked' if b else 'ok'), n.strftime('%H:%MZ'))"`. A backtest starts only on `window=ok`: never within 45 minutes of 00:00Z (`sync_repair`) or 03:00Z (`sync_backfill`) (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:805-824`).
- **TRADERLOG `<since>`**: SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --timestamps --no-color --since <since> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`. Omit `--since <since>` to read the whole retained log.
- **Push**: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`. A release is `develop:master` in the same command and is always an [ASK]. Check: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. Never print a token.
- **RUNSDEF** (the one run table; scripts that need it start with it):
```python
RUNS = {
    1: ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    2: ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "stop", "exit_mode": "strategy"}),
    3: ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    4: ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "stop", "exit_mode": "strategy"}),
}
```
- **BTRUN** (`.cache/f.py` = RUNSDEF followed by this block; run with PRODPY `<n>` or, to poll an already submitted run, PRODPY `<n> <id>`):
```python
import json
import sys
import time
import urllib.request
from datetime import datetime

from pocketquant.core.config import get_settings

START, END = "2025-11-09T00:00:00", "2026-11-08T23:59:00"
BASE = "http://localhost:41921/api/v1/backtest"
n = int(sys.argv[1])
code, intervals, params = RUNS[n]
set_key = f"{code}:{','.join(intervals)}"
params_key = ",".join(f"{k}={v}" for k, v in sorted(params.items()))
if len(sys.argv) > 2:
    run_id = sys.argv[2]
else:
    body = {
        "strategy_id": code, "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": START, "end_date": END, "parameters": params,
        "name": f"{set_key} {params_key}",
    }
    token = get_settings().admin_token.get_secret_value()
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    run_id = json.load(urllib.request.urlopen(req))["request_id"]
    print(f"run={n} id={run_id} submitted", flush=True)
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
    f"run={n} id={run_id} set={set_key} params={params_key} status={doc['status']} "
    f"elapsed_s={int(elapsed)} trades={m.get('total_trades')} return={m.get('total_return')} "
    f"pf={m.get('profit_factor')} max_dd={m.get('max_drawdown')} sharpe={m.get('sharpe_ratio')} "
    f"win={m.get('win_rate')} commission={m.get('total_commission')} error={doc.get('error_message')}"
)
```
- **VERDICT** (local; write to `.cache/verdict.py`, run `uv run python .cache/verdict.py <report path>`; it is the reusable gate):
```python
import re
import sys

sets: dict[str, list[tuple[bool, float, int, int]]] = {}
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"run=(\d+) id=\S+ set=(\S+) .*status=finished .*trades=(\d+) .*pf=([0-9.]+) ", line)
    if m:
        n, key, trades, pf = int(m[1]), m[2], int(m[3]), float(m[4])
        sets.setdefault(key, []).append((pf >= 1.2 and trades >= 100, pf, n, trades))
for key, runs in sets.items():
    ok, pf, n, trades = max(runs)
    print(f"verdict: {key} {'pass' if ok else 'fail'} run={n} profit_factor={pf:.4f} total_trades={trades}")
```

## Phases

| # | Phase | Prod effect | Depends on |
|---|---|---|---|
| 01 | [Track A: plan commit, 1m coverage and look-ahead checks](./phase-01-track-a-coverage.md) | read-only | none |
| 02 | [Track A: four Triple Screen backtests, table, verdicts](./phase-02-track-a-backtests-and-verdicts.md) | 4 backtest runs | 01 |
| 06 | [Paper for passing sets: start, 14 days, reconciliation](./phase-06-paper-reconciliation.md) | subscription creates | 02 |
| 07 | [Final verdicts, close and archive](./phase-07-verdicts-close-archive.md) | none | 06 |

Track A runs first and needs no code. Phase 06 starts paper only for sets whose verdict is `pass`; with no passing set it records `paper_sets=0` and the plan closes on the backtest verdicts.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run has a table row with `profit_factor` and `total_trades`; one verdict line per set | `grep -c -E "^\| [1-4] \| " R/phase-02-*.md` prints `4`; `grep -c "^verdict: " R/phase-02-*.md` prints `2` |
| AC2 | Every run finished | four `run=<n> id=... status=finished` lines in the Phase 02 report |
| AC5 | One paper subscription per passing set, at least 14 days, with the four A5 columns against its deciding backtest | Phase 06 `paper_sub=` lines, the 14-day check and the reconciliation table; or `paper_sets=0` |
| AC6 | The three existing paper subscriptions untouched | SUBS lines for `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d` identical before and after every prod write of Phase 06 |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` succeeds and its `plan.md` has `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Existing guards | Live path passes the spec: `tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec`; closed higher-timeframe context with a 1m entry in live, warm-up and backtest: `tests/backtest_test/test_higher_timeframe_context.py` | Phase 01 |
| End to end (prod) | Four 12-month backtests; paper subscriptions for passing sets; reconciliation | Phases 02, 06 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes over 1800 s or presses the 3.9 GB VPS; the route has no cap and no cancel and shares the live Mongo pool (`app/routes/backtest.py:46-47`) | M x M | One run at a time, costliest set first, FREE after each, WINDOWCHK, [ASK] before the next run after any run over 1800 s |
| R2 | 1m bars have holes in the window | L x H | Phase 01 coverage gate (1m calendar coverage and derived-interval coverage) before any run |
| R6 | Trader log rotation (10 MB x 3, `deploy/compose.prod.yml:16-20`) or a redeploy loses error lines during the 14 paper days | M x M | Daily check-ins; each one proves the retained log starts before the previous check-in, else STOP |
| R7 | Paper sizing differs from the backtest (pooled paper account vs 10 000 initial capital), so commission per trade differs | H x L | Recorded beside the numbers; the A5 columns stay as decided |
| R8 | A single 12-month window overfits | M x M | Accepted by the owner (D4); sweep, DSR and PBO are out of scope |

## Backwards compatibility and rollback

- No schema, route, contract or code change. Triple Screen is untouched.
- Rollback per phase is in each phase file. Backtest runs stay as records. Paper subscriptions are stopped and deleted only on an owner yes.

## Docs impact

None expected. No doc names a strategy (`git grep -n -i -E "triple" -- docs README.md CLAUDE.md` prints nothing on `00272823`).

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions. Also not in scope (advice suggestions the owner did not confirm): archiving the two other completed plans, a second shifted 12-month window, compare-view URLs. No paper run for a failing set.

## Unresolved

1. Whether the new paper subscriptions keep running after the plan closes is not decided; Phase 07 leaves them running and lists their ids.

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

=== FILE: phase-01-track-a-coverage.md ===
---
phase: 1
title: "Track A: plan commit, 1m coverage and look-ahead checks"
status: pending
priority: P2
effort: "0.25d"
dependencies: []
---

# Phase 01: Track A: plan commit, 1m coverage and look-ahead checks

## Goal

The plan is on `origin/develop` and in the plan store; the prod `XAUUSD:EXNESS` spec carries the seeded costs; the 12-month window has 1m bars and the derived 5m, 15m and 1h bars it needs; the 1m-entry no-look-ahead tests pass. No backtest runs in this phase.

## Context

- Window and sets: plan.md "Planning rules". Track A sets need intervals `1m`, `5m`, `15m`, `1h`. The top intervals are `15m` (`1m,5m,15m`) and `1h` (`1m,15m,1h`); Triple Screen needs `macd_slow + macd_signal + 1 = 36` top bars before its first decision (`src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py:83`, DEFAULTS `:25-34`). The backtest reads context history before the run start from Mongo.
- Coverage rule, carried from the amended Task 16.1 (`plans/261101-0843-stf-to-mtf-foundation/phase-16-backtests-and-paper-start.md`, "Amended 2026-11-02"; report lines 57-82): the Exness calendar has no holidays, so a derived interval's expected bars are the buckets of the calendar minutes that have a stored 1m bar, and each must reach 99.9 %. For 1m itself the measure is calendar coverage; Phase 16 measured `min_1m_cal_pct=98.33` with venue holidays and early closes. This phase requires `cal_pct >= 98.00` for 1m.
- Calendar API: `TradingCalendarFactory.get` (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26-38`), `trading_minutes` and `bar_start` (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:217-230`), `CALENDAR_EXNESS_XAUUSD` (`src/pocketquant/core/domain/symbol/value_objects.py:15`).
- Seeded gold costs: `commission_per_contract=0.035`, `spread=0.08`, `multiplier=1.0` (`scripts/seed_exness_symbols.py:39-47`). A2: no explicit cost is sent, so the run takes the spread from the spec (`src/pocketquant/engine/backtest/backtest_execution_service.py:43`) and the broker takes the per-contract commission from it (`src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:85-96`).
- Net metrics and per-symbol spread are on master: `f37060aa` and `1e47ca94` are ancestors of `origin/master` (checked 2026-11-09).
- No-look-ahead (`docs/governance/no-look-ahead-rules.md`, "Checks Before Trusting a Multi-Timeframe Backtest"): `tests/backtest_test/test_higher_timeframe_context.py` already checks a `["1m", "1h"]` subscription: the first entry bar of a bucket sees the previous bucket's close (`test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`), entry bars never see their own bucket, a partial bucket is never served, and backtest contexts equal live contexts at every boundary (`test_backtest_contexts_equal_live_contexts_at_every_boundary`). Running it is the governance check for the Track A 1m-entry sets.
- Ops lines: KEY, PRODPY, HEADER are in plan.md "Ops recipe". R = `plans/261109-1349-1m-strategy-evidence/reports`.

## Entry gate

1. EG (1) and (2) from plan.md Conventions. There is no previous report.
2. `git merge-base --is-ancestor 1e47ca94 origin/master && git merge-base --is-ancestor f37060aa origin/master && echo on-master` prints `on-master`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 01 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-01-track-a-coverage.md`.
- Commit (already on disk): the plan directory and `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`.
- Modify: `plan.md` front matter through `ak plan update` only.
- Prod writes: none.

## Tasks

### Task 01.1 — Commit the plan and register it

**Goal:** the plan and its two source reports are on `origin/develop`, and the plan store knows `pocketquant/261109-1349` as `in-progress`.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/`, `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`.

**Steps:**
1. `ak plan validate plans/261109-1349-1m-strategy-evidence`; it must exit 0.
2. `git add plans/261109-1349-1m-strategy-evidence plans/reports/advise-261109-1309-next-plan.md plans/reports/advise-261109-1309-next-plan-state.md`; do not add `.claude/`. Commit `docs(plans): add the 1m strategy evidence plan`. Push with the Ops recipe (Markdown only, no CI).
3. `ak plan --help`, then `ak plan reindex --apply`, then `ak plan update pocketquant/261109-1349 --status in-progress --no-interactive`. Commit the front-matter change `docs(plans): start the 1m strategy evidence plan` and push.

**Success criteria:** the plan validates, is pushed, and the store lists it.

**Verify:** `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `1` then `pushed`.

### Task 01.2 — No-look-ahead tests for a 1m entry (local)

**Goal:** the engine's closed-bucket rule holds for a 1m entry in live, warm-up and backtest before any 1m-entry backtest is trusted.

**Target files and symbols:** `tests/backtest_test/test_higher_timeframe_context.py`.

**Steps:**
1. `docker ps > /dev/null 2>&1 || { "/c/Program Files/Docker/Docker/Docker Desktop.exe" & sleep 20; }`.
2. `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`; record the line in the report.

**Success criteria:** every test in the file passes.

**Verify:** `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `passed` and contains neither `failed` nor `error`.

### Task 01.3 — Prod spec and 1m coverage check (read-only)

**Goal:** the symbol spec holds the seeded costs and every interval the Track A sets read is covered over the window, with enough top-interval history before it.

**Target files and symbols:** prod `symbols`, `bars`; `TradingCalendarFactory.get`, `trading_minutes`, `bar_start`.

**Steps:**
1. KEY. Write `.cache/f.py` as HEADER plus:
```python
from collections import Counter
from datetime import UTC, datetime
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
SYM = "XAUUSD:EXNESS"
START = datetime(2025, 11, 9, tzinfo=UTC)
END = datetime(2026, 11, 9, tzinfo=UTC)
spec = (db.symbols.find_one({"symbol": SYM}) or {}).get("contract_spec") or {}
print(f"spec commission_per_contract={spec.get('commission_per_contract')} spread={spec.get('spread')} multiplier={spec.get('multiplier')}")
first = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", 1)])
last = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", -1)])
print(f"first_1m={first['datetime'].date().isoformat()} bar_calendar={last.get('calendar_id')}")
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)
minutes = set(cal.trading_minutes(START, END))
stored_1m = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find({"symbol": SYM, "interval": "1m", "datetime": {"$gte": START, "$lt": END}}, {"datetime": 1})}
covered_1m = stored_1m & minutes
print(f"1m calendar={len(minutes)} covered={len(covered_1m)} cal_pct={100.0 * len(covered_1m) / len(minutes):.2f} extra={len(stored_1m - minutes)}")
missing = Counter(m.date().isoformat() for m in minutes - stored_1m)
print("missing_1m_top=" + " ".join(f"{d}:{c}" for d, c in missing.most_common(15)))
worst = 100.0
for iv in ["5m", "15m", "1h"]:
    expected = {cal.bar_start(m, Interval(iv)) for m in covered_1m}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    pct = 100.0 * len(expected & stored) / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    print(f"{iv} expected={len(expected)} covered={len(expected & stored)} pct={pct:.2f} before={before}")
print(f"worst_pct={worst:.2f}")
```
2. PRODPY. Append the whole output to the report in a fenced block.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** the spec matches the seed; `first_1m` is on or before `2025-11-09`; `bar_calendar=EXNESS_XAUUSD`; 1m `cal_pct >= 98.00`; 5m, 15m and 1h `pct >= 99.90`; `before >= 36` for `15m` and `1h`.

**Verify:** the output's first line is exactly `spec commission_per_contract=0.035 spread=0.08 multiplier=1.0`; its second line is `first_1m=<date> bar_calendar=EXNESS_XAUUSD` with `<date> <= 2025-11-09`; the `1m calendar=` line shows `cal_pct=<x>` with `x >= 98.00`; the last line is `worst_pct=<n>` with `n >= 99.90`; the `15m` and `1h` lines show `before=` values `>= 36`.

### Task 01.4 — Report and phase close

**Goal:** the phase is recorded and closed, and no key copy remains.

**Target files and symbols:** R/phase-01-track-a-coverage.md; plan store.

**Steps:**
1. Write the report: entry-gate outputs, the Task 01.1 commit shas, the Task 01.2 tail line, the Task 01.3 output; then `Result: PASS` as the last line.
2. `ak plan phase close pocketquant/261109-1349 1 --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the 1m coverage check`; push.

**Success criteria:** report ends `Result: PASS`; HEAD pushed; key gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-01-track-a-coverage.md; test ! -e .cache/ssh/vps_key && echo key-gone; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS`, `key-gone`, `pushed`.

## Rollback

Read-only on prod. The plan commits can be reverted with `git revert <sha>` and pushed (Markdown only).

## Report

`reports/phase-01-track-a-coverage.md`: entry-gate outputs; commit shas; the look-ahead test line; the spec and coverage output; `Result: PASS`.

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

=== FILE: phase-02-track-a-backtests-and-verdicts.md ===
---
phase: 2
title: "Track A: four Triple Screen backtests, table, verdicts"
status: pending
priority: P2
effort: "0.5d (about 2 h of runs)"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen backtests, table, verdicts

## Goal

Four finished 12-month Triple Screen runs on `XAUUSD:EXNESS` with a 1m entry (A1), each followed by a memory reading, recorded in one table, with one `verdict:` line per set under the table.

## Context

- Runs 1-4 of RUNSDEF (plan.md Ops recipe): `1m,5m,15m` and `1m,15m,1h`, each with `entry_type=market, exit_mode=sl_tp` and `entry_type=stop, exit_mode=strategy`. Run 1 (`1m,5m,15m` market) goes first: it has the most entry signals of the four, as the `5m,15m,1h` market run had in Phase 16 (8516 trades, 234 s; `plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md:86`). Expected run time is unverified: the advice estimates 20-25 minutes from the 5x bar ratio.
- Cost: no `spread` and no commission field is sent (A2). The command defaults `commission_bps=3.0` (`src/pocketquant/engine/backtest/backtest_command_service.py:26`) are ignored for gold because a per-contract commission in the spec wins (`src/pocketquant/core/domain/trading/commission_model.py:25-28`).
- Run status is `started`, `finished` or `failed`; `GET /api/v1/backtest/{id}` returns `started_at`, `completed_at`, `metrics` (`src/pocketquant/core/domain/backtest/entities.py:61-79`). There is no cancel route (`src/pocketquant/app/routes/backtest.py`, routes at `:41-158`), so the 1800 s ask is about the next run, not the running one.
- The backtest runs as an asyncio task in the api process with no cap and shares the live Mongo pool (`src/pocketquant/app/routes/backtest.py:46-60`); the three existing paper subscriptions keep trading meanwhile. Hence one run at a time, WINDOWCHK before each run and FREE after each.
- Table format: Phase 16 Task 16.3, with `entry_type`/`exit_mode` folded into `parameters`, a `strategy` column and a `verdict` column.
- Ops lines: KEY, PRODPY, FREE, WINDOWCHK, RUNSDEF, BTRUN, VERDICT in plan.md. R = `plans/261109-1349-1m-strategy-evidence/reports`.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-01-track-a-coverage.md`.

On a miss (here or any `NOT_YET` below), run `rm -f .cache/ssh/vps_key`, edit nothing else and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 02 after <UTC time>
```

## Files

- Create: `R/phase-02-track-a-backtests-and-verdicts.md` with the four headings `## Runs`, `## Table`, `## Verdicts`, `## Notes`, in that order, before Task 02.1.
- Prod writes: four `backtest_runs` with their orders and trades.

## Tasks

### Task 02.1 — Four backtests, one at a time

**Goal:** runs 1-4 finished, each with a `free_after_run=` line.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`; `.cache/f.py`.

**Steps:**
1. KEY. Write `.cache/f.py` as RUNSDEF followed by BTRUN. Record `free_before_runs=<FREE output>` under `## Runs`.
2. For `n` in 1, 2, 3, 4, in order:
   a. Skip `n` when `## Runs` already holds `run=<n> id=... status=finished`.
   b. If `n > 1` and the previous run's line shows `elapsed_s` above `1800` and `## Notes` holds no `cost_ask=<n> yes`: [ASK] (intent) "run <n-1> took <minutes> min; free after it: <line>; start run <n> (<set> <params>)?" `Recommended: yes` when the `available` column of the last `free_after_run=` line is above 500, else `no`; reason: runs are sequential and the paper subscriptions share the api's Mongo pool. Record `cost_ask=<n> <reply>` under `## Notes`; a non-yes ends with `NOT_YET`.
   c. WINDOWCHK. On `window=blocked`, end with `NOT_YET: backtest window` and `Resume ... after <the window time + 46 min>`.
   d. When `## Runs` holds only `run=<n> id=<id> submitted`, PRODPY `<n> <id>` (poll, no new run); else PRODPY `<n>`. Append every printed line under `## Runs`.
   e. FREE; append `free_after_run=<n> <output>` under `## Runs`.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four `status=finished` lines and four `free_after_run=` lines; every ask answered yes is recorded.

**Verify:** `grep -c -E "^run=[1-4] id=\S+ set=\S+ params=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md; grep -c -E "^free_after_run=[1-4] " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md` prints `4` then `4`.

### Task 02.2 — Table

**Goal:** the four runs read side by side.

**Target files and symbols:** `## Table` of the phase report.

**Steps:**
1. Under `## Table` write the header `| # | strategy | intervals | parameters | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate | total_commission | verdict |` and the separator row.
2. One row per run, copied from its `run=<n> ... status=finished` line: `#` = n; `strategy` and `intervals` from `set=<code>:<intervals>`; `parameters` from `params=`; `trades`, `return`, `pf`, `max_dd`, `sharpe`, `win`, `commission` to 4 decimals (`sharpe` 2). `verdict` = `pass` when `pf >= 1.2` and `trades >= 100`, else `fail` (the run's own gate result).

**Success criteria:** four table rows.

**Verify:** `grep -c -E "^\| [1-4] \| triple_screen \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md` prints `4`.

### Task 02.3 — Verdict lines per set

**Goal:** one mechanical `verdict:` line per Track A set directly under the table.

**Target files and symbols:** `.cache/verdict.py`; `## Verdicts`.

**Steps:**
1. Write `.cache/verdict.py` as the VERDICT block (plan.md Ops recipe).
2. `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md`.
3. Paste its two output lines unchanged under `## Verdicts`.

**Success criteria:** two lines, one for `triple_screen:1m,5m,15m` and one for `triple_screen:1m,15m,1h`.

**Verify:** `grep -c -E "^verdict: triple_screen:1m,(5m,15m|15m,1h) (pass|fail) run=[1-4] profit_factor=[0-9.]+ total_trades=[0-9]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md` prints `2`.

### Task 02.4 — Report and phase close

**Goal:** the Track A numbers are on `origin/develop`.

**Target files and symbols:** the phase report; plan store.

**Steps:**
1. Append `Result: PASS` as the last line of the report.
2. `ak plan phase close pocketquant/261109-1349 2 --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the triple screen 1m backtests`; push.

**Success criteria:** report ends `Result: PASS`; pushed; key gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md; test ! -e .cache/ssh/vps_key && echo key-gone; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS`, `key-gone`, `pushed`.

## Rollback

The runs are records and stay. The owner can delete a run in the UI. Nothing else changed on prod.

## Report

`reports/phase-02-track-a-backtests-and-verdicts.md`: `## Runs` (submission and result lines, `free_before_runs=`, four `free_after_run=`), `## Table`, `## Verdicts` (two lines), `## Notes` (any `cost_ask=`), then `Result: PASS`.

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

=== FILE: phase-06-paper-reconciliation.md ===
---
phase: 6
title: "Paper for passing sets: start, 14 days, reconciliation"
status: pending
priority: P2
effort: "0.5d work + 14 days observation (daily check-ins)"
dependencies: [2]
---

# Phase 06: Paper for passing sets: start, 14 days, reconciliation

## Goal

Every set whose verdict is `pass` runs as one paper subscription on `XAUUSD:EXNESS` for at least 14 days with its deciding run's parameters, and a reconciliation record holds the four A5 columns for paper and for its deciding backtest. With no passing set the phase records `paper_sets=0` and creates nothing.

## Context

- Passing sets: the `verdict:` lines with `pass` in `R/phase-02-track-a-backtests-and-verdicts.md`; `run=<n>` names the deciding run, and RUNSDEF entry `n` holds its strategy, intervals and parameters. The deciding run's backtest id is on its `run=<n> id=<id> set=...` line. Failing sets never go to paper (D4).
- One subscription per set fits the unique index on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-131`); the new `1m,...` keys do not collide with the existing `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d`.
- Create and start: `POST /api/v1/strategies/{code}/subscriptions` with `{symbol, intervals, parameters, broker}` returns `id`; a new subscription is `stopped` until `POST /api/v1/subscriptions/{id}/start` (`src/pocketquant/engine/strategy/strategy_command_service.py:77-116`; `src/pocketquant/app/routes/strategy.py:55-63,90`). Mutations need `X-Admin-Token`, read inside the container from `get_settings().admin_token`. All paper subscriptions share one pooled paper account (A5), so per-subscription results come from `trades` by `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:37-39`; index `ix_trades_run_id`, `src/pocketquant/core/infra/persistence/repositories/trade_repository.py:54`).
- A5 columns: trades per trading day; average commission per trade (`Trade.commission`, `src/pocketquant/core/domain/trading/value_objects.py:85-104`); exit-reason mix (`Trade.exit_reason`; values such as `auto_sl`, `auto_tp`, `strategy_exit`, `src/pocketquant/core/domain/brokers/events.py:16-23`); and the count of `strategy_on_bar_error` (`strategy_app_service.py:623`, key `strategy_id=<sub id>`) and stale skips (`strategy.entry_skipped` with `reason=stale`, key `subscription_id=<sub id>`, `strategy_app_service.py:633-647`; 1m bars are stale after 10 s, `:53`). Backtest trades are in `backtest_trades` with `run_id` = backtest run id (`src/pocketquant/engine/backtest/backtest_report_app_service.py:100-117`).
- Trading days: the number of distinct UTC dates with at least one stored `XAUUSD:EXNESS` 1m bar, over whole UTC days only. Paper window: from the first UTC midnight after the latest `paper_started_at` to the UTC midnight of the reconciliation day. Backtest window: the plan window. Trades count by `entry_time` inside the window.
- Commission per trade scales with position size, and paper sizes from the pooled account balance while the backtest starts at 10 000 (`RunBacktestCommand.initial_capital`, `backtest_command_service.py:24`): state that beside the numbers; do not adjust them (R7).
- Trader logs rotate at 10 MB x 3 (`deploy/compose.prod.yml:16-20`) and a redeploy replaces the container, so the error counts come from daily check-ins, each proving the retained log starts before the previous check-in (R6). No deploy is planned during this phase.
- A6: the three existing subscriptions are not touched; SUBS before and after the creates must match for them.
- Ops lines: KEY, SSH, PRODPY, HEADER, SUBS, FREE, TRADERLOG, RUNSDEF in plan.md. R = `plans/261109-1349-1m-strategy-evidence/reports`.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-02-track-a-backtests-and-verdicts.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md` prints `2`.

On a miss (here or any `NOT_YET` below), run `rm -f .cache/ssh/vps_key`, edit nothing else and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 06 after <UTC time>
```

## Files

- Create: `R/phase-06-paper-reconciliation.md`, `.cache/count.py` (local, not committed).
- Prod writes: one subscription created and started per passing set.

## Tasks

### Task 06.1 — Passing sets

**Goal:** the list of sets that go to paper is fixed from the verdict lines.

**Target files and symbols:** the two verdict sections.

**Steps:**
1. `grep -h -E "^verdict: \S+ pass run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md`; copy each line into the report as `paper_set=<set> run=<n> backtest_id=<id from that run's result line>`.
2. Record `paper_sets=<number of lines>`.
3. If `paper_sets=0`, skip Tasks 06.2-06.5, write `No set passed the backtest gate; no paper subscription was created.` and go to Task 06.6.

**Success criteria:** `paper_sets=` equals the number of passing verdict lines.

**Verify:** `test "$(grep -h -c -E "^verdict: \S+ pass run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md | awk '{s+=$1} END {print s}')" = "$(sed -n 's/^paper_sets=//p' plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md)" && echo sets-match` prints `sets-match`.

### Task 06.2 — Create and start the paper subscriptions

**Goal:** one running paper subscription per passing set, with the deciding run's parameters; the three existing subscriptions unchanged.

**Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`, prod `subscriptions`.

**Steps:**
1. KEY. PRODPY with HEADER plus SUBS; record the lines as `subs_before_paper`.
2. Write `.cache/f.py` as HEADER, then RUNSDEF, then:
```python
import sys
import time
import urllib.request
n = int(sys.argv[1])
code, intervals, params = RUNS[n]
API = "http://localhost:41921/api/v1"
token = s.admin_token.get_secret_value()

def post(path, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    return json.load(urllib.request.urlopen(req))

found = db.subscriptions.find_one({"strategy_code": code, "symbol": "XAUUSD:EXNESS", "intervals_key": ",".join(intervals)})
if found and found.get("parameters") != params:
    print(f"conflict id={found['_id']} parameters={json.dumps(found.get('parameters'), sort_keys=True)}")
    sys.exit(1)
sid = found["_id"] if found else post(f"/strategies/{code}/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": intervals, "parameters": params, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
time.sleep(30)
d = db.subscriptions.find_one({"_id": sid})
print(f"paper_sub=run={n} id={sid}")
print(f"state=run={n} {d['desired_state']}/{d['actual_state']} broker={d['broker']} intervals_key={d['intervals_key']} parameters={json.dumps(d['parameters'], sort_keys=True)}")
```
3. For each `paper_set=` line, in report order: skip it when the report already holds `paper_sub=run=<n>`; else record `paper_started_at=run=<n> <UTC ISO now>`, run PRODPY `<n>`, and record both output lines. A `conflict` line is a failed Verify.
4. PRODPY with HEADER plus SUBS; record as `subs_after_paper`. FREE; record `free_after_paper_start=`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** each new subscription is `running/running`, `paper`, on the set's intervals, with the deciding run's parameters; the three existing lines are unchanged.

**Verify:** for each set, its `state=run=<n>` line reads `state=run=<n> running/running broker=paper intervals_key=<RUNS[n] intervals comma-joined> parameters=<RUNS[n] parameters as sorted JSON>`; the `sub triple_screen 5m,15m,1h`, `sub triple_screen 15m,1h,4h` and `sub triple_screen 1h,4h,1d` lines of `subs_after_paper` are identical to those of `subs_before_paper`.

### Task 06.3 — Log counter (local)

**Goal:** a local script counts the A5 error events per subscription in a pulled trader log and proves the log covers the period.

**Target files and symbols:** `.cache/count.py`.

**Steps:**
1. Write `.cache/count.py`:
```python
import re
import sys
from datetime import datetime

since = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
sids = sys.argv[2:]
stamp = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)")
first = None
errors = dict.fromkeys(sids, 0)
stale = dict.fromkeys(sids, 0)
for line in open(".cache/trader.log", encoding="utf-8", errors="replace"):
    m = stamp.search(line)
    if not m:
        continue
    at = datetime.fromisoformat(m.group(1) + "+00:00")
    first = first or at
    if at < since:
        continue
    for sid in sids:
        if "strategy_on_bar_error" in line and f"strategy_id={sid}" in line:
            errors[sid] += 1
        if "strategy.entry_skipped" in line and "reason=stale" in line and f"subscription_id={sid}" in line:
            stale[sid] += 1
print("continuity=" + ("ok" if first is not None and first <= since else "broken"), f"first_log_ts={first.isoformat() if first else 'none'}")
for sid in sids:
    print(f"id={sid} errors={errors[sid]} stale={stale[sid]}")
```

**Success criteria:** the file exists.

**Verify:** `uv run python -c "import ast; ast.parse(open('.cache/count.py').read()); print('parsed')"` prints `parsed`.

### Task 06.4 — Daily check-ins until 14 days have passed (resumable)

**Goal:** the error and stale counts cover the whole paper window with no log gap.

**Target files and symbols:** trader log; the phase report.

**Steps:**
1. Let `since` be the `at=` of the last `checkin=` line, or, before the first check-in, the earliest `paper_started_at=`. Let `k` be the number of `checkin=` lines plus 1.
2. If now is earlier than `since + 24 h` and earlier than the latest `paper_started_at` + 14 days, end with `NOT_YET: next paper check-in` and `Resume ... after <since + 24 h>`.
3. KEY. TRADERLOG without `--since` (the whole retained log). `rm -f .cache/ssh/vps_key`.
4. `uv run python .cache/count.py <since> <every paper sub id>`. Record `checkin=<k> from=<since> at=<UTC ISO now> <first output line>`, then each `id=` line as `checkin=<k> <line>`.
5. If now is earlier than the latest `paper_started_at` + 14 days, end with `NOT_YET: paper window open` and `Resume ... after <now + 24 h, or the 14-day mark if sooner>`. Otherwise continue to Task 06.5.

**Success criteria:** every check-in shows `continuity=ok`; the last check-in is at or after the 14-day mark.

**Verify:** `grep -c -E "^checkin=[0-9]+ from=\S+ at=\S+ continuity=broken" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md` prints `0`, and `uv run python -c "import re,datetime as d; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md').read(); s=max(d.datetime.fromisoformat(x.replace('Z','+00:00')) for x in re.findall(r'^paper_started_at=run=\d+ (\S+)', t, re.M)); a=max(d.datetime.fromisoformat(x.replace('Z','+00:00')) for x in re.findall(r'^checkin=\d+ from=\S+ at=(\S+)', t, re.M)); print('window=' + ('done' if a >= s + d.timedelta(days=14) else 'open'))"` prints `window=done`.

### Task 06.5 — Reconciliation

**Goal:** the four A5 columns for each paper subscription and its deciding backtest, side by side.

**Target files and symbols:** prod `trades`, `backtest_trades`, `bars`; the phase report.

**Steps:**
1. KEY. Write `.cache/f.py` as HEADER plus:
```python
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
n, sid, started, bt_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
SYM = "XAUUSD:EXNESS"

def midnight(t):
    return t.replace(hour=0, minute=0, second=0, microsecond=0)

def days(a, b):
    q = {"symbol": SYM, "interval": "1m", "datetime": {"$gte": a, "$lt": b}}
    return len({d["datetime"].date() for d in db.bars.find(q, {"datetime": 1})})

def stats(coll, run_id, a, b):
    ts = list(db[coll].find({"run_id": run_id, "entry_time": {"$gte": a, "$lt": b}}, {"commission": 1, "exit_reason": 1}))
    count, dd = len(ts), days(a, b)
    avg = sum(t.get("commission", 0.0) for t in ts) / count if count else 0.0
    mix = dict(Counter(str(t.get("exit_reason")) for t in ts))
    return f"trades={count} days={dd} trades_per_day={count / dd if dd else 0:.3f} avg_commission={avg:.4f} exit_mix={json.dumps(mix, sort_keys=True)}"

p_from = midnight(datetime.fromisoformat(started.replace("Z", "+00:00"))) + timedelta(days=1)
p_to = midnight(datetime.now(UTC))
print(f"reconcile=run={n} paper {stats('trades', sid, p_from, p_to)} window={p_from.date()}..{p_to.date()}")
print(f"reconcile=run={n} backtest {stats('backtest_trades', bt_id, datetime(2025, 11, 9, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC))}")
```
2. For each set: PRODPY `<n> <paper sub id> <paper_started_at of run n> <backtest_id>`; record both lines. After the last set, `rm -f .cache/ssh/vps_key`.
3. For each paper sub id, sum its check-ins: `grep -E "^checkin=[0-9]+ id=<sid> " plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md | sed -E 's/.*errors=([0-9]+) stale=([0-9]+).*/\1 \2/' | awk '{e+=$1; s+=$2} END {print "errors=" e " stale=" s}'`; record `events=run=<n> <output>`.
4. Write `## Reconciliation` with the header `| run | set | source | trades | days | trades/day | avg commission/trade | exit-reason mix | strategy_on_bar_error | stale skips |` and two rows per set (`paper`, `backtest`; the backtest row shows `n/a` in the last two columns), copied from the lines above. Under the table write one sentence: commission per trade scales with position size, and paper sizes from the pooled paper balance while the backtest starts at 10 000.

**Success criteria:** two `reconcile=` lines, one `events=` line and two table rows per set.

**Verify:** for `S` = the `paper_sets=` value, `grep -c "^reconcile=run=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md; grep -c "^events=run=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md; grep -c -E "^\| [1-4] \| \S+ \| (paper|backtest) \| " plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md` prints `2S`, `S`, `2S`.

### Task 06.6 — Report and phase close

**Goal:** the paper record is on `origin/develop`.

**Target files and symbols:** the phase report; plan store.

**Steps:**
1. Append `Result: PASS`.
2. `ak plan phase close pocketquant/261109-1349 6 --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the 1m paper reconciliation`; push.

**Success criteria:** report pushed; key gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md; test ! -e .cache/ssh/vps_key && echo key-gone; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS`, `key-gone`, `pushed`.

## Rollback

[ASK] each step. For a new paper subscription only (never the three existing ones): `POST /api/v1/subscriptions/<id>/stop`, wait until `actual_state` is `stopped`, then `DELETE /api/v1/subscriptions/<id>` (`src/pocketquant/app/routes/strategy.py:99,161`), from a PRODPY script with the token header. Its closed trades stay as records.

## Report

`reports/phase-06-paper-reconciliation.md`: entry-gate outputs; `paper_set=` lines and `paper_sets=`; `subs_before_paper` / `subs_after_paper`; `paper_started_at=`, `paper_sub=`, `state=` lines; `free_after_paper_start=`; every `checkin=` block; `reconcile=` and `events=` lines; `## Reconciliation`; then `Result: PASS`.

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

=== FILE: phase-07-verdicts-close-archive.md ===
---
phase: 7
title: "Final verdicts, close and archive"
status: pending
priority: P2
effort: "0.1d"
dependencies: [6]
---

# Phase 07: Final verdicts, close and archive

## Goal

One file states the final pass/fail verdict per set with its gate values and its paper outcome (D5); the plan is `status: completed` and lives under `plans/archive/`.

## Context

- The final verdict of a set is its backtest verdict (D4); the paper reconciliation is attached, not a gate (plan.md "Planning rules").
- Archive convention: the previous plan was archived by moving its directory under `plans/archive/` in a `docs(plans)` commit (`git show --stat 00272823`).
- Plan close through the CLI: `ak plan update <id> --status completed` rewrites the `plan.md` front matter (`ak plan update --help`).
- The new paper subscriptions keep running; whether to stop them is not decided (plan.md "Unresolved"), so this phase lists their ids and leaves them.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-06-paper-reconciliation.md`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 07 after <UTC time>
```

## Files

- Create: `R/final-verdicts.md`, `R/phase-07-verdicts-close-archive.md`.
- Modify: `plan.md` front matter through `ak plan update` only.
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.

## Tasks

### Task 07.1 — Final verdict file

**Goal:** one line per set with the verdict, the gate values and the paper outcome.

**Target files and symbols:** `R/final-verdicts.md`.

**Steps:**
1. Write `R/final-verdicts.md`: a heading `# Final verdicts`; the gate sentence `A set passes when one of its runs has net profit_factor >= 1.2 and total_trades >= 100 over 2025-11-09..2026-11-08 on XAUUSD:EXNESS.`; then the two `verdict:` lines copied unchanged from the Phase 02 report, each with ` paper=<value>` appended, where `<value>` is `reconciled sub=<paper sub id>` for a set with a `paper_sub=` line in the Phase 06 report, else `not-run`.
2. Under them, one line per paper subscription: `running_paper_sub=<id> set=<set>` (left running; owner decides).
3. If no set passed, add the sentence `No 1m set passed the gate at the seeded Exness Raw Spread gold costs.`

**Success criteria:** two verdict lines with a paper value.

**Verify:** `grep -c -E "^verdict: \S+ (pass|fail) run=[1-4] profit_factor=[0-9.]+ total_trades=[0-9]+ paper=(reconciled sub=\S+|not-run)$" plans/261109-1349-1m-strategy-evidence/reports/final-verdicts.md` prints `2`.

### Task 07.2 — Close and archive

**Goal:** the plan is completed, archived and pushed.

**Target files and symbols:** `plan.md` front matter; the plan directory.

**Steps:**
1. Write the phase report (the acceptance table AC1-AC8 from plan.md, each row with the report path and line that proves it), ending with `Result: PASS`.
2. `ak plan --help`; `ak plan phase close pocketquant/261109-1349 7 --no-interactive`; `ak plan update pocketquant/261109-1349 --status completed --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; `git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`.
4. Commit `docs(plans): record the 1m verdicts and archive the plan`; push (Markdown only, no CI).
5. `test ! -e .cache/ssh/vps_key && echo key-gone`.

**Success criteria:** archived, completed, pushed, no key copy.

**Verify:** `test -d plans/archive/261109-1349-1m-strategy-evidence && test ! -e plans/261109-1349-1m-strategy-evidence && echo archived; grep -c "^status: completed$" plans/archive/261109-1349-1m-strategy-evidence/plan.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed; test ! -e .cache/ssh/vps_key && echo key-gone` prints `archived`, `1`, `pushed`, `key-gone`.

## Rollback

`git mv plans/archive/261109-1349-1m-strategy-evidence plans/261109-1349-1m-strategy-evidence`, `ak plan update pocketquant/261109-1349 --status in-progress --no-interactive`, commit and push.

## Report

`reports/phase-07-verdicts-close-archive.md`: entry-gate output; the AC1-AC8 table with evidence lines; the `ak plan` outputs; then `Result: PASS`.

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
