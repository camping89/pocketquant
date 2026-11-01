---
phase: 1
title: "Spike A: worktree, cascade-lag measurement, subscription key, context in three paths, backtest cost"
status: pending
priority: P1
effort: 1d
dependencies: []
---

# Phase 01: Spike A: worktree, cascade-lag measurement, subscription key, context in three paths, backtest cost

## Goal

Prove in a throwaway worktree that the subscription key, the closed higher-timeframe context in live, warm-up and backtest, and the backtest cost work, and record the prod cascade lag as evidence, with every result written to `reports/spike-go-no-go.md`.

## Context

- C11 is met by a throwaway worktree `../pocketquant-spike` on local branch `spike/mtf`, started from `develop` HEAD. Only reports reach `develop`. Spike code is never committed, cherry-picked, merged or copied; later phases are written from their own specs (synthesis D7).
- Rough code is allowed in the spike tree: no docs, no polish, no validation beyond what a test needs. Spike test names still describe behaviour and carry no plan ids.
- Closed-bar rule (plan.md Design verdicts): a higher bar `b` is visible to an entry bar when `b.datetime + step(b.interval) <= entry_bar_start`, with the entry bar start as the instant in every path. The only existing closed filter is `_closed_bars` (`src/pocketquant/engine/strategy/strategy_app_service.py:285-289`).
- Cache verdict: `StrategyAppService._context[(symbol, interval)] = (window_start, bars)`, re-read only when `calendar.bar_start(instant, interval)` moves.
- Traps: the backtest clock is the bar start (`engine/backtest/backtest_app_service.py:109`) and its event has no `bar_end`; the sandbox builds the engine with `NoStoredBars()` and `Continuous24x7CalendarFactory()` (`engine/backtest/backtest_sandbox_app_service.py:125-139`), and its only caller `engine/backtest/backtest_execution_service.py:120` holds the real `self._bar_repo` and `self._calendar_factory`. Warm-up calls `strategy.on_bar_completed` directly (`strategy_app_service.py:252-264`), not `_on_bar_completed`. A unique index on a list is multikey, so the key must be a scalar `intervals_key` (scout-backend §0.1). The old unique index is `ix_subscriptions_dedup_triple` (`core/infra/persistence/repositories/subscription_repository.py:79-83`).
- `sync_1m` runs at second 12 (`engine/market_data/app_services/sync_jobs.py:734-740`) with a 100-minute cascade lookback (`:410`). The lag measurement is evidence only, never a gate or a constant (synthesis D1).
- <!-- Red team 2026-11-01: #15 --> D9 drops the freshness column, so this spike measures no `sync_status` freshness.
- A spike test that stays red after the Failure Protocol's `kongming` counsel names it a design limit (not a rough-code bug) is a `no-go` result, not a phase failure: record the row as `no-go` with that counsel and continue. The owner decides at Phase 02 (C11).
- No pyright baseline is recorded: the GATES in plan.md do not use one.
- Local `develop` is one docs commit (`e4a998b8`) ahead of `origin/develop` today, and the plan dir plus the advice files are untracked. Task 01.1 commits and pushes them. Commits under `plans/**` and `docs/**` trigger no CI (`.github/workflows/cicd.yml:3-11`).

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`. This phase replaces EG line (2): it cannot require `HEAD == origin/develop`, because Task 01.1 is the push that makes it true.

1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && git rev-list --count HEAD..origin/develop` prints `0`, and `git diff --name-only origin/develop..HEAD -- src web deploy tests scripts .github | wc -l` prints `0` (local is ahead only by docs or plans commits).
3. No previous report (first phase).
4. `git worktree list | grep -c pocketquant-spike` prints `0`, and `git branch --list spike/mtf | wc -l` prints `0`. On a resume these may print `1` when Task 01.2's Verify passes.
5. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok` (if not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background, retry after 10 s).

On a miss, end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 01 after <UTC time>
```

## Files

