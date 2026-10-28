---
phase: 1
title: "Spike: two ticks sessions on one key"
status: done
priority: P1
effort: "2h (35 min measurement)"
dependencies: []
---

# Phase 01 — Spike: two ticks sessions on one key

## Goal

Decide with prod evidence whether a second Exness ticks WebSocket session on the same API key and account disturbs prod's own ticks session (D15, D24). The result is one line `Result: PASS` or `Result: FAIL` in `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md`. PASS keeps the hot-standby trader with tick overlap (F1-A). FAIL goes to the owner for a fallback; Phases 02-06 still run and Phase 07 stays blocked until the owner decides. Nothing is committed to `src/`, nothing is deployed, and `EXNESS_LIVE_TRADING` stays false (D17).

## Context

- Exness WS limits are per account per node: up to 10 active connections (`docs/journals/2026-10-13-exness-api-spike.md:38`). Prod's single `app` holds a ticks session and an events session; the spike adds a third.
- Prod writes `quote:latest:{symbol}` to Redis on every tick (`src/pocketquant/engine/market_data/app_services/quote_app_service.py:70-71`, key template `src/pocketquant/core/common/constants.py:25`). The cached JSON carries the venue tick `timestamp` (`src/pocketquant/engine/market_data/app_services/quote_dto.py:31-34`). Its age is the victim measurement.
- The spike session reuses the prod classes: `ExnessClient(settings)` (`src/pocketquant/core/infra/exness/exness_client.py:198`), `ExnessQuoteAdapter(client)` with `disconnect`, `subscribe` and `run_forever` (`src/pocketquant/core/infra/exness/exness_quote_adapter.py:32,50,54,73`). <!-- Red team 2026-10-28: #15 --> Only `XAUUSD`, `EURUSD`, `BTCUSD` are mapped (`src/pocketquant/core/infra/exness/exness_mappers.py:28-32`), so the spike sends no unknown instrument (an unknown one is a strike).
- The REST share is cut with `exness_rate_fraction` (`src/pocketquant/core/config.py:118`, used at `exness_client.py:355`); the spike uses 0.05. <!-- Red team 2026-10-28: #15 -->
- Prod WS log events: `exness_ws.connection_failed`, `exness_ws.circuit_breaker_open`, `exness_ws.reconnecting`, `exness_ws.stale_detected` (`src/pocketquant/core/infra/exness/exness_stream.py:65,115,119,133`) and `exness_ws.error_frame` (`exness_quote_adapter.py:116`). REST throttling logs `exness.rate_limited` and `exness.rate_limited_retry` (`exness_client.py:306,311`). Prod logs are `LOG_FORMAT=console` with ANSI colours; the counts below strip them with `sed 's/\x1b\[[0-9;]*m//g'` first and then grep the bare event name. <!-- Red team 2026-10-28: #15 -->
- `.cache` is git-ignored (`.gitignore:42`). Output of `docker exec -d` goes to the file it is redirected to, not to `docker logs pocketquant-app`, so prod's log only shows prod's own session.
- The run takes 35 min (A 10 min solo, B 15 min with the second session, C 10 min solo). The window is Mon-Thu 13:00-16:00 UTC (liquid FX and metals, no cron hour, outside every deploy blackout), so it must start by 15:20 UTC.

## Entry gate

Run each command from `D:/w/_me/algotrading/pocketquant`.

1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `d=$(date -u +%u); t=$((10#$(date -u +%H)*60 + 10#$(date -u +%M))); if [ "$d" -le 4 ] && [ $t -ge 780 ] && [ $t -le 920 ]; then echo WINDOW_OK; else echo "NOT_IN_WINDOW d=$d t=$t"; fi` prints `WINDOW_OK`.
3. `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key && HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r') && ssh -i .cache/ssh/vps_key "$HOST" 'docker ps -q --filter name=^pocketquant-app$ --filter status=running | wc -l'` prints `1`.

On any miss: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, leave the phase pending, and end with exactly these three lines (for a window miss, `<UTC time>` is the next Monday-Thursday 13:00 UTC):

```text
Status: BLOCKED
NOT_YET: <which gate line missed and what it printed>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 01 after <UTC time>
```

## Files to create/modify

