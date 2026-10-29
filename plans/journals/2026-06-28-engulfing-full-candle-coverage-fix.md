# Engulfing Full-Candle Coverage Fix: Wick Omission Caught in User Testing

**Date**: 2026-06-28 23:55  
**Severity**: High  
**Component**: Pattern detection (Python + TypeScript), golden fixtures  
**Status**: Resolved  

---

## What Happened

User reported a false-positive engulfing detection: a candle whose body engulfed the previous body but whose range (wick) sat strictly inside the previous range was incorrectly flagged as engulfing. The detector returned `is_engulfing=True`, `rejection_wick_pct=<low value>`, but the actual candle never had the high and low wicks to cover the full prior candle.

Root cause: Both `detect_engulfing` (Python) and `detectEngulfing` (TypeScript) checked **body coverage only** (open/close comparisons). They ignored the wick (high/low) coverage requirement. A strict-body engulfing is not a valid candlestick engulfing pattern; the pattern requires the entire range to contain the previous range.

Fix deployed: Added full-candle coverage conditions to both runtimes:
- Bullish: `high >= prev_high AND low <= prev_low` (in addition to existing body check)
- Bearish: same condition (symmetrical)
- The `rejection_wick_pct` quality metric (close location in wick, strong/weak grade) remained independent and unchanged.

---

## The Brutal Truth

This is embarrassing. The engulfing implementation shipped 16 hours ago with a textbook definition hole — any candlestick reference defines engulfing as the entire candle covering the previous candle, not just the body. The prior session's fixture-lock + vitest parity checks caught off-by-one deque semantics, but neither caught the semantic gap: we tested the implementation against itself (both Python and TS did the same wrong thing) and never checked the implementation against the actual candlestick pattern definition.

What's worse: the first user who ran a real backtest immediately saw the false positive. The detector was passing every fixture case because the **fixture itself only had full-wick-coverage examples** (we never added a body-engulfing-without-wick regression case). This is a validation debt: we locked parity early, but we didn't validate the locked behavior against the domain definition.

The fix was trivial (two lines per runtime). The frustration is that a single regression test case (`high=prev_high+1, low>prev_low`, both bullish and bearish) would have caught this in the prior session. We had vitest running. We had golden fixtures. We just didn't think to test the boundary.

---

## Technical Details

### Files Changed

| File | Change | Lines |
|---|---|---|
| `src/pocketquant/core/domain/strategy/patterns/engulfing_detector.py` | Added `high >= prev_high and low <= prev_low` to `is_bullish()` and `is_bearish()` check. Docstring "strict-body engulfing" → "full-candle engulfing". | 2 per method |
| `web/src/lib/indicators/engulfing.ts` | Mirrored Python condition: `high >= prevHigh && low <= prevLow`. | 2 per method |
| `tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json` | Added 4 regression cases: bullish/bearish with body engulfed but wick inside (expected `is_engulfing=false`). | 4 cases |
| `web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` | Byte-identical copy of Python fixture (parity lock enforced). | 4 cases |
| `src/pocketquant/core/domain/strategy/services/engulfing.py` | Docstring updated to reflect full-candle definition. | 1 line |
| `docs/swing-pivot-key-level.md` | Chart toggle description: "strict-body" → "full-candle engulfing". | 1 line |

### Golden Fixture Parity Lock

The fixture JSON was updated with 4 new regression cases, all added identically to both files:

```json
{
  "name": "bullish_body_engulfs_but_low_inside_prev",
  "prev": { "open": 100.0, "high": 100.5, "low": 97.5, "close": 98.0 },
  "curr": { "open": 97.9, "high": 101.0, "low": 97.8, "close": 100.5 },
  "expected": { "is_bullish": false, "is_bearish": false, "rejection_wick_pct": 1.0 }
},
{
  "name": "bullish_body_engulfs_but_high_inside_prev",
  "prev": { "open": 100.0, "high": 100.5, "low": 97.5, "close": 98.0 },
  "curr": { "open": 97.0, "high": 100.3, "low": 96.0, "close": 100.2 },
  "expected": { "is_bullish": false, "is_bearish": false, "rejection_wick_pct": 1.0 }
},
{
  "name": "bearish_body_engulfs_but_low_inside_prev",
  "prev": { "open": 98.0, "high": 100.5, "low": 97.5, "close": 100.0 },
  "curr": { "open": 101.0, "high": 101.2, "low": 97.6, "close": 97.8 },
  "expected": { "is_bullish": false, "is_bearish": false, "rejection_wick_pct": 1.0 }
},
{
  "name": "bearish_body_engulfs_but_high_inside_prev",
  "prev": { "open": 98.0, "high": 100.5, "low": 97.5, "close": 100.0 },
  "curr": { "open": 100.2, "high": 100.3, "low": 96.0, "close": 97.0 },
  "expected": { "is_bullish": false, "is_bearish": false, "rejection_wick_pct": 1.0 }
}
```

Byte-identical JSON verification:
```bash
diff tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json \
     web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json
# No output: files are identical.
```

### Test Results

