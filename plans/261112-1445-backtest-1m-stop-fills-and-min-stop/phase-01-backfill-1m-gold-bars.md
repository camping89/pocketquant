---
phase: 1
title: "Backfill 1m gold bars through local Mongo"
status: done
priority: P1
effort: "4h plus the fetch wall time"
dependencies: []
---

# Phase 1: Backfill 1m gold bars through local Mongo

## Goal
Load every XAUUSD:EXNESS 1m bar that Exness serves (from about 2024-05) into the local Mongo. Record baseline B0. Then copy to prod only the 1m bars older than prod's first 1m bar, without rewriting any prod bar.

## Facts
- When checked on 2026-11-12, Exness served XAUUSD M1 starting somewhere between 2024-04-15 and 2024-05-01 (`docs/deployment.md:217`). Whether that window rolls forward with the date is unknown, so run this phase first.
- `scripts/backfill/provider_bars.py` fetches the whole list into memory, then calls `BarRepository.insert_many` in chunks of 5 000.
  - `insert_many` upserts one bar at a time. It logs and skips a failing bar as `bar_repo.insert_many.upsert_failed` (`bar_repository.py:18-33`).
  - The script prints `fetched=<n> inserted=<n> total_bars=<n>` and returns 0 whenever bars were fetched. `total_bars` is a count on the same database, so it proves nothing about the write.
- The script refuses to run only when the local `EXNESS_LIVE_TRADING` is true (`provider_bars.py:76-78`). The trader's armed state lives in the prod `safeguards` collection (`safeguards_repository.py`).
- The prod Exness rate fractions already sum to 0.95: api 0.05, worker 0.3 and trader 0.6 (`deploy/compose.prod.yml:82,98,115`). This phase uses 0.05.
- Prod already has 1m bars from about 2025-10-21, from the live sync.
- `mongorestore --drop` drops the whole target collection (`docs/deployment.md:172-176`). It is never used in this plan.
- VPS access: copy the normalised key to `.cache/ssh/vps_key` (`tr -d '\r' < ../pocketquant-config/vps/default/id_rsa`, then `chmod 600`). Read the host with `head -1 ../pocketquant-config/vps/default/host | tr -d '\r'`. Put multi-line remote commands in a script under `.cache/p1/` and run `ssh ... 'bash -s' < file`. Do not use `docker exec -i` inside a piped script.
- Prod database name: `pocketquant`. The container is `pocketquant-mongodb` on both the VPS and this machine. Both use the env vars `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD` inside the container. Use them as `$VAR` inside `sh -c '...'`, never expanded on this machine.

## Files to Create / Modify
- No repo source file.
- Scratch files, all under `.cache/` (gitignored): `.cache/p1/guard.py`, `.cache/p1/*.sh`, `.cache/dumps/`, `.cache/bf1m/run.log`, `.cache/p1/audit.py`, `.cache/p1/audit.txt`, `.cache/golden/b0.csv`.

## Tasks

### Task 1.1 — Target guard
- **Goal:** prove that the repo `.env` points at the local Mongo, before anything writes.
- **Target files:** `.cache/p1/guard.py` (new scratch file).
- **Steps:**
  1. Check that no tunnel runs. Run `netstat -ano | grep LISTENING | grep ':27017 '`, note each owning PID, and run `tasklist //FI "PID eq <pid>"` for each. No owner may be `ssh.exe`. If one is, stop and report; do not kill it, because it may belong to another session.
  2. Write `.cache/p1/guard.py`:
     ```python
     import asyncio
     from pymongo import AsyncMongoClient
     from pocketquant.core.config import get_settings

     async def main():
         s = get_settings()
         host = s.mongodb_url.hosts()[0]["host"]
         print("host", host, "db", s.mongodb_database)
         c = AsyncMongoClient(str(s.mongodb_url))
         syms = await c[s.mongodb_database].bars.distinct("symbol")
         print("symbols", sorted(syms))
         await c.close()

     asyncio.run(main())
     ```
  3. Start Docker Desktop if `docker ps` fails, then run `just up`.
  4. Run `uv run python .cache/p1/guard.py`.
