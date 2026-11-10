=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry, gated backtests, paper reconciliation"
description: "Backtest Triple Screen with a 1m entry screen on 12 months of XAUUSD:EXNESS, gate each set on net profit_factor >= 1.2 and >= 100 trades, paper-test only passing sets for 14 days, reconcile against the backtest and write a pass/fail verdict per set."
status: pending
priority: P2
effort: "about 1.5d hands-on + 4 backtest runs + 14 days paper"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, xauusd, exness]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m strategy evidence on `XAUUSD:EXNESS` with the owner's own gate. The plan backtests Triple Screen with a 1m entry screen and needs no code. Each set passes or fails on net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets run on paper, for 14 days, to reconcile with the backtest. The plan closes with one written verdict per set and moves to `plans/archive/`. A fail for every set is a valid, useful outcome.

The plan is written for a downstream executor model. Every phase carries tasks with Goal, Target files, Steps, Success criteria and a mechanical Verify, and ends with the same Failure Protocol block.

## Sources

- Fixed brief: `reports/evidence-packet.md` (D1-D5, A1-A6, constraints, handover contract).
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`; interview record `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and ops exemplar: `plans/261101-0843-stf-to-mtf-foundation/phase-15-release-d2.md` (Ops lines, LIVECHK), `phase-16-backtests-and-paper-start.md` (run script, coverage check, run table, 1800 s ask), `phase-14-triple-screen.md` (strategy and test shape).
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Code rules: `CLAUDE.md`, `docs/code-standards.md`. Deploy: `docs/deployment.md`.

## Owner decisions (interview 2026-11-09, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

## Confirmed assumptions

- A1: The plan runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`.
- A2: Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when a run exceeds 1800 s.
- A5: Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id`, because the paper account is pooled.
- A6: The three existing Triple Screen paper subscriptions keep running and are not touched.

## Planning verdicts (fixed here; do not re-decide in a phase)

- **P1 Window.** Every run uses one fixed window: `start_date=2025-11-07T00:00:00`, `end_date=2026-11-06T23:59:00` (12 months; stored 1m history starts 2025-10-21, `phase-16-backtests-and-paper-start.md` report line `first_1m=2025-10-21`).
- **P2 Set and verdict.** A set is a strategy plus its interval list: `triple_screen 1m,5m,15m` (runs 1, 2), `triple_screen 1m,15m,1h` (runs 3, 4). A set passes when at least one of its runs meets the gate. Its paper subscription uses the passing run with the highest `profit_factor` (ties: more trades). Reason: the unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)` allows one subscription per set (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-132`). The verdict is the gate's. The paper reconciliation is recorded beside it and changes no verdict (D4: no paper threshold).
- **P8 Run order.** Run 1 (`1m,5m,15m`, market, sl_tp) goes first: it has the most entry signals, as the 5m set did in Phase 16 (8516 trades, 234 s).

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions; a second shifted window; archiving other plans; compare-view URLs.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one fresh worker per phase. File order is execution order. All phases are sequential; no phase edits repo code.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`. Every Verify is one self-contained command run from there. The shell keeps no variables between commands. Times are UTC.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md`, where `<slug>` is the phase file's slug. Each phase ends its report with `Result: PASS` when every task passed, then commits the report (`docs(plans): record <what the phase did>`) and pushes `develop` with the Push recipe. `plans/**` is in the CI `paths-ignore` (`.github/workflows/cicd.yml:5-10`), so report commits run no CI.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) after `git fetch -q origin`, `git rev-parse HEAD` equals `git rev-parse origin/develop`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) the phase-specific lines. A resumed phase may show its own uncommitted task files and `HEAD` ahead of `origin/develop` by its own commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts. "No" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Record the answer in English in the report.
- **Stop-and-ask points:** any backtest run whose age or elapsed time passes 1800 s (Phase 02); re-submitting a failed run; any destructive prod action; any change outside the confirmed scope.
- **Search** uses `git grep` (`rg` is not installed in Git Bash).
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` exits 0; `uv run pyright <touched .py files>` prints `0 errors`. If only the metric ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the report; never pad or split code to pass it.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the count prints `0` (the excluded modules are the known local timezone failures). Record the tail line. About 100 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references); Push; then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`.
- **No plan ids**, phase numbers, decision codes or finding codes in code, comments, test names, log events or commit messages.
- **Code** follows `CLAUDE.md`: no docstrings (a WHY goes in a `#` comment), a flow reads in one file, at most two hops to I/O, no new class/flag/param/helper without a real caller today, UUIDv7 ids, repositories only in `core.infra.persistence.repositories`, fastapi only in app, log level by frequency.
- **Prod** is read-only except the planned backtest runs (Phase 02) and the paper subscription creates and starts (Phase 06). Live stays disarmed. Secrets never go on a command line, into a report or into the repo.

## Recipes (phases cite these by name)

- **KEY**: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`. Every phase that ran KEY ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit.
- **SSH `<cmd>`**: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`.
- **COMPOSE**: on the VPS, `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`.
- **PRODPY `<name>` `[args]`**: write the script to `.cache/<name>.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/<name>.py' < .cache/<name>.py && ssh -o ServerAliveInterval=60 -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/<name>.py api:/tmp/<name>.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/<name>.py [args]'`. It runs inside the `api` container.
- **HEADER** (first lines of every PRODPY script that reads Mongo): `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]`.
- **ADMINGET** (after HEADER, for admin-guarded reads): `import json` / `import urllib.request` / `def admin_get(path):` / `    req = urllib.request.Request("http://localhost:41921/api/v1" + path, headers={"X-Admin-Token": s.admin_token.get_secret_value()})` / `    return json.load(urllib.request.urlopen(req))`.
- **LIVECHK**: write `.cache/live.py` with `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'`. Pass: `trader_live=False`. It runs in `trader` because only the trader has no `EXNESS_LIVE_TRADING` pin (`deploy/compose.prod.yml:75-83,109-114`).
- **Push**: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; check `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed`. Never print a token.
- **FREE `<label>`**: SSH `free -m | grep Mem:`; append `<label> <output line>` to the report.
- **WINDOW**: `uv run python -c "import datetime as d; n=d.datetime.now(d.UTC); m=n.hour*60+n.minute; print('window_ok=' + ('yes' if 15<=m<140 or 195<=m<1400 else 'no'))"`. A run may start only on `window_ok=yes` (00:15-02:20Z or 03:15-23:20Z), so it starts at least 40 min before and 15 min after the 00:00Z and 03:00Z repair and backfill jobs. On `no`, end with `NOT_YET` and resume at the next allowed minute.
- **ORIG3** (A6 check), PRODPY `orig3` with HEADER plus: `rows = sorted((d["intervals_key"], d.get("desired_state"), d.get("actual_state")) for d in db.subscriptions.find({"strategy_code": "triple_screen", "intervals_key": {"$in": ["5m,15m,1h", "15m,1h,4h", "1h,4h,1d"]}}))` / `print("original_subs=" + ";".join(f"{k}:{a}/{b}" for k, a, b in rows))`. Phase 01 records the baseline line; later phases pass when the line equals it.
- **BTRUN**: the run script `.cache/bt.py`, used with PRODPY `bt <n>` (submit) and PRODPY `bt <n> <id>` (poll, at most 480 s per call; give the Bash call a 590000 ms timeout):