- Create (git-ignored, never committed): `.cache/spike/two_tick_sessions.py`, `.cache/spike/evaluate.py`, `.cache/spike/raw.log`, `.cache/spike/result.json`.
- Create (stateful record, committed): `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md`.
- No file under `src`, `tests`, `web`, `deploy`, `scripts` or `docs` changes.

## Tasks

### Task 1.1 — Write the spike script

**Goal:** one throwaway script that samples prod's quote age every second and opens a second ticks session only in segment B.

**Target files and symbols:** `.cache/spike/two_tick_sessions.py` (new, git-ignored); uses `get_settings`, `ExnessClient`, `ExnessQuoteAdapter`, `redis.asyncio`.

**Steps:**
1. Run `mkdir -p .cache/spike`.
2. Write `.cache/spike/two_tick_sessions.py` with exactly this content:

```python
"""Throwaway: does a second Exness ticks session disturb prod's own session?"""

import asyncio
import json
import time
from datetime import UTC, datetime

import redis.asyncio as aioredis

from pocketquant.core.config import get_settings
from pocketquant.core.infra.exness.exness_client import ExnessClient
from pocketquant.core.infra.exness.exness_quote_adapter import ExnessQuoteAdapter

SYMBOLS = ["EURUSD:EXNESS", "XAUUSD:EXNESS", "BTCUSD:EXNESS"]
SEGMENTS = (("A", 600, False), ("B", 900, True), ("C", 600, False))


def p99(values):
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))], 3)


async def main():
    settings = get_settings().model_copy(update={"exness_rate_fraction": 0.05})
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    client = ExnessClient(settings)
    out = {"window_start": datetime.now(UTC).isoformat(timespec="seconds"), "segments": {}}
    for name, seconds, with_session in SEGMENTS:
        ages = {s: [] for s in SYMBOLS}
        own = {s: [] for s in SYMBOLS}
        adapter = task = None
        if with_session:
            adapter = ExnessQuoteAdapter(client)
            for s in SYMBOLS:
                await adapter.subscribe(s, lambda _q, s=s: own[s].append(time.monotonic()))
            task = asyncio.create_task(adapter.run_forever())
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            now = datetime.now(UTC)
            for s in SYMBOLS:
                raw = await redis.get(f"quote:latest:{s}")
                if raw:
                    ts = datetime.fromisoformat(json.loads(raw)["timestamp"])
                    ages[s].append((now - ts).total_seconds())
            await asyncio.sleep(1.0)
        if task is not None:
            await adapter.disconnect()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        segment = {}
        for s in SYMBOLS:
            segment[s] = {"p99_quote_age_s": p99(ages[s]), "samples": len(ages[s])}
            if with_session:
                gaps = [b - a for a, b in zip(own[s], own[s][1:])]
                segment[s]["ticks"] = len(own[s])
                segment[s]["max_gap_s"] = round(max(gaps), 3) if gaps else None
        out["segments"][name] = segment
    out["window_end"] = datetime.now(UTC).isoformat(timespec="seconds")
    await client.close()
    await redis.close()
    print("SPIKE_RESULT " + json.dumps(out), flush=True)


asyncio.run(main())
```

**Success criteria:** the file exists, is git-ignored and compiles.

**Verify:** `git check-ignore -q .cache/spike/two_tick_sessions.py && uv run python -m py_compile .cache/spike/two_tick_sessions.py && echo ok` prints `ok` and exits 0.

### Task 1.2 — Write the evaluator

**Goal:** turn the JSON and the prod log counts into the record with no judgement left to the executor.

**Target files and symbols:** `.cache/spike/evaluate.py` (new, git-ignored).

**Steps:**
1. Write `.cache/spike/evaluate.py` with exactly this content:

