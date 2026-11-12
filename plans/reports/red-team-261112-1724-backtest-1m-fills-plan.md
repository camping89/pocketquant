# Red-team findings: plan 261112-1445 (backtest 1m fills, Triple Screen stop and target)

Plan: `plans/261112-1445-backtest-1m-stop-fills-and-min-stop/`. Reviewers: Assumption Destroyer (AD), Failure Mode Analyst (FM), Security Adversary (SA). 27 raw findings, deduplicated to 15 below. Every finding cites code; the controller re-checked F1, F4, F7, F12 and F15 evidence directly.

## Findings

### F1 — Critical — Phase 1 rollback would drop the whole prod `bars` collection (FM1, SA1)
The backup is filtered to XAUUSD 1m. The rollback points at `docs/deployment.md:172-176`, which restores with `--archive --drop`; `--drop` drops all of `bars` (every symbol and interval) and restores only the 1m subset. A non-drop restore reverts nothing, because `upsert_bar` keeps `_id` and `$set`s values (`bar_repository.py:52-98`). The backup shape (`.cache/bf15.sh:3-4`, `--quiet` plus shell redirect) leaves a 0-byte archive on a failed dump, and nothing checks its document count.
Fix: rollback = `deleteMany` on `{symbol, interval:"1m", source:"rest_backfill", updated_at >= run start}`, then `mongorestore` without `--drop`; check the archive doc count equals `countDocuments(query)`; forbid `--drop` for filtered archives.