```python
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime

from pocketquant.core.config import get_settings

RUNS = {
    1: ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    2: ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "stop", "exit_mode": "strategy"}),
    3: ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    4: ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "stop", "exit_mode": "strategy"}),
}
START = "2025-11-07T00:00:00"
END = "2026-11-06T23:59:00"
BASE = "http://localhost:41921/api/v1/backtest"


def at(value):
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


n = int(sys.argv[1])
strategy, intervals, parameters = RUNS[n]
if len(sys.argv) == 2:
    label = " ".join(f"{k}={v}" for k, v in sorted(parameters.items())) or "defaults"
    body = {
        "strategy_id": strategy, "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": START, "end_date": END, "parameters": parameters,
        "name": f"{strategy} {' '.join(intervals)} {label}",
    }
    token = get_settings().admin_token.get_secret_value()
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    print(f"run={n} id={json.load(urllib.request.urlopen(req))['request_id']}")
    sys.exit(0)
run_id = sys.argv[2]
deadline = time.time() + 480
while True:
    doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
    if doc["status"] != "started" or time.time() > deadline:
        break
    time.sleep(30)
if doc["status"] == "started":
    age = (datetime.now(UTC) - at(doc["started_at"])).total_seconds()
    print(f"run={n} id={run_id} status=started age_s={int(age)}")
    sys.exit(0)
m = doc.get("metrics") or {}
elapsed = (at(doc["completed_at"]) - at(doc["started_at"])).total_seconds()
print(
    f"run={n} id={run_id} status={doc['status']} elapsed_s={int(elapsed)} trades={m.get('total_trades')} "
    f"return={m.get('total_return')} pf={m.get('profit_factor')} max_dd={m.get('max_drawdown')} "
    f"sharpe={m.get('sharpe_ratio')} win={m.get('win_rate')} error={doc.get('error_message')}"
)
```

  No `spread`, `commission_bps` or commission key is sent: the backtest takes the spread from the symbol spec when the run sets none (`src/pocketquant/engine/backtest/backtest_execution_service.py:43`) and a per-contract commission wins over bps (`src/pocketquant/core/domain/trading/commission_model.py:25-28`, fed from the spec at `backtest_sandbox_app_service.py:93-95`). `profit_factor` is already net of commission (`src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:198-217`).

- **VERDICT**: the local script `.cache/verdict.py`, run as `uv run python .cache/verdict.py "<set>" <report files...>`. It is the one gate implementation:

```python
import re
import sys

SETS = {
    "triple_screen 1m,5m,15m": (1, 2),
    "triple_screen 1m,15m,1h": (3, 4),
}
LINE = re.compile(r"^run=(\d) id=(\S+) status=finished elapsed_s=\d+ trades=(\d+) return=\S+ pf=(\S+) ")
runs = {}
for path in sys.argv[2:]:
    for line in open(path, encoding="utf-8"):
        m = LINE.match(line)
        if m:
            runs[int(m[1])] = (m[2], int(m[3]), float(m[4]))
name = sys.argv[1]
nums = SETS[name]
missing = [n for n in nums if n not in runs]
if missing:
    sys.exit(f"missing finished runs {missing}")
passing = [n for n in nums if runs[n][2] >= 1.2 and runs[n][1] >= 100]
best = max(passing, key=lambda n: (runs[n][2], runs[n][1])) if passing else None
detail = " ".join(f"run{n}:pf={runs[n][2]:.4f},trades={runs[n][1]}" for n in nums)
paper = f"{best}:{runs[best][0]}" if best else "none"
print(f"verdict: {name} {'pass' if passing else 'fail'} {detail} paper_run={paper}")
```

## Data flows

- **Backtest.** BTRUN in the `api` container posts `RunBacktestCommand` to `POST /api/v1/backtest/run` (`src/pocketquant/app/routes/backtest.py:48-60`). `BacktestCommandService.run` validates through `check_strategy_inputs` and stores a `started` doc (`src/pocketquant/engine/backtest/backtest_command_service.py:52-70`). `BacktestExecutionService.run` reads the symbol's `ContractSpec` (`backtest_execution_service.py:101-102`), puts it on `StrategyConfig.contract_spec` (`:111-119`) and on the paper broker (`:124-130`), replays stored 1m bars and preloads the higher intervals once. Results land in `backtest_runs` and `backtest_trades` (`run_id` = run id). BTRUN polls `GET /api/v1/backtest/{id}`; the report line feeds VERDICT, which prints one `verdict:` line per set.
- **Paper.** The `paper_run=<n>:<id>` of a passing verdict names a backtest run. PAPER reads that run's `strategy_code`, `intervals`, `parameters` from `backtest_runs` and creates and starts one `broker=paper` subscription with exactly those. The trader's reconcile loop loads it with the symbol spec; its closed trades land in `trades` with `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:39`). Engine errors and stale skips go to the trader log (`src/pocketquant/engine/strategy/strategy_app_service.py:623,631-649`). Phase 07 counts them per subscription from the logs and reads trades by `run_id`.

## Phases

| # | Phase | Prod writes | Depends on | Status |
|---|---|---|---|---|
| 01 | [Commit the plan; A6 baseline; 1m coverage and cost spec check](./phase-01-data-coverage.md) | none | — | Pending |
| 02 | [Four Triple Screen 1m backtests, table, verdicts](./phase-02-triple-screen-1m-backtests.md) | 4 backtest runs | 01 | Pending |
| 06 | [Paper: one subscription per passing set](./phase-06-paper-start.md) | subscription creates and starts | 02 | Pending |
| 07 | [Paper: 14 days of log check-ins and the reconciliation](./phase-07-paper-reconcile.md) | none | 06 | Pending |
| 08 | [Close: verdicts in plan.md, completed, archive](./phase-08-close-and-archive.md) | none | 07 | Pending |

