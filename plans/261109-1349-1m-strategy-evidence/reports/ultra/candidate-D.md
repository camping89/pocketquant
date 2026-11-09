=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry and revived hitnrun2, backtest gate, paper reconciliation"
description: "Backtest Triple Screen with a 1m entry screen (no code change) and a revived hitnrun2 with a cost filter over 12 months on XAUUSD:EXNESS, gate each set on net profit_factor >= 1.2 and total_trades >= 100, paper-trade only the passing sets for 14 days to reconcile with the backtest, and close with a pass/fail verdict per set."
status: pending
priority: P2
effort: "about 1.5d code and ops + about 3h backtest wall time + 14 days paper"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, hitnrun2, exness, evidence]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry and revived hitnrun2

## Overview

The go-live plan is parked on "no profitable strategy yet". This plan produces 1m strategy evidence for `XAUUSD:EXNESS` with the owner's own gate, net of cost. Track A backtests Triple Screen with a 1m entry screen and needs no code. Track B revives the deleted hitnrun2 on the current multi-interval contract with a cost filter, releases it, and backtests it. Each set passes or fails on its 12-month backtest. Only passing sets run 14 days on paper, and the paper run only reconciles with the backtest. The plan ends with one written verdict per set. Live trading stays disarmed throughout.

The plan is written for a downstream executor model. Every phase has ordered tasks with Goal, Target files and symbols, Steps, Success criteria and a mechanical Verify, and ends with the same Failure Protocol block.

## Sources (read when a phase cites them)

- Fixed brief: `reports/evidence-packet.md` (scope, D1-D5, A1-A6, constraints, handover contract).
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`; interview record: `plans/reports/advise-261109-1309-next-plan-state.md`.
- Format and run recipes: `plans/261101-0843-stf-to-mtf-foundation/plan.md` (Conventions, Ops recipe), `phase-14-triple-screen.md`, `phase-15-release-d2.md` (KEY, HEADER, ADMINGET, LIVECHK), `phase-16-backtests-and-paper-start.md` (Task 16.1 coverage, Task 16.2 run script, Task 16.5 subscription create).
- Earlier evidence: `plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md` (`first_1m=2025-10-21`; 5m-set runs took 234 s and 273 s; the amended coverage rule).
- Deleted hitnrun2: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `git show f3bb9e64^:tests/core_test/unit/domain/strategy/test_hitnrun2.py`.
- Governance: `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`. Code rules: `CLAUDE.md`, `docs/code-standards.md`. Release: `docs/deployment.md`.

## Owner decisions (interview 2026-11-09, asked in Vietnamese, recorded in English)

| # | Decision |
|---|---|
| D1 | The plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Both tracks. Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. Track B: a dedicated 1m strategy. |
| D3 | Track B revives hitnrun2 (240-bar breakout, 480-bar SL extreme, 60-bar TP extreme, max loss 1%, min profit 2%) rewritten to the current multi-interval contract, with a cost filter that skips entries whose exit distance cannot cover the round-trip cost. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

Confirmed assumptions:

- A1: Track A runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`.
- A2: Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s.
- A3: hitnrun2 runs as one interval, `intervals=["1m"]`.
- A4: The cost filter reads the cost from the symbol spec (`config.contract_spec`), never a hard-coded 0.15.
- A5: Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id` because the paper account is pooled.
- A6: The three existing Triple Screen paper subscriptions keep running and are not touched.

## Design rules (planner, derived from the sources; do not re-decide in a phase)

- **Window.** Every backtest uses `start_date=2025-11-09T00:00:00`, `end_date=2026-11-08T23:59:00` (the latest 12 months before the plan date; stored 1m bars start 2025-10-21). Track B uses the same window so all six runs compare.
- **Set and verdict.** A set is one `(strategy, intervals)` pair: `triple_screen/1m,5m,15m`, `triple_screen/1m,15m,1h`, `hitnrun2/1m`. A set has two runs (A1 for Track A; Track B: `min_profit_pct` 0.02 and one lower value). A run passes when `status=finished`, `profit_factor >= 1.2` and `total_trades >= 100`. A set passes when at least one of its runs passes. Its paper run uses the parameters of its passing run with the highest `profit_factor`. Reason: the unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-133`) allows exactly one subscription per set, so one set can carry only one parameter setting on paper.
- **Net metrics.** `profit_factor` is already net of commission (`src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:197-217`, capped at 100). No recomputation.
- **Costs in backtests.** The run body sends no `spread`, so the run takes `contract_spec.spread` (`src/pocketquant/engine/backtest/backtest_execution_service.py:43`). The per-contract commission from the spec wins over `commission_bps` (`src/pocketquant/core/domain/trading/commission_model.py:25-28`). `slippage_bps` keeps its default 0.5, as in the earlier Phase 16 runs.
- **Spec reaches the strategy.** Read on HEAD `00272823`: the backtest builds `StrategyConfig(contract_spec=config.contract_spec)` from `SymbolLookupHelper.contract_spec` (`backtest_execution_service.py:101-118`); the trader's reconcile loop does the same (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:154-177`), wired with the helper in `src/pocketquant/app/di/services.py:171`. Phase 03 re-checks this before any code and stops for the owner if a fix would need an engine change.
- **hitnrun2 contract.** `HitNRun2StrategyService(IStrategyService)` in `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, registry key `"hitnrun2"`, `DEFAULTS` as a `ClassVar` (the type contract `check_strategy_inputs` reads), exactly one interval, no `bar["context"]` read, market entries only, `restore_direction` from the base class, `Signal` fields as Triple Screen builds them. The old decision logic is kept: long when the close breaks below the previous `entry_lookback_bars` lows, short when it breaks above the previous highs; SL and TP from the old formulas. Live warm-up replays 500 bars (`src/pocketquant/engine/strategy/strategy_app_service.py:55`), which covers the 480-bar SL window.
- **Cost filter.** `round_trip = commission_per_contract * 2 / multiplier + spread`, read from `config.contract_spec` (`None` commission counts as 0). For seeded gold (`multiplier=1.0`, `scripts/seed_exness_symbols.py:40-48`) this is 0.15. An entry is skipped when the nearer of the TP and SL distances is below `min_cost_multiple * round_trip`. Fact from the old code: TP is at least 2% of price away, so only the SL side can trigger the filter with the default `min_profit_pct`. Fact from the old tests: a long's SL lands above its entry whenever the 480-bar low equals the 240-bar low (`test_long_entry_on_breakdown_below_prev_window_low` at `f3bb9e64^`: entry 99.0, window low 99.5, so SL 99.5). Phase 03 asks the owner whether distances are signed (such entries are skipped) or absolute (they are kept). Recommended: signed.
- **One run at a time, time guard.** A new run starts only when no `backtest_runs` document has `status=started` and the UTC hour is in 04-21, so a run of up to two hours never reaches the 00:00Z `sync_repair` or the 03:00Z `sync_backfill` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:805-824`). Polls wait at most 8 minutes per command so the shell tool limit never cuts them.
- **Paper window.** All passing sets start together after both tracks have verdicts. No `develop:master` release runs between the paper start and the reconciliation, because a deploy replaces the trader container and drops its logs.
- **Error evidence.** The trader logs `strategy_on_bar_error` with `strategy_id=` (`strategy_app_service.py:623,931`) and stale skips as `strategy.entry_skipped` with `reason=stale` and `subscription_id=` (`:631-647`). Docker keeps 3 x 10 MB of trader logs (`deploy/compose.prod.yml:16-20`), so Phase 07 counts them in checkpoints at most 2 days apart and checks that each checkpoint's retained log starts before the previous checkpoint ended.
- **Not touched.** Triple Screen code, the three existing paper subscriptions (`intervals_key` `5m,15m,1h`, `15m,1h,4h`, `1h,4h,1d`), `EXNESS_LIVE_TRADING`, the go-live plan, the api `BROKER_DISABLED` check and the SPA strip flag. The new 1m keys cannot collide with the existing three.

## Data flows

- **Backtest (Tracks A and B).** RUNBT posts `RunBacktestCommand` to `POST /api/v1/backtest/run` (`src/pocketquant/app/routes/backtest.py:46-60`). `BacktestCommandService.run` validates with `check_strategy_inputs` and stores a `started` run. `BacktestExecutionService.execute_and_persist` looks up the symbol spec, builds `BacktestConfig` and `StrategyConfig` with it, replays stored 1m bars through a sandbox paper broker priced with the spec, and writes `backtest_runs` (metrics) and `backtest_trades` (`run_id`, `commission`, `exit_reason`). VERDICT reads `backtest_runs.metrics` and prints one `verdict:` line per set into the phase report.
- **hitnrun2 decision.** A 1m bar dict enters `on_bar_completed`; the strategy compares the close with the previous windows, computes SL and TP, applies the cost filter from `config.contract_spec`, and returns a market `Signal` or `None`. Fills and rejections update `_open_direction`.
- **Paper.** Phase 06 creates and starts one subscription per passing set through the api. The trader's reconcile loop loads it with the symbol spec into the pooled paper broker. Closed trades land in `trades` with `run_id=<subscription id>` (`src/pocketquant/engine/live/live_trade_collector.py:37-39`). Phase 07 reads them by `run_id` and the passing run's `backtest_trades` by `run_id`, counts log events from the trader container, and writes one `reconcile:` line per set.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in strict numeric order, one fresh worker per phase. File order is execution order. Phases 01-02 (Track A) run before any Track B code.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`. Every Verify is one self-contained command run from there. The shell keeps no variables between commands. `R` below means `plans/261109-1349-1m-strategy-evidence/reports`.
- **Reports** go to `R/phase-NN-<slug>.md`. Each phase writes its own report and ends it with `Result: PASS` when every task passed. At the end of each phase (and before any `NOT_YET` exit) commit the plan directory with `docs(plans): <what was recorded>` and push `develop` with the Ops recipe. Commits that touch only `plans/**` or `**/*.md` trigger no CI (`.github/workflows/cicd.yml:5-10`).
- **Entry gate (EG)** runs first in every phase: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) after `git fetch -q origin`, `git rev-parse HEAD` equals `git rev-parse origin/develop`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) the phase-specific lines. A resumed phase may show its own task files as uncommitted and may be ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: edit nothing, spawn no `kongming`, run `rm -f .cache/ssh/vps_key`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Record the answer in English in the report. Only an explicit yes (or the named choice) counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward unless the answer names what it covers. Every `develop:master` push is an [ASK].
- **Stop-and-ask points** (from the handover brief): a backtest run fails or exceeds 1800 s; the strategy does not receive the symbol's `contract_spec` and a fix needs an engine change; a release to master is due; a destructive action (deleting prod data, force-push) would be needed; a change outside the confirmed scope seems required.
- **Search** uses `git grep` (`rg` is not installed in Git Bash): `git grep -n -E "<pattern>" -- <paths>`; counts pipe to `wc -l`.
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` prints `All checks passed!`; `uv run pyright src <every test file the phase touched>` ends with `0 errors, 0 warnings, 0 informations`. If only the metric ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the report; never pad or split code to satisfy it.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the tail line contains `passed` and the count prints `0` (the two excluded tests fail under a non-UTC local zone, as in the earlier plans). About 100 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references, no plan or phase ids); push `develop`; then `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals the pushed code commit.
- **No plan ids**, phase numbers, decision codes or finding codes in code, comments, test names, log events or commit messages.
- **Code** follows `CLAUDE.md`: no docstrings (a WHY goes in a `#` comment), a flow in one file, a new helper or parameter only with a real caller, delete dead code in the same change, UUIDv7 ids, repositories only in `core.infra.persistence.repositories`, fastapi only in `app`, log level by frequency. The strategy logs nothing.
- **Data**: no fake or synthetic data on prod. Tests use seeded bars in the test Mongo only. Prod is read-only except the planned backtest runs (Phases 02 and 05) and subscription creates and starts (Phase 06).
- **Secrets** never go on a command line or into the repo. Prod reads and admin calls run as a Python script inside the `api` container (PRODPY). Delete `.cache/ssh/vps_key` at the end of every phase that copied it and before every `NOT_YET` exit.
- **Failure Protocol**: each phase file ends with the literal block in "Failure Protocol" below. A failed Verify stops the phase and goes to `kongming`; a `NOT_YET` exit or an [ASK] does not.

