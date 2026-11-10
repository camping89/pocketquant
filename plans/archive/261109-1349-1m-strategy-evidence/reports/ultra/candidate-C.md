=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry and a revived hitnrun2, gated backtests, paper reconciliation"
description: "Backtest Triple Screen with a 1m entry screen and a revived hitnrun2 with a cost floor on 12 months of XAUUSD:EXNESS, gate each set on net profit_factor >= 1.2 and >= 100 trades, paper-test only passing sets for 14 days, reconcile against the backtest and write a pass/fail verdict per set."
status: pending
priority: P2
effort: "about 1.5d hands-on + 6 backtest runs + 14 days paper"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, hitnrun2, xauusd, exness]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry and a revived hitnrun2

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m strategy evidence on `XAUUSD:EXNESS` with the owner's own gate. Track A backtests Triple Screen with a 1m entry screen and needs no code. Track B revives hitnrun2 on the current multi-interval contract with a cost floor, releases it and backtests it. Each set passes or fails on net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets run on paper, for 14 days, to reconcile with the backtest. The plan closes with one written verdict per set and moves to `plans/archive/`. A fail for every set is a valid, useful outcome.

The plan is written for a downstream executor model. Every phase carries tasks with Goal, Target files, Steps, Success criteria and a mechanical Verify, and ends with the same Failure Protocol block.

## Sources

- Fixed brief: `reports/evidence-packet.md` (D1-D5, A1-A6, constraints, handover contract).
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`; interview record `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and ops exemplar: `plans/261101-0843-stf-to-mtf-foundation/phase-15-release-d2.md` (Ops lines, LIVECHK), `phase-16-backtests-and-paper-start.md` (run script, coverage check, run table, 1800 s ask), `phase-14-triple-screen.md` (strategy and test shape).
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Code rules: `CLAUDE.md`, `docs/code-standards.md`. Deploy: `docs/deployment.md`.
- Deleted hitnrun2: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py` and `git show f3bb9e64^:tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

## Owner decisions (interview 2026-11-09, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Both tracks. Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. Track B: a dedicated 1m strategy. |
| D3 | Track B revives hitnrun2 (240-bar breakout, 480-bar SL extreme, 60-bar TP extreme, max loss 1%, min profit 2%) on the current multi-interval contract, with a cost filter that skips entries whose exit distance cannot cover the round-trip cost. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

## Confirmed assumptions

- A1: Track A runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`.
- A2: Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when a run exceeds 1800 s.
- A3: hitnrun2 runs as one interval, `intervals=["1m"]`.
- A4: The cost filter reads the cost from `config.contract_spec`, never a hard-coded 0.15.
- A5: Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id`, because the paper account is pooled.
- A6: The three existing Triple Screen paper subscriptions keep running and are not touched.

## Planning verdicts (fixed here; do not re-decide in a phase)

- **P1 Window.** Every run uses one fixed window: `start_date=2025-11-07T00:00:00`, `end_date=2026-11-06T23:59:00` (12 months; stored 1m history starts 2025-10-21, `phase-16-backtests-and-paper-start.md` report line `first_1m=2025-10-21`). Track A and Track B are directly comparable.
- **P2 Set and verdict.** A set is a strategy plus its interval list: `triple_screen 1m,5m,15m` (runs 1, 2), `triple_screen 1m,15m,1h` (runs 3, 4), `hitnrun2 1m` (runs 5, 6). A set passes when at least one of its runs meets the gate. Its paper subscription uses the passing run with the highest `profit_factor` (ties: more trades). Reason: the unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)` allows one subscription per set (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-132`). The verdict is the gate's. The paper reconciliation is recorded beside it and changes no verdict (D4: no paper threshold).
- **P3 hitnrun2 runs.** Run 5 uses the defaults (`min_profit_pct=0.02`). Run 6 uses `min_profit_pct=0.002` (0.2 % of price, about 8 USD/oz near 4000 USD gold) as the "one lower value" from the advice. Every other parameter stays at its default, `min_cost_multiple=3.0` included.
- **P4 Cost floor.** `floor = min_cost_multiple * (commission_per_contract * 2 / multiplier + spread)`, all from `config.contract_spec`; a `None` commission counts as 0. For the seeded gold spec (`multiplier=1.0`, `scripts/seed_exness_symbols.py:46-47`) this is the advice formula `commission_per_contract * 2 + spread` = 0.15. The division turns a per-contract fee into price units (`ContractSpec.multiplier` = currency per 1.0 of price per contract, `src/pocketquant/core/domain/symbol/value_objects.py:24-25`). An entry is skipped when the nearer of the TP and SL distances is below the floor.
- **P5 Signed distances.** Distances run in the trade's favour (long: `tp - close`, `close - sl`). Fact from the old code: when the close also breaks the 480-bar extreme, `sl = max(480-bar low, close * 0.99)` lies above a long's entry (old test `test_long_entry_on_breakdown_below_prev_window_low`: entry 99.0, all prior lows 99.5, so SL 99.5). Such an entry has a negative SL distance, cannot cover any cost, and the floor skips it. Inference (unverified): part of the old 84.6 % win rate may come from such stops. The Track B backtest shows the effect.
- **P6 hitnrun2 keeps the old entry sides.** Fact from the old code and tests: it goes LONG when the close breaks below the 240-bar low and SHORT when it breaks above the 240-bar high (a fade). The revival keeps this.
- **P7 Interval.** hitnrun2 accepts exactly `intervals == ["1m"]` (A3); its lookbacks count 1m bars. Any other list is a 422 through `check_strategy_inputs`.
- **P8 Run order.** Run 1 (`1m,5m,15m`, market, sl_tp) goes first: it has the most entry signals, as the 5m set did in Phase 16 (8516 trades, 234 s).

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions; a second shifted window; archiving other plans; compare-view URLs.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one fresh worker per phase. File order is execution order. All phases are sequential; only Phase 03 edits repo code.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`. Every Verify is one self-contained command run from there. The shell keeps no variables between commands. Times are UTC.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md`, where `<slug>` is the phase file's slug. Each phase ends its report with `Result: PASS` when every task passed, then commits the report (`docs(plans): record <what the phase did>`) and pushes `develop` with the Push recipe. `plans/**` is in the CI `paths-ignore` (`.github/workflows/cicd.yml:5-10`), so report commits run no CI.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) after `git fetch -q origin`, `git rev-parse HEAD` equals `git rev-parse origin/develop`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) the phase-specific lines. A resumed phase may show its own uncommitted task files and `HEAD` ahead of `origin/develop` by its own commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts. "No" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Record the answer in English in the report.
- **Stop-and-ask points:** every `develop:master` push (Phase 04); any backtest run whose age or elapsed time passes 1800 s (Phases 02, 05); `StrategyConfig.contract_spec` not reaching the strategy in the backtest or trader path when fixing it needs an engine change (Phase 03); re-submitting a failed run; any destructive prod action; any change outside the confirmed scope.
- **Search** uses `git grep` (`rg` is not installed in Git Bash).
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` exits 0; `uv run pyright <touched .py files>` prints `0 errors`. If only the metric ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the report; never pad or split code to pass it.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the count prints `0` (the excluded modules are the known local timezone failures). Record the tail line. About 100 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references); Push; then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`.
- **No plan ids**, phase numbers, decision codes or finding codes in code, comments, test names, log events or commit messages.
- **Code** follows `CLAUDE.md`: no docstrings (a WHY goes in a `#` comment), a flow reads in one file, at most two hops to I/O, no new class/flag/param/helper without a real caller today, UUIDv7 ids, repositories only in `core.infra.persistence.repositories`, fastapi only in app, log level by frequency.
- **Prod** is read-only except the planned backtest runs (Phases 02, 05), the release (Phase 04) and the paper subscription creates and starts (Phase 06). Live stays disarmed. Secrets never go on a command line, into a report or into the repo.

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
    5: ("hitnrun2", ["1m"], {}),
    6: ("hitnrun2", ["1m"], {"min_profit_pct": 0.002}),
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