Phase 06 needs every verdict; this keeps one paper start and one reconciliation.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run finished and is in a table with `profit_factor` and `total_trades` | Phase 02 Verify: 4 `status=finished` lines and table rows |
| AC2 | One verdict line per set (2 sets) | `grep -c "^verdict: " plans/archive/261109-1349-1m-strategy-evidence/plan.md` prints `2` |
| AC5 | One paper subscription per passing set, at least 14 days, with the four A5 columns | Phase 07 `reconcile_backtest:`, `reconcile_paper:`, `reconcile_errors:` lines per set |
| AC6 | The three original subscriptions are untouched | ORIG3 equals the Phase 01 baseline in Phases 06, 08 |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` and `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Integration (existing) | spec reaches the backtest config and broker; reconcile loads the symbol spec | `tests/backtest_test/test_backtest_dispatch_contract_spec.py`, `tests/engine_test/test_contract_spec_wiring.py` |
| End to end | 4 prod backtests; paper subscriptions trading live 1m bars for 14 days | Phases 02, 06, 07 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes over 1800 s and loads the shared Mongo pool while three paper subscriptions trade | M x M | One run at a time, WINDOW guard, FREE after each run, [ASK] once a run passes 1800 s |
| R2 | 1m or cascaded bars have holes in the window | L x H | Phase 01 coverage check stops the plan before any run |
| R4 | Trader log rotation (`max-size 10m`, `max-file 3`, `deploy/compose.prod.yml:16-20`) or a container recreate loses error lines inside the 14 days | M x M | Check-ins at most every 3 days; each one proves the oldest kept log line is not later than its `since` |
| R5 | 1m paper entries hit the 10 s stale limit (`_STALE_AFTER_S["1m"]`, `strategy_app_service.py:53`) | M x L | Counted in the reconciliation as recorded; no fix in scope |
| R6 | Single window and best-of-two selection overstate an edge | H x M | Accepted by the owner (DSR/PBO deferred); stated in the verdict section |
| R8 | No set passes | H x L | A valid result: Phases 06-07 record `paper_sets=none` and the plan closes with fail verdicts |

## Rollback (per phase)

01, 02, 07: no repo or prod state to undo (backtest runs stay; the owner can delete them in the UI). 06: [ASK] then stop and delete only the new subscriptions (never the three originals). 08: `git mv` the folder back and restore `status`.

## Backwards compatibility and docs impact

The plan changes no repo code: no schema, index, route, config key or migration changes; Triple Screen and the existing subscriptions are untouched. Docs impact: none.

## Unresolved questions

1. P2: a set passes when either of its runs passes, because only one subscription per set can exist.
2. The new paper subscriptions keep running after the plan closes unless the owner says otherwise.
3. Phase 01 accepts 1m calendar coverage from 98.00 % (D16 measured 98.33 % over 2025-11-03..2026-10-31 and the owner accepted the gaps as venue closures).

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

=== FILE: phase-01-data-coverage.md ===
---
phase: 1
title: "Commit the plan; A6 baseline; 1m coverage and cost spec check"
status: pending
priority: P2
effort: "0.5h"
dependencies: []
---

# Phase 01: Commit the plan; A6 baseline; 1m coverage and cost spec check

## Goal

The plan is on `origin/develop`, the state of the three original subscriptions is recorded, and the 12-month window (P1) has full 1m and cascaded `5m`, `15m`, `1h` coverage with the seeded gold costs in place, so the runs compare like with like.

## Context

- Window P1: `2025-11-07T00:00Z` to `2026-11-07T00:00Z` (runs end at `2026-11-06T23:59`).
- Coverage rule (carried from the amended Task 16.1 in `plans/261101-0843-stf-to-mtf-foundation/phase-16-backtests-and-paper-start.md` and its report): for `5m`, `15m`, `1h`, `expected` is the set of buckets of the calendar minutes that have a stored 1m bar, and `pct >= 99.90`. For `1m` itself the measure is `cal_pct` = stored calendar minutes / calendar minutes; the D16 run measured `min_1m_cal_pct=98.33` and the owner accepted the gaps as venue holidays and early closes, so the pass floor is `98.00`.
- Triple Screen needs `macd_slow + macd_signal + 1 = 36` top-interval bars before its first decision (`src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py:83`); the top intervals are `15m` and `1h`; the context reads history before the run start from Mongo. So every interval needs `before >= 36`.
- Calendar: `CALENDAR_EXNESS_XAUUSD` (`src/pocketquant/core/domain/symbol/value_objects.py:15`); `TradingCalendarFactory.get` needs no lookup (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26-38`); `trading_minutes` and `bar_start` (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:217,229`).
- Costs A2/A4: seed `commission_per_contract=0.035`, `spread=0.08`, `multiplier=1.0` (`scripts/seed_exness_symbols.py:40-48`); the symbol document stores them under `contract_spec` (`src/pocketquant/core/domain/symbol/entities.py:78-88`).
- Recipes: plan.md KEY, PRODPY, HEADER, ORIG3, Push.

## Entry gate

1. Conventions EG (1). EG (2) and (3) do not apply: this phase pushes the plan first.
2. `git branch --show-current` prints `develop`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 01 after <UTC time>
```

## Files

- Repo: commit the plan folder and the two advice reports; this phase's report.
- Prod writes: none.

## Tasks

### Task 01.1 — Commit and push the plan

**Goal:** every later entry gate can compare `HEAD` with `origin/develop`.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/`, `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`.

**Steps:**
1. `git add plans/261109-1349-1m-strategy-evidence plans/reports/advise-261109-1309-next-plan.md plans/reports/advise-261109-1309-next-plan-state.md`.
2. `git commit -m "docs(plans): add the 1m strategy evidence plan"`.
3. Push (plan.md recipe).

**Success criteria:** the plan commit is on `origin/develop`.

**Verify:** `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && git ls-tree -r --name-only HEAD plans/261109-1349-1m-strategy-evidence/plan.md` prints `plans/261109-1349-1m-strategy-evidence/plan.md`.

### Task 01.2 — A6 baseline of the three original subscriptions

**Goal:** later phases can prove the three Triple Screen paper subscriptions were not touched.

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. PRODPY `orig3` (plan.md ORIG3).
2. Append the printed line to the report as `baseline_` + the line (for example `baseline_original_subs=15m,1h,4h:running/running;...`).

**Success criteria:** the baseline lists three interval keys.

**Verify:** `grep -c -E "^baseline_original_subs=[^;]+;[^;]+;[^;]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md` prints `1`.

### Task 01.3 — Coverage and cost spec check (read-only)

