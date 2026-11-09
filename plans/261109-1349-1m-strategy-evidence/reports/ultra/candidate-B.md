=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry and a revived hitnrun2 with a cost filter"
description: "Backtest Triple Screen with a 1m entry screen and a revived hitnrun2 with a cost filter over 12 months of XAUUSD:EXNESS, gate each set on net profit factor and trade count, paper-reconcile only the passing sets for 14 days, and close with a written verdict per set."
status: pending
priority: P2
effort: "about 3d work + 14 days paper observation"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, hitnrun2, xauusd, exness]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry and a revived hitnrun2 with a cost filter

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m evidence by the owner's own gate. Track A backtests Triple Screen with a 1m entry screen, with no code change. Track B revives hitnrun2 on the current multi-interval contract, with a cost filter that reads the symbol's costs, releases it, and backtests it. Each set passes or fails on its 12-month backtest. Only passing sets run on paper for 14 days, and paper only reconciles. The plan ends with a written verdict per set. Live trading stays disarmed throughout.

The plan is written for a downstream executor model. Every task has Goal, Target files and symbols, Steps, Success criteria and a mechanical Verify. Every phase file ends with the same Failure Protocol block.

## Sources

- Fixed brief: `plans/261109-1349-1m-strategy-evidence/reports/evidence-packet.md`.
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`. Interview record: `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and recipes: `plans/261101-0843-stf-to-mtf-foundation/plan.md` (Conventions, Ops recipe), `phase-15-release-d2.md` (LIVECHK, release, rollback), `phase-16-backtests-and-paper-start.md` (coverage check Task 16.1, run script Task 16.2, table format Task 16.3, paper create Task 16.5) and its report `reports/phase-16-backtests-and-paper-start.md` (coverage amendment, run times 20-273 s).
- Deleted hitnrun2: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`; old tests `git show f3bb9e64^:tests/core_test/unit/domain/strategy/test_hitnrun2.py` and `git show f3bb9e64^:tests/backtest_test/engine/test_hitnrun2_backtest.py`.
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Rules: `CLAUDE.md`, `docs/code-standards.md`, `docs/deployment.md`.

## Owner decisions (2026-11-09, asked in Vietnamese, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Both tracks. Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. Track B: a dedicated 1m strategy. |
| D3 | Track B revives hitnrun2 (240-bar breakout, 480-bar SL extreme, 60-bar TP extreme, max loss 1%, min profit 2%) on the current multi-interval contract, with a cost filter that skips entries whose exit distance cannot cover the round-trip cost. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

Accepted assumptions: A1 Track A runs 4 backtests, each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`. A2 costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s. A3 hitnrun2 runs as one interval, `intervals=["1m"]`. A4 the cost filter reads the cost from `config.contract_spec`, never a hard-coded 0.15. A5 paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events; per-subscription trades are read by `trades.run_id` because the paper account is pooled. A6 the three existing Triple Screen paper subscriptions keep running and are not touched.

## Planning rules fixed here (do not re-decide in a phase)

- **Set.** A set is one strategy on one interval list: `triple_screen:1m,5m,15m`, `triple_screen:1m,15m,1h` (A1, two runs each) and `hitnrun2:1m` (two runs: default `min_profit_pct=0.02` and one lower value). Three sets, so three verdict lines. Reason: A1 and D2 name the interval lists as the sets, and the subscription unique index on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-131`) allows exactly one paper subscription per set.
- **Gate per set.** A set passes when at least one of its runs has `profit_factor >= 1.2` and `total_trades >= 100`. The deciding run is the passing run with the highest `profit_factor`, or, when none passes, the run with the highest `profit_factor`. The paper subscription of a passing set uses the deciding run's parameters, and its reconciliation compares against the deciding run. The VERDICT snippet below applies this rule mechanically.
- **Window.** Every backtest uses `2025-11-09T00:00:00` to `2026-11-08T23:59:00` UTC: the latest 12 full months before the plan date, the same for both tracks so verdicts compare. Stored 1m `XAUUSD:EXNESS` bars start 2025-10-21 (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md:72`).
- **Lower `min_profit_pct`.** The second hitnrun2 run uses `0.005`, a quarter of the default. Planner choice: the advice asks for "one lower value" without naming one. The owner may change it before Phase 05 by editing the RUNS entry 6.
- **`profit_factor` is already net of commission** (`src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:197-217`, fixed in `f37060aa`), capped at 100 when there is no loss (`:145-148`). No recomputation.
- **Cost filter.** Round-trip cost per unit of price = `(commission_per_contract or 0.0) * 2 + spread`, read from `config.contract_spec` in the strategy constructor. An entry is skipped when `min(SL distance, TP distance) < min_cost_multiple * round_trip_cost`, with `min_cost_multiple` default `3.0`. Distances are signed, so a stop on the wrong side of the entry is skipped too (see Phase 03 Context).
- **Paper reconciliation is a record, not a gate (D4).** The final verdict of a set is its backtest verdict. The reconciliation is written beside it.

## Data flows