## Ops recipe (phases cite these names)

- **KEY**: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
- **SSH `<cmd>`**: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`.
- **COMPOSE**: on the VPS, `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env <args>`.
- **PRODPY**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -o ServerAliveInterval=60 -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py'`. **PRODPY-ARG `<args>`** is the same command with ` <args>` appended after `python /tmp/f.py`.
- **HEADER** (first lines of every script that reads Mongo): `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]`. Scripts never print a secret.
- **LIVECHK**: write `.cache/live.py` with the two lines `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'`. Pass: `trader_live=False`.
- **SUBS3**: PRODPY with HEADER plus `keys = ["5m,15m,1h", "15m,1h,4h", "1h,4h,1d"]` / `subs = list(db.subscriptions.find({"strategy_code": "triple_screen", "intervals_key": {"$in": keys}}, {"desired_state": 1, "actual_state": 1}))` / `print(f"existing_subs={len(subs)} running={sum(1 for d in subs if d.get('desired_state') == 'running' and d.get('actual_state') == 'running')}")`. Pass: `existing_subs=3 running=3`.
- **FREE**: SSH `free -m`; record its `Mem:` line.
- **Push**: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`. A release is `develop:master` in the same command and is always an [ASK]. Never print a token. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`; wait `sleep 15` before looking up a run.
- Prod logs are console format with ANSI colours: strip with `sed 's/\x1b\[[0-9;]*m//g'`.

## Shared scripts

**RUNBT** (Phases 02 and 05). Write to `.cache/f.py`; run with PRODPY-ARG `<label>` to start a run, or `<label> <run_id>` to keep waiting for one. Phase 05 first replaces the line `MIN_PROFIT_PCT_LOW = None` with the recorded value.

```python
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime

from pymongo import MongoClient

from pocketquant.core.config import get_settings

MIN_PROFIT_PCT_LOW = None
RUNS = {
    "A1": ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "stop", "exit_mode": "strategy"}),
    "A2": ("triple_screen", ["1m", "5m", "15m"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "A3": ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "stop", "exit_mode": "strategy"}),
    "A4": ("triple_screen", ["1m", "15m", "1h"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "B1": ("hitnrun2", ["1m"], {}),
    "B2": ("hitnrun2", ["1m"], {"min_profit_pct": MIN_PROFIT_PCT_LOW}),
}
BASE = "http://localhost:41921/api/v1/backtest"
s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
label = sys.argv[1]
strategy, intervals, params = RUNS[label]
if None in params.values():
    sys.exit("MIN_PROFIT_PCT_LOW is not set")
if len(sys.argv) > 2:
    run_id = sys.argv[2]
else:
    busy = db.backtest_runs.find_one({"status": "started"}, {"_id": 1})
    if busy:
        print(f"busy={busy['_id']}")
        sys.exit(2)
    body = {
        "strategy_id": strategy, "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": "2025-11-09T00:00:00", "end_date": "2026-11-08T23:59:00",
        "parameters": params,
        "name": f"{strategy} {' '.join(intervals)} {json.dumps(params, sort_keys=True)}",
    }
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": s.admin_token.get_secret_value()},
    )
    run_id = json.load(urllib.request.urlopen(req))["request_id"]
    print(f"run={label} id={run_id}", flush=True)
deadline = time.time() + 480
doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
while doc["status"] == "started" and time.time() < deadline:
    time.sleep(30)
    doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
started = datetime.fromisoformat(str(doc["started_at"]).replace("Z", "+00:00")).replace(tzinfo=UTC)
if doc["status"] == "started":
    print(f"run={label} id={run_id} status=started running_s={int((datetime.now(UTC) - started).total_seconds())}")
    sys.exit(0)
completed = datetime.fromisoformat(str(doc["completed_at"]).replace("Z", "+00:00")).replace(tzinfo=UTC)
m = doc.get("metrics") or {}
print(
    f"run={label} id={run_id} status={doc['status']} elapsed_s={int((completed - started).total_seconds())} "
    f"trades={m.get('total_trades')} return={m.get('total_return')} pf={m.get('profit_factor')} "
    f"max_dd={m.get('max_drawdown')} sharpe={m.get('sharpe_ratio')} win={m.get('win_rate')} "
    f"commission={m.get('total_commission')} error={doc.get('error_message')}"
)
```

**VERDICT** (Phases 02 and 05). Write to `.cache/f.py`; run with PRODPY-ARG `<set> <label>=<run_id> <label>=<run_id>`. It prints one `gate_run=` line per run and one `verdict:` line.

```python
import sys

from pymongo import MongoClient

from pocketquant.core.config import get_settings

GATE_PF = 1.2
GATE_TRADES = 100
s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
rows = []
for arg in sys.argv[2:]:
    label, run_id = arg.split("=", 1)
    doc = db.backtest_runs.find_one({"_id": run_id}, {"status": 1, "metrics": 1}) or {}
    m = doc.get("metrics") or {}
    pf, trades = float(m.get("profit_factor") or 0.0), int(m.get("total_trades") or 0)
    ok = doc.get("status") == "finished" and pf >= GATE_PF and trades >= GATE_TRADES
    rows.append((ok, pf, trades, label))
    print(f"gate_run={label} id={run_id} status={doc.get('status')} pf={pf:.4f} trades={trades} pass={'yes' if ok else 'no'}")
ok, pf, trades, label = max(rows, key=lambda r: (r[0], r[1]))
print(f"verdict: {'pass' if ok else 'fail'} set={sys.argv[1]} run={label} pf={pf:.4f} trades={trades}")
```

## Phases

| # | Phase | Prod writes | Depends on |
|---|---|---|---|
| 01 | [Push the plan, no-look-ahead check, 1m coverage and spec check](./phase-01-plan-push-and-coverage.md) | none | — |
| 02 | [Track A: four Triple Screen 1m backtests, table, two verdicts](./phase-02-track-a-backtests.md) | 4 backtest runs | 01 |
| 03 | [Track B: hitnrun2 on the multi-interval contract with the cost filter, tests, CI](./phase-03-hitnrun2-strategy.md) | none | 02 |
| 04 | [Track B release: develop:master, deploy, post-checks](./phase-04-hitnrun2-release.md) | release [ASK] | 03 |
| 05 | [Track B: two hitnrun2 backtests, table, one verdict](./phase-05-hitnrun2-backtests.md) | 2 backtest runs | 04 |
| 06 | [Paper start for passing sets only](./phase-06-paper-start.md) | 0-3 subscriptions | 02, 05 |
| 07 | [Paper observation checkpoints and reconciliation](./phase-07-paper-reconcile.md) | none | 06 |
| 08 | [Close: verdict per set, status, archive](./phase-08-close.md) | none | 07 |

Dependency graph: `01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07 -> 08`. Phase 06 also reads Phase 02's verdicts. Only Phase 03 changes repo code, so no two phases touch the same code file. Every phase writes only its own report; Phase 08 also edits `plan.md` and moves the directory.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run recorded with `profit_factor` and `total_trades` | Phase 02 table has 4 rows `A1`-`A4`, Phase 05 table has 2 rows `B1`-`B2`, every run line `status=finished` |
| AC2 | One verdict per set | `grep -h "^verdict: " R/phase-02-*.md R/phase-05-*.md \| wc -l` prints `3`; Phase 08 repeats the three lines |
| AC3 | hitnrun2 on master with `intervals=["1m"]` and a `min_cost_multiple` filter reading `config.contract_spec` | Phase 03 tests pass; `STRATEGY_REGISTRY` keys `['hitnrun2', 'triple_screen']`; `git grep -n "0\.15" -- src/pocketquant/core/domain/strategy` prints nothing; Phase 04 master run `completed success`; prod `/api/v1/backtest/strategies` lists `hitnrun2` |
| AC4 | The filter is proven to skip and to take | Phase 03 unit tests (skip under the multiple, take above it, same bars taken with no costs) and the backtest-path test (`trades == 0` at a huge multiple with the seeded spec) |
| AC5 | Paper only for passing sets, at least 14 days | Phase 06 `paper_sets=` equals the passing sets; Phase 07 reconciles only after `paper_end` |
| AC6 | Reconciliation record with the four A5 columns | One `reconcile:` line per paper set with `trades_per_day`, `avg_commission`, `exit_mix`, `on_bar_error`, `stale` |
| AC7 | Existing paper subscriptions untouched, live disarmed | SUBS3 `existing_subs=3 running=3` in Phases 04, 06, 07; LIVECHK `trader_live=False` in Phase 04 |
| AC8 | Plan closed | `test -d plans/archive/261109-1349-1m-strategy-evidence` and its `plan.md` has `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Unit | hitnrun2 signals, SL/TP formulas, direction filter, one position, fill and rejection state, `restore_direction`, cost filter skip/take, spec-driven cost, wrong-side stop | `tests/core_test/unit/domain/strategy/test_hitnrun2.py` (Phase 03) |
| Backtest path (real test Mongo) | hitnrun2 finishes through `BacktestCommandService` and `BacktestExecutionService`; the seeded symbol spec reaches the strategy | `tests/backtest_test/engine/test_hitnrun2_backtest.py` (Phase 03) |
| Existing guards | spec wiring in backtest and reconcile; closed higher-timeframe context with a 1m entry | `tests/backtest_test/test_backtest_dispatch_contract_spec.py`, `tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec`, `tests/backtest_test/test_higher_timeframe_context.py` (uses `["1m", "1h"]`) |
| Suite and CI | FULLSUITE, GATES, develop and master CI | Phases 03, 04 |
| End to end on prod | six 12-month backtests, paper subscriptions trading, reconciliation | Phases 02, 05, 06, 07 |

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes far longer than the 20-25 min estimate or presses api memory while paper subscriptions trade | M x M | One run at a time, `free -m` after each, owner [ASK] after any run above 1800 s, 3 h hard stop, time guard 04-21 UTC |
| R2 | 1m or cascaded bars have holes in the window (live cascade only since 2026-11-02) | L x H | Phase 01 coverage check stops before any run |
| R3 | The filter skips nearly every hitnrun2 entry, so `total_trades < 100` | M x L | A valid result: the set fails and the record says so |
| R4 | Docker log rotation or a container replacement hides error events | M x M | Checkpoints at most 2 days apart with a continuity check; no release during the paper window |
| R5 | The release restarts the trader and the three existing paper subscriptions warm up again | H x L | Expected by the rolling deploy; SUBS3 after the deploy |
| R6 | One window and a fixed threshold overfit | H x M | Accepted by the owner (sweep, DSR, PBO deferred); stated in the close |
| R7 | Paper commission per trade differs from the backtest because the pooled account sizes differently from the 10 000 backtest capital | H x L | Recorded as is; paper has no threshold |
| R8 | The old hitnrun2 SL can sit on the wrong side of the entry | H x M | Phase 03 [ASK] on signed vs absolute distance, with a unit test either way |

## Backwards compatibility and rollback

No data migration. hitnrun2 adds one registry key; existing subscriptions, runs and trades keep their shape. Backtest runs are additive. Rollback per phase: Phases 01-02 and 05 write only runs (left in place; the owner can delete them in the UI); Phase 03 `git revert` on `develop`; Phase 04 re-roll the recorded previous image and revert (each step an [ASK]); Phase 06 stop and delete the new subscriptions (each step an [ASK]); Phases 07-08 change only plan files.

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions. Not adopted from the advice's optional list: archiving the two older completed plans, a second shifted window, compare-view URLs. Cutting Track B after Track A is an owner-only scope change; the plan does not offer it.

## Unresolved

1. Phase 03 [ASK]: signed or absolute exit distance for the cost filter, the default `min_cost_multiple` (recommended 3), and the lower `min_profit_pct` for run B2 (recommended 0.005).
2. Whether the new paper subscriptions keep running after the plan closes. Stopping them is a prod write outside the confirmed scope, so Phase 08 lists their ids for the owner and leaves them running.
3. Trader log volume per day is unknown; the 2-day checkpoint interval assumes 30 MB holds at least two days.

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
title: "Push the plan, no-look-ahead check, 1m coverage and spec check"
status: pending
priority: P2
effort: 0.5h
dependencies: []
---

# Phase 01: Push the plan, no-look-ahead check, 1m coverage and spec check

## Goal

The plan is on `origin/develop`; the closed-bucket context rule is proven by its tests for a 1m entry; the stored `XAUUSD:EXNESS` bars cover the backtest window for every interval Track A uses; and the symbol's stored spec holds the seeded gold costs.

## Context

- Window: `2025-11-09T00:00:00Z` to `2026-11-09T00:00:00Z` (plan.md Design rules). Track A intervals: `1m`, `5m`, `15m`, `1h`. Top intervals: `15m` (set `1m,5m,15m`) and `1h` (set `1m,15m,1h`).
- Coverage rule as amended and accepted in the earlier Phase 16 (`plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md`, `coverage_ask=yes`): the expected buckets of an interval are the buckets of calendar minutes that have a stored 1m bar; every interval needs `pct >= 99.9`; `cal_pct` is printed for the record (the Exness calendar has no holidays, so it sits near 98.3-99.7). A top interval needs at least 36 bars before the start (Triple Screen needs `macd_slow + macd_signal + 1 = 36`).
- Calendar API: `TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)` (`src/pocketquant/core/infra/calendars/trading_calendar_factory.py:26-38`), `trading_minutes`, `bar_start` (`src/pocketquant/core/domain/market_data/trading_calendar_port.py:38-41`).
- Spec seed: `commission_per_contract=0.035`, `spread=0.08` (`scripts/seed_exness_symbols.py:40-48`). Symbols are stored in `symbols` keyed by field `symbol` (`src/pocketquant/core/infra/persistence/repositories/symbol_repository.py:41-43`).
- No-look-ahead: `tests/backtest_test/test_higher_timeframe_context.py` runs the live, warm-up and backtest context paths with a `["1m", "1h"]` entry (lines 217, 262) and checks the first entry bar of a bucket sees only the previous bucket (governance checks 1-4).
- The plan directory and the two advice reports are untracked at plan time.

## Entry gate

1. EG (1) of plan.md Conventions prints nothing.
2. `git fetch -q origin && git rev-parse HEAD` equals `git rev-parse origin/develop`.
3. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (start Docker Desktop per FULLSUITE and retry once).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 01 after <UTC time>
```

