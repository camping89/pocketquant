# Advice: finish the MTF foundation plan now, without waiting and without fake data

Date: 2026-11-02 17:40 UTC (2026-11-03 00:40 Bangkok). Plan: `plans/261101-0843-stf-to-mtf-foundation/`. Interview: 4 questions, recorded in `advise-261103-0025-finish-mtf-plan-now-state.md`. Preview confirmed: `advise-261103-0025-finish-mtf-plan-now-preview.html`.

## Needs from you

1. Approve three plan amendments before the run, so the executor is not forced into the Failure Protocol. Record them in `plan.md` Owner decisions as D13, D14, D15 (D11 and D12 are already used by the synthesis). Recommended: approve all three; the wording is in "What you should do", step 1.
2. During the run: one `DRAWER OK` reply, one `Cancel pending` click only if a stop is resting, and the two explicit `yes` replies for the STF list and the orphans (Tasks 17.4 and 17.5). These stay as the plan wrote them.

## Verdict

Your instinct is right and your proposed means is wrong. The plan is not blocked by missing capability evidence; it is blocked by its own wording. Three of the four missing observations already have real evidence on prod that nobody has read back yet: you closed the primary position through the drawer at about 16:22 UTC (obs-3), the `1h,4h,1d` subscription sent a strategy EXIT on its 12:00 UTC bar (obs-2 by any-subscription rule), and the drawer you used is obs-6. obs-4 needs a resting stop, which Triple Screen re-places on the next 15m bar while the setup holds, so it is either available right now or honestly skippable. The 7-day 1d window is the only true wait, and it protects less than it looks: `cascade_for_symbol` is one function shared by the live job and the batch run (`sync_jobs.py:403`, `tracked_symbols_backfill.py:160`), Phase 16 already ran it over the whole history, and the vendor comparison it guards has never been executed once. Simulating orders and positions by writing synthetic documents to prod would prove nothing the test suite does not already prove, would pollute the paper trade record of a subscription you keep running, and breaks your own rule against fake data to satisfy a check. The right move is a small set of plan amendments and one resumed Phase 17 run today, about one to two hours plus your replies.

## What you should do

1. Amend the plan file first (Markdown only, no CI), then commit `docs(plans): amend phase 17 for a same-day close`:
   - D13 (obs-2): a strategy EXIT trade from any of the three Triple Screen paper subscriptions satisfies obs-2, recorded as `obs-2 PASS trade=<id> sub=<id>`. The three subscriptions run the same deployed code and the same engine EXIT path. The executor runs STATUS with the `1h,4h,1d` id `01a19bbf-9788-7487-8c7e-9f110ed8c595` and `started_at=2026-11-02T10:13:00Z`, applies the existing inference rule (`tp=None`, exit inside the SL), and greps EXITLOG with that subscription id. If no subscription has such a trade (an EXIT sent while flat only cancels the stop, see `test_exit_when_the_setup_is_gone_with_a_stop_armed`), record `obs-2 SKIPPED by owner` and cite `test_strategy_mode_sets_no_take_profit_and_exits_on_a_tide_flip` and `test_close_cancels_the_stop_and_closes_the_position` in the A7 row.
   - D13 (obs-3): `requested_at` is taken from the subscription document's `manual_action_outcome.at` (D7 records `{action, outcome, at}`), not from a chat reply. Pass rule unchanged: no `open_position` line, `manual_action=None`, outcome contains `accepted`, newest trade `exit_time` within 120 s of `at` or later, `exit != entry`.
   - D13 (obs-4): asked only if STATUS shows a `stop_market` order with `status=submitted` or `pending` and the XAUUSD session is open (closed 20:58 to 22:00:30 UTC); otherwise `obs-4 SKIPPED by owner`, citing `test_a_cancelled_stop_never_fills` and `test_cancel_leaves_the_position_open`.
   - D14 (Task 17.2): the window is the latest 14 stored days ending at the current UTC midnight (`LAST = today 00:00Z`, `FIRST = LAST - 14 days`, `n_bars = 20`); pass rule unchanged, `mismatches=0 repair_1d=0`, `min_days >= 5`. A6 is recorded as met on that output; no dated re-check. This is your call from Q2; the cost is in Trade-offs.
   - D15 (new Task 17.2b, read-only): a code review of the live 1d cascade path, written into the phase report as a findings section. Scope: `cascade_aggregator.py` `compute_boundaries` and `cascade_for_symbol` (lines 60-175), `sync_jobs.py` `sync_1m` (383-422), the schedule block (718-780), `sync_backfill` and `SYNC_INTERVALS` (44-62, 425-432), `sync_repair` (477-518); `exness_session_calendar_adapter.py` `bar_start`, `session_date`, `session_close` (170-240); `bar_repository.py` `upsert_bar` (42-98). The review answers the four questions in step 5. A finding that the 1d bar can go wrong in future is a stop condition: the executor reports it and asks you; it does not patch code inside this plan.
