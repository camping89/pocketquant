---
name: feedback-no-waiting-no-fake-data
description: Owner rejects plan steps that wait on live events or calendar windows; wants them replaced by evidence that already exists (prod ids, tests), never by synthetic prod data
metadata:
  type: feedback
---

When a plan phase is parked on "wait for the next live event" or "wait N days", the owner calls it a waste of time and asks to "simulate and finish". Resolve this by re-reading evidence that already exists (prod documents, logs, named tests) and amending the plan wording, not by writing synthetic orders/positions/trades to prod.

**Why:** 2026-11-02, Phase 17 of the MTF plan sat NOT_YET on four paper observations and a 7-day 1d window; three observations already had prod ids nobody had read back. The owner accepted "existing prod evidence + tests" over fake data and over a local simulation, and chose to drop a dated re-check rather than keep the plan open.

**How to apply:** in any advisory on a blocked phase, first list what evidence is already on prod or in tests, then propose plan amendments (owner-decision rows) that bind to it; offer "skip with test citation" as the fallback; present the dropped-wait cost as a trade-off, not a blocker. Keep the irreversible steps (prod deletes) as separate explicit yeses. See [[pocketquant-one-plan-to-cook]] for the owner's preference to extend rather than split plans.
