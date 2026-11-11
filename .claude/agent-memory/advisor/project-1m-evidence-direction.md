---
name: project-1m-evidence-direction
description: As of 2026-11-09 the agreed next plan is a 1m strategy-evidence plan (Triple Screen 1m entry backtests); go-live stays parked until a set passes the backtest gate
metadata:
  type: project
---

Next plan agreed 2026-11-09 (advise report `plans/reports/advise-261109-1309-next-plan.md`): the plan backtests Triple Screen with a 1m entry (`1m,5m,15m`, `1m,15m,1h`) with no code change. Gate: net PF >= 1.2 and >= 100 trades over 12 months; passing sets get a 2-week paper reconciliation. Go-live (plan `261019-1957`, Phase 11 called off 2026-10-22 for "no profitable strategy") and the split-runtime bugs (api `BROKER_DISABLED`, strip flag) are out of scope.

**Why:** every 12-month Triple Screen backtest was net negative and one week of paper was too small to judge; the owner wants 1m evidence before any go-live decision.

**How to apply:** when advising on go-live or strategy work, check this plan's verdict lines first. Verify current state in `plans/` before relying on this.