```python
"""Usage: evaluate.py <prod_ws_lines> <prod_rate_limited_lines> <own_ws_lines>. Prints the record."""

import json
import sys

r = json.load(open(".cache/spike/result.json"))
prod_ws, prod_rl, own_ws = (int(x) for x in sys.argv[1:4])
A, B, C = (r["segments"][k] for k in "ABC")
fx = ("EURUSD:EXNESS", "XAUUSD:EXNESS")
if any(seg[s]["samples"] == 0 for seg in (A, B, C) for s in fx):
    print("INVALID: a segment has no prod quote sample for EURUSD or XAUUSD")
    sys.exit(2)
c1 = prod_ws == 0
c2 = all(
    A[s]["p99_quote_age_s"] is not None
    and B[s]["p99_quote_age_s"] is not None
    and B[s]["p99_quote_age_s"] <= A[s]["p99_quote_age_s"] + 1.0
    for s in A
)
c3 = all(B[s]["ticks"] > 0 and B[s]["max_gap_s"] is not None and B[s]["max_gap_s"] <= 10 for s in fx)
c4 = prod_rl == 0
lines = [
    "# Spike: two Exness ticks sessions on one key",
    "",
    f"Window (UTC): {r['window_start']} to {r['window_end']}. Rate fraction 0.05. "
    "Segments: A 600 s solo, B 900 s with the second session, C 600 s solo.",
    "",
    "| Symbol | A p99 quote age s | B p99 quote age s | C p99 quote age s | B own ticks | B own max gap s |",
    "|---|---|---|---|---|---|",
]
for s in A:
    lines.append(
        f"| {s} | {A[s]['p99_quote_age_s']} | {B[s]['p99_quote_age_s']} | "
        f"{C[s]['p99_quote_age_s']} | {B[s]['ticks']} | {B[s]['max_gap_s']} |"
    )
lines += [
    "",
    "| Condition | Value | Pass |",
    "|---|---|---|",
    f"| Prod WS failure lines = 0 | {prod_ws} | {c1} |",
    f"| B p99 quote age <= A + 1.0 s, every symbol | see table | {c2} |",
    f"| Own session ticks > 0 and max gap <= 10 s, EURUSD and XAUUSD | see table | {c3} |",
    f"| Prod exness.rate_limited lines = 0 | {prod_rl} | {c4} |",
    "",
    f"Spike session own WS lines (record only): {own_ws}",
    "",
    "Result: " + ("PASS" if c1 and c2 and c3 and c4 else "FAIL"),
]
print("\n".join(lines))
```

**Success criteria:** the file compiles.

**Verify:** `uv run python -m py_compile .cache/spike/evaluate.py && echo ok` prints `ok`.

### Task 1.3 — Run the spike inside the prod container

**Goal:** measure interference in the real topology, on the real account.

**Target files and symbols:** VPS container `pocketquant-app`, files `/tmp/two_tick_sessions.py` and `/tmp/spike.log` inside it; local `.cache/spike/raw.log`, `.cache/spike/result.json`.

**Steps:**
1. Copy and start the script detached (one command):
   `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'cat > /tmp/two_tick_sessions.py' < .cache/spike/two_tick_sessions.py && ssh -i .cache/ssh/vps_key "$HOST" 'docker cp /tmp/two_tick_sessions.py pocketquant-app:/tmp/two_tick_sessions.py && docker exec -d pocketquant-app sh -c "python /tmp/two_tick_sessions.py > /tmp/spike.log 2>&1" && echo started'`. It must print `started`.
2. Wait for the result line. Run this with the runtime's background-command facility (it ends by itself after at most 45 min; do not use a foreground sleep longer than the tool timeout):
   `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); for i in $(seq 1 45); do if ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app grep -c "^SPIKE_RESULT " /tmp/spike.log' 2>/dev/null | grep -q '^1$'; then echo done; break; fi; sleep 60; done`
3. Fetch the output: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app cat /tmp/spike.log' > .cache/spike/raw.log && grep '^SPIKE_RESULT ' .cache/spike/raw.log | sed 's/^SPIKE_RESULT //' > .cache/spike/result.json`.
4. Remove the spike files on the VPS: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app rm -f /tmp/two_tick_sessions.py /tmp/spike.log; rm -f /tmp/two_tick_sessions.py; echo cleaned'`.

**Success criteria:** step 2 printed `done`; `result.json` is one JSON object with segments `A`, `B`, `C` and both window timestamps.

**Verify:** `uv run python -c "import json; r=json.load(open('.cache/spike/result.json')); print(sorted(r['segments']), bool(r['window_start']), bool(r['window_end']))"` prints `['A', 'B', 'C'] True True`.

### Task 1.4 — Count prod log lines and write the record

**Goal:** add prod's own failure counts for the same window and produce `Result: PASS|FAIL`.

**Target files and symbols:** `plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` (new).