2. Resume Phase 17 with `/eve:cook-plan ... --from 17`. The entry gate is unchanged; the resume rule lets the phase skip obs-1 and obs-5, which already pass.
3. The executor reads STATUS once, records obs-3 and obs-2 from the existing prod state, asks you for obs-4 only if a stop rests, asks for `DRAWER OK`, then runs the amended 17.2 and the 17.2b review.
4. Tasks 17.3 to 17.7 run exactly as written: id lists, your two yeses, children first, every `deleted_count` asserted, re-list to zero, guard collections unchanged. Task 17.8 closes the plan.
5. Make the 17.2b review answer these four questions, each with the file and line it rests on:
   - Bucket definition. The Exness 1d bar is stamped at UTC midnight with a `session_date` and covers `[00:00, 24:00)` UTC (`test_a_session_calendar_cascades_its_daily_bar_at_utc_midnight`), while the session runs 22:00:30 to 20:58 UTC. Does `ExnessAdapter.fetch_ohlcv` return 1d candles with the same stamp? The 17.2 script joins by `datetime`, so a vendor stamped at 22:00 would show every day as `diff`. Running the comparison today answers this empirically.
   - Finalisation. `sync_1m` runs every minute at +12 s with a 100-minute lookback, and `compute_boundaries` keeps any bucket that overlaps the range, so the day bucket is re-aggregated every minute until about 01:40 UTC the next day (`test_1d_today_bucket_kept_alive_through_the_day`). Any 1m bar that lands after that (a `sync_repair` at 12:00 UTC, a late REST fill) is never folded into the 1d bar. Is that acceptable, and does `sync_repair` re-cascade after repairing 1m?
   - Overwrite precedence. `upsert_bar` has no source precedence: it rewrites OHLCV whenever the values differ and stamps the writer's `source`; equal values return early. `sync_backfill` at 03:00 UTC still lists `DAY_1` and writes `rest_backfill` with no cascade-aware skip (grep of `sync_jobs.py` and `sync_service.py` found none). Inference: a REST 1d bar that differs from the cascaded one replaces it every morning after the bucket has left the lookback, which would turn the 17.2 `source == "cascade"` check red from 2026-11-03 03:00 UTC on. The comparison today, run before 03:00 UTC, measures whether vendor and cascade values differ at all; if they are equal the overwrite is a no-op and the risk is closed.
   - Monitoring. `sync_verify_cascade` runs hourly but compares 5m only (`reason="no_cascade_5m_bars_in_window"`). There is no 1d check in prod. State this as negative knowledge in the report; adding one is outside this plan.

## What you shouldn't do

- Do not insert synthetic `orders`, `positions` or `trades` documents into prod Mongo. They would sit under the paper subscription id, so Task 17.3 would not even list them as orphans, and they would stay in the record of a subscription you keep running.
- Do not build a local end-to-end "simulation". `ScriptedStrategy` lives only in `tests/strategy_doubles.py`; forcing a signal on a running trader needs a registry entry in `src`, which is code outside the plan, and it still would not exercise the prod wiring that obs-* exist for.
- Do not skip all four observations through the D12 escape hatch when three of them have ids waiting on prod. A7 with real ids costs ten minutes more than A7 on tests alone.
- Do not let the executor "fix" a review finding inside Phase 17. The plan's rule is that a failed Verify goes to `kongming` and a scope change goes to you; a code change here would also break the entry gate of the close.
- Do not run Task 17.2 after 03:00 UTC on 2026-11-03 with the current script. If the backfill overwrite in step 5 is real, every differing day would show `source=rest_backfill` and the pass rule would fail for a reason that is not an arithmetic error.
- Do not widen the delete filter or call `TrackedSymbolService.remove`; it cascades the symbol's bars and subscriptions.

