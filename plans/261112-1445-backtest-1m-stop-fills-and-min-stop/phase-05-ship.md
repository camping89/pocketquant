---
phase: 5
title: "Ship"
status: pending
priority: P3
effort: "1h"
dependencies: [4]
---

# Phase 5: Ship

## Goal
Merge the engine and strategy changes to `develop`. Release to `master` only on the owner's explicit yes. Open a paper subscription for C only if C survived phase 4.

## Tasks & Steps
1. Push `develop` and wait for develop CI to pass.
2. **Count stored parameters again.** Count, read-only, the prod subscriptions holding `stop_lookback`. If the count is not 0:
   - back up `subscriptions` with `mongodump`;
   - apply the reviewed rename right after the release (phase 3, step 4).
3. **Ask the owner** whether to release `develop` to `master`, in Vietnamese with a leading `Recommended:` line. State the live effect:
   - Fills are unchanged, because live paper already acts on 1m bars (phase 2, step 1).
   - The running Triple Screen paper subscriptions move to `stoploss_lookback=2`, which is 8 entry bars of lookback instead of 5.
4. **On yes:**
   - fast-forward `master` and watch the CI deploy;
   - confirm `/api/v1/health` and the trader lease;
   - confirm the subscriptions' parameters and states.
5. **If C survived phase 4,** ask the owner whether to open one paper subscription with C's exact parameters for 3 to 6 months (rubric G6). It measures fills, spread, slippage and swap.
6. **Docs:** update only what a reader needs. Candidate: a `docs/system-architecture.md` line saying that backtests fill on the finest stored interval, as live does, and what happens without 1m coverage.

## Verification
- develop CI is green, and on release, master CI and the deploy are green.
- The paper subscriptions keep their states; only the parameter change named in step 3 applies.