**Goal:** the window is fully covered and the seeded gold costs are in the symbol spec.

**Target files and symbols:** prod `bars`, `symbols`; `TradingCalendarFactory.get`, `trading_minutes`, `bar_start`.

**Steps:**
1. PRODPY `cover` with HEADER plus:
```python
from datetime import UTC, datetime
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
SYM = "XAUUSD:EXNESS"
START = datetime(2025, 11, 7, tzinfo=UTC)
END = datetime(2026, 11, 7, tzinfo=UTC)
spec = (db.symbols.find_one({"symbol": SYM}) or {}).get("contract_spec") or {}
spec_line = f"spec commission_per_contract={spec.get('commission_per_contract')} spread={spec.get('spread')} multiplier={spec.get('multiplier')}"
print(spec_line)
first = db.bars.find_one({"symbol": SYM, "interval": "1m"}, sort=[("datetime", 1)])
print(f"first_1m={first['datetime'].date().isoformat()}")
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)
minutes = set(cal.trading_minutes(START, END))
q1 = {"symbol": SYM, "interval": "1m", "datetime": {"$gte": START, "$lt": END}}
stored_1m = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q1, {"datetime": 1})}
traded = minutes & stored_1m
cal_pct = 100.0 * len(traded) / len(minutes)
print(f"1m cal_minutes={len(minutes)} stored={len(traded)} cal_pct={cal_pct:.2f} extra={len(stored_1m - minutes)}")
missing = {}
for m in minutes - stored_1m:
    missing[m.date()] = missing.get(m.date(), 0) + 1
print("missing_1m_dates=" + ",".join(f"{d.isoformat()}:{n}" for d, n in sorted(missing.items()) if n >= 60))
worst, fewest = 100.0, None
for iv in ["5m", "15m", "1h"]:
    expected = {cal.bar_start(m, Interval(iv)) for m in traded}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    pct = 100.0 * len(expected & stored) / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    fewest = before if fewest is None else min(fewest, before)
    print(f"{iv} expected={len(expected)} covered={len(expected & stored)} pct={pct:.2f} before={before}")
print(f"worst_pct={worst:.2f}")
ok = (
    spec_line == "spec commission_per_contract=0.035 spread=0.08 multiplier=1.0"
    and first["datetime"].date() <= START.date()
    and cal_pct >= 98.0
    and worst >= 99.9
    and fewest >= 36
)
print("coverage_ok=" + ("yes" if ok else "no"))
```
2. Append the whole output to the report.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** costs match the seed, the 1m history starts before the window, `cal_pct >= 98.00`, every cascaded interval `pct >= 99.90`, every `before >= 36`.

**Verify:** the PRODPY output's first line is `spec commission_per_contract=0.035 spread=0.08 multiplier=1.0` and its last line is `coverage_ok=yes`.

### Task 01.4 — Report and push

**Goal:** the evidence is in git.

**Target files and symbols:** `reports/phase-01-data-coverage.md`.

**Steps:**
1. The report holds the Task 01.1 commit sha, the baseline line, the Task 01.3 output, then `Result: PASS` as its last line.
2. `git add plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md && git commit -m "docs(plans): record the 1m coverage check"`; Push.

**Success criteria:** the report is on `origin/develop`.

**Verify:** `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md | tail -1` prints `Result: PASS`.

## Rollback

Nothing to roll back: the phase only reads prod and commits docs.

## Report

`reports/phase-01-data-coverage.md`: entry-gate outputs, the plan commit sha, `baseline_original_subs=`, the full coverage output, `Result: PASS`.

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

=== FILE: phase-02-triple-screen-1m-backtests.md ===
---
phase: 2
title: "Four Triple Screen 1m backtests, table, verdicts"
status: pending
priority: P2
effort: "about 2h wall time (estimate 20-25 min per run)"
dependencies: [1]
---

# Phase 02: Four Triple Screen 1m backtests, table, verdicts

## Goal

Four finished 12-month backtests of Triple Screen with a 1m entry screen (A1), each followed by a memory reading, one table, and one `verdict:` line per set from VERDICT.

## Context

- No code change: `check_strategy_inputs` requires only strictly ascending intervals, each a multiple of the entry interval (`src/pocketquant/core/domain/strategy/services/__init__.py:36-48`); Triple Screen requires exactly three (`triple_screen_strategy_service.py:48-49`). `1m,5m,15m` and `1m,15m,1h` pass today. Do not change Triple Screen (non-goal).
- No look-ahead: the engine serves only higher-timeframe bars closed by the entry bar's start, in live, warm-up and backtest alike (`docs/governance/no-look-ahead-rules.md`; `StrategyAppService._refresh_context` and `preload_context`, `src/pocketquant/engine/strategy/strategy_app_service.py:354-400`). This phase adds nothing that bypasses it.
- Runs 1-4 of BTRUN (plan.md), `1m,5m,15m` first (P8). Costs from the spec (A2); nothing explicit is sent.
- Cost: a run is an asyncio task in the `api` process with no concurrency cap and shares the live Mongo pool (`src/pocketquant/app/routes/backtest.py:46-47`). The 5m set took 234-273 s in D16; 1m has about five times the bars, so the estimate is 20-25 min [UNVERIFIED until run 1 ends]. Run status is `started`, `finished` or `failed` (`src/pocketquant/core/domain/backtest/entities.py:23`).
- A Bash call times out at 600 s, so BTRUN polls at most 480 s per call and the executor repeats the poll.
- Recipes: plan.md KEY, SSH, PRODPY, BTRUN, VERDICT, WINDOW, FREE.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-01-data-coverage.md`.
2. `grep -c "^coverage_ok=yes$" plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 02 after <UTC time>
```

## Files

- Repo: this phase's report only. Local scratch: `.cache/bt.py`, `.cache/verdict.py` (git-ignored by `.gitignore:39`).
- Prod writes: four `backtest_runs` (Task 02.1).

## Tasks

### Task 02.1 — Four backtests, one at a time, run 1 first

**Goal:** four `status=finished` runs, each followed by a `free -m` line; any run over 1800 s has an owner yes.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`; `.cache/bt.py`.

