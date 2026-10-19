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
- `ExnessClient.access_point()` resolves once and caches the host in `self._access_point` (`core/infra/exness/exness_client.py:238-246`). Nothing ever clears it.
- `call()` sends every operation except `getAccessPoint` to that host (`:268-271`). A transport failure surfaces as `ExnessApiError(0, "TRANSPORT", ...)` after 3 attempts (`_send`, `:310-319`, raised through `_send_paced`, `:280-303`). Any other non-2xx answer becomes `_api_error(response)` (`:276-278`, `:393-410`).
- The WS reads the host on every connect, through `ws_url` → `access_point()` (`exness_client.py:378-379`, `exness_stream.py:72`). Clearing the cache therefore also moves the next WS reconnect, with no stream change.
- `getAccessPoint` goes through the bootstrap pacer (`_BOOTSTRAP_OPS`, `:61`), so re-resolving is rate-limited.

## Files
- Modify: `src/pocketquant/core/infra/exness/exness_client.py`, `tests/core_test/infra/exness/test_exness_client.py`, `docs/deployment.md` (`:115`)

## Steps
1. In `call()`, wrap `response = await self._send_paced(...)` in `try/except ExnessApiError as e`. When `e.code == "TRANSPORT"`, set `self._access_point = None`, log a warning `exness.access_point_reset` with `reason="transport"` and `op`, and re-raise.
2. After the send, when `response.status_code == 421`, set `self._access_point = None` and log the same event with `reason="421"`, then raise `_api_error(response)` as today.
3. Do not retry inside the same call. A data call is retried by its next scheduled run. An order becomes REJECTED, and the reconcile requested by the E1 fix calls `getTradingStateSnapshot`, which re-resolves the host. No new function is added, so the ratchet stays unchanged.
4. Tests, reusing the fake transport in `test_exness_client.py:72-81`:
   - a 421 on a data call raises, and the next call requests `getAccessPoint` again and is sent to the new host;
   - three transport errors raise `TRANSPORT`, and the next call resolves again;
   - a 200 keeps the cached host (the existing test at `:128` must stay green).
5. Docs: extend `docs/deployment.md:115` with: "A transport failure or a 421 clears it; the next call resolves it again."

## Validation
- `uv run python -m pytest tests/core_test/infra/exness -q` exits 0.
- ruff, pyright and the ratchet pass.
- Ship: `git push origin develop`.

## Risk
- If only the WS host fails while REST still succeeds, the cache is not cleared (L/M). `exness_ws.connection_failed` and `exness_ws.circuit_breaker_open` show it. This residual is accepted, because `sync_1m` calls REST every minute on the same host.
- A flapping network adds `getAccessPoint` calls (L/L). They are paced by the bootstrap pacer.

## Rollback
Revert the commit. There is no state outside the process.
