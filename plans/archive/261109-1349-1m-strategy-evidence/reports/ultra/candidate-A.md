=== FILE: plan.md ===
---
title: "1m strategy evidence: Triple Screen 1m entry and revived hitnrun2, backtest gate, paper reconcile"
description: "Backtest Triple Screen with a 1m entry screen and a revived hitnrun2 with a cost filter on 12 months of XAUUSD:EXNESS, gate each set on net profit_factor >= 1.2 and total_trades >= 100, paper-reconcile passing sets for 14 days, and close with a verdict per set."
status: pending
priority: P2
effort: "about 2d work + 14d paper window"
branch: develop
tags: [strategy, backtest, paper, 1m, triple-screen, hitnrun2, exness]
blockedBy: []
blocks: []
created: 2026-11-09
---

# 1m strategy evidence: Triple Screen 1m entry and revived hitnrun2

## Overview

The go-live plan waits for a strategy that clears a gate. This plan produces the 1m evidence. Track A backtests Triple Screen with a 1m entry screen and changes no code. Track B revives hitnrun2 on the current multi-interval contract with a cost filter, releases it, and backtests it. A backtest gate decides each set. Only passing sets run 14 days on paper, and paper only reconciles. The plan closes with a written verdict per set and moves to `plans/archive/`. Live trading stays disarmed throughout.

The plan is written for a downstream executor model. Every phase has ordered tasks with Goal, Target files, Steps, Success criteria and a mechanical Verify, and ends with the Failure Protocol block.

## Sources (read when a phase cites them)

- Fixed brief: `reports/evidence-packet.md`.
- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md`; interview record `plans/reports/advise-261109-1309-next-plan-state.md`.
- Rules: `CLAUDE.md`, `docs/governance/no-look-ahead-rules.md`, `docs/governance/documentation-rules.md`, `docs/code-standards.md`, `docs/deployment.md`, `README.md`.
- Format and recipes: `plans/261101-0843-stf-to-mtf-foundation/phase-16-backtests-and-paper-start.md` (run recipe, coverage check Task 16.1 and its amended pass rule, run table, 1800 s ask) and its report `plans/261101-0843-stf-to-mtf-foundation/reports/phase-16-backtests-and-paper-start.md`.
- Deleted hitnrun2: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, old tests `git show f3bb9e64^:tests/core_test/unit/domain/strategy/test_hitnrun2.py`.
- Context only, out of scope: `plans/handoffs/exness-only-runtime-undone-items-20261031-1302.md`.

## Owner decisions (interview 2026-11-09, fixed; do not reopen)

| # | Decision |
|---|---|
| D1 | The next plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Both tracks. Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. Track B: a dedicated 1m strategy. |
| D3 | Track B revives hitnrun2 (240-bar breakout, 480-bar SL extreme, 60-bar TP extreme, max loss 1%, min profit 2%) rewritten to the current multi-interval contract, with a cost filter that skips entries whose exit distance cannot cover the round-trip cost. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

## Confirmed assumptions (owner accepted every one)

- A1: Track A runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`.
- A2: Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s.
- A3: hitnrun2 runs as one interval, `intervals=["1m"]`.
- A4: The cost filter reads the cost from the symbol spec (`config.contract_spec`), never a hard-coded 0.15.
- A5: Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id` because the paper account is pooled.
- A6: The three existing Triple Screen paper subscriptions keep running and are not touched.

## Definitions used by every phase

- **Set.** A strategy plus its interval list, the word D2 uses: `ts-1m-5m-15m` (Triple Screen `1m,5m,15m`), `ts-1m-15m-1h` (Triple Screen `1m,15m,1h`), `hitnrun2-1m` (hitnrun2 `1m`). Three sets.
- **Run.** One backtest of a set with one parameter setting. Six runs: `r1`-`r4` (Track A, A1) and `r5`-`r6` (Track B, default and one lower `min_profit_pct`).
- **Gate (per run).** `gate=pass` when the run finished, `profit_factor >= 1.2` and `total_trades >= 100`; else `gate=fail`. `profit_factor` is already net of commission (commit `f37060aa`; `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:198-200`).
- **Verdict (per set).** `pass` when at least one run of the set has `gate=pass`, else `fail`. One `verdict:` line per set, three in total. Why per set and not per run: the unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)` (`src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:129-133`) allows exactly one subscription per set, which matches D4's "one paper subscription per passing set". When both runs of one set pass, the owner picks the parameters for paper (Phase 06 [ASK]).
- **Window.** Every run uses `start_date=2025-11-09T00:00:00`, `end_date=2026-11-08T23:59:00` (UTC), the latest 12 months before plan day. All six runs share it, so they are comparable. The stored `XAUUSD:EXNESS` 1m history starts 2025-10-21 (Phase 16 report, Task 16.1).
- **Trading day.** A UTC date with at least one stored `XAUUSD:EXNESS` 1m bar. The same rule counts backtest and paper days.

## Facts verified while planning (re-check only where a phase says so)

