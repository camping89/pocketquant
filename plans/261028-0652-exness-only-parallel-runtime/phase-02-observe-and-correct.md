---
phase: 2
title: "Observe and correct: KISS rule, loop-lag probe, skip listener, docstrings, machine baseline"
status: done
priority: P1
effort: "3h + deploy D-1"
dependencies: []
---

# Phase 02 — Observe and correct

## Goal

Measure the current 2 vCPU / 3 GB host at idle (D25, record only per D31), rewrite the `CLAUDE.md` "more code" rule (D16), add an event-loop lag probe to `/health`, make the scheduler skip listener record max-instances skips instead of raising, remove every text that claims two schedulers may share one job store, print console tracebacks without local variables, move the image to `python:3.14-slim`, and deploy all of it as D-1. It also writes the one `oom_baseline=` line that every later OOM check compares against. `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.` in this phase (the last phase where 8 is right). <!-- Red team 2026-10-28: #2, #7 -->

## Context

- D16 target: `CLAUDE.md:26` reads "When a change needs more code than the code it replaces, stop and ask." Line 15 ("Single uvicorn worker only") changes in Phase 07, not here.
- Skip listener: `JobScheduler._on_skip` (`src/pocketquant/core/infra/scheduling/scheduler.py:95-99`) passes `event.scheduled_run_time` for both codes. In APScheduler 3.11.2 (checked with `inspect`), `EVENT_JOB_MAX_INSTANCES` is a `JobSubmissionEvent(code, job_id, jobstore, scheduled_run_times)` with a list and no `scheduled_run_time`, and `EVENT_JOB_MISSED` is a `JobExecutionEvent(code, job_id, jobstore, scheduled_run_time, ...)`. `_dispatch_skip` (`scheduler.py:117-135`) drops the future of `asyncio.run_coroutine_threadsafe` (`:133`), so a failed write is silent. `JobHistoryRepository.record_skip(*, job_id, scheduled_run_time, status, error=None)` is at `src/pocketquant/core/infra/persistence/repositories/job_history_repository.py:76-83`.
- Wrong "shared job store" text: `scheduler.py:3-5` (module docstring), `scheduler.py:53-55` (comment in `initialize`), `src/pocketquant/engine/market_data/app_services/sync_jobs.py:641-643` ("Multi-instance safe ..."), `docs/system-architecture.md:229`, `docs/deployment.md:221`, `docs/project-overview-pdr.md:110`.
- Lag probe home: `src/pocketquant/app/main_extensions.py` next to `start_quote_feed` (`:185`), using the existing `_cancel` helper (`:175-182`). `/health` is `health_check` inside `register_routes` (`main_extensions.py:372-380`); it is a closure over `app` and returns 200 with whatever it builds. Lifespan: `src/pocketquant/app/main.py:51-86` (`assert_utc_runtime()` at `:52`, `finally` at `:76`).
- Image: `deploy/Dockerfile:4` and `:28` use `python:3.14-rc-slim`.
- Tests: `asyncio_mode = "auto"` (`pyproject.toml:74`); log capture pattern `structlog.testing.capture_logs()` (e.g. `tests/app_test/market_data/test_cascade_aggregator.py:392`); existing scheduler test style `tests/core_test/infra/scheduling/test_scheduler_on_error_logging.py`.
- CI ignores `**/*.md` pushes (`.github/workflows/cicd.yml:6-10`); this phase has code changes, so the push runs CI.
- Backend container before Phase 08: `pocketquant-app`. Prod logs are `LOG_FORMAT=console`; `structlog.dev.ConsoleRenderer(colors=True)` at `src/pocketquant/core/common/logging/setup.py:71` uses the structlog 25.5.0 default `exception_formatter`, which is `RichTracebackFormatter(show_locals=True)` (checked with `inspect`), so a logged exception prints the local variables of every frame. `structlog.dev.plain_traceback` prints the traceback without them (checked by rendering an exception both ways). The existing test `tests/core_test/unit/common/test_logging_setup.py` patches `structlog.configure` and `logging.basicConfig`; `build_settings()` (`tests/core_test/infra/market_data/conftest.py:25`) uses `log_format="console"`. <!-- Red team 2026-10-28: #7 -->
- VPS versions (Compose, Engine) go to the git-ignored `.cache/vps-versions.txt`, never into a committed report, because this repository is public. <!-- Red team 2026-10-28: #7 -->
- Machine measurements use the three inline commands below. Phase 08 installs the same snapshot and OOM logic as `/opt/pocketquant/bin/snapshot.sh` and `oom-check.sh`; until then no script is copied to the VPS or kept in `.cache/`. Every command runs from `D:/w/_me/algotrading/pocketquant` with the key at `.cache/ssh/vps_key`. <!-- Red team 2026-10-28: #2, #11 -->
  - **Snapshot command.** Replace `<label>` and `<file>`. Line 1 has the `snapshot.sh` fields `label= ts= mem_used_mb= mem_available_mb= swap_used_mb= load1= psi_some_avg10= oom= boot_id=`; the next lines are one `docker stats` row per container (D25 per-container CPU and memory). `oom` is the kernel's `oom_kill` counter from `/proc/vmstat`, which counts every OOM kill since boot (no ring buffer to roll over).

    ```bash
    HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'echo "label=<label> ts=$(date -u +%FT%TZ) $(free -m | awk "/^Mem:/{printf \"mem_used_mb=%s mem_available_mb=%s \", \$3, \$7} /^Swap:/{printf \"swap_used_mb=%s\", \$3}") load1=$(cut -d" " -f1 /proc/loadavg) psi_some_avg10=$(awk "/^some/{sub(\"avg10=\",\"\",\$2); print \$2}" /proc/pressure/memory 2>/dev/null || echo absent) oom=$(awk "/^oom_kill /{print \$2}" /proc/vmstat) boot_id=$(cat /proc/sys/kernel/random/boot_id)"; docker stats --no-stream --format "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"' > <file>
    ```
  - **OOM check command** (the plan.md OOM rule). It prints `OOM_OK`, or `OOM_STOP <reason>` when the boot id differs from the baseline, the counter is higher, or `pocketquant-app` has `State.OOMKilled=true`:

    ```bash
    B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); N=$(ssh -i .cache/ssh/vps_key "$HOST" 'echo "$(cat /proc/sys/kernel/random/boot_id) $(awk "/^oom_kill /{print \$2}" /proc/vmstat) $(docker inspect -f "{{.State.OOMKilled}}" pocketquant-app)"'); set -- $B $N; if [ "$#" -ne 5 ]; then V="OOM_STOP unreadable"; elif [ "$3" != "$1" ]; then V="OOM_STOP boot_id_changed"; elif [ "$4" -gt "$2" ]; then V="OOM_STOP oom_kill=$4 baseline=$2"; elif [ "$5" != false ]; then V="OOM_STOP oomkilled=$5"; else V=OOM_OK; fi; echo "$V"
    ```
  - **Deploy window command** (the plan.md Conventions window: Mon-Fri 06:00-11:20 or 12:50-19:30 UTC, which lies outside every blackout). It prints `WINDOW_OK` or `NOT_IN_WINDOW d=<weekday> t=<minute>`:

    ```bash
    d=$(date -u +%u); t=$((10#$(date -u +%H)*60 + 10#$(date -u +%M))); if [ "$d" -le 5 ] && { { [ $t -ge 360 ] && [ $t -lt 680 ]; } || { [ $t -ge 770 ] && [ $t -lt 1170 ]; }; }; then echo WINDOW_OK; else echo "NOT_IN_WINDOW d=$d t=$t"; fi
    ```