### F2 — Critical — The golden check cannot run as written (AD1, FM6)
Run `01a1c41f` covers 2025-11-09..2026-11-08 (`plans/reports/backtest-261111-1155-...md:3`); prod 1m bars start 2025-10-21, so phase 2 step 2 turns the 1m path on for that window. No DB without 1m bars is named; the local copy is made in phase 4. The check also needs `stoploss_lookback=20` (phase 3) though phase 2 lists no dependency on 3 (`services/__init__.py:50-52` rejects unknown keys). Side issue: kongming report 1356 line 7 says 490 trades "same as `01a1c41f`", plan says 489.
Fix: name the DB (local Mongo restored without 1m bars, or a pre-2024-04 window against `01a1c980`'s slice); move local-copy creation before phase 2; run the check with `stop_lookback=80` before the rename or make it depend on phase 3; settle 489 vs 490.

### F3 — High — The simulation-clock rule is left to the implementer, and both obvious rules break a plan promise (AD2, FM4)
Today clock and `occurred_at` are the bar start (`backtest_app_service.py:107,119`); `placed_at`, `opened_at`, `exit_time` come from `get_current_time()` (`paper_broker_adapter.py:139,438,463`). Merged by bar end with 1m first, a bar-start clock runs backwards (15m bar T after 1m T+14) and gives exit times before entry times. A bar-end clock shifts every single-interval timestamp by one interval, breaking "single-interval result unchanged" and every trade-keyed comparison (replica CSV keys on bar starts).
Fix: decide the rule in the plan, state trade-timestamp meaning, define how golden/replica/A-vs-`01a1c980` comparisons key trades, add an `exit_time >= entry_time` test.

### F4 — High — Phase 1 backfill: ~1.8M serial round trips over the tunnel, swallowed errors, a tautological check (AD4, FM2, FM3, SA3)
`insert_many` loops `upsert_bar` per bar (`bar_repository.py:18-33`), each a `find_one` + `update_one`; per-bar exceptions are logged and skipped; the script returns 0 whenever bars were fetched and prints `total_bars = repo.count()` on the same DB (`provider_bars.py:97-104`). "total_bars equals the prod count" is true by construction. An `ExnessApiError` late in the fetch discards everything (`provider_bars.py:89-95`). Effort "2h" is likely 10+ hours (inference, RTT not measured).
Fix: gate on `inserted == fetched` and zero `upsert_failed` lines; time a 1-day slice first; or backfill into local Mongo and copy to prod by dump/restore without `--drop`.

### F5 — High — A 1m gap skips fills and exits; it does not delay them (AD8, FM5)
`_finest_interval_s` pins to 60 s after the first 1m bar (`paper_broker_adapter.py:524-529`); every later 15m event returns early in `fill_resting_stops` (`:554`) and the broker's SL/TP handler (`:678`). A stop re-sent each bar is cancelled when it changes (`strategy_app_service.py:790-803`), so a gap-bucket fill is lost; a multi-day hole disables SL/TP for C. The coverage gate checks only the first 1m bar. Phase 1 audits gaps with no threshold.
Fix: correct the step-6 claim; pre-register a coverage threshold that aborts phase 4 (or per-bucket fallback); add a missing-bucket test.

### F6 — High — Prod-pointed `.env`, shared port 27017 and dump files can turn "local" work into prod writes or leaks (FM8, SA4, SA9)
Phase 1 overwrites `.env` with prod credentials for hours; README forbids pytest on it (`README.md:37`); the test guard matches only the VPS IP (`tests/conftest.py:25,50-56`). `just tunnel` binds 27017 (`justfile:53`), the same port as the local Mongo and the test default (`deploy/compose.local.yml:9`, `tests/conftest.py:36`). A crash skips the `.env` restore; a re-run overwrites the good backup. Phase 1 step 1 does not say "key names only". `.gitignore` has no `*.archive` or `dump/`.
Fix: never overwrite repo `.env` (use `POCKETQUANT_ROOT`, `config.py:10-12`, or inline env); stop the tunnel and assert the target host before phase 2 tests and every phase 4 step; local Mongo off 27017; key-names-only check; archives under `.cache/`, deleted after use; `df -h` before VPS dumps.

### F7 — High — Exness rate budget overcommitted, and the trader's armed state is never checked (SA2)
Prod fractions are 0.05 + 0.3 + 0.6 = 0.95 (`deploy/compose.prod.yml:82,98,115`); the plan adds 0.5, twice (dry run fetches everything). The script's guard reads only the local `EXNESS_LIVE_TRADING` (`provider_bars.py:76-78`), not the safeguards doc (`safeguards_repository.py:20-22`). A 429 on an order call is not retried (`exness_client.py:172-173`).
Fix: `--rate-fraction 0.05`; dry run with `--days 3`; read `live_trading` from the safeguards doc before and after, abort unless false; grep `exness.rate_limited` during the run.

### F8 — High — The 1m path turns on for every prod backtest of every symbol, and nobody is told (AD5, SA7)
Every symbol stores 1m bars (`sync_jobs.py:51`); backtests run uncapped in the api process sharing the live Mongo pool (`routes/backtest.py:45-46,56`, `docs/system-architecture.md:25`). After release, every recent-window UI backtest changes fills and costs ~15x the events. Phase 5 step 3 mentions only paper fills and the lookback default; non-goals exclude other symbols.
Fix: state the global effect in phase 5 step 3 and the docs line; measure one 1-year merged run against `/health` loop lag and lease age; or scope the switch explicitly.

### F9 — High — The "out-of-sample" segment is selection data for C, and C's kill rule nearly cannot fail (AD6)
C was chosen by an anchored walk-forward over 2023-01..2026-11 (`kongming-261112-1527...md:81,89`); replica t on 2024-05..2026-11 is 2.58/2.71 (`:181`). The step-8 rule (mean R <= 0 or t < 1.5) on that same window mostly tests engine vs replica agreement. "Or the first full 1m day" adds a start-date choice the pre-registration did not have (`:178` fixes 2024-05-01).
Fix: label segments per config (for C both are "used in selection"); state that the step-8 rule tests the engine only; fix the start at 2024-05-01 and abort if coverage starts later.

### F10 — Medium — Two concurrent Mongo cursors; the slow 15m cursor can idle past the server cursor timeout (AD3)
`stream` is `find().sort()` with no `batch_size` or `no_cursor_timeout` (`bar_repository.py:130-151`). With merging, the 15m cursor idles while its batch of 1m bars replays; a 2-hour run can exceed the default 10-minute idle-cursor timeout and raise `CursorNotFound` (inference).
Fix: load the window's entry-interval bars into a list (~87k) and stream only 1m.

### F11 — Medium — The stored-subscription rename contingency is unsafe (FM7, SA5)
Dividing by ratio gives non-integers (5/4) and `deque(maxlen=1.25)` raises (`triple_screen_strategy_service.py:67`); reconcile loads without validation (`strategy_reconcile_app_service.py:143`) and skips running instances (`:137-141`); a raw update bypasses the stopped-and-flat guard (`subscription_repository.py:37`, `strategy_command_service.py:124-135`) and unloading drops positions (`strategy_app_service.py:516-522`); between deploy and rename the stale key is ignored silently.
Fix: migrate before release, subscriptions stopped and flat, per-document integer rounding from each doc's own ratio, filter by `strategy_code`, matched-count check, validate with `check_strategy_inputs`, via the API update path.

### F12 — Medium — Parameter validation gaps and an equivalence test with no baseline (FM9, SA6)
"Validate each as >= 0" lets `stoploss_lookback=0` through; `min()` on an empty window raises, swallowed as `skipped:strategy_error` (`strategy_app_service.py:617-623`); today the floor is 1 (`triple_screen_strategy_service.py:61-62`). NaN passes `>= 0`-style checks and `_type_matches` (`services/__init__.py:22-23`); no lookback cap versus live warm-up of 500 bars (`strategy_app_service.py:55`). No test pins `stop_lookback` today, so "same signals as `stop_lookback=80` did" is circular unless captured before the rename.
Fix: `stoploss_lookback >= 1`; `math.isfinite` on floats; cap `max(lookbacks) x ratio <= 500`; capture a signal fixture from the current code before step 1; add tests.

### F13 — Medium — The replica check demands an exact match despite a known warm-up difference (AD7)
The engine's swing deque starts empty at `start_date` (`triple_screen_strategy_service.py:67,71,99`; preload covers only `intervals[1:]`, `strategy_app_service.py:354-364`); the replica's rolling window sees earlier bars (`.cache/km3/sim_mtf.py:29-33`). The earlier replica already differed on the first trade for this reason (`kongming-261112-1356...md:267`).
Fix: pre-register the match rule (skip the first `max(L,P) x ratio` entry bars; match side and fill time; prices within 1e-6).

### F14 — Medium — Phase 5 uses a wrong health route and omits Exness-broker subscriptions (SA8)
The route is `/health` (`app/main_extensions.py:301`), not `/api/v1/health`. Subscriptions can use `broker: "exness"` (`routes/strategy.py:20`); the new default changes their stops too, and phase 5 step 3 speaks only of paper.
Fix: use `/health` or `deploy/vps/11-verify.sh`; list subscriptions by broker and state before asking the owner.

### F15 — Medium — `stoploss_buffer_atr` has no caller in any planned run (AD9)
All three runs set it to 0 and "nothing else runs"; CLAUDE.md requires a second real caller for a new parameter; kongming's own design added no SL buffer (`kongming-261112-1527...md:30`). This is owner decision 2, so it cannot be cut without the owner.

## Checked and not raised
- Broker fill state is per run (`backtest_sandbox_app_service.py:88`, `paper_broker_adapter.py:794` reset, ContextVar clock); no leak into the live trader.
- Live builds and acts on 1m bars (`bar_app_service.py:38-46`).
- Only the SL is checked on the fill bar; TP waits a bar (`paper_broker_adapter.py:532-541`).
- 80 entry bars = `stoploss_lookback=20` x 4, signal bar included.
- A local process pointed at prod Mongo starts no trader, scheduler or lease (`infrastructure.py:88-94`, `config.py:62`).
- Stored backtest runs are never re-validated (`backtest_execution_service.py:104`).
- Run ids `01a1c41f` (in-sample year) and `01a1c980` (2023-01..2026-11) are distinct and used consistently.