- **Track A (Phases 01-02).** Prod `bars` (1m, 5m, 15m, 1h) and the `symbols` document of `XAUUSD:EXNESS` feed `POST /api/v1/backtest/run` (`src/pocketquant/app/routes/backtest.py:48-60`). `BacktestExecutionService.run` reads the symbol spec (`src/pocketquant/engine/backtest/backtest_execution_service.py:101-102`), sets the run spread from it when the body sends none (`:43`) and passes it to the strategy and the broker (`:111-130`). The run writes `backtest_runs`, `backtest_orders`, `backtest_trades`. BTRUN prints one result line per run into the phase report; VERDICT turns those lines into one `verdict:` line per set.
- **Track B code (Phase 03).** `StrategyConfig.contract_spec` (`src/pocketquant/core/domain/strategy/value_objects.py:42`) carries the symbol spec into `HitNRun2StrategyService.__init__`, which computes the round-trip cost once. Backtest path: `backtest_execution_service.py:111-119`. Live path: `src/pocketquant/engine/live/strategy_reconcile_app_service.py:154-177` builds the config with the looked-up spec, and `src/pocketquant/engine/strategy/strategy_app_service.py:262` constructs the strategy with it.
- **Track B prod (Phases 04-05).** `develop:master` deploys the code (`docs/deployment.md` "Deploy"); the same backtest flow as Track A runs for `hitnrun2`.
- **Paper (Phase 06).** A paper subscription per passing set is created through `POST /api/v1/strategies/{code}/subscriptions` and started through `POST /api/v1/subscriptions/{id}/start` (`src/pocketquant/app/routes/strategy.py:55-63,90`). The trader's reconcile loop loads it with the symbol spec; closed paper trades land in `trades` with `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:37-39`); `strategy_on_bar_error` (`strategy_app_service.py:623`) and `strategy.entry_skipped reason=stale` (`:633-647`) land in the trader log. The reconciliation reads both and the deciding backtest run's `backtest_trades`.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one phase at a time. No two phases run in parallel, so no file is owned by two phases at once.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`, Git Bash. Every Verify is one self-contained command run from there. The shell keeps no variables between commands.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md` (R below). Each phase writes its own report and ends it with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git rev-parse HEAD` equals `git rev-parse origin/develop` after `git fetch -q origin`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) any phase-specific lines. A resumed phase may show its own task files as uncommitted and `HEAD` ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Only an explicit yes counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. Fixed [ASK] points: every `develop:master` push; starting a backtest after any run of this plan took more than 1800 s; a fix that needs a change under `src/pocketquant/engine/` so the strategy receives the symbol's `contract_spec`; any destructive prod action; any change outside the confirmed scope.
- **Search** uses `git grep` (`rg` is not installed in Git Bash).
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` prints `All checks passed!`. If only the ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the phase report; never pad or split code to satisfy it.
- **FULLSUITE <out>**: `docker ps > /dev/null 2>&1 || { "/c/Program Files/Docker/Docker/Docker Desktop.exe" & sleep 20; docker ps > /dev/null && echo docker-ok; }`; then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | sed -E 's/ - .*//' | sort -u > <out>; wc -l < <out>`. About 100 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references, no plan or phase ids); push `develop` with the Ops recipe; then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`. Commits that touch only `**/*.md` or `plans/**` trigger no CI (`.github/workflows/cicd.yml:4-10`).
- **Code** follows `CLAUDE.md`: no docstrings (WHY goes in a `#` comment above the code), short code, a flow reads in one file, no new class, flag, parameter or config key without a real caller, repositories only in core, fastapi only in app, UUIDv7 ids, log levels by frequency. No literal `0.15` anywhere.
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
    5: ("hitnrun2", ["1m"], {"min_profit_pct": 0.02}),
    6: ("hitnrun2", ["1m"], {"min_profit_pct": 0.005}),
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
- **VERDICT** (local; write to `.cache/verdict.py`, run `uv run python .cache/verdict.py <report path>`; it is the reusable gate for both tracks):
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
| 03 | [Track B: hitnrun2 with the cost filter, tests, CI](./phase-03-hitnrun2-with-cost-filter.md) | none (CI) | 02 (Track A numbers exist) |
| 04 | [Track B: release to master and post-deploy checks](./phase-04-release-hitnrun2.md) | deploy [ASK] | 03 |
| 05 | [Track B: two hitnrun2 backtests, table, verdict](./phase-05-track-b-backtests-and-verdict.md) | 2 backtest runs | 04 |
| 06 | [Paper for passing sets: start, 14 days, reconciliation](./phase-06-paper-reconciliation.md) | subscription creates | 02, 05 |
| 07 | [Final verdicts, close and archive](./phase-07-verdicts-close-archive.md) | none | 06 |

Track A runs first and needs no code. Track B is not optional (D2); its code starts only after Track A has verdict lines. Phase 06 starts paper only for sets whose verdict is `pass`; with no passing set it records `paper_sets=0` and the plan closes on the backtest verdicts.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run has a table row with `profit_factor` and `total_trades`; one verdict line per set | `grep -c -E "^\| [1-4] \| " R/phase-02-*.md` prints `4`; `grep -c -E "^\| [56] \| " R/phase-05-*.md` prints `2`; `grep -c "^verdict: " R/phase-02-*.md R/phase-05-*.md` totals `3` |
| AC2 | Every run finished | six `run=<n> id=... status=finished` lines across the Phase 02 and 05 reports |
| AC3 | hitnrun2 on master with `intervals=["1m"]` and a `min_cost_multiple` filter reading `config.contract_spec`; unit and backtest-path tests pass; CI green | Phase 03 Verify lines; Phase 04 `completed success <sha>` master run; prod `strategies=hitnrun2,triple_screen` |
| AC4 | The filter skips an entry whose nearer exit is under `min_cost_multiple` round-trip costs and takes it otherwise; no literal `0.15` | Phase 03 `test_the_nearer_exit_must_cover_the_cost_multiple` (3 cases); `git grep -n "0\.15" -- src/pocketquant/core/domain/strategy | wc -l` prints `0` |
| AC5 | One paper subscription per passing set, at least 14 days, with the four A5 columns against its deciding backtest | Phase 06 `paper_sub=` lines, the 14-day check and the reconciliation table; or `paper_sets=0` |
| AC6 | The three existing paper subscriptions untouched | SUBS lines for `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d` identical before and after every prod write of Phases 04 and 06 |
| AC7 | Live stays disarmed | LIVECHK prints `trader_live=False` before and after the Phase 04 deploy |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` succeeds and its `plan.md` has `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Unit | hitnrun2 rules: validation, warm-up, long and short levels, SL cap, TP floor, direction filter, cost multiple (3 cases), wrong-side stop, one position at a time, closing fill, rejection, registry validation | `tests/core_test/unit/domain/strategy/test_hitnrun2.py` (15 tests, Phase 03) |
| Integration (real Mongo) | The symbol cost reaches the filter through the real backtest path: gold costs trade, a prohibitive cost trades nothing | `tests/backtest_test/engine/test_hitnrun2_backtest.py` (2 tests, Phase 03) |
| Existing guards | Live path passes the spec: `tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec`; closed higher-timeframe context with a 1m entry in live, warm-up and backtest: `tests/backtest_test/test_higher_timeframe_context.py` | Phases 01 and 03 |
| Suite | FULLSUITE failures are a subset of the pre-change baseline; GATES; pyright `0 errors` on touched files; CI on `develop` and `master` | Phases 03, 04 |
| End to end (prod) | Six 12-month backtests; paper subscriptions for passing sets; reconciliation | Phases 02, 05, 06 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes over 1800 s or presses the 3.9 GB VPS; the route has no cap and no cancel and shares the live Mongo pool (`app/routes/backtest.py:46-47`) | M x M | One run at a time, costliest set first, FREE after each, WINDOWCHK, [ASK] before the next run after any run over 1800 s |
| R2 | 1m bars have holes in the window | L x H | Phase 01 coverage gate (1m calendar coverage and derived-interval coverage) before any run |
| R3 | The spec does not reach the strategy in one path | L x H | Verified on HEAD for both paths (Data flows); Phase 03 re-checks with greps, the existing live test and the new backtest-path test; an engine fix is an [ASK] |
| R4 | The revived hitnrun2 skips many entries because its old SL rule can land on the wrong side of the entry | H x M | This is a result, not a defect: the gate decides. The Phase 03 test pins it; the Phase 05 report states the trade count |
| R5 | The Phase 04 deploy restarts the trader under the three running paper subscriptions | M x L | Standard rolling deploy (`deploy/vps/10-deploy.sh`); SUBS before and after; no deploy during the Phase 06 paper window (phase order) |
| R6 | Trader log rotation (10 MB x 3, `deploy/compose.prod.yml:16-20`) or a redeploy loses error lines during the 14 paper days | M x M | Daily check-ins; each one proves the retained log starts before the previous check-in, else STOP |
| R7 | Paper sizing differs from the backtest (pooled paper account vs 10 000 initial capital), so commission per trade differs | H x L | Recorded beside the numbers; the A5 columns stay as decided |
| R8 | A single 12-month window overfits | M x M | Accepted by the owner (D4); sweep, DSR and PBO are out of scope |

## Backwards compatibility and rollback

- No schema, route or contract change. hitnrun2 adds one registry key and one strategy file; Triple Screen is untouched.
- The closed MTF plan's acceptance grep "no `hitnrun2` in src" (`plans/261101-0843-stf-to-mtf-foundation/plan.md` A2) intentionally stops holding: D3 revives the strategy on the multi-interval contract, not the deleted single-timeframe paths.
- Rollback per phase is in each phase file. Backtest runs stay as records. Paper subscriptions are stopped and deleted only on an owner yes. The release rolls back by revert and re-release, or by an image pin (`docs/deployment.md` "Rollback").

