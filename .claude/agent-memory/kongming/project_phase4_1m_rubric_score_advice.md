---
name: phase4-1m-rubric-score-advice
description: 2026-11-12 advice on plan 261112-1445 phase 4 rubric marks for A/B/C with 1m fills, the DSR assumption, and C's profit anatomy
metadata:
  type: project
---

Advice given 2026-11-12 before the task 4.9 report of plan 261112-1445 (1m stop fills, min stop).

- A and B: no real money (G2, G3, G4 fail on P/Y). A scores 4 with 2 open (max 8, reject by score). B scores 7 with 2 open (max 11), so B is "no real money by gates", not "reject by score". B's Kelly sub-test is a boundary value (0.040 on a 0.001 grid), not a fail.
- C: G2 pass on the joined sample (t 3.45, n 743); t over W 2.74. "Candidate for incubation" is a plan label (phase file line 43), not the rubric's "incubate" verdict; G1, G3, G4, G5 and S stay open.
- DSR: computed ad hoc under the rubric's own null (224 independent no-skill trials, trial SR variance 1/(n-1), per-trade SR, skew and kurtosis from the R list). Expected best t of 224 trials = 2.80. DSR: A Y 0.12, B Y 0.17, C joined 0.75, C over W 0.47. Not in score.py at the time.
- C anatomy: TP is the farther of 1 R and the 10-bar swing extreme (triple_screen_strategy_service.py:192-198). 273 TP exits average +1.32 R (max 5.23); 277 SL exits average -1.006 R. With every TP capped at 1 R the sum would be about -6 R, so the whole profit comes from the roughly 20% of targets beyond 1 R. Long mean +0.254 (n 271), short +0.049 (n 279).
- P vs Y for C: difference in mean 0.12 R, t about 1.06, so neither decay nor stability is shown.

**Why:** the verdict wording decides whether C goes to paper; the earlier OOS diagnosis found long profit was gold drift ([[triple-screen-oos-diagnosis-and-rubric]]).
**How to apply:** when C is scored again on new data, compute the trend adjustment per side first and reuse the same DSR assumption so the numbers stay comparable.
