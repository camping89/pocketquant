---
status: completed
---

# Phase 02 — Volume aggregation: delta-pass adapter (Bug #2)

## Context links

- Brainstorm Bug #2: [`brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md`](../reports/brainstorm-260507-1835-vps-bars-mismatch-tv-pro-fix.md) §"Bug #2"
- Research code skeleton: [`researcher-02-volume-and-audit.md`](./research/researcher-02-volume-and-audit.md)
- Phase 01 deliverable: `BinanceWebSocketClient` emits `@aggTrade` with `q` = per-trade delta volume
- File: `pocketquant-core/src/pocketquant/core/domain/bar/services/bar_builder.py`
- Caller: `pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py:79-114`
- Adapter: `pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py` — `on_quote_update`

## Overview

- **Priority:** P1 — independent fix, ships in parallel with Phase 01
- **Status:** pending
- **Effort:** 1h
- **Description:** With `@aggTrade` feeding **delta** volume per event (Phase 01), `BarBuilder.add_tick()` current code (`self.volume += volume`) is naturally correct. The fix scope reduces to: **ensure the WS→tick adapter (`QuoteAppService.on_quote_update`) passes the per-event delta `event.q`, never a cumulative value**. Add lightweight clamping (no negatives), drop the originally proposed baseline-diff logic.

## Key insights

- `@aggTrade` event `q` is per-trade quantity (delta). Direct sum across ticks within a bar = correct bar volume.
- Phase 01 mapper `aggtrade_to_quote_dict()` already emits `volume = float(q)` (delta).
- `BarBuilder.add_tick()` summing semantics (`self.volume += volume`) becomes correct under delta input — no rewrite needed.
- The bug was the previous TV WS path emitting cumulative session volume. Removing TV (Phase 03) eliminates that pathway.
- Defensive checks: clamp negative `q` to 0 (impossible per Binance spec but cheap insurance); ignore zero-quantity events (no-op).

## Requirements

### Functional
- `QuoteAppService.on_quote_update(quote_data: dict)`:
  - Reads `quote_data["volume"]` (already delta from Phase 01 adapter)
  - Constructs `QuoteTick(volume=delta)` with `delta = max(0.0, raw)` if `raw is not None`
  - Skips processing entirely if `delta == 0.0` (no volume contribution; OHLC still updates)
- `BarBuilder.add_tick(price, volume, timestamp)`:
  - Behavior unchanged: `self.volume += volume` if `volume is not None`
  - Add docstring contract: "volume is per-tick DELTA, not cumulative"
  - No new fields, no baseline tracking

### Non-functional
- Pure domain logic — no I/O, no clock dependency
- Backwards compatible: signature unchanged
- Zero new dependencies

## Architecture

```
BinanceWebSocketClient (@aggTrade)
        │
        │ event {"q": "0.05", "p": "50000", "T": ...}
        ▼
binance_mappers.aggtrade_to_quote_dict
        │
        │ {"volume": 0.05, "last_price": 50000, "timestamp": ...}  (delta)
        ▼
QuoteAppService.on_quote_update
        │
        │ QuoteTick(volume = max(0.0, 0.05))  (clamped delta)
        ▼
BarAppService._process_tick_for_interval
        │
        │ current_bar.add_tick(price, 0.05, ts)
        ▼
BarBuilder.add_tick
        │
        └── self.volume += 0.05   (delta-sum; current code correct)
```

## Related code files