## Docs impact

None expected. No doc names a strategy (`git grep -n -i -E "triple|hitnrun" -- docs README.md CLAUDE.md` prints nothing on `00272823`). Phase 03 re-runs that grep.

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions. Also not in scope (advice suggestions the owner did not confirm): archiving the two other completed plans, a second shifted 12-month window, compare-view URLs. No paper run for a failing set.

## Unresolved

1. The lower `min_profit_pct` value (`0.005`) is a planner choice; the owner may change RUNS entry 6 before Phase 05.
2. Whether the new paper subscriptions keep running after the plan closes is not decided; Phase 07 leaves them running and lists their ids.

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

=== FILE: phase-03-hitnrun2-with-cost-filter.md ===
---
phase: 3
title: "Track B: hitnrun2 with the cost filter, tests, CI"
status: pending
priority: P2
effort: "1d"
dependencies: [2]
---

# Phase 03: Track B: hitnrun2 with the cost filter, tests, CI

## Goal

`hitnrun2` is back in `STRATEGY_REGISTRY` on the multi-interval contract with `intervals=["1m"]`, its rules unchanged from the deleted code except for one parameter `min_cost_multiple` that skips an entry whose nearer exit cannot pay that many round-trip costs read from `config.contract_spec`. Unit tests and a real-Mongo backtest-path test pass; GATES, FULLSUITE and CI on `develop` are green.

## Context

- Old code: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`. Facts from it: windows are snapshotted before the current bar is appended (`:60-70`); warm-up needs `sl_lookback_bars` earlier bars (`:72-74`); one position at a time (`:76-78`); a LONG on a close below the prior `entry_lookback_bars` low with `sl = max(480-bar low, close * (1 - max_loss_pct))` and `tp = max(60-bar high, close * (1 + min_profit_pct))` (`:80-86`); the SHORT mirror (`:88-94`); an opposite-side fill clears the position (`:98-104`); any rejection clears it (`:106-107`); `entry_logic` tags `hitnrun2:breakdown` / `hitnrun2:breakup`. The `_closes` deque is written and never read: it is dropped.
- Contract changes from the old code: `DEFAULTS: ClassVar[dict]` replaces `_DEFAULTS` (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:18`); `StrategyConfig.intervals` replaces `interval`; `check_strategy_inputs` type-checks parameters against `DEFAULTS` and maps a constructor `ValueError` to `INVALID_PARAMETERS` (`src/pocketquant/core/domain/strategy/services/__init__.py:27-73`); `restore_direction` comes from the base class (`strategy_service_interface.py:35-36`); no `bar["context"]` read (the engine sets it, `src/pocketquant/engine/strategy/strategy_app_service.py:424`); `timestamp=bar["timestamp"]` (the bar dict always has it, `strategy_app_service.py:73-83`), no clock read. No `snapshot`: the engine tolerates `None` (`strategy_app_service.py:90`).
- Live warm-up replays up to 500 stored entry bars (`_WARMUP_BARS`, `strategy_app_service.py:55`), more than the 480-bar SL window, so a paper subscription decides from its first live bar.
- Fact behind D3's filter form (advice item 4): `min_profit_pct=0.02` puts the TP at least 2 % away (about 80 USD/oz at today's gold, per the advice), so a filter on TP distance alone never fires; the filter compares the nearer of the two exits.
- Fact found while planning: the old SL rule can put the stop on the wrong side of the entry. For a LONG, `close` is below every low of the 240-bar window; when it is also below every low of the 480-bar window, `max(480-bar low, close * 0.99)` is above `close`. The current paper broker exits such a LONG at the next bar's open (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:707-708`, `min(bar.open, sl)`), paying the full round trip for no move. With signed distances the filter skips it: a negative distance cannot cover a positive cost (D3). The unit test `test_a_stop_loss_beyond_the_entry_is_skipped` pins this.
- Spec reaches the strategy (advice "Unverified" item 1, verified on `00272823`): backtest `backtest_execution_service.py:111-119` (`StrategyConfig(..., contract_spec=config.contract_spec)`), live `strategy_reconcile_app_service.py:154-177` then `strategy_app_service.py:262` (`strategy_class(config)`). `ContractSpec.commission_per_contract` is `None` for `LINEAR_SPEC` (`src/pocketquant/core/domain/symbol/value_objects.py:31,64`); every seeded spec has `multiplier=1.0` (`scripts/seed_exness_symbols.py:39-61`), so per contract equals per unit of price.
- `check_strategy_inputs` builds the strategy with the default `LINEAR_SPEC` (`services/__init__.py:61-70`), so the constructor must accept a `None` commission.
- Test patterns: `tests/core_test/unit/domain/strategy/test_triple_screen.py` (helpers, `SimpleNamespace` fills); `tests/backtest_test/engine/test_triple_screen_backtest.py` (real Mongo `database` fixture `tests/backtest_test/conftest.py:39-50`, `_execution`, `_cmd_svc`); spec stand-in pattern `_FakeLookup` in `tests/backtest_test/test_backtest_dispatch_contract_spec.py:19-21`. `asyncio_mode = "auto"` (`pyproject.toml:63`).
- No look-ahead: hitnrun2 reads no higher-timeframe bar, and its windows end at the previous bar.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-02-track-a-backtests-and-verdicts.md`.
2. Track A numbers exist: `grep -c "^verdict: triple_screen:" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md` prints `2`.
3. `git grep -n -i "hitnrun" -- src tests | wc -l` prints `0` (a resumed phase may show its own files).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 03 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `tests/backtest_test/engine/test_hitnrun2_backtest.py`, `R/phase-03-hitnrun2-with-cost-filter.md`.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py`.
- Delete: none. No file under `src/pocketquant/engine/` or `src/pocketquant/app/` changes.

## Tasks

### Task 03.1 — FULLSUITE baseline before any change

**Goal:** the set of failing tests on HEAD is known, so the change is judged against it.

**Target files and symbols:** `.cache/pytest-base.txt`.

**Steps:**
1. FULLSUITE `.cache/pytest-base.txt` (plan.md Conventions). Record the tail line and the count in the report.

**Success criteria:** Docker is up; the baseline file exists.

**Verify:** `docker ps > /dev/null 2>&1 && echo docker-ok; test -f .cache/pytest-base.txt && echo base-ok` prints `docker-ok` then `base-ok`.

### Task 03.2 — The spec reaches the strategy in both paths (read-only)

**Goal:** confirm on HEAD that `StrategyConfig.contract_spec` carries the symbol spec in the backtest and live paths, before writing code that depends on it.

**Target files and symbols:** `backtest_execution_service.py` `BacktestExecutionService.run`; `strategy_reconcile_app_service.py` `_ensure_instances`; test `test_reconcile_loads_a_contract_subscription_with_its_spec`.

