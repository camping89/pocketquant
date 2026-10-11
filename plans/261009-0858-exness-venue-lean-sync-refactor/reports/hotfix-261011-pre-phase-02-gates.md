# Hotfix 2026-10-11: pre-Phase-02 gates

**Outcome:** Both gates are green. CI run 38138392784 deployed commit `22f04b6`, and its VPS verify step reported `Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures)`. `GET /api/v1/market-data/symbols` returns HTTP 200, both from inside the app container right after the data fix and again after the deploy.

## (A) Prod data fix

### Inventory (read-only)

The check counted documents whose `symbol` contains a character outside `[A-Z0-9_:-]`. It found three symbols, not one: `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI`.

| Collection | Invalid / total | Distinct invalid symbols |
|---|---|---|
| symbols | 3 / 6 | ES1!:CME_MINI, NQ1!:CME_MINI, YM1!:CBOT_MINI |
| tracked_symbols | 3 / 6 | the same three |
| bars | 160,395 / 4,853,291 | the same three |
| sync_status | 21 / 42 | the same three |
| subscriptions | 0 / 2 | none |

No code in `src/`, `scripts/` or `deploy/` references these symbols, so the app does not re-seed them on boot.

Because more symbols were affected than the brief named, I asked the coordinator before deleting anything. The coordinator approved deleting all three. Deleting only ES1! would have kept the 400, because `find_all` would still raise on the other two.

### Backup

`mongodump` with `--nsInclude` failed on the VPS (`unknown option nsInclude`). I then ran the full-database dump pattern from `docs/deployment.md`.

- Path: `/opt/pocketquant/backup-pre-phase02-invalid-symbols-20261011T1209.archive` on the VPS
- Size: 1,564,729,945 bytes
- Contents: all 13 collections, including symbols (6), tracked_symbols (6), sync_status (42) and bars (4,853,294)

### Deletion

The `deleteMany({symbol: {$in: [the three symbols]}})` call ran on `symbols` and on `tracked_symbols`.

- symbols: 3 deleted, 3 remain (BTCUSDT, ETHUSDT and SOLUSDT on BINANCE), 0 invalid left.
- tracked_symbols: 3 deleted, 3 remain, 0 invalid left. The deleted `_id`s were `01a0cdbc-b709-70f9-902a-6745a34b963b` (ES1!), `01a0cdbc-b710-7380-ac28-8cb1e8f692b5` (NQ1!) and `01a0cdbc-b714-71a7-9007-6474592ad0ad` (YM1!).
- bars and sync_status were not touched. After the deletion they still hold 160,395 and 21 rows for these symbols.

The `symbols` `_id`s were dropped from the console output by a grep filter, so they are not recorded here. The backup archive holds them.

`COMPOSITE_SYMBOL_RE`, `find_all` and `11-verify.sh` were not changed.

## (B) Test fixes

- Commit `22f04b6`: `test: read layout contract files as utf-8 and narrow optional take-profit`
  - `tests/core_test/test_core_layout_contract.py:76` now opens files with `encoding="utf-8"`.
  - `tests/core_test/unit/domain/strategy/test_engulfing.py:173` now asserts `sig.take_profit_price is not None` before the `<` comparison.
- Local results, run without PYTHONUTF8:
  - `just test` passed 647 tests and skipped 1, with 0 failed.
  - `pyright` reported 0 errors, 0 warnings and 0 informations.
- I pushed `8fd78b9..22f04b6` to origin master. The untracked `plans/` and `.claude/` files were not committed.

## CI and verify

- CI/CD run 38138392784 succeeded across the tests, build-app and deploy jobs.
- The "Verify on VPS" step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Unresolved questions

- The 160,395 bars and 21 sync_status rows for the three futures symbols are orphaned. Nothing reads them through `symbols` now. It is still open whether to purge them or to re-add these futures under a symbol format the regex accepts.