- The backtest route accepts a 1m entry for Triple Screen today: `check_strategy_inputs` needs strictly ascending intervals, each a multiple of the entry (`src/pocketquant/core/domain/strategy/services/__init__.py:39-47`), and Triple Screen needs exactly three (`triple_screen_strategy_service.py:48-49`).
- `StrategyConfig.contract_spec` defaults to `LINEAR_SPEC` (`src/pocketquant/core/domain/strategy/value_objects.py:42`). The backtest path sets it from the symbol (`src/pocketquant/engine/backtest/backtest_execution_service.py:101-102,111-119`). The trader path sets it in the reconcile loop (`src/pocketquant/engine/live/strategy_reconcile_app_service.py:154-156,171-177`), and prod DI passes the symbol lookup (`src/pocketquant/app/di/services.py:159-171`). The only other `StrategyConfig(` site is the validation probe in `check_strategy_inputs` (`services/__init__.py:63`), which uses `LINEAR_SPEC`. Phase 03 re-checks this and adds a backtest-path test.
- Gold spec seed: `multiplier=1.0`, `commission_per_contract=0.035`, `spread=0.08` (`scripts/seed_exness_symbols.py:41-48`). With multiplier 1.0 the per-contract fee is USD per oz, which is the price unit, so `commission_per_contract * 2 + spread` is the round trip in price units (0.15 for gold).
- A backtest that sends no `spread` takes `contract_spec.spread` (`backtest_execution_service.py:42-43`); the per-contract fee wins over `commission_bps` (`src/pocketquant/core/domain/trading/commission_model.py:25-28`).
- The old hitnrun2 (`f3bb9e64^`, lines 80-94) goes LONG when the close breaks below the previous 240-bar low and sets `sl = max(480-bar low, close * (1 - max_loss_pct))`, `tp = max(60-bar high, close * (1 + min_profit_pct))` (SHORT mirrors). So the TP distance is at least 2% of price, and the SL lands above a LONG entry whenever the close is also below the 480-bar low. The signed nearer-exit distance is then at most 0, so the D3 cost filter skips that entry. This changes how often the revived strategy trades compared with the old code; the gate will show the effect.
- Live warm-up replays 500 entry bars (`src/pocketquant/engine/strategy/strategy_app_service.py:55`), enough for the 480-bar SL window plus the decision bar.
- The engine context tests already use a 1m entry (`["1m","1h"]`), including backtest-equals-live at every boundary (`tests/backtest_test/test_higher_timeframe_context.py:259,270,283,410`). Phase 01 runs them.
- Paper trades carry `run_id = subscription_id` (`src/pocketquant/engine/live/live_trade_collector.py:37-39`); backtest trades go to `backtest_trades` with `run_id = backtest run id` (`src/pocketquant/engine/backtest/backtest_report_app_service.py:98-101`; `src/pocketquant/core/common/constants.py:14`). Both carry `commission` and `exit_reason` (`src/pocketquant/core/domain/trading/value_objects.py:83-103`).
- Error events: `strategy_on_bar_error strategy_id=<sid>` (`strategy_app_service.py:623`) and `strategy.entry_skipped reason=stale subscription_id=<sid>` (`strategy_app_service.py:633-649`).
- Trader logs are json-file, 10 MB x 3 files (`deploy/compose.prod.yml:16-20`), and a deploy replaces the container, so Phase 06 reads them daily and checks that each read is contiguous.
- No backtest cancel route exists (`src/pocketquant/app/routes/backtest.py`), so the 1800 s ask is taken after a run, before the next one starts.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in numeric order, one fresh worker per phase. File order is execution order. Phases never run in parallel, so no two phases own the same file at once.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`, Git Bash. Every Verify is one self-contained command run from there. The shell keeps no variables between commands. Give every SSH or poll command a 600000 ms tool timeout.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md` (R below means `plans/261109-1349-1m-strategy-evidence/reports`). Machine lines (`run=`, `gate`, `verdict:`, `existing_sub`, `paper=`, `daycheck`, `recon:`, `final:`) are written as plain lines at the start of a line, never inside a code block or a list. Each report ends with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase from 02 on: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) the phase-specific lines. A resumed phase may show its own task files as uncommitted, and `HEAD` may be ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Record the question intent and the answer in English in the report. Only an explicit yes (or the named option) counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. The plan's [ASK] points are: a run above 1800 s (Phases 02, 05); `contract_spec` not reaching the strategy when the fix needs an engine change (Phase 03); every `develop:master` push (Phase 04); the lower `min_profit_pct` value (Phase 05); both runs of one set passing (Phase 06); stopping the new paper subscriptions (Phase 06); any destructive prod action or any change outside the confirmed scope (any phase).
- **Search** uses `git grep` (`rg` is not installed in Git Bash): `git grep -n -E "<pattern>" -- <paths>`; counts pipe to `wc -l`.
- **WINDOW**: `uv run python -c "import datetime as d; t=d.datetime.now(d.UTC); m=t.hour*60+t.minute; print('window_ok=' + ('yes' if 45 <= m < 135 or 240 <= m < 1395 else 'no') + ' utc=' + t.strftime('%H:%M'))"`. A backtest may start only on `window_ok=yes` (00:45-02:15 or 04:00-23:15 UTC), so a run of up to 45 min stays clear of the 00:00 `sync_repair` and the 03:00 `sync_backfill` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:805-824`). On `window_ok=no` end with `NOT_YET: outside the backtest window` and a resume time at the next window start.
- **GATES**: `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0; `uv run ruff check src tests scripts` prints `All checks passed!`; `uv run pyright src <every touched test file>` prints `0 errors, 0 warnings, 0 informations`. If only the ratchet fails, raise its ceiling in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code metric ceiling` and say so in the report; never pad or split code to satisfy it.
- **FULLSUITE**: run `docker ps`; if it fails start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s. Then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. Pass: the tail line contains `4 failed` and `4 errors`, and the count prints `0` (baseline of the last archived plan, `plans/archive/261103-1741-1d-cascade-fold-and-small-fixes/reports/phase-04-daily-bar-check.md:27`). About 109 setup errors mean Docker is down, not a code failure.
- **CLOSE** (end of the code phase): GATES and FULLSUITE pass; commit (conventional, English, no AI references); push `develop` with the Ops recipe; then `sleep 15` and poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Pass: `conclusion` is `success` and `headSha` equals `git rev-parse HEAD`. Commits that touch only `**/*.md` or `plans/**` trigger no CI (`.github/workflows/cicd.yml:3-10`).
- **No plan ids**, phase numbers, decision codes or run labels in code, comments, test names, log events or commit messages.
- **Code** follows `CLAUDE.md`: no docstrings (a WHY goes in a `#` comment above the code), a flow reads in at most 3 files, a new class, flag, parameter or config key needs a real caller today, delete dead code in the same change, log level by frequency, repositories only in core, fastapi only in app. The strategy file has no logging.
- **Strategy-agnostic**: `git grep -n -i -E "hitnrun|triple[ _-]?screen" -- web/src src/pocketquant/app src/pocketquant/engine | wc -l` prints `0` (AGNOSTIC). Strategy names live only in their strategy file, their tests and the registry.
- **Secrets** never go on a command line, into a report or into the repo. Prod reads and admin calls run as a Python script inside the `api` container (PRODPY) and read secrets from `get_settings()`.
- **Failure Protocol**: each phase file carries the literal block at the end. A failed Verify stops the phase and goes to `kongming`; a `NOT_YET` exit does not.

## Ops recipe (phases cite these names)

- **KEY**: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`. Every phase that used the key ends with `rm -f .cache/ssh/vps_key`, also before a `NOT_YET` exit.
- **SSH** `<cmd>`: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'`.
- **COMPOSE** prefix on the VPS: `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env`; services `api`, `worker`, `trader`, `web`.
- **HEADER** (first lines of every PRODPY script): `from pymongo import MongoClient` / `from pocketquant.core.config import get_settings` / `s = get_settings()` / `db = MongoClient(str(s.mongodb_url))[s.mongodb_database]`. Scripts never print a secret.
- **PRODPY**: write the script to `.cache/f.py`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -o ServerAliveInterval=60 -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py'`.
- **PRODPY-ARG** `<args>`: the PRODPY command with ` <args>` appended after `python /tmp/f.py` inside the quotes.
- **LIVECHK**: write `.cache/live.py` with the two lines `from pocketquant.core.config import get_settings` / `print("trader_live=" + str(get_settings().exness_live_trading))`, then `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/live.py' < .cache/live.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/live.py trader:/tmp/live.py && docker compose -f compose.prod.yml --env-file .env exec -T trader python /tmp/live.py'`. Pass: exactly `trader_live=False`. It runs in `trader` because compose pins the flag off only for api and worker (`deploy/compose.prod.yml:83,99`).
- **FREE**: SSH `free -m | grep Mem:`; record it as the named line.
- **SUBSCHECK**: PRODPY with HEADER plus the lines below; save its output to `.cache/subs.txt` (append `> .cache/subs.txt` to the PRODPY command). It lists only the three existing Triple Screen paper subscriptions (A6).
```python
for d in db.subscriptions.find(
    {"strategy_code": "triple_screen", "intervals_key": {"$in": ["5m,15m,1h", "15m,1h,4h", "1h,4h,1d"]}}
).sort("intervals_key", 1):
    print(f"existing_sub id={d['_id']} intervals_key={d['intervals_key']} state={d['desired_state']}/{d['actual_state']} broker={d['broker']} parameters={sorted(d['parameters'].items())}")
```
  SUBSDIFF: `diff <(grep "^existing_sub " plans/261109-1349-1m-strategy-evidence/reports/phase-01-coverage-and-baseline.md) <(grep "^existing_sub " .cache/subs.txt) && echo subs_unchanged` prints `subs_unchanged`.
- **Push**: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`. A release is `develop:master` in the same command and is always an [ASK]. Every `gh` call carries `GH_TOKEN=$(gh auth token --user camping89)`. Never print a token.
- **Logs**: prod logs are console format with ANSI colours; strip with `sed 's/\x1b\[[0-9;]*m//g'` and grep `key=value`. `grep -c` prints `0` and exits 1 when nothing matches; the printed number is what counts.

## Shared scripts

**BTRUN** (`.cache/f.py`, run with PRODPY-ARG `<label>` to submit, `<label> <id>` to poll). It refuses to submit while another run is `started` (one run at a time), polls for at most 480 s per call so a call fits the 600 s tool timeout, and prints the gate. Before upload, replace `<LOW>` with `None` in Phase 02 and with the recorded `min_profit_low` value in Phase 05.

```python
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime

from pymongo import MongoClient

from pocketquant.core.config import get_settings

s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
LOW = <LOW>
TS = "triple_screen"
RUNS = {
    "r1": ("ts-1m-5m-15m", TS, ["1m", "5m", "15m"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "r2": ("ts-1m-5m-15m", TS, ["1m", "5m", "15m"], {"entry_type": "stop", "exit_mode": "strategy"}),
    "r3": ("ts-1m-15m-1h", TS, ["1m", "15m", "1h"], {"entry_type": "market", "exit_mode": "sl_tp"}),
    "r4": ("ts-1m-15m-1h", TS, ["1m", "15m", "1h"], {"entry_type": "stop", "exit_mode": "strategy"}),
    "r5": ("hitnrun2-1m", "hitnrun2", ["1m"], {"min_profit_pct": 0.02}),
    "r6": ("hitnrun2-1m", "hitnrun2", ["1m"], {"min_profit_pct": LOW}),
}
BASE = "http://localhost:41921/api/v1/backtest"
label = sys.argv[1]
set_name, code, intervals, params = RUNS[label]
if len(sys.argv) > 2:
    run_id = sys.argv[2]
else:
    busy = db.backtest_runs.count_documents({"status": "started"})
    if busy:
        print(f"busy={busy} run={label} not submitted")
        sys.exit(0)
    body = {
        "strategy_id": code, "symbol": "XAUUSD:EXNESS", "intervals": intervals,
        "start_date": "2025-11-09T00:00:00", "end_date": "2026-11-08T23:59:00",
        "parameters": params,
        "name": f"{code} {' '.join(intervals)} " + " ".join(f"{k}={v}" for k, v in params.items()),
    }
    req = urllib.request.Request(
        f"{BASE}/run", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Token": s.admin_token.get_secret_value()},
    )
    run_id = json.load(urllib.request.urlopen(req))["request_id"]
    print(f"run={label} set={set_name} id={run_id}", flush=True)
deadline = time.time() + 480
doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
while doc["status"] == "started" and time.time() < deadline:
    time.sleep(30)
    doc = json.load(urllib.request.urlopen(f"{BASE}/{run_id}"))
started = datetime.fromisoformat(doc["started_at"])
if doc["status"] == "started":
    age = datetime.now(UTC) - started.replace(tzinfo=UTC)
    print(f"still_running run={label} id={run_id} elapsed_s={int(age.total_seconds())}")
    sys.exit(0)
m = doc.get("metrics") or {}
elapsed = (datetime.fromisoformat(doc["completed_at"]) - started).total_seconds()
pf, trades = m.get("profit_factor"), m.get("total_trades")
ok = doc["status"] == "finished" and pf is not None and pf >= 1.2 and trades is not None and trades >= 100
print(
    f"run={label} set={set_name} id={run_id} status={doc['status']} elapsed_s={int(elapsed)} "
    f"trades={trades} pf={pf} return={m.get('total_return')} max_dd={m.get('max_drawdown')} "
    f"win={m.get('win_rate')} gate={'pass' if ok else 'fail'} error={doc.get('error_message')}"
)
```

**VERDICT** (local, `.cache/verdict.py`, run `uv run python .cache/verdict.py <report path>`). It reads the finished `run=` lines of one report and prints one `verdict:` line per set. It is the reusable gate snippet: Phases 02 and 05 use the same code.

```python
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
line = r"^run=(r\d) set=(\S+) id=\S+ status=finished elapsed_s=\d+ trades=(\S+) pf=(\S+) .* gate=(pass|fail) "
sets: dict[str, dict[str, str]] = {}
for label, set_name, trades, pf, gate in re.findall(line, text, re.M):
    sets.setdefault(set_name, {})[label] = f"{label}:pf={pf},trades={trades},gate={gate}"
for set_name, runs in sets.items():
    verdict = "pass" if any(r.endswith("gate=pass") for r in runs.values()) else "fail"
    print(f"verdict: {set_name} {verdict} " + " ".join(runs[k] for k in sorted(runs)))
```

## Phases

| # | Phase | Prod write | Depends on | Status |
|---|---|---|---|---|
| 01 | [Push the plan; no-look-ahead tests; spec, baseline and 1m coverage](./phase-01-coverage-and-baseline.md) | none | none | Pending |
| 02 | [Track A: four Triple Screen 1m backtests, table, verdicts](./phase-02-track-a-backtests.md) | 4 backtest runs | 01 | Pending |
| 03 | [Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI](./phase-03-hitnrun2-strategy.md) | none | 02 | Pending |
| 04 | [Track B release to master and post-deploy checks](./phase-04-release-hitnrun2.md) | release [ASK] | 03 | Pending |
| 05 | [Track B: two hitnrun2 backtests, table, verdict](./phase-05-track-b-backtests.md) | 2 backtest runs | 04 | Pending |
| 06 | [Paper for passing sets: create, 14 days of checks, reconcile](./phase-06-paper-reconcile.md) | 0-3 subscriptions | 02, 05 | Pending |
| 07 | [Written verdict per set, status completed, archive](./phase-07-verdicts-and-archive.md) | none | 06 | Pending |

Dependency graph: `01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07`. Track A (01-02) runs before any Track B code (advice: Track B starts only once Track A numbers exist). Paper (06) starts after the Track B release, so the release deploy cannot restart the trader in the middle of a paper window and drop its logs.

## Data flow

- Track A: Phase 01 reads prod `bars`, `symbols`, `subscriptions` (read-only) -> Phase 02 BTRUN posts `POST /api/v1/backtest/run` -> the api runs `BacktestExecutionService` with the symbol spec -> `backtest_runs.metrics` and `backtest_trades` -> `run=` lines -> VERDICT -> `verdict:` lines in R/phase-02.
- Track B: recovered code -> `HitNRun2StrategyService` reads `config.contract_spec` once at construction -> unit and backtest-path tests -> CI -> release -> Phase 05 BTRUN -> `verdict:` line in R/phase-05.
- Paper: passing set -> `POST /api/v1/strategies/{code}/subscriptions` + `/start` -> the trader's reconcile loop loads it with the symbol spec -> `trades` (`run_id` = subscription id) and trader logs -> daily `daycheck` lines -> RECON (`backtest_trades` vs `trades`) -> `recon:` lines -> Phase 07 `final:` lines.

## Acceptance criteria

| # | Criterion | Measured by |
|---|---|---|
| AC1 | Every run recorded with `profit_factor` and `total_trades` | R/phase-02 and R/phase-05 tables: 4 and 2 rows; every run line `status=finished` |
| AC2 | One verdict line per set | `grep -h -c "^verdict: " R/phase-02-*.md R/phase-05-*.md` prints `2` and `1` |
| AC3 | hitnrun2 on master with `intervals=["1m"]` and a `min_cost_multiple` filter reading `config.contract_spec` | Phase 03 tests (17 unit, 2 backtest-path) pass; Phase 04 master CI `success`; prod `GET /api/v1/backtest/strategies` lists `hitnrun2` |
| AC4 | The spec reaches the strategy in both paths | Phase 03 Task 03.1 greps and the trader test; the backtest-path test where a costly spec yields `total_trades == 0` |
| AC5 | One paper subscription per passing set, at least 14 days, four A5 columns | R/phase-06 `paper=` lines, `paper_days=` at least 14, `recon:` lines per set |
| AC6 | The three existing subscriptions untouched | SUBSDIFF prints `subs_unchanged` in Phases 02, 04, 05, 06 |
| AC7 | Live stays disarmed | LIVECHK `trader_live=False` in Phases 01, 04, 06 |
| AC8 | Plan closed and archived | `test -d plans/archive/261109-1349-1m-strategy-evidence` and its `plan.md` has `status: completed` |

## Test matrix

| Level | What | Where |
|---|---|---|
| Unit | hitnrun2 validation, windows, SL/TP, direction, position cap, fills, rejection, restore, cost filter from the spec, wrong-side stop | `tests/core_test/unit/domain/strategy/test_hitnrun2.py` (new, 17 tests) |
| Integration (backtest path, real Mongo) | the backtest hands the symbol's spec to hitnrun2: a free spec trades, a costly spec trades nothing | `tests/backtest_test/engine/test_hitnrun2_backtest.py` (new, 2 cases) |
| Integration (existing) | trader path loads the symbol spec; context rules hold for a 1m entry | `tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec`; `tests/backtest_test/test_higher_timeframe_context.py` |
| Full suite and CI | no regression | FULLSUITE; develop and master CI |
| End to end (prod) | 6 backtests; paper subscriptions; reconciliation | Phases 02, 05, 06 |

## Backwards compatibility and rollback

- No schema, index, route or config change. The registry gains one key (`hitnrun2`). Existing subscriptions, backtest runs and Triple Screen code are untouched.
- Prod gains six `backtest_runs` documents and their `backtest_trades`/`backtest_orders`, plus at most three paper subscriptions on the pooled paper account.
- Rollback per phase is in each phase file. Code rollback is `git revert` on `develop` plus a release [ASK]. A paper subscription is stopped then deleted, each step an [ASK].

## Risks

| # | Risk | L x I | Mitigation |
|---|---|---|---|
| R1 | A 1m run takes over 1800 s or presses memory in the api process, which shares the Mongo pool with the trader and three paper subscriptions (`app/routes/backtest.py:46-47`) | M x M | One run at a time (BTRUN `busy` guard), WINDOW rule, FREE after each run, owner ask above 1800 s, SUBSDIFF after the runs |
| R2 | 5m/15m/1h buckets missing for part of the window, so a run compares a shorter period | L x H | Phase 01 coverage check with the owner-approved Phase 16 rule; stop on a miss |
| R3 | The strategy does not get the symbol spec | L x H | Verified by reading (Facts); Phase 03 re-checks and adds a backtest-path test; [ASK] if a fix needs an engine change |
| R4 | The wrong-side SL rule and the cost filter cut hitnrun2 below 100 trades | M x M | A result, not a defect: the gate records it; the lower `min_profit_pct` run is the second data point |
| R5 | Two passing runs share one set, but the unique index allows one subscription | L x M | Phase 06 [ASK] for the parameters |
| R6 | Trader log rotation or a redeploy loses error evidence during paper | M x M | Daily `daycheck` with a contiguity check; a gap stops the phase |
| R7 | Pooled paper balance sizes positions differently from a 10 000 backtest, so commission per trade differs | H x L | Recorded as a known difference in the reconciliation; no threshold (D4) |
| R8 | A single 12-month window overfits | M x M | Accepted by the owner (DSR, PBO and sweeps are non-goals) |
| R9 | The metric ratchet fails on the new file | M x L | Raise the ceiling in its own commit (GATES) |

## Docs impact

None. The change adds a registry entry and a strategy file; strategy names and parameters live in code (`docs/governance/documentation-rules.md`, Line Test rule 1). No setup, command, route, config or architecture changes.

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions; archiving other plans; a second shifted backtest window.

## Unresolved

1. The definition "set = strategy plus intervals" is the planner's reading of D2 and D4, chosen because the unique subscription index allows one paper subscription per set. Each run still carries its own `gate=` value, so a per-run reading can be taken from the same tables.
2. The lower `min_profit_pct` value is not owner-decided; Phase 05 asks it.
3. D4 gives paper no threshold, so a non-zero error or stale count is recorded as a discrepancy and does not change a set's verdict. The owner can still act on it.

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

=== FILE: phase-01-coverage-and-baseline.md ===
---
phase: 1
title: "Push the plan; no-look-ahead tests; spec, baseline and 1m coverage"
status: pending
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

=== FILE: phase-02-track-a-backtests.md ===
---
phase: 2
title: "Track A: four Triple Screen 1m backtests, table, verdicts"
status: pending
priority: P2
effort: "about 2.5h wall time (4 runs at an estimated 20-25 min each)"
dependencies: [1]
---

# Phase 02: Track A: four Triple Screen 1m backtests, table, verdicts

## Goal

Four finished Triple Screen backtests on `XAUUSD:EXNESS` over the plan window (A1), run one at a time with the seeded costs (A2), recorded in the Phase 16 table format plus a `gate` column, and one `verdict:` line for each of the two sets.

## Context

- Runs (plan.md BTRUN): `r1` `1m,5m,15m` market/sl_tp, `r2` `1m,5m,15m` stop/strategy, `r3` `1m,15m,1h` market/sl_tp, `r4` `1m,15m,1h` stop/strategy. The body sends no `spread`, `commission_bps` or commission, so the symbol spec applies (`backtest_execution_service.py:42-43`; per-contract fee wins, `commission_model.py:25-28`). No code change: the route accepts a 1m entry today (plan.md Facts).
- Cost: a run is an asyncio task in the api process with no cap, sharing the live Mongo pool (`src/pocketquant/app/routes/backtest.py:46-60`). The 12-month 5m set took 234-273 s (Phase 16 report, run lines 1-2); 1m has five times the entry bars, so 20-25 min is an estimate, not a measurement. A2: owner ask when a run exceeds 1800 s. No cancel route exists, so the ask comes after the run and before the next one.
- Run status values `started`, `finished`, `failed` (`src/pocketquant/core/domain/backtest/entities.py:23`); BTRUN prints `still_running` while it polls.
- Do not change Triple Screen (non-goal).
- Ops names: plan.md Ops recipe; BTRUN and VERDICT: plan.md Shared scripts.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-01-coverage-and-baseline.md`.
2. `grep -c "^existing_sub " plans/261109-1349-1m-strategy-evidence/reports/phase-01-coverage-and-baseline.md` prints `3`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 02 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md`; local scratch `.cache/f.py`, `.cache/verdict.py`, `.cache/subs.txt` (not committed).
- Prod writes: four `backtest_runs` (and their `backtest_orders`, `backtest_trades`).

## Tasks

### Task 02.1 — Four backtests, one at a time

**Goal:** `r1`-`r4` finish, each followed by a memory reading; a run above 1800 s gets the owner's answer before the next run starts.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`.

**Steps:**
1. KEY. Write BTRUN from plan.md to `.cache/f.py` with `<LOW>` replaced by `None`.
2. For each label in `r1`, `r2`, `r3`, `r4`, in order:
   - If the report already has `run=<label> set=... status=finished`, skip the label.
   - If it has only `run=<label> set=<set> id=<id>`, poll: PRODPY-ARG `<label> <id>`.
   - Else run WINDOW; on `window_ok=no` run `rm -f .cache/ssh/vps_key` and exit `NOT_YET` (plan.md WINDOW). On `yes`, submit: PRODPY-ARG `<label>`. A `busy=` line means another run is `started`: wait 5 min and submit again, at most 6 times, then treat it as a failed Verify.
   - While the output's last line starts with `still_running`, run PRODPY-ARG `<label> <id>` again. Each call returns within about 8 min.
   - Append the `run=<label> set=<set> id=<id>` line and the final `run=` line to the report as plain lines.
   - FREE; append `free_after_run=<label> <Mem: line>`.
   - If the final line's `elapsed_s` is above `1800` and a later label remains, [ASK] (intent) "run <label> took <minutes> min; free -m after it: <line>; start the next 1m run?" `Recommended: yes`, reason: runs go one at a time, the paper subscriptions keep trading, and the memory line shows headroom. Record `cost_ask=<label> <reply>`. A non-yes ends the phase with `NOT_YET`.
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** four final `run=` lines with `status=finished`, four `free_after_run=` lines, and a `cost_ask=` line for every run above 1800 s that had a run after it. A `status=failed` line, or a run still `started` after 3 h of polling, is a failed Verify.

**Verify:** `grep -c -E "^run=r[1-4] set=\S+ id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c -E "^free_after_run=r[1-4] " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `4`.

### Task 02.2 — Run table

**Goal:** the four runs read side by side in the Phase 16 format plus the gate.

**Target files and symbols:** the phase report.

**Steps:**
1. Write a table `| # | set | intervals | entry_type | exit_mode | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |` with one row per run (`| r1 | ts-1m-5m-15m | 1m 5m 15m | market | sl_tp | ...`), values copied from the final `run=` lines (4 decimals for ratios).
2. Under it, two compare URLs: `https://pocketquant.xyz/backtest/compare?runs=<r1 id>,<r2 id>` and `https://pocketquant.xyz/backtest/compare?runs=<r3 id>,<r4 id>`.

**Success criteria:** 4 rows and 2 URLs.

**Verify:** `grep -c -E "^\| r[1-4] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `4` then `2`.

### Task 02.3 — Verdict lines

**Goal:** one `verdict:` line per Track A set, produced by the shared VERDICT code.

**Target files and symbols:** `.cache/verdict.py`; the phase report.

**Steps:**
1. Write VERDICT from plan.md to `.cache/verdict.py`.
2. `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md`; append its two lines to the report right under the table, as plain lines.

**Success criteria:** two lines, one per set, each `pass` or `fail` with both runs' values.

**Verify:** `grep -c -E "^verdict: (ts-1m-5m-15m|ts-1m-15m-1h) (pass|fail) r[1-4]:pf=\S+,trades=\S+,gate=(pass|fail) r[1-4]:pf=\S+,trades=\S+,gate=(pass|fail)$" plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2`.

### Task 02.4 — Existing subscriptions untouched

**Goal:** the runs did not disturb the three paper subscriptions (A6).

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. SUBSCHECK with output to `.cache/subs.txt`. `rm -f .cache/ssh/vps_key`.
2. SUBSDIFF; record its output.

**Success criteria:** the three lines equal Phase 01's.

**Verify:** SUBSDIFF prints `subs_unchanged`.

## Rollback

Nothing to roll back in code. The four runs stay as evidence; only the owner deletes a run (UI). A failed run leaves a `failed` document, which is recorded, not deleted.

## Report

`reports/phase-02-track-a-backtests.md`: entry-gate outputs; every `run=` line, `free_after_run=` line and `cost_ask=` answer; the table and two URLs; the two `verdict:` lines; the SUBSDIFF output; then `Result: PASS`.

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
title: "Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI"
status: pending
priority: P2
effort: "1d"
dependencies: [2]
---

# Phase 03: Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI

## Goal

`HitNRun2StrategyService` is back in the registry as `hitnrun2`, on the current contract with exactly one interval, with a `min_cost_multiple` filter that reads the round-trip cost from `config.contract_spec`, proven by 17 unit tests and a backtest-path test, with CI green on `develop`.

## Context

- D3, A3, A4 and the advice: keep the three lookbacks, `max_loss_pct`, `min_profit_pct` and `direction` as parameters; add one parameter `min_cost_multiple` (default 3.0); round-trip cost = `commission_per_contract * 2 + spread` from `config.contract_spec`; skip when the nearer of the TP and SL distances is under `min_cost_multiple` times that cost. Never a literal 0.15. For the seeded gold spec the multiplier is 1.0, so the per-contract fee is in price units and the formula is exact (plan.md Facts).
- Old code (`git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`): LONG when `close < min(previous entry window lows)`, `sl = max(min(previous SL window lows), close * (1 - max_loss_pct))`, `tp = max(max(previous TP window highs), close * (1 + min_profit_pct))`; SHORT mirrors (`:80-94`); windows exclude the current bar (`:60-70`); warm-up until the SL window is full (`:72-74`); one position at a time (`:76-78`); an opposite-side fill closes (`:98-104`); a rejection clears (`:106-107`).
- Signed distances: LONG `tp - close` and `close - sl`; SHORT `close - tp` and `sl - close`. When the close is also beyond the SL-window extreme, the SL sits on the wrong side and the nearer distance is `<= 0`, so the filter skips (plan.md Facts). The filter also skips `<= 0` when the spec cost is 0.
- Current contract (`src/pocketquant/core/domain/strategy/strategy_service_interface.py:16-48`): `DEFAULTS: ClassVar[dict]` is the parameter and type contract that `check_strategy_inputs` enforces (`services/__init__.py:49-71`); `restore_direction`; `snapshot` (optional, the engine tolerates `None`, `strategy_app_service.py:87-97`). The engine adds `bar["context"]` (`strategy_app_service.py:422-425`); a one-interval strategy never reads it. `Signal` fields as Triple Screen uses them (`triple_screen_strategy_service.py:182-202`). Style model: `triple_screen_strategy_service.py`.
- Spec wiring (plan.md Facts): backtest `backtest_execution_service.py:101-119`; trader `strategy_reconcile_app_service.py:154-177`, DI `app/di/services.py:159-171`. Existing trader test: `tests/engine_test/test_contract_spec_wiring.py:154` (`test_reconcile_loads_a_contract_subscription_with_its_spec`). The existing backtest test (`tests/backtest_test/test_backtest_dispatch_contract_spec.py:44-73`) checks the backtest config and broker, not the strategy, so this phase adds the strategy-level backtest test.
- Symbol lookups are cached per symbol for 60 s in a module-level cache (`src/pocketquant/core/infra/persistence/symbol_lookup_helper.py:15,25-38`), so the backtest test uses a different symbol per case.
- Test patterns: `tests/core_test/unit/domain/strategy/test_triple_screen.py` (helpers, `SimpleNamespace` fills); `tests/backtest_test/engine/test_triple_screen_backtest.py` (`_execution`, `_cmd_svc`, `_series`, seeding and cleanup); `database` fixture `tests/backtest_test/conftest.py:38-55`; `asyncio_mode = "auto"` (`pyproject.toml:63`).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-02-track-a-backtests.md`.
2. `grep -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md` prints `2` (Track A numbers exist before Track B code).
3. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (start Docker Desktop per FULLSUITE and retry once).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 03 after <UTC time>
```

## Files

- Create: `src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`, `tests/core_test/unit/domain/strategy/test_hitnrun2.py`, `tests/backtest_test/engine/test_hitnrun2_backtest.py`, the phase report.
- Modify: `src/pocketquant/core/domain/strategy/services/__init__.py` (registry and `__all__` only).
- Delete: none. Docs: none (plan.md Docs impact).

## Tasks

### Task 03.1 — The spec reaches the strategy in both paths

**Goal:** confirm, before writing the filter, that `StrategyConfig.contract_spec` carries the symbol's spec in the backtest and the trader path.

**Target files and symbols:** `backtest_execution_service.py` (`BacktestExecutionService.run`), `strategy_reconcile_app_service.py`, `app/di/services.py` (`get_reconcile_service`).

**Steps:**
1. `git grep -n "contract_spec=" -- src/pocketquant/engine/backtest/backtest_execution_service.py src/pocketquant/engine/live/strategy_reconcile_app_service.py`; record it.
2. `git grep -n "symbol_lookup=symbol_lookup" -- src/pocketquant/app/di/services.py`; record it.
3. `uv run python -m pytest "tests/engine_test/test_contract_spec_wiring.py::test_reconcile_loads_a_contract_subscription_with_its_spec" -q 2>&1 | tail -1`; record it.
4. If a grep misses or the test fails, [ASK] (intent) "the strategy does not receive the symbol's contract_spec in <path>; fixing it needs an engine change in <file>; make that change in this plan?" `Recommended: yes, one line passing the spec`, reason: A4 cannot hold without it. A non-yes ends the phase with `NOT_YET`.

**Success criteria:** both paths pass the spec; the trader test passes.

**Verify:** `git grep -n "contract_spec=" -- src/pocketquant/engine/backtest/backtest_execution_service.py src/pocketquant/engine/live/strategy_reconcile_app_service.py | grep -c -E "backtest_execution_service.py:(46|118|129):|strategy_reconcile_app_service.py:177:"` prints `4`; step 2's output contains `services.py:171:`; step 3's line contains `1 passed`. (Line numbers are those of `00272823`; if only the numbers moved and the same four assignments exist, record the new numbers and treat the check as passed.)

### Task 03.2 — Unit tests first

**Goal:** the strategy's rules are pinned before it exists.

**Target files and symbols:** `tests/core_test/unit/domain/strategy/test_hitnrun2.py`.

**Steps:**
1. Helpers (copy the style of `test_triple_screen.py`):
   - `GOLD = ContractSpec(multiplier=1.0, tick_size=0.001, commission_per_contract=0.035, spread=0.08)` with a `#` comment that it mirrors the seeded gold spec; `LINEAR_SPEC` from `pocketquant.core.domain.symbol`.
   - `_cfg(intervals=("1m",), spec=LINEAR_SPEC, **params)` returns `StrategyConfig(id="sub-1", name="hitnrun2", symbol="XAUUSD:EXNESS", intervals=list(intervals), parameters={"entry_lookback_bars": 2, "sl_lookback_bars": 8, "tp_lookback_bars": 3, **params}, contract_spec=spec)`.
   - `async def _strategy(spec=LINEAR_SPEC, **params)` builds `HitNRun2StrategyService(_cfg(spec=spec, **params))` and awaits `on_start()`.
   - `_bar(high, low, close, i)` returns `{"symbol": "XAUUSD:EXNESS", "interval": "1m", "open": close, "high": high, "low": low, "close": close, "volume": 1.0, "timestamp": _T0 + timedelta(minutes=i)}` with `_T0 = datetime(2026, 1, 5, tzinfo=UTC)`.
   - `async def _warm(s, deep=98.0, high3=None, high7=None)` feeds bars `i = 0..7` with `high=100.5, low=99.5, close=100.0`, except bar 3 has `low=deep` when `deep` is not None and `high=high3` when given, and bar 7 has `high=high7` when given. It asserts each returns `None`.
   - `_fill(side)` returns `SimpleNamespace(side=OrderSide[side])`.
   - `TRIGGER = (99.5, 98.9, 99.0)` (high, low, close) at `i=8`.
   - Unless a test says otherwise, it builds the strategy with `_strategy()` and calls `await _warm(s)` before the trigger; every test is `async def`.
2. Tests (names state the rule; expected values were derived from the rules in Context):
   - `test_more_than_one_interval_is_rejected`: `_cfg(intervals=("1m", "5m"))` raises `ValueError`.
   - `test_an_unknown_direction_is_rejected`: `direction="up"` raises `ValueError`.
   - `test_a_negative_cost_multiple_is_rejected`: `min_cost_multiple=-1.0` raises `ValueError`.
   - `test_check_strategy_inputs_accepts_one_interval_and_rejects_two`: `check_strategy_inputs("hitnrun2", ["1m"], {"min_cost_multiple": 2})` returns `HitNRun2StrategyService`; `["1m", "5m"]` raises `DomainError` with `error_code == "INVALID_PARAMETERS"`.
   - `test_the_sl_window_warms_up_first`: `_warm(s)`; after it `s.snapshot["decision"] == {"action": "skip", "reason": "warming up"}`.
   - `test_long_entry_on_a_close_below_the_previous_entry_window_low`: `_warm(s)`, then `TRIGGER` gives `Direction.LONG`, `entry_type == "market"`, `entry_price == 99.0`, `stop_loss_price == pytest.approx(98.01)`, `take_profit_price == pytest.approx(100.98)`, `entry_logic == "hitnrun2:breakdown"`. A `#` comment: the trigger's own low 98.9 is above its close, so a signal also proves the bar is not in its own window.
   - `test_short_entry_on_a_close_above_the_previous_entry_window_high`: `_warm(s, deep=None, high3=102.0)`, then bar `(101.2, 100.6, 101.0)` gives `Direction.SHORT`, `stop_loss_price == pytest.approx(102.0)`, `take_profit_price == pytest.approx(98.98)`, `entry_logic == "hitnrun2:breakup"`.
   - `test_the_sl_is_the_window_low_capped_at_max_loss_pct`: with `deep=50.0` the SL is `pytest.approx(98.01)`; a fresh strategy with `deep=98.7` gives `pytest.approx(98.7)`.
   - `test_the_tp_takes_the_window_high_above_the_min_profit`: `_warm(s, high7=105.0)`, then `TRIGGER` gives `take_profit_price == pytest.approx(105.0)`.
   - `test_direction_long_ignores_a_breakup`: `direction="long"`, `_warm(s, deep=None, high3=102.0)`, bar `(101.2, 100.6, 101.0)` returns `None` and `s.snapshot["decision"]["reason"] == "no breakout"`.
   - `test_one_position_until_the_opposite_fill`: `TRIGGER` gives LONG; `await s.on_order_filled(_fill("BUY"), 99.0)`; bar `(99.0, 98.5, 98.6)` at `i=9` returns `None` with reason `"position held"`; `await s.on_order_filled(_fill("SELL"), 98.6)`; bar `(98.6, 98.2, 98.3)` at `i=10` gives `Direction.LONG`.
   - `test_a_rejected_entry_clears_the_position`: `TRIGGER` gives LONG; `await s.on_order_rejected("zero position size")`; bar `(99.0, 98.5, 98.6)` at `i=9` gives `Direction.LONG`.
   - `test_a_restored_direction_blocks_an_entry`: `_warm(s)`; `s.restore_direction(Direction.SHORT)`; `TRIGGER` returns `None` with reason `"position held"`.
   - `test_an_entry_whose_nearer_exit_is_under_the_cost_multiple_is_skipped`: `spec=GOLD`, `_warm(s, deep=98.7)`; `TRIGGER` returns `None` and `s.snapshot["decision"] == {"action": "skip", "reason": "nearer exit under the cost multiple"}`. A `#` comment: the SL distance 0.3 is under 3 x 0.15.
   - `test_an_entry_whose_nearer_exit_covers_the_cost_multiple_is_taken`: `spec=GOLD`, `_warm(s, deep=98.0)`; `TRIGGER` gives `Direction.LONG` (nearer 0.99).
   - `test_the_cost_comes_from_the_contract_spec`: `deep=98.7` and `TRIGGER` give `Direction.LONG` with `spec=LINEAR_SPEC`, and also with `spec=GOLD, min_cost_multiple=1.0` (0.3 covers 0.15). Together with the skip test this shows the spec and the multiple decide, not a constant.
   - `test_an_entry_with_its_stop_on_the_wrong_side_is_skipped`: `spec=LINEAR_SPEC`, `_warm(s, deep=None)`; `TRIGGER` returns `None` with reason `"nearer exit under the cost multiple"` (the SL window low 99.5 is above the close 99.0).
3. Run `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -3`; expected red: an import error (the module does not exist). Record it.

**Success criteria:** the file holds 17 tests and fails only because the strategy is missing.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | grep -c -E "ModuleNotFoundError|ImportError|cannot import"` prints a number `>= 1`.

### Task 03.3 — The strategy and its registry entry

**Goal:** `HitNRun2StrategyService` implements the rules and is registered as `hitnrun2`.

**Target files and symbols:** `hitnrun2_strategy_service.py` (`HitNRun2StrategyService`); `services/__init__.py` (`STRATEGY_REGISTRY`, `__all__`).

**Steps:**
1. Recover the old file as a starting point: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py > src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py`.
2. Rewrite it to this shape (keep it about this short; no logging; no docstrings):
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
            raise ValueError("hitnrun2 decides on exactly one interval")
        if self.direction not in ("long", "short", "both"):
            raise ValueError(f"direction must be long|short|both, got {self.direction!r}")
        if any(n < 1 for n in lookbacks):
            raise ValueError("lookbacks must be >= 1")
        if self.max_loss_pct <= 0 or self.min_profit_pct < 0 or self.min_cost_multiple < 0:
            raise ValueError("max_loss_pct must be above 0; min_profit_pct, min_cost_multiple >= 0")
        spec = config.contract_spec
        # A fee on entry and on exit plus one spread, in price units on the seeded gold spec
        # (multiplier 1.0). A spec without a per-contract fee adds no commission here.
        self._round_trip = (spec.commission_per_contract or 0.0) * 2 + spec.spread
        self._highs: deque[float] = deque(maxlen=max(lookbacks))
        self._lows: deque[float] = deque(maxlen=max(lookbacks))

    async def on_start(self) -> None:
        await super().on_start()
        self._highs.clear()
        self._lows.clear()
        self._open_direction = None

    def _breakout(
        self, highs: list[float], lows: list[float], close: float
    ) -> tuple[Direction, float, float, str] | None:
        # LONG on a close below the entry-window low (SL below, TP above); SHORT mirrors.
        ...  # returns (direction, sl, tp, tag) with the old formulas, or None

    async def on_bar_completed(self, bar: dict) -> Signal | None:
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # Read before the current bar joins, so a bar never breaks its own range.
        highs, lows = list(self._highs), list(self._lows)
        self._highs.append(high)
        self._lows.append(low)
        ...  # decide in this order: warming up -> position held -> no breakout ->
        ...  # cost filter -> enter; set self.snapshot; return the Signal or None
```
   Fill in the `...` parts exactly as follows:
   - `_breakout(highs: list[float], lows: list[float], close: float)`: if `self.direction != "short"` and `close < min(lows[-self.entry_lookback_bars:])`, return `(Direction.LONG, max(min(lows[-self.sl_lookback_bars:]), close * (1 - self.max_loss_pct)), max(max(highs[-self.tp_lookback_bars:]), close * (1 + self.min_profit_pct)), "breakdown")`; elif `self.direction != "long"` and `close > max(highs[-self.entry_lookback_bars:])`, return `(Direction.SHORT, min(max(highs[-self.sl_lookback_bars:]), close * (1 + self.max_loss_pct)), min(min(lows[-self.tp_lookback_bars:]), close * (1 - self.min_profit_pct)), "breakup")`; else `None`.
   - `on_bar_completed` decision: `len(lows) < self.sl_lookback_bars` -> `("skip", "warming up")`; `self._open_direction is not None` -> `("hold", "position held")`; `_breakout(...)` is `None` -> `("hold", "no breakout")`; else compute `nearer = min(tp - close, close - sl)` for LONG and `min(close - tp, sl - close)` for SHORT; with a `#` comment "A stop on the wrong side of the close gives a distance <= 0, which no cost covers.", if `nearer <= 0 or nearer < self.min_cost_multiple * self._round_trip` -> `("skip", "nearer exit under the cost multiple")`; else `("enter_long" | "enter_short", tag)`, set `self._open_direction = direction` and build `Signal(symbol=self.config.symbol, direction=direction, confidence=0.7, timestamp=bar["timestamp"], subscription_id=self.id, entry_price=close, stop_loss_price=sl, take_profit_price=tp, entry_logic=f"hitnrun2:{tag}")`. Always set `self.snapshot = {"readings": [], "decision": {"action": action, "reason": reason}}` before returning.
   - `on_order_filled(self, order: FilledOrder, fill_price: float)`: with the `#` comment "Broker SL/TP fills arrive as the opposite side, so an opposite-side fill is the close.", clear `_open_direction` when it is LONG and `order.side == OrderSide.SELL`, or SHORT and `order.side == OrderSide.BUY`.
   - `on_order_rejected(self, reason: str)`: with the `#` comment "Only market entries are sent, so a rejection means no position opened.", set `_open_direction = None`.
3. Registry in `services/__init__.py`: import `HitNRun2StrategyService` from `pocketquant.core.domain.strategy.services.hitnrun2_strategy_service`; `STRATEGY_REGISTRY = {"triple_screen": TripleScreenStrategyService, "hitnrun2": HitNRun2StrategyService}`; add `"HitNRun2StrategyService"` to `__all__` (sorted).
4. Delete nothing from the old file's behaviour except the `datetime.now` fallback for the timestamp (the engine always sets `bar["timestamp"]`, `strategy_app_service.py:73-83`).

**Success criteria:** every Task 03.2 test passes; the registry lists both strategies.

**Verify:** `uv run python -m pytest tests/core_test/unit/domain/strategy/test_hitnrun2.py -q 2>&1 | tail -1` contains `17 passed` and contains neither `failed` nor `error`; `uv run python -c "from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY; print(sorted(STRATEGY_REGISTRY))"` prints `['hitnrun2', 'triple_screen']`.

### Task 03.4 — Backtest-path test: the symbol's spec decides the filter

**Goal:** a real backtest over seeded Mongo hands the symbol's spec to hitnrun2: a free spec trades, a costly spec trades nothing (AC4).

**Target files and symbols:** `tests/backtest_test/engine/test_hitnrun2_backtest.py` (`test_the_backtest_filter_reads_the_symbol_spec`).

**Steps:**
1. Copy `_execution`, `_cmd_svc` and the `_reset_sim_time` fixture from `tests/backtest_test/engine/test_triple_screen_backtest.py:39-59`.
2. `_T0 = datetime(2026, 1, 1, tzinfo=UTC)`. `_series(symbol)` builds 2 days of 1m `Bar`s from `_T0` with `close_k = 100 + 10 * sin(2 * pi * k / 30)`, `open` = previous close, `high = max(open, close) + 0.2`, `low = min(open, close) - 0.2`, `volume=1.0`, `tick_count=1` (same shape as the Triple Screen `_series`). A `#` comment: a 30-bar sine keeps the previous trough inside the 40-bar SL window, so breakdowns have a stop on the right side.
3. Parametrize `(symbol, spec, any_trades)` over `("HNRFREE:BINANCE", ContractSpec(), True)` and `("HNRDEAR:BINANCE", ContractSpec(commission_per_contract=1.0), False)`. A `#` comment: the nearer exit is at most `max_loss_pct` of about 100, near 1.0, below 3 x 2.0, so the costly spec must skip every entry; distinct symbols avoid the 60 s symbol lookup cache.
4. Test body: delete `bars` and `symbols` documents for `symbol` (collections `COLLECTION_BARS`, `COLLECTION_SYMBOLS` from `pocketquant.core.common.constants`); `await SymbolRepository(database).upsert(Symbol.create(symbol, contract_spec=spec))`; insert `_series(symbol)`; run `RunBacktestCommand(strategy_id="hitnrun2", symbol=symbol, intervals=["1m"], start_date=_T0 + timedelta(days=1), end_date=_T0 + timedelta(days=2), slippage_bps=0, commission_bps=0, parameters={"entry_lookback_bars": 20, "sl_lookback_bars": 40, "tp_lookback_bars": 10, "min_profit_pct": 0.0})` through `_cmd_svc(database).run` and `_execution(database).execute_and_persist`; load the run with `BacktestRepository(database).get(run_id)`; assert `status == "finished"` and `metrics.total_trades >= 1` when `any_trades`, else `== 0`. Delete the same `bars` and `symbols` documents in a `finally`.
5. Run the file.

**Success criteria:** 2 cases pass.

**Verify:** `uv run python -m pytest tests/backtest_test/engine/test_hitnrun2_backtest.py -q 2>&1 | tail -1` contains `2 passed` and contains neither `failed` nor `error`.

### Task 03.5 — CLOSE

**Goal:** gates hold, one feature commit, CI green on `develop`.

**Target files and symbols:** all files of this phase.

**Steps:**
1. AGNOSTIC (plan.md Conventions) prints `0`.
2. GATES with pyright on `src tests/core_test/unit/domain/strategy/test_hitnrun2.py tests/backtest_test/engine/test_hitnrun2_backtest.py`; FULLSUITE. Record every tail line.
3. `git add` the four files; commit `feat(strategy): add the hitnrun2 1m breakout strategy with a cost filter`; push `develop`; run the CLOSE check.

**Success criteria:** CI `success` on `HEAD`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse HEAD`.

## Rollback

`git revert <feature commit>` on `develop` and push. Nothing reaches prod before Phase 04.

## Report

`reports/phase-03-hitnrun2-strategy.md`: entry-gate outputs; the Task 03.1 greps and test line (and any [ASK] answer); the expected red; each Verify output; AGNOSTIC, GATES and FULLSUITE lines; any metric-ceiling commit; the commit sha and CI run id; then `Result: PASS`.

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
title: "Track B release to master and post-deploy checks"
status: pending
priority: P2
effort: "0.5h + CI time"
dependencies: [3]
---

# Phase 04: Track B release to master and post-deploy checks

## Goal

With the owner's explicit yes, `master` equals `develop`, the master pipeline deploys, prod lists `hitnrun2`, live stays off, the trader reconciles without failures, and the three existing subscriptions run unchanged.

## Context

- `develop:master` is an explicit owner ask every time (`CLAUDE.md` memory rule, `docs/deployment.md` Branches). A `master` push runs tests, builds and deploys; a green run needs no extra check (`docs/deployment.md` Deploy, Verify). Images are tagged `sha-<7 chars>`; a manual re-roll is `IMAGE_TAG=sha-<short> bash deploy/vps/10-deploy.sh` (`docs/deployment.md` Restart while live).
- No `exness` subscription exists (Phase 01 baseline: three paper subscriptions), so the "Restart while live" steps do not apply. The deploy rolls the trader; the three paper subscriptions warm up again in the new trader, which is a restart, not a config change (A6).
- Reconcile log events: `reconcile.failed`, `reconcile.load_failed`, `reconcile.unknown_template` (`src/pocketquant/engine/live/strategy_reconcile_app_service.py`).
- Ops names: plan.md Ops recipe.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-03-hitnrun2-strategy.md`.
2. `git fetch -q origin && git diff --stat origin/master origin/develop -- src tests | tail -1` contains `changed`.
3. KEY, then LIVECHK prints exactly `trader_live=False`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 04 after <UTC time>
```

## Files

- Create: the phase report. Repo code: none.
- Prod writes: the release push (deploy).

## Tasks

### Task 04.1 — Pre-release record

**Goal:** the rollback tag and memory baseline are recorded.

**Target files and symbols:** `origin/master`; VPS memory.

**Steps:**
1. Record `prev_master=$(git rev-parse --short=7 origin/master)` as `prev_master=<sha7>`.
2. FREE; record `free_before=<Mem: line>`.
3. Record `commits_to_release=` with the output of `git log --oneline origin/master..origin/develop | wc -l`.

**Success criteria:** the three lines exist.

**Verify:** `grep -c -E "^(prev_master=[0-9a-f]{7}|free_before=Mem:|commits_to_release=[1-9][0-9]*)" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `3`.

### Task 04.2 — [ASK] release

**Goal:** the owner approves the release.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Release hitnrun2 to prod? It ships one new strategy file and its registry entry (`hitnrun2`, one 1m interval, cost filter `min_cost_multiple` reading the symbol spec) plus tests; <commits_to_release> commits; no schema, route or config change; no subscription is created; live stays off (`trader_live=False`). The deploy restarts the trader, so the three paper subscriptions warm up again. Rollback: re-roll `sha-<prev_master>`." Lead with `Recommended: yes`, reason: CI is green on develop and nothing on prod uses the new strategy until Phase 06.
2. Record `release_ask=<reply>`. Only an explicit yes continues.

**Success criteria:** the report holds the owner's yes.

**Verify:** no verification needed (Task 04.3 runs only after the recorded yes).

### Task 04.3 — Release push and master run

**Goal:** `master` equals `develop` and the master pipeline succeeds.

**Target files and symbols:** `origin/master`.

**Steps:**
1. Record `pushed_at=<output of date -u +%Y-%m-%dT%H:%M:%SZ>`.
2. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; then `test "$(git rev-parse origin/master)" = "$(git rev-parse origin/develop)" && echo released` prints `released`.
3. `sleep 15`, then poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` every 60 s until `status` is `completed`. Record the run id.

**Success criteria:** the master run concludes `success` on the released sha.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` with `<sha>` equal to `git rev-parse origin/develop`.

### Task 04.4 — Post-deploy checks

**Goal:** prod serves `hitnrun2`, live is off in the new trader, reconcile is clean, and A6 holds.

**Target files and symbols:** `GET /api/v1/backtest/strategies`; trader container and log; prod `subscriptions`.

**Steps:**
1. PRODPY with HEADER plus:
```python
import json
import urllib.request
codes = json.load(urllib.request.urlopen("http://localhost:41921/api/v1/backtest/strategies"))
print("prod_has_hitnrun2=" + ("yes" if "hitnrun2" in codes else "no") + " codes=" + ",".join(sorted(codes)))
```
2. LIVECHK.
3. SSH `cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env logs --since <pushed_at> trader 2>&1` piped locally to `sed 's/\x1b\[[0-9;]*m//g' > .cache/trader.log`; then `grep -c -E "reconcile\.(failed|load_failed|unknown_template)" .cache/trader.log`.
4. SUBSCHECK to `.cache/subs.txt`; SUBSDIFF.
5. FREE; record `free_after=<Mem: line>`. `rm -f .cache/ssh/vps_key`.

**Success criteria:** `hitnrun2` listed; live off; no reconcile failure; the three subscriptions unchanged.

**Verify:** step 1 prints `prod_has_hitnrun2=yes codes=hitnrun2,triple_screen`; LIVECHK prints `trader_live=False`; the `grep -c` prints `0`; SUBSDIFF prints `subs_unchanged`.

## Rollback

Each step is an [ASK]. SSH `cd /opt/pocketquant && IMAGE_TAG=sha-<prev_master> bash deploy/vps/10-deploy.sh`, then `git revert <feature commit>` on `develop`, push `develop`, and a later release [ASK] brings `master` back in line. No prod data depends on `hitnrun2` before Phase 06. Record `free -m` after a rollback.

## Report

`reports/phase-04-release-hitnrun2.md`: entry-gate outputs; `prev_master=`, `free_before=`, `commits_to_release=`; `release_ask=`; `pushed_at=`, the master run id and sha; the post-check lines, `free_after=`; then `Result: PASS`.

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

=== FILE: phase-05-track-b-backtests.md ===
---
phase: 5
title: "Track B: two hitnrun2 backtests, table, verdict"
status: pending
priority: P2
effort: "about 1.5h wall time"
dependencies: [4]
---

# Phase 05: Track B: two hitnrun2 backtests, table, verdict

## Goal

Two finished hitnrun2 backtests on `XAUUSD:EXNESS` over the same window as Track A, one with the default `min_profit_pct` (0.02) and one with a lower value the owner picks, recorded in the same table format, and one `verdict:` line for the `hitnrun2-1m` set from the same VERDICT code.

## Context

- Advice: backtest hitnrun2 with the default `min_profit_pct` and one lower value; the 2% floor means a TP at least about 80 USD/oz away at today's gold price (advice, item 4), which a 1m strategy may rarely reach. The lower value is not owner-decided, so Task 05.1 asks it.
- Runs (plan.md BTRUN): `r5` `{"min_profit_pct": 0.02}`, `r6` `{"min_profit_pct": <LOW>}`. Every other parameter takes `DEFAULTS` (240/480/60 bars, `max_loss_pct=0.01`, `direction=both`, `min_cost_multiple=3.0`). Costs: the seeded spec, nothing sent (A2, A4).
- Coverage: Phase 01 checked 1m over this exact window; the window ends before plan day, so it does not move.
- Cost rule and recipe: the same as Phase 02 (1800 s ask, WINDOW, one at a time).
- Ops names: plan.md Ops recipe; BTRUN and VERDICT: plan.md Shared scripts.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-04-release-hitnrun2.md`.
2. `grep -c "^prod_has_hitnrun2=yes" plans/261109-1349-1m-strategy-evidence/reports/phase-04-release-hitnrun2.md` prints `1`.

On a miss, run `rm -f .cache/ssh/vps_key`, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 05 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`; local scratch `.cache/f.py`, `.cache/verdict.py`, `.cache/subs.txt`.
- Prod writes: two `backtest_runs`.

## Tasks

### Task 05.1 — [ASK] the lower `min_profit_pct`

**Goal:** the second hitnrun2 run's `min_profit_pct` is the owner's choice.

**Target files and symbols:** none.

**Steps:**
1. Ask in Vietnamese (intent): "Which lower `min_profit_pct` should the second hitnrun2 backtest use? Options: 0.005, 0.01, 0.0 (TP purely the 60-bar extreme). The default 0.02 runs anyway." Lead with `Recommended: 0.005`, reason: it keeps a TP floor (about 20 USD/oz at a 4000 USD gold price, an inference from the advice's 80 USD for 2%) that a 1m position can reach within hours, still far above 3 x the 0.15 round trip, and it changes one parameter only. Add the Track A verdict lines from `reports/phase-02-track-a-backtests.md` as context.
2. Record `min_profit_low=<value>` (a decimal, for example `min_profit_low=0.005`) and the reply.

**Success criteria:** one `min_profit_low=` line with a value below 0.02.

**Verify:** `grep -c -E "^min_profit_low=0(\.[0-9]+)?$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `1`, and `uv run python -c "print(<value> < 0.02)"` prints `True`.

### Task 05.2 — Two backtests, one at a time

**Goal:** `r5` and `r6` finish, each followed by a memory reading.

**Target files and symbols:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/{id}`.

**Steps:**
1. KEY. Write BTRUN from plan.md to `.cache/f.py` with `<LOW>` replaced by the `min_profit_low` value (a Python float literal, for example `0.005`).
2. For `r5` then `r6`, follow Phase 02 Task 02.1 step 2 exactly (skip, poll, WINDOW, submit, `busy=` retry, `still_running` re-poll, report lines, `free_after_run=<label>`, and the 1800 s [ASK] recorded as `cost_ask=<label> <reply>` before `r6`).
3. `rm -f .cache/ssh/vps_key`.

**Success criteria:** two final `run=` lines with `status=finished` and two `free_after_run=` lines. A `failed` run or a run still `started` after 3 h is a failed Verify.

**Verify:** `grep -c -E "^run=r[56] set=hitnrun2-1m id=\S+ status=finished " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md; grep -c -E "^free_after_run=r[56] " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `2`.

### Task 05.3 — Run table

**Goal:** the two runs read side by side, in the Phase 02 format.

**Target files and symbols:** the phase report.

**Steps:**
1. Write the table `| # | set | intervals | min_profit_pct | run id | elapsed_s | trades | total_return | profit_factor | max_drawdown | win_rate | gate |` with rows `| r5 | hitnrun2-1m | 1m | 0.02 | ...` and `| r6 | hitnrun2-1m | 1m | <min_profit_low> | ...`, values copied from the final `run=` lines.
2. Under it, `https://pocketquant.xyz/backtest/compare?runs=<r5 id>,<r6 id>`.

**Success criteria:** 2 rows and 1 URL.

**Verify:** `grep -c -E "^\| r[56] \| " plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md; grep -c "^https://pocketquant.xyz/backtest/compare?runs=" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `1`.

### Task 05.4 — Verdict line

**Goal:** one `verdict:` line for `hitnrun2-1m`, from the same code as Track A.

**Target files and symbols:** `.cache/verdict.py`; the phase report.

**Steps:**
1. Write VERDICT from plan.md to `.cache/verdict.py` (unchanged).
2. `uv run python .cache/verdict.py plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md`; append its line under the table as a plain line.

**Success criteria:** one line.

**Verify:** `grep -c -E "^verdict: hitnrun2-1m (pass|fail) r5:pf=\S+,trades=\S+,gate=(pass|fail) r6:pf=\S+,trades=\S+,gate=(pass|fail)$" plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `1`.

### Task 05.5 — Existing subscriptions untouched

**Goal:** A6 holds after the runs.

**Target files and symbols:** prod `subscriptions`.

**Steps:**
1. KEY. SUBSCHECK to `.cache/subs.txt`. `rm -f .cache/ssh/vps_key`.
2. SUBSDIFF.

**Success criteria:** unchanged.

**Verify:** SUBSDIFF prints `subs_unchanged`.

## Rollback

None in code. The two runs stay as evidence; only the owner deletes a run (UI).

## Report

`reports/phase-05-track-b-backtests.md`: entry-gate outputs; `min_profit_low=` and the reply; every `run=`, `free_after_run=` and `cost_ask=` line; the table and URL; the `verdict:` line; the SUBSDIFF output; then `Result: PASS`.

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

=== FILE: phase-06-paper-reconcile.md ===
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
- Known difference (R7): the pooled paper balance sizes positions differently from a 10 000 backtest, so commission per trade can differ; it is recorded, not judged.
- Ops names: plan.md Ops recipe.

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-05-track-b-backtests.md`.
2. `grep -h -c "^verdict: " plans/261109-1349-1m-strategy-evidence/reports/phase-02-track-a-backtests.md plans/261109-1349-1m-strategy-evidence/reports/phase-05-track-b-backtests.md` prints `2` then `1`.
3. On a resume with `paper=` lines in this phase's report, `now >= <latest daycheck until> + 20 h` (the daily cadence); otherwise end with `NOT_YET: waiting for the next daily check` and a resume time of `<latest daycheck until> + 24 h`.

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

=== FILE: phase-07-verdicts-and-archive.md ===
---
phase: 7
title: "Written verdict per set, status completed, archive"
status: pending
priority: P2
effort: "0.5h"
dependencies: [6]
---

# Phase 07: Written verdict per set, status completed, archive

## Goal

One written `final:` line per set (three) with the backtest verdict and the paper record, a one-paragraph conclusion, the plan at `status: completed`, and the plan directory moved to `plans/archive/`.

## Context

- D5: the plan ends at the paper reconciliation and a written pass/fail verdict per set. D4: the backtest decides; paper only reconciles. So a set's final verdict is its `verdict:` line; the paper record is attached, not judged.
- If no set passed, the conclusion states that 1m does not clear the gate on gold at these costs, with the numbers (advice, "My take").
- Plan status changes go through `ak plan update <id> --status completed`, which rewrites the `plan.md` front matter (`ak plan update --help`). The plan id is `pocketquant/261109-1349` once indexed (`ak plan list --json`). Earlier plans were archived with a `git mv` into `plans/archive/` and a docs-only commit (commit `00272823`).
- Commits touching only `plans/**` trigger no CI (`.github/workflows/cicd.yml:3-10`).

## Entry gate

1. Conventions EG (1)-(3); the previous report is `reports/phase-06-paper-reconcile.md`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from 07 after <UTC time>
```

## Files

- Create: `plans/261109-1349-1m-strategy-evidence/reports/phase-07-verdicts-and-archive.md`.
- Modify: `plan.md` front matter (through `ak plan update` only).
- Move: `plans/261109-1349-1m-strategy-evidence/` to `plans/archive/261109-1349-1m-strategy-evidence/`.

## Tasks

### Task 07.1 — Final verdict per set

**Goal:** three `final:` lines and a summary table that a reader can act on.

**Target files and symbols:** reports of Phases 02, 05, 06.

**Steps:**
1. For each set `ts-1m-5m-15m`, `ts-1m-15m-1h`, `hitnrun2-1m`, write `final: <set> <pass|fail> backtest=<the verdict line's run values> paper=<recorded|not_run> on_bar_error=<n|n/a> stale=<n|n/a>`, where `<pass|fail>` is copied from that set's `verdict:` line and the paper values from its `recon:` error line (`not_run` and `n/a` for a set that failed the gate).
2. A table `| set | runs (pf, trades, gate) | verdict | paper trades/day (bt vs paper) | avg commission (bt vs paper) | exit mix (bt vs paper) | errors/stale |` with one row per set, values copied from the reports.
3. A conclusion of at most five sentences: which sets pass, the main number behind each fail, and, if none passed, the sentence "1m does not clear the gate (net profit_factor >= 1.2 and total_trades >= 100 over 12 months) on XAUUSD:EXNESS at the seeded costs." Facts only; label any inference as such.

**Success criteria:** three `final:` lines whose pass/fail match the verdict lines.

**Verify:** `uv run python -c "import re; r='plans/261109-1349-1m-strategy-evidence/reports/'; t=open(r+'phase-02-track-a-backtests.md',encoding='utf-8').read()+open(r+'phase-05-track-b-backtests.md',encoding='utf-8').read(); f=open(r+'phase-07-verdicts-and-archive.md',encoding='utf-8').read(); v=dict(re.findall(r'^verdict: (\S+) (pass|fail) ', t, re.M)); g=dict(re.findall(r'^final: (\S+) (pass|fail) ', f, re.M)); print('final_ok=' + str(len(v) == 3 and v == g))"` prints `final_ok=True`.

### Task 07.2 — Status completed

**Goal:** `plan.md` front matter reads `status: completed`.

**Target files and symbols:** `plans/261109-1349-1m-strategy-evidence/plan.md`.

**Steps:**
1. `ak plan list --json | grep -c '"id": "pocketquant/261109-1349"'`; if it prints `0`, run `ak plan reindex` and check again.
2. `ak plan update pocketquant/261109-1349 --status completed`.

**Success criteria:** the front matter changed through the CLI.

**Verify:** `grep -c "^status: completed$" plans/261109-1349-1m-strategy-evidence/plan.md` prints `1`.

### Task 07.3 — Archive, commit, push

**Goal:** the plan lives in `plans/archive/` on `origin/develop`.

**Target files and symbols:** the plan directory.

**Steps:**
1. Append to the report everything above plus `Result: PASS` as the last line (the report moves with the directory).
2. `git mv plans/261109-1349-1m-strategy-evidence plans/archive/261109-1349-1m-strategy-evidence`; then `ak plan reindex`.
3. `git add -A plans/archive/261109-1349-1m-strategy-evidence`; commit `docs(plans): record the 1m strategy verdicts and archive the plan`; push `develop` (no CI runs for `plans/**`).

**Success criteria:** the directory is archived, completed and pushed.

**Verify:** `test -d plans/archive/261109-1349-1m-strategy-evidence && test ! -e plans/261109-1349-1m-strategy-evidence && grep -c "^status: completed$" plans/archive/261109-1349-1m-strategy-evidence/plan.md && git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo archived` prints `1` then `archived`.

## Rollback

`git revert <archive commit>` and push restores the directory; `ak plan update pocketquant/261109-1349 --status in-progress` reopens it.

## Report

`reports/phase-07-verdicts-and-archive.md`: entry-gate outputs; the three `final:` lines, the table and the conclusion; the `ak` outputs; then `Result: PASS` (written before the move, as Task 07.3 says).

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