## Entry gate

1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `git rev-parse --abbrev-ref HEAD` prints `develop`.

On any miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with exactly:

```text
Status: BLOCKED
NOT_YET: <which gate line missed and what it printed>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 02 after <UTC time>
```

## Files to create/modify

- Modify: `CLAUDE.md`, `src/pocketquant/core/infra/scheduling/scheduler.py`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `src/pocketquant/app/main_extensions.py`, `src/pocketquant/app/main.py`, `src/pocketquant/core/common/logging/setup.py`, `tests/core_test/unit/common/test_logging_setup.py`, `deploy/Dockerfile`, `docs/system-architecture.md`, `docs/deployment.md`, `docs/project-overview-pdr.md`. <!-- Red team 2026-10-28: #7 -->
- Create: `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py`, `tests/app_test/unit/test_loop_lag_probe.py`, `plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md`.
- Create (git-ignored scratch): `.cache/snap-*.txt`, `.cache/vps-versions.txt`. No snapshot script file. <!-- Red team 2026-10-28: #7, #11 -->
- Modify only if the ratchet trips: `pyproject.toml` `[tool.code-metrics]`.

## Tasks

### Task 2.0 — Machine baseline at idle

**Goal:** record the D25 measurements before anything changes, and the one OOM baseline every later phase compares against. <!-- Red team 2026-10-28: #2, #11 -->

