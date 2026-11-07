---
name: phase10-exness-pending-stop-ws-gap-risk
description: Phase 10 (Exness close/pending/cancel) GO on 2026-11-02; the open pre-arming risk is a parked stop whose fill or placement lands while the WS is down
metadata:
  type: project
---

Phase 10 of plan 261101-0843 got GO on 2026-11-02 with no blocking issue. The carried risk: a parked Exness stop is tracked from the stream only, so a fill (or the placement ack) that lands while the WS is disconnected is lost; the next snapshot releases the stop as CANCELLED and marks the instrument unmapped, so the engine is flat while the venue holds a position (SL/TP still on it).

**Why:** WS drops are daily on this account (see [[exness-ws-failure-baseline-by-hour]]), so this is not a corner case once live is armed. `_recover_fill` covers market orders through operation status + deals; nothing equivalent exists for a parked stop.

**How to apply:** before any go-live advice, require re-adoption: in the gone-parked snapshot branch, look up the deal with `order_id == venue_id` before releasing. The docs Limitations bullet names "in transit" and "crash" but not a stream disconnect; treat that as a wording gap, not a falsehood. The stop fill event carries no `client_request_id` (spec: omitted for system-generated updates), so the fall-through link by `deal.order_id` is the right path.
