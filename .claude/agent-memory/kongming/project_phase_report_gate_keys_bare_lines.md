---
name: phase-report-gate-keys-bare-lines
description: Plan entry gates grep `^key=` at line start; a report that writes the key as a bullet or in backticks fails the next phase's gate (Phase 15 -> 16 d2_pushed_at, 2026-11-02)
metadata:
  type: project
---

Entry-gate greps in plan 261101-0843 (and the same cook convention elsewhere) anchor on `^key=`. A phase report must write such keys as bare lines (`d2_pushed_at=2026-11-02T08:43:47Z`), never as `- \`d2_pushed_at=...\``.

**Why:** On 2026-11-02 the Phase 15 report wrote `d2_pushed_at` as a backticked bullet; Phase 16 EG line 2 (`grep -c "^d2_pushed_at="`) printed 0, which would loop the phase into NOT_YET with no fix path (gate miss = "edit nothing"). Same family as [[phase15-d1-check-off-by-one]]: gate arithmetic/wording, not prod state, blocks the resume.

**How to apply:** At any post-phase checkpoint, run the next phase's gate greps against the just-written report before advising GO. Fix wording in the report (docs-only commit, no CI) before the next phase starts.