## Files

- Repo: commit the plan directory and `plans/reports/advise-261109-1309-next-plan.md`, `plans/reports/advise-261109-1309-next-plan-state.md`. Create `R/phase-01-plan-push-and-coverage.md`.
- Prod: read-only.

## Tasks

### Task 01.1 — Commit and push the plan

**Goal:** the runner and later phases read the plan from `origin/develop`.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/`, the two advice reports.

**Steps:**
1. `git add plans/261109-1349-1m-strategy-evidence plans/reports/advise-261109-1309-next-plan.md plans/reports/advise-261109-1309-next-plan-state.md`.
2. `git commit -m "docs(plans): add the 1m strategy evidence plan"`.
3. Push with the Ops recipe.

**Success criteria:** the plan directory has no uncommitted file and `HEAD` equals `origin/develop`.

**Verify:** `git status --porcelain -- plans/261109-1349-1m-strategy-evidence | wc -l; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `0` then `pushed`.

### Task 01.2 — Closed higher-timeframe rule holds for a 1m entry

**Goal:** the governance checks before trusting a multi-timeframe backtest pass on the current code.

**Target files and symbols:** `tests/backtest_test/test_higher_timeframe_context.py`.

**Steps:**
1. `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`.
2. Record the tail line in the report.

**Success criteria:** every test in the file passes.

**Verify:** `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `passed` and does not contain `failed` or `error`.

### Task 01.3 — Coverage and spec check (read-only)

**Goal:** every Track A interval covers the window, the top intervals have history before it, and the stored spec holds the seeded costs.

**Target files and symbols:** prod `bars`, `symbols`.

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
spec = (db.symbols.find_one({"symbol": SYM}) or {}).get("contract_spec") or {}
print(f"spec_commission={spec.get('commission_per_contract')} spec_spread={spec.get('spread')} spec_multiplier={spec.get('multiplier')}")
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)
minutes = cal.trading_minutes(START, END)
q1 = {"symbol": SYM, "interval": "1m", "datetime": {"$gte": START, "$lt": END}}
stored_1m = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q1, {"datetime": 1})}
have = [m for m in minutes if m in stored_1m]
print(f"1m cal_expected={len(minutes)} stored={len(have)} cal_pct={100.0 * len(have) / len(minutes):.2f}")
worst = 100.0
for iv in ["5m", "15m", "1h"]:
    cal_expected = {cal.bar_start(m, Interval(iv)) for m in minutes}
    expected = {cal.bar_start(m, Interval(iv)) for m in have}
    q = {"symbol": SYM, "interval": iv, "datetime": {"$gte": min(cal_expected), "$lt": END}}
    stored = {b["datetime"].replace(tzinfo=UTC) for b in db.bars.find(q, {"datetime": 1})}
    covered = len(expected & stored)
    pct = 100.0 * covered / len(expected)
    worst = min(worst, pct)
    before = db.bars.count_documents({"symbol": SYM, "interval": iv, "datetime": {"$lt": START}})
    print(f"{iv} expected={len(expected)} covered={covered} pct={pct:.2f} cal_pct={100.0 * len(cal_expected & stored) / len(cal_expected):.2f} extra={len(stored - cal_expected)} before={before}")
print(f"worst_pct={worst:.2f}")
```
2. Record every output line in the report. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `first_1m` is on or before `2025-11-09`; `bar_calendar=EXNESS_XAUUSD`; the spec line shows `0.035`, `0.08` and `1.0`; `worst_pct >= 99.90`; `before` for `15m` and `1h` is at least 36.

**Verify:** the output's first line is `first_1m=<date> bar_calendar=EXNESS_XAUUSD` with `<date> <= 2025-11-09`; its second line is exactly `spec_commission=0.035 spec_spread=0.08 spec_multiplier=1.0`; its last line is `worst_pct=<n>` with `n >= 99.90`; the `15m` and `1h` lines show `before=` values `>= 36`.

### Task 01.4 — Report and commit

**Goal:** the phase record is on `origin/develop`.

**Target files and symbols:** `R/phase-01-plan-push-and-coverage.md`.

**Steps:**
1. Write the report: entry-gate outputs, the Task 01.1 commit sha, the Task 01.2 tail line, the Task 01.3 output, then the last line `Result: PASS`.
2. Commit `docs(plans): record the 1m coverage check` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-01-plan-push-and-coverage.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

Nothing on prod changed. `git revert` the plan commit only if the owner withdraws the plan.

## Report

`R/phase-01-plan-push-and-coverage.md`: entry-gate outputs, commit sha, the context-test tail line, the coverage and spec output, `Result: PASS`.

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
effort: "0.5h work + about 2h run wall time"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen 1m backtests, table, two verdicts

## Goal

Four finished 12-month Triple Screen runs with a 1m entry screen on `XAUUSD:EXNESS` (A1), each followed by a memory reading, in one table, with one gate verdict per set.

## Context

- Runs (A1, D2): `A1` = `1m,5m,15m` stop/strategy, `A2` = `1m,5m,15m` market/sl_tp, `A3` = `1m,15m,1h` stop/strategy, `A4` = `1m,15m,1h` market/sl_tp. They are the `RUNS` entries of RUNBT (plan.md Shared scripts). No code change: `check_strategy_inputs` accepts all four (strictly ascending multiples; Triple Screen needs exactly 3 intervals, `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py:48-49`); checked on HEAD `00272823` with `uv run python -c` for all four inputs.
- Costs (A2): the body sends no `spread` and no commission; the seeded spec applies (plan.md Design rules, "Costs in backtests").
- Cost and isolation: a run is an asyncio task in the api process with no concurrency cap (`src/pocketquant/app/routes/backtest.py:46-60`). The trader runs in its own container, but Mongo is shared. Estimate 20-25 min per 1m run (advice; the 5m set took 234 s and 273 s). RUNBT refuses to start while any run is `started` and waits at most 8 min per call.
- Run status values: `started`, `finished`, `failed` (`src/pocketquant/core/domain/backtest/entities.py:23`). Metrics keys include `profit_factor`, `total_trades`, `total_commission` (`src/pocketquant/core/domain/trading/value_objects.py:178-194`).
- Gate (D4) and set rule: plan.md Design rules, "Set and verdict"; VERDICT script.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-01-plan-push-and-coverage.md`.
2. `grep -c "^worst_pct=" plans/261109-1349-1m-strategy-evidence/reports/phase-01-plan-push-and-coverage.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 02 after <UTC time>
```

## Files

- Repo: `R/phase-02-track-a-backtests.md` only.
- Prod writes: four `backtest_runs` with their orders and trades.

## Tasks

### Task 02.1 — Four runs, one at a time

**Goal:** `A1`-`A4` finished, each with a `free -m` line, and an owner answer for any run above 1800 s.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`; RUNBT.

**Steps:**
1. KEY. Write RUNBT to `.cache/f.py` unchanged.
2. For `<label>` in `A1`, `A2`, `A3`, `A4`, in that order:
   1. If the report holds `run=<label> id=<id> status=finished`, skip this label.
   2. If the report holds `run=<label> id=<id>` without a final line, run PRODPY-ARG `<label> <id>` (poll only) and go to step 2.5.
   3. Before a new run: if the previous label's final line has `elapsed_s` above `1800`, the report must hold a `cost_ask=` line whose `covers=` list contains `<label>`; otherwise do step 3 first. Then run `date -u +%H`; if the hour is below `04` or above `21`, run `rm -f .cache/ssh/vps_key`, commit and push the report, and end with `NOT_YET: outside the 04-21 UTC run window` and `Resume: ... --from 02 after <next 04:00Z>`.
   4. Run PRODPY-ARG `<label>`. Append the `run=<label> id=<id>` line to the report at once. If the output is `busy=<id>`, append it, run `rm -f .cache/ssh/vps_key`, commit and push the report, and end with `NOT_YET: another backtest is running` and `Resume: ... --from 02 after <now + 30 min>`.
   5. While the last output line contains `status=started`, run PRODPY-ARG `<label> <id>` again. If `running_s` exceeds `10800` (3 h), that is a failed Verify.
   6. Append the final line. SSH `free -m` and append its `Mem:` line as `free_after_run=<label> <line>`.
