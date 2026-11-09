---
title: "1m strategy evidence: Triple Screen 1m entry and revived hitnrun2, backtest gate, paper reconcile"
description: "Backtest Triple Screen with a 1m entry screen and a revived hitnrun2 with a cost filter on 12 months of XAUUSD:EXNESS, gate each set on net profit_factor >= 1.2 and total_trades >= 100, paper-reconcile passing sets for 14 days, and close with a verdict per set."
status: in-progress
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
| D6 | (Validation 2026-11-09.) A set is a strategy plus its interval list, as defined below: three sets, two runs each; a set passes when at least one of its runs passes the gate. |
| D7 | (Validation 2026-11-09.) The second hitnrun2 run uses `min_profit_pct=0.005`. Phase 05 records it and does not ask. |
| D8 | (Validation 2026-11-09.) No backtest starts within 45 min of a job start: besides `sync_repair` 00:00Z and `sync_backfill` 03:00Z, also `sync_integrity` 04:00Z and `sync_repair` 12:00Z (see WINDOW). |
| D9 | (Validation 2026-11-09.) Paper `strategy_on_bar_error` and stale-bar counts are recorded next to the verdict and never change it. |

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
- Paper fills carry no spread: the broker factory builds `PaperBrokerAdapter` without a `spread` argument (`src/pocketquant/core/infra/brokers/broker_factory.py:41-57`), and the adapter default is `spread=0.0` (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:68`). A backtest charges the spec spread of 0.08. Phase 06 records this as a known difference.
- Paper trades carry `run_id = subscription_id` (`src/pocketquant/engine/live/live_trade_collector.py:37-39`); backtest trades go to `backtest_trades` with `run_id = backtest run id` (`src/pocketquant/engine/backtest/backtest_report_app_service.py:98-101`; `src/pocketquant/core/common/constants.py:14`). Both carry `commission` and `exit_reason` (`src/pocketquant/core/domain/trading/value_objects.py:83-103`).
- Error events: `strategy_on_bar_error strategy_id=<sid>` (`strategy_app_service.py:623`) and `strategy.entry_skipped reason=stale subscription_id=<sid>` (`strategy_app_service.py:633-649`).
- Trader logs are json-file, 10 MB x 3 files (`deploy/compose.prod.yml:16-20`), and a deploy replaces the container, so Phase 06 reads them daily and checks that each read is contiguous.
- No backtest cancel route exists (`src/pocketquant/app/routes/backtest.py`), so the 1800 s ask is taken after a run, before the next one starts.

## Conventions (every phase follows these)

- **Run order.** The runner executes `phase-NN-*.md` in numeric order, one fresh worker per phase. File order is execution order. Phases never run in parallel, so no two phases own the same file at once.
- **Working dir** `D:/w/_me/algotrading/pocketquant`, branch `develop`, Git Bash. Every Verify is one self-contained command run from there. The shell keeps no variables between commands. Give every SSH or poll command a 600000 ms tool timeout.
- **Reports** go to `plans/261109-1349-1m-strategy-evidence/reports/phase-NN-<slug>.md` (R below means `plans/261109-1349-1m-strategy-evidence/reports`). Machine lines (`run=`, `gate`, `verdict:`, `existing_sub`, `paper=`, `daycheck`, `recon:`, `final:`) are written as plain lines at the start of a line, never inside a code block or a list. Each report ends with `Result: PASS` when every task passed.
- **Entry gate (EG)** runs first in every phase from 02 on: (1) `git status --porcelain -- src web deploy tests scripts docs .github` prints nothing; (2) `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`; (3) the previous phase report exists and its last line is `Result: PASS`; (4) the phase-specific lines. A resumed phase may show its own task files as uncommitted, and `HEAD` may be ahead of `origin/develop` by its own unpushed commits. A miss is not a failed verification: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, and end with exactly three lines: `Status: BLOCKED` / `NOT_YET: <reason>` / `Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261109-1349-1m-strategy-evidence --from NN after <UTC time>`. A resumed phase skips every task whose Verify already passes and never repeats a prod write whose recorded result exists.
- **[ASK]** = stop and ask the owner in Vietnamese, leading with `Recommended: <reply>` and a one-line reason, then the facts. Record the question intent and the answer in English in the report. Only an explicit yes (or the named option) counts; "no" or "wait" ends the phase with the `NOT_YET` block. No approval carries forward. The plan's [ASK] points are: a run above 1800 s (Phases 02, 05); `contract_spec` not reaching the strategy when the fix needs an engine change (Phase 03); every `develop:master` push (Phase 04); both runs of one set passing (Phase 06); stopping the new paper subscriptions (Phase 06); any destructive prod action or any change outside the confirmed scope (any phase).
- **Search** uses `git grep` (`rg` is not installed in Git Bash): `git grep -n -E "<pattern>" -- <paths>`; counts pipe to `wc -l`.
- **WINDOW**: `uv run python -c "import datetime as d; t=d.datetime.now(d.UTC); m=t.hour*60+t.minute; print('window_ok=' + ('yes' if 45 <= m < 135 or 285 <= m < 675 or 765 <= m < 1395 else 'no') + ' utc=' + t.strftime('%H:%M'))"`. A backtest may start only on `window_ok=yes` (00:45-02:15, 04:45-11:15 or 12:45-23:15 UTC), so a run of up to 45 min stays clear of `sync_repair` at 00:00 and 12:00 (`cron_expression="0 */12 * * *"`), `sync_backfill` at 03:00 and `sync_integrity` at 04:00 (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:805-824`; owner decision D8). On `window_ok=no` end with `NOT_YET: outside the backtest window` and a resume time at the next window start.
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
| 01 | [Push the plan; no-look-ahead tests; spec, baseline and 1m coverage](./phase-01-coverage-and-baseline.md) | none | none | Completed |
| 02 | [Track A: four Triple Screen 1m backtests, table, verdicts](./phase-02-track-a-backtests.md) | 4 backtest runs | 01 | Completed |
| 03 | [Track B: spec check, hitnrun2 rewrite with cost filter, tests, CI](./phase-03-hitnrun2-strategy.md) | none | 02 | Completed |
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
| R7 | Pooled paper balance sizes positions differently from a 10 000 backtest, so commission per trade differs; paper fills carry no spread while the backtest charges 0.08 | H x L | Both recorded as known differences in the reconciliation; no threshold (D4) |
| R8 | A single 12-month window overfits | M x M | Accepted by the owner (DSR, PBO and sweeps are non-goals) |
| R9 | The metric ratchet fails on the new file | M x L | Raise the ceiling in its own commit (GATES) |

## Docs impact

None. The change adds a registry entry and a strategy file; strategy names and parameters live in code (`docs/governance/documentation-rules.md`, Line Test rule 1). No setup, command, route, config or architecture changes.

## Non-goals

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions; archiving other plans; a second shifted backtest window.

## Unresolved

None. The set definition, the lower `min_profit_pct`, the backtest window and the paper error rule were settled at validation (D6-D9). Phase 06 still asks which parameters to paper when both runs of one set pass, and whether to stop the new paper subscriptions at the end.

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

## Ultra selection

Chosen by a best-of-5 verifier pass: five candidates from `reports/evidence-packet.md`, scored by `kongming` (record: `reports/kongming-261109-1441-ultra-verdict.md`). This plan is the winning candidate, materialized unchanged, then revised with the validation answers D6-D9 (set definition, lower `min_profit_pct`, backtest window, paper error rule) and the verified paper-spread fact.

ultra: picked=A/5 margin=low unanimous=no rejected_all=no
