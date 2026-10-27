# Ultra verifier ranking

The verifier was `kongming` on Fable. It scored five anonymized candidates, each produced by an independent `planner` running on Opus from the same `evidence-packet.md`. The winner was materialized unchanged into `plan.md` and the `phase-*.md` files.

| Rank | Label | Source file | Faith | Ground | Exec | Safety | KISS | Total |
|---|---|---|---|---|---|---|---|---|
| 1 | A | `planner-ultra-candidate-4.md` | 18 | 19 | 19 | 19 | 16 | 91 |
| 2 | C | `planner-ultra-candidate-5.md` | 18 | 18 | 18 | 19 | 17 | 90 |
| 3 | B | `planner-ultra-candidate-1.md` | 15 | 15 | 16 | 16 | 17 | 79 |
| 4 | D | `planner-ultra-candidate-3.md` | 14 | 18 | 17 | 13 | 15 | 77 |
| 5 | E | `planner-ultra-candidate-2.md` | 12 | 16 | 12 | 15 | 15 | 70 |

## Hard constraints

All five candidates passed the literal hard constraints. The verifier still flagged two handover-contract problems:

- D deletes OKX helper functions with no user gate.
- E leaves out the Success, Goal and Target fields and the Verification sections.

## Why A won

A and C were nearly tied. A won on executability: its 80 tasks are fully fielded, the load-bearing code is written inline, and every Verify step is mechanical. Its grounding was also slightly tighter.

The verifier rated C's approach to the metric gate, which predicts the numbers before editing, as the better engineering choice. That is why its confidence in the result is medium rather than high.

## Weaknesses of the winner raised for validation

1. The metric gate in task T5.5 will almost certainly fire. Other candidates project about 41% tiny functions and about 45 delegations. The user should decide the target before execution starts.
2. Task T7.7 adds a per-subscription `broker` field. This is an additive change to the public API, and there is no global live kill switch to go with it.
3. `IBroker.fills_async` changes a core port. A check for `broker_type != "paper"` would avoid that.
4. T2.4 needs Docker/testcontainers. T1.9 runs the spike over ssh inside the prod container.
5. D6 hard-codes "19 checks" for `11-verify.sh`. The script prints `N/M passed, W warnings, F failures`, so the assertion should be `0 failures`.

## Verifier receipt

ultra: picked=4/5 margin=low unanimous=no rejected_all=no
