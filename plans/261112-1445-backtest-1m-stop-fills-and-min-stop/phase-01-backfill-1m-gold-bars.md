---
phase: 1
title: "Backfill 1m gold bars"
status: pending
priority: P2
effort: "2h"
dependencies: []
---

# Phase 1: Backfill 1m gold bars

## Goal
Load every XAUUSD:EXNESS 1m bar Exness serves (from about 2024-05) into prod `bars` without loading them into memory on the VPS.

## Facts
- Exness served XAUUSD M1 only from between 2024-04-15 and 2024-05-01 when checked on 2026-11-12 (`docs/deployment.md`, Exness symbols and deep history).
- `scripts/backfill/provider_bars.py` builds the whole list in memory (`ExnessAdapter.fetch_ohlcv`), then inserts in chunks of 5 000. About 900k 1m bars would not fit beside the live trader on the 3.9 GB VPS.
- Prod already has 1m bars from 2025-10-21, from the live sync.

## Files to Create / Modify
- None in the repo. The run uses `../pocketquant-config/local/remote-db.env` (see `README.md`, remote-db mode).

## Tasks & Steps
1. Read `README.md` remote-db mode. Check that `remote-db.env` carries the Exness API settings that `provider_bars.py` needs. If it does not, stop and ask: the settings live only in `../pocketquant-config/` and must not be copied into this repo.
2. Back up prod 1m XAUUSD bars on the VPS: `mongodump --collection bars --query '{"symbol":"XAUUSD:EXNESS","interval":"1m"}'` to `/opt/pocketquant/backups/bars-xauusd-1m-pre-backfill-<date>.archive`. Use the same command shape as the 15m backup taken on 2026-11-11.
3. Start `just tunnel`, back up `.env` and copy `remote-db.env` in, as `README.md` says.
4. Run `uv run python scripts/backfill/provider_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 1000 --rate-fraction 0.5 --dry-run` locally. Expect `fetched` near 900k and watch local memory.
5. Run the same command without `--dry-run`.
6. Restore `.env` and stop the tunnel.
7. Audit read-only on prod:
   - first and last 1m bar, and counts per month;
   - 15m buckets since the first 1m bar that have no 1m bar inside;
   - 15m bars whose high or low differ from the max or min of their 1m bars by more than 0.01.
8. Record the results in the phase-4 report draft. Update `docs/deployment.md` only if the 1m start differs from what it says.

## Verification
- `total_bars` printed by the script equals the prod count.
- The audit lists the first 1m bar and the number of 15m buckets without 1m bars.
- The live trader keeps running: `free -m` on the VPS is unchanged, and the latest 1m bar timestamps keep advancing during and after the run.

## Risk and rollback
- The insert upserts the same Exness candles the live sync writes, so overlapping bars are rewritten with equal values (seen in the 15m backfill on 2026-11-11).
- Rollback: delete 1m XAUUSD bars older than 2025-10-21, or restore the archive with `mongorestore` (see `docs/deployment.md`, Mongo backup and restore).