- **VERDICT**: the local script `.cache/verdict.py`, run as `uv run python .cache/verdict.py "<set>" <report files...>`. It is the one gate implementation for both tracks:

```python
import re
import sys

SETS = {
    "triple_screen 1m,5m,15m": (1, 2),
    "triple_screen 1m,15m,1h": (3, 4),
    "hitnrun2 1m": (5, 6),
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

- **Backtest (both tracks).** BTRUN in the `api` container posts `RunBacktestCommand` to `POST /api/v1/backtest/run` (`src/pocketquant/app/routes/backtest.py:48-60`). `BacktestCommandService.run` validates through `check_strategy_inputs` and stores a `started` doc (`src/pocketquant/engine/backtest/backtest_command_service.py:52-70`). `BacktestExecutionService.run` reads the symbol's `ContractSpec` (`backtest_execution_service.py:101-102`), puts it on `StrategyConfig.contract_spec` (`:111-119`) and on the paper broker (`:124-130`), replays stored 1m bars and preloads the higher intervals once. Results land in `backtest_runs` and `backtest_trades` (`run_id` = run id). BTRUN polls `GET /api/v1/backtest/{id}`; the report line feeds VERDICT, which prints one `verdict:` line per set.
- **Cost floor (Track B).** `HitNRun2StrategyService.on_bar_completed` reads `self.config.contract_spec` on every decision; the same object comes from the symbol in both paths (backtest `:118`; trader `src/pocketquant/engine/live/strategy_reconcile_app_service.py:154-177`, wired with the real `SymbolLookupHelper` at `src/pocketquant/app/di/services.py:164-171`).
- **Paper.** The `paper_run=<n>:<id>` of a passing verdict names a backtest run. PAPER reads that run's `strategy_code`, `intervals`, `parameters` from `backtest_runs` and creates and starts one `broker=paper` subscription with exactly those. The trader's reconcile loop loads it with the symbol spec; its closed trades land in `trades` with `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:39`). Engine errors and stale skips go to the trader log (`src/pocketquant/engine/strategy/strategy_app_service.py:623,631-649`). Phase 07 counts them per subscription from the logs and reads trades by `run_id`.

## Phases

| # | Phase | Prod writes | Depends on | Status |
|---|---|---|---|---|
| 01 | [Commit the plan; A6 baseline; 1m coverage and cost spec check](./phase-01-data-coverage.md) | none | — | Pending |
| 02 | [Track A: four Triple Screen 1m backtests, table, verdicts](./phase-02-triple-screen-1m-backtests.md) | 4 backtest runs | 01 | Pending |
| 03 | [Track B: revive hitnrun2 with the cost floor; tests; CI](./phase-03-hitnrun2-revival.md) | none | 02 | Pending |
| 04 | [Track B: release to master and post-deploy checks](./phase-04-release-hitnrun2.md) | release [ASK] | 03 | Pending |
| 05 | [Track B: two hitnrun2 backtests, table, verdict](./phase-05-hitnrun2-backtests.md) | 2 backtest runs | 04 | Pending |
| 06 | [Paper: one subscription per passing set](./phase-06-paper-start.md) | subscription creates and starts | 02, 05 | Pending |
| 07 | [Paper: 14 days of log check-ins and the reconciliation](./phase-07-paper-reconcile.md) | none | 06 | Pending |
| 08 | [Close: verdicts in plan.md, completed, archive](./phase-08-close-and-archive.md) | none | 07 | Pending |

Phase 03 starts only after Phase 02 has numbers (advice: Track A first). Phase 06 needs every verdict, so Track A paper waits for Track B; this keeps one paper start and one reconciliation.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run finished and is in a table with `profit_factor` and `total_trades` | Phase 02 and 05 Verify: 4 + 2 `status=finished` lines and table rows |
| AC2 | One verdict line per set (3 sets) | `grep -c "^verdict: " plans/archive/261109-1349-1m-strategy-evidence/plan.md` prints `3` |
| AC3 | hitnrun2 on master with `intervals=["1m"]` and a `min_cost_multiple` floor reading `config.contract_spec` | Phase 03 tests; Phase 04 master CI `completed success`; prod `strategies=hitnrun2,triple_screen params=7 min_cost_multiple=3.0` |
| AC4 | A unit test proves the floor skips an entry whose nearer exit is under `min_cost_multiple` round-trip costs and takes it otherwise | Phase 03 Task 03.2 tests pass |
| AC5 | One paper subscription per passing set, at least 14 days, with the four A5 columns | Phase 07 `reconcile_backtest:`, `reconcile_paper:`, `reconcile_errors:` lines per set |
| AC6 | The three original subscriptions are untouched | ORIG3 equals the Phase 01 baseline in Phases 04, 06, 08 |
| AC7 | Live stays disarmed | LIVECHK `trader_live=False` in Phase 04 |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` and `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Unit | hitnrun2 entry rules, SL/TP formulas, cost floor (spec and multiple), signed distance, one position at a time, fill and rejection state, 1m-only check through `check_strategy_inputs` | `tests/core_test/unit/domain/strategy/test_hitnrun2.py` (new) |
| Integration | hitnrun2 through the real backtest path and Mongo: trades when costs fit; zero trades when the symbol spec makes the floor exceed every exit | `tests/backtest_test/engine/test_hitnrun2_backtest.py` (new) |
| Integration (existing) | spec reaches the backtest config and broker; reconcile loads the symbol spec | `tests/backtest_test/test_backtest_dispatch_contract_spec.py`, `tests/engine_test/test_contract_spec_wiring.py` |
| Suite | FULLSUITE, GATES, CI on `develop` and `master` | Phases 03, 04 |
| End to end | 6 prod backtests; paper subscriptions trading live 1m bars for 14 days | Phases 02, 05, 06, 07 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes over 1800 s and loads the shared Mongo pool while three paper subscriptions trade | M x M | One run at a time, WINDOW guard, FREE after each run, [ASK] once a run passes 1800 s |
| R2 | 1m or cascaded bars have holes in the window | L x H | Phase 01 coverage check stops the plan before any run |
| R3 | Signed distances skip many old hitnrun2 entries (inverted stops) | H x L | P5 is explicit, tested, and listed under Unresolved for the owner |
| R4 | Trader log rotation (`max-size 10m`, `max-file 3`, `deploy/compose.prod.yml:16-20`) or a container recreate loses error lines inside the 14 days | M x M | Check-ins at most every 3 days; each one proves the oldest kept log line is not later than its `since` |
| R5 | 1m paper entries hit the 10 s stale limit (`_STALE_AFTER_S["1m"]`, `strategy_app_service.py:53`) | M x L | Counted in the reconciliation as recorded; no fix in scope |
| R6 | Single window and best-of-two selection overstate an edge | H x M | Accepted by the owner (DSR/PBO deferred); stated in the verdict section |
| R7 | The release breaks prod | L x H | CI tests, deploy verify job, ORIG3 and LIVECHK after deploy, rollback recipe in Phase 04 |
| R8 | No set passes | H x L | A valid result: Phases 06-07 record `paper_sets=none` and the plan closes with fail verdicts |

## Rollback (per phase)

01, 02, 05, 07: no repo or prod state to undo (backtest runs stay; the owner can delete them in the UI). 03: `git revert <sha>` on `develop`, Push. 04: [ASK] then `git revert <sha> && git push` to master per `docs/deployment.md` "Rollback", or the emergency `IMAGE_TAG=sha-<prev_master>` pin. 06: [ASK] then stop and delete only the new subscriptions (never the three originals). 08: `git mv` the folder back and restore `status`.

## Backwards compatibility and docs impact

The change adds one registry entry and one strategy file. No schema, index, route, config key or migration changes; Triple Screen and the existing subscriptions are untouched; the web is strategy-agnostic (Phase 03 checks that no `hitnrun` name enters `web/src`, `app` or `engine`). Docs impact: none. `git grep -n -i "hitnrun\|triple.screen" -- docs README.md CLAUDE.md` printed nothing on 2026-11-09, so no doc names strategies, and the registry owns the list (`docs/governance/documentation-rules.md`, Line Test rule 1). The completed MTF plan's A2 grep ("no hitnrun2") is a closed record; D3 supersedes it.

## Unresolved questions

1. P5: signed distances skip every hitnrun2 entry whose stop lies past its entry price, which the old code produced. If the owner prefers the old behaviour, change only the distance formula before Phase 03.
2. P3: the lower `min_profit_pct` is 0.002, a planner value. The owner may name another before Phase 05.
3. P2: a set passes when either of its runs passes, because only one subscription per set can exist.
4. The new paper subscriptions keep running after the plan closes unless the owner says otherwise.
5. Phase 01 accepts 1m calendar coverage from 98.00 % (D16 measured 98.33 % over 2025-11-03..2026-10-31 and the owner accepted the gaps as venue closures).
6. [UNVERIFIED] A backtest with zero trades finishes with `status=finished`; the empty-list guards in `performance_calculator_domain_service.py:140-148` suggest it, and Task 03.4 proves it.

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

The plan is on `origin/develop`, the state of the three original subscriptions is recorded, and the 12-month window (P1) has full 1m and cascaded `5m`, `15m`, `1h` coverage with the seeded gold costs in place, so the Track A runs compare like with like.

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
title: "Track A: four Triple Screen 1m backtests, table, verdicts"
status: pending
priority: P2
effort: "about 2h wall time (estimate 20-25 min per run)"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen 1m backtests, table, verdicts

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

**Goal:** the Track A evidence is in git before any Track B code starts.

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

=== FILE: phase-03-hitnrun2-revival.md ===
---
phase: 3
title: "Track B: revive hitnrun2 with the cost floor; tests; CI"
status: pending
priority: P2
effort: "1d"
dependencies: [2]
---

# Phase 03: Track B: revive hitnrun2 with the cost floor; tests; CI

## Goal

hitnrun2 lives again as `HitNRun2StrategyService` on the current contract with `intervals=["1m"]`, a `min_cost_multiple` floor read from `config.contract_spec`, unit tests and a backtest-path test, registered as `"hitnrun2"`, with CI green on `develop`.

## Context

- Old code: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py` (lines 15-22 defaults, 55-96 decision, 98-107 fill and rejection). Old tests: `git show f3bb9e64^:tests/core_test/unit/domain/strategy/test_hitnrun2.py`. Old shape that no longer exists: `StrategyConfig(interval=...)`, module-level `_DEFAULTS`, `bar.get("timestamp") or datetime.now(UTC)`.
- Current contract: `IStrategyService` with `DEFAULTS: ClassVar[dict]`, `restore_direction`, `snapshot` (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:16-48`); `StrategyConfig.intervals`, `contract_spec` (`src/pocketquant/core/domain/strategy/value_objects.py:32-42`); `Signal` (`value_objects.py:10-29`). Model: `triple_screen_strategy_service.py`.
- `check_strategy_inputs` type-checks every parameter against its `DEFAULTS` value and turns a constructor `ValueError` into a 422 `INVALID_PARAMETERS` (`services/__init__.py:50-73`); it builds the class with `LINEAR_SPEC`, so the constructor must not need a spec.
- Engine facts the strategy relies on: warm-up replays up to 500 stored bars (`_WARMUP_BARS`, `strategy_app_service.py:55`), so the 480-bar window is full at start; every warm-up signal gets `on_order_rejected("warmup")` (`:321`) and then `restore_direction` from the open position (`:332`); a single-interval config skips context reads (`_refresh_context`, `:366-368`); `_decide` sets `bar["context"]` (`:424`) but this strategy never reads it, so no higher-timeframe look-ahead is possible.
- ContractSpec units: `multiplier` = currency per 1.0 of price per contract; `commission_per_contract` may be `None` (`src/pocketquant/core/domain/symbol/value_objects.py:22-33`).
- Planning verdicts P4-P7 (plan.md) fix the floor, the signed distances, the entry sides and the interval rule.
- Test shape: `tests/core_test/unit/domain/strategy/test_triple_screen.py`, `tests/backtest_test/engine/test_triple_screen_backtest.py` (real Mongo through testcontainers, `tests/backtest_test/conftest.py:13-55`; Docker must run).
- The completed MTF plan's acceptance A2 ("no hitnrun2 in src") is a closed record; owner decision D3 supersedes it.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-02-triple-screen-1m-backtests.md`.
2. `grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md` prints `2`.
3. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (start Docker Desktop per FULLSUITE and retry once).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 03 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `tests/backtest_test/engine/test_hitnrun2_backtest.py`.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py`.
- Delete: none. Prod writes: none.

## Tasks

### Task 03.1 — The symbol spec reaches the strategy in both paths

**Goal:** confirm, before writing the floor, that `StrategyConfig.contract_spec` is the symbol's spec in the backtest and the trader path.

**Target files and symbols:** `BacktestExecutionService.run` (`src/pocketquant/engine/backtest/backtest_execution_service.py:101-130`); `StrategyReconcileAppService` load (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:154-177`).

