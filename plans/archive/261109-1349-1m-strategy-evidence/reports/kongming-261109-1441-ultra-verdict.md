# Ultra verifier verdict (kongming, Fable)

Five anonymized candidates (`reports/ultra/candidate-A..E.md`) were written from the same `reports/evidence-packet.md`. All five passed hard constraints H1-H5: Failure Protocol verbatim in every phase, no out-of-scope work, cost read from `config.contract_spec`, owner asks for master push / >1800 s / engine change, paper only for passing sets.

| Criterion | A | B | C | D | E |
|---|---|---|---|---|---|
| R1 faithfulness | 18 | 15 | 14 | 18 | 17 |
| R2 evidence | 18 | 16 | 16 | 18 | 18 |
| R3 executability | 18 | 11 | 16 | 16 | 11 |
| R4 design | 17 | 16 | 17 | 17 | 17 |
| R5 KISS | 16 | 14 | 14 | 15 | 17 |
| R6 ask hygiene | 17 | 12 | 12 | 19 | 14 |
| Total | 104 | 84 | 89 | 103 | 94 |

Winner: A, materialized unchanged. B and E poll a run for up to 3 h in one call, which breaks the 600 s tool cap.

Confidence: medium. A and D are close to equivalent.

## Winner defects surfaced to the owner (not fixed by the verifier)

1. The WINDOW rule avoids 00:00Z and 03:00Z, but `sync_repair` also runs at 12:00Z (`cron_expression="0 */12 * * *"`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py:819-824`, checked by the controller). `sync_integrity` runs at 04:00Z (`:812-818`), which is where the window opens.
2. Phase 06 entry gate "now >= last daycheck + 20 h" is a judgment, not a command output.
3. The Phase 02 compare URLs go beyond the packet.
4. Paper fills use no modelled spread (`broker_factory.py:41-57`), while the backtest charges 0.08. So paper cost per trade will look lower than backtest cost.

ultra: picked=A/5 margin=low unanimous=no rejected_all=no
