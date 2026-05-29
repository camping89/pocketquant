---
phase: 2
title: "Trim Handler Pipelines"
status: completed
priority: P2
effort: "1h"
dependencies: [1]
---

# Phase 2: Trim Handler Pipelines

## Overview
Trim `handler-pipelines.md` (831L, largest doc) to remove the flow-narrative that overlaps `system-architecture.md`. Keep only the per-handler pipeline detail that exists nowhere else. Replace removed narrative with a one-line link back to system-architecture.

## Requirements
- Functional: per-handler pipeline descriptions (the 26–27 handlers across market-data/backtest/strategy/trading) remain fully intact.
- Non-functional: sections that merely restate system-architecture's "Data Pipelines (Overview)", "Clean Architecture Request Flow", and "Key Data Flows" are removed or reduced to a pointer.

## Architecture
`handler-pipelines.md` current sections (from heading scan):
- §Handler Categories
- §A Market Data Handlers (13)
- §B Backtesting Handlers (5)
- §C Strategy Handlers (4)
- §D Trading Handlers (4)
- §Key Data Flows  ← overlaps system-architecture §Data Pipelines + §Key Data Flows
- §Handler Registration
- §Performance Notes  ← partial overlap with system-architecture §Performance & Security

Keep §A–§D (unique per-handler detail) + §Handler Categories + §Handler Registration.
Trim §Key Data Flows: if it duplicates system-architecture's flow sections, delete and replace with: `> End-to-end data flows: see [system-architecture.md](./system-architecture.md#data-pipelines-overview).`
Trim §Performance Notes: keep only handler-specific perf notes; drop generic ones already in system-architecture.

## Related Code Files
- Modify: `docs/handler-pipelines.md`

## Implementation Steps
1. Re-read `docs/handler-pipelines.md` §Key Data Flows and §Performance Notes in full.
2. Re-read `docs/system-architecture.md` §Data Pipelines (Overview), §Clean Architecture Request Flow, §Key Data Flows (lines ~497, ~653, ~739) to confirm what overlaps.
3. Delete the overlapping flow narrative in handler-pipelines §Key Data Flows; replace with a single pointer line to system-architecture.
4. Reduce §Performance Notes to handler-specific items only.
5. Verify per-handler sections §A–§D untouched and handler count still matches reality (cross-check against `HandlerProvider` count noted as 27 in CLAUDE.md / system-architecture).
6. Confirm intra-doc anchors still resolve after section removal.

## Success Criteria
- [ ] §A–§D per-handler detail fully preserved.
- [ ] Overlapping flow narrative replaced by a pointer to system-architecture.
- [ ] `handler-pipelines.md` line count meaningfully reduced (target ~500–600L from 831L) without losing per-handler content.
- [ ] No broken intra-doc anchor links.

## Risk Assessment
- **Risk:** deleting a flow detail that is NOT actually in system-architecture. **Mitigation:** Step 2 confirms overlap before deleting; when in doubt, keep in handler-pipelines.
- **Risk:** anchor target for the new pointer (`#data-pipelines-overview`) wrong. **Mitigation:** verify the exact slug system-architecture generates for that heading.