**Target files and symbols:** `.cache/snap-baseline.txt`, `.cache/vps-versions.txt`, `plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md`.

**Steps:**
1. Copy the SSH key: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key`.
2. Take the snapshot: run the Context snapshot command with `<label>` = `baseline` and `<file>` = `.cache/snap-baseline.txt`. <!-- Red team 2026-10-28: #11 -->
3. Record the versions locally only (git-ignored, never copied into a report): `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'echo "nproc=$(nproc) compose=$(docker compose version --short) engine=$(docker version -f "{{.Server.Version}}")"' > .cache/vps-versions.txt`. <!-- Red team 2026-10-28: #7 -->
4. Write the report. The `oom_baseline=<boot_id> <oom_kill>` line comes from the same snapshot line, so the baseline and the recorded snapshot cannot disagree: `L=$(head -1 .cache/snap-baseline.txt); { printf '# Machine baseline\n\nD25 measurements on the prod VPS, record only (D31: the only machine stop is the OOM rule in plan.md Conventions). Warm-up seconds: n/a (no standby trader exists yet).\n\n'; echo "oom_baseline=${L##* boot_id=} $(echo "$L" | sed -E 's/.* oom=([0-9]+) .*/\1/')"; printf '\n## Idle, before the loop-lag probe\n\n```text\n'; cat .cache/snap-baseline.txt; printf '```\n'; } > plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md`. <!-- Red team 2026-10-28: #2 -->

**Success criteria:** the report holds exactly one `oom_baseline=` line, one full `label=baseline` snapshot line, at least one per-container `docker stats` row, and no Compose or Engine version.

**Verify:** `F=plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md; echo "$(grep -cE '^oom_baseline=[0-9a-f-]{36} [0-9]+$' $F) $(grep -cE '^label=baseline ts=[0-9T:Z-]+ mem_used_mb=[0-9]+ mem_available_mb=[0-9]+ swap_used_mb=[0-9]+ load1=[0-9.]+ psi_some_avg10=[^ ]+ oom=[0-9]+ boot_id=[0-9a-f-]+$' $F) $(grep -cE 'compose=|engine=' $F) $(grep -c ' cpu=' $F)"` prints `1 1 0 <n>` with `<n>` ≥ 1. <!-- Red team 2026-10-28: #2 -->

### Task 2.1 — Rewrite the "more code" rule (D16)

**Goal:** the executor of later phases does not stop on net line counts.

**Target files and symbols:** `CLAUDE.md:26`.

**Steps:**
1. Replace the line `  - When a change needs more code than the code it replaces, stop and ask.` with `  - Prefer the simplest design that meets the requirement; a larger diff is fine when it removes complexity or is required by the scope.` Keep the two-space indent. Change nothing else in `CLAUDE.md`.

**Success criteria:** the old sentence is gone; the new one appears once.

**Verify:** `echo "$(grep -c 'stop and ask' CLAUDE.md) $(grep -c 'Prefer the simplest design that meets the requirement' CLAUDE.md)"` prints `0 1`.

### Task 2.2 — Event-loop lag probe on `/health`

**Goal:** `/health` reports `event_loop_lag_max_s` (max over the last 60 s) and each stall above 0.25 s logs one WARNING.

**Target files and symbols:** `src/pocketquant/app/main_extensions.py` (new `start_loop_lag_probe`, `stop_loop_lag_probe`, `_run_loop_lag_probe`; `health_check` at `:372-380`); `src/pocketquant/app/main.py` (import list `:9-24`, lifespan `:51-86`); new `tests/app_test/unit/test_loop_lag_probe.py`.

**Steps:**
1. In `main_extensions.py` add `from collections import deque` to the imports and, right after `_cancel` (`:175-182`), add:

```python
_LAG_SAMPLE_S = 0.5
_LAG_WARN_S = 0.25
_LAG_WINDOW_SAMPLES = 120  # 60 s of 0.5 s samples