**Steps:**
1. `git grep -n "contract_spec=config.contract_spec" -- src/pocketquant/engine/backtest/backtest_execution_service.py | wc -l` (expected `2`: the `StrategyConfig` and the broker).
2. `git grep -n "contract_spec=contract_spec" -- src/pocketquant/engine/live/strategy_reconcile_app_service.py | wc -l` (expected `1`).
3. `uv run python -m pytest tests/backtest_test/test_backtest_dispatch_contract_spec.py tests/engine_test/test_contract_spec_wiring.py -q 2>&1 | tail -1`.
4. If step 1 or 2 differs from its expected count, or step 3 fails, [ASK] (intent): "The strategy does not receive the symbol's contract_spec in <path>; fixing it needs an engine change outside the confirmed scope. Allow the change?" `Recommended: no, stop the plan here`, reason: the scope excludes engine changes. A non-yes ends with `NOT_YET`.

**Success criteria:** both paths set the spec from the symbol; the existing wiring tests pass.

**Verify:** `git grep -n "contract_spec=config.contract_spec" -- src/pocketquant/engine/backtest/backtest_execution_service.py | wc -l; git grep -n "contract_spec=contract_spec" -- src/pocketquant/engine/live/strategy_reconcile_app_service.py | wc -l; uv run python -m pytest tests/backtest_test/test_backtest_dispatch_contract_spec.py tests/engine_test/test_contract_spec_wiring.py -q 2>&1 | tail -1` prints `2`, then `1`, then a line containing `passed` and neither `failed` nor `error`.