**Steps:**
1. Count prod WS failure lines in the window (prints one number):
   `S=$(uv run python -c "import json; print(json.load(open('.cache/spike/result.json'))['window_start'])"); E=$(uv run python -c "import json; print(json.load(open('.cache/spike/result.json'))['window_end'])"); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker logs --since $S --until $E pocketquant-app 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -cE 'exness_ws\.(reconnecting|circuit_breaker_open|stale_detected|connection_failed|error_frame)'" | tee .cache/spike/prod_ws.txt` <!-- Red team 2026-10-28: #15 -->
2. Count prod REST throttling lines in the same window (terminal and retry both count):
   `S=$(uv run python -c "import json; print(json.load(open('.cache/spike/result.json'))['window_start'])"); E=$(uv run python -c "import json; print(json.load(open('.cache/spike/result.json'))['window_end'])"); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" "docker logs --since $S --until $E pocketquant-app 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -c 'exness\.rate_limited'" | tee .cache/spike/prod_rl.txt` <!-- Red team 2026-10-28: #15 -->
3. Count the spike session's own WS lines (record only): `grep -cE 'exness_ws\.(reconnecting|circuit_breaker_open|connection_failed|error_frame)' .cache/spike/raw.log | tee .cache/spike/own_ws.txt`
4. Write the record: `uv run python .cache/spike/evaluate.py "$(cat .cache/spike/prod_ws.txt)" "$(cat .cache/spike/prod_rl.txt)" "$(cat .cache/spike/own_ws.txt)" > plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md; echo "rc=$?"`. It must print `rc=0`. Exit code 2 (`INVALID`) means prod had no quote for EURUSD or XAUUSD in a segment: the measurement is void, which is a failed Verify.

**Success criteria:** the record holds the per-symbol table, the four conditions with their values, and exactly one `Result:` line.

**Verify:** `grep -cE "^Result: (PASS|FAIL)$" plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md` prints `1`.

### Task 1.5 — Gate decision and owner fallback on FAIL

**Goal:** fix the F1 choice for Phase 07.

**Target files and symbols:** the record from Task 1.4.

**Steps:**
1. Read the `Result:` line.
2. If `Result: PASS`: append `F1: A (hot standby with tick overlap)` with `echo "F1: A (hot standby with tick overlap)" >> plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md`. Go to step 5.
3. If `Result: FAIL`: [ASK] the owner with this message, filling in the failed conditions and values from the record:
   > Recommended: có — dùng một tài khoản Exness thứ hai cho feed tick của trader standby (D24). Lý do: spike cho thấy phiên tick thứ hai trên cùng key làm nhiễu feed của prod. Sự thật: <điều kiện trượt và số đo>. Phase 02-06 vẫn chạy bình thường; Phase 07 chờ quyết định này và một bản sửa plan. Anh đồng ý dùng tài khoản Exness thứ hai không?
4. This [ASK] does not gate this phase: whatever the reply, the phase completes, because Phases 02-06 do not depend on it. On an explicit yes append `Owner fallback: second-account`; on any other reply or no reply append `Owner fallback: pending (<reply or "no reply">)`. Use `echo "<line>" >> plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md`. Phase 07's entry gate reads this file.
5. Commit the record locally (no push needed; a `**/*.md` commit triggers no CI): `git add plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md && git commit -m "docs(plans): record the two ticks sessions spike result"`.
6. Run `rm -f .cache/ssh/vps_key`.

**Success criteria:** the record ends with an `F1: A` line (PASS) or an `Owner fallback:` line (FAIL); the commit exists; the key copy is gone.

**Verify:** `echo "$(grep -cE '^(F1: A|Owner fallback: )' plans/261028-0652-exness-only-parallel-runtime/reports/spike-two-tick-sessions.md) $(git log -1 --format=%s) $(test -e .cache/ssh/vps_key && echo key_present || echo key_gone)"` prints `1 docs(plans): record the two ticks sessions spike result key_gone`.

## Rollback

Nothing is deployed and no prod state changes. If the spike must stop early, kill it with `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app pkill -f /tmp/two_tick_sessions.py; docker exec pocketquant-app rm -f /tmp/two_tick_sessions.py /tmp/spike.log'`; its session closes with the process. Revert the record commit with `git revert --no-edit HEAD` only if the record itself is wrong. Always end with `rm -f .cache/ssh/vps_key`.

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
