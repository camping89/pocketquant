# TODO — Deflated Sharpe / PBO / CSCV: the overfitting-aware evaluation direction

Deferred from the hybrid backtest-rubric work (`scripts/rubric/`). The rubric scores *individual runs*; this doc captures the *multiple-testing / overfitting* layer that the current data cannot support yet. Read before refactoring how strategies are developed and swept.

## Why this is deferred, not skipped

The rubric answers "is this one run healthy?". It cannot answer "did we fool ourselves by picking the best of many trials?" — the question that separates a real edge from a data-mined artifact. That question needs a **family of trials of the same strategy** (a parameter sweep, or many configs of one logic), which the DB does not contain today:

- 6 finished runs across **3 different strategies**, default params, **no sweep**.
- DSR needs `N` = number of trials to deflate a Sharpe; PBO needs a `trials × time-splits` performance matrix.

Applying either to the current data would produce numbers that look rigorous but mean nothing (deflating against N≈1 per family; ranking across strategies that are not the same family). So: build the per-run rubric now; build this when a sweep exists.

**What the rubric covers instead (single-run robustness that IS computable now):** bootstrap of trade order → maxDD distribution, and PSR (single return series, no multiple-testing correction). These bound *sampling* uncertainty within one run. They do NOT correct for *selection across trials* — that is the gap DSR/PBO fill, and only once a sweep exists. Boundary: PSR lives in the rubric; DSR (= PSR against a deflated benchmark `SR*`) lives here.

## Prerequisite: a sweep harness

Note (memory): the old `/backtest/optimize` async-queue path was removed in the 2026-06-29 single-run refactor. Reviving overfitting analysis requires re-introducing a way to run **many parameterizations of one strategy over one symbol/interval** and persist each trial's return series. Minimum needed per trial:

- strategy_code + the exact parameter vector (the thing being swept)
- per-period returns (ideally per-bar mark-to-market, not just trade-keyed) — DSR/PSR need a return series with estimable skew/kurtosis
- a stable time index shared across trials (so trials can be split into the same IS/OOS folds)

Without persisted per-trial return series aligned on a common time index, neither method is computable.

## Method 1 — Probabilistic Sharpe Ratio (PSR)

Already partially in scope for the rubric (single-run, no multiple-testing). Included here for completeness because DSR is built on it.

PSR estimates the probability that the *true* Sharpe exceeds a benchmark `SR*`, correcting for sample length, skewness, and kurtosis of returns:

```
PSR(SR*) = Φ( (SR_hat − SR*) · sqrt(n − 1)
              / sqrt(1 − γ3·SR_hat + ((γ4 − 1)/4)·SR_hat²) )
```

- `SR_hat` — observed Sharpe (same frequency as returns)
- `n` — number of return observations
- `γ3, γ4` — skewness, kurtosis of returns
- `Φ` — standard normal CDF
- `SR* = 0` for "is the Sharpe reliably positive?" (use 0 at n=6-run scale; document the choice)

Interpretation: PSR > 0.95 ⇒ Sharpe reliably above `SR*`. Fat tails (high γ4) and negative skew *lower* PSR — a high Sharpe on ugly-tailed returns is less trustworthy.

## Method 2 — Deflated Sharpe Ratio (DSR)

DSR = PSR evaluated against a **deflated benchmark** `SR*` that accounts for having selected the best of `N` trials. The more configurations tried, the higher the bar a Sharpe must clear to be called real.

The deflated benchmark uses the dispersion of Sharpes across trials and the expected maximum of `N` draws:

```
SR*  =  sqrt(Var[{SR_n}]) · [ (1 − γ_euler)·Z⁻¹(1 − 1/N)
                              + γ_euler·Z⁻¹(1 − 1/(N·e)) ]
```

- `Var[{SR_n}]` — variance of the Sharpe ratios across all `N` trials
- `N` — number of trials actually run (must be recorded honestly — the whole point)
- `γ_euler` — Euler–Mascheroni constant ≈ 0.5772
- `Z⁻¹` — inverse standard normal CDF
- `e` — Euler's number

Then `DSR = PSR(SR*)` with that `SR*`. DSR > 0.95 ⇒ the selected strategy's Sharpe is significant *after* correcting for selection bias, sample length, and non-normality.

Practical requirement: record **every** trial's return series when developing one strategy (e.g. all 100 sweep runs), not just the winner. Underreporting `N` inflates DSR — defeats the purpose.

## Method 3 — Probability of Backtest Overfitting (PBO) via CSCV

Model-free, non-parametric estimate of P(overfit). Combinatorially Symmetric Cross-Validation:

1. Build matrix `M`: rows = time slices, columns = trials (each column a trial's per-slice performance).
2. Split the `T` time slices into `S` disjoint sub-slices (S even, e.g. 16); form all `C(S, S/2)` combinations as in-sample (IS), complement as out-of-sample (OOS).
3. For each split: pick the trial that ranks best IS; find its rank OOS.
4. Logit of the OOS relative rank → distribution across all splits.
5. **PBO = fraction of splits where the IS-best trial lands in the bottom half OOS.**

Also yields: performance degradation (IS-vs-OOS regression slope), probability of loss OOS, stochastic dominance. High PBO (e.g. > 0.5) ⇒ IS selection does not carry to OOS ⇒ the "edge" is overfit.

CSCV is symmetric (IS/OOS interchangeable), model-free, and gives small-error PBO estimates — the reason it is the standard over a single holdout.

## How this changes strategy development

The refactor direction the user flagged: stop treating a single backtest run as evidence. Instead:

- Development produces a **sweep of trials**, all persisted with return series + parameter vectors + shared time index.
- Selection of the "final" params is gated by **DSR > threshold** (not raw Sharpe) and **PBO < threshold**.
- The per-run rubric (`scripts/rubric/`) becomes the *within-trial* health check; DSR/PBO become the *across-trial* selection gate. Two layers, different questions.

## Build order when picked up

1. Sweep harness that persists per-trial return series on a common time index (prerequisite — nothing works without it).
2. PSR (cheap, single-series; also upgrades the rubric's robustness axis).
3. DSR on top of PSR once `N` trials exist.
4. CSCV/PBO matrix pipeline (heaviest; needs the trials × slices matrix).
5. Wire DSR/PBO as a selection gate into strategy development.

## Sources
- Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- "Deflated Sharpe ratio" — https://en.wikipedia.org/wiki/Deflated_Sharpe_ratio
- Bailey, Borwein, Lopez de Prado, Zhu, "The Probability of Backtest Overfitting" — https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- PBO / CSCV reference implementation (R) — https://cran.r-project.org/web/packages/pbo/readme/README.html