**Steps:**
1. `grep -c "contract_spec=config.contract_spec" src/pocketquant/engine/backtest/backtest_execution_service.py`.
2. `grep -c "contract_spec=contract_spec" src/pocketquant/engine/live/strategy_reconcile_app_service.py`.
3. `uv run python -m pytest "tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec" -q 2>&1 | tail -1`.
4. If step 1 prints less than `2`, step 2 prints `0`, or step 3 fails, the strategy does not receive the spec and fixing it needs an engine change: [ASK] (intent) "the strategy does not receive the symbol spec in <path>; fixing it changes `<file>`; allow that engine change?" `Recommended: yes`, reason: A4 requires the cost from the spec. A non-yes ends with `NOT_YET`.

**Success criteria:** both greps match and the live test passes.

**Verify:** the three commands print `2`, `1`, and a line containing `1 passed`.

### Task 03.3 — Unit tests first

**Goal:** the strategy's rules and the filter are pinned before the code exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Steps:**
1. Imports: `datetime`, `UTC`, `timedelta`, `SimpleNamespace`, `pytest`; `DomainError` from `pocketquant.core.common.exceptions`; `OrderSide` from `pocketquant.core.domain.order`; `Direction` from `pocketquant.core.domain.strategy.enums`; `check_strategy_inputs` from `pocketquant.core.domain.strategy.services`; `HitNRun2StrategyService` from `pocketquant.core.domain.strategy.services.hitnrun2_strategy_service`; `StrategyConfig` from `pocketquant.core.domain.strategy.value_objects`; `LINEAR_SPEC`, `ContractSpec` from `pocketquant.core.domain.symbol`.
2. Module constants and helpers (no docstrings; one `#` comment above `_primed` saying why bar 10 carries the extremes):
   - `_T0 = datetime(2026, 1, 5, tzinfo=UTC)`; `GOLD = ContractSpec(commission_per_contract=0.035, spread=0.08)`; `DEAR = ContractSpec(commission_per_contract=0.2, spread=0.1)`; `_SMALL = {"entry_lookback_bars": 5, "sl_lookback_bars": 20, "tp_lookback_bars": 3}`; `LONG_BAR = {"high": 99.5, "low": 98.5, "close": 99.0}`; `SHORT_BAR = {"high": 101.5, "low": 100.5, "close": 101.0}`; `NEXT_LONG_BAR = {"high": 98.5, "low": 97.5, "close": 98.0}`.
   - `_cfg(intervals=("1m",), spec=GOLD, **params)` returns `StrategyConfig(id="sub-1", name="hitnrun2", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters={**_SMALL, **params}, contract_spec=spec)`.
   - `_bar(i, high=100.5, low=99.5, close=100.0)` returns `{"symbol": "XAUUSD:EXNESS", "interval": "1m", "open": close, "high": high, "low": low, "close": close, "volume": 1.0, "timestamp": _T0 + timedelta(minutes=i)}`.
   - `async def _primed(spec=GOLD, wick=True, **params)`: builds the strategy from `_cfg(spec=spec, **params)`, awaits `on_start()`, feeds bars 0-19 with `_bar(i)` except bar 10, which is `_bar(10, high=150.0, low=50.0)` when `wick` is true; asserts each returns `None`; returns the strategy. Bar 10 sits inside the 20-bar SL window but outside the 5-bar entry window.
   - `_fill(side)` returns `SimpleNamespace(side=OrderSide[side])`.
3. Tests (names state the rule; numbers checked against the Task 03.4 code on 2026-11-09):
   - `test_more_than_one_interval_is_rejected`: `HitNRun2StrategyService(_cfg(intervals=("1m", "5m")))` raises `ValueError`.
   - `test_an_unknown_direction_is_rejected`: `direction="up"` raises `ValueError`.
   - `test_a_lookback_below_one_is_rejected`: `entry_lookback_bars=0` raises `ValueError`.
   - `test_no_signal_until_the_stop_loss_window_is_full`: a fresh started strategy fed `_bar(i)` for i 0-18 and `_bar(19, **LONG_BAR)` returns `None` every time.
   - `test_a_close_below_the_entry_window_low_goes_long`: `_primed()`, then `_bar(20, **LONG_BAR)` gives `Direction.LONG`, `entry_price == 99.0`, `stop_loss_price == pytest.approx(99.0 * 0.99)` (capped at `max_loss_pct`), `take_profit_price == pytest.approx(99.0 * 1.02)` (floored at `min_profit_pct`), `entry_logic == "hitnrun2:breakdown"`.
   - `test_a_close_above_the_entry_window_high_goes_short`: `_primed()`, then `_bar(20, **SHORT_BAR)` gives `Direction.SHORT`, `entry_price == 101.0`, `stop_loss_price == pytest.approx(101.0 * 1.01)`, `take_profit_price == pytest.approx(101.0 * 0.98)`, `entry_logic == "hitnrun2:breakup"`.
   - `test_direction_short_ignores_a_long_setup`: `_primed(direction="short")`, then `_bar(20, **LONG_BAR)` returns `None`.
   - `test_the_nearer_exit_must_cover_the_cost_multiple`, parametrized `("spec", "multiple", "enters")` over `(GOLD, 3.0, True)`, `(DEAR, 3.0, False)`, `(DEAR, 1.0, True)`: `_primed(spec, min_cost_multiple=multiple)`, then `(await s.on_bar_completed(_bar(20, **LONG_BAR)) is not None) is enters`. One `#` comment above it: the nearer exit is the stop at 0.99 away; gold costs 0.15 per round trip, the dear spec 0.5.
   - `test_a_stop_loss_beyond_the_entry_is_skipped`: `_primed(LINEAR_SPEC, wick=False, min_cost_multiple=0.0)`; `_bar(20, **LONG_BAR)` returns `None`; a second `_primed(LINEAR_SPEC, wick=False, min_cost_multiple=0.0)` with `_bar(20, **SHORT_BAR)` returns `None`. One `#` comment: without the bar-10 extremes the SL window extreme lies beyond the close, so the stop sits on the wrong side.
   - `test_an_open_position_blocks_the_next_entry`: `_primed()`, LONG on bar 20, `await s.on_order_filled(_fill("BUY"), 99.0)`, then `_bar(21, **NEXT_LONG_BAR)` returns `None`.
   - `test_the_closing_fill_frees_the_next_entry`: `_primed()`, LONG on bar 20, `await s.on_order_filled(_fill("SELL"), 98.0)`, then `_bar(21, **NEXT_LONG_BAR)` gives `Direction.LONG` with `stop_loss_price == pytest.approx(98.0 * 0.99)` and `take_profit_price == pytest.approx(100.5)`.
   - `test_a_rejected_entry_frees_the_next_entry`: `_primed()`, LONG on bar 20, `await s.on_order_rejected("zero position size")`, then `_bar(21, **NEXT_LONG_BAR)` gives `Direction.LONG`.
   - `test_check_strategy_inputs_takes_one_interval_only`: `check_strategy_inputs("hitnrun2", ["1m"], {"min_profit_pct": 0.005})` returns `HitNRun2StrategyService`; `check_strategy_inputs("hitnrun2", ["1m", "5m"], {})` raises `DomainError` with `error_code == "INVALID_PARAMETERS"`; `check_strategy_inputs("hitnrun2", ["1m"], {"entry_lookback_bars": 240.0})` raises `DomainError` with `error_code == "INVALID_PARAMETERS"`.
4. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1`; expected red (an import error): the module does not exist yet.

**Success criteria:** the file exists with 13 test functions (15 cases) and fails only on the missing module.

**Verify:** no verification needed (Task 03.4's Verify runs this file).

### Task 03.4 — Strategy file and registry entry

**Goal:** `HitNRun2StrategyService` implements the rules and the filter, registered as `"hitnrun2"`.

**Target files and symbols:** `hitnrun2_strategy_service.py` (`HitNRun2StrategyService`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. Write `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py` with exactly this content (ruff may reflow it; behaviour must stay):
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
        if len(config.intervals) != 1:
            raise ValueError("hitnrun2 trades exactly 1 interval")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        lookbacks = (self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars)
        if any(n < 1 for n in lookbacks):
            raise ValueError("lookback bars must be >= 1")
        spec = config.contract_spec
        # Commission on entry and exit plus one spread, in price units: every seeded spec
        # has multiplier 1.0, so one contract is one unit of price.
        self._round_trip_cost = (spec.commission_per_contract or 0.0) * 2 + spec.spread
        self._highs: deque[float] = deque(maxlen=max(lookbacks))
        self._lows: deque[float] = deque(maxlen=max(lookbacks))

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
        if len(lows) < self.sl_lookback_bars or self._open_direction is not None:
            return None
        if self.direction != "short" and close < min(lows[-self.entry_lookback_bars :]):
            sl = max(min(lows[-self.sl_lookback_bars :]), close * (1 - self.max_loss_pct))
            tp = max(max(highs[-self.tp_lookback_bars :]), close * (1 + self.min_profit_pct))
            return self._enter(bar, Direction.LONG, close, sl, tp, min(close - sl, tp - close))
        if self.direction != "long" and close > max(highs[-self.entry_lookback_bars :]):
            sl = min(max(highs[-self.sl_lookback_bars :]), close * (1 + self.max_loss_pct))
            tp = min(min(lows[-self.tp_lookback_bars :]), close * (1 - self.min_profit_pct))
            return self._enter(bar, Direction.SHORT, close, sl, tp, min(sl - close, close - tp))
        return None

    # An entry whose nearer exit cannot pay several round trips is skipped. Distances are
    # signed, so a stop on the wrong side of the entry is skipped too.
    def _enter(
        self, bar: dict, direction: Direction, close: float, sl: float, tp: float, nearer: float
    ) -> Signal | None:
        if nearer < self.min_cost_multiple * self._round_trip_cost:
            return None
        self._open_direction = direction
        return Signal(
            symbol=self.config.symbol,
            direction=direction,
            confidence=0.7,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            entry_price=close,
            stop_loss_price=sl,
            take_profit_price=tp,
            entry_logic=f"hitnrun2:{'breakdown' if direction == Direction.LONG else 'breakup'}",
        )

    # Broker SL/TP exits fill on the opposite side, so an opposite-side fill is the close.
    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        closing = OrderSide.SELL if self._open_direction == Direction.LONG else OrderSide.BUY
        if self._open_direction is not None and order.side == closing:
            self._open_direction = None

    async def on_order_rejected(self, reason: str) -> None:
        self._open_direction = None
```
2. In `services/__init__.py`: import `HitNRun2StrategyService` from `pocketquant.core.domain.strategy.services.hitnrun2_strategy_service` (sorted before the triple screen import); `STRATEGY_REGISTRY = {"hitnrun2": HitNRun2StrategyService, "triple_screen": TripleScreenStrategyService}`; `__all__ = ["STRATEGY_REGISTRY", "HitNRun2StrategyService", "TripleScreenStrategyService", "check_strategy_inputs"]`.
3. `uv run ruff format src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Success criteria:** every Task 03.3 test passes; the registry has both keys.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1; uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(sorted(STRATEGY_REGISTRY))"` prints a line containing `15 passed` with no `failed` or `error`, then `['hitnrun2', 'triple_screen']`.

### Task 03.5 — Backtest-path test over real Mongo

**Goal:** the symbol's cost reaches the filter through the real backtest path: gold costs trade, a prohibitive cost trades nothing.

**Target files and symbols:** `tests/backtest_test/engine/test_hitnrun2_backtest.py` (`test_the_symbol_cost_reaches_the_hitnrun2_filter_in_a_backtest`).

**Steps:**
1. Write the file:
```python
from __future__ import annotations

import math
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.constants import COLLECTION_BARS
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.symbol import ContractSpec
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.symbol_lookup_helper import SymbolLookupHelper
from pocketquant.engine.backtest.backtest_command_service import (
    BacktestCommandService,
    RunBacktestCommand,
)
from pocketquant.engine.backtest.backtest_execution_service import BacktestExecutionService

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_MINUTES = 2 * 24 * 60
_PARAMS = {"entry_lookback_bars": 20, "sl_lookback_bars": 100, "tp_lookback_bars": 10}
# The seeded gold costs, and a cost no exit distance in this series can cover.
GOLD = ContractSpec(commission_per_contract=0.035, spread=0.08)
PRICEY = ContractSpec(commission_per_contract=1000.0, spread=0.08)


@pytest.fixture(autouse=True)
def _reset_sim_time() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


class _SpecLookup:
    def __init__(self, spec: ContractSpec) -> None:
        self._spec = spec

    async def contract_spec(self, composite: str) -> ContractSpec:
        return self._spec


def _execution(database: Database, spec: ContractSpec) -> BacktestExecutionService:
    return BacktestExecutionService(
        bar_repository=BarRepository(database),
        backtest_repository=BacktestRepository(database),
        backtest_order_repository=BacktestOrderRepository(database),
        backtest_trade_repository=BacktestTradeRepository(database),
        calendar_factory=TradingCalendarFactory(SymbolLookupHelper(SymbolRepository(database))),
        # A stand-in lookup sets the symbol spec directly; the execution path is real.
        symbol_lookup=_SpecLookup(spec),  # type: ignore[arg-type]
    )


def _bars() -> list[Bar]:
    bars: list[Bar] = []
    prev = 100.0
    for k in range(_MINUTES):
        close = 100 + 10 * math.sin(2 * math.pi * k / 240) + 0.3 * math.sin(2 * math.pi * k / 7)
        bars.append(
            Bar(
                symbol=_SYM,
                interval=Interval.MINUTE_1,
                datetime=_T0 + timedelta(minutes=k),
                open=prev,
                high=max(prev, close) + 0.2,
                low=min(prev, close) - 0.2,
                close=close,
                volume=1.0,
                tick_count=1,
            )
        )
        prev = close
    return bars


@pytest.mark.asyncio
@pytest.mark.parametrize(("spec", "trades"), [(GOLD, True), (PRICEY, False)])
async def test_the_symbol_cost_reaches_the_hitnrun2_filter_in_a_backtest(
    database: Database, spec: ContractSpec, trades: bool
) -> None:
    coll = database.get_collection(COLLECTION_BARS)
    await coll.delete_many({"symbol": _SYM, "interval": "1m"})
    try:
        await coll.insert_many([b.to_mongo() for b in _bars()])
        run_id, config = await BacktestCommandService(
            backtest_repository=BacktestRepository(database)
        ).run(
            RunBacktestCommand(
                strategy_id="hitnrun2",
                symbol=_SYM,
                intervals=["1m"],
                start_date=_T0,
                end_date=_T0 + timedelta(minutes=_MINUTES - 1),
                slippage_bps=0,
                commission_bps=0,
                parameters=_PARAMS,
            )
        )
        await _execution(database, spec).execute_and_persist(run_id, config)

        run = await BacktestRepository(database).get(run_id)
        assert run is not None
        assert run.status == "finished"
        assert (run.metrics.total_trades >= 1) is trades
    finally:
        await coll.delete_many({"symbol": _SYM, "interval": "1m"})
```
2. Run it. If the `PRICEY` case trades or the `GOLD` case does not, the spec does not reach the filter in the backtest path: that is a failed Verify, and if kongming's fix needs a change under `src/pocketquant/engine/`, apply the Task 03.2 step 4 [ASK] before changing it.