3. **[ASK] when a finished run's `elapsed_s` is above 1800.** Ask in Vietnamese (intent): "Run `<label>` took `<minutes>` min; `free -m` after it: `<line>`. Continue with `<remaining labels>`, one at a time?" Lead with `Recommended: yes`, reason: runs never overlap and memory after the run is the line shown. Record `cost_ask=<label> <reply> covers=<labels the yes names>`. A non-yes ends the phase with `NOT_YET` (after `rm -f .cache/ssh/vps_key` and a report commit).
4. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four `status=finished` lines, four `free_after_run=` lines, a `cost_ask=` yes covering every run that followed a run above 1800 s.

**Verify:** `grep -c -E "^run=A[1-4] id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c -E "^free_after_run=A[1-4] " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `4`.

### Task 02.2 — Run table

**Goal:** the four runs read side by side in one table.

**Target files and symbols:** the phase report.

**Steps:**
1. Write the header `| label | strategy | intervals | parameters | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | sharpe | win_rate | total_commission |`.
2. Write one row per label from its final run line, e.g. `| A1 | triple_screen | 1m,5m,15m | entry_type=stop exit_mode=strategy | <id> | <elapsed_s> | <trades> | <return> | <pf> | <max_dd> | <sharpe> | <win> | <commission> |`. Copy values; do not round.

**Success criteria:** 4 rows.

**Verify:** `grep -c -E "^\| A[1-4] \| triple_screen \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4`.

### Task 02.3 — Gate verdict per set

**Goal:** one `verdict:` line per Track A set, computed from `backtest_runs`.

**Target files and symbols:** VERDICT; prod `backtest_runs`.

**Steps:**
1. KEY. Write VERDICT to `.cache/f.py`.
2. PRODPY-ARG `triple_screen/1m,5m,15m A1=<A1 id> A2=<A2 id>`; append all output lines to the report directly under the table.
3. PRODPY-ARG `triple_screen/1m,15m,1h A3=<A3 id> A4=<A4 id>`; append all output lines.
4. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two `verdict:` lines, each naming its set, `pass` only when its named run has `pf >= 1.2` and `trades >= 100`.

**Verify:** `grep -c -E "^verdict: (pass|fail) set=triple_screen/(1m,5m,15m|1m,15m,1h) run=A[1-4] pf=[0-9.]+ trades=[0-9]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2`.

### Task 02.4 — Report and commit

**Goal:** the Track A record is on `origin/develop`.

**Target files and symbols:** `R/phase-02-track-a-backtests.md`.

**Steps:**
1. Make sure the report holds: entry-gate outputs; all run lines and `free_after_run=` lines; any `cost_ask=` lines; the table; the `gate_run=` and `verdict:` lines; last line `Result: PASS`.
2. Commit `docs(plans): record the triple screen 1m backtests` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

Nothing to undo: the four runs stay as evidence; the owner may delete them in the UI.

## Report

`R/phase-02-track-a-backtests.md`: entry-gate outputs; eight run lines (plus any poll lines); four `free_after_run=` lines; any `cost_ask=` answers; the table; the VERDICT output; `Result: PASS`.

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

=== FILE: phase-03-hitnrun2-strategy.md ===
---
phase: 3
title: "Track B: hitnrun2 on the multi-interval contract with the cost filter, tests, CI"
status: pending
priority: P2
effort: 1d
dependencies: [2]
---

# Phase 03: Track B: hitnrun2 on the multi-interval contract with the cost filter, tests, CI

## Goal

`hitnrun2` is registered on the current strategy contract with `intervals=["1m"]` and a `min_cost_multiple` filter that reads the round-trip cost from `config.contract_spec`; unit and backtest-path tests pass; `develop` CI is green.

## Context