async def _run_loop_lag_probe(app: FastAPI) -> None:
    loop = asyncio.get_running_loop()
    samples: deque[float] = deque(maxlen=_LAG_WINDOW_SAMPLES)
    while True:
        started = loop.time()
        await asyncio.sleep(_LAG_SAMPLE_S)
        lag = max(0.0, loop.time() - started - _LAG_SAMPLE_S)
        samples.append(lag)
        app.state.loop_lag_max_s = round(max(samples), 3)
        if lag > _LAG_WARN_S:
            logger.warning("event_loop.lag", lag_s=round(lag, 3))


def start_loop_lag_probe(app: FastAPI) -> None:
    """Sample loop lag every 0.5 s; ``/health`` reports the 60 s maximum."""
    app.state.loop_lag_max_s = 0.0
    app.state.loop_lag_task = asyncio.create_task(_run_loop_lag_probe(app))


async def stop_loop_lag_probe(app: FastAPI) -> None:
    await _cancel(getattr(app.state, "loop_lag_task", None))
```
2. In `health_check`, after `result["environment"] = settings.environment`, add `result["event_loop_lag_max_s"] = getattr(app.state, "loop_lag_max_s", 0.0)`.
3. In `main.py`, add `start_loop_lag_probe` and `stop_loop_lag_probe` to the `main_extensions` import list (alphabetical order), call `start_loop_lag_probe(app)` on the line right after `assert_utc_runtime()` (`:52`), and make `await stop_loop_lag_probe(app)` the first statement of the `finally` block (before `drain_backtest_tasks`).
4. Write `tests/app_test/unit/test_loop_lag_probe.py`:

```python
import asyncio
import time
from types import SimpleNamespace

import structlog

from pocketquant.app.main_extensions import start_loop_lag_probe, stop_loop_lag_probe


async def test_blocked_loop_is_reported_and_warned_once() -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    with structlog.testing.capture_logs() as logs:
        start_loop_lag_probe(app)  # type: ignore[arg-type]
        await asyncio.sleep(0.6)
        time.sleep(1.1)  # blocks the loop: the next sample is late by at least 0.6 s
        await asyncio.sleep(1.1)
        await stop_loop_lag_probe(app)  # type: ignore[arg-type]
    assert app.state.loop_lag_max_s >= 0.5
    assert [entry["event"] for entry in logs].count("event_loop.lag") == 1
```

**Success criteria:** the test passes; `/health` carries the field.

**Verify:** `uv run python -m pytest tests/app_test/unit/test_loop_lag_probe.py -q 2>&1 | tail -1` contains `1 passed` and no `failed`.

### Task 2.3 — Skip listener records max-instances skips and logs failed writes

**Goal:** a dropped run becomes a `job_history` row; a failed write logs one WARNING instead of vanishing.

**Target files and symbols:** `scheduler.py` `_on_skip` (`:95-99`), `_dispatch_skip` (`:117-135`); new `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py`.

**Steps:**
1. In `_on_skip`, compute the run time per code and pass it:

```python
        status = "skipped_max_instances" if event.code == EVENT_JOB_MAX_INSTANCES else "missed"
        # A max-instances event is a submission event: it carries a list of run times.
        if event.code == EVENT_JOB_MAX_INSTANCES:
            run_time = event.scheduled_run_times[-1]
        else:
            run_time = event.scheduled_run_time
        self._dispatch_skip(event.job_id, run_time, status, None)
```
2. In `_dispatch_skip`, replace the `try`/`except` around `run_coroutine_threadsafe` with:

```python
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            logger.warning("scheduler.listener_dispatch_failed", exc_info=True)
            return

        def _log_failure(done: Any) -> None:
            if not done.cancelled() and done.exception() is not None:
                logger.warning(
                    "scheduler.record_skip_failed",
                    job_id=job_id,
                    error=type(done.exception()).__name__,
                )

        future.add_done_callback(_log_failure)