**Modify:**
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_app_service.py` — clamp `volume` to `max(0.0, raw)`; skip zero-volume ticks for volume aggregation (still update OHLC if price present)
- `packages/pocketquant-core/src/pocketquant/core/domain/bar/services/bar_builder.py` — add docstring on `add_tick` clarifying delta contract; no logic change
- `packages/pocketquant-core/tests/unit/domain/bar/services/test_bar_builder.py` — extend cases for delta semantics
- `packages/pocketquant-api/tests/unit/market_data/app_services/test_quote_app_service.py` — adapter contract tests

**Read for reference:**
- `pocketquant-api/src/pocketquant/api/market_data/app_services/quote_dto.py` — `QuoteTick` definition
- Phase 01: `binance_mappers.py` — confirm mapper emits delta

## Implementation steps

1. Update `QuoteAppService.on_quote_update`:
   ```python
   raw_vol = quote_data.get("volume")
   delta = max(0.0, float(raw_vol)) if raw_vol is not None else None
   tick = QuoteTick(symbol=..., price=..., volume=delta, timestamp=...)
   ```
2. Add docstring to `BarBuilder.add_tick`:
   ```python
   """Aggregate a tick into the in-progress bar.

   volume MUST be per-tick DELTA (e.g., Binance @aggTrade `q` field).
   Cumulative session totals will inflate bar volume — adapters must
   convert before calling this method.
   """
   ```
3. Confirm `BarBuilder.add_tick` body is `self.volume += volume` for non-None — no change.
4. Extend `test_bar_builder.py` with delta-semantics cases (Test Matrix below).
5. Add `test_quote_app_service.py` cases for adapter contract.
6. Run `just test-pkg core && just test-pkg api` — green.
7. Run `just lint && just types` — clean.

## Test matrix

### `BarBuilder.add_tick` (delta semantics)

| Case | Setup | Assertion |
|---|---|---|
| **Single delta tick** | `add_tick(100, 0.5, t0)` | `bar.volume == 0.5` |
| **Sum of deltas** | `add_tick(100, 0.5)`, `add_tick(101, 0.3)`, `add_tick(102, 0.2)` | `bar.volume == 1.0` |
| **Zero delta tick** | `add_tick(100, 0.0, t0)` | `bar.volume == 0.0`, OHLC updates |
| **Volume = None** | `add_tick(100, None, t0)`, `add_tick(101, None, t1)` | `bar.volume == 0.0`, OHLC still updates |
| **Mix None + delta** | `add_tick(100, None)`, `add_tick(101, 0.5)` | `bar.volume == 0.5` |
| **Out-of-bar tick rejected** | `add_tick(100, 0.5, ts_after_bar_end)` | returns `False`, no state change |

### `QuoteAppService.on_quote_update` (adapter clamping)

| Case | Setup | Assertion |
|---|---|---|
| **Positive delta** | `quote_data["volume"] = 0.05` | `QuoteTick.volume == 0.05` |
| **Negative delta (defensive)** | `quote_data["volume"] = -0.01` | `QuoteTick.volume == 0.0` |
| **None volume** | `quote_data["volume"] = None` | `QuoteTick.volume is None` |
| **Zero volume** | `quote_data["volume"] = 0` | `QuoteTick.volume == 0.0`, OHLC processed |

## Todo list

- [x] Add docstring to `BarBuilder.add_tick` documenting delta contract
- [x] Update `QuoteAppService.on_quote_update` to clamp `volume` via `max(0.0, raw)`
- [x] Extend `test_bar_builder.py` with 6 delta-semantics cases
- [x] Add `test_quote_app_service.py` with 4 adapter cases
- [x] Run `just test-pkg core && just test-pkg api` — green
- [x] Run `just lint && just types` — clean

## Success criteria

- All 10 test cases pass
- Existing tests in `test_bar_builder.py` still pass (regression-free)
- Live in-progress 1m bar volume on dev VPS within ±5% of Binance API ground truth (post-Phase 03 deploy)
- No file exceeds 200 LOC

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Adapter mistakenly passes cumulative (regression) | Low | Critical | Adapter unit test explicitly asserts delta passthrough; Phase 01 mapper unit-tested for delta semantics |
| Future provider emits cumulative (mistaken contract) | Medium | High | `BarBuilder.add_tick` docstring enforces "DELTA only"; code-review checklist + grep guard |
| Negative `q` from Binance (spec violation) | Effectively zero | Low | `max(0.0, raw)` clamp |
| `volume = None` mid-bar leaves bar volume at 0 | Low | Medium | Test "Mix None + delta" verifies subsequent delta accumulates correctly |

## Security considerations

- Pure math, no I/O — zero attack surface added.
- Numeric clamp `max(0.0, raw)` defends against malformed input.

## Next steps

- Phase 5 documents delta-contract in `code-standards.md` to prevent regression.
- Independent of Phase 1/3/4 — can ship as standalone PR (depends only on Phase 01 mapper for end-to-end validation).

## Outcome

`BarBuilder.add_tick` docstring updated (delta contract clarified); `QuoteAppService.on_quote_update` now clamps negative volume to 0.0 via `max(0.0, raw)`. 10 new test cases added (6 in `test_bar_builder.py`, 4 in adapter); all pass. Volume aggregation now correctly sums per-trade deltas from Binance @aggTrade. See [tester-260507-1902-phase-02-volume-fix.md](../reports/tester-260507-1902-phase-02-volume-fix.md).

## Unresolved questions

1. Should adapter log a warning on negative `q` (vs silent clamp)? **Recommendation:** Yes — `logger.warning("binance_ws.negative_volume", q=raw)` for observability; clamp still applied.
2. Per-interval threshold for "abnormal" volume detection (audit alert)? **Defer to Phase 04 audit script** — uses 5000 BTC/min threshold per research-02.