- **Success criteria:** the host is `localhost` or `127.0.0.1`. The symbols list is `[]` or `['XAUUSD:EXNESS']`.
- **Verify:** the output's `host` field is exactly `localhost` or `127.0.0.1`, and its `symbols` field is `[]` or `['XAUUSD:EXNESS']`. Record the printed `db` value as `LOCAL_DB` for the later tasks. Repeat this task before tasks 1.3, 1.6 and 1.8.
- **Amended 2026-11-12 (kongming counsel after the first run failed):** the local DB holds leftover `BTCUSDT:BINANCE` and `ETHUSDT:BINANCE` dev bars, and the symbols clause cannot tell local from prod once XAUUSD is loaded. A `just tunnel` also shows `localhost`, on port 27017. The guard now prints `port` and `prod_marker` (count of run `01a1c980-...` in `backtest_runs`) and a `GUARD PASS|FAIL` line. It passes only when: no `ssh.exe` owns `:27017`; host is `localhost` or `127.0.0.1`; port is `47017` and `docker port pocketquant-mongodb 27017` maps to `:47017`; `prod_marker` is `0`; symbols are a subset of `{BTCUSDT:BINANCE, ETHUSDT:BINANCE, XAUUSD:EXNESS}`. This replaces the Verify above for every repeat. The Binance bars stay; every later query filters by symbol.

### Task 1.2 — Copy the coarse prod bars to local
- **Goal:** the local Mongo holds the prod XAUUSD:EXNESS 15m, 1h, 4h and 1d bars and the XAUUSD `symbols` doc.
- **Target files:** `.cache/p1/dump-coarse.sh` (new), `.cache/dumps/`.
- **Steps:**
  1. On the VPS, run `df -h /opt/pocketquant` and record the free space. If it is below 2 GB, stop and report.
  2. On the VPS, without `--quiet`, dump to `/opt/pocketquant/backups/p1-coarse-<yyyymmdd>.archive` and `/opt/pocketquant/backups/p1-symbols-<yyyymmdd>.archive`:
     - `bars` with query `{"symbol":"XAUUSD:EXNESS","interval":{"$in":["15m","1h","4h","1d"]}}`;
     - `symbols` with query `{"symbol":"XAUUSD:EXNESS"}`. If that field name does not match, read one `symbols` doc's keys first and use the right one.
     Keep mongodump's stderr: it prints `done dumping pocketquant.bars (N documents)`.
  3. On the VPS, run `countDocuments` for the same two queries with `mongosh`.
  4. `scp` both archives to `.cache/dumps/`. Delete them on the VPS.
  5. Restore locally: `docker exec pocketquant-mongodb sh -c 'mongorestore --uri="mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin" --archive --nsFrom "pocketquant.*" --nsTo "<LOCAL_DB>.*"' < .cache/dumps/<file>`. No `--drop`. This uses `-i`-free stdin redirection on the local machine, which is fine.
- **Success criteria:** the local counts equal the prod counts.
- **Verify:** the `N documents` from mongodump equals the prod `countDocuments` for each archive. The local `countDocuments` of the same queries equals that `N`. Any difference fails.

### Task 1.3 — Armed check
- **Goal:** live trading is off on prod before Exness is called.
- **Target files:** none.
- **Steps:**
  1. On the VPS, read `db.safeguards.findOne({})` in database `pocketquant` with `mongosh`, and print only its `live_trading` field.
- **Success criteria:** `live_trading` is `false` or absent.
- **Verify:** the printed value is `false` or `null`. Any other value fails.

### Task 1.4 — Exness settings for one command
- **Goal:** the backfill command gets the four Exness API settings as process environment, without writing them into the repo.
- **Target files:** none in the repo.
- **Steps:**
  1. Find which file under `../pocketquant-config/` holds `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` and `EXNESS_SECRET_KEY`. Use `grep -l '^EXNESS_API_KEY=' -r ../pocketquant-config/`, and print key names only. If a privacy hook blocks the read, stop and ask the user for approval.
  2. Write `.cache/p1/exness-env.sh`. It exports those four keys read from that file, plus `EXNESS_LIVE_TRADING=false`, and contains no literal value: use `grep '^EXNESS_' <file> | tr -d '\r'` piped into `export`.
- **Success criteria:** `source .cache/p1/exness-env.sh && env | grep -c '^EXNESS_'` prints `5`.
- **Verify:** that command prints `5`. Never print `env` itself.

### Task 1.5 — Timing slice
- **Goal:** the fetch works at 0.05 of the rate, and a 3-day fetch time is known.
- **Target files:** none.
- **Steps:**
  1. Run `source .cache/p1/exness-env.sh && time uv run python scripts/backfill/provider_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 3 --rate-fraction 0.05 --dry-run`.