```
3. Write `tests/core_test/infra/scheduling/test_scheduler_skip_listener.py` with a fake repo `class _Repo` whose `async def record_skip(self, **kwargs)` appends `kwargs` to `self.calls`, and a `_FailingRepo` whose `record_skip` raises `RuntimeError("boom")`. Each test builds `JobScheduler(history_repo=repo)`, sets `scheduler._loop = asyncio.get_running_loop()`, calls `scheduler._on_skip(event)`, then `await asyncio.sleep(0.05)`. Use `t1 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)` and `t2 = t1 + timedelta(minutes=1)`. Tests:
   - `test_max_instances_event_records_the_latest_run_time`: event `JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "sync_1m", "default", [t1, t2])`; assert `repo.calls == [{"job_id": "sync_1m", "scheduled_run_time": t2, "status": "skipped_max_instances", "error": None}]`.
   - `test_missed_event_records_its_run_time`: event `JobExecutionEvent(EVENT_JOB_MISSED, "sync_1m", "default", t1)`; assert `repo.calls == [{"job_id": "sync_1m", "scheduled_run_time": t1, "status": "missed", "error": None}]`.
   - `test_failed_write_logs_one_warning`: `_FailingRepo`, the max-instances event, inside `structlog.testing.capture_logs()`; assert exactly one entry with `event == "scheduler.record_skip_failed"`, `job_id == "sync_1m"`, `error == "RuntimeError"`.

**Success criteria:** all three tests pass.

**Verify:** `uv run python -m pytest tests/core_test/infra/scheduling/test_scheduler_skip_listener.py -q 2>&1 | tail -1` contains `3 passed` and no `failed`.

### Task 2.4 — Remove the "shared job store" claims

**Goal:** no file says two schedulers may share `apscheduler_jobs`.

**Target files and symbols:** `scheduler.py:3-5`, `:53-55`; `sync_jobs.py:641-643`; `docs/system-architecture.md:229`; `docs/deployment.md:221`; `docs/project-overview-pdr.md:110`.

**Steps:**
The new wording names the scheduler, not the process, so it stays true after the scheduler moves into the worker; Phase 09's doc gate bans "one process," (with the comma), `ENABLE_JOBS=` and the other old-topology phrases listed in its Context, and none of the lines below contains one. <!-- Red team 2026-10-28: #10 -->

1. `scheduler.py:3-5`: replace the three lines ("Uses APScheduler with MongoDBJobStore for distributed coordination ... wins each tick.") with `Only one scheduler may run at a time. APScheduler 3 does not support two` / `schedulers on one job store: jobs run twice or are skipped.` (two docstring lines). <!-- Red team 2026-10-28: #10 -->
2. `scheduler.py:53-55`: replace the three comment lines with one line `        # Only one scheduler runs at a time; the Mongo store only keeps jobs across restarts.` <!-- Red team 2026-10-28: #10 -->
3. `sync_jobs.py:641-643`: replace the sentence that starts `Multi-instance safe:` and ends `only one execution.` with `` ``add_one_off_job`` uses ``replace_existing=True`` with a stable ``_catchup`` `` / `` suffix, so a repeated resolve replaces the pending catch-up instead of adding one. `` Keep the following sentence that starts `Fresh DB (``last is None``)` unchanged; re-wrap the docstring lines under 100 characters.
4. `docs/system-architecture.md:229`: make the row `` | `apscheduler_jobs` | APScheduler's job store. Only one scheduler runs at a time; APScheduler 3 does not support two on one job store. | ``. <!-- Red team 2026-10-28: #10 -->
5. `docs/deployment.md:221`: replace only the sentence `` Multiple processes coordinate via the shared `apscheduler_jobs` collection — see `system-architecture.md`. `` with `APScheduler 3 does not support two schedulers on one job store.`
6. `docs/project-overview-pdr.md:110` today reads `` - Several processes may share one database only with jobs enabled in exactly one of them (`ENABLE_JOBS=false` elsewhere). ``. Make it `- Several processes may share one database; only one of them runs the scheduler, because APScheduler 3 does not support two schedulers on one job store.` <!-- Red team 2026-10-28: #10 -->

