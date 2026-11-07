---
name: feedback-single-plan-runner-order
description: Extend one plan dir instead of creating new plans; phase file numbers must equal execution order because a runner cooks phases strictly by number
metadata:
  type: feedback
---

Keep one effort in ONE plan dir; when extending, add phases to the existing plan instead of creating a sibling plan. Number phase files so numeric order equals execution order (renumber with `git mv`, fix every cross-reference, keep user gates inside phases).

**Why:** User (2026-10-20, Exness go-live plan) cooks plans later with a runner that executes `phase-NN` files in strict numeric order; a separate plan or out-of-order numbering breaks that.

**How to apply:** When new work must run between existing phases, renumber. Note in plan.md when two phases are independent by file ownership but still run sequentially under the runner. Split phases with a user/manual round in the middle (e.g. tunnel code vs DNS cutover) so each file is one runnable step.