- Create (develop tree, plans only): `plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md`, `plans/261101-0843-stf-to-mtf-foundation/reports/phase-01-spike-a-data-path.md`.
- Create (local scratch, ignored by git): `.cache/f.py`, `.cache/ssh/vps_key`.
- Modify (spike tree only, never committed): any file under `../pocketquant-spike/src`, new tests under `../pocketquant-spike/tests/spike_test/`.
- Commit to develop: the plan dir (except `.claude/`, which `.gitignore:117` ignores) and `plans/reports/advise-261101-0847-stf-to-mtf-migration*` (5 files).

## Tasks

### Task 01.1 — Commit and push the plan

**Goal:** `develop` on origin holds the plan and the advice it cites, so every later entry gate can require `HEAD == origin/develop`.

**Target files and symbols:** `plans/261101-0843-stf-to-mtf-foundation/`, `plans/reports/advise-261101-0847-stf-to-mtf-migration*`.

**Steps:**
1. `git add plans/261101-0843-stf-to-mtf-foundation plans/reports/advise-261101-0847-stf-to-mtf-migration*`.
2. `git diff --cached --name-only | grep -c -E "agent-memory|^src/|^tests/|^web/"` must print `0`; otherwise `git reset -q` and stop under the Failure Protocol. Do not add the other untracked files under `plans/journals/` or `plans/reports/`.
3. `git commit -m "docs(plans): plan the move to multi-timeframe strategies"`.
4. Push with the Ops recipe: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`.

**Success criteria:** origin `develop` equals local HEAD; no CI run starts (plans and docs only).

**Verify:** `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

### Task 01.2 — Spike worktree

**Goal:** an isolated tree with its own venv.

**Target files and symbols:** `D:/w/_me/algotrading/pocketquant-spike` (branch `spike/mtf`, local only).

**Steps:**
1. `git worktree add ../pocketquant-spike -b spike/mtf develop`.
2. `cd ../pocketquant-spike && uv sync --frozen`.

**Success criteria:** the worktree exists on `spike/mtf` at the commit of Task 01.1.

**Verify:** `git merge-base --is-ancestor "$(git -C ../pocketquant-spike rev-parse HEAD)" HEAD && git -C ../pocketquant-spike rev-parse --abbrev-ref HEAD` prints `spike/mtf`.

### Task 01.3 — Prod measurements (read-only)

**Goal:** record how long after a bucket end the final cascade value lands. <!-- Red team 2026-11-01: #15 -->

**Target files and symbols:** `.cache/f.py` (PRODPY), `reports/spike-go-no-go.md` section `## Measurements`.

**Steps:**
1. SSH key: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
2. Write `.cache/f.py`:
```python
from datetime import UTC, datetime, timedelta

from pymongo import MongoClient

from pocketquant.core.config import get_settings

s = get_settings()
db = MongoClient(str(s.mongodb_url), tz_aware=True)[s.mongodb_database]
print("ok")
steps = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
now = datetime.now(UTC)
syms = sorted(d["symbol"] for d in db.tracked_symbols.find({}, {"symbol": 1}) if d["symbol"].endswith(":EXNESS"))
for sym in syms:
    for iv, step in steps.items():
        lags = []
        q = {"symbol": sym, "interval": iv, "source": "cascade", "datetime": {"$gte": now - timedelta(hours=72)}}
        for b in db.bars.find(q, {"datetime": 1, "updated_at": 1}):
            end = b["datetime"] + timedelta(seconds=step)
            if end <= now - timedelta(minutes=5) and b.get("updated_at"):
                lags.append((b["updated_at"] - end).total_seconds())
        lags.sort()
        if not lags:
            print(f"lag {sym} {iv} n=0")
            continue
        p = lambda f: lags[min(len(lags) - 1, int(f * len(lags)))]
        le40 = sum(x <= 40 for x in lags) / len(lags)
        print(f"lag {sym} {iv} n={len(lags)} p50_s={p(0.5):.1f} p99_s={p(0.99):.1f} max_s={lags[-1]:.1f} share_le_40s={le40:.3f}")
```
3. Run PRODPY f: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/f.py' < .cache/f.py && ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant/deploy && docker compose -f compose.prod.yml --env-file .env cp /tmp/f.py api:/tmp/f.py && docker compose -f compose.prod.yml --env-file .env exec -T api python /tmp/f.py' > .cache/measure.txt 2>&1; rm -f .cache/ssh/vps_key`.
4. Copy every `lag` line into `reports/spike-go-no-go.md` under `## Measurements`, with the UTC time of the run. State that the lag is evidence only and sets no constant.