**Success criteria:** none of the old phrases remains in `src` or `docs` (journals excluded, D28); the new lines contain neither "one process" nor `ENABLE_JOBS`.

**Verify:** `git grep -n -i -E "distributed coordination|first to update|Multi-instance safe|coordinate through it|coordinate via the shared|scheduler instances race|one process runs" -- src docs ':!docs/journals' ':!plans'; echo "rc=$?"` prints only `rc=1`. <!-- Red team 2026-10-28: #10 -->

### Task 2.5 — Stable Python image

**Goal:** prod runs a final Python 3.14 release.

**Target files and symbols:** `deploy/Dockerfile:4`, `:28`.

**Steps:**
1. Change `FROM python:3.14-rc-slim AS builder` to `FROM python:3.14-slim AS builder` and `FROM python:3.14-rc-slim AS runtime` to `FROM python:3.14-slim AS runtime`.

**Success criteria:** both stages use the final image.

**Verify:** `echo "$(grep -c 'python:3.14-slim' deploy/Dockerfile) $(grep -c 'rc-slim' deploy/Dockerfile)"` prints `2 0`.

### Task 2.6 — Console tracebacks without local variables

<!-- Red team 2026-10-28: #7 -->
**Goal:** a logged exception prints its traceback but no local variables, because the deploy prints log tails into the public GitHub Actions output and a local can hold a token or a request payload.

**Target files and symbols:** `src/pocketquant/core/common/logging/setup.py:71` (`structlog.dev.ConsoleRenderer(colors=True)` inside `setup_logging`); `tests/core_test/unit/common/test_logging_setup.py`.

**Steps:**
1. In `setup.py`, replace the line `            structlog.dev.ConsoleRenderer(colors=True),` with:

```python
            structlog.dev.ConsoleRenderer(
                colors=True,
                # Tracebacks reach the public deploy output; locals can hold secrets.
                exception_formatter=structlog.dev.plain_traceback,
            ),
```
   Leave the JSON branch unchanged (`format_exc_info` prints no locals).
2. In `test_logging_setup.py`, add `import sys` and `from typing import Any` to the imports and append:

```python
def test_console_tracebacks_print_no_local_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prod tracebacks reach the public deploy output; a local can hold a secret."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(structlog, "configure", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    logging_setup.setup_logging(build_settings())

    def fail() -> None:
        local_only = "-".join(["local", "only", "value"])
        raise ValueError(len(local_only))

    try:
        fail()
    except ValueError:
        rendered = captured["processors"][-1](
            None, "error", {"event": "boom", "exc_info": sys.exc_info()}
        )

    assert "ValueError" in rendered
    assert "local-only-value" not in rendered
```
   The value is built at run time, so it is absent from the source lines a traceback prints; only a locals dump can show it. Against today's `setup.py` the second assert fails.

**Success criteria:** both tests in the file pass.

**Verify:** `uv run python -m pytest tests/core_test/unit/common/test_logging_setup.py -q 2>&1 | tail -1` contains `2 passed` and no `failed`.

### Task 2.7 — Local gates and commits

**Goal:** green local gates and focused commits on `develop`.

**Target files and symbols:** every file above.

