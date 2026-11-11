# Triple Screen stop_lookback sweep

The sweep ran Triple Screen on XAUUSD:EXNESS from 2025-11-09 to 2026-11-08. Costs were slippage 0.1 bp, spread 0.08 and commission 0.035 per oz per side. It covered five interval sets, both entry modes (`stop` + `exit_mode=strategy`, `market` + `exit_mode=sl_tp`) and `stop_lookback` 5, 10, 20, 40 and 80. That makes 50 runs, and all of them finished. The 1m sets at lookback 5 are the reruns in `backtest-261110-1150-slippage-0-1bp-rerun.md`. Gate: `profit_factor >= 1.2` and `total_trades >= 100`.

## Profit factor (trades)

| Set | Mode | lb 5 | lb 10 | lb 20 | lb 40 | lb 80 |
|---|---|---|---|---|---|---|
| 15m,1h,4h | stop | **1.234** (926) | **1.256** (890) | **1.358** (660) | **1.424** (508) | **1.456** (489) |
| 15m,1h,4h | market | 0.943 (2486) | 0.974 (2067) | 1.115 (739) | **1.395** (126) | 1.886 (11) |
| 5m,15m,1h | stop | 0.819 (3652) | 0.834 (3362) | 0.904 (2388) | 0.908 (2076) | 0.911 (1977) |
| 5m,15m,1h | market | 0.849 (8625) | 0.889 (6247) | 1.185 (1135) | 1.134 (288) | **1.460** (126) |
| 1h,4h,1d | stop | 0.668 (275) | 0.667 (259) | 0.690 (196) | 0.689 (134) | 0.706 (121) |
| 1h,4h,1d | market | 0.832 (722) | 0.836 (671) | 0.721 (309) | 0.877 (31) | 0.675 (21) |
| 1m,5m,15m | stop | 0.885 (14943) | 0.892 (14507) | 0.947 (11432) | 0.991 (8542) | 0.999 (8041) |
| 1m,5m,15m | market | 0.843 (36847) | 0.861 (31827) | 0.925 (14604) | 1.108 (1889) | 1.129 (727) |
| 1m,15m,1h | stop | 0.811 (7798) | 0.814 (7522) | 0.814 (7369) | 0.830 (6633) | 0.890 (4007) |
| 1m,15m,1h | market | 0.834 (27265) | 0.851 (22492) | 0.882 (19850) | 0.904 (15781) | 1.015 (3493) |

Bold cells pass the gate. 15m,1h,4h market at lb 80 has PF 1.886 but only 11 trades, so it fails.

For 15m,1h,4h stop, the return over the year is +3.8% to +6.0% and the max drawdown is under 1% at every lookback. Win rate rises from 25% to 38%.

## Measured

- **One set passes at every lookback.** It is 15m,1h,4h stop, and its PF rises with every step of lookback.
- **Wider stops raise PF almost everywhere.** The exceptions are 1h,4h,1d and 5m,15m,1h market between lb 20 and 40.
- **A 1m entry bar does not pass at any lookback.** The best 1m run is 1m,5m,15m market at lb 80, with PF 1.129.
- **1h,4h,1d fails at every lookback.**
- **Market-mode trade counts collapse as lookback grows** (15m,1h,4h: 2486 trades at lb 5, 11 at lb 80). The cause was not checked.

## Caveats

- Each of these runs was picked from many tries on one 12-month window: 50 sweep runs plus earlier ones. A pass here is a lead, not proof.
- Absolute returns are small because the 10% exposure cap sets every position size.
- The rising-PF pattern on 15m,1h,4h stop is smooth across five lookbacks. That makes a single lucky value less likely, but it does not rule out a window effect (inference).

## Execution notes

- The first 27 runs went one at a time through the api route.
- The last 19 ran as two parallel lanes. Each run was its own Python process inside the api container, using the app's DI container, so the second CPU core was used.
- Under two lanes, load was about 3 on 2 cores and the lowest available RAM was about 600 MB. The trader stayed at 3-4% CPU.
- All temporary scripts were removed from the VPS and the container.

## Unresolved questions

- Should 15m,1h,4h stop be validated on data outside this window (older 15m bars, if they exist) or on forward paper?
- Should Triple Screen move to Elder's canonical trigger and stop (taken from the middle bar) before any paper test?