## What could be better

1. Cheapest, highest value: run the comparison tonight, before 03:00 UTC. Same script, two changed lines. It settles the bucket-stamp question and the overwrite question at once.
2. If the comparison shows `diff` rows only because of `source=rest_backfill` with equal values, the honest next step after this plan is a one-line change in `_sync_by_intervals` to skip cascaded intervals for symbols that have stored 1m bars, or dropping `DAY_1` from `SYNC_INTERVALS` for session calendars. That is a new small plan, not a Phase 17 fix.
3. The obs-3 `requested_at` taken from `manual_action_outcome.at` is better evidence than the chat timestamp the plan originally asked for; keep that rule for any future manual-action observation.

## My take and how to get there

Amend, then run once. Order of the day: commit the amendments (10 minutes); resume Phase 17 (entry gate passes on a Markdown-only commit once pushed); STATUS read and obs-2, obs-3 from existing state (10 minutes); obs-4 and obs-6 asks (your two replies); the amended 17.2 before 03:00 UTC and the 17.2b review (30 to 45 minutes); 17.3 lists and your two yeses; delete, re-list, docs check, acceptance table, `ak plan update`, push (20 minutes). If 17.2 prints a `diff` row, stop and read the `source=` column before deciding anything: `rest_backfill` means the precedence question in step 5, `cascade` with different values means the arithmetic or the vendor's stamp, and only the second kind is a Phase 03 rollback question.

## Benefits

- The plan closes today with every acceptance row citing a prod id or a named test, not a wait.
- A7 keeps real prod evidence for stop entry, manual close, snapshot and the drawer; EXIT and cancel are covered by prod ids where they exist and by named tests where they do not.
- The 1d comparison runs for the first time, and the review turns "wait a week" into four answered questions about how the cascade behaves in future.
- No fake data, no code change, no prod write outside the plan's own delete.

## Trade-offs

- Your Q2 choice drops the live-timing evidence the 7-day window would have given. The code shows the day bucket finalises by about 01:40 UTC and is then exposed to the 03:00 UTC REST overwrite; without a re-check nobody will see a drift until a strategy on `1h,4h,1d` behaves oddly. I recorded my disagreement; the cheapest hedge is to re-run the 17.2 script by hand once in the week of 2026-11-09, outside the plan.
- obs-2 from a non-primary subscription proves the EXIT path on prod but not on the configuration you picked as primary. Same code, different interval set; the risk is in the strategy's setup detection, not in the platform.
- `obs-4 SKIPPED by owner` leaves manual cancel proven by tests and the Phase 02 spike only. If a stop rests when the executor looks, take the click.
- The delete is irreversible by your decision C12. The exact lists in `stf-delete-ids.json` are the only record of what went.
- The recommendation stops being right if the comparison shows value differences with `source=cascade`: then the cascade arithmetic or the vendor stamp is wrong, A6 is genuinely failed, and closing the plan would hide it. Switching away then costs a Phase 03 rollback decision and the plan stays open.

## Unverified

- The prod state after 16:22 UTC: the owner's close outcome, whether a new stop rests, whether the `1h,4h,1d` EXIT produced a trade. Source: the orchestrator's message and the Phase 16 report. Confirmed by: the Phase 17 STATUS read.
- Exness 1d candle timestamps versus the UTC-midnight stamp. Looked at `exness_session_calendar_adapter.py` and the cascade tests only; `fetch_ohlcv` output was not fetched. Confirmed by: the first 17.2 run.
- That REST backfill really overwrites a cascaded 1d bar on prod. Derived from `upsert_bar` (no precedence), `SYNC_INTERVALS` (includes `DAY_1`), the 03:00 UTC cron, and the absence of a skip in `sync_jobs.py` and `sync_service.py`. Confirmed by: counting XAUUSD:EXNESS 1d bars by `source` after 2026-11-03 03:00 UTC.
- Whether `sync_repair` re-cascades after repairing 1m bars. Not read (`sync_jobs.py:477-518`). Confirmed by: the 17.2b review.