### Task 03.2 — Unit tests first

**Goal:** the rules are pinned before the class exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Steps:**
1. Helpers (no docstrings):
   - `GOLD = ContractSpec(commission_per_contract=0.035, spread=0.08)` (floor 0.45 at the default multiple 3.0).
   - `SMALL = {"entry_lookback_bars": 5, "sl_lookback_bars": 8, "tp_lookback_bars": 3, "max_loss_pct": 0.01, "min_profit_pct": 0.001}`.
   - `_cfg(spec=GOLD, intervals=("1m",), **params)` returns `StrategyConfig(id="sub-1", name="hitnrun2", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters={**SMALL, **params}, contract_spec=spec)`.
   - `_bar(i, h, lo, c)` returns `{"symbol": "XAUUSD:EXNESS", "interval": "1m", "open": c, "high": h, "low": lo, "close": c, "volume": 1.0, "timestamp": datetime(2026, 1, 5, tzinfo=UTC) + timedelta(minutes=i)}`.
   - `async def _warm(s, lows=(99.5, 98.0, 99.5, 99.5, 99.5, 99.5, 99.5, 99.5), highs=(100.5,) * 8)`: calls `await s.on_start()` then feeds bars 0-7 with close `100.0` and asserts each returns `None`.
   - `LONG = (99.6, 98.9, 99.0)` and `SHORT = (101.1, 100.4, 101.0)` as `(h, lo, c)` of bar 8; `_fill(side)` returns `SimpleNamespace(side=OrderSide[side])`.