- **pytest** (detector golden + strategy unit + backtest integration): 35 passed
- **vitest** (fixture parity): 13 passed (9 prior cases + 4 new regression)
- **eslint** (engulfing.ts): clean, no warnings
- **diff** 2 golden fixtures: byte-identical (no output)

### Test Execution Note

Running pytest required overriding `MONGODB_URL` and `REDIS_URL` because the repo's `.env` points at the production VPS and `conftest.py` has a guard refusing to run tests against prod. Set local overrides:

```bash
MONGODB_URL=mongodb://localhost:27017/test \
REDIS_URL=redis://localhost:6379/0 \
pytest tests/core_test/unit/domain/strategy/patterns/test_engulfing_detector.py -v
```

This guard is deliberate and correct; it prevents accidental test runs against live prod data.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Add coverage check to BOTH runtimes in lockstep | The fixture is byte-identical across Python ↔ TS; touching one detector without the other breaks parity. Both edited together, both fixtures updated identically. |
| Keep coverage gate separate from `rejection_wick_pct` | `rejection_wick_pct` is a quality grade (close location within range), orthogonal to the binary engulfing gate. Folding coverage into it would conflate two concerns. Left the metric untouched. |
| Add 4 explicit "reject" regression cases | Body-engulfs-but-wick-inside, across bullish/bearish × low-inside/high-inside. Makes the boundary the fix addresses visible in the fixture instead of implicit. |

---

## Root Cause Analysis

### Why the bug shipped:

1. **Fixture only tested happy paths.** The golden fixture had 9 cases, all with full-candle coverage. A body-engulfed-but-wick-inside case never appeared in the test suite, so the gap went undetected.

2. **Implementation validated against itself.** Fixture-lock parity caught Python ↔ TS divergence (deque off-by-one), but it validated both runtimes against **each other**, not against the candlestick pattern definition. If both implementations have the same semantic hole, parity tests pass.

3. **Domain knowledge gap.** The prior session focused on implementation correctness (off-by-one, fill routing, rejection grading) but didn't cross-check the pattern definition against a candlestick reference. "Engulfing" has a precise meaning; we implemented a subset.

### Why user testing caught it immediately:

Real backtest data has edge cases (gaps, small wicks, tight ranges) that curated fixture data avoids. Once a user ran a live backtest, the false positive appeared in the first few hundred bars.

---

## Lessons Learned

1. **Test the domain definition, not just the implementation.** Fixture parity validates that two implementations agree on behavior. Regression tests validate that behavior against the spec. Without both, you can ship a fast, consistent wrong implementation.

2. **Golden fixtures should include boundary cases.** Body-covers-previous + wick-inside is a natural boundary for engulfing. It should have been in the fixture from day one. Add at least one "reject this" case per boundary for every pattern definition.

3. **Domain semantic gaps are expensive.** A two-line fix is cheap. A user discovering your pattern detector is wrong on live data is expensive (credibility damage, backtest re-runs, confusion). A 30-second code review asking "does this match the textbook definition?" would have caught it.

4. **Fixture-lock is not sufficient validation.** Parity tests are a safety net for implementation divergence. They are not a substitute for domain review. Always sanity-check locked behavior against a reference (textbook, domain expert, live example).

5. **Quick validation beats elegant fixtures.** A single "reject body-but-wick-inside" case in vitest would have flushed this out in the prior session. We were clever with byte-identical JSON; we should have been paranoid with boundary cases.

---

## Next Steps

1. **Document engulfing pattern definition in code-standards.** Add a candlestick reference and a one-paragraph definition of engulfing (full-candle coverage) to `docs/code-standards.md` under Strategy Patterns, so future patterns include this context.

2. **Extend fixture test pattern.** For any strategy pattern fixture, mandate at least one "reject close candidate" case (body covers but wick inside, wick covers but body inside, etc.). Update testing guidance in docs.

3. **Re-validate backtest results.** Any backtest run with engulfing before this fix needs re-run to confirm results are not biased by false positives. Check strategy backtest history for engulfing runs before 2026-06-28 23:55 and flag for re-execution.

4. **Consider a pattern validator.** Long-term: write a `validate_pattern_definition(pattern_name, reference_description, fixture)` helper that spot-checks fixtures against common boundary cases (body engulfed but wick inside, etc.). Not urgent, but would reduce cognitive load on future patterns.

---

## Verification

| Check | Result |
|---|---|
| Regression test cases | 4 added; both Python and TS now reject body-but-wick-inside. |
| Fixture parity | 13 cases total (9 prior + 4 new), byte-identical JSON, diff clean. |
| Unit + integration tests | 35 pytest passed (detector golden + strategy unit + backtest integration). |
| TS parity tests | 13 passed (vitest fixture runner). |
| Lint | eslint on engulfing.ts clean, no warnings. |

---

Status: DONE  
Summary: Fixed engulfing false-positive by adding full-candle coverage check (high >= prev_high AND low <= prev_low) to both Python and TypeScript detectors; added 4 regression cases to golden fixture (byte-identical parity maintained); 35 pytest + 13 vitest cases pass.  
Concerns: None. But document the lesson: fixture parity validates consistency, not correctness. Add boundary cases early.