## Work checklist

- [ ] Add D13, D14, D15 to `plan.md` Owner decisions and edit `phase-17-observe-compare-delete.md` accordingly (obs-2 any-sub rule, obs-3 `requested_at` from `manual_action_outcome.at`, obs-4 conditional, 17.2 window, 17.2b review task with its Verify: a findings section with four answered questions).
- [ ] Commit `docs(plans): amend phase 17 for a same-day close`, push `develop`.
- [ ] Resume Phase 17; entry gate; STATUS on the primary and on `01a19bbf-9788-7487-8c7e-9f110ed8c595`.
- [ ] Record obs-3 from the existing close; obs-2 from an EXIT trade or `SKIPPED by owner` with test names.
- [ ] obs-4: ask Cancel only if a stop rests and the session is open; else `SKIPPED by owner`.
- [ ] obs-6: owner replies `DRAWER OK`.
- [ ] Run the amended 17.2 before 2026-11-03 03:00 UTC; paste the output; stop and ask on any `diff`.
- [ ] Write the 17.2b review findings (four questions, file and line for each).
- [ ] 17.3 id lists; 17.4 and 17.5 explicit yeses; 17.6 delete children first; 17.7 re-list to zero.
- [ ] 17.8 docs line test, A1-A13 table with evidence lines, `ak plan update pocketquant/261101-0843 --status completed`, commit, push.

## Success metrics

- `grep -c -E "^obs-[1-6] (PASS|SKIPPED by owner)" reports/phase-17-observe-compare-delete.md` prints `6`, with at least obs-1, obs-3, obs-5 as `PASS`.
- The 17.2 output ends with `min_days=<n>` where `n >= 5` and `mismatches=0 repair_1d=0`.
- The phase report has a `## 1d cascade review` section answering bucket definition, finalisation, overwrite precedence and monitoring, each with a file and line.
- `stf_total=0 orphans_total=0 paper=running/running` after the re-list; `tracked_symbols` count unchanged.
- `grep -c "^status: completed$" plans/261101-0843-stf-to-mtf-foundation/plan.md` prints `1`; `HEAD` equals `origin/develop`.
- Seven days later, by hand: the 17.2 script re-run prints `mismatches=0 repair_1d=0` (hedge, outside the plan).

## Handoff brief

```text
Objective: close plan 261101-0843 today by amending Phase 17 (D13 obs rules, D14 same-day 1d comparison, D15 read-only 1d cascade review), then running Phase 17 once to the end including the STF and orphan delete.
Done means: phase-17 report ends with Result: PASS; six obs-[1-6] lines (PASS with ids or SKIPPED by owner with test names); 17.2 output mismatches=0 repair_1d=0 min_days>=5; a "1d cascade review" findings section answering bucket definition, finalisation, overwrite precedence and monitoring with file and line; stf-delete-relist summary stf_total=0 orphans_total=0 paper=running/running; plan.md status: completed; HEAD equals origin/develop.
Out of scope: synthetic documents in prod Mongo; local end-to-end simulation; any change under src, tests or web; a dated re-check on 2026-11-09; changes to the three running paper subscriptions.
Constraints: plan.md Conventions (entry gate, Failure Protocol, [ASK] explicit yes in Vietnamese, NOT_YET on no); D5, D7, D12; C12 no backup; never TrackedSymbolService.remove; run the amended 17.2 before 2026-11-03T03:00Z; prod reads and admin calls only through PRODPY; remove .cache/ssh/vps_key before every exit.
Stop and ask only if: the 17.2 output shows any diff row or repair_1d above 0 (report the source= column); the 1d cascade review finds the 1d bar can be wrong in future; a Verify fails for a reason the Failure Protocol does not resolve; any action would delete data outside the exact id lists; a change outside plans/ or docs/ seems required.
```