**Steps:**
1. Write `.cache/bt.py` with the exact BTRUN text from plan.md. KEY.
2. For `n` in `1, 2, 3, 4`, in order:
   a. If the report holds `run=<n> id=<id> status=finished`, skip `n`.
   b. If the report holds `run=<n> id=<id>` but no finished line, go to step d with that id (never submit twice).
   c. Otherwise run WINDOW. On `window_ok=no`, run `rm -f .cache/ssh/vps_key` and end with `NOT_YET: outside the backtest window` and a resume time at the next allowed minute. On `window_ok=yes`, PRODPY `bt <n>`; append the printed `run=<n> id=<id>` line to the report.
   d. PRODPY `bt <n> <id>` with a 590000 ms Bash timeout. Repeat while the printed line shows `status=started`. The first time a started line shows `age_s` above `1800`, append it to the report and do step f before polling again.
   e. Append the final line (`status=finished` or `status=failed`). Then FREE `free_after_run=<n>`.
   f. [ASK] (once per run, when `age_s` or `elapsed_s` passes 1800): "Run <n> (`<intervals> <entry_type>/<exit_mode>`) has taken <minutes> min; `free -m`: <Mem line>. Continue: wait for it and run the rest one at a time?" `Recommended: yes`, reason: the paper subscriptions run in the trader container and share only the Mongo pool; runs stay one at a time. Record `cost_ask=<n> <reply>`. A non-yes: `rm -f .cache/ssh/vps_key`, end with `NOT_YET` (the run keeps going on prod; a resume polls it by its id).
3. A `status=failed` line, or a started line with `age_s` above `10800`, is a failed Verify. Never re-submit a run without the owner's explicit yes.
4. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four finished lines, four `free_after_run=` lines, and a `cost_ask=<n> yes` line for every run that passed 1800 s.

**Verify:** `grep -c -E "^run=[1-4] id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md; grep -c "^free_after_run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md` prints `4` then `4`.

### Task 02.2 — Run table and verdict lines

**Goal:** the four runs read side by side, and each set has one gate verdict.

**Target files and symbols:** the phase report; `.cache/verdict.py`.

**Steps:**
1. Write a table `| # | strategy | intervals | parameters | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate |` with one row per run (`| 1 | triple_screen | 1m 5m 15m | market/sl_tp | ...`), values copied from the Task 02.1 finished lines.
2. Write `.cache/verdict.py` with the exact VERDICT text from plan.md.
3. Run `uv run python .cache/verdict.py "triple_screen 1m,5m,15m" plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md` and `uv run python .cache/verdict.py "triple_screen 1m,15m,1h" plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md`. Append both printed lines under the table, unchanged.

**Success criteria:** 4 table rows and 2 verdict lines.

**Verify:** `grep -c -E "^\| [1-4] \| triple_screen \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md; grep -c -E "^verdict: triple_screen (1m,5m,15m|1m,15m,1h) (pass|fail) " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md` prints `4` then `2`.

### Task 02.3 — Report and push

**Goal:** the backtest evidence is in git.

**Target files and symbols:** `reports/phase-02-triple-screen-1m-backtests.md`.

**Steps:**
1. End the report with `Result: PASS`.
2. `git add plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md && git commit -m "docs(plans): record the triple screen 1m backtests"`; Push.

**Success criteria:** the report is on `origin/develop`.

**Verify:** `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md | tail -1` prints `Result: PASS`.

## Rollback

None needed. The four runs stay in `backtest_runs`; the owner can delete them in the UI.

## Report

`reports/phase-02-triple-screen-1m-backtests.md`: entry-gate outputs; every `run=` line (submit, any started line over 1800 s, final); four `free_after_run=` lines; any `cost_ask=` answer; the table; two `verdict:` lines; `Result: PASS`.

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
title: "Paper: one subscription per passing set"
status: pending
priority: P2
effort: "0.5h"
dependencies: [2]
---

# Phase 06: Paper: one subscription per passing set

## Goal

Every set whose verdict is `pass` has exactly one running paper subscription on `XAUUSD:EXNESS` with the strategy, intervals and parameters of its `paper_run`, deciding on live 1m bars. A failing set gets none. With no passing set the phase records that and ends.

## Context

- D4: only passing sets go to paper. P2: the `paper_run=<n>:<id>` of the verdict line names the backtest run to mirror.
- A backtest run document carries `strategy_code`, `intervals` and `parameters` (`src/pocketquant/core/domain/backtest/entities.py:61-79`), so the script copies them from Mongo; nothing is typed by hand.
- Create body `{symbol, intervals, parameters, broker}` (`src/pocketquant/app/routes/strategy.py:16-20`, `POST /api/v1/strategies/{code}/subscriptions`); a new subscription is stored `stopped` (`src/pocketquant/engine/strategy/strategy_command_service.py:100-114`); `POST /api/v1/subscriptions/{id}/start`. Mutations need `X-Admin-Token` (`src/pocketquant/app/middleware/admin_auth_middleware.py:16-30`); the script reads it from `get_settings().admin_token` (`src/pocketquant/core/config.py:85`) and never prints it.
- All paper subscriptions share one pooled paper broker per contract spec (`StrategyAppService._get_or_create_broker`, `strategy_app_service.py:962-975`), so per-subscription results are read later by `trades.run_id` (A5).
- Snapshot ring: `GET /api/v1/subscriptions/{id}/snapshot` (admin token, `src/pocketquant/app/routes/strategy.py:136`); warm-up fills the ring without writing, so only entries whose `bar_start` is after the start count as live.
- A6: the three original subscriptions are not touched; ORIG3 proves it.
- Recipes: plan.md KEY, SSH, PRODPY, HEADER, ADMINGET, ORIG3, FREE.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-02-triple-screen-1m-backtests.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md` prints `2`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 06 after <UTC time>
```

## Files

- Repo: this phase's report only.
- Prod writes: one subscription created and started per passing set (Task 06.2).

## Tasks

### Task 06.1 — List the passing sets

**Goal:** the report names the sets that go to paper and their backtest run ids.

**Target files and symbols:** the report of Phase 02.

**Steps:**
1. `grep -h "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md`; copy the two lines into this report.
2. For each line with ` pass `, write `paper_set=<set> run=<id>` where `<id>` is the part after the colon in `paper_run=<n>:<id>`.
3. If no line has ` pass `, write `paper_sets=none`, skip Tasks 06.2 and 06.3, and go to Task 06.4.

**Success criteria:** the number of `paper_set=` lines equals the number of passing verdicts, or `paper_sets=none` is written.

**Verify:** `uv run python -c "import re; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md',encoding='utf-8').read(); p=len(re.findall(r'^verdict: .* pass ',t,re.M)); s=len(re.findall(r'^paper_set=',t,re.M)); n=len(re.findall(r'^paper_sets=none$',t,re.M)); print('sets_ok=' + ('yes' if (p==s and p>0 and n==0) or (p==0 and s==0 and n==1) else 'no'))"` prints `sets_ok=yes`.

### Task 06.2 — Create and start one paper subscription per passing set