**Success criteria:** the script printed `ok` and at least one `lag` line with `n>0`; the key file is gone.

**Verify:** `echo "lag=$(grep -c -E "^lag [^ ]+ [0-9]+[mh] n=[1-9]" plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md) key=$(test -f .cache/ssh/vps_key && echo present || echo gone)"` prints `lag=<n>` with `n >= 1`, then `key=gone`.

### Task 01.4 — S1 subscription key

**Goal:** prove that `["15m","1h"]` and `["15m","4h"]` coexist for one code and symbol while a repeat collides.

**Target files and symbols (spike tree):** `Subscription` (`core/domain/subscription/entities.py`), `SubscriptionRepository.add` and `ensure_indexes`, `StrategyCommandService.add_symbol`, `CreateSubscriptionBody` and `create_subscription` (`app/routes/strategy.py:13-16,46-52`); new `tests/spike_test/test_spike_subscription_key.py`.

**Steps:**
1. Write the test first, through `app_client` (`tests/app_test/integration/conftest.py:15`): monkeypatch a spike probe class into `STRATEGY_REGISTRY` as `"probe"`, upsert tracked symbol `BTCUSDT:BINANCE` through `TrackedSymbolRepository` from the dishka container, then POST `/api/v1/strategies/probe/subscriptions` with `{"symbol": "BTCUSDT:BINANCE", "intervals": ["15m","1h"]}` and `["15m","4h"]` (both `201`), then `["15m","1h"]` again (`409`). Name the tests `test_two_interval_sets_sharing_the_entry_interval_both_insert` and `test_a_repeated_interval_set_is_a_conflict`. Run them; expected red (`422`, the body has no `intervals`).
2. Rough change: entity `intervals: tuple[Interval, ...]`; `to_mongo` writes `intervals` (values) and `intervals_key = ",".join(...)`; unique index `ix_subscriptions_dedup_intervals` on `(strategy_code, symbol, intervals_key)`; body and `add_symbol` take `intervals`. Fix only the src readers the tests reach.

**Success criteria:** both tests pass in the spike tree.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_subscription_key.py -q 2>&1 | tail -1` contains `2 passed` (or, per Context, `grep -c "^| S1 .* no-go " plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `1`).

### Task 01.5 — S2 context in three paths, S3 reads per rollover

**Goal:** the first entry bar of a new hour sees the previous hour's close, the bar before it does not, and the partial current hour is never served, in live, warm-up and backtest; context reads happen once per rollover.

**Target files and symbols (spike tree):** `StrategyConfig` (`core/domain/strategy/value_objects.py:26-35`), `StrategyAppService._on_bar_completed`, `start_strategy`, `_closed_bars`, `build_backtest_sandbox`, `BacktestExecutionService.run`, `BacktestConfig`; new `tests/spike_test/test_spike_context.py`.

**Steps:**
1. Tests first, real test Mongo (`database` fixture), symbol `BTCUSDT:BINANCE` (24/7), entry `1m`, context `1h`. Seed 1m bars 2026-01-05 00:30-01:59 and 1h bars at 2026-01-04 23:00, 2026-01-05 00:00 and a partial 01:00. A probe strategy records `bar["context"]["1h"][-1].datetime` per decided bar.
   - `test_live_first_entry_bar_of_an_hour_sees_the_previous_hour`: publish `BarCompletedEvent` for 00:59 and 01:00 with `bar_end` set and the simulation clock 1 s after `bar_end`; recorded values are 23:00 and 00:00.
   - `test_warm_up_contexts_match_the_live_rule`: `start_strategy` at 01:31:25; for every replayed bar starting at `t`, the recorded value is `floor_hour(t) - 1h`, never 01:00.
   - `test_backtest_contexts_match_the_live_rule`: `BacktestExecutionService.run` with intervals `["1m","1h"]` over 00:30-01:59; same assertion per bar.
   - `test_context_reads_once_per_rollover`: wrap `BarRepository.find` with a counter for `interval="1h"`; across the live bars 00:58-01:02 the count is `2` (two windows).
   Run them; expected red (`KeyError: 'context'`).
