---
title: Phase 8 verification — rows 10 and 11 do not match their literal pass clauses
date: 2026-10-22
author: kongming (advisory only; no code, plan file or prod touched)
plan: pocketquant/plans/260921-1436-asset-class-index-futures/phase-08-close-open-metrics.md
---

# TL;DR

Row 10 passes in substance: the one `1w` insert on 2026-10-17T03:00Z is the closed week's bar landing at the first backfill after the Friday close, which is the adapter's closed-bar rule working; my own pass clause in the phase ("no backfill insert") was mis-specified. Row 11 fails as worded and the cause is a timing defect in the verify job, not in the cascade: `sync_verify_cascade` fires at HH:00:00, `sync_1m` at HH:00:02, and the verify compares the newest stored 5m bucket while that bucket still lacks its last minute. The delayed feed only shifts which bucket is newest; crypto diverges the same way with zero lag. Record row 11 as "Fail as worded; cascade correct on every completed bucket; verify-job defect diagnosed; follow-up fix filed", re-word the metric so vendor fetch failures do not break a "24 consecutive" count, and go to Task 6 now. Do not expand this phase into a code change and deploy.

# Reframed problem

The decision is not "how to make rows 10 and 11 pass" but "what is the honest record for a close-out phase that was declared no-code, when one pass clause was written wrong and one metric measures a job that has a defect of its own". Requirements: no prod risk, no code in this phase unless the user widens it, a record that a reader in a year can trust, and the plan archived if nothing load-bearing stays open.

# Verified facts (file:line, read on develop at `0dbf98ac`)

1. **Job order.** `sync_verify_cascade` cron `0 * * * *` with no `second` (fires at HH:00:00), `sync_1m` cron `*/1` with `second=2` — `sync_jobs.py:843-864`. Both TradingView fetches go through one `asyncio.Lock` (`tvdatafeed_client.py:102,117`); the verify fetch starts first.
2. **What the verify compares.** `_verify_one_symbol` fetches 12 REST 5m bars and compares every one that has a stored 5m counterpart, including the newest — `sync_jobs.py:543-580`. Nothing excludes a bucket that is still filling.
3. **The stored bucket can be short by design.** The cascade persists whatever 1m bars a bucket has and says so: "An open bucket is still filling, a delayed feed fills closed buckets late" — `cascade_aggregator.py:207-215`. The `partial_aggregate` warning was removed on purpose (`a9233245`).
4. **The 1m sync never stores the vendor's newest bar while open.** The adapter drops bars at or after `calendar.bar_start(now, interval)` and, on a non-realtime plan while the market is open, also drops the frontier bar by position — `tradingview_adapter.py:75-109`. So at HH-1:59:02 with a ~600 s lag the vendor's 1m frontier is HH-1:49; it is dropped; stored 1m ends at HH-1:48; the stored 5m HH-1:45 bucket holds 4 of 5 minutes until `sync_1m` at HH:00:02 stores HH-1:49 and the cascade rewrites the bucket.
5. **The REST side of the comparison is complete.** At HH:00:00 the 5m fetch has cutoff HH:00; the vendor's forming 5m bar (HH-1:50 on a 600 s delay) is the frontier and is dropped; HH-1:45 is the newest REST bar and is closed at the vendor. 12 fetched minus 1 frontier = 11 compared, which is the measured `compared=11`.
6. **Crypto has the same race without lag.** Binance caps at the last closed bar (`binance_adapter.py:82-85`): at 03:00:00 the REST 5m newest is 02:55, complete; the 02:59:02 sync stored 1m only through 02:58 (cutoff 02:59), so the stored 02:55 bucket has 4 minutes. `compared=12`, newest bucket divergent — the measured crypto alert. The 2026-09-24 addendum saw exactly this and called it "consistent but not proven" (`completion-report.md:249-255`).
7. **Thresholds explain the field pattern.** Volume 5 % (`sync_jobs.py:105`): one missing minute of five is ~20 % short, so volume always flags. Price 0.01 % (`:104`): ES at ~6,800 flags close when the missing minute moved more than ~0.7 points (about 3 ticks) — sometimes. High/low flag only when the missing minute extended the range — sometimes. That is the measured "mostly volume-only, sometimes close/high/low".
8. **Row 10 mechanism.** `sync_backfill` runs on a shut market for up to one week after the close (`grace` = the longest interval in the list, `sync_jobs.py:187-194`). On Saturday 03:00Z the CME calendar's `session_date` returns the NEXT session (`cme_globex_calendar_adapter.py:112-127`), so `bar_start(now, 1w)` = Sunday 2026-10-18T22:00Z (`:177-182`). The closed week's bar at 2026-10-11T22:00Z is below that cutoff and the market is closed, so the frontier drop does not apply (`tradingview_adapter.py:90-99`, which names "the last closed daily and weekly bars never persisting" as the bug this rule fixed). The bar can first persist on the first backfill after Friday 21:00Z, which is 2026-10-17T03:00Z. `created_at 03:00:27Z` matches.
9. **A deploy today would carry only the fix.** `git log origin/master..develop -- src web` is empty (local `master` is stale; `origin/master` is `b30ea30c`). Deploy is a `master` push (`docs/deployment.md:7-15`).
10. **The misaligned-bars log event carries no symbol.** `market_data.sync.misaligned_bars_dropped` logs `count, interval, calendar_id, sample_times` (`bar_filters.py:79-85`). A per-symbol grep of that event returns 0 by construction unless the logger binds a symbol from context, which I did not verify. The per-symbol figure lives in `job_history` details as `filtered_misaligned` (the 17-19 you already saw on the backfill).

