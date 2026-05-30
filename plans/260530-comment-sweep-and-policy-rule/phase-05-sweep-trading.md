---
phase: 5
title: "Sweep trading"
status: completed
priority: P1
effort: "2.5h"
dependencies: [4]
---

# Phase 5: Sweep trading

## Overview

Sweep `pocketquant-trading` — 94 src files / 4353 loc + 10 test files / 752 loc, 152 full-line `#`. Live trading, OKX broker, strategy orchestration.

## Requirements
- Functional: redundant comments/docstrings removed per Keep Bar; test pass/skip counts identical to baseline.
- Non-functional: preserve OKX/external-broker quirk comments and strategy state-machine ordering notes.

## Architecture
Depends on core. `OKXBroker`, `StrategyAppService` lifecycle, order app services. External-system quirk comments (OKX API behavior, rate limits, idempotency) are KEEP. State-machine ordering / publish-before-subscribe notes are KEEP.

## Related Code Files
- Modify: `packages/pocketquant-trading/**/*.py` (src + tests), excluding venv/pycache.

## Implementation Steps
Follow Per-Phase Sweep Protocol:
1. `just test-pkg trading` → green baseline (infra up if needed).
2. Agent reads each src+test `.py`. KEEP OKX quirks, strategy lifecycle ordering, broker retry/idempotency notes. Remove restatements + banners + name-echo docstrings.
3. `just lint` → `just fmt`.
4. `just test-pkg trading` → green, same counts.
5. Commit: `refactor: trim redundant comments in pocketquant-trading`.

## Success Criteria
- [ ] `just test-pkg trading` green, counts match baseline
- [ ] `just lint` clean
- [ ] OKX quirk + strategy lifecycle why-notes preserved
- [ ] Commit made

## Risk Assessment
- Deleting broker-quirk notes that prevent future bugs. Mitigation: any comment referencing OKX/exchange behavior → KEEP.
