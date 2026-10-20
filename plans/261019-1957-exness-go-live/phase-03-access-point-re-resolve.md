---
phase: 3
title: "Re-resolve the access point on transport failure or 421 (B8)"
status: pending
priority: P2
effort: 2h
dependencies: []
---

# Phase 03: Re-resolve the access point on transport failure or 421 (B8)

## Context
- `ExnessClient.access_point()` caches the host in `self._access_point` (`core/infra/exness/exness_client.py:238-246`); nothing clears it.
- `call()` sends every op except `getAccessPoint` to that host (`:268-271`). A transport failure surfaces as `ExnessApiError(0, "TRANSPORT", ...)` after 3 attempts (`_send`, `:305-319`, via `_send_paced`, `:280-303`). Other non-2xx answers become `_api_error(response)`.
- The WS reads the host on every connect (`ws_url` → `access_point()`, `exness_client.py:378-379`; `exness_stream.py:72`), so clearing the cache also moves the next reconnect.
- `getAccessPoint` is paced by the bootstrap pacer (`_BOOTSTRAP_OPS`, `:61`).

## Gates in this phase
None. The `develop` push (Task 3.4) is authorized by the plan.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 03 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s; still failing → `NOT_YET: Docker Desktop is not running`).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing (else `NOT_YET: uncommitted code changes`).

## Tasks

### Task 3.1 — Clear the cached host on TRANSPORT or 421
- Goal: the next call after a transport failure or a 421 resolves the access point again.
- Target files and symbols: `src/pocketquant/core/infra/exness/exness_client.py` → `call`.
- Steps:
  1. Wrap `response = await self._send_paced(...)` in `try/except ExnessApiError as e`. When `e.code == "TRANSPORT"`: `self._access_point = None`, log WARNING `exness.access_point_reset` with `reason="transport"` and `op`, re-raise.
  2. After the send, when `response.status_code == 421`: `self._access_point = None`, log the same event with `reason="421"`, then raise `_api_error(response)` as today.
  3. No retry inside the same call; no new function.
- Success criteria: two reset points, no new function.
- Verify: no verification needed (Task 3.2).

### Task 3.2 — Tests
- Goal: the reset is pinned.
- Target files and symbols: `tests/core_test/infra/exness/test_exness_client.py` (reuse the fake transport at `:72-81`).
- Steps — cases:
  1. A 421 on a data call raises, and the next call requests `getAccessPoint` again and goes to the new host.
  2. Three transport errors raise `TRANSPORT`, and the next call resolves again.
  3. A 200 keeps the cached host (the existing test near `:128` stays green).
- Success criteria: two new cases; the old one unchanged.
- Verify: `uv run python -m pytest tests/core_test/infra/exness -q` exits 0.

### Task 3.3 — Docs
- Goal: the deployment doc says when the access point is re-resolved.
- Target files and symbols: `docs/deployment.md:115` (sentence starting "The per-account Exness access point is not an env var").
- Steps: append "A transport failure or a 421 clears it; the next call resolves it again."
- Success criteria: one sentence added.
- Verify: `grep -c "A transport failure or a 421 clears it" docs/deployment.md` prints `1`.

### Task 3.4 — Gates and push
- Goal: green on `origin/develop`.
- Target files and symbols: whole repo.
- Steps: ruff and pyright on `src` and the touched test; `uv run python scripts/code_metrics.py --ratchet`; commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: gates pass, push succeeds.
- Verify: ruff `All checks passed!`; pyright `0 errors`; ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- Only the WS host fails while REST works (L/M): the cache is not cleared. `exness_ws.connection_failed` shows it; `sync_1m` calls REST every minute on the same host.
- A flapping network adds `getAccessPoint` calls (L/L); they are paced.

## Rollback
Revert the commit. No state outside the process.

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
