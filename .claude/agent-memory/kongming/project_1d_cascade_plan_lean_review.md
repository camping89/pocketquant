---
name: 1d-cascade-plan-lean-review
description: 2026-11-05 lean review of plan 261103-1741 (1d cascade fold): hourly 1d self-consistency check judged redundant after Phases 02/03 (reverses owner item 2, needs owner yes); D16 volume "mismatch" is a script tolerance artefact (1e-4 vs VOLUME_THRESHOLD_PCT 5%); repair 1m resync writes 5000 bars, not 7 days
metadata:
  type: project
---

Findings from the 2026-11-05 lean review of the shipped plan (master = develop = 3473b87b, deployed 2026-11-04T04:13Z):

- Every 1m/1d writer re-folds in the same job after Phase 03: `sync_1m` (100 min), `sync_repair` 00/12Z and `sync_backfill` 03Z (7 d via `_cascade_all`), symbol-add backfill cascades too; repair no longer REST-writes 5m-1d (E3). No persistent path leaves a stored 1d different from its stored 1m aggregate for longer than 12 h, so the hourly `cascade.daily_divergence` check only sees mid-job transients (hence the two-run debounce rule) or a cascade regression already logged as `cascade.symbol_failed`. Advised: delete it (about 50 src + 143 test lines, inline `aggregate_bucket` back, restore the `continue` structure). This reverses owner decision plan item 2 / Phase 17 D15, so it needs an explicit owner yes.
- `sync_repair`'s 1m resync writes the newest 5000 bars (`SyncSymbolCommand n_bars=5000, skip_filter=True`), which is under 7 days for every calendar; `_REPAIR_DAYS = 7` covers it. `days_back=_REPAIR_DAYS` duplicates `repair_integrity`'s default of 7.
- D16 "issue" (BTCUSD:EXNESS 2026-10-24 volume 113120 stored vs 113100 at Exness, OHLC equal, stored == 1m aggregate): the one-off `.cache/d16.py` used a flat 1e-4 tolerance; the system's own `VOLUME_THRESHOLD_PCT` is 5 %, under which the bars are equal. Advised no code change.

**Why:** owner asked on 2026-11-05 whether the plan over-engineered; CLAUDE.md requires a second real caller for a helper and deleting dead code.

**How to apply:** if the owner keeps the 1d check, do not re-raise deletion; if a REST-vs-stored 1d refresh is ever proposed, recall that E3 removed REST 1d writes on purpose.