# Answers

## 1. Is the row-11 hypothesis sound?

Half. The REST bar is not "unfinished": the adapter drops the forming and frontier bars, so the newest REST bucket is closed at the vendor (fact 5). The stored side is not "captured while forming" either: it is missing its last minute because the verify runs 2 s before the sync that stores that minute (facts 1, 4). The lag is not the cause; crypto shows the identical pattern at zero lag (fact 6). So the proposed rule "exclude bars newer than now - lag - one interval" is the wrong fix: it depends on a lag that varies 10-15 minutes and does nothing for crypto.

**Cheap read-only confirmation (Mongo, no vendor call).** For `ES1!:TRADINGVIEW`, for each alert hour HH in {03,04,05,06,07,08,10} and the ok hour 09:

- the 1m bar with `datetime = (HH-1):49` — read `created_at`. Prediction: at or after HH:00:02 for every alert hour (the minute landed after the comparison); before HH:00:00 for the 09:00 ok hour (lag briefly under 600 s, so 08:49 had closed at the vendor by 08:59:02).
- the 5m bar with `datetime = (HH-1):45` — read `updated_at` and `source`. Prediction: `updated_at` at or after HH:00:02 and `source = cascade` for the alert hours (rewritten after the verify read it); the diff-aware upsert only bumps `updated_at` on a value change (`bar_repository.py:71-78`), so this is direct evidence the compared value changed.
- same for `BTCUSDT:BINANCE`: 1m `02:59` `created_at` at or after 03:00:02 (always true by construction, which is the point: provider-independent).

That is seven documents per symbol and settles it. **Do not run a one-off TradingView fetch from a second process.** The client docstring says this process never opens two scraper sockets at once because the unofficial endpoint can ban the IP (`tvdatafeed_client.py:13-17`); a second process on the same VPS during a session can overlap `sync_1m` at :02 and the quote pollers, and the plan already records that the scraper drops bursts. It would also prove nothing the timestamps do not.

**One more cheap grep, because it shapes the follow-up:** timestamps of the 14 ES `no_progress` lines — how many fall in minute :00 or :01. The verify job's three scraper calls at HH:00:00 share the lock with `sync_1m` at HH:00:02; if the no-progress lines cluster there, the verify burst is starving the sync it checks, and the follow-up should also move the job off the top of the hour. This is inference until counted.

## 2. Row 11: which option?

**(a) plus the re-wording part of (c).** Record: "Fail as worded. 8 of 24 runs observed (03:00-10:00Z, container up since 02:01:48Z): ES 1 ok (11/11), 5 alerts (10/11 match, the one divergent bucket is always the newest stored bucket), 2 vendor fetch failures. Every completed bucket matched across 8 runs x 3 futures symbols. Cause: the verify job compares the bucket still filling, 2 s before `sync_1m` stores its last minute (file:line as above). Follow-up fix filed; not in this phase."