2. Tests (names state the rule; numbers checked by hand: long entry 99.0, SL `max(98.0, 99.0 * 0.99) = 98.01`, TP `max(100.5, 99.099) = 100.5`, nearer distance 0.99):
   - `test_two_intervals_are_rejected`: `_cfg(intervals=("1m", "5m"))` raises `ValueError`.
   - `test_an_entry_interval_other_than_1m_is_rejected`: `("5m",)` raises `ValueError`.
   - `test_an_unknown_direction_is_rejected`: `direction="up"` raises `ValueError`.
   - `test_the_check_accepts_1m_and_rejects_5m`: `check_strategy_inputs("hitnrun2", ["1m"], {}) is HitNRun2StrategyService`; `check_strategy_inputs("hitnrun2", ["5m"], {})` raises `DomainError` with `error_code == "INVALID_PARAMETERS"` and `status_code == 422`.
   - `test_warming_up_sends_nothing`: during `_warm`, the last snapshot has `decision == {"action": "skip", "reason": "warming up"}`.
   - `test_a_close_below_the_entry_window_low_goes_long`: bar 8 = `LONG` gives `Direction.LONG`, `entry_price == 99.0`, `stop_loss_price == pytest.approx(98.01)` (the 1 % cap wins over the 98.0 window low), `take_profit_price == pytest.approx(100.5)`, `entry_type == "market"`, `entry_logic == "hitnrun2:enter_long"`.
   - `test_a_close_above_the_entry_window_high_goes_short`: `_warm(s, lows=(99.5,) * 8, highs=(100.5, 102.0, 100.5, 100.5, 100.5, 100.5, 100.5, 100.5))`, bar 8 = `SHORT` gives `Direction.SHORT`, `stop_loss_price == pytest.approx(102.0)`, `take_profit_price == pytest.approx(99.5)`.
   - `test_the_take_profit_is_at_least_min_profit_pct`: `min_profit_pct=0.02`, bar 8 = `LONG` gives `take_profit_price == pytest.approx(100.98)`.
   - `test_the_cost_floor_takes_an_entry_whose_nearer_exit_covers_it`: same as the long test with `GOLD` (0.99 >= 0.45); `snapshot["readings"] == [{"interval": "1m", "name": "nearer_exit_distance", "value": pytest.approx(0.99), "ok": True}]`.
   - `test_the_cost_floor_reads_the_symbol_spec`: `spec=ContractSpec(commission_per_contract=0.2)` (floor 1.2), bar 8 = `LONG` returns `None` and `decision == {"action": "skip", "reason": "exit distance under the cost floor"}`.
   - `test_the_cost_floor_scales_with_min_cost_multiple`: `GOLD`, `min_cost_multiple=10.0` (floor 1.5), bar 8 = `LONG` returns `None` with the same decision.
   - `test_an_entry_whose_stop_is_past_the_entry_price_is_skipped`: `spec=LINEAR_SPEC` (floor 0), `_warm(s, lows=(99.5,) * 8)`, bar 8 = `LONG` returns `None` (SL 99.5 above entry 99.0, distance -0.5) with reason `"exit distance under the cost floor"`.
   - `test_a_long_only_strategy_ignores_a_short_setup`: `direction="long"`, short warm-up as above, bar 8 = `SHORT` returns `None`, `decision == {"action": "hold", "reason": "no breakout"}`.
   - `test_one_position_at_a_time`: after the long signal, bar 9 `(98.95, 98.4, 98.5)` returns `None` with `decision == {"action": "hold", "reason": "position held"}`.
   - `test_an_opposite_fill_frees_the_next_entry`: after the long signal, `await s.on_order_filled(_fill("SELL"), 98.01)`; bar 9 `(98.95, 98.4, 98.5)` gives `Direction.LONG` with `stop_loss_price == pytest.approx(98.0)` (nearer 0.5 >= 0.45).
   - `test_a_same_side_fill_keeps_the_position`: after the long signal, `on_order_filled(_fill("BUY"), 99.0)`; bar 9 holds.
   - `test_a_rejected_entry_frees_the_next_entry`: after the long signal, `await s.on_order_rejected("zero position size")`; bar 9 gives `Direction.LONG`.
   - `test_a_restart_holds_no_position`: after the long signal, `_warm` again (it calls `on_start`); bar 8 = `LONG` gives `Direction.LONG`.
3. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1`; expected red (an import error), because the module does not exist yet.

**Success criteria:** the file exists and fails only because the strategy is missing.

**Verify:** no verification needed (Task 03.3's Verify runs this file).

### Task 03.3 — Strategy and registry entry

**Goal:** `HitNRun2StrategyService` implements P4-P7 and is registered as `"hitnrun2"`.

**Target files and symbols:** `hitnrun2_strategy_service.py` (`HitNRun2StrategyService`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. Create the strategy file with exactly this content:
```python
from __future__ import annotations

from collections import deque
from typing import ClassVar

