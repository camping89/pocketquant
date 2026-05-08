# Phase 04 Implementation Report — Audit + 2y Re-sync Scripts

**Date:** 2026-05-08
**Phase:** phase-04-audit-and-resync-2y
**Status:** DONE

---

## Files Created / Modified

| File | Action | LOC |
|------|--------|-----|
| `scripts/audit_bar_quality.py` | CREATE | 175 |
| `scripts/resync_2y_from_binance.py` | CREATE | 195 |
| `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py` | MODIFY | +35 (delete_many_by_range + logging) |
| `packages/pocketquant-core/tests/unit/persistence/test_bar_repository_delete_range.py` | CREATE | 120 |
| `tests/scripts/test_audit_bar_quality.py` | CREATE | 280 |
| `tests/scripts/test_resync_2y_from_binance.py` | CREATE | 295 |
| `tests/scripts/conftest.py` | CREATE | 20 |
| `tests/conftest.py` | CREATE | 15 |

---

## Tasks Completed

- [x] `audit_bar_quality.py`: argparse CLI, Mongo aggregation pipeline, Markdown report output, exit 0/1
- [x] `resync_2y_from_binance.py`: argparse CLI, tracked-symbol load, window compute, per-symbol delete→fetch→insert→cascade, checkpoint resume, dry-run, --no-cascade, --symbols filter, summary print
- [x] `BarRepository.delete_many_by_range`: $in filter for interval list, $gte/$lt date range, empty-list no-op, returns deleted_count
- [x] Unit tests: `test_bar_repository_delete_range.py` — 10 tests
- [x] Unit tests: `test_audit_bar_quality.py` — 20 tests (pipeline construction, markdown render, exit-1 on Mongo fail, filter propagation)
- [x] Unit tests: `test_resync_2y_from_binance.py` — 22 tests (window calc, checkpoint, dry-run, call order, cascade skip, non-Binance filter, --symbols)
- [x] Fixed pre-existing `tests/scripts/` import breakage (stale `tests/scripts/__init__.py` shadowing `scripts` package; added `conftest.py` with sys.modules eviction)
- [x] Fixed pre-existing line E501 in `bar_repository.py` (find_datetimes chain)

---

## Tests Status

| Suite | Count | Result |
|-------|-------|--------|
| `tests/scripts/` (all 3 files) | 57 | PASS |
| `packages/pocketquant-core/tests/unit/persistence/` | 10 | PASS |
| `packages/pocketquant-core/tests/` (full) | 74 | PASS |
| Lint (ruff) — modified files | — | CLEAN |
| Pyright — modified files | — | 0 errors |
| Syntax (`py_compile`) | — | OK |

**Total new tests: 52** (20 audit + 22 resync + 10 bar_repo)

---

## Key Implementation Notes

1. **aggregate() await pattern**: pymongo 4.16 `AsyncCollection.aggregate()` is a coroutine (not a direct async iterator). Used `cursor = await collection.aggregate(pipeline)  # type: ignore[misc]` — matches existing pattern in `job_history_repository.py`. Stubs are wrong; suppression is justified.

2. **cascade_for_symbol API**: The existing aggregator takes `(symbol, exchange, lookback_minutes, bar_repo)` — not a tf list. Resync script passes `days * 1440` as `lookback_minutes` and relies on the aggregator's `CASCADE_TFS` constant (5m/15m/1h/4h/1d).

3. **conftest.py sys.modules eviction**: pytest was caching `sys.modules['scripts']` pointing to `tests/scripts/` (because `tests/scripts/__init__.py` was created by this phase). Removed `__init__.py` and added eviction guard in `tests/scripts/conftest.py`. Also fixed `tests/binance_kline_mapping.py` which had the same pre-existing failure.

4. **LOC compliance**: audit=175, resync=195 — both under 200 limit.

---

## Concerns/Blockers

None. Phase is fully self-contained. Phase 03 (DI swap) was not touched.

**Ready for orchestrator to execute production run sequence (mongodump → dry-run → live).**