**Goal:** each passing set runs on paper with its backtest's settings.

**Target files and symbols:** `POST /api/v1/strategies/{code}/subscriptions`, `POST /api/v1/subscriptions/{id}/start`; prod `subscriptions`.

**Steps:**
1. KEY. Record `paper_started_at=<UTC ISO now>` once, before the first create (keep the first value on a resume).
2. For each `paper_set=` line, PRODPY `paper <run id>` with HEADER plus (it reuses an existing document on a resume):
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
code, intervals, params = run["strategy_code"], list(run["intervals"]), dict(run.get("parameters") or {})
key = ",".join(intervals)
found = db.subscriptions.find_one({"strategy_code": code, "symbol": "XAUUSD:EXNESS", "intervals_key": key})
sid = found["_id"] if found else post(f"/strategies/{code}/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": intervals, "parameters": params, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
time.sleep(30)
d = db.subscriptions.find_one({"_id": sid})
print(f"paper_sub={code} {key} id={sid} run={RUN} started_at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
print(f"state={d['desired_state']}/{d['actual_state']} broker={d['broker']} intervals_key={d['intervals_key']} params_match={d['parameters'] == params}")
```
3. Append both lines per set. Then record `paper_ready_at=<UTC ISO now>` once after the last set, and FREE `free_after_paper_start`.

**Success criteria:** every passing set has a running paper subscription whose parameters equal its backtest run's.

**Verify:** `uv run python -c "import re; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md',encoding='utf-8').read(); s=len(re.findall(r'^paper_set=',t,re.M)); ok=len(re.findall(r'^state=running/running broker=paper intervals_key=\S+ params_match=True$',t,re.M)); print(f'subs={s} ok={ok}')"` prints `subs=<k> ok=<k>` with both numbers equal.

### Task 06.3 — Snapshot ring after live 1m bars

**Goal:** each new subscription decides on live bars, not only warm-up bars.

**Target files and symbols:** `GET /api/v1/subscriptions/{id}/snapshot`.

**Steps:**
1. If now is earlier than `paper_ready_at + 5 min`, run `rm -f .cache/ssh/vps_key` and end with `NOT_YET: waiting for live 1m bars` and a resume time of `paper_ready_at + 5 min`.
2. For each `paper_sub=` id, PRODPY `ring <id> <paper_started_at>` with HEADER, ADMINGET plus:
```python
import sys
from datetime import UTC, datetime
since = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
ring = admin_get(f"/subscriptions/{sys.argv[1]}/snapshot")
live = [e for e in ring if datetime.fromisoformat(str(e["bar_start"]).replace("Z", "+00:00")).replace(tzinfo=UTC) > since]
print(f"ring={sys.argv[1]} entries={len(ring)} live_distinct_bar_start={len({e['bar_start'] for e in live})}")
```
3. Append each line. `rm -f .cache/ssh/vps_key`.

**Success criteria:** every new subscription has at least 2 distinct live `bar_start` values.

**Verify:** `uv run python -c "import re; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md',encoding='utf-8').read(); s=len(re.findall(r'^paper_sub=',t,re.M)); ok=len(re.findall(r'^ring=\S+ entries=\d+ live_distinct_bar_start=([2-9]|[1-9]\d+)$',t,re.M)); print(f'subs={s} live={ok}')"` prints `subs=<k> live=<k>` with both numbers equal.

### Task 06.4 — A6 check, report and push

**Goal:** the original subscriptions are unchanged and the paper start is in git.

**Target files and symbols:** prod `subscriptions`; `reports/phase-06-paper-start.md`.

**Steps:**
1. KEY (if not present). PRODPY `orig3`; record its line. `rm -f .cache/ssh/vps_key`.
2. End the report with `Result: PASS`; commit `docs(plans): record the paper start`; Push.

**Success criteria:** the ORIG3 line equals the Phase 01 baseline; the report is on `origin/develop`.

**Verify:** `uv run python -c "import re; a=open('plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md',encoding='utf-8').read(); b=open('plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md',encoding='utf-8').read(); x=re.search(r'^baseline_(original_subs=\S+)$',a,re.M).group(1); print('orig3_same=' + ('yes' if re.search('^' + re.escape(x) + '$',b,re.M) else 'no'))"` prints `orig3_same=yes`, and `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md | tail -1` prints `Result: PASS`.

## Rollback

[ASK] each step. For each `paper_sub=` id only: `POST /api/v1/subscriptions/<id>/stop`, wait until `actual_state` is `stopped`, then `DELETE /api/v1/subscriptions/<id>` (from a PRODPY script with the token header). Never touch the three original subscriptions.

## Report

`reports/phase-06-paper-start.md`: entry-gate outputs; the two verdict lines; `paper_set=` lines or `paper_sets=none`; `paper_started_at=`; per set the `paper_sub=` and `state=` lines; `paper_ready_at=`; `free_after_paper_start`; ring lines; the ORIG3 line; `Result: PASS`.

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
title: "Paper: 14 days of log check-ins and the reconciliation"
status: pending
priority: P2
effort: "14 days calendar; about 15 min per check-in, 30 min for the reconciliation"
dependencies: [6]
---

# Phase 07: Paper: 14 days of log check-ins and the reconciliation

## Goal

Each paper subscription has run for at least 14 days, and each passing set has a reconciliation record with the four A5 columns against its backtest: trades per trading day, average commission per trade, exit-reason mix, and the count of `strategy_on_bar_error` and stale-bar events.

## Context

- Window: from `paper_started_at` to `paper_ready_at + 14 days` (both in the Phase 06 report). Every subscription runs at least 14 days inside it.
- Errors and stale skips exist only in the trader log: `strategy_on_bar_error` with `strategy_id=<sub id>` (`src/pocketquant/engine/strategy/strategy_app_service.py:623,931`) and `strategy.entry_skipped` with `reason=stale` and `subscription_id=<sub id>` (`:631-649`). The trader log keeps at most 3 files of 10 MB (`deploy/compose.prod.yml:16-20`) and a container recreate drops the old log, so a check-in runs at least every 3 days, and each one proves the oldest kept log line is not later than its `since`.
- Trades: `trades` documents carry `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:39`; `src/pocketquant/core/infra/persistence/repositories/trade_repository.py:24-27`); backtest trades are `backtest_trades` with `run_id` = run id; both have `commission` and `exit_reason` (`src/pocketquant/core/domain/trading/value_objects.py:85-130`).
- Trading days: distinct UTC dates with at least one stored `XAUUSD:EXNESS` 1m bar inside the window (the same rule for backtest and paper).
- Sizing differs (the backtest starts at 10 000; the paper account is pooled), so average commission per trade is recorded, not judged. D4: no paper threshold; the verdict stays the gate's.
- Recipes: plan.md KEY, SSH, COMPOSE, PRODPY, HEADER.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-06-paper-start.md`. A resumed run of this phase may hold its own uncommitted report.
2. If the Phase 06 report holds `paper_sets=none`: write `reports/phase-07-paper-reconcile.md` with `No passing set: no paper subscription, nothing to reconcile.` and `Result: PASS`, commit `docs(plans): record that no set went to paper`, Push, and end the phase.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 07 after <UTC time>
```

## Files

- Repo: this phase's report only.
- Prod writes: none.

## Tasks

### Task 07.1 — Log check-in (repeat every session until the window ends)

**Goal:** an unbroken chain of log windows from `paper_started_at` to the window end, with error and stale counts per subscription.

**Target files and symbols:** trader container log.

**Steps:**
1. Write `window_end=<paper_ready_at + 14 days, UTC ISO>` once at the top of the report.
2. `SINCE` = the `until=` of the last `checkin=` line in this report, or `paper_started_at` for the first one. `UNTIL` = the earlier of now (UTC ISO, seconds) and `window_end`. `k` = the number of earlier `checkin=` header lines plus 1.
3. KEY. Oldest kept line: SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --timestamps --no-log-prefix trader 2>&1 | head -1 | cut -c1-19`; call the output `OLDEST`.
4. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <SINCE> --until <UNTIL> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`.
5. `uv run python -c "import sys; print('log_covered=' + ('yes' if sys.argv[1][:19] <= sys.argv[2][:19] else 'no'))" "<OLDEST>" "<SINCE>"`.
6. Append `checkin=<k> since=<SINCE> until=<UNTIL> oldest=<OLDEST> <log_covered line>`. Then for each `paper_sub=` id append `checkin=<k> sub=<id> on_bar_error=<a> stale=<b>`, with `a` = `grep "strategy_on_bar_error" .cache/trader.log | grep -c "<id>"` and `b` = `grep "strategy.entry_skipped" .cache/trader.log | grep "reason=stale" | grep -c "<id>"`.
7. `rm -f .cache/ssh/vps_key`. If `UNTIL` is earlier than `window_end`, commit the report (`docs(plans): record a paper log check-in`), Push, and end with `NOT_YET: paper window open until <window_end>` and `Resume: ... --from 07 after <the earlier of UNTIL + 3 days and window_end>`.

**Success criteria:** every check-in header shows `log_covered=yes`; the chain reaches `window_end`.

**Verify:** `uv run python -c "import re; t=open('plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md',encoding='utf-8').read(); h=re.findall(r'^checkin=\d+ since=(\S+) until=(\S+) oldest=\S+ log_covered=(\w+)$',t,re.M); print('last_covered=' + (h[-1][2] if h else 'none'))"` prints `last_covered=yes` after each check-in.

### Task 07.2 — Window closed and the chain unbroken

**Goal:** the counts cover the whole window with no gap.

**Target files and symbols:** this phase's report; the Phase 06 report.

**Steps:**
1. Run only when the last check-in's `until=` equals `window_end`.
2. Run the Verify command and append its output lines to the report.

**Success criteria:** the first `since` is `paper_started_at`, each `since` equals the previous `until`, the last `until` is `window_end`, and every header shows `log_covered=yes`.

**Verify:** `uv run python -c "import re; d='plans/261109-1349-1m-strategy-evidence/reports/'; t=open(d+'phase-07-paper-reconcile.md',encoding='utf-8').read(); p=open(d+'phase-06-paper-start.md',encoding='utf-8').read(); s0=re.search(r'^paper_started_at=(\S+)$',p,re.M).group(1); end=re.search(r'^window_end=(\S+)$',t,re.M).group(1); h=re.findall(r'^checkin=\d+ since=(\S+) until=(\S+) oldest=\S+ log_covered=(\w+)$',t,re.M); ok=bool(h) and h[0][0]==s0 and h[-1][1]==end and all(a[1]==b[0] for a,b in zip(h,h[1:])) and all(x[2]=='yes' for x in h); print('chain_ok=' + ('yes' if ok else 'no'))"` prints `chain_ok=yes`.

### Task 07.3 — Reconciliation per passing set

**Goal:** the four A5 columns for each passing set, paper against backtest.

**Target files and symbols:** prod `trades`, `backtest_trades`, `backtest_runs`, `bars`.

**Steps:**
1. KEY. For each `paper_sub=<set> id=<sid> run=<rid> ...` line of the Phase 06 report, PRODPY `recon <sid> <rid> <paper_started_at> <window_end>` with HEADER plus:
```python
import json
import sys
from collections import Counter
from datetime import UTC, datetime
SUB, RUN = sys.argv[1], sys.argv[2]
P0, P1 = (datetime.fromisoformat(a.replace("Z", "+00:00")) for a in sys.argv[3:5])
B0, B1 = datetime(2025, 11, 7, tzinfo=UTC), datetime(2026, 11, 7, tzinfo=UTC)
run = db.backtest_runs.find_one({"_id": RUN}, {"strategy_code": 1, "intervals": 1})
label = f"{run['strategy_code']} {','.join(run['intervals'])}"


def days(a, b):
    out = list(db.bars.aggregate([
        {"$match": {"symbol": "XAUUSD:EXNESS", "interval": "1m", "datetime": {"$gte": a, "$lt": b}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$datetime"}}}},
        {"$count": "n"},
    ]))
    return out[0]["n"] if out else 0


def row(kind, trades, n_days):
    n = len(trades)
    comm = sum(t.get("commission") or 0.0 for t in trades) / n if n else 0.0
    mix = dict(sorted(Counter(t.get("exit_reason") or "none" for t in trades).items()))
    per_day = n / n_days if n_days else 0.0
    print(
        f"reconcile_{kind}: {label} trades={n} trading_days={n_days} trades_per_day={per_day:.3f} "
        f"avg_commission={comm:.4f} exit_mix={json.dumps(mix, separators=(',', ':'))}"
    )


fields = {"commission": 1, "exit_reason": 1}
row("backtest", list(db.backtest_trades.find({"run_id": RUN}, fields)), days(B0, B1))
row("paper", list(db.trades.find({"run_id": SUB, "exit_time": {"$gte": P0, "$lt": P1}}, fields)), days(P0, P1))
```
2. Append both lines per set. Then append `reconcile_errors: <set> sub=<sid> strategy_on_bar_error=<sum of on_bar_error over every checkin line for sid> stale=<sum of stale>` (sum with `grep "^checkin=[0-9]* sub=<sid> " <this report>` and add the numbers).
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** each passing set has a backtest line, a paper line and an errors line. The values are recorded as they are; none of them is a pass condition (D4).

**Verify:** `uv run python -c "import re; d='plans/261109-1349-1m-strategy-evidence/reports/'; t=open(d+'phase-07-paper-reconcile.md',encoding='utf-8').read(); k=len(re.findall(r'^paper_sub=',open(d+'phase-06-paper-start.md',encoding='utf-8').read(),re.M)); b=len(re.findall(r'^reconcile_backtest: .* trades_per_day=\S+ avg_commission=\S+ exit_mix=\{',t,re.M)); p=len(re.findall(r'^reconcile_paper: .* trades_per_day=\S+ avg_commission=\S+ exit_mix=\{',t,re.M)); e=len(re.findall(r'^reconcile_errors: .* strategy_on_bar_error=\d+ stale=\d+$',t,re.M)); print(f'sets={k} backtest={b} paper={p} errors={e}')"` prints four equal numbers, `sets=<k> backtest=<k> paper=<k> errors=<k>`.

### Task 07.4 — Report and push

**Goal:** the reconciliation is in git.

**Target files and symbols:** `reports/phase-07-paper-reconcile.md`.

**Steps:**
1. End the report with `Result: PASS`; commit `docs(plans): record the paper reconciliation`; Push.

**Success criteria:** the report is on `origin/develop`.

**Verify:** `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md | tail -1` prints `Result: PASS`.

## Rollback

Nothing to roll back: the phase only reads prod.

## Report

`reports/phase-07-paper-reconcile.md`: `window_end=`; every check-in header and per-subscription line; the `chain_ok=` line; per set the `reconcile_backtest:`, `reconcile_paper:` and `reconcile_errors:` lines; `Result: PASS`.

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
title: "Close: verdicts in plan.md, completed, archive"
status: pending
priority: P2
effort: "0.5h"
dependencies: [7]
---

# Phase 08: Close: verdicts in plan.md, completed, archive

## Goal

`plan.md` carries one written verdict per set with the reconciliation lines of the passing sets, the plan is `status: completed`, and the folder is in `plans/archive/`.

## Context

- D5: the plan ends at the reconciliation and a pass/fail verdict per set. P2: the verdict is the gate's; the reconciliation sits beside it.
- Plan state: the session hook asks to change status through the `ak plan` CLI (`ak plan update <id> --status completed` rewrites the plan.md front matter). Archive precedent: commit `00272823` moved a closed plan with `git mv plans/<dir> plans/archive/<dir>`.
- A6: ORIG3 must still equal the Phase 01 baseline. The new paper subscriptions keep running (plan.md Unresolved 4).
- Recipes: plan.md KEY, PRODPY, HEADER, ORIG3, Push.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-07-paper-reconcile.md`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 08 after <UTC time>
```

## Files

- Modify: `plans/261109-1349-1m-strategy-evidence/plan.md`; this phase's report.
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.
- Prod writes: none.

## Tasks

### Task 08.1 — A6 final check

**Goal:** the three original subscriptions were never touched.

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. PRODPY `orig3`; record its line in the report. `rm -f .cache/ssh/vps_key`.

**Success criteria:** the line equals the Phase 01 baseline.

**Verify:** `uv run python -c "import re; a=open('plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md',encoding='utf-8').read(); b=open('plans/261109-1349-1m-strategy-evidence/reports/phase-08-close-and-archive.md',encoding='utf-8').read(); x=re.search(r'^baseline_(original_subs=\S+)$',a,re.M).group(1); print('orig3_same=' + ('yes' if re.search('^' + re.escape(x) + '$',b,re.M) else 'no'))"` prints `orig3_same=yes`.

### Task 08.2 — Write the verdicts into plan.md

**Goal:** the plan states the result in one place.

**Target files and symbols:** `plan.md`, new section `## Verdicts` before `## Failure Protocol (copied verbatim into every phase file)`.

**Steps:**
1. Copy the two `verdict:` lines from the Phase 02 report unchanged, one per line.
2. Under them, copy every `reconcile_backtest:`, `reconcile_paper:` and `reconcile_errors:` line from the Phase 07 report unchanged, and every `paper_sub=` line from the Phase 06 report; with no passing set write `No set passed the gate; no paper subscription was started.`
3. Add one sentence: `The verdict is the backtest gate (net profit_factor >= 1.2 and total_trades >= 100 over 2025-11-07..2026-11-06); the paper lines are a record and change no verdict.`
4. Add one sentence naming the result in words, built from the verdict lines only: either `Passing sets: <list>.` or `No 1m set passed the gate at the seeded XAUUSD:EXNESS costs.`
5. Change the Phases table `Status` cells to `Completed`.

**Success criteria:** plan.md holds two verdict lines.

**Verify:** `grep -c -E "^verdict: (triple_screen 1m,5m,15m|triple_screen 1m,15m,1h) (pass|fail) " plans/261109-1349-1m-strategy-evidence/plan.md` prints `2`.

### Task 08.3 — Status completed and archive

**Goal:** the plan is closed and archived.

**Target files and symbols:** plan.md front matter; the plan folder.

**Steps:**
1. `ak plan list --json` and find the entry whose path ends with `261109-1349-1m-strategy-evidence`. If it exists, `ak plan update <its id> --status completed --no-interactive`. If the plan is not in the store, change the front matter line `status: pending` to `status: completed` in plan.md.
2. Write the phase report (Task 08.1 line, the Task 08.2 Verify output, the status command used and its output), ending with `Result: PASS`.
3. `git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`.
4. `git add -A plans/archive/261109-1349-1m-strategy-evidence && git commit -m "docs(plans): close and archive the 1m strategy evidence plan"`; Push.

**Success criteria:** the archived folder exists on `origin/develop` with `status: completed`.

**Verify:** `git fetch -q origin && test -d plans/archive/261109-1349-1m-strategy-evidence && git show origin/develop:plans/archive/261109-1349-1m-strategy-evidence/plan.md | grep -c "^status: completed$"` prints `1`.

## Rollback

`git mv plans/archive/261109-1349-1m-strategy-evidence plans/261109-1349-1m-strategy-evidence`, restore `status` with `ak plan update <id> --status in-progress` (or the front matter line), commit and Push.

## Report

`reports/phase-08-close-and-archive.md`: entry-gate outputs; the ORIG3 line; the verdict count; the status command and its output; `Result: PASS`.

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
