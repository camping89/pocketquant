---
title: Closing the open items of the asset-class index-futures plan
date: 2026-10-22
author: kongming (advisory only; no code or prod touched)
plan: plans/archive/260921-1436-asset-class-index-futures/
---

# TL;DR

Four of the five "open" items are either already resolved by work that landed after the completion report was written, or are measurable today from data that survives deploys. No new cascade code is needed: `cascade.partial_aggregate` was removed outright on 2026-09-24 by user decision (`a9233245`), and the stored `session_date` problem disappeared when prod's futures data was wiped on 2026-10-12 and re-seeded on 2026-10-13 under the `:TRADINGVIEW` names, after the stamping fix was already on develop. Recommendation: run one read-only measurement-and-reconcile phase (new `phase-08` in the existing plan dir), record a drop decision for the week-long metric 4 and for G2 (#13), then archive the plan. A `/ak:fix` is offered only for a residual that the measurement may surface, and I recommend against it unless the user wants a clean metric for its own sake.

# Verified facts (scouted; file:line)

Each line below was read from the repo on develop at `1bf4b71e`, not recalled from the report.

1. **`cascade.partial_aggregate` no longer exists.** `grep partial_aggregate src` returns nothing. Commit `a9233245` (2026-09-24 16:56 +07) deleted the emit block; the current `cascade_for_symbol` loop only skips empty buckets (`src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:207-213`). The plan records it as a user decision: `plans/260921-1436-asset-class-index-futures/plan.md:1394-1398` ("removed outright... Metric 4's `partial_aggregate` clause therefore no longer applies; the other four events in that metric still do"). `completion-report.md` was written earlier the same day and was never updated, which is why the caller's brief still describes it as failing. The remaining test is `test_a_closed_bucket_short_of_bars_is_aggregated_silently` (`tests/app_test/market_data/test_cascade_aggregator.py:464`).

