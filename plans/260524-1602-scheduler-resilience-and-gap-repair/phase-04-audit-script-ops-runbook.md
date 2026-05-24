---
phase: 4
title: "Audit script + ops runbook"
status: completed
priority: P3
effort: "2h"
dependencies: []
---

# Phase 4: Audit script + ops runbook

## Overview

One-shot script to verify whether any bar-data gaps persist around historical missed-`sync_backfill` days (2026-05-08, 05-11, 05-21) plus a runbook section in `deployment-guide.md`. Likely a no-op for the historical dates due to 100-min cascade lookback self-healing, but provides ongoing tooling for future gap incidents.

## Requirements

- Functional:
  - Script accepts `--dates` (comma-separated YYYY-MM-DD) and optional `--window-hours` (default 6).
  - For each (date, symbol, interval): expected_bars = window_hours * (60 / interval_minutes). Counts actual bars in `bars` collection.
  - Prints table sorted by gap magnitude. Non-zero exit code if any gap > 0.
  - Reads `MONGODB_URL` from env (same as other scripts).
- Non-functional:
  - Standalone (no FastAPI), ~80 LOC.
  - kebab-case filename per Python convention is `snake_case` (audit_bar_gaps.py — language convention overrides general kebab preference).

## Architecture

```
scripts/audit_bar_gaps.py
  ├── parse_args()        → Namespace
  ├── compute_window()    → (start, end) UTC
  ├── expected_bars(interval, window_hours) → int
  ├── audit_one(symbol, interval, window) → AuditRow
  └── main() → print table, sys.exit(1) if gaps

docs/deployment-guide.md → append "Sync Gap Repair" section
```

## Related Code Files

- Create: `scripts/audit_bar_gaps.py`
- Modify: `docs/deployment-guide.md` (append new section, do NOT create new doc file)

## Implementation Steps

1. **Create `scripts/audit_bar_gaps.py`:**
   - Use `motor` async driver (matches existing repo pattern).
   - Iterate tracked symbols from `tracked_symbols` collection + `SYNC_INTERVALS` from sync_jobs.
   - Per (date, symbol, interval), query `bars` count in `[date_start, date_start + window_hours]`.
   - Compare with expected = `window_hours * 60 / interval_minutes`.
   - Output Rich table (already a dep).
   - Exit 1 if any actual < expected; else 0.

2. **Append to `docs/deployment-guide.md`** — new section "## Sync Gap Repair":
   ```markdown
   ## Sync Gap Repair

   When job_history shows `missed` events for sync_backfill or after manual deploy windows that overlapped 03:00-04:00 UTC, verify and repair:

   ### Step 1: Audit
   ```bash
   ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/audit_bar_gaps.py --dates 2026-05-08,2026-05-11,2026-05-21"
   ```

   ### Step 2: Repair (if audit shows gaps)
   For each (symbol, interval) with gap, hit per-symbol sync endpoint:
   ```bash
   ssh -i $KEY $VPS "curl -X POST http://localhost:\$APP_PORT/api/v1/market-data/sync \
     -H 'Content-Type: application/json' \
     -d '{\"symbol\":\"BTCUSDT:BINANCE\",\"interval\":\"1m\",\"n_bars\":5000}'"
   ```

   ### Step 3: Verify
   Re-run audit script — expect exit code 0.
   ```

3. **Run one-shot audit on VPS** as part of plan completion (separate operational step, not part of code review):
   ```bash
   ssh -i $KEY $VPS "cd /opt/pocketquant && python scripts/audit_bar_gaps.py --dates 2026-05-08,2026-05-11,2026-05-21"
   ```

## Success Criteria

- [x] `scripts/audit_bar_gaps.py` created, runnable, ≤120 LOC
- [x] Script exits 0 on parity, 1 on gaps
- [x] `docs/deployment-guide.md` includes "Sync Gap Repair" section
- [x] No new doc files created (rule respected)
- [x] Sample run against historical dates included in PR description

## Risk Assessment

- **Risk:** Script triggers production load when run against VPS. **Mitigation:** Read-only count queries; minimal impact.
- **Risk:** Expected bar count differs from actual due to market closures / exchange downtime not modelled. **Mitigation:** Crypto markets are 24/7 — no closures. Exchange downtime would show as a gap and require human judgement (acceptable).

## Next Steps

Phase 5 covers unit tests for the foundations + catch-up logic.