- Old code (`git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`): windows taken before the current bar is appended; warm-up until `sl_lookback_bars` previous bars exist; one position at a time; long when `close < min(previous entry_lookback_bars lows)` with `sl = max(min(previous sl_lookback_bars lows), close * (1 - max_loss_pct))` and `tp = max(max(previous tp_lookback_bars highs), close * (1 + min_profit_pct))`; short mirrored; any opposite-side fill closes; any rejection clears the position. Its `_closes` deque is unused and its `datetime.now(UTC)` timestamp fallback reads the clock; both are dropped.
- Current contract: `IStrategyService` (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:16-49`: `DEFAULTS: ClassVar[dict]`, `_open_direction`, `restore_direction`, `on_order_filled(order: FilledOrder, fill_price)`, `on_order_rejected(reason)`); `Signal` (`src/pocketquant/core/domain/strategy/value_objects.py:10-28`); `StrategyConfig.contract_spec` (`:42`); `ContractSpec` fields `multiplier`, `commission_per_contract` (may be `None`), `spread` (`src/pocketquant/core/domain/symbol/value_objects.py:22-36`); registry and `check_strategy_inputs` (`src/pocketquant/core/domain/strategy/services/__init__.py`), which constructs the class with the default `LINEAR_SPEC` (`commission_per_contract=None`, `spread=0.0`).
- The engine sets `bar["context"]` for every strategy (`src/pocketquant/engine/strategy/strategy_app_service.py:422-425`); hitnrun2 never reads it. `snapshot` stays `None` (optional, `:87-97`).
- Cost filter definition and the wrong-side SL fact: plan.md Design rules, "Cost filter".
- Test shapes to follow: `tests/core_test/unit/domain/strategy/test_triple_screen.py`, `tests/backtest_test/engine/test_triple_screen_backtest.py`. `asyncio_mode = "auto"` (`pyproject.toml:63`). Fills use `OrderAggregate.create` (`src/pocketquant/core/domain/order/entities.py:52-63`) so pyright accepts them as `FilledOrder` (a `SimpleNamespace` fails pyright, as in `test_triple_screen.py`).
- DRY: `_execution` and `_cmd_svc` already exist in `tests/backtest_test/test_backtest_single_run_direct_task.py:104-117` and in `test_triple_screen_backtest.py:46-59`. The new backtest test imports them from `test_backtest_single_run_direct_task` instead of adding a third copy (the repo already imports helpers across test modules, e.g. `tests/app_test/unit/market_data/test_sync_jobs_fold.py:10`).
- `SymbolLookupHelper` caches lookups for 60 s in the module-level `_CACHE`, misses included (`src/pocketquant/core/infra/persistence/symbol_lookup_helper.py:15-38`); a test that seeds a symbol clears it before and after (precedent `tests/app_test/integration/test_futures_sync_end_to_end.py:103,135`).
- Baselines on HEAD `00272823`: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; ratchet exits 0; ruff `All checks passed!`; `uv run pyright src` `0 errors, 0 warnings, 0 informations`.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-02-track-a-backtests.md`.
2. `grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2` (Track A numbers exist before any Track B code).
3. `git grep -n -i "hitnrun" -- src tests | wc -l` prints `0`.
4. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 03 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `tests/backtest_test/engine/test_hitnrun2_backtest.py`.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py`.
- Report: `R/phase-03-hitnrun2-strategy.md`.

## Tasks

### Task 03.1 — [ASK] the filter form and the second run's `min_profit_pct`

**Goal:** the owner fixes the two open choices with the Track A numbers in hand.

**Target files and symbols:** the phase report.

**Steps:**
1. Ask in Vietnamese (intent), with the Phase 02 table and verdict lines: "hitnrun2 will skip an entry when the nearer of its TP and SL distances is below `min_cost_multiple` x the round-trip cost from the symbol spec (gold: 0.035 x 2 + 0.08 = 0.15, so 0.45 at a multiple of 3). (1) The old code puts a long's SL above its entry whenever the 480-bar low equals the 240-bar low (old test: entry 99.0, SL 99.5). Signed distance skips those entries; absolute distance keeps them. Which? (2) Default `min_cost_multiple`? (3) The second backtest uses which lower `min_profit_pct` (default 0.02, about 80 USD/oz on gold)?" Lead with `Recommended: signed, 3, 0.005`, reason: a stop on the wrong side of the entry leaves no room to cover any cost, and 0.5 % is a quarter of the old target while still far above three round-trip costs.
2. Record three lines: `filter_form=signed` or `filter_form=absolute`; `min_cost_multiple_default=<number>`; `min_profit_pct_low=<number>`.

**Success criteria:** the three lines exist; `min_profit_pct_low` is above 0 and below 0.02; `min_cost_multiple_default` is at least 0.

**Verify:** `grep -c -E "^(filter_form=(signed|absolute)|min_cost_multiple_default=[0-9]+(\.[0-9]+)?|min_profit_pct_low=0\.0[0-9]+)$" plans/261109-1349-1m-strategy-evidence/reports/phase-03-hitnrun2-strategy.md` prints `3`, and `grep -E "^min_profit_pct_low=" plans/261109-1349-1m-strategy-evidence/reports/phase-03-hitnrun2-strategy.md | cut -d= -f2 | awk '{print ($1 > 0 && $1 < 0.02) ? "low-ok" : "low-bad"}'` prints `low-ok`.

### Task 03.2 — The symbol spec reaches the strategy in both paths (read-only)

**Goal:** the Unverified item 1 of the advice is settled before code depends on it.

**Target files and symbols:** `src/pocketquant/engine/backtest/backtest_execution_service.py` (`run`), `src/pocketquant/engine/live/strategy_reconcile_app_service.py` (`_ensure_instances`), `src/pocketquant/app/di/services.py` (`get_reconcile_service`).

**Steps:**
1. `git grep -n "contract_spec=config.contract_spec" -- src/pocketquant/engine/backtest/backtest_execution_service.py | wc -l` (strategy config and broker; expect `2`).
2. `git grep -n "contract_spec=contract_spec," -- src/pocketquant/engine/live/strategy_reconcile_app_service.py | wc -l` (expect `1`).
3. `git grep -n "symbol_lookup=symbol_lookup" -- src/pocketquant/app/di/services.py | wc -l` (expect `2`).
4. `uv run python -m pytest tests/backtest_test/test_backtest_dispatch_contract_spec.py "tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec" -q 2>&1 | tail -1`.
5. **Stop-and-ask on a miss.** If any count differs or the tests fail, the spec does not reach the strategy and a fix needs an engine change. Do not edit any engine file and do not run the Failure Protocol. [ASK] in Vietnamese (intent): "The strategy does not receive the symbol's `contract_spec` on the <backtest|trader> path (<command and output>). A fix needs an engine change in <file>, outside the confirmed scope. How do you want to proceed?" Lead with `Recommended: stop here; fix the engine in its own reviewed change first`, reason: the filter would silently see zero cost. Record `spec_ask=<reply>` and end with `NOT_YET`. Only an owner instruction that names the change continues.

**Success criteria:** counts `2`, `1`, `2`; the tests pass.

**Verify:** `git grep -n "contract_spec=config.contract_spec" -- src/pocketquant/engine/backtest/backtest_execution_service.py | wc -l; git grep -n "contract_spec=contract_spec," -- src/pocketquant/engine/live/strategy_reconcile_app_service.py | wc -l; git grep -n "symbol_lookup=symbol_lookup" -- src/pocketquant/app/di/services.py | wc -l` prints `2`, `1`, `2`, and the step 4 tail line contains `passed` and not `failed` or `error`.

### Task 03.3 — Unit tests first

**Goal:** hitnrun2's behaviour and the filter are pinned before the strategy exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Steps:**
1. Helpers in the test file (no docstrings):
   - `_T0 = datetime(2026, 1, 1, tzinfo=UTC)`; `_GOLD = ContractSpec(commission_per_contract=0.035, spread=0.08)`; `_GOLD_LOTS = ContractSpec(multiplier=100.0, commission_per_contract=3.5, spread=0.08)` (the same 0.15 per unit of price).
   - Bar rows `(high, low, close)`: `_DEEP = (99.6, 98.0, 99.5)`, `_FLAT = (100.1, 99.9, 100.0)`, `_RISE = (102.0, 100.4, 100.5)`, `_BREAK_DOWN = (100.0, 99.0, 99.2)`, `_BREAK_UP = (101.0, 100.0, 100.8)`, `_REENTRY = (99.0, 98.5, 98.6)`. `_LONG_SETUP = [_DEEP] * 3 + [_FLAT] * 5` (8-bar low 98.0, 5-bar low 99.9); `_SHORT_SETUP = [_RISE] * 3 + [_FLAT] * 5`.
   - `_cfg(spec=LINEAR_SPEC, intervals=("1m",), **params)` returns `StrategyConfig(id="sub-1", name="hitnrun2", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters={"entry_lookback_bars": 5, "sl_lookback_bars": 8, "tp_lookback_bars": 3, "min_cost_multiple": 3.0, **params}, contract_spec=spec)`. The explicit `min_cost_multiple=3.0` keeps the tests independent of the default the owner chose.
   - `_bar(i, row)` returns `{"symbol": "XAUUSD:EXNESS", "interval": "1m", "open": c, "high": h, "low": lo, "close": c, "volume": 1.0, "timestamp": _T0 + timedelta(minutes=i)}`.
   - `async def _started(spec=LINEAR_SPEC, **params)` builds `HitNRun2StrategyService(_cfg(spec, **params))`, awaits `on_start()`, returns it.
   - `async def _feed(s, rows, first=0)` feeds `rows` as bars `first, first+1, ...` and returns the list of results.
   - `_fill(side)` returns `OrderAggregate.create(subscription_id="sub-1", symbol="XAUUSD:EXNESS", side=side, order_type=OrderType.MARKET, quantity=1.0, price=99.0)`.
2. Tests (names state the rule; numbers follow from the rows above):
   - `test_more_than_one_interval_is_rejected`: `_cfg(intervals=("1m", "5m"))` raises `ValueError`.
   - `test_an_unknown_direction_is_rejected`: `direction="sideways"` raises `ValueError` matching `direction`.
   - `test_a_negative_cost_multiple_is_rejected`: `min_cost_multiple=-1.0` raises `ValueError`.
   - `test_no_signal_until_the_stop_window_is_full`: feeding `[_DEEP] * 3 + [_FLAT] * 4 + [_BREAK_DOWN]` returns `None` for every bar.
   - `test_long_when_the_close_breaks_below_the_entry_window`: the last result of `_LONG_SETUP + [_BREAK_DOWN]` has `direction == Direction.LONG`, `entry_price == 99.2`, `entry_type == "market"`, `entry_logic == "hitnrun2:breakdown"`, `timestamp == _T0 + timedelta(minutes=8)`.
   - `test_the_stop_is_capped_at_max_loss_pct`: same signal, `stop_loss_price == pytest.approx(99.2 * 0.99)`.
   - `test_the_stop_uses_the_window_low_inside_the_cap`: `[(99.6, 98.5, 99.5)] * 3 + [_FLAT] * 5 + [_BREAK_DOWN]` gives `stop_loss_price == pytest.approx(98.5)`.
   - `test_the_target_is_at_least_min_profit_pct`: the `_LONG_SETUP + [_BREAK_DOWN]` signal has `take_profit_price == pytest.approx(99.2 * 1.02)`.
   - `test_the_target_uses_the_window_high_above_the_minimum`: `[_DEEP] * 3 + [_FLAT] * 4 + [(105.0, 99.9, 100.0)] + [_BREAK_DOWN]` gives `take_profit_price == pytest.approx(105.0)`.
   - `test_short_mirrors_the_long`: `_SHORT_SETUP + [_BREAK_UP]` gives `Direction.SHORT`, `entry_price == 100.8`, `stop_loss_price == pytest.approx(100.8 * 1.01)`, `take_profit_price == pytest.approx(100.8 * 0.98)`, `entry_logic == "hitnrun2:breakup"`.
   - `test_direction_long_skips_a_short_breakout`: `direction="long"`, `_SHORT_SETUP + [_BREAK_UP]` ends with `None`.
   - `test_direction_short_skips_a_long_breakdown`: `direction="short"`, `_LONG_SETUP + [_BREAK_DOWN]` ends with `None`.
   - `test_one_position_at_a_time`: after the long signal, `_REENTRY` as bar 9 returns `None`.
   - `test_an_opposite_fill_closes_the_position`: after the long signal, `await s.on_order_filled(_fill(OrderSide.SELL), 98.2)`; `_REENTRY` as bar 9 returns `Direction.LONG`.
   - `test_a_same_side_fill_keeps_the_position`: after the long signal, `await s.on_order_filled(_fill(OrderSide.BUY), 99.2)`; `_REENTRY` returns `None`.
   - `test_a_rejected_entry_clears_the_position`: after the long signal, `await s.on_order_rejected("zero position size")`; `_REENTRY` returns `Direction.LONG`.
   - `test_a_restored_position_blocks_a_new_entry`: feed `_LONG_SETUP`, call `s.restore_direction(Direction.LONG)`, then `_BREAK_DOWN` as bar 8 returns `None`.
   - `test_an_entry_whose_nearer_exit_is_under_the_cost_multiple_is_skipped`, parametrized over `_GOLD` and `_GOLD_LOTS`: `[(99.6, 98.9, 99.5)] * 3 + [_FLAT] * 5 + [_BREAK_DOWN]` ends with `None` (stop distance 0.3 is below 3 x 0.15).
   - `test_the_same_entry_is_taken_when_the_symbol_has_no_costs`: the same rows with `LINEAR_SPEC` give `Direction.LONG` with `stop_loss_price == pytest.approx(98.9)`.
   - `test_an_entry_whose_nearer_exit_covers_the_cost_multiple_is_taken`: `_GOLD`, `_LONG_SETUP + [_BREAK_DOWN]` gives `Direction.LONG` (stop distance 0.992).
   - If `filter_form=signed`: `test_a_stop_on_the_wrong_side_of_the_entry_is_skipped`: `LINEAR_SPEC`, `[_FLAT] * 8 + [_BREAK_DOWN]` ends with `None` (the stop would be 99.9, above the 99.2 entry). If `filter_form=absolute`: `test_a_stop_on_the_wrong_side_of_the_entry_is_kept`: the same rows give `Direction.LONG` with `stop_loss_price == pytest.approx(99.9)`.
3. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1`; expected red (the module does not exist yet).

**Success criteria:** the file has 22 test cases and fails only because the strategy module is missing.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | grep -c -E "ModuleNotFoundError|ImportError"` prints a number `>= 1`.

### Task 03.4 — Strategy and registry entry

**Goal:** `HitNRun2StrategyService` implements the old rules on the current contract plus the cost filter, and is registered as `"hitnrun2"`.

**Target files and symbols:** `hitnrun2_strategy_service.py` (`HitNRun2StrategyService`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. Create the strategy file with this content. Set the `"min_cost_multiple"` default to the recorded `min_cost_multiple_default`. If `filter_form=absolute`, replace the two lines under the `# Signed distances` comment with `nearer = min(abs(tp - close), abs(close - sl))` and replace that comment with `# Absolute distances, as the owner chose: a stop on the wrong side still counts its distance.`; drop the now unused `sign` line.
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
        lookbacks = (self.entry_lookback_bars, self.sl_lookback_bars, self.tp_lookback_bars)
        if len(config.intervals) != 1:
            raise ValueError("hitnrun2 decides on exactly 1 interval")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        if any(n < 1 for n in lookbacks):
            raise ValueError("lookbacks must be >= 1")
        if self.max_loss_pct <= 0 or self.min_profit_pct <= 0:
            raise ValueError("max_loss_pct and min_profit_pct must be above 0")
        if self.min_cost_multiple < 0:
            raise ValueError("min_cost_multiple must be >= 0")
        spec = config.contract_spec
        # Price units per unit of size: commission on both sides plus one spread. A symbol on
        # the percentage commission model has no per-contract fee, so only its spread counts.
        fee = (spec.commission_per_contract or 0.0) * 2 / spec.multiplier
        self._round_trip_cost = fee + spec.spread
        self._highs: deque[float] = deque(maxlen=max(lookbacks))
        self._lows: deque[float] = deque(maxlen=max(lookbacks))

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._open_direction = None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # The windows end at the previous bar, so a bar never breaks its own range.
        highs, lows = list(self._highs), list(self._lows)
        self._highs.append(high)
        self._lows.append(low)
        if len(lows) < self.sl_lookback_bars or self._open_direction is not None:
            return None
        if self.direction in ("long", "both") and close < min(lows[-self.entry_lookback_bars :]):
            sl = max(min(lows[-self.sl_lookback_bars :]), close * (1 - self.max_loss_pct))
            tp = max(max(highs[-self.tp_lookback_bars :]), close * (1 + self.min_profit_pct))
            return self._enter(bar, Direction.LONG, close, sl, tp, "breakdown")
        if self.direction in ("short", "both") and close > max(highs[-self.entry_lookback_bars :]):
            sl = min(max(highs[-self.sl_lookback_bars :]), close * (1 + self.max_loss_pct))
            tp = min(min(lows[-self.tp_lookback_bars :]), close * (1 - self.min_profit_pct))
            return self._enter(bar, Direction.SHORT, close, sl, tp, "breakup")
        return None

    def _enter(
        self, bar: dict, direction: Direction, close: float, sl: float, tp: float, tag: str
    ) -> Signal | None:
        sign = 1 if direction == Direction.LONG else -1
        # Signed distances: a stop on the wrong side of the entry leaves no room for any cost.
        nearer = min(sign * (tp - close), sign * (close - sl))
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
            entry_logic=f"hitnrun2:{tag}",
        )

    # Broker SL/TP exits fill on the opposite side, so any opposite-side fill is the close.
    async def on_order_filled(self, order: FilledOrder, fill_price: float) -> None:
        closing = OrderSide.SELL if self._open_direction == Direction.LONG else OrderSide.BUY
        if self._open_direction is not None and order.side == closing:
            self._open_direction = None

    async def on_order_rejected(self, reason: str) -> None:
        self._open_direction = None
```
2. In `services/__init__.py`: add `from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (HitNRun2StrategyService,)` above the Triple Screen import; set `STRATEGY_REGISTRY = {"triple_screen": TripleScreenStrategyService, "hitnrun2": HitNRun2StrategyService}`; set `__all__ = ["STRATEGY_REGISTRY", "HitNRun2StrategyService", "TripleScreenStrategyService", "check_strategy_inputs"]`.
3. `uv run ruff format src/pocketquant/core/domain/strategy/services tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Success criteria:** every Task 03.3 test passes; the registry holds both keys; `check_strategy_inputs` accepts `hitnrun2` with one interval and rejects two; no literal cost in the strategy.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1` contains `22 passed` and not `failed` or `error`; `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY, check_strategy_inputs; print(sorted(STRATEGY_REGISTRY)); print(check_strategy_inputs('hitnrun2', ['1m'], {'min_profit_pct': 0.005}).__name__)"` prints `['hitnrun2', 'triple_screen']` then `HitNRun2StrategyService`; `uv run python -c "from pocketquant.core.domain.strategy.services import check_strategy_inputs
try:
    check_strategy_inputs('hitnrun2', ['1m', '5m'], {})
except Exception as e:
    print(type(e).__name__)"` prints `DomainError`; `git grep -n -E "0\.15|0\.035|0\.08" -- src/pocketquant/core/domain/strategy | wc -l` prints `0`.

### Task 03.5 — Backtest-path test with the seeded spec