2. **The old futures data is gone; the symbols were re-created.** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/symbol-cascade-delete-261012.md:3`: prod cleanup of `ES1!:CME_MINI`, `NQ1!:CME_MINI`, `YM1!:CBOT_MINI` done and verified, "no document or Redis key references them any more". `.../reports/integrate-develop-step2-suffix-routing.md:71-75`: before the suffix-routing deploy prod held only the three Binance symbols; after deploy (CI run 38365651685) the seeder created `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW`, `YM1!:TRADINGVIEW`, and `sync_1m` started fetching for them at 08:01 UTC on 2026-10-13. So the "4999 unstamped 1d ES bars" from metric 5 do not exist in prod any more.

3. **Every provider-bar write path stamps `session_date` for 1d and 1w.** `sync_internals/calendar_stamp.py:13-25` (`_SESSION_KEYED = {DAY_1, WEEK_1}`), called from `sync_service.py:170` (used by `sync_1m` and the nightly `sync_backfill`, which runs all `SYNC_INTERVALS` including `DAY_1`/`WEEK_1` at n=5000, `sync_jobs.py:72-79,764`) and from `tracked_symbols_backfill.py:163,197`. Commit `f101f4ee` (2026-09-24) predates the 2026-10-13 re-seed, so every futures 1d/1w row now in prod was written through a stamping path. Still unverified on prod: a count. Nothing reads `session_date` yet (only the index at `bar_repository.py:305-306` and serialization in `bar/entities.py:82,105-107`).

4. **Futures are still tracked and documented.** `scripts/seed_index_futures.py:45-55` seeds the three `:TRADINGVIEW` names; `README.md:3,41-47` and `docs/system-architecture.md:111,121,145` document TradingView index futures and the data-lag flag; `TRADINGVIEW_EXCHANGE_BY_CODE` maps codes to `CME_MINI`/`CBOT_MINI` (`tradingview_mappers.py`). No commit since 2026-09-24 removed them. (Whether the three tracked documents still exist in prod today is an inference from the 10-13 report plus the absence of any later removal record; the measurement phase confirms it in one query.)

5. **Weekend quiet (#10) is measurable from Mongo, not logs.** `sync_1m` writes a per-symbol detail `status="skipped", error="closed"` into `job_history` for a shut market (`sync_jobs.py` around lines 200-215, `record_detail` at `job_history_repository.py:106-135`), and `job_history` has a 30-day TTL (`job_history_repository.py:28-29`). The weekend of 2026-10-17/18 (first full weekend after the re-seed) is therefore still queryable until mid-November, and a deploy does not clear it.

6. **`divergent_fraction` (#11) exists only in logs.** `sync_verify_cascade` records only `status` in `job_history` (`sync_jobs.py:589-680`); the per-symbol result is `sync_verify_cascade.ok ... divergence_count=` at INFO. The `app` container's log driver is `json-file`, `max-size 10m`, `max-file 3` (`deploy/compose.prod.yml:87-91`). The last container restart was the disarm redeploy: `app StartedAt 2026-10-22T02:01:48Z` (`plans/261019-1957-exness-go-live/reports/ship-log.md:13`). Hourly runs fire at `:00` (`sync_jobs.py:859-862`), so 24 consecutive runs exist from 2026-10-23T02:00Z onward, provided no deploy happens before then.

7. **The remaining metric-4 events and their current rules.** `market_data.sync.no_progress` (WARNING) and `stuck_threshold_crossed` (ERROR at streak == 3 when the newest bar is older than 3 x cadence) in `sync_internals/anomaly_log.py:18,66-76`; silent only while the calendar says closed (`:40-47`). `integrity.issues_found` fires from the 04:00 UTC daily job (`sync_jobs.py:367-385`, schedule `:872-876`) whenever `check_integrity` reports missing bars; the grid's upper bound is `calendar.bar_start(now, interval)` with no allowance for feed lag (`integrity_jobs.py:66-108`). `plan.md:1443-1446` already records that the 04:00 run falls inside a Globex session, so the delayed feed's last ~12 minutes show as missing on every run ("Ending the integrity grid at `now - lag` would remove that; not done").

8. **Sizing (#13) is unchanged for paper futures.** `position_calculator_domain_service.py:45-55`: `cap = balance * max_exposure * leverage / price`, divided by the multiplier, floored to `lot_step`, returns 0 below one lot. `RiskConfig.leverage` now exists (`core/domain/risk/value_objects.py:16`, added in `96c4675b`) but only Exness subscriptions receive a non-default `RiskConfig` (`strategy_reconcile_app_service.py:179-184`: `self._exness_risk if sub.broker == "exness" ... else RiskConfig()`). `paper_initial_balance` is a single global of 10,000 (`core/config.py:139`). At ES ~7800 and 10,000 balance the cap is 0.0026 contracts, so sizing to zero is still the arithmetic.

9. **Project focus.** `plans/261019-1957-exness-go-live/plan.md:68-69,108`: go-live called off 2026-10-22 at Task 11.5 "because no strategy is profitable yet"; live trading disarmed (`EXNESS_LIVE_TRADING=false`, config `efb6c90`). Deploy path: a `develop` push runs tests only; only `master` deploys (`docs/deployment.md:7-15`).

# Reframed problem

The question is not "how do we fix five metrics" but "what is the cheapest honest way to close a plan whose gates were written for a real-time feed, now that the data feed is a delayed free scraper, the data was reset, and the project's attention moved to finding a profitable Exness strategy". Requirements: no prod risk, no code that lacks a second caller (CLAUDE.md), a truthful record in the plan, and the plan archived if nothing load-bearing stays open. Non-goal: making metric 4 pass as literally worded.

# Per-item recommendation

| # | Item | Recommendation | Why |
|---|------|----------------|-----|
| 4 | Zero anomaly events for ES over a full week incl. 11-26 early close | **Drop the week-long measurement; record a one-day measurement and re-scope.** No new cascade code. | The `partial_aggregate` clause is already retired by user decision (fact 1). The two residual sources are structural on a delayed free feed: the daily `integrity.issues_found` at 04:00 UTC (fact 7, recorded in `plan.md:1443`) and, by inference, a `no_progress` run-up plus one `stuck_threshold_crossed` at each 22:00 UTC open while the 10-12 minute delay means nothing new arrives. The operator already chose the data-lag flag (Session 11) as the "is the feed behind" signal. A week of watching cannot change either outcome; only code with a single caller could, which CLAUDE.md tells us to stop and ask about. |
| 5 | `session_date` on stored futures 1d bars | **Close after one read-only count; repair only if the count is non-zero.** | Facts 2-3: the unstamped rows were deleted on 2026-10-12 and every write path since stamps. Expected result: 0 rows without `session_date` on `ES1!/NQ1!/YM1!:TRADINGVIEW` at 1d and 1w. If any exist, the documented repair (`bars` dump, then `POST /tracked-symbols/{symbol}/backfill?interval=1d&mode=direct&n=5000` per symbol, same for 1w) stays valid, behind an [ASK]. Nothing reads the field, so a non-zero count is a correctness debt, not an outage. |
| 10 | Weekend quiet in `job_history` | **Close by measuring now (read-only Mongo).** | Fact 5: the 2026-10-17/18 weekend is in `job_history` with per-symbol `skipped/closed` details and survives deploys. Pass rule: between Friday 2026-10-16 21:00Z + 1 min grace and Sunday 2026-10-18 22:00Z, every `sync_1m` detail for a `:TRADINGVIEW` symbol is `skipped/closed`, and no `sync_backfill` detail for them is `completed` with `bars_inserted > 0`. |
| 11 | `divergent_fraction = 0.0` for 24 consecutive runs | **Close by measuring from the current log window on or after 2026-10-23T03:05Z (10:05 Bangkok), with no deploy before then.** | Fact 6. If a deploy intervenes, the window restarts; the rule "measure 24 h after the last restart" is the whole procedure. The 2026-09-24 addendum's non-ES newest-bucket divergences are not part of the metric (ES only). |
| 13 | G2: paper ES full session in USD | **Drop for now; record the fork and a default.** User decision stays with the user. | With no profitable strategy and the venue focus on Exness, a paper ES round trip proves arithmetic that tests already pin (`completion-report.md:172-179`). If the user later wants it, the smallest path is to pass a configured `leverage` into futures paper `RiskConfig` through the field that now exists (second caller: Exness), e.g. leverage 20 at a 10,000 balance caps notional at 200,000 — still under one ES contract (390,000). So in practice "fund futures paper accounts more" is the only option that reaches one contract without new code: `PAPER_INITIAL_BALANCE` >= ~400,000 at 10 percent exposure, or ~40,000 with leverage 10. Both are config/decision, not code. |

**Archive:** yes, after the measurement phase lands with the decisions recorded. Convention is `git mv` into `plans/archive/` as done in `1bf4b71e`. Set `plan.md` front-matter `status: completed` and add the deferred G2 note in the completion report's addendum, not in evergreen docs.

# What to do (order)

1. **Now (any time):** run Prompt 1 up to and including the weekend-quiet and `session_date` checks, which do not depend on the log window. If the session starts before 2026-10-23T03:05Z, the phase records the `divergent_fraction` and metric-4 counts as "pending window" and stops before the archive step; re-run `/ak:cook` on the same phase file after the window.
2. **2026-10-23 after 10:05 Bangkok, no deploy in between:** complete Prompt 1 (24 verify runs, one-day anomaly count for ES including the 22:00Z open of 10-22 and the 04:00Z integrity run of 10-23), write the completion-report addendum, flip plan status, archive, commit, push develop.
3. **Only if the user wants the residual ERROR/WARNING lines gone:** Prompt 2 (`/ak:fix --advice`). Decide after reading the measured counts; default is not to run it.

# What to avoid

- Do not write a "delay-aware closed-bucket rule" in the cascade. The cascade no longer reports shortfalls at all (fact 1); there is nothing left to make delay-aware there.
- Do not re-backfill 1d/1w futures before counting. The rows the report wanted repaired were deleted on 2026-10-12. A blind backfill at n=5000 is 6 scraper fetches that can fail one in nine (`plan.md:1173-1178`) for no gain.
- Do not deploy between now and the 24-run measurement; a deploy recreates the `app` container and clears its log (fact 6).
- Do not keep metric 4's week-long watch alive to 2026-11-30 "just in case". It cannot pass as worded on this feed, and leaving it open is what made this plan look unfinished for a month.
- Do not raise `paper_initial_balance` globally as a side effect of #13 without saying so: it changes every crypto paper account too.

# Alternatives and trade-offs

- **Make metric 4 literally pass (two small code changes).** (a) Bound the integrity grid by the symbol's newest stored 1m bar instead of `now` (`integrity_jobs.py:98-100`), about five lines plus a test; cost: a stalled feed's frontier gap is then reported only by `data_lag_check`, not by integrity. (b) Keep `emit_no_progress` silent for the first N minutes after `session_open` on a delayed feed; cost: couples the anomaly log to plan capabilities, one caller. Both add code they do not replace, so CLAUDE.md says stop and ask first. Prompt 2 frames (a) as the candidate because it is self-contained and testable; (b) needs the measurement to prove the open-window ERROR first (it is my inference, not an observation).
- **Re-run the whole 18-metric sweep.** Not worth it: 13 metrics passed on code that has since been refactored but whose tests still run in CI; re-measuring them adds nothing the suite does not.
- **Close the plan without measuring.** Cheaper, but #10 and #11 cost one query and one grep each, and they are the only two futures claims nobody has ever confirmed on real data. Measure them.

# Work checklist

- [ ] Prompt 1: add `phase-08-close-open-metrics.md` to the plan dir, run it (read-only prod reads; [ASK] before any repair).
- [ ] Record results in `completion-report.md` as a dated addendum; update the summary table rows 4, 5, 10, 11, 13.
- [ ] `plan.md`: status `completed`, a Session 12 entry with the decisions (metric 4 re-scoped, G2 deferred/dropped).
- [ ] `git mv plans/260921-1436-asset-class-index-futures plans/archive/` and fix any link in `plans/reports/*` that points at the old path.
- [ ] Commit, push develop through the `camping89` token URL (tests only).
- [ ] Optional Prompt 2 after reading the measured counts.

# Success metrics

- `completion-report.md` has no row that says "open" with a date in the past.
- #10 and #11 each cite one command and one number from prod.
- `session_date` count: 0 unstamped 1d/1w futures rows, or a backup archive path plus a post-repair count of 0.
- The plan directory sits under `plans/archive/` and `plans/` lists only the Exness plans as in-progress.
- No prod deploy was triggered by closing this plan.

# Assumptions (made instead of asking)

| Assumption | Confidence | What would flip it |
|---|---|---|
| The three `:TRADINGVIEW` tracked symbols still exist in prod and sync. | High (10-13 report; no removal since) | The first query in Prompt 1 returns fewer than three. Then #10/#11 are moot and the plan is archived with "futures no longer tracked". |
| No deploy happens between 2026-10-22T02:01:48Z and 2026-10-23T03:05Z. | Medium | Any `master` push or config dispatch; the 24-run window restarts from the new `StartedAt`. |
| The app's 30 MB log cap holds 24 h of INFO logs for nine tracked symbols. | Medium (inference from per-minute line counts, not measured) | `docker logs --since` shows fewer than 24 `sync_verify_cascade.ok` lines for ES while the container uptime exceeds 24 h. Then count what exists, and note the cap. |
| `stuck_threshold_crossed` fires for each futures symbol at each 22:00Z open on the delayed feed. | Low-medium (inference from `anomaly_log.py:66-76` and the 10-12 min lag; Session 7 predicted it, nobody measured it) | The 10-22 22:00Z open is inside the current log window; Prompt 1 counts it. |
| No `:TRADINGVIEW` paper subscription exists in prod, so #13 blocks nothing today. | Medium | `subscriptions` holds one; then G2's zero-size behaviour is live noise (`zero_position_size` per signal) and #13 moves from "drop" to "decide". |
| The user accepts dropping the 2026-11-30 week-long watch. | Medium | If not, Prompt 2 is the only route to a passing metric, and it needs the "more code than it replaces" approval up front. |

# Prompts (verbatim, copy-paste into a fresh Claude Code session)

## Prompt 1 — measure, reconcile, archive (`/ak:cook`)

```text
/ak:cook Close the open items of plans/260921-1436-asset-class-index-futures/ by adding and executing a new phase file in that plan dir. Advisory source: plans/reports/kongming-261022-1145-asset-class-open-items.md (read it first; its "Verified facts" section lists the file:line evidence).

Work context: D:/w/_me/algotrading/pocketquant, branch develop, timezone Asia/Bangkok, today 2026-10-22. English only. Read CLAUDE.md. Creds live in ../pocketquant-config (never print a token, password or URL with a password). Prod reads are read-only; the ONLY prod write allowed is the session_date repair in step 3, and only after its [ASK].

Step 0 — add the phase file. Create plans/260921-1436-asset-class-index-futures/phase-08-close-open-metrics.md with: context (the five open items and why each is now closable; cite the kongming report), the tasks below as numbered tasks with Verify commands, the [ASK] gate, risk (one prod data repair, otherwise none), rollback (restore the bars dump). Add the row "8 | Close open metrics and archive | phase-08-close-open-metrics.md | 0.5d | 7" to the phase table in plan.md. Then execute the phase.

Ops recipe (same as the Exness go-live plan): SSH key copy: mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key; HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" '<cmd>'. Mongo probes run inside the app container as `docker exec -i pocketquant-app python - <<'EOF' ... EOF` using `from pocketquant.core.config import Settings` for mongodb_url and mongodb_database (collections: bars, job_history, tracked_symbols, subscriptions); print counts only, never the connection string. Delete .cache/ssh/vps_key at the end and before any early exit. The shell keeps no variables between commands; set HOST in every command.

Task 1 — tracked set (read-only). Count tracked_symbols and list their symbol fields; list subscriptions with symbol, broker, status. Expected: ES1!:TRADINGVIEW, NQ1!:TRADINGVIEW, YM1!:TRADINGVIEW present. If fewer than three futures are tracked, stop the measurements, record that futures are no longer tracked, and go to Task 6 with every item marked "moot".

Task 2 — item 10, weekend quiet (read-only). Query job_history for job_id="sync_1m" with started_at in [2026-10-16T21:01:00Z, 2026-10-18T22:00:00Z]; unwind details; for symbols matching ":TRADINGVIEW" group by (status, error) and count. Pass: every group is status="skipped", error="closed"; zero details with status="completed". Also query job_id="sync_backfill" runs started 2026-10-17 and 2026-10-18 at 03:00Z: no :TRADINGVIEW detail with bars_inserted > 0. Record the counts and the exact window.

Task 3 — item 5, session_date (read-only first). For each of the three futures and each interval in {"1d","1w"}: count bars docs total, and count with session_date missing or null. Expected 0 unstamped (prod data was wiped 2026-10-12 and re-seeded 2026-10-13 after commit f101f4ee). If every unstamped count is 0: item 5 is closed, no repair. If any is non-zero: [ASK] "Recommended: yes — repair N unstamped rows. Facts: <counts>. Plan: mongodump --archive of bars filtered to the three symbols and intervals 1d,1w to /opt/pocketquant/backups/pre-session-date-repair-<UTC stamp>.archive, then for each symbol run inside the container: curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" "http://localhost:41921/api/v1/market-data/tracked-symbols/<SYMBOL url-encoded, ':' as %3A>/backfill?interval=1d&mode=direct&n=5000" and the same with interval=1w, 20 s apart (the scraper drops bursts). Then recount." Only an explicit yes runs the repair. Record backup path and before/after counts. Note: upsert_bar is an upsert; confirm from src/pocketquant/core/infra/persistence/repositories/bar_repository.py that a direct backfill overwrites the stored row's session_date before relying on it; if it is insert-only, stop and report instead of repairing.

Task 4 — item 11, 24 consecutive divergent_fraction = 0.0 (read-only, log-based). The app container last started 2026-10-22T02:01:48Z. Run: ssh ... 'docker logs pocketquant-app --since 2026-10-22T02:01:48Z 2>&1 | grep "sync_verify_cascade.ok" | grep "ES1!:TRADINGVIEW"' and count lines and divergence_count values; also grep "cascade.divergence_alert" for ES. Pass: >= 24 consecutive lines with divergence_count=0 and no alert line for ES. If fewer than 24 lines exist because less than 24 h have passed, record "pending; measure after 2026-10-23T03:05Z (10:05 Bangkok); do not deploy before then", stop before Task 6, and tell the user to re-run this prompt then. If the container StartedAt (docker inspect) is later than 2026-10-22T02:01:48Z, a deploy happened: use the new StartedAt and the same rule.

Task 5 — item 4, re-scope with a one-day count (read-only, log-based). Over the same log window count, for ES1!:TRADINGVIEW only, the events: market_data.sync.misaligned_bars_dropped, integrity.issues_found (the 04:00Z run of 2026-10-23 is inside the window once it passes), market_data.sync.no_progress, market_data.sync.stuck_threshold_crossed. Also count the same for NQ and YM for context. Record per event: count, first and last timestamp, and whether it clusters at 22:00Z (session open) or 04:00Z (integrity). Then record this decision in plan.md Session 12 and completion-report.md: the partial_aggregate clause was retired by user decision on 2026-09-24 (plan.md Session 11); the remaining events that fire are structural on the delayed free feed (integrity grid bounded by now, no_progress during the open window) and are covered operationally by the data-lag flag; the 2026-11-30 full-week watch is dropped. Do not change any code in this phase. If the user wants those lines gone, the follow-up is the /ak:fix prompt in the kongming report.

Task 6 — item 13 and records. In completion-report.md add a dated addendum (do not rewrite the 2026-09-24 text) updating rows 4, 5, 10, 11, 13 with the measured results; row 13: G2 deferred by user decision — no futures strategy is pursued while no strategy is profitable; if revisited, the no-code options are PAPER_INITIAL_BALANCE >= ~400,000 at the 10 percent cap, or a smaller balance with RiskConfig.leverage routed to futures paper subscriptions (the field exists; only Exness subscriptions use it today, src/pocketquant/engine/live/strategy_reconcile_app_service.py:179-184). Before writing row 13, [ASK] "Recommended: defer G2. Alternatives: fund paper futures to >= 400k, or route a leverage into futures paper RiskConfig (small code, one new caller)." In plan.md set front-matter status: completed and add Session 12 with the decisions and the command outputs' numbers.

Task 7 — archive. git mv plans/260921-1436-asset-class-index-futures plans/archive/260921-1436-asset-class-index-futures; grep -rn "260921-1436-asset-class-index-futures" plans docs README.md CLAUDE.md --include=*.md and fix links that would break (keep report filenames unchanged). Run uv run ruff check src tests scripts (no code changed, so it must stay green) and ak plan validate if available. Commit as docs(plans): close and archive the asset-class index-futures plan. Push: git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin. Every gh call uses GH_TOKEN=$(gh auth token --user camping89). A develop push runs tests only and does not deploy.

Acceptance: every item in the completion-report summary table is Pass, Closed, Dropped or Deferred with a date and a number or decision; zero code files changed (git diff --stat on src web tests scripts is empty); the plan dir is under plans/archive; develop is pushed; .cache/ssh/vps_key is deleted. End with Status: DONE | DONE_WITH_CONCERNS | BLOCKED, a two-line summary, and the list of numbers measured.
```

## Prompt 2 — optional residual fix (`/ak:fix --advice`), only after Prompt 1's counts are known

```text
/ak:fix --advice The daily sync_integrity run reports the delayed TradingView feed's last ~12 minutes as missing 1m bars for ES1!/NQ1!/YM1!:TRADINGVIEW, so integrity.issues_found WARNs once per futures symbol per day even though the next sync_1m cycle fills those minutes. Evidence: plans/archive/260921-1436-asset-class-index-futures/plan.md Session 11 "Still open" (the 04:00 UTC run falls inside a Globex session); measured counts in plans/archive/260921-1436-asset-class-index-futures/completion-report.md addendum of <DATE> (paste the integrity.issues_found lines for ES here before running); kongming report plans/reports/kongming-261022-1145-asset-class-open-items.md.

Work context: D:/w/_me/algotrading/pocketquant, branch develop, English only, read CLAUDE.md first. Code touched: src/pocketquant/engine/market_data/app_services/integrity_jobs.py (check_integrity, the `in_progress` bound at the "The UTC cutoff above is not the calendar's" comment) and its tests under tests/app_test/ (test_integrity_calendar.py and the integrity tests that pin the in-progress exclusion from commit c92c0777). No prod access needed; do not SSH; do not deploy.

Cause to prove before editing: check_integrity bounds the expected grid by calendar.bar_start(now, interval); the store's 1m frontier for a delayed feed is ~10-12 minutes behind now, so instants between the frontier and now count as missing. Write a failing test first: a CME-calendar symbol whose newest stored 1m bar is 12 minutes old, during a session, must report missing_count 0 for 1m when every minute up to that frontier is stored.

Candidate fix (smallest; confirm against the test, do not assume): bound expected instants by the symbol's newest stored 1m bar as well as by in_progress, for every interval (a 5m or 15m bucket whose start is after the 1m frontier cannot exist yet). One extra repository read per symbol (reuse bar_repo.find_latest or the equivalent that already exists in bar_repository.py; do not add a new repository method unless none exists). Keep the crypto behaviour identical when the frontier is current (the frontier bound equals in_progress - 1 minute). Trade-off to state in the commit body: a stalled feed's frontier gap is reported by data_lag_check (stuck), no longer by integrity.

CLAUDE.md gate: this adds code it does not replace. Before editing, show the user the diff size estimate and [ASK] "Recommended: yes — about 5 lines plus one test; the alternative is to accept one WARNING per futures symbol per day." Only an explicit yes proceeds.

Do not touch cascade_aggregator.py (the partial_aggregate event was removed on purpose in a9233245) and do not change anomaly_log.py thresholds in this fix; if the measured counts show stuck_threshold_crossed at each 22:00Z open, report it as a separate finding with the numbers and stop.

Verify: uv run pytest tests/app_test -q -k integrity, then uv run pytest tests/ -q (expected local red on Windows is exactly 4 failed, 4 errors in test_utc_runtime_guard.py and test_cron_trigger_timezone.py; Docker Desktop must be running), uv run ruff check src tests scripts, uv run pyright src, uv run lint-imports, and the code-metric ratchet (uv run python scripts/code_metrics.py or the justfile recipe). Update docs/system-architecture.md's sync_integrity row in one sentence. Commit as fix(market-data): bound the integrity grid by the stored 1m frontier. Push develop with git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin (tests only; no deploy). A deploy to master is a separate [ASK] and is not part of this fix. End with Status: DONE | DONE_WITH_CONCERNS | BLOCKED and the cause, diff, and verification lines.
```

# Unresolved questions (for the user, not blockers)

1. Do you want the daily `integrity.issues_found` and the (inferred) open-window `stuck_threshold_crossed` lines gone, or is the data-lag badge enough? Default: enough; skip Prompt 2.
2. G2 (#13): defer, fund paper futures to >= 400k, or route leverage into futures paper sizing? Default: defer.

Status: DONE_WITH_CONCERNS
Summary: Items 4 and 5 are already resolved by `a9233245` and the 2026-10-12/13 data reset; items 10 and 11 are measurable today without code; item 13 is a decision with a recommended default of defer. One phase file in the existing plan dir, then archive.
Concerns: the 24-run window needs no deploy until 2026-10-23T03:05Z; the open-window `stuck_threshold_crossed` claim is inference until Prompt 1 counts it.
