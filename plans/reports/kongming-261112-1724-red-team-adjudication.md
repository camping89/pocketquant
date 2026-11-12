# Adjudication of red-team findings F1..F15, plan 261112-1445

Date: 2026-11-12. Author: kongming (model Fable 5.2). Advisory only; no plan or source file was edited.

Labels: **[V]** = verified today in code, a report or local scratch data. **[I]** = my inference, not verified.

## TL;DR

- All 15 findings are accepted. Three fixes change: F8 (no scoping flag), F9 (kill-rule thresholds stay) and F10 (cursor batch size, not an in-memory list).
- Backfill 1m bars into the **local** Mongo first. Copy only the range older than prod's first 1m bar to prod with `mongorestore` and no `--drop`. Nothing on prod is overwritten, so the rollback is one `deleteMany` and F1 disappears.
- One clock formula: `clock = bar start + own interval - finest interval`. Single-interval runs keep today's timestamps exactly.
- The reviewers missed one item that decides C's verdict: **the sample for the binding G2 test is not defined.** On the phase-4 window the replica's t is 2.58 (fails 3.0). On C's full selection window it is 3.32 (passes) [V]. The plan must fix the sample before the run.

## Owner decisions that stand (plan.md, 2026-11-12)

1. `min_stop_atr` widens a closer stop and keeps the trade; value 0.5.
2. X applies to the entry and the stop loss, as `entry_buffer_atr` and `stoploss_buffer_atr`.
3. `stoploss_lookback` defaults to 2.
4. G2 binds on in-sample t >= 3.0; the DSR is reported only.
5. The 2022 holdout stays untouched.
6. A paper subscription for C only if C survives phase 4.
7. Backtests run locally on a local Mongo copy, in parallel.

Nothing below overturns any of them. Section 8 gives the owner a trade-off on decision 2 and leaves the call with the owner. Section 9a asks the owner to confirm a default that decision 4 leaves open.

## 1. Findings

| # | Verdict | Reason |
|---|---|---|
| F1 | Accept | `docs/deployment.md:172-175` restores with `--drop` [V]. `upsert_bar` keeps `_id` [V]. Section 5 removes the overwrite, so no restore is needed at all. |
| F2 | Accept | The prod gate turns 1m on for the `01a1c41f` window. Fix in section 4. 489 against 490 is settled there. |
| F3 | Accept | Both obvious rules break a promise. Rule in section 2. |
| F4 | Accept | `insert_many` does `find_one` + `update_one` per bar and swallows errors [V]. The 15m backfill of 2026-11-11 ran inside the VPS api container (`.cache/bf15.sh`) [V], so the tunnel route has no precedent. The "10+ hours" figure is the reviewers' inference. |
| F5 | Accept | `_is_finest` pins the finest interval [V]. Precision: a fill is lost only when the stop is changed or cancelled before the next 1m bar; otherwise it is late. Fix in section 3. |
| F6 | Accept | Section 5 uses no tunnel and no prod-pointed `.env`. Tests use an ephemeral container and `pocketquant_test` (`tests/backtest_test/conftest.py:26-27`) [V], so they do not touch the local backtest data. |
| F7 | Accept | The prod roles sum to 0.95 (`deploy/compose.prod.yml:82,98,115`) [V]. Use 0.05. |
| F8 | Accept the disclosure and the measurement. **Reject scoping.** | Section 6. |
| F9 | Accept the labels and the fixed start. **Keep the kill-rule thresholds.** | Section 7. The replica gives t 2.58 on the same window [V], so the rule tests engine agreement, as it was written to. |
| F10 | Accept the risk, **change the fix** | The risk is an inference. Loading entry bars into a list grows api memory on a long UI run. Put `.batch_size(1000)` inside `BarRepository.stream` (no new parameter). It bounds the idle time of both cursors. |
| F11 | Accept, simplify | The count was 0 at 14:32. Do not script a migration in advance. If the count is not 0 at release time, stop and ask the owner for each document's new integer value. |
| F12 | Accept | `stoploss_lookback >= 1`, `takeprofit_lookback >= 0`, floats `math.isfinite` and `>= 0`, and `max(lookbacks) x ratio <= 500`. The baseline comes from section 4. |
| F13 | Accept | Match rule in section 7. |
| F14 | Accept | Use `/health`. List subscriptions by broker and state in the owner question. |
| F15 | Accept as a real conflict | Section 8. |