**Goal:** hitnrun2 runs end to end through the real backtest path, and the cost it filters on comes from the stored symbol spec.

**Target files and symbols:** `tests/backtest_test/engine/test_hitnrun2_backtest.py` (`test_hitnrun2_backtest_takes_its_cost_from_the_symbol_spec`).

**Steps:**
1. Create the test file. Imports (paths as in `tests/backtest_test/engine/test_triple_screen_backtest.py:1-31`): `from pocketquant.core.common.constants import COLLECTION_BARS`; `from pocketquant.core.common.time.simulation import clear_simulation_time`; `from pocketquant.core.domain.bar.entities import Bar`; `from pocketquant.core.domain.shared.enums import Interval`; `from pocketquant.core.domain.symbol import ContractSpec, Symbol`; `from pocketquant.core.infra.persistence.mongodb import Database`; `from pocketquant.core.infra.persistence.repositories.backtest_repository import BacktestRepository`; `from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository`; `from pocketquant.core.infra.persistence.symbol_lookup_helper import _CACHE`; `from pocketquant.engine.backtest.backtest_command_service import RunBacktestCommand`; `from tests.backtest_test.test_backtest_single_run_direct_task import _cmd_svc, _execution`.
2. Module constants: `_SYM = "HNR2TEST:BINANCE"`, `_T0 = datetime(2026, 1, 1, tzinfo=UTC)`, `_SPEC = ContractSpec(commission_per_contract=0.035, spread=0.08)` with the comment `# Gold's seeded costs: 0.15 per round trip.`, and the rows `_DEEP = (99.6, 98.0, 99.5)`, `_FLAT = (100.1, 99.9, 100.0)`, `_BREAK = (100.0, 99.0, 99.2)` as `(high, low, close)`.
3. `_bars()` builds `shape = [_DEEP] * 3 + ([_FLAT] * 5 + [_BREAK] + [_DEEP] * 3) * 4` and returns `Bar(symbol=_SYM, interval=Interval.MINUTE_1, datetime=_T0 + timedelta(minutes=i), open=c, high=h, low=lo, close=c, volume=1.0, tick_count=1)` per row. Comment above it: `# Four cycles: each break closes below the last five lows with the stop 0.99 under the entry, and the next deep bar stops the trade out.`
4. `async def _cleanup(database)`: delete `bars` and `symbols` documents with `{"symbol": _SYM}`, then `_CACHE.clear()` with the comment `# A miss cached by another test would hide the seeded spec.`
5. An autouse fixture `_reset_sim_time` exactly as in `test_triple_screen_backtest.py:39-43`.
6. The test, `@pytest.mark.asyncio`, parametrized `("min_cost_multiple", "trades")` over `(3.0, 4)` and `(1000.0, 0)`: `await _cleanup(database)`; in `try`: `await SymbolRepository(database).upsert(Symbol.create(symbol=_SYM, contract_spec=_SPEC))`; insert `[b.to_mongo() for b in _bars()]` into `COLLECTION_BARS`; `run_id, config = await _cmd_svc(database).run(RunBacktestCommand(strategy_id="hitnrun2", symbol=_SYM, intervals=["1m"], start_date=_T0, end_date=_T0 + timedelta(minutes=60), slippage_bps=0, commission_bps=0, parameters={"entry_lookback_bars": 5, "sl_lookback_bars": 8, "tp_lookback_bars": 3, "min_cost_multiple": min_cost_multiple}))`; `await _execution(database).execute_and_persist(run_id, config)`; load the run with `BacktestRepository(database).get(run_id)`; assert it is not `None`, `run.status == "finished"`, `run.metrics.total_trades == trades`; in `finally`: `await _cleanup(database)`. Comment above the parametrize: `# With the seeded spec the round trip is 0.15, so a multiple of 1000 skips every entry; under LINEAR_SPEC it would cost 0 and all four would trade.`
7. `uv run ruff format tests/backtest_test/engine/test_hitnrun2_backtest.py`.

**Success criteria:** both cases pass: 4 trades at the multiple 3 and 0 trades at 1000.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_hitnrun2_backtest.py -q 2>&1 | tail -1` contains `2 passed` and not `failed` or `error`.

### Task 03.6 — CLOSE

**Goal:** gates hold, one code commit, `develop` CI green.

**Target files and symbols:** all files of this phase.

**Steps:**
1. `uv run python -m pytest tests/core_test/unit/domain/strategy tests/backtest_test/engine -q 2>&1 | tail -1` contains `passed` and not `failed` or `error`.
2. GATES with the pyright line `uv run pyright src tests/core_test/unit/domain/strategy/test_hitnrun2.py tests/backtest_test/engine/test_hitnrun2_backtest.py`. FULLSUITE.
3. `git add` the four code and test files; commit `feat(strategy): add the hitnrun2 strategy with a cost filter`; record `code_sha=<git rev-parse HEAD>`; push `develop`.
4. `sleep 15`, then poll the CLOSE command every 60 s until `status` is `completed`.

**Success criteria:** CI `success` on the code commit.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to the recorded `code_sha`.

### Task 03.7 — Report and commit

**Goal:** the Track B code record is on `origin/develop`.

**Target files and symbols:** `R/phase-03-hitnrun2-strategy.md`.

**Steps:**
1. Write the report: entry-gate outputs; the three Task 03.1 lines and the owner's words in English; Task 03.2 outputs; the expected red; every Verify output; GATES and FULLSUITE tail lines; any metric-ceiling commit; `code_sha=` and the CI run id; last line `Result: PASS`.
2. Commit `docs(plans): record the hitnrun2 strategy phase` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-03-hitnrun2-strategy.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

`git revert <code_sha>` on `develop` and push; the registry holds `triple_screen` only again. Nothing reaches prod before Phase 04.

## Report

`R/phase-03-hitnrun2-strategy.md`, as in Task 03.7.

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

=== FILE: phase-04-hitnrun2-release.md ===
---
phase: 4
title: "Track B release: develop:master, deploy, post-checks"
status: pending
priority: P2
effort: 0.5h + CI time
dependencies: [3]
---

# Phase 04: Track B release: develop:master, deploy, post-checks

## Goal

Prod runs the hitnrun2 code: `master` equals `develop`, the master pipeline deployed it, prod lists `hitnrun2`, live trading is still off in the trader, and the three existing paper subscriptions run again after the roll.

## Context

- Release path (`docs/deployment.md`, "Branches", "Deploy", "Verify"): a fast-forward push `develop:master`; the master pipeline tests, builds, deploys with `deploy/vps/10-deploy.sh` and verifies with `11-verify.sh`; a green run needs no extra check. The roll replaces `api`, `worker` and `trader` one at a time, so the trader re-warms the three paper subscriptions (R5).
- `origin/master` is `684e2ab1` and `origin/develop` is `00272823` at plan time; the four commits between them touch only `plans/`, so the deployed image predates them. The rollback therefore uses the image tag read from the running api container, not `origin/master`.
- Live flag: api and worker pin `EXNESS_LIVE_TRADING: "false"`; the trader reads `.env` (`deploy/compose.prod.yml:73-112`). LIVECHK reads it inside the trader.
- Strategy list route: `GET /api/v1/backtest/strategies` returns `list(STRATEGY_REGISTRY.keys())` (`src/pocketquant/app/routes/backtest.py:41-43`).
- Reconcile failures log `reconcile.load_failed` (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:186-189`).

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-03-hitnrun2-strategy.md`.
2. `git fetch -q origin && git log --oneline origin/master..origin/develop -- src | wc -l` prints a number `>= 1`.
3. KEY, then LIVECHK prints `trader_live=False`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 04 after <UTC time>
```

## Files

- Repo: `R/phase-04-hitnrun2-release.md` only.
- Prod writes: the release push (Task 04.3).

## Tasks

### Task 04.1 — Pre-release state

**Goal:** the rollback image, memory baseline and subscription state are recorded.

**Target files and symbols:** VPS containers; prod `subscriptions`.

**Steps:**
1. SSH `docker ps --filter name=pocketquant-prod-api --format "{{.Image}}"`; record the first line as `prev_image=<image>`.
2. FREE; record as `free_before=<line>`.
3. SUBS3; record its line.

**Success criteria:** `prev_image=` ends with `:sha-` and 7 hex characters; `free_before=` exists; SUBS3 prints `existing_subs=3 running=3`.

**Verify:** `grep -c -E "^prev_image=\S+:sha-[0-9a-f]{7}$" plans/261109-1349-1m-strategy-evidence/reports/phase-04-hitnrun2-release.md` prints `1` and the SUBS3 output is `existing_subs=3 running=3`.

### Task 04.2 — [ASK] release

**Goal:** the owner approves the release.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Release hitnrun2 to prod? It ships one new strategy file and one registry entry (`<git log --oneline origin/master..origin/develop -- src tests | wc -l>` code commits). No data migration. Live stays off (`trader_live=False`). The roll restarts the trader, so the three paper subscriptions warm up again. Rollback: re-roll `<prev_image tag>` and revert the commit." Lead with `Recommended: yes`, reason: develop CI is green and the change is additive.
2. Record `release_answer=<reply>`. Only an explicit yes continues.

**Success criteria:** the report holds the owner's yes.

**Verify:** `grep -c -i -E "^release_answer=.*\byes\b" plans/261109-1349-1m-strategy-evidence/reports/phase-04-hitnrun2-release.md` prints `1`.

### Task 04.3 — Release push and master run

**Goal:** `master` equals `develop` and the master pipeline succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. LIVECHK prints `trader_live=False`.
2. Record `pushed_at=<UTC ISO now>`.
3. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released` prints `released`.
4. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Record the run id.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/develop`.

### Task 04.4 — Post-deploy checks

**Goal:** prod serves hitnrun2, containers are healthy, live is off, the reconcile loop loaded every subscription, and the existing paper subscriptions run.

**Target files and symbols:** prod api, trader container, `subscriptions`.

**Steps:**
1. PRODPY with HEADER plus `import json` / `import urllib.request` / `print("strategies=" + ",".join(sorted(json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies")))))`.
2. SSH `docker ps --format "{{.Names}} {{.Status}}"` and record the lines for `pocketquant-prod-api`, `-worker`, `-trader`.
3. LIVECHK.
4. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <pushed_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`; then `grep -c "reconcile.load_failed" .cache/trader.log`.
5. Wait until at least 3 minutes after the master run completed, then SUBS3.
6. FREE as `free_after=<line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `strategies=hitnrun2,triple_screen`; three app containers `Up` and `(healthy)`; `trader_live=False`; `0` load failures; `existing_subs=3 running=3`.

**Verify:** the step 1 output is `strategies=hitnrun2,triple_screen`; the step 2 lines for api, worker and trader each contain `Up` and `(healthy)`; LIVECHK prints `trader_live=False`; the `grep -c` prints `0`; SUBS3 prints `existing_subs=3 running=3`.

### Task 04.5 — Report and commit

**Goal:** the release record is on `origin/develop`.

**Target files and symbols:** `R/phase-04-hitnrun2-release.md`.

**Steps:**
1. Write the report: entry-gate outputs; `prev_image=`, `free_before=`, SUBS3 before; `release_answer=`; `pushed_at=`, master run id and sha; every post-check output; `free_after=`; last line `Result: PASS`.
2. Commit `docs(plans): record the hitnrun2 release` and push `develop` (md-only, no CI).

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-04-hitnrun2-release.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

Each step is an [ASK]. (1) SSH `cd /opt/pocketquant && IMAGE_TAG=<the tag part of prev_image> bash deploy/vps/10-deploy.sh` (`deploy/vps/10-deploy.sh:9`). (2) `git revert <code_sha>` on `develop`, push, and later release the revert like Task 04.3. No data changes to undo; backtest runs of hitnrun2 would stay as records. Record `free -m` after a rollback.