**Steps:**
1. Run `docker ps`; if it fails, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background, wait 10 s and retry.
2. `uv run ruff check src tests` prints `All checks passed!`; `uv run ruff format --check src tests` reports no file to reformat (run `uv run ruff format` on the touched files if needed); `uv run pyright` prints `0 errors`.
3. `uv run python scripts/code_metrics.py --ratchet; echo "rc=$?"` prints `rc=0`. If it fails only because of the new small functions, raise the failing ceiling in `pyproject.toml` `[tool.code-metrics]` to the measured value and commit it alone: `git add pyproject.toml && git commit -m "chore(metrics): raise the code-metrics ceiling"`. Say so in the phase summary.
4. Run the full suite: `just test` (fallback `uv run python -m pytest tests/ -q`). The only red allowed is `4 failed, 4 errors`, all in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`. About 109 setup errors mean Docker is down.
5. Commit in this order:
   - `git add CLAUDE.md docs/system-architecture.md docs/deployment.md docs/project-overview-pdr.md && git commit -m "docs: rewrite the simple-design rule and the single-scheduler wording"`
   - `git add src/pocketquant/core/infra/scheduling/scheduler.py src/pocketquant/engine/market_data/app_services/sync_jobs.py tests/core_test/infra/scheduling/test_scheduler_skip_listener.py && git commit -m "fix(scheduler): record max-instances skips and log failed skip writes"`
   - `git add src/pocketquant/app/main_extensions.py src/pocketquant/app/main.py tests/app_test/unit/test_loop_lag_probe.py && git commit -m "feat(app): report event-loop lag on /health"`
   - `git add src/pocketquant/core/common/logging/setup.py tests/core_test/unit/common/test_logging_setup.py && git commit -m "fix(logging): print console tracebacks without local variables"` <!-- Red team 2026-10-28: #7 -->
   - `git add deploy/Dockerfile && git commit -m "build: use the stable python:3.14-slim image"`

**Success criteria:** no red outside the two timezone files; contracts unchanged; working tree clean for the gate paths.

**Verify:** `test "$(uv run python -m pytest tests/ -q 2>&1 | grep -E '^(FAILED|ERROR)' | grep -vcE 'test_utc_runtime_guard|test_cron_trigger_timezone')" = 0 && test -z "$(git status --porcelain -- src web deploy tests scripts docs)" && uv run lint-imports | tail -1` prints `Contracts: 8 kept, 0 broken.`

### Task 2.8 — Push `develop` and wait for CI

**Goal:** CI is green on the pushed commit.

**Target files and symbols:** remote `develop`.

**Steps:**
1. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`, then `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
2. `sleep 15`.
3. Watch the run (re-run the same command if the tool times out): `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch develop --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --repo camping89/pocketquant --exit-status > /dev/null; echo "rc=$?"`.

**Success criteria:** the run concluded `success`.

**Verify:** `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch develop --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --repo camping89/pocketquant --json conclusion -q .conclusion` prints `success`.

### Task 2.9 — Deploy D-1 [ASK]

**Goal:** the probe, the listener fix, the traceback fix and the final image run in prod; memory is recorded before and after; the OOM rule holds. <!-- Red team 2026-10-28: #2, #7 -->

**Target files and symbols:** remote `master`; VPS `pocketquant-app`; `.cache/snap-d1-before.txt`, `.cache/snap-d1-after.txt`.

**Steps:**
1. [ASK] the owner:
   > Recommended: có — deploy D-1 lên prod ngay. Lý do: bản này chỉ thêm đo độ trễ event loop trên `/health`, sửa listener ghi lượt job bị bỏ qua, bỏ biến cục bộ khỏi traceback trong log và chuyển sang image `python:3.14-slim` bản chính thức; không đổi dữ liệu. Sự thật: CI `develop` xanh (run <RUN_ID>); `EXNESS_LIVE_TRADING=false`; deploy khởi động lại `pocketquant-app` khoảng 1-2 phút. Cho phép push `develop:master` không? <!-- Red team 2026-10-28: #7 -->
   Only an explicit yes continues. A "no" or "wait" ends the phase with the `NOT_YET` block (run `rm -f .cache/ssh/vps_key` first).
2. Check the deploy window (plan.md Conventions) with the Context deploy window command. On `NOT_IN_WINDOW`, wait until the next window opens, re-checking every 10 min (use the runtime's background-command facility for a wait longer than the tool timeout), then continue. <!-- Red team 2026-10-28: #11 -->
3. Snapshot before: run the Context snapshot command with `<label>` = `d1-before` and `<file>` = `.cache/snap-d1-before.txt`. <!-- Red team 2026-10-28: #11 -->
4. Release: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`, then `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" && echo released` prints `released`.
5. `sleep 15`, then watch (re-run on tool timeout): `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch master --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --repo camping89/pocketquant --exit-status > /dev/null; echo "rc=$?"` prints `rc=0`.
6. Verdict: `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch master --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --repo camping89/pocketquant --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.
7. Snapshot after (at least 5 min after the run ended): run the Context snapshot command with `<label>` = `d1-after` and `<file>` = `.cache/snap-d1-after.txt`. <!-- Red team 2026-10-28: #11 -->

**Success criteria:** deploy run green with a 0-failure verdict; both snapshots exist; the OOM check against `oom_baseline=` prints `OOM_OK` (boot id unchanged, counter not higher, `pocketquant-app` not OOM-killed). An `OOM_STOP` is a failed Verify (D31). <!-- Red team 2026-10-28: #2 -->

**Verify:** `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); N=$(ssh -i .cache/ssh/vps_key "$HOST" 'echo "$(cat /proc/sys/kernel/random/boot_id) $(awk "/^oom_kill /{print \$2}" /proc/vmstat) $(docker inspect -f "{{.State.OOMKilled}}" pocketquant-app)"'); set -- $B $N; if [ "$#" -ne 5 ]; then V="OOM_STOP unreadable"; elif [ "$3" != "$1" ]; then V="OOM_STOP boot_id_changed"; elif [ "$4" -gt "$2" ]; then V="OOM_STOP oom_kill=$4 baseline=$2"; elif [ "$5" != false ]; then V="OOM_STOP oomkilled=$5"; else V=OOM_OK; fi; echo "$V $(cat .cache/snap-d1-before.txt .cache/snap-d1-after.txt | grep -cE '^label=d1-(before|after) ts=.* oom=[0-9]+ boot_id=[0-9a-f-]+$')"` prints `OOM_OK 2`. <!-- Red team 2026-10-28: #2 -->

### Task 2.10 — Post-deploy checks and report

**Goal:** prove the probe and the image in prod and complete the baseline record.

**Target files and symbols:** VPS `pocketquant-app`; `plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md`.

**Steps:**
1. Check version, health field and listener errors: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app python -c "import sys; print(sys.version.split()[0])"; docker exec pocketquant-app curl -s http://localhost:41921/health | grep -c "\"event_loop_lag_max_s\""; docker logs --since 30m pocketquant-app 2>&1 | grep -c "Error notifying listener"'`. Expected three lines: a version matching `3.14.<n>` with no `rc`, then `1`, then `0`. The version is checked on screen only and is not written to the report. <!-- Red team 2026-10-28: #7 -->
2. Record the lag value: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app curl -s http://localhost:41921/health' | uv run python -c "import json, sys; print('event_loop_lag_max_s=' + str(json.load(sys.stdin)['event_loop_lag_max_s']))" > .cache/snap-d1-lag.txt`.
3. Append the deploy section: `{ printf '\n## D-1 deploy (single app)\n\n### Before\n\n```text\n'; cat .cache/snap-d1-before.txt; printf '```\n\n### After\n\n```text\n'; cat .cache/snap-d1-after.txt; cat .cache/snap-d1-lag.txt; printf '```\n'; } >> plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md`.
4. Commit: `git add plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md && git commit -m "docs(plans): record the machine baseline and the first deploy measurements"`.
5. Run `rm -f .cache/ssh/vps_key`.