from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.strategy_service_interface import (
    FilledOrder,
    IStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import Signal, StrategyConfig


class HitNRun2StrategyService(IStrategyService):
    DEFAULTS: ClassVar[dict] = {
        "entry_lookback_bars": 240,
        "sl_lookback_bars": 480,
        "tp_lookback_bars": 60,
        "max_loss_pct": 0.01,
        "min_profit_pct": 0.02,
        "direction": "both",
        "min_cost_multiple": 3.0,
    }

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        p = config.parameters or {}
        d = self.DEFAULTS
        self.entry_lookback_bars = p.get("entry_lookback_bars", d["entry_lookback_bars"])
        self.sl_lookback_bars = p.get("sl_lookback_bars", d["sl_lookback_bars"])
        self.tp_lookback_bars = p.get("tp_lookback_bars", d["tp_lookback_bars"])
        self.max_loss_pct = float(p.get("max_loss_pct", d["max_loss_pct"]))
        self.min_profit_pct = float(p.get("min_profit_pct", d["min_profit_pct"]))
        self.direction = p.get("direction", d["direction"])
        self.min_cost_multiple = float(p.get("min_cost_multiple", d["min_cost_multiple"]))
        # The lookbacks count 1m bars.
        if list(config.intervals) != ["1m"]:
            raise ValueError("hitnrun2 runs on intervals ['1m'] only")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        lookbacks = (self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars)
        if min(lookbacks) < 1:
            raise ValueError("lookbacks must be >= 1")
        if self.max_loss_pct <= 0 or self.min_profit_pct <= 0 or self.min_cost_multiple < 0:
            raise ValueError("max_loss_pct and min_profit_pct must be above 0")
        self._warm = max(lookbacks)
        self._highs: deque[float] = deque(maxlen=self._warm)
        self._lows: deque[float] = deque(maxlen=self._warm)

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # The windows end at the previous bar, so a bar never sets its own breakout level.
        highs, lows = list(self._highs), list(self._lows)
        self._highs.append(high)
        self._lows.append(low)
        spec = self.config.contract_spec
        # Commission is per contract and a contract moves `multiplier` per 1.0 of price, so
        # this is the round trip in price units: two commissions plus one spread.
        floor = self.min_cost_multiple * (
            (spec.commission_per_contract or 0.0) * 2 / spec.multiplier + spec.spread
        )
        entry: tuple[Direction, float, float] | None = None
        if len(lows) < self._warm:
            action, reason = "skip", "warming up"
        elif self._open_direction is not None:
            action, reason = "hold", "position held"
        else:
            action, reason = "hold", "no breakout"
            e = self.entry_lookback_bars
            if self.direction != "short" and close < min(lows[-e:]):
                sl = max(min(lows[-self.sl_lookback_bars :]), close * (1 - self.max_loss_pct))
                tp = max(max(highs[-self.tp_lookback_bars :]), close * (1 + self.min_profit_pct))
                entry = (Direction.LONG, sl, tp)
            elif self.direction != "long" and close > max(highs[-e:]):
                sl = min(max(highs[-self.sl_lookback_bars :]), close * (1 + self.max_loss_pct))
                tp = min(min(lows[-self.tp_lookback_bars :]), close * (1 - self.min_profit_pct))
                entry = (Direction.SHORT, sl, tp)

        nearer: float | None = None
        signal: Signal | None = None
        if entry is not None:
            direction, sl, tp = entry
            sign = 1 if direction == Direction.LONG else -1
            # Distances run in the trade's favour, so a stop past the entry price is negative
            # and skips like any exit too close to pay the round trip.
            nearer = min(sign * (tp - close), sign * (close - sl))
            if nearer < floor:
                action, reason = "skip", "exit distance under the cost floor"
            else:
                action = "enter_long" if sign == 1 else "enter_short"
                reason = "close broke the entry window"
                self._open_direction = direction
                signal = Signal(
                    symbol=self.config.symbol,
                    direction=direction,
                    confidence=0.7,
                    timestamp=bar["timestamp"],
                    subscription_id=self.id,
                    entry_price=close,
                    stop_loss_price=sl,
                    take_profit_price=tp,
                    entry_logic=f"hitnrun2:{action}",
                )
        self.snapshot = {
            "readings": [
                {
                    "interval": "1m",
                    "name": "nearer_exit_distance",
                    "value": nearer,
                    "ok": signal is not None,
                }
            ],
            "decision": {"action": action, "reason": reason},
        }
        return signal

    # The broker's SL or TP fill is the opposite side, so any opposite-side fill closes.
    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        if (self._open_direction == Direction.LONG and order.side == OrderSide.SELL) or (
            self._open_direction == Direction.SHORT and order.side == OrderSide.BUY
        ):
            self._open_direction = None

    # The only signal is a market entry, so any rejection means no position opened.
    async def on_order_rejected(self, reason: str) -> None:
        self._open_direction = None
```
2. In `services/__init__.py`: import `HitNRun2StrategyService` from `pocketquant.core.domain.strategy.services.hitnrun2_strategy_service` above the Triple Screen import; `STRATEGY_REGISTRY = {"hitnrun2": HitNRun2StrategyService, "triple_screen": TripleScreenStrategyService}`; add `"HitNRun2StrategyService"` to `__all__`.
3. `uv run ruff check --fix src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py` and `uv run ruff format src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Success criteria:** every Task 03.2 test passes; the registry lists both codes.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1; uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(sorted(STRATEGY_REGISTRY))"` prints a line containing `passed` and neither `failed` nor `error`, then `['hitnrun2', 'triple_screen']`.

### Task 03.4 — Backtest-path test over seeded Mongo

**Goal:** hitnrun2 runs end to end through `BacktestCommandService` and `BacktestExecutionService`, and the floor sees the symbol spec the backtest hands it.

**Target files and symbols:** `tests/backtest_test/engine/test_hitnrun2_backtest.py`.

**Steps:**
1. Copy the shape of `tests/backtest_test/engine/test_triple_screen_backtest.py` (autouse `_reset_sim_time`, `_cmd_svc`, `_clear_bars`, `try/finally`). Constants: `_SYM = "BTCUSDT:BINANCE"`, `_T0 = datetime(2026, 1, 1, tzinfo=UTC)`, `_PARAMS = {"entry_lookback_bars": 20, "sl_lookback_bars": 60, "tp_lookback_bars": 10, "min_profit_pct": 0.001}`.
2. `_series()` builds 2 days of 1m `Bar`s (`2880`): `a = 3.0 if (k // 30) % 2 == 0 else 1.5`; `close = 100 + a * sin(2 * pi * k / 30)`; `open` = previous close (first: `100.0`); `high = max(open, close) + 0.05`; `low = min(open, close) - 0.05`; `volume=1.0`, `tick_count=1`, `interval=Interval("1m")`, `datetime=_T0 + k minutes`. The alternating trough depth keeps a deeper low inside the 60-bar stop window, so long entries at the shallow troughs have a positive stop distance (checked by a local simulation on 2026-11-09: positive nearer distances from about 0.05 to 1.02).
3. `class _SpecLookup` with `__init__(self, spec)` and `async def contract_spec(self, composite: str) -> ContractSpec: return self.spec`. `_execution(database, spec)` builds `BacktestExecutionService(bar_repository=BarRepository(database), backtest_repository=..., backtest_order_repository=..., backtest_trade_repository=..., calendar_factory=TradingCalendarFactory(SymbolLookupHelper(SymbolRepository(database))), symbol_lookup=_SpecLookup(spec))`, with `# type: ignore[arg-type]` on `symbol_lookup` and a `#` comment above it: the run reads only `contract_spec` from the lookup (`backtest_execution_service.py:101` is its one use).
4. Two tests, each seeding the bars, running `RunBacktestCommand(strategy_id="hitnrun2", symbol=_SYM, intervals=["1m"], start_date=_T0, end_date=_T0 + timedelta(days=2), slippage_bps=0, commission_bps=0, parameters=_PARAMS)` through `_cmd_svc(database).run(...)` and `_execution(database, spec).execute_and_persist(run_id, config)`, then reading `BacktestRepository(database).get(run_id)`:
   - `test_hitnrun2_backtest_trades_when_the_exits_cover_the_costs`: `spec=LINEAR_SPEC`; asserts `status == "finished"` and `metrics.total_trades >= 1`.
   - `test_hitnrun2_backtest_skips_every_entry_when_the_symbol_costs_exceed_the_exits`: `spec=ContractSpec(commission_per_contract=1.0)` (floor 6.0, above every exit distance); asserts `status == "finished"` and `metrics.total_trades == 0`.
5. `uv run ruff check --fix` and `uv run ruff format` on the file.

**Success criteria:** both cases pass; the second proves the spec reaches the floor through the backtest path.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_hitnrun2_backtest.py -q 2>&1 | tail -1` contains `2 passed` and neither `failed` nor `error`.

### Task 03.5 — CLOSE

**Goal:** gates hold, no strategy name leaks into platform or UI code, one commit, CI green.

**Target files and symbols:** every file of this phase.

**Steps:**
1. `git grep -n -i "hitnrun" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0`.
2. `uv run python -m pytest tests/core_test/unit/domain/strategy tests/backtest_test/engine -q 2>&1 | tail -1` contains `passed` and neither `failed` nor `error`.
3. GATES with `uv run pyright src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py tests/backtest_test/engine/test_hitnrun2_backtest.py`; FULLSUITE.
4. `git add` the four files; `git commit -m "feat(strategy): revive hitnrun2 on one 1m interval with a cost floor"`; Push; poll CI per CLOSE.
5. Report: Task 03.1 outputs, the test tails, GATES and FULLSUITE lines, the commit sha, the CI run line, then `Result: PASS`. Commit it (`docs(plans): record the hitnrun2 revival`) and Push.

**Success criteria:** CI `success` on the code commit.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --workflow cicd.yml --limit 5 --json headSha,status,conclusion -q '.[] | "\(.status) \(.conclusion) \(.headSha)"' | grep -c "^completed success $(git log -1 --format=%H -- src tests)$"` prints `1`.

## Rollback

`git revert <code sha>` on `develop`, then Push. Nothing on prod changed.

## Report

`reports/phase-03-hitnrun2-revival.md`: entry-gate outputs; Task 03.1 outputs; test tails; GATES and FULLSUITE lines; commit sha; CI run id and conclusion; `Result: PASS`.

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

=== FILE: phase-04-release-hitnrun2.md ===
---
phase: 4
title: "Track B: release to master and post-deploy checks"
status: pending
priority: P2
effort: "1h"
dependencies: [3]
---

# Phase 04: Track B: release to master and post-deploy checks

## Goal

Prod runs the commit with hitnrun2: `master` equals `develop`, the master pipeline (tests, build, deploy, verify) succeeds, the api lists hitnrun2 with its seven parameters, live stays off in the trader, and the three original subscriptions are unchanged.

## Context

- A release is `develop:master`, a fast-forward (`docs/deployment.md` "Branches"); the master push runs tests, builds, deploys and runs `deploy/vps/11-verify.sh` (`.github/workflows/cicd.yml:86-89,220-223`; `docs/deployment.md` "Verify": a green run needs no extra check). Every master push is an owner [ASK].
- On 2026-11-09 `origin/master..origin/develop` held only `plans/` commits, so this release ships the hitnrun2 commit plus plan records.
- Live off: LIVECHK must print `trader_live=False` before and after.
- Public reads: `GET /api/v1/backtest/strategies` (`src/pocketquant/app/routes/backtest.py:41-43`), `GET /api/v1/strategies/{code}` returning `parameters = DEFAULTS` (`src/pocketquant/engine/strategy/strategy_query_service.py:34-42`).
- Recipes: plan.md KEY, SSH, COMPOSE, PRODPY, HEADER, ORIG3, LIVECHK, FREE, Push.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-03-hitnrun2-revival.md`.
2. `git fetch -q origin && git log --oneline origin/master..origin/develop -- src | wc -l` prints a number `>= 1`.
3. KEY, then LIVECHK prints `trader_live=False`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 04 after <UTC time>
```

## Files

- Repo: this phase's report only.
- Prod writes: the release push (Task 04.3).

## Tasks

### Task 04.1 — Pre-release state

**Goal:** the rollback tag, the memory baseline and the A6 state are recorded.

**Target files and symbols:** `origin/master`; prod `subscriptions`.

**Steps:**
1. Record `prev_master=$(git rev-parse --short=7 origin/master)` (the printed sha).
2. FREE `free_before`.
3. PRODPY `orig3`; record its line.

**Success criteria:** `prev_master=`, `free_before` and the ORIG3 line are in the report; the ORIG3 line equals the Phase 01 baseline.

**Verify:** `uv run python -c "import re; a=open('plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md',encoding='utf-8').read(); b=open('plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md',encoding='utf-8').read(); x=re.search(r'^baseline_(original_subs=\S+)$',a,re.M).group(1); print('orig3_same=' + ('yes' if re.search('^' + re.escape(x) + '$',b,re.M) else 'no'))"` prints `orig3_same=yes`.

### Task 04.2 — [ASK] release

**Goal:** the owner approves the release.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Release hitnrun2 to prod? It adds one strategy (`hitnrun2`, 1m only, cost floor from the symbol spec) and changes nothing else in the engine, schema or UI. Commits: `<git log --oneline origin/master..origin/develop | wc -l>`. Live stays off (`trader_live=False`). Rollback: revert and push, or pin `sha-<prev_master>`." Lead with `Recommended: yes`, reason: tests and CI are green and the change is one strategy file plus its registry line.
2. Only an explicit yes continues; record the reply as `release_ask=<reply>`.

**Success criteria:** the report holds the owner's yes.

**Verify:** no verification needed (Task 04.3 runs only after the recorded yes).

### Task 04.3 — Release push and master run

**Goal:** `master` equals `develop` and the master run succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. Record `released_at=<UTC ISO now>`.
2. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released` prints `released`.
3. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/master`.

### Task 04.4 — Post-deploy checks

**Goal:** prod serves hitnrun2, live is off, reconcile is clean and the original subscriptions are unchanged.

**Target files and symbols:** api routes; trader container and log; prod `subscriptions`.

**Steps:**
1. PRODPY `post` with:
```python
import json
import urllib.request
names = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies"))
p = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/strategies/hitnrun2")).get("parameters") or {}
print(f"strategies={','.join(sorted(names))} params={len(p)} min_cost_multiple={p.get('min_cost_multiple')}")
```
2. LIVECHK.
3. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <released_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`; then `grep -c "reconcile.failed" .cache/trader.log`.
4. PRODPY `orig3`; record its line.
5. FREE `free_after`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `strategies=hitnrun2,triple_screen params=7 min_cost_multiple=3.0`; `trader_live=False`; `reconcile.failed` count `0`; the ORIG3 line appears twice in this report with the same value as the baseline.

**Verify:** the PRODPY `post` output is exactly `strategies=hitnrun2,triple_screen params=7 min_cost_multiple=3.0`; LIVECHK prints `trader_live=False`; `grep -c "reconcile.failed" .cache/trader.log` prints `0`; `uv run python -c "import re; a=open('plans/261109-1349-1m-strategy-evidence/reports/phase-01-data-coverage.md',encoding='utf-8').read(); b=open('plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md',encoding='utf-8').read(); x=re.search(r'^baseline_(original_subs=\S+)$',a,re.M).group(1); o=re.findall(r'^original_subs=\S+$',b,re.M); print(f'orig3_lines={len(o)} same={sum(1 for l in o if l == x)}')"` prints `orig3_lines=2 same=2`.

### Task 04.5 — Report and push

**Goal:** the release record is in git.

**Target files and symbols:** `reports/phase-04-release-hitnrun2.md`.

**Steps:**
1. End the report with `Result: PASS`; commit `docs(plans): record the hitnrun2 release`; Push.

**Success criteria:** the report is on `origin/develop`.

**Verify:** `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md | tail -1` prints `Result: PASS`.

## Rollback

Each step is an [ASK]. Standard: `git revert <hitnrun2 sha>`, push `develop`, then push `develop:master` (the master CI redeploys). Emergency: SSH `cd /opt/pocketquant && IMAGE_TAG=sha-<prev_master> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh` (`docs/deployment.md` "Rollback"). No data migration exists, so nothing else reverts. Record `free -m` after a rollback.

## Report

`reports/phase-04-release-hitnrun2.md`: entry-gate outputs (LIVECHK); `prev_master=`; `free_before`, `free_after`; ORIG3 lines; `release_ask=`; `released_at=`; the master run id and sha; post-check outputs; `Result: PASS`.

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

=== FILE: phase-05-hitnrun2-backtests.md ===
---
phase: 5
title: "Track B: two hitnrun2 backtests, table, verdict"
status: pending
priority: P2
effort: "about 1h wall time"
dependencies: [4]
---

# Phase 05: Track B: two hitnrun2 backtests, table, verdict

## Goal

Two finished 12-month hitnrun2 backtests on the same window as Track A (P1): run 5 with the defaults and run 6 with `min_profit_pct=0.002` (P3), a table, and one `verdict:` line for the set `hitnrun2 1m` from the same VERDICT script Track A used.

## Context

- Runs 5 and 6 of BTRUN (plan.md); same cost source (A2), same WINDOW, FREE and 1800 s rules as Phase 02.
- One interval: no higher-timeframe context is read (`strategy_app_service.py:366-368`), so the run should be shorter than a Triple Screen 1m run [UNVERIFIED until run 5 ends].
- The first 480 bars of the window only warm the strategy up (8 hours of a 12-month window).
- Recipes: plan.md KEY, SSH, PRODPY, BTRUN, VERDICT, WINDOW, FREE.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-04-release-hitnrun2.md`.
2. `grep -c "^strategies=hitnrun2,triple_screen params=7 min_cost_multiple=3.0$" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 05 after <UTC time>
```

## Files

- Repo: this phase's report only. Local scratch: `.cache/bt.py`, `.cache/verdict.py`.
- Prod writes: two `backtest_runs` (Task 05.1).

## Tasks

### Task 05.1 — Two backtests, one at a time

**Goal:** runs 5 and 6 finished, each followed by a `free -m` line; any run over 1800 s has an owner yes.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`; `.cache/bt.py`.

**Steps:**
1. If `.cache/bt.py` is missing or differs from the BTRUN text in plan.md, write it from plan.md. KEY.
2. For `n` in `5, 6`, in order, follow Phase 02 Task 02.1 step 2 (a-f) exactly, with this phase's report and `n` in place; the [ASK] text names `hitnrun2 1m <parameters>`.
3. A `status=failed` line, or a started line with `age_s` above `10800`, is a failed Verify. Never re-submit without the owner's explicit yes.
4. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two finished lines and two `free_after_run=` lines.

**Verify:** `grep -c -E "^run=[5-6] id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md; grep -c "^free_after_run=" plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `2` then `2`.

### Task 05.2 — Run table and verdict line

**Goal:** the set `hitnrun2 1m` has one gate verdict computed like Track A's.

**Target files and symbols:** the phase report; `.cache/verdict.py`.

**Steps:**
1. Write the table with the Phase 02 header and one row per run (`| 5 | hitnrun2 | 1m | defaults | ...`, `| 6 | hitnrun2 | 1m | min_profit_pct=0.002 | ...`).
2. If `.cache/verdict.py` is missing or differs from the VERDICT text in plan.md, write it from plan.md.
3. Run `uv run python .cache/verdict.py "hitnrun2 1m" plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md`; append the printed line unchanged under the table.

**Success criteria:** 2 table rows and 1 verdict line.

**Verify:** `grep -c -E "^\| [5-6] \| hitnrun2 \| " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md; grep -c -E "^verdict: hitnrun2 1m (pass|fail) " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `2` then `1`.

### Task 05.3 — Report and push

**Goal:** the Track B evidence is in git.

**Target files and symbols:** `reports/phase-05-hitnrun2-backtests.md`.

**Steps:**
1. End the report with `Result: PASS`; commit `docs(plans): record the hitnrun2 backtests`; Push.

**Success criteria:** the report is on `origin/develop`.

**Verify:** `git fetch -q origin && git show origin/develop:plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md | tail -1` prints `Result: PASS`.

## Rollback

None needed. The runs stay in `backtest_runs`; the owner can delete them in the UI.

## Report

`reports/phase-05-hitnrun2-backtests.md`: entry-gate outputs; every `run=` line; two `free_after_run=` lines; any `cost_ask=` answer; the table; the verdict line; `Result: PASS`.

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
dependencies: [2, 5]
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

1. Conventions EG (1)-(3); the previous report is `reports/phase-05-hitnrun2-backtests.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `2` then `1`.

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

**Target files and symbols:** reports of Phases 02 and 05.

**Steps:**
1. `grep -h "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-triple-screen-1m-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md`; copy the three lines into this report.
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

`reports/phase-06-paper-start.md`: entry-gate outputs; the three verdict lines; `paper_set=` lines or `paper_sets=none`; `paper_started_at=`; per set the `paper_sub=` and `state=` lines; `paper_ready_at=`; `free_after_paper_start`; ring lines; the ORIG3 line; `Result: PASS`.

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
1. Copy the three `verdict:` lines from the Phase 02 and 05 reports unchanged, one per line.
2. Under them, copy every `reconcile_backtest:`, `reconcile_paper:` and `reconcile_errors:` line from the Phase 07 report unchanged, and every `paper_sub=` line from the Phase 06 report; with no passing set write `No set passed the gate; no paper subscription was started.`
3. Add one sentence: `The verdict is the backtest gate (net profit_factor >= 1.2 and total_trades >= 100 over 2025-11-07..2026-11-06); the paper lines are a record and change no verdict.`
4. Add one sentence naming the result in words, built from the verdict lines only: either `Passing sets: <list>.` or `No 1m set passed the gate at the seeded XAUUSD:EXNESS costs.`
5. Change the Phases table `Status` cells to `Completed`.

**Success criteria:** plan.md holds three verdict lines.

**Verify:** `grep -c -E "^verdict: (triple_screen 1m,5m,15m|triple_screen 1m,15m,1h|hitnrun2 1m) (pass|fail) " plans/261109-1349-1m-strategy-evidence/plan.md` prints `3`.

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
