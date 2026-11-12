# Triple Screen with 1m fills: stop, target and rubric score

Plan: [261112-1445](../261112-1445-backtest-1m-stop-fills-and-min-stop/plan.md), phase 4. Symbol XAUUSD:EXNESS, Triple Screen `15m,1h,4h`, 2% risk per trade over the strategy stop.

## Verdict

- **A (frozen config): no real money, and reject.** G2, G3 and G4 fail. The score is 4 with 2 points open, so it cannot reach 10.
- **B (A plus `min_stop_atr=0.5`): no real money.** G2, G3 and G4 fail. The score is 7 with 4 points open.
- **C (walk-forward candidate): candidate for incubation, the plan's label.** C passed the engine-survival rule and G2. No gate failed, but G1, G3, G4 and G5 are open and the S criteria are unscored, because no out-of-sample data exists for C. This is not the rubric's "incubate" verdict. Paper trading would be C's first out-of-sample data.
- C has no shown edge. Its t over W of 2.74 is about what the best of 224 no-skill trials would show by luck (expected maximum t 2.80, DSR 0.47).

## Data (phase 1)

- Local 1m bars run from 2024-05-01T00:00Z to 2026-11-12T12:04Z, in 59862 15m buckets. E0 is 0, E1 is 0, E0_run is 0 and ratio is 0.0. Every 15m high and low equals its 1m aggregation.
- B0 reproduced the stored run `01a1c980` with 1991 trades and 0 differing rows.
- Prod received the 521645 older 1m bars before `C` = 2025-10-21T07:20:00Z, with 0 failed documents. No prod bar was rewritten.
- Phase 4 used local 1m bars, which all come from Exness REST. On prod, 1m bars are REST before `C` and live sync after it.
- Source: `.cache/p1/audit.txt`.

## Runs

| Id | Run id | fill_interval | Trades | Void counts |
|---|---|---|---|---|
| R0 | `01a1d075-9cf8-7030-bc2b-383697b04958` | 15m | 745 | 0 |
| A | `01a1d089-dd4f-7758-aad8-6d528c7b3fa5` | 1m | 1248 | 0 |
| B | `01a1d089-deac-75a6-9774-c96fbbde8322` | 1m | 1164 | 0 |
| C | `01a1d089-dfc3-7706-9707-e41b107645d2` | 1m | 550 | 0 |
| C1 | `01a1d089-e000-71cc-ab26-16c124a264da` | 1m | 487 | 0 |
| C2 | `01a1d089-e02e-76b4-999f-7ba1420f509d` | 1m | 442 | 0 |
| C3 | `01a1d089-e1da-751c-b842-0639ae99e3a6` | 1m | 403 | 0 |

- **Replica check (R0):** 739 matched, 0 unmatched, 0 disagreeing, on R net of commission (`.cache/p4/replica-R0.txt`).
- **Speed:**
  - A solo run on 2024-05 replayed about 7 934 events per second; W holds 955 273 events.
  - The projection for W was about 120 s.
  - The six main runs in parallel took about 217 s of replay each and 236 s wall time in total.

## A against stored run `01a1c980`

Keyed on side and 15m entry bucket, over W (`.cache/p4/classes.txt`):

- The union holds 1293 trades.
- 35 have the same entry and the same exit.
- 1205 have the same entry and a different exit. 84 of those are old same-bar stop-loss exits that the 1m fill removed.
- 45 are only in the old run, and 8 only in the new run.
- Sum R is +17.0 for the old run and +109.4 for the new.

This does not show that the 1m fill improved A. The 1205 changed exits are not broken down further, and they may include plain 15m against 1m timestamp differences.

## Rubric

Segment labels by entry time: P is 2024-05-01 to 2025-11-09 and Y is 2025-11-09 to 2026-11-09. For A and B, P is out of sample (its second read) and Y is in sample. For C, every segment is selection data. Source: `.cache/p4/score.txt`.

### Gates

| Gate | A | B | C |
|---|---|---|---|
| G1 | open: ambiguity clause met (0 E0/E1 trades, 1 same-1m-bar exit of 1248); swap not charged | open: as A, 0 same-1m-bar exits | open: as A, 0 same-1m-bar exits |
| G2 | fail: Y t 1.81 | fail: Y t 1.95 | pass: joined t 3.45, n 743 |
| G3 | fail: P mean +0.0654, t 0.89, n 764 | fail: P mean +0.0649, t 1.22, n 710 | open: no OOS data |
| G4 | fail: P_dd50 0.2417 over W, 0.4648 over P; Kelly 0.021 over P | fail: P_dd50 0.1380 over P; Kelly 0.040 over P, so half-Kelly equals the planned 2% (boundary pass) | open: no OOS data |
| G5 | pass: P mean at 2x cost +0.0398 | pass: +0.0484 | open: no OOS data |