**Success criteria:** both cases pass.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_hitnrun2_backtest.py -q 2>&1 | tail -1` contains `2 passed` and contains neither `failed` nor `error`.

### Task 03.6 — Scope, cost-literal and docs checks

**Goal:** hitnrun2 names live only in its strategy file, the registry and its tests; no literal cost; no doc is stale.

**Target files and symbols:** `src`, `web/src`, `scripts`, `docs`.

**Steps:**
1. `git grep -n -i "hitnrun" -- src web/src scripts | grep -v -E "^src/pocketquant/core/domain/strategy/services/(hitnrun2_strategy_service|__init__)\.py:" | wc -l`.
2. `git grep -n "0\.15" -- src/pocketquant/core/domain/strategy | wc -l`.
3. `git grep -n -i -E "triple|hitnrun" -- docs README.md CLAUDE.md | wc -l`.
4. `uv run pyright src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py tests/backtest_test/engine/test_hitnrun2_backtest.py 2>&1 | grep -c "^0 errors"`.

**Success criteria:** no stray names, no literal cost, no doc to update, pyright clean.

**Verify:** the four commands print `0`, `0`, `0`, `1`.

### Task 03.7 — CLOSE

**Goal:** gates hold, failures are a subset of the baseline, one commit, CI green on `develop`.

**Target files and symbols:** all files of this phase.

**Steps:**
1. GATES.
2. FULLSUITE `.cache/pytest-after.txt`.
3. `comm -23 .cache/pytest-after.txt .cache/pytest-base.txt | wc -l` must print `0`.
4. Commit `feat(strategy): revive hitnrun2 on the multi-interval contract with a cost filter` (code and tests only); push; run the CLOSE CI poll.
5. Write the report (baseline and after tail lines, the Task 03.2 outputs, test lines, check counts, commit sha, CI run id), append `Result: PASS`; `ak plan phase close pocketquant/261109-1349 3 --no-interactive`; commit `docs(plans): record the hitnrun2 revival`; push.

**Success criteria:** CI `success` on the code commit; report pushed.

**Verify:** `comm -23 .cache/pytest-after.txt .cache/pytest-base.txt | wc -l; GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 5 --json headSha,conclusion -q '.[] | select(.headSha == "'"$(git log -1 --format=%H -- src tests)"'") | .conclusion'; tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-03-hitnrun2-with-cost-filter.md` prints `0`, `success`, `Result: PASS`.

## Rollback

`git revert <code commit>` and push `develop`; nothing reached prod in this phase.

## Report

`reports/phase-03-hitnrun2-with-cost-filter.md`: entry-gate outputs; FULLSUITE baseline and after; the spec-wiring outputs; unit and backtest-path test lines; Task 03.6 counts; GATES; commit sha and CI run; then `Result: PASS`.

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
effort: "0.5d"
dependencies: [3]
---

# Phase 04: Track B: release to master and post-deploy checks

## Goal

Prod runs the hitnrun2 code after an explicit owner yes: the master pipeline succeeds, the api serves `hitnrun2` with its defaults, live trading stays off in the trader, the trader logs no reconcile failure, and the three existing paper subscriptions are as they were.

## Context

- Release path: `develop:master` is a fast-forward push; CI tests, builds, deploys with `deploy/vps/10-deploy.sh` and verifies with `deploy/vps/11-verify.sh` (`docs/deployment.md` "Branches", "Deploy", "Verify"; `.github/workflows/cicd.yml:220-275`). A deploy rolls `api`, `worker`, `trader` one at a time.
- On 2026-11-09 `origin/master..origin/develop` held only `docs(plans)` commits, so this release ships the Phase 03 code plus plan Markdown. Task 04.2 lists the commits that touch code.
- Live flag: only an approved go-live sets `EXNESS_LIVE_TRADING=true` (`docs/deployment.md` "Credentials"); LIVECHK reads it in `trader`.
- Rollback: emergency image pin `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh`; standard revert and push (`docs/deployment.md` "Rollback"). CI tags images `sha-<7 chars>`; `cleanup-tags` may prune old tags.
- Reconcile log events: `reconcile.failed`, `reconcile.load_failed` (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:73,188`).
- `GET /api/v1/backtest/strategies` lists registry keys (`src/pocketquant/app/routes/backtest.py:41-43`); `GET /api/v1/strategies/{code}` returns `parameters` = `DEFAULTS` (`src/pocketquant/engine/strategy/strategy_query_service.py:34-42`).
- Ops lines: KEY, SSH, COMPOSE, FREE, PRODPY, HEADER, SUBS, LIVECHK, TRADERLOG, Push in plan.md.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-03-hitnrun2-with-cost-filter.md`.
2. `git fetch -q origin && git log --oneline origin/master..origin/develop -- src | wc -l` prints a number `>= 1`.
3. `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(sorted(STRATEGY_REGISTRY))"` prints `['hitnrun2', 'triple_screen']`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 04 after <UTC time>
```

## Files

- Create: `R/phase-04-release-hitnrun2.md`.
- Prod writes: the release deploy only.

## Tasks

### Task 04.1 — Pre-release state

**Goal:** the rollback image, the memory baseline, the subscription baseline and the live flag are recorded.

**Target files and symbols:** last master CI run; VPS memory; prod `subscriptions`; trader settings.

**Steps:**
1. `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,conclusion -q '.[0] | "\(.conclusion) \(.headSha[0:7])"'`; record `prev_image=sha-<7 chars>` (the image the last master deploy built).
2. KEY. FREE; record `free_before=<line>`.
3. PRODPY with HEADER plus SUBS; record every line under `subs_before`.
4. LIVECHK; record the line.

**Success criteria:** `prev_image=` from a successful run; three `sub triple_screen` lines for `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d`; `trader_live=False`.

**Verify:** step 1 prints `success <7 chars>`; the SUBS output has exactly 3 lines starting `sub triple_screen ` and no other `sub ` line; LIVECHK prints exactly `trader_live=False`.

### Task 04.2 — [ASK] release

**Goal:** the owner approves the push to master.

**Target files and symbols:** none.

**Steps:**
1. Collect `git log --oneline origin/master..origin/develop -- src tests` and the count of all commits `git log --oneline origin/master..origin/develop | wc -l`.
2. Ask in Vietnamese (intent): "Release hitnrun2 to prod? It ships one new strategy file, one registry entry and its tests (`<code commits>`), plus `<n>` commits in total including plan docs. No schema, route or Triple Screen change. Live trading stays off in the trader (`trader_live=False`). The deploy restarts api, worker and trader one at a time; the three paper subscriptions resume. Rollback: pin `<prev_image>` or revert and re-release." Lead with `Recommended: yes`, reason: tests and CI are green and nothing live changes.
3. Only an explicit yes continues; record `release_ask=<reply>`.

**Success criteria:** the report holds the owner's yes.

**Verify:** no verification needed (Task 04.3 runs only after the recorded yes).

### Task 04.3 — Release push and master run

**Goal:** `master` equals `develop` and the master pipeline succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. LIVECHK again; it must print `trader_live=False`.
2. Record `released_at=<UTC ISO now>`.
3. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released`.
4. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Record the run id and `released=yes`.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/master`.

### Task 04.4 — Post-deploy checks

**Goal:** the new code serves hitnrun2, live stays off, no reconcile failure, the paper subscriptions are as before.

**Target files and symbols:** containers; api routes; trader log; prod `subscriptions`.

**Steps:**
1. Wait until 3 minutes after the master run completed (the trader's health start period is 180 s, `deploy/compose.prod.yml` trader `start_period`).
2. SSH `docker ps --format "{{.Names}} {{.Status}}"`; record the lines for `api`, `worker`, `trader` and `web`.
3. PRODPY with HEADER plus SUBS plus:
```python
import urllib.request
codes = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies"))
print("strategies=" + ",".join(sorted(codes)))
p = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/strategies/hitnrun2")).get("parameters") or {}
print(f"params={len(p)} min_cost_multiple={p.get('min_cost_multiple')} min_profit_pct={p.get('min_profit_pct')}")
```
4. LIVECHK.
5. TRADERLOG `<released_at>`; then `grep -c "reconcile.failed" .cache/trader.log; grep -c "reconcile.load_failed" .cache/trader.log`.
6. FREE; record `free_after=<line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** containers healthy; `strategies=hitnrun2,triple_screen`; `params=7 min_cost_multiple=3.0 min_profit_pct=0.02`; SUBS lines equal `subs_before`; `trader_live=False`; both log counts `0`.