2. Rough change: `StrategyConfig.intervals`; module-level `closed_before(bars, step, instant)` with the verdict rule; `self._context` cache refreshed when `calendar.bar_start(instant, interval)` moves; `bar["context"]` set before every decision in live and warm-up (warm-up prefetches each context interval once before `on_start()` and slices in memory); `build_backtest_sandbox(bar_repository, calendar_factory)` gets the real ones from `backtest_execution_service.py:120`; `BacktestConfig.intervals` with the stream on `intervals[0]`.

**Success criteria:** the four tests pass; any trap found is noted for the report.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_context.py -q 2>&1 | tail -1` contains `4 passed` (or, per Context, rows S2 and S3 read `no-go`).

### Task 01.6 — S4 backtest cost

**Goal:** measure what the context costs in a backtest.

**Target files and symbols (spike tree):** new `tests/spike_test/test_spike_backtest_cost.py`.

**Steps:**
1. Seed 30 days of 1m bars (43,200) for `BTCUSDT:BINANCE` from 2026-01-01 with their 1h (720) and 4h (180) aggregates.
2. Time `BacktestExecutionService.run` once with intervals `["1m","1h","4h"]` and once with `["1m"]`, same probe; count `BarRepository.find` calls for `1h` and `4h` in the first run.
3. Print one line `spike_cost find_calls=<n> rollovers=900 t_mtf_s=<x> t_stf_s=<y>`.

**Success criteria:** the line is printed; go means `find_calls <= 902` and `t_mtf_s <= 2 * t_stf_s`.

**Verify:** `cd ../pocketquant-spike && uv run python -m pytest tests/spike_test/test_spike_backtest_cost.py -q -s 2>&1 | grep -c "^spike_cost find_calls="` prints `1`.

### Task 01.7 — Record S1-S4 and push the reports

**Goal:** the go/no-go rows for this phase are on origin.

**Target files and symbols:** `reports/spike-go-no-go.md`, `reports/phase-01-spike-a-data-path.md`.

**Steps:**
1. In `spike-go-no-go.md` add `## Go/no-go` with header `| piece | go/no-go | evidence | carried to phase |` and rows `| S1 subscription key |`, `| S2 context in live, warm-up, backtest |`, `| S3 one read per rollover |`, `| S4 backtest cost |`. Evidence is the test names with their asserted values and the `spike_cost` numbers. Mark `go` only when the task's Verify passed and S4 meets its bounds; otherwise `no-go`.
2. Add `## Traps found` (free text) and `## Kept vs rewritten`: kept = this report, the numbers and the test scenarios as prose; rewritten = all code and tests. Never cherry-pick, merge, `git checkout spike/mtf -- <path>` or copy a spike file.
3. Write the phase report (see Report), then `git add plans/261101-0843-stf-to-mtf-foundation/reports && git commit -m "docs(plans): record the data-path spike results"`, then push with the Ops recipe. The worktree stays for Phase 02.

**Success criteria:** four rows exist; origin has the commit.

**Verify:** `echo "rows=$(grep -c -E "^\| S[1-4] " plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md) synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `rows=4 synced=yes`.

## Rollback

Develop holds only plan and report commits; revert them with `git revert <sha>` and push. The spike is local: `git worktree remove --force ../pocketquant-spike && git branch -D spike/mtf`. Prod was only read.

## Report

`reports/phase-01-spike-a-data-path.md`: the Task 01.1 commit sha; the measurement run time and a pointer to `## Measurements`; the four Verify outputs of Tasks 01.4-01.6 verbatim; the S1-S4 decisions; traps found; any deviation. Last line `Result: PASS`.

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