- **Success criteria:** exit code 0, and `fetched` is over 2 000 (3 days cover at least two trading days).
- **Verify:** the exit code is 0, and the printed `fetched=` value is above 2000. Record the wall time. Estimate the full fetch as wall time x 333. If the estimate is over 8 hours, stop and report the estimate.
- **Amended 2026-11-12 (kongming counsel after the first run failed with `TRANSPORT`):** this machine's network resets TLS to `api.exness.com`; the VPS reaches it. Only the backfill process's Exness traffic goes through an SSH SOCKS proxy to the VPS: `ssh -N -D 127.0.0.1:1080 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=4 -i .cache/ssh/vps_key <host>` as a tracked background process. Gates before the run: `:1080` free beforehand, no `*_proxy` vars, `curl --socks5-hostname 127.0.0.1:1080 https://api.exness.com/` prints 404 while the direct curl fails with (35), the same check through `uv run --with socksio` httpx prints 404, and the guard passes. The command becomes `uv run --with socksio env HTTPS_PROXY=socks5://127.0.0.1:1080 NO_PROXY=localhost,127.0.0.1 python scripts/backfill/provider_bars.py ...`. The proxy is never exported in the shell or written to any env file. Result: exit 0, `fetched=4320`, wall 51.6 s, full-fetch estimate about 4.8 h.

### Task 1.6 — Full backfill into local Mongo
- **Goal:** all served 1m bars are in the local Mongo, with no lost write.
- **Target files:** `.cache/bf1m/run.log`.
- **Steps:**
  1. Repeat task 1.1.
  2. Run `source .cache/p1/exness-env.sh && uv run python scripts/backfill/provider_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 1000 --rate-fraction 0.05 > .cache/bf1m/run.log 2>&1`, in the background.
  3. When it exits with code 1, run it again once. The upserts are idempotent.
  4. Run `grep -c upsert_failed .cache/bf1m/run.log`, `grep -c REQUEST_RATE_LIMIT .cache/bf1m/run.log` and `grep -c rate_limited .cache/bf1m/run.log`.
- **Success criteria:** the last line has `fetched == inserted`; there are no failed upserts and no rate-limit errors.
- **Verify:** the exit code is 0; in the last `fetched=<a> inserted=<b>` line, `a == b`; the first two greps print `0`. Record the third grep's count; it is informational.
- After the run, repeat task 1.3. It must still print `false` or `null`.
- **Amended 2026-11-12:** run through the task 1.5 proxy wrapper, with `--rate-fraction 0.05`. Before the run and before the one allowed rerun, confirm the ssh PID is alive and the proxied curl prints 404. Also run `grep -c TRANSPORT` and `grep -c access_point_reset` on the log: both must be `0` on the passing run. Kill the ssh PID afterwards and confirm `:1080` no longer listens.

### Task 1.7 — Local audit
- **Goal:** know the 1m coverage before any backtest relies on it.
- **Target files:** `.cache/p1/audit.py` (new), `.cache/p1/audit.txt`.
- **Steps:**
  1. Write `.cache/p1/audit.py`. Using the same settings as `guard.py`, over XAUUSD:EXNESS from 2024-05-01T00:00Z to 2026-11-10T23:59Z, it prints:
     - `first_1m`, `last_1m` and the 1m count per calendar month;
     - `buckets`: the number of 15m bars in the window;
     - `E0`: the number of 15m bars with no 1m bar starting inside `[start, start + 15m)`;
     - `E1`: the number of 15m bars that have 1m bars but whose high differs from the max of their 1m highs by more than 0.01, or whose low differs from the min of their 1m lows by more than 0.01;
     - `E0_run`: the longest run of consecutive E0 bars;
     - `ratio`: `(E0 + E1) / buckets`. The thresholds below (1% and 96) were confirmed by the owner in Validation Session 1.
  2. Run `uv run python .cache/p1/audit.py > .cache/p1/audit.txt`.
- **Success criteria:** `first_1m <= 2024-05-01T00:00Z`, `ratio <= 0.01` and `E0_run <= 96`.
- **Verify:** all three comparisons hold in `audit.txt`. If `first_1m` is later than 2024-05-01T00:00Z, stop and ask the owner; the start date is fixed and does not move. If `ratio > 0.01` or `E0_run > 96`, stop and report.