## Report

`R/phase-04-hitnrun2-release.md`, as in Task 04.5.

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
title: "Track B: two hitnrun2 backtests, table, one verdict"
status: pending
priority: P2
effort: "0.5h work + about 1h run wall time"
dependencies: [4]
---

# Phase 05: Track B: two hitnrun2 backtests, table, one verdict

## Goal

Two finished 12-month hitnrun2 runs on `XAUUSD:EXNESS` with `intervals=["1m"]` (A3): `B1` with the default `min_profit_pct` 0.02 and `B2` with the owner's lower value, in the same table format as Track A, with one gate verdict for the set `hitnrun2/1m`.

## Context

- Same window, costs, one-at-a-time rule, time guard, 1800 s ask and 3 h stop as Phase 02 (plan.md Design rules). `B1` sends `parameters={}` so every default applies, including the owner's `min_cost_multiple` default; `B2` sends only `min_profit_pct`.
- The lower value is `min_profit_pct_low=` in `R/phase-03-hitnrun2-strategy.md`.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-04-hitnrun2-release.md`.
2. `grep -c "^strategies=hitnrun2,triple_screen$" plans/261109-1349-1m-strategy-evidence/reports/phase-04-hitnrun2-release.md` prints `1`.
3. `grep -c -E "^min_profit_pct_low=" plans/261109-1349-1m-strategy-evidence/reports/phase-03-hitnrun2-strategy.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 05 after <UTC time>
```

## Files

- Repo: `R/phase-05-hitnrun2-backtests.md` only.
- Prod writes: two `backtest_runs` with their orders and trades.

## Tasks

### Task 05.1 — Two runs, one at a time

**Goal:** `B1` and `B2` finished, each with a `free -m` line, and an owner answer for any run above 1800 s.

**Target files and symbols:** RUNBT; `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{run_id}`.

**Steps:**
1. KEY. Write RUNBT to `.cache/f.py`, then replace the line `MIN_PROFIT_PCT_LOW = None` with `MIN_PROFIT_PCT_LOW = <value of min_profit_pct_low>`. Check: `grep -c "^MIN_PROFIT_PCT_LOW = 0\." .cache/f.py` prints `1`.
2. For `<label>` in `B1`, `B2`, follow Phase 02 Task 02.1 steps 2.1-2.6 and step 3 exactly, with `B` labels and this phase's report and `--from 05` in any `NOT_YET` resume line.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two `status=finished` lines and two `free_after_run=` lines; a `cost_ask=` yes covering `B2` if `B1` ran above 1800 s.

**Verify:** `grep -c -E "^run=B[12] id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md; grep -c -E "^free_after_run=B[12] " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `2` then `2`.

### Task 05.2 — Run table

**Goal:** the two runs in the Phase 02 table format.

**Target files and symbols:** the phase report.

**Steps:**
1. Write the Phase 02 Task 02.2 header and one row per label, e.g. `| B1 | hitnrun2 | 1m | defaults | <id> | ... |` and `| B2 | hitnrun2 | 1m | min_profit_pct=<value> | <id> | ... |`.

**Success criteria:** 2 rows.

**Verify:** `grep -c -E "^\| B[12] \| hitnrun2 \| 1m \| " plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `2`.

### Task 05.3 — Gate verdict

**Goal:** one `verdict:` line for `hitnrun2/1m`, computed by the same VERDICT script as Track A.

**Target files and symbols:** VERDICT; prod `backtest_runs`.

**Steps:**
1. KEY. Write VERDICT to `.cache/f.py` unchanged.
2. PRODPY-ARG `hitnrun2/1m B1=<B1 id> B2=<B2 id>`; append all output lines under the table.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** one `verdict:` line for the set.

**Verify:** `grep -c -E "^verdict: (pass|fail) set=hitnrun2/1m run=B[12] pf=[0-9.]+ trades=[0-9]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md` prints `1`.

### Task 05.4 — Report and commit

**Goal:** the Track B record is on `origin/develop`.

**Target files and symbols:** `R/phase-05-hitnrun2-backtests.md`.

**Steps:**
1. Make sure the report holds: entry-gate outputs; run lines, `free_after_run=` lines, any `cost_ask=`; the table; the VERDICT output; last line `Result: PASS`.
2. Commit `docs(plans): record the hitnrun2 backtests` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

Nothing to undo: the two runs stay as evidence.

## Report

`R/phase-05-hitnrun2-backtests.md`, as in Task 05.4.

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
title: "Paper start for passing sets only"
status: pending
priority: P2
effort: 0.5h
dependencies: [2, 5]
---

# Phase 06: Paper start for passing sets only

## Goal

Exactly one running paper subscription per set whose verdict is `pass`, each a copy of its passing run's strategy, intervals and parameters on the pooled paper account; none for a failing set; the three existing subscriptions untouched.

## Context

- D4: only passing sets go to paper; a failing set is never put on paper "to see what happens" (advice, "What you shouldn't do").
- The passing run of a set is the `run=` label in its `verdict: pass` line (VERDICT picks the passing run with the highest `profit_factor`). Its id is on the `run=<label> id=<id> status=finished` line of the same report.
- The script reads `strategy_code`, `intervals` and `parameters` from that `backtest_runs` document (`src/pocketquant/core/domain/backtest/entities.py:61-78`), so the subscription matches the run exactly.
- Create: `POST /api/v1/strategies/{code}/subscriptions` with `{symbol, intervals, parameters, broker}` (`src/pocketquant/app/routes/strategy.py:55`); start: `POST /api/v1/subscriptions/{id}/start` (`:90`); both need `X-Admin-Token`. Pattern: earlier Phase 16 Task 16.5. Paper uses the symbol spec commission (`src/pocketquant/core/infra/brokers/broker_factory.py:41-45`); all paper subscriptions share one pooled paper broker per spec (`src/pocketquant/engine/strategy/strategy_app_service.py:965`). The Exness `entries_paused` safeguard gates only the Exness broker (`src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:231-243`).
- Uniqueness: one subscription per `(strategy_code, symbol, intervals_key)`; the 1m keys differ from the three existing keys.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-05-hitnrun2-backtests.md`.
2. `grep -h "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md | wc -l` prints `3`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 06 after <UTC time>
```

## Files

- Repo: `R/phase-06-paper-start.md` only.
- Prod writes: one subscription created and started per passing set.

## Tasks

### Task 06.1 — List the passing sets

**Goal:** the paper sets are exactly the passing sets.

**Target files and symbols:** the Phase 02 and Phase 05 reports.

**Steps:**
1. `grep -h "^verdict: pass " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md`.
2. For each line, take `set=` and `run=<label>`, and look up the id on that report's `run=<label> id=<id> status=finished` line. Record one line `paper_set=<set> run=<label> run_id=<id>` per passing set.
3. If there is no passing set, record `paper_sets=none`, skip Tasks 06.2-06.3, and write the report with `Result: PASS`.

**Success criteria:** the number of `paper_set=` lines equals the number of `verdict: pass` lines; or `paper_sets=none` when it is zero.

**Verify:** `p=$(grep -h "^verdict: pass " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-hitnrun2-backtests.md | wc -l); q=$(grep -c "^paper_set=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md); n=$(grep -c "^paper_sets=none$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md); echo "$p $q $n"` prints `0 0 1`, or `<k> <k> 0` with `k >= 1`.

### Task 06.2 — Create and start one subscription per passing set

**Goal:** each passing set runs on paper with its passing run's parameters.

**Target files and symbols:** prod `subscriptions`, `backtest_runs`; the two routes above.

**Steps:**
1. KEY. Write `.cache/f.py`: HEADER plus
```python
import json
import sys
import time
import urllib.request

API = "http://localhost:41921/api/v1"
token = s.admin_token.get_secret_value()


def post(path, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
    )
    return json.load(urllib.request.urlopen(req))


run = db.backtest_runs.find_one({"_id": sys.argv[1]})
code, intervals, params = run["strategy_code"], run["intervals"], run.get("parameters") or {}
key = ",".join(intervals)
found = db.subscriptions.find_one({"strategy_code": code, "symbol": "XAUUSD:EXNESS", "intervals_key": key})
if found and (found.get("parameters") or {}) != params:
    print(f"conflict={found['_id']} parameters={json.dumps(found.get('parameters'), sort_keys=True)}")
    sys.exit(3)
sid = found["_id"] if found else post(f"/strategies/{code}/subscriptions", {
    "symbol": "XAUUSD:EXNESS", "intervals": intervals, "parameters": params, "broker": "paper",
})["id"]
post(f"/subscriptions/{sid}/start", {})
time.sleep(30)
d = db.subscriptions.find_one({"_id": sid})
print(f"paper_sub={code}/{key} id={sid}")
print(f"state={d['desired_state']}/{d['actual_state']} broker={d['broker']} intervals_key={d['intervals_key']} parameters={json.dumps(d['parameters'], sort_keys=True)}")
```
2. For each `paper_set=` line in order: skip it if the report already holds `paper_sub=<set> id=`; otherwise record `paper_started_at=<set> <UTC ISO now>` just before the run, then PRODPY-ARG `<run_id>` and append both output lines. A `conflict=` line is a failed Verify (a document for that set exists with other parameters; it is not this plan's).
3. Record `paper_end=<latest paper_started_at + 14 days, UTC ISO>`.

**Success criteria:** every passing set has `state=running/running broker=paper` with the run's intervals and parameters.

**Verify:** for each `paper_set=` line, the report holds `paper_sub=<set> id=<id>` followed by a line matching `^state=running/running broker=paper intervals_key=<intervals of the set> parameters=\{.*\}$`, and `grep -c "^paper_end=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md` prints `1`.

### Task 06.3 — Existing subscriptions untouched, memory

**Goal:** A6 holds after the creates.

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. SUBS3; record its line.
2. FREE as `free_after_paper_start=<line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `existing_subs=3 running=3`.

**Verify:** the SUBS3 output is `existing_subs=3 running=3`.

### Task 06.4 — Report and commit

**Goal:** the paper start record is on `origin/develop`.

**Target files and symbols:** `R/phase-06-paper-start.md`.

**Steps:**
1. Write the report: entry-gate outputs; `paper_set=` lines or `paper_sets=none`; per set `paper_started_at=`, `paper_sub=`, `state=`; `paper_end=`; SUBS3; `free_after_paper_start=`; last line `Result: PASS`.
2. Commit `docs(plans): record the paper start` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

[ASK] each step. Stop a new subscription (`POST /api/v1/subscriptions/<id>/stop`), wait until `actual_state` is `stopped`, then `DELETE /api/v1/subscriptions/<id>`, both from a PRODPY script with the admin token header. Only the ids recorded on `paper_sub=` lines; never the three existing subscriptions.

## Report

`R/phase-06-paper-start.md`, as in Task 06.4.

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
title: "Paper observation checkpoints and reconciliation"
status: pending
priority: P2
effort: "14 days wall time, about 10 min per checkpoint"
dependencies: [6]
---

# Phase 07: Paper observation checkpoints and reconciliation

## Goal

Every paper subscription runs at least 14 days with its error and stale-bar events counted over the whole window without a gap, and each set has one reconciliation line with the four A5 columns against its passing backtest run.

## Context

- A5 columns: trades per trading day, average commission per trade, exit-reason mix, `strategy_on_bar_error` and stale-bar event counts. Paper trades are read by `trades.run_id = <subscription id>` (pooled account). Backtest trades are `backtest_trades` with `run_id = <passing run id>`; both use the `Trade` shape with `commission`, `exit_reason`, `exit_time` (`src/pocketquant/core/domain/trading/value_objects.py:111-131`).
- A trading day is a UTC date with at least one `EXNESS_XAUUSD` calendar trading minute; both sides use the same definition. The paper window of a set is `[paper_started_at, paper_started_at + 14 days)`; the backtest window is `[2025-11-09, 2026-11-09)`.
- No profit threshold (D4). The lines are a record, not a judgment. Average commission per trade differs with position size, and the pooled paper balance differs from the 10 000 backtest capital (R7).
- Log events and retention: plan.md Design rules, "Error evidence". `docker compose logs --timestamps --no-log-prefix` prints each line's RFC 3339 time as its first token.
- If Phase 06 recorded `paper_sets=none`, this phase records `reconcile=none` and passes.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-06-paper-start.md`.
2. `grep -c -E "^(paper_end=|paper_sets=none$)" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 07 after <UTC time>
```