- The G3 trend adjustment was not computed. For A and B it does not matter, because t already fails.
- **G2 for C** joins R0's 193 coarse-fill trades before 2024-05 with C's 550 1m-fill trades, so the join is not seamless. The 1m run starts flat with an empty swing window. Six of the coarse trades are the pre-2023-01-09 trades that the replica check excluded. C's t over W alone is 2.74.
- **DSR** (reported, not gating). It assumes N independent no-skill trials, trial Sharpe variance 1/(n-1), and per-trade Sharpe with skew and kurtosis taken from the R list. Correlated trials make the effective N smaller than 224.

| Sample | n | t | DSR at N=224 | DSR at N=50 |
|---|---|---|---|---|
| A, Y | 481 | 1.81 | 0.12 | 0.29 |
| B, Y | 451 | 1.95 | 0.17 | 0.36 |
| C, joined | 743 | 3.45 | 0.75 | 0.89 |
| C, W | 550 | 2.74 | 0.47 | 0.68 |

### Scored criteria (A and B on P)

| # | A | B |
|---|---|---|
| S1 SQN-100 | 0 (0.32) | 0 (0.46) |
| S2 PF in R | 1 (1.157) | 1 (1.184) |
| S3 WFE | 2 (32.9 / 60.1 R per year) | 2 (30.3 / 50.3) |
| S4 PBO | open (not computed) | open |
| S5 plateau | open (no neighbour runs) | open |
| S6 concentration | 0 (-46.6 without top 5) | 0 (-9.0 without top 5) |
| S7 consistency | 0 (0.47 positive months) | 1 (0.53; short side -6.0) |
| S8 MAR | 0 (0.60) | 1 (1.14) |
| S9 pain | 0 (ulcer 30.5) | 0 (ulcer 22.2) |
| S10 cost/stop | 1 (2.56%) | 2 (1.65%) |
| Total | 4, 4 points open | 7, 4 points open |

The S3 in-sample denominator is Y re-priced with 1m fills, not the coarse year that chose A.

## C in detail

- **Decision rule:** passes. Mean R over W is +0.1501, above 0, and t is 2.74, at least 1.5. The diagnostic sum R of +82.5 is inside 67.7..91.7, so no engine investigation was needed.
- **Segments:**
  - P has mean +0.1955 and t 2.81.
  - Y has mean +0.0759, t 0.85 and n 189.
  - The sample cannot separate decay from noise (inference).
- **Profit anatomy over W:**
  - 273 take-profit exits average +1.323 R, with a maximum of 5.23 and a 90th percentile of 2.69.
  - 277 stop-loss exits average -1.006 R.
  - The target is the farther of 1 R and the 10-bar swing extreme, so `risk_reward=1.0` is a floor.
  - With every trade's R capped at +1.0, sum R would be -6.9. The whole profit comes from targets beyond 1 R.
- **Sides:** longs have n 271, mean +0.254 and t 3.56. Shorts have n 279, mean +0.049 and t 0.60. The trend adjustment is not computed, and this is the main unknown behind G3.
- **W values, informational only, not scores:**
  - P_dd50 0.0022 and Kelly 0.099;
  - mean R at 2x cost +0.1384;
  - MAR 2.08, ulcer 15.5, 406 days under water;
  - positive months 0.65;
  - sum R without the top 10 trades +42.5.
- **Power:**
  - sd(R) is 1.286.
  - At G3's minimum of 300 trades, t = 2 needs a mean of +0.149 or more.
  - At Y's mean, t = 2 needs about 1149 trades.
- **Not counted:** a stop and a target touched in the same 1m bar. `same_1m_bar_exits` only counts an entry and its exit in the same minute.
- **P_dd50 method:** an i.i.d. bootstrap, so it ignores loss clustering.

## C1 to C3 (informational)

These are trials 222 to 224, run on the data that selected C. They never change C's verdict.

| Run | Buffer | n | mean R | t | sum R |
|---|---|---|---|---|---|
| C | 0.0 | 550 | +0.1501 | 2.74 | +82.5 |
| C1 | 0.1 | 487 | +0.1543 | 2.75 | +75.1 |
| C2 | 0.2 | 442 | +0.1088 | 1.91 | +48.1 |
| C3 | 0.3 | 403 | +0.0814 | 1.42 | +32.8 |

Sum R falls as the buffer grows. C sits at the edge of the grid, not on a plateau.

## Costs not modelled

- **Swap:** not charged in any run. C holds a trade for about 38 hours on average.
- **Trial count:** 224.

## Next step

1. Ship the engine and strategy changes (phase 5).
2. The owner decides whether to paper-trade C as its first out-of-sample data (G6). Before that, I recommend charging swap in the backtest and computing the G3 trend adjustment, because the long side carries most of C's result.

## Unresolved questions

- Does the owner want C on paper now, or only after swap and trend adjustment are modelled?