**Verify:** in step 2 every `api`, `worker`, `trader` and `web` line contains `(healthy)`; the PRODPY output contains `strategies=hitnrun2,triple_screen` and `params=7 min_cost_multiple=3.0 min_profit_pct=0.02`, and its `sub ` lines are identical to `subs_before`; LIVECHK prints `trader_live=False`; the two `grep -c` commands print `0` then `0`.

### Task 04.5 — Report and phase close

**Goal:** the release is recorded and closed.

**Target files and symbols:** the phase report; plan store.

**Steps:**
1. Write the report; append `Result: PASS`.
2. `ak plan phase close pocketquant/261109-1349 4 --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the hitnrun2 release`; push `develop` only.

**Success criteria:** report pushed; key gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md; test ! -e .cache/ssh/vps_key && echo key-gone; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS`, `key-gone`, `pushed`.

## Rollback

Each step is an [ASK]. Emergency: KEY, then SSH `cd /opt/pocketquant && IMAGE_TAG=<prev_image> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh` (`docs/deployment.md` "Rollback"); record FREE after it. Standard: `git revert <code commit>`, push `develop`, then the same release [ASK] and push. No data migrates, so nothing else to undo. A later roll-forward starts again at Task 04.1.

## Report

`reports/phase-04-release-hitnrun2.md`: entry-gate outputs; `prev_image=`; `free_before`/`free_after`; `subs_before` and the post-deploy SUBS lines; every LIVECHK line; `release_ask=`; `released_at=`, `released=yes`, the master run id and sha; container lines; route output; log counts; then `Result: PASS`.

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

=== FILE: phase-05-track-b-backtests-and-verdict.md ===
---
phase: 5
title: "Track B: two hitnrun2 backtests, table, verdict"
status: pending
priority: P2
effort: "0.25d (about 1 h of runs)"
dependencies: [4]
---

# Phase 05: Track B: two hitnrun2 backtests, table, verdict

## Goal

Two finished 12-month hitnrun2 runs on `XAUUSD:EXNESS` with `intervals=["1m"]` (A3), one with the default `min_profit_pct=0.02` and one with `0.005`, both with the default `min_cost_multiple=3.0`, recorded in the table format of Phase 02, with one `verdict:` line for the set `hitnrun2:1m`.

## Context

- Runs 5 and 6 of RUNSDEF (plan.md Ops recipe); window, gate and the lower value: plan.md "Planning rules". Costs from the symbol spec, nothing sent (A2, A4).
- The 1800 s rule spans phases: before run 5, the previous run is run 4 in `R/phase-02-track-a-backtests-and-verdicts.md`.
- hitnrun2 reads one interval, so it needs no context preload and no top-interval history; its first 480 bars in the window are warm-up (Phase 03 Context).
- Ops lines: KEY, PRODPY, HEADER, FREE, WINDOWCHK, RUNSDEF, BTRUN, VERDICT in plan.md.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-04-release-hitnrun2.md`.
2. `grep -c "^released=yes$" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `1`.

On a miss (here or any `NOT_YET` below), run `rm -f .cache/ssh/vps_key`, edit nothing else and end with exactly:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 05 after <UTC time>
```

## Files

- Create: `R/phase-05-track-b-backtests-and-verdict.md` with the headings `## Runs`, `## Table`, `## Verdicts`, `## Notes`, in that order.
- Prod writes: two `backtest_runs` with their orders and trades.

## Tasks

### Task 05.1 — Prod serves hitnrun2

**Goal:** the api that runs backtests knows `hitnrun2`.

**Target files and symbols:** `GET /api/v1/backtest/strategies`.

**Steps:**
1. KEY. PRODPY with HEADER plus `import urllib.request` / `print("strategies=" + ",".join(sorted(json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies")))))`.

**Success criteria:** both strategies listed.

**Verify:** the output is exactly `strategies=hitnrun2,triple_screen`.

### Task 05.2 — Two backtests, one at a time

**Goal:** runs 5 and 6 finished, each with a `free_after_run=` line.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`; `.cache/f.py`.

**Steps:**
1. Write `.cache/f.py` as RUNSDEF followed by BTRUN. Record `free_before_runs=<FREE output>` under `## Runs`.
2. For `n` in 5, 6, in order:
   a. Skip `n` when `## Runs` already holds `run=<n> id=... status=finished`.
   b. The previous run is run 4 (from the Phase 02 report) for `n=5`, run 5 for `n=6`. If its line shows `elapsed_s` above `1800` and `## Notes` holds no `cost_ask=<n> yes`: [ASK] exactly as Phase 02 Task 02.1 step 2b; record `cost_ask=<n> <reply>`; a non-yes ends with `NOT_YET`.
   c. WINDOWCHK; on `window=blocked` end with `NOT_YET: backtest window` and `Resume ... after <the window time + 46 min>`.
   d. When `## Runs` holds only `run=<n> id=<id> submitted`, PRODPY `<n> <id>`; else PRODPY `<n>`. Append every printed line under `## Runs`.
   e. FREE; append `free_after_run=<n> <output>`.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two `status=finished` lines and two `free_after_run=` lines.

**Verify:** `grep -c -E "^run=[56] id=\S+ set=hitnrun2:1m params=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md; grep -c -E "^free_after_run=[56] " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md` prints `2` then `2`.

### Task 05.3 — Table and verdict

**Goal:** the two runs in the Phase 02 table format and one verdict line for `hitnrun2:1m` under the table.

