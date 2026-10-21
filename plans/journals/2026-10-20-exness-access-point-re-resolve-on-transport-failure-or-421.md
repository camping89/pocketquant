---
title: Exness access point re-resolve on transport failure or 421
date: 2026-10-20
summary: ExnessClient now clears the cached access point on TRANSPORT or 421 so the next call rediscovers it
---

# Exness access point re-resolve on transport failure or 421

## What happened
`ExnessClient.access_point()` cached the per-account host for the whole process, so a moved or dead access point kept every REST call and every WS reconnect on the bad host until a restart.

## Change
- `ExnessClient.call` clears `_access_point` and logs WARNING `exness.access_point_reset` (`reason`, `op`) when `_send_paced` raises `ExnessApiError` with code `TRANSPORT` (after 3 attempts), and when the answer is HTTP 421. The error is still raised; there is no retry inside the same call.
- Two tests pin it: a 421 makes the next call rediscover and go to the new host; three `ConnectError`s raise `TRANSPORT` and the next call rediscovers. Both fail without the change.
- `docs/deployment.md` states when the access point is re-resolved.
- Commit `0a5eb65` on `develop`, pushed.

## Hiccup
A docstring edit joined two lines and tripped ruff E501; rewrapped with no wording change after counsel.

## Risk left
Only the WS host failing while REST works does not clear the cache; `exness_ws.connection_failed` shows it.

## Next steps
Phase 04 (integrity on unexpected bars).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