**Success criteria:** step 1 printed the three expected lines; the report holds three snapshot lines (`baseline`, `d1-before`, `d1-after`), still exactly one `oom_baseline=` line, one lag line and no Compose or Engine version; the key copy is gone. <!-- Red team 2026-10-28: #2, #7 -->

**Verify:** `F=plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md; echo "$(grep -cE '^label=(baseline|d1-before|d1-after) ' $F) $(grep -c '^oom_baseline=' $F) $(grep -c '^event_loop_lag_max_s=' $F) $(grep -cE 'compose=|engine=' $F) $(test -e .cache/ssh/vps_key && echo key_present || echo key_gone)"` prints `3 1 1 0 key_gone`. <!-- Red team 2026-10-28: #2 -->

## Rollback

All changes are code and docs; no data changes. Revert the phase commits (`git revert --no-edit <sha>` for each, newest first), run the Task 2.7 gates, push `develop`, then [ASK] and push `develop:master` inside the deploy window as in Task 2.9. <!-- Red team 2026-10-28: #7, #11 --> The documented emergency path pins the previous image without a code change, also after an [ASK] and inside the **Deploy window** of plan.md Conventions: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cd /opt/pocketquant && IMAGE_TAG=sha-<previous short sha> bash deploy/vps/10-deploy.sh && bash deploy/vps/11-verify.sh'` (`docs/deployment.md:169-170`). End with `rm -f .cache/ssh/vps_key`.

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