## Files

- Repo: `R/phase-07-paper-reconcile.md` only.
- Prod: read-only.

## Tasks

### Task 07.0 — No paper set

**Goal:** a plan with no passing set closes cleanly.

**Target files and symbols:** the Phase 06 report.

**Steps:**
1. If `R/phase-06-paper-start.md` holds `paper_sets=none`: write `reconcile=none` and the last line `Result: PASS` into this phase's report, commit and push, and skip Tasks 07.1-07.3.

**Success criteria:** `reconcile=none` exists exactly when `paper_sets=none` exists.

**Verify:** `echo "$(grep -c "^paper_sets=none$" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md) $(grep -c "^reconcile=none$" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md 2>/dev/null || echo 0)"` prints `1 1` or `0 0`.

### Task 07.1 — Log checkpoint (repeat until the window ends)

**Goal:** error and stale-bar events of every paper subscription are counted for contiguous slices of the window.

**Target files and symbols:** the trader container logs.

**Steps:**
1. `SINCE` = the `to` value of the last `logcheck=` line in this report, or the earliest `paper_started_at=` of Phase 06 if none. `END` = `paper_end=` of Phase 06. `TO` = the earlier of the current UTC time (`date -u +%Y-%m-%dT%H:%M:%SZ`) and `END`. If `SINCE` equals `END`, skip to Task 07.2.
2. KEY. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --no-log-prefix --timestamps trader 2>&1 | head -1 | cut -d" " -f1`; record the output as `FIRST`.
3. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --no-log-prefix --since <SINCE> --until <TO> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`.
4. For each `paper_sub=<set> id=<sid>` line of Phase 06: `e=$(grep "strategy_on_bar_error" .cache/trader.log | grep -c "strategy_id=<sid>")`; `t=$(grep "strategy.entry_skipped" .cache/trader.log | grep "reason=stale" | grep -c "subscription_id=<sid>")`; append `logcheck=<SINCE>..<TO> first=<FIRST> sub=<sid> on_bar_error=<e> stale=<t>`.
5. `rm -f .cache/ssh/vps_key`. If `TO` is before `END`: commit and push the report, then end with `NOT_YET: paper window open until <END>` and `Resume: ... --from 07 after <the earlier of TO + 2 days and END>`.

**Success criteria:** each checkpoint's retained log starts at or before its `SINCE` (no gap), and the checkpoints chain from the earliest start to `paper_end`.

**Verify:** for the lines just appended, the first 19 characters of `first=` are less than or equal to the first 19 characters of `SINCE` (string comparison of `YYYY-MM-DDTHH:MM:SS`), and `grep -c "^logcheck=" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md` grew by the number of paper subscriptions.

### Task 07.2 — Window complete

**Goal:** reconciliation starts only after every subscription ran 14 days and the counted slices cover the whole window.

**Target files and symbols:** this report.

**Steps:**
1. Check that the current UTC time is at or after `paper_end`, and that the last `logcheck=` line ends with `..<paper_end>`.
2. For each `<sid>`: `grep -E "^logcheck=.* sub=<sid> " <this report> | sed -E 's/.*on_bar_error=([0-9]+) stale=([0-9]+)$/\1 \2/' | awk '{e+=$1; t+=$2} END {print "events sub=<sid> on_bar_error=" e+0 " stale=" t+0}'`; append the output.

**Success criteria:** the window is complete and one `events` line exists per subscription.

**Verify:** `grep -c "^events sub=" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md` equals `grep -c "^paper_sub=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md`, and the last `logcheck=` line's `to` equals the `paper_end=` value.

### Task 07.3 — Reconciliation per set

**Goal:** one line per set with the four A5 columns, paper against backtest.

**Target files and symbols:** prod `trades`, `backtest_trades`.

**Steps:**
1. KEY. Write `.cache/f.py`: HEADER plus
```python
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta

from pocketquant.core.domain.symbol.value_objects import CALENDAR_EXNESS_XAUUSD
from pocketquant.core.infra.calendars.trading_calendar_factory import TradingCalendarFactory

SET, SID, RUN, ERRORS, STALE = sys.argv[1], sys.argv[2], sys.argv[4], sys.argv[5], sys.argv[6]
START = datetime.fromisoformat(sys.argv[3].replace("Z", "+00:00"))
END = START + timedelta(days=14)
cal = TradingCalendarFactory(None).get(CALENDAR_EXNESS_XAUUSD)


def side(trades, start, end):
    days = len({m.date() for m in cal.trading_minutes(start, end)})
    n = len(trades)
    avg = sum(t.get("commission") or 0.0 for t in trades) / n if n else 0.0
    mix = Counter(t.get("exit_reason") or "none" for t in trades)
    mix_s = ",".join(f"{k}:{v / n:.2f}" for k, v in sorted(mix.items())) if n else "none"
    return f"{n / days:.2f}", f"{avg:.4f}", mix_s


paper = list(db.trades.find({"run_id": SID, "exit_time": {"$gte": START, "$lt": END}}, {"commission": 1, "exit_reason": 1}))
bt = list(db.backtest_trades.find({"run_id": RUN}, {"commission": 1, "exit_reason": 1}))
p = side(paper, START, END)
b = side(bt, datetime(2025, 11, 9, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC))
print(f"paper_trades={len(paper)} backtest_trades={len(bt)}")
print(
    f"reconcile: set={SET} sub={SID} run={RUN} trades_per_day=paper:{p[0]}/backtest:{b[0]} "
    f"avg_commission=paper:{p[1]}/backtest:{b[1]} exit_mix=paper:{p[2]}/backtest:{b[2]} "
    f"on_bar_error={ERRORS} stale={STALE}"
)
```
2. For each paper set, PRODPY-ARG `<set> <sid> <paper_started_at of the set> <run_id of the set> <on_bar_error from its events line> <stale from its events line>`; append both output lines.
3. SUBS3; record its line. `rm -f .cache/ssh/vps_key`.

**Success criteria:** one complete `reconcile:` line per paper set; the existing subscriptions still run.

**Verify:** `grep -c -E "^reconcile: set=\S+ sub=\S+ run=\S+ trades_per_day=paper:[0-9.]+/backtest:[0-9.]+ avg_commission=paper:[0-9.]+/backtest:[0-9.]+ exit_mix=paper:\S+/backtest:\S+ on_bar_error=[0-9]+ stale=[0-9]+$" plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md` equals `grep -c "^paper_sub=" plans/261109-1349-1m-strategy-evidence/reports/phase-06-paper-start.md`, and SUBS3 prints `existing_subs=3 running=3`.

### Task 07.4 — Report and commit

**Goal:** the reconciliation record is on `origin/develop`.

**Target files and symbols:** `R/phase-07-paper-reconcile.md`.

**Steps:**
1. Make sure the report holds: entry-gate outputs; every `logcheck=` line; the `events` lines; the reconcile output; SUBS3; last line `Result: PASS`.
2. Commit `docs(plans): record the paper reconciliation` and push.

**Success criteria:** the report ends with `Result: PASS` and is pushed.

**Verify:** `tail -1 plans/261109-1349-1m-strategy-evidence/reports/phase-07-paper-reconcile.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `Result: PASS` then `pushed`.

## Rollback

Nothing to undo: this phase only reads prod.

## Report

`R/phase-07-paper-reconcile.md`, as in Task 07.4.

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

=== FILE: phase-08-close.md ===
---
phase: 8
title: "Close: verdict per set, status, archive"
status: pending
priority: P2
effort: 0.5h
dependencies: [7]
---

# Phase 08: Close: verdict per set, status, archive

## Goal

One close report holds the six-run table, the three gate verdicts and the paper reconciliation; the plan has `status: completed` and sits in `plans/archive/`.

## Context

- D5: the plan ends at the reconciliation with a written verdict per set. The verdict of a set is its gate verdict (D4: the backtest decides); the reconciliation is attached as a record.
- Plan status: `ak plan update <id> --status completed` rewrites the `plan.md` front matter (`ak plan update --help`); the store lists plans as `pocketquant/<YYMMDD-HHMM>` (`ak plan list --json`). The repo's last close moved the directory with `git mv` (commit `00272823`).
- New paper subscriptions keep running after the close (stopping them is outside the confirmed prod writes); the report lists them for the owner.

## Entry gate

1. EG (1)-(3); the previous report is `R/phase-07-paper-reconcile.md`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 08 after <UTC time>
```

## Files

- Create: `R/phase-08-close.md`.
- Modify: `plan.md` front matter `status`.
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.

## Tasks

### Task 08.1 — Close report

**Goal:** the whole result reads in one file.

**Target files and symbols:** `R/phase-08-close.md`.

**Steps:**
1. Copy the four Track A table rows and the two Track B rows under one copy of the table header.
2. Copy the three `verdict:` lines verbatim.
3. Copy each `reconcile:` line, or `reconcile=none`.
4. For each set write `final: set=<set> verdict=<pass|fail> paper=<subscription id or none>`.
5. Write one line `open_paper_subscriptions=<comma-joined ids from paper_sub= lines, or none>` and the sentence: "These subscriptions keep running; stopping them is an owner decision."
6. Write the sentence: "One 12-month window and a fixed threshold; the sweep harness, DSR and PBO stay deferred."
7. Last line `Result: PASS`.

**Success criteria:** 6 table rows, 3 verdict lines, 3 final lines.

**Verify:** `grep -c -E "^\| (A[1-4]|B[12]) \| " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close.md; grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-08-close.md; grep -c "^final: set=" plans/261109-1349-1m-strategy-evidence/reports/phase-08-close.md` prints `6`, `3`, `3`.

### Task 08.2 — Status completed and archive

**Goal:** the plan is closed and archived.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/plan.md`, `plans/archive/`.

**Steps:**
1. `ak plan reindex`, then `ak plan update pocketquant/261109-1349 --status completed --no-interactive`. If the store does not know the id, edit the front matter line `status: pending` (or `in-progress`) to `status: completed` in `plan.md`.
2. `git add plans/261109-1349-1m-strategy-evidence && git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`.
3. `git commit -m "docs(plans): close and archive the 1m strategy evidence plan"`; push `develop`. Then `ak plan reindex`.

**Success criteria:** the archived plan has `status: completed`; the old path is gone; pushed.

**Verify:** `test -d plans/archive/261109-1349-1m-strategy-evidence && test ! -e plans/261109-1349-1m-strategy-evidence && grep -c "^status: completed$" plans/archive/261109-1349-1m-strategy-evidence/plan.md; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `1` then `pushed`.

## Rollback

`git revert` the close commit to move the plan back and reset its status.

## Report

`R/phase-08-close.md` (archived with the plan), as in Task 08.1.

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