### Task 1.8 — Baseline B0
- **Goal:** the code as it is before phase 2 reproduces stored run `01a1c980` on the local data.
- **Target files:** `.cache/golden/b0.py` (new), `.cache/golden/b0.csv`, `.cache/golden/stored.csv`.
- **Steps:**
  1. Repeat task 1.1.
  2. Read `01a1c980`'s `config_snapshot` from prod, read-only. Get it from the prod `backtest_runs` collection (`COLLECTION_BACKTEST_RUNS`, `src/pocketquant/core/common/constants.py:12`). The `_id` is the string `"01a1c980-46bc-7400-acb1-f2f6a90c6323"`, not a UUID type (`backtest_repository.py:21`). <!-- Updated: Validation Session 1 - _id is a string --> Save it as `.cache/golden/config.json`. Expected: Triple Screen `15m,1h,4h`, `entry_type=stop`, `exit_mode=strategy`, `stop_lookback=80`, spread 0.08, commission 3 bp, slippage 0.1 bp, 10 000 USD, 2023-01-01..2026-11-10 23:59 UTC.
  3. Convert the stored trades in `.cache/oos/pull.txt` (lines starting `T `, a JSON list `[side, entry_time, exit_time, ...]`) to `.cache/golden/stored.csv` with columns `side,entry_time,exit_time`.
  4. Write `.cache/golden/b0.py`. It runs that config locally through `BacktestCommandService.run` and `BacktestExecutionService.execute_and_persist`, the same path as `.cache/ts_direct.py` (`create_container()`, then `BacktestCommandService.run(RunBacktestCommand(...))` and `BacktestExecutionService.execute_and_persist(run_id, config)`). Do not copy `.cache/bt.py`: it calls the HTTP API. <!-- Updated: Validation Session 1 - runner template is ts_direct.py -->, then writes the run's trades to `.cache/golden/b0.csv` with columns `side,entry_time,exit_time,entry_price,exit_price,quantity,pnl,exit_reason`, in time order.
  5. Run it, then compare on `(side, entry_time, exit_time)`.
- **Success criteria:** 1 991 trades, identical to the stored list.
- **Verify:** `b0.csv` has 1 991 rows, and the comparison prints `0` differing rows. Any difference fails: it means the bars changed since 2026-11-11.

### Task 1.9 — Copy the older 1m bars to prod
- **Goal:** prod holds the 1m bars older than its first pre-existing 1m bar. No prod bar is rewritten.
- **Target files:** `.cache/p1/load-prod.sh` (new), `.cache/dumps/`.
- **Steps:**
  1. On prod, read `C`, the `datetime` of the earliest XAUUSD:EXNESS 1m bar: `db.bars.find({symbol:"XAUUSD:EXNESS",interval:"1m"}).sort({datetime:1}).limit(1)`. Record `C` in `.cache/p1/audit.txt`. Also record `before_from_C` = the prod 1m count with `datetime >= C`.
  2. Locally, count the 1m bars with `datetime < C` as `N`. Dump them with `--query '{"symbol":"XAUUSD:EXNESS","interval":"1m","datetime":{"$lt":{"$date":"<C as ISO-8601 Z>"}}}'`, without `--quiet`, to `.cache/dumps/p1-1m-older.archive`.
  3. On the VPS, run `free -m` and `df -h /opt/pocketquant`. If free disk is below 2 GB, stop and report.
  4. `scp` the archive to `/opt/pocketquant/backups/`.
  5. On the VPS: `docker exec pocketquant-mongodb sh -c 'mongorestore --uri="mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin" --archive --nsFrom "<LOCAL_DB>.*" --nsTo "pocketquant.*" --nsInclude "pocketquant.bars" --noIndexRestore --numInsertionWorkersPerCollection=1' < /opt/pocketquant/backups/p1-1m-older.archive`. Run it as one ssh command. Never pass `--drop`. Run `mongorestore --help` on the VPS first and confirm that every flag exists.
  6. On prod, count the 1m bars with `datetime < C` and with `datetime >= C`. Read the newest 1m bar's `datetime` twice, 2 minutes apart. Run `free -m` again.
  7. Delete the archive on the VPS and locally.
- **Success criteria:** the prod count older than `C` equals `N`, and nothing from `C` on was touched.
- **Verify:**
  - The mongodump `N documents` equals the local count `N`.
  - The prod count with `datetime < C` equals `N`.
  - The prod count with `datetime >= C` is at least `before_from_C`.
  - The second newest-bar read is later than the first.
  - mongorestore printed `0 document(s) failed to restore`.

### Task 1.10 — Record
- **Goal:** the results are kept for the phase-4 report.
- **Target files:** `.cache/p1/audit.txt`; `docs/deployment.md` only if needed.
- **Steps:**
  1. Append to `.cache/p1/audit.txt`: `first_1m`, `C`, `N`, `E0`, `E1`, `E0_run`, `ratio`, the B0 result, the rate-limit retry count.
  2. If `first_1m` is outside the bracket that `docs/deployment.md:217` states, update that one line.
- **Success criteria:** the file holds every value listed.
- **Verify:** no verification needed; phase 4 task 4.9 reads these values.

## Risk and rollback
- **Rollback of task 1.9:** `db.bars.deleteMany({symbol:"XAUUSD:EXNESS", interval:"1m", datetime:{$lt: C}})` on prod. This is exact, because that set was empty before task 1.9. No backup archive or `--drop` is needed.
- The local Mongo is disposable. To redo the local data, delete the local XAUUSD bars and repeat from task 1.2.
- Phase-4 numbers come from the local copy, where every 1m bar comes from REST. On prod, 1m bars are REST before `C` and live sync after. The phase-4 report says so.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