**Target files and symbols:** `## Table`, `## Verdicts`; `.cache/verdict.py`.

**Steps:**
1. Under `## Table` write the Phase 02 Task 02.2 header and one row per run (`| 5 | hitnrun2 | 1m | min_profit_pct=0.02 | ...`), filled the same way.
2. Write `.cache/verdict.py` as the VERDICT block if it is missing; run `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md`; paste its one line under `## Verdicts`.

**Success criteria:** two rows and one verdict line.

**Verify:** `grep -c -E "^\| [56] \| hitnrun2 \| " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md; grep -c -E "^verdict: hitnrun2:1m (pass|fail) run=[56] profit_factor=[0-9.]+ total_trades=[0-9]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md` prints `2` then `1`.

### Task 05.4 — Report and phase close

**Goal:** the Track B numbers are on `origin/develop`.

**Target files and symbols:** the phase report; plan store.

**Steps:**
1. Append `Result: PASS`.
2. `ak plan phase close pocketquant/261109-1349 5 --no-interactive`.
3. `git add plans/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the hitnrun2 backtests`; push.

**Success criteria:** report pushed; key gone.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md; test ! -e .cache/ssh/vps_key && echo key-gone; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS`, `key-gone`, `pushed`.

## Rollback

The runs are records and stay; the owner can delete them in the UI.

## Report

`reports/phase-05-track-b-backtests-and-verdict.md`: entry-gate outputs; the strategies line; `## Runs`, `## Table`, `## Verdicts`, `## Notes`; then `Result: PASS`.

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
dependencies: [2, 5]
---

# Phase 06: Paper for passing sets: start, 14 days, reconciliation

## Goal

Every set whose verdict is `pass` runs as one paper subscription on `XAUUSD:EXNESS` for at least 14 days with its deciding run's parameters, and a reconciliation record holds the four A5 columns for paper and for its deciding backtest. With no passing set the phase records `paper_sets=0` and creates nothing.

## Context

- Passing sets: the `verdict:` lines with `pass` in `R/phase-02-track-a-backtests-and-verdicts.md` and `R/phase-05-track-b-backtests-and-verdict.md`; `run=<n>` names the deciding run, and RUNSDEF entry `n` holds its strategy, intervals and parameters. The deciding run's backtest id is on its `run=<n> id=<id> set=...` line. Failing sets never go to paper (D4).
- One subscription per set fits the unique index on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-131`); the new `1m,...` keys do not collide with the existing `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d`.
- Create and start: `POST /api/v1/strategies/{code}/subscriptions` with `{symbol, intervals, parameters, broker}` returns `id`; a new subscription is `stopped` until `POST /api/v1/subscriptions/{id}/start` (`src/pocketquant/engine/strategy/strategy_command_service.py:77-116`; `src/pocketquant/app/routes/strategy.py:55-63,90`). Mutations need `X-Admin-Token`, read inside the container from `get_settings().admin_token`. All paper subscriptions share one pooled paper account (A5), so per-subscription results come from `trades` by `run_id` = subscription id (`src/pocketquant/engine/live/live_trade_collector.py:37-39`; index `ix_trades_run_id`, `src/pocketquant/core/infra/persistence/repositories/trade_repository.py:54`).
- A5 columns: trades per trading day; average commission per trade (`Trade.commission`, `src/pocketquant/core/domain/trading/value_objects.py:85-104`); exit-reason mix (`Trade.exit_reason`; values such as `auto_sl`, `auto_tp`, `strategy_exit`, `src/pocketquant/core/domain/brokers/events.py:16-23`); and the count of `strategy_on_bar_error` (`strategy_app_service.py:623`, key `strategy_id=<sub id>`) and stale skips (`strategy.entry_skipped` with `reason=stale`, key `subscription_id=<sub id>`, `strategy_app_service.py:633-647`; 1m bars are stale after 10 s, `:53`). Backtest trades are in `backtest_trades` with `run_id` = backtest run id (`src/pocketquant/engine/backtest/backtest_report_app_service.py:100-117`).
- Trading days: the number of distinct UTC dates with at least one stored `XAUUSD:EXNESS` 1m bar, over whole UTC days only. Paper window: from the first UTC midnight after the latest `paper_started_at` to the UTC midnight of the reconciliation day. Backtest window: the plan window. Trades count by `entry_time` inside the window.
- Commission per trade scales with position size, and paper sizes from the pooled account balance while the backtest starts at 10 000 (`RunBacktestCommand.initial_capital`, `backtest_command_service.py:24`): state that beside the numbers; do not adjust them (R7).
- Trader logs rotate at 10 MB x 3 (`deploy/compose.prod.yml:16-20`) and a redeploy replaces the container, so the error counts come from daily check-ins, each proving the retained log starts before the previous check-in (R6). No deploy is planned during this phase.
- A6: the three existing subscriptions are not touched; SUBS before and after the creates must match for them.
- Ops lines: KEY, SSH, PRODPY, HEADER, SUBS, FREE, TRADERLOG, RUNSDEF in plan.md. R = `plans/261109-1349-1m-strategy-evidence/reports`.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-05-track-b-backtests-and-verdict.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md` prints `2` then `1`.

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
1. `grep -h -E "^verdict: \S+ pass run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md`; copy each line into the report as `paper_set=<set> run=<n> backtest_id=<id from that run's result line>`.
2. Record `paper_sets=<number of lines>`.
3. If `paper_sets=0`, skip Tasks 06.2-06.5, write `No set passed the backtest gate; no paper subscription was created.` and go to Task 06.6.

**Success criteria:** `paper_sets=` equals the number of passing verdict lines.

**Verify:** `test "$(grep -h -c -E "^verdict: \S+ pass run=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests-and-verdicts.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests-and-verdict.md | awk '{s+=$1} END {print s}')" = "$(sed -n 's/^paper_sets=//p' plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md)" && echo sets-match` prints `sets-match`.

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

**Verify:** for `S` = the `paper_sets=` value, `grep -c "^reconcile=run=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md; grep -c "^events=run=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md; grep -c -E "^\| [1-6] \| \S+ \| (paper|backtest) \| " plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-reconciliation.md` prints `2S`, `S`, `2S`.

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
1. Write `R/final-verdicts.md`: a heading `# Final verdicts`; the gate sentence `A set passes when one of its runs has net profit_factor >= 1.2 and total_trades >= 100 over 2025-11-09..2026-11-08 on XAUUSD:EXNESS.`; then the three `verdict:` lines copied unchanged from the Phase 02 and 05 reports, each with ` paper=<value>` appended, where `<value>` is `reconciled sub=<paper sub id>` for a set with a `paper_sub=` line in the Phase 06 report, else `not-run`.
2. Under them, one line per paper subscription: `running_paper_sub=<id> set=<set>` (left running; owner decides).
3. If no set passed, add the sentence `No 1m set passed the gate at the seeded Exness Raw Spread gold costs.`

**Success criteria:** three verdict lines with a paper value.

**Verify:** `grep -c -E "^verdict: \S+ (pass|fail) run=[1-6] profit_factor=[0-9.]+ total_trades=[0-9]+ paper=(reconciled sub=\S+|not-run)$" plans/261109-1349-1m-strategy-evidence/reports/final-verdicts.md` prints `3`.

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