No finding is wrong on its evidence. One note: the task says the controller verified F14; the findings file says F15. I treated both as unverified by me except where marked [V].

## 2. Clock rule (F3)

**One formula, for every published bar:**

`clock = bar.datetime + step(bar's interval) - step(finest)`

- `finest` is 1m in a merged run, and the entry interval in a single-stream run.
- Set `set_simulation_time(clock)` and `occurred_at=clock`. `bar_start` stays `bar.datetime`.
- Do not set `bar_end` on the event. It turns on the live stale and gap checks and the snapshot write (`strategy_app_service.py`, `_handle_bar` and `_on_bar_completed`) [V].

| Bar | Clock |
|---|---|
| Single-stream entry bar starting T | T (today's value) |
| 1m bar starting t, merged run | t |
| Entry bar starting T, merged run | T + step - 60 s (the start of its last 1m slot) |
| Stand-in bar for an empty bucket (section 3) | T |

**Publish order, merged run.** For each entry bar E in time order:

1. Publish every 1m bar not yet published whose start is before E's end, oldest first.
2. If none of them started at or after E's start, publish the stand-in (section 3).
3. Publish E.

After the last entry bar, publish any 1m bars left in the window.

**Meaning of the stored times.**

| Field | Single stream | Merged |
|---|---|---|
| `placed_at` | start of the signal bar | signal bar end minus 60 s |
| `opened_at` | start of the entry bar that filled | start of the 1m bar that filled |
| `exit_time`, SL or TP | start of the bar that hit | start of the 1m bar that hit |
| `exit_time`, strategy exit | start of the deciding bar | deciding bar end minus 60 s |

**Why it holds [V by reading the code paths].**

- **No look-ahead.** A stop exists only after its signal bar is published, and that happens after every 1m bar of its bucket. The broker also needs `placed_at < occurred_at`: T+14 min is before T+15 min.
- **Monotonic.** 1m T+14 has clock T+14, entry bar T has clock T+14, 1m T+15 has clock T+15. The clock never decreases.
- **SL and TP.** `_sl_tp_hits` skips a position with `opened_at >= occurred_at`. A fill on 1m bar t is checked for TP from 1m bar t+1, as today.
- **Dates.** A bar-end clock would move a 23:45 decision into the next day. This rule keeps it at 23:59.

**Single-interval runs keep today's timestamps exactly.** That includes any run whose window starts before the first 1m bar.

**Comparison keys.**

- Same mode (baseline, golden, replica against a coarse engine run): `(side, entry_time, exit_time)`, exact.
- Across modes (a 1m run against a coarse run or the replica): `(side, floor(entry_time, entry interval))`. The floored time equals the coarse value, because a coarse fill is stamped with its bucket start.

**Tests to add.**

- The clock never decreases across the published events of a merged run.
- Every trade has `exit_time >= entry_time`.
- Every filled stop has `opened_at >= signal bar start + entry step`.

## 3. Gaps (F5)

**Pick: per-bucket fallback.** A threshold alone is rejected: it would leave a shipped engine that drops fills and switches off SL and TP inside a hole in any later UI backtest.

- **Rule.** In a merged run, when no 1m bar starts inside an entry bar's bucket, publish that entry bar's OHLCV once as an event with `interval="1m"`, `bar_start` = bucket start and clock = bucket start, just before the entry bar. The broker then applies today's coarse rule to that bucket. No broker change.
- **Keep the run-level gate** (first 1m bar at or before `start_date`). A run without coverage then stays byte-identical to today. A run made only of stand-ins would not be: its strategy-exit times would move by 14 minutes.
- **Correct phase 2 step 6:** a bucket without 1m bars is filled by the coarse rule; it is not delayed.
- **Test:** a stop whose only touching bucket has no 1m bar fills in that bucket at the coarse price.

The fallback does not cover a bucket that has some 1m bars but misses the minute that touched a level. That is a data check for phase 4 only, not an engine rule. These numbers are my settings:

- `E0` = entry buckets in the window with no 1m bar. `E1` = buckets with 1m bars whose 15m high or low differs from the 1m envelope by more than 0.01.
- Stop phase 4 and report if `(E0 + E1) / buckets > 1%`, or if any run of consecutive `E0` buckets is longer than 96.
- The report gives, per run, the trades whose entry bucket is in `E0` or `E1`. Above 2% of a run's trades, G1 counts them as ambiguous.

## 4. Golden check (F2)

**Use run `01a1c980`, not `01a1c41f`.** Its window starts 2023-01-01, before any 1m bar, so the run-level gate keeps the replay coarse on any DB. No special DB and no flag are needed.

- **DB:** the local Mongo of section 5 (XAUUSD:EXNESS 15m, 1h, 4h, 1d and the `symbols` doc from prod; 1m may be present).
- **Config:** the stored config of `01a1c980`, read from prod read-only: Triple Screen `15m,1h,4h`, `entry_type=stop`, `exit_mode=strategy`, `stop_lookback=80`, spread 0.08, commission 3 bp, slippage 0.1 bp, 10 000 USD, 2023-01-01..2026-11-10 23:59 UTC.
- **Baseline B0 (end of phase 1, code as it is before phase 2):** run that config locally and export the trades to `.cache/golden/b0.csv`. Compare B0 with the stored trades of `01a1c980` (already in `.cache/oos/pull.txt`): 1 991 trades, key `(side, entry_time, exit_time)`. If they differ, stop and report: the bars changed since 2026-11-11, and every replica figure rests on them.
- **G-a (end of phase 2, strategy untouched):** the same config gives the same ordered list as B0, exact on `(side, entry_time, exit_time, entry_price, exit_price, quantity, pnl)`. The run snapshot shows fill interval `15m`.
- **G-b (end of phase 3):** the same config with `stoploss_lookback=20` in place of `stop_lookback=80` gives the same list as B0. This is also the equivalence baseline F12 asks for.
- **Order:** 1 (data, B0), 2 (G-a), 3 (G-b), 4, 5. Make phase 3 depend on phase 2, so that a G-b failure blames only the rename.
- **489 against 490 [V, recomputed from `.cache/oos/pull.txt`]:** 489 is the stored count of `01a1c41f`. In `01a1c980`, 490 trades closed, and 491 opened, in 2025-11-09..2026-11-08. "Same as `01a1c41f`" in my 1356 report was loose wording. The count no longer gates anything.

## 5. Backfill route (F1, F4, F6, F7)

**Pick: backfill into local Mongo, then copy only the range older than prod's first 1m bar to prod.**

- **Rejected, tunnel:** about 1.8 M serial round trips, plus a prod-pointed `.env`.
- **Rejected, VPS api container:** about 900 k bar objects in memory beside the trader.

Phase 4 needs the 1m bars locally anyway (owner decision 7).

**Steps.**

1. **Target guard, before every write and every run.** No `just tunnel` process is running. The repo `.env` is the local one; never copy `remote-db.env`. Print only the host and database of `MONGODB_URL`; the host must be `localhost` or `127.0.0.1`. `db.bars.distinct("symbol")` on the target is empty or exactly `["XAUUSD:EXNESS"]`. Prod holds many symbols, so this tells the two apart.
2. **Prod, read-only.** Check `df -h` on the VPS. `mongodump` `bars` with `{"symbol":"XAUUSD:EXNESS","interval":{"$in":["15m","1h","4h","1d"]}}` and the XAUUSD `symbols` doc to `/opt/pocketquant/backups/`. Do not pass `--quiet`. The "(N documents)" line must equal `countDocuments` of the same query. `scp` the files to `.cache/dumps/` and delete the VPS copies.
3. **Local restore.** `just up`, then `mongorestore` into the local DB. Use `--nsFrom`/`--nsTo` if the local database name differs. Check the counts again.
4. **Armed check.** Read `live_trading` in the prod safeguards doc, read-only. Stop unless it is false. Repeat after step 6.
5. **Timing slice.** Run `provider_bars.py --symbol XAUUSD:EXNESS --interval 1m --days 3 --rate-fraction 0.05 --dry-run`. Pass the four `EXNESS_*` API settings as process environment for that one command, with `EXNESS_LIVE_TRADING=false`. Do not write them into the repo.
6. **Full run into local Mongo.** The same command with `--days 1000`, no `--dry-run`, output to `.cache/bf1m/run.log`. Pass only if `fetched == inserted`, there is no `upsert_failed` line and no `REQUEST_RATE_LIMIT` error. Report the count of `exness.rate_limited_retry` lines. On exit code 1, run it again; the upserts are idempotent.
7. **Local audit.** First and last 1m bar, counts per month, and `E0`, `E1` and the longest `E0` run of section 3. The first 1m bar must be at or before 2024-05-01T00:00Z; otherwise stop (section 7).
8. **Baseline B0** (section 4).
9. **Prod load.**
   - Read `C` = the earliest prod 1m XAUUSD bar time. Record it. By definition no prod 1m bar is older.
   - Dump the local 1m bars with `datetime < C` (`{"$lt":{"$date":"<C>"}}`). The dump's "(N documents)" must equal the local count.
   - Check `free -m` and `df -h` on the VPS, then `scp` the archive there.
   - Restore on the VPS: `mongorestore --archive --nsInclude pocketquant.bars --noIndexRestore --numInsertionWorkersPerCollection=1`, **never `--drop`**. Run it as one ssh command with `< file`.
   - Verify: the prod count of 1m bars older than `C` equals N; the count from `C` on is unchanged or higher; the newest 1m bar keeps advancing; `free -m` is steady.
   - Delete the archives on both sides.
10. **Rollback (F1):** `db.bars.deleteMany({symbol:"XAUUSD:EXNESS", interval:"1m", datetime:{$lt: C}})`. It is exact, because that set was empty before step 9. No backup archive and no `--drop` exist anywhere in this route.

**Effects to state in the plan.**

- Prod bars from `C` on are never rewritten.
- Local 1m bars are all from REST; prod's are REST before `C` and the live sync after. Phase-4 numbers come from the local copy, and the report says so.
- `check_integrity` looks back 7 days only (`integrity_jobs.py:56-61`) [V]. Old 1m bars start no job there. I did not re-read the repair and cascade windows today.

## 6. Scope of the 1m switch (F8)

**Keep it automatic for every symbol and backtest. Add no flag.**

- The design goal is "a backtest fills as live paper does". Live paper acts on 1m bars for every symbol. A switch would create two fill rules to maintain.
- A flag has no second real caller. Its only users would be one-off checks, and section 4 shows those do not need it.
- **Cost.** The api container is its own process (`APP_ROLES: "api"`, `deploy/compose.prod.yml:81`) [V], so a long replay does not block the trader's loop. It does share the VPS CPU and the Mongo pool.
- **Plan changes:**
  - Phase 4 step 4 records events per second and the wall time of a one-year merged run.
  - Phase 5 step 3 tells the owner: every backtest whose window starts after the symbol's first 1m bar now fills on 1m bars, for all symbols; about 16 times the events; the measured time.
  - The run snapshot carries the fill interval.
  - Phase 5 step 6 keeps its docs line.

## 7. Segments, start date, replica match, kill rule (F9, F13)

**Start date.** 2024-05-01T00:00Z, fixed. Delete "or the first full 1m day". If the first local 1m bar is later, stop and ask the owner. The replica figures (A 1 285 trades, C 552) are for that start [V].

**Segments, cut by entry fill time (`opened_at`).**

- **P:** 2024-05-01T00:00Z up to, not including, 2025-11-09T00:00Z.
- **Y:** 2025-11-09T00:00Z up to, not including, 2026-11-09T00:00Z.
- 2026-11-09 and 11-10 count in the window totals only.

| Config | P | Y |
|---|---|---|
| A | Out of sample for A's parameters; second read (first read: `01a1c980`) | In sample (the year that chose A) |
| B | As A, and used to choose `min_stop_atr` by a rule that did not read profit | As A |
| C | Selection data (walk-forward test folds) | Selection data |

- C has no out-of-sample segment. G3 for C is "open", never "pass". C's ceiling in phase 4 is "candidate for incubation".
- Replace "out-of-sample segment" and "in-sample year" in phase 4 step 7 and in the plan's report criterion with this table.

**Replica match rule, fixed now.**

- Run C on the engine over 2023-01-01..2026-11-10 23:59 UTC. The gate keeps it coarse. Check that the snapshot says `15m`.
- Compare with all of `.cache/km3/candidate_trades.csv`: 745 trades, the pessimistic bound, sum +121.3 R, t 3.32 [V].
- Drop trades with `entry_time` before 2023-01-09T00:00Z from both lists (6 CSV rows [V]). The engine's swing window starts empty; the replica's does not.
- Match on `(side, entry_time)`, exact. A matched pair must agree on `exit_time` and exit reason, on entry and exit price within 0.001, and on R within 0.01.
- Pass: at most 3 trades unmatched or disagreeing, counted over both lists, each listed in the report. Otherwise stop, as phase 4 step 2 says.

**Kill rule.** Keep step 8 as written: drop C if mean R <= 0 or t < 1.5 on the 1m run, 2024-05-01..2026-11-10. Add one sentence: "This rule tests that the result survives the engine with 1m fills. Passing it is not evidence of an edge." Changing a threshold now would be a change made after seeing the numbers.

**One diagnostic, not a selection rule (my setting):** if C's 1m-run sum R is outside 67.7..91.7 R (the replica bounds 77.7 and 81.7, plus or minus 10), investigate the engine against the replica before writing the report.

## 8. Stop-loss buffer (F15), for the owner

**Fact.** No planned run uses a non-zero `stoploss_buffer_atr`. The `CLAUDE.md` rule asks for a second real caller for a new parameter.

**What the parameter can do [I].** The stop is `min(swing - buffer, entry - 0.5 x ATR)`. Where the 0.5 ATR floor sets the stop, the buffer changes nothing. It only widens stops that are already wider than the floor. In the sweep the minimum stop removed the fast stop-outs (15.1% to 7.7%), and the entry offset moved them little (7.7% to 7.1%) [V, report 1527].

| Option | Gain | Cost |
|---|---|---|
| A. Ship it now, default 0.0, unit-tested | The owner's decision is delivered in full; about 3 lines; no behavior change | A knob with no evidence, and an owner-granted exception to the second-caller rule |
| B. Add it when a trial that uses it is pre-registered | No unused parameter | The owner's request waits; the strategy file is touched again later |
| C. Ship it and pre-register one trial now (C with 0.1) | The parameter has a real caller | Trial 222 on used data; it can inform, it cannot promote |

**Recommendation: A.** Record the exception in the plan in one line, and run no non-zero value until it is pre-registered. Choose B if the owner does not expect to test it in the next plan. I do not recommend C: one more reading of used data buys little.

## 9. What the reviewers missed

a. **The G2 sample is undefined, and it decides C.** Owner decision 4 binds G2 on in-sample t >= 3.0. From `candidate_trades.csv` [V]: the full window gives t 3.32; from 2024-05-01 it gives 2.58; before it, 2.11. Fix before the run:
   - A and B: t on segment Y of their 1m runs.
   - C: t over the R list of the coarse engine run of section 7 for entries before 2024-05-01T00:00Z, joined with the whole 1m run. The join is not seamless: the 1m run starts flat with an empty swing window. Say so in the report.
   - Report C's t on the phase-4 window next to it.
   - This reading follows the rubric's own definition of in-sample. The owner should confirm it; it is the default if the owner does not answer.

b. **Swallowed errors can thin the trade list silently.** A strategy exception becomes `skipped:strategy_error`, and a fill error is logged as `paper.stop_fill_failed` (`strategy_app_service.py`, `_handle_bar` and `_on_bar_completed`) [V]. A run with either line in its log is void. Capture each run's log and require zero of both.

c. **Silent coarse fallback.** If the first local 1m bar is even minutes after the start, the run-level gate makes the whole run coarse. Check the snapshot fill interval of A, B and C before reading any number.

d. **Exness M1 depth may be a rolling window [I].** `docs/deployment.md:217` gives only a bracket (2024-04-15..2024-05-01). If the window moves with the date, the first served bar passes 2024-05-01 soon. Do section 5 steps 4 to 7 first, today if possible.

e. **Segment cut.** My 1356 report cut by close time; the folds of report 1527 cut by entry time. Section 7 fixes entry time.

f. **Stored Sharpe and drawdown are not rubric inputs.** Compute every rubric number from the trade list, as `.cache/oos/an.py` does. The mark-to-market handler must skip non-entry bars (phase 2 step 4). In a merged run, exit times no longer equal mark-to-market times, so an equity curve over the persist cap no longer keeps its trade points (`_downsample_equity_curve`) [V]. Accept it and say so, or stamp the mark-to-market point with the clock.

g. **A-against-`01a1c980` comparison.** The lists diverge after the first changed trade. Report four classes on the cross-mode key: same exit; same entry and a different exit, with the old same-bar `auto_sl` cases counted as "fill-bar stops removed"; only in the old run; only in the new run.

h. **Privacy hook.** A read of `../pocketquant-config/*.env` is blocked by a hook until the owner approves; it blocked me today. The controller must get that approval before section 5 step 5. I could not check that the `EXNESS_*` key names in the prod env file match `core/config.py`.

## What to avoid

- `--drop` with any filtered archive, and any rewrite of prod bars from `C` on.
- A config flag or a second fill path for the 1m switch.
- A bar-end clock, or setting `bar_end` on backtest events.
- Reading C's profit before the replica match passes.
- Moving the start date, the kill thresholds or the min stop after a number is seen.
- Running any non-zero `stoploss_buffer_atr`, or any neighbour of C.

## Assumptions

| Assumption | Confidence | What would change the answer |
|---|---|---|
| The repo `.env` on this machine is the all-local file, and `just up` gives a Mongo that tests do not share. | Medium | A prod-pointed `.env`: restore the local one first. |
| The prod env file holds `EXNESS_API_BASE_URL`, `EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY` and `EXNESS_SECRET_KEY`. | Medium (field names in `core/config.py` [V]; file not read) | Other names: map them; never copy values into the repo. |
| Local and prod 15m, 1h and 4h bars equal the bars `01a1c980` and the replica used. | Medium | B0 differs from the stored run: stop (section 4). |
| A bucket with 15m data and no 1m bar is rare in Exness data. | Medium | The audit shows more than 1%: phase 4 stops (section 3). |
| The Mongo idle-cursor limit is 10 minutes, and the `mongorestore` flags named exist in the installed tools. | Medium (from memory, not fetched today) | Check `mongorestore --help` on the VPS first. |
| The owner accepts the G2 sample of section 9a. | Medium | The owner wants the phase-4 window only: C is expected to fail G2 (t about 2.6). |

## Unresolved questions

1. Owner: G2 sample for C, the full selection window (recommended) or the phase-4 window only?
2. Owner: stop-loss buffer, option A (recommended), B or C?
3. Owner: approve one read of the `pocketquant-config` env files for the backfill command.
4. Is the Exness M1 history a rolling window? Unknown until the audit shows the first bar.

Status: DONE_WITH_CONCERNS
Summary: All 15 findings are accepted, with changed fixes for F8, F9 and F10 and one concrete rule for each open design question. The G2 sample for candidate C and the stop-loss buffer need the owner's answer; the plan can be patched with the stated defaults meanwhile.