Why not (b): the phase was declared no-code; the fix is small (see below) but it needs a `master` push, which restarts the container, clears the log window and starts a new 24-run clock, so the plan could not close before 2026-10-24. The benefit is a literally green row in a plan whose futures work is parked while the project looks for a profitable Exness strategy. And (b) alone still cannot pass the literal metric: ES had 2 vendor "no series" failures in 8 runs; at that rate the chance of 24 consecutive `.ok` lines with no `symbol_failed` between them is well under 1 %, so the wording must change whatever path is taken.

Why not waiting for 2026-10-23T02:00Z: the remaining 16 runs cannot change a mechanism that sits in the code, and the literal "24 consecutive" is already unreachable because of the vendor drops. Say that in the record instead of pretending the window matters.

**Re-worded metric (for the follow-up, not for this phase's row):** "24 consecutive completed comparisons with `divergence_count = 0` for ES; a run where the vendor returned no series is skipped, not counted; the bucket that contains the stored 1m frontier is excluded from the comparison."

**Follow-up fix, smallest form (for the record; do not implement here):** in `_verify_one_symbol`, after matching REST bars to stored bars, drop the newest matched bucket from the comparison. Reason it is robust: stored 1m bars arrive in order, so the only stored 5m bucket that can be short is the one holding the 1m frontier, and the newest matched bucket is either that one or an older, complete one. It needs no lag value, no extra repository read, and works for both providers. About 4 lines plus one test (12 REST bars, 12 stored, newest stored short by one minute: expect `compared = 11, divergence_count = 0`). Optional second change in the same fix, only if the `no_progress` grep above clusters at :00: move the verify cron to minute 30 so its three scraper calls stop contending with `sync_1m` at the top of the hour. The YAGNI alternative is to delete the job and the metric; it has found nothing in a month except its own artifact. Present both to the user; default is the 4-line fix.

Because the phase has an [ASK] in Task 6 already, add the row-11 choice to that same question: "Row 11: record diagnosed Fail and file the follow-up (recommended), or widen this phase to fix, deploy and re-measure (closes no earlier than 2026-10-24)". One question, one default.

## 3. Row 10: pass in substance?

Yes. The literal clause "no futures `sync_backfill` detail with `bars_inserted > 0`" came from my 2026-10-22 11:45 report and was wrong: the weekly bar closes Friday 21:00Z and can only persist on a backfill after that, so the Saturday 03:00Z run is exactly where it must land (fact 8). What the clause meant — no intraday bar is written while the market is shut — holds: 2,874 `sync_1m` runs, 2,874 `skipped/closed` details per symbol, zero `completed`, and the 2026-10-18 backfill inserted 0.

Record it as: "Pass. Window 2026-10-16T21:01Z to 2026-10-18T22:00Z: 2,874 `sync_1m` runs, every futures detail `skipped/closed`, zero `completed`. `sync_backfill` 2026-10-17T03:00Z inserted one `1w` bar per symbol (datetime 2026-10-11T22:00Z, `session_date` 2026-10-12, created 03:00:27Z): the week that closed Friday, written at the first run after the close, by the adapter's closed-bar rule (`tradingview_adapter.py:90-99`). 2026-10-18 run: 0 inserts. The phase's 'no backfill insert' clause was mis-specified and is corrected here." Keep the measured numbers; do not soften the fact that the clause was wrong.

Two optional checks, cheap and read-only, that would strengthen the row: (i) `created_at` and `source` of the ES 1d bar at 2026-10-15T22:00Z (Friday's session). It must be at or after 2026-10-16T21:00Z; if it is earlier, a forming daily bar persisted, which is a real finding to add to the follow-up. My expectation (inference) is Saturday 00:00Z via `sync_repair` with `source = rest_repair`, since `_run_repair` has no closed-market skip (`sync_jobs.py:401-436`), which would explain why the 03:00Z backfill had no 1d insert. (ii) Compare `filtered_misaligned` 17-19 on the weekend backfill with a weekday backfill (10-21 or 10-22). If equal, it is the standing figure and belongs in row 4 as a `job_history` number, not a weekend effect.

## 4. Anything else in these numbers?

- **Row 4's `misaligned_bars_dropped 0/0/0` is probably a grep artifact** (fact 10). Count the event without a symbol filter, and report the per-symbol number from `job_history.details.filtered_misaligned`. Not a blocker; a wrong zero in the record is.
- **Row 4's window has no session open yet.** 02:01:48Z-10:45Z holds the 04:00Z integrity run (the 3 issues per symbol at 04:00-04:06Z) but not the 22:00Z open of 10-22, so the "open-window no_progress / stuck" claim stays unmeasured. `stuck_threshold_crossed = 0` across the day is good. Record the window honestly; do not wait for the open — the data-lag flag covers it and the user already accepted that re-scope.
- **`no_progress` YM 59 vs ES 14** is consistent with YM's thin overnight minutes (`data_lag_service.py:44-46`) and a delay that drifts by a minute; `stuck_threshold_crossed = 0` says nothing stalled. Not a blocker.
- **Vendor "no series" on 2 of 8 ES verify fetches** is the scraper dropping a burst at :00 (inference; the plan recorded about one in nine earlier). It matters for the follow-up's design, not for closing this plan.
- **Nothing here blocks closing the plan.** The cascade is shown correct on every completed bucket; the open defect is in a read-only monitoring job and is documented with a fix spec.

# Go / no-go for Task 6

**Go**, in this order:

1. Run the Mongo `created_at` / `updated_at` check for ES hours 03-10 and BTC 03:00 (five minutes, read-only). Run the `no_progress` minute-of-hour grep. Optionally the Friday 1d `created_at`.
2. Re-count `misaligned_bars_dropped` without the symbol filter; take the per-symbol figure from `job_history`.
3. Task 6 [ASK]: G2 (default defer) plus the row-11 choice (default: diagnosed Fail, follow-up filed, archive now).
4. Write the addendum with rows 10 and 11 as worded above, row 4 with the corrected count source and the honest window, and put the follow-up fix spec (and the re-worded metric) in Session 12 so it survives the archive.
5. Task 7 as planned. No deploy.

# What to avoid

- No vendor fetch from a second process on prod.
- No lag-based exclusion rule; it is the wrong invariant (fact 6).
- No code or deploy inside this phase unless the user widens it at the Task 6 ask.
- No waiting until 2026-10-23T02:00Z "to be sure"; the mechanism is in the code and the literal count is unreachable anyway.
- Do not rewrite the 2026-09-24 text or my 11:45 report; correct the clause in the dated addendum and say it was mis-specified.

# Assumptions

| Assumption | Confidence | What would flip it |
|---|---|---|
| The ES `1m (HH-1):49` bars for the alert hours have `created_at` at or after HH:00:02. | High (code path, facts 1 and 4) | A `created_at` before HH:00:00 on an alert hour means the divergence is not the missing minute; then compare stored 1m sums against the stored 5m bar for that bucket before filing the fix. |
| The 09:00 ok run is lag briefly under 600 s. | Medium | The same check: 1m 08:49 created before 09:00:00. If not, it was lock interleaving; the fix is unchanged. |
| The logger does not bind `symbol` from context onto `misaligned_bars_dropped`. | Medium (logging module not read) | A symbol-filtered grep that returns non-zero lines elsewhere in the day. |
| Friday's 1d bar persisted after the 21:00Z close. | Medium (inference from adapter cutoff and repair path) | `created_at` before 2026-10-16T21:00Z; then a forming-bar bug exists and joins the follow-up. |
| The user prefers archiving now over a two-day extension for a cosmetic green row. | Medium (go-live called off; focus on Exness) | The user picks "widen" at the Task 6 ask; then the fix spec above is the scope, hotfix on `master`, merge back, 24 runs from the new `StartedAt`. |

# Unresolved questions (for the user, via the Task 6 ask)

1. Row 11: file the follow-up and archive now, or widen this phase to fix, deploy and re-measure (earliest close 2026-10-24)?
2. Follow-up shape: 4-line "skip the newest matched bucket" (default), plus moving the job to :30 if the `no_progress` grep clusters at :00, or delete the verify job altogether?

Status: DONE_WITH_CONCERNS
Summary: Row 10 passes in substance (the pass clause was mis-specified; the 1w insert is the closed week's bar). Row 11 fails as worded because the verify job compares the still-filling bucket 2 s before `sync_1m` fills it — a verify-job defect, lag-independent, cascade output correct on every completed bucket; record the diagnosed Fail, file a 4-line follow-up, re-word the metric, and go to Task 6 now.
Concerns: row 4's per-symbol `misaligned_bars_dropped` zero is likely a grep artifact; confirm the diagnosis with the Mongo `created_at` check before writing the addendum.
