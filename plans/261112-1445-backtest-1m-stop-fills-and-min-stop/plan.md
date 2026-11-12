---
title: "Backtest fills on 1m bars and Triple Screen stop and target parameters"
description: "Backfill 1m gold bars through a local Mongo, make backtests replay 1m bars so stop entries, SL and TP fill in true order as in live paper, give Triple Screen higher-timeframe stop-loss and take-profit lookbacks, entry and stop offsets and a minimum stop, then run pre-registered configs and score them with the strategy assessment rubric at 2% risk."
status: done
priority: P2
effort: 3d
branch: develop
tags: [backend, backtest, experimental]
blockedBy: []
blocks: []
created: 2026-11-12
---

# Backtest fills on 1m bars and Triple Screen stop and target parameters

## For the executor

This plan is handover-ready: an executor model can run it without inventing a step.
- Run the phases in the order of the table below. Inside a phase, run the tasks in order.
- Each task has Goal, Target files, Steps, Success criteria and Verify.
- Every phase file carries its own Failure Protocol. When a Verify step fails, stopping is the intended behaviour, not a stall.
- Never print a secret value. When you need a credential, print only key names, or the host and database of a URL.
- Read every file in `docs/governance/` and the repo `CLAUDE.md` before phase 1.

## Outcome

- **1m fills:** a backtest whose entry interval is coarser than 1m, and whose symbol has a 1m bar at or before `start_date`, fills resting stops and checks SL and TP on the 1m bars inside each entry bar, in time order. Today a stop counts as stopped out whenever its fill bar's range also touches the SL. In the 2025-11..2026-11 replay, about 18 of 32 such stops were false.
- **New Triple Screen parameters:**
  - `stoploss_lookback` (the renamed `stop_lookback`) and a new `takeprofit_lookback`, both counted in bars of the next higher timeframe;
  - an entry offset and a stop-loss offset against fakeouts;
  - a minimum stop distance.
- **Measurement:** pre-registered configurations run on 2024-05-01..2026-11-10 and are scored with `docs/governance/strategy-assessment-rubric.md` at the owner's fixed 2% risk.

## Why

- **Evidence:**
  - `plans/reports/kongming-261112-1356-triple-screen-diagnosis-and-assessment-rubric.md`, sections 5.3 and 5.6;
  - `plans/reports/kongming-261112-1527-mtf-lookback-takeprofit-and-entry-offset.md`, the parameter design, the pre-registered sweep and candidate C;
  - `plans/reports/backtest-261111-1432-triple-screen-2023-2026-out-of-sample-2pct.md`.
- **Fill rule:** the stop-on-fill-bar rule (`fill_resting_stops` in `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`) moves the out-of-sample total between -11 R and +84 R.
- **Stop size:** stops as close as 0.5 USD make positions up to 87x equity at 2% risk. A minimum stop of 0.5 x ATR(4h) caps them at about 18x, and cuts undecidable fill-bar trades from 4.7% to 1.1%.

## Design decisions

- **1m fills.**
  - The paper broker acts only on the finest interval it has seen for a symbol (`_is_finest`). Live paper sees 1m bars (`bar_app_service.py:38-46`, verified by the red team).
  - The backtest replays only the entry interval today (`backtest_app_service.py`, the `self._bar_repo.stream(...)` loop).
  - So the backtest also publishes 1m bars, merged in time order, and the broker's existing rules run at 1m resolution, as in live.
  - The switch is automatic for every symbol and every backtest, with no flag. A flag would have no second real caller (`CLAUDE.md`).
  - Rejected: a lazy resolver inside the broker. It would add a second fill path that live never uses.
- **Clock rule (one formula).** For every published bar, `clock = bar start + step(bar interval) - step(finest interval in the run)`. `set_simulation_time(clock)` and `occurred_at=clock`; `bar_start` stays the bar start; `bar_end` is not set. A single-interval run therefore keeps today's timestamps exactly. Phase 2 has the publish order and the meaning of each stored time.
- **Gaps.** In a merged run, an entry bucket with no 1m bar is published once as a stand-in 1m event carrying that entry bar's OHLCV. The broker then applies today's coarse rule to that bucket. No broker change.
- **Backfill route.** Backfill 1m into the local Mongo first. Then copy to prod only the 1m bars older than prod's first 1m bar, with `mongorestore` and never `--drop`. Prod bars are never rewritten, so the rollback is one exact `deleteMany`. Rejected:
  - remote-db through `just tunnel`, which means about 1.8M serial round trips and a prod-pointed `.env`;
  - the VPS api container, which would hold about 900k bars in memory beside the trader.
- **Parameters.** The definitions in the kongming report, section 3.2, plus the owner's stop-loss offset (phase 3).
- **Offsets as two parameters.** The owner wants X on both the entry and the stop loss. They are two parameters, `entry_buffer_atr` and `stoploss_buffer_atr`, so candidate C keeps its pre-registered values (entry offset 0.1, stop-loss offset 0). The non-zero stop-loss offsets 0.1, 0.2 and 0.3 run as three pre-registered informational trials on C (owner decision 8). Those trials are the parameter's real callers.
- **Golden check.** Use stored run `01a1c980` (2023-01-01..2026-11-10, 1 991 trades). Its window starts before any 1m bar, so the run stays coarse on any database. Run `01a1c41f` cannot serve, because prod 1m bars start before its window.

## Phases

| # | Phase | Status | Depends on |
|---|---|---|---|
| 1 | [Backfill 1m gold bars through local Mongo](./phase-01-backfill-1m-gold-bars.md) | done | - |
| 2 | [Backtest replays 1m bars for fills](./phase-02-backtest-replays-1m-fills.md) | done | 1 |
| 3 | [Triple Screen stop and target parameters](./phase-03-triple-screen-stop-and-target-parameters.md) | done | 2 |
| 4 | [Re-run and rubric score](./phase-04-rerun-and-rubric-score.md) | done | 1, 2, 3 |
| 5 | [Ship](./phase-05-ship.md) | done | 4 |

Phase 1 comes first because the Exness M1 history may be a rolling window. The first bar it serves could pass 2024-05-01 soon (this is an inference; `docs/deployment.md:217` gives only a bracket).

## Acceptance criteria

- **Local coverage:** the local Mongo holds XAUUSD:EXNESS 1m bars from at or before 2024-05-01T00:00Z, with `fetched == inserted` and no `upsert_failed` log line. The audit numbers E0, E1 and the longest E0 run are recorded.
- **Prod coverage:** prod holds the 1m bars older than its first pre-existing 1m bar `C`. The count older than `C` equals the archive's document count. Prod bars from `C` on are unchanged. No `--drop` was used.
- **Baseline B0:** before phase 2's code, the local engine reproduces the 1 991 stored trades of `01a1c980` on `(side, entry_time, exit_time)`.
- **No look-ahead:** in a merged run, no stop fills on a 1m bar that starts before its signal bar closed. The simulation clock never decreases. Every trade has `exit_time >= entry_time`. Tests prove these points, together with `docs/governance/no-look-ahead-rules.md`.
- **Fill order:** a stop whose fill bucket touched the SL only before the entry is not stopped out. One whose SL was touched after the entry is. A bucket with no 1m bar fills by the coarse rule.
- **Golden G-a:** after phase 2, `01a1c980`'s config gives a trade list identical to B0. The run snapshot says `fill_interval` `15m`.
- **Golden G-b:** after phase 3, the same config with `stoploss_lookback=20` in place of `stop_lookback=80` gives a trade list identical to B0.
- **Parameters:**
  - Triple Screen has `stoploss_lookback` (default 2, at least 1), `takeprofit_lookback` (default 0), and `entry_buffer_atr`, `stoploss_buffer_atr` and `min_stop_atr` (default `0.0`, finite, at least 0).
  - `max(stoploss_lookback, takeprofit_lookback) x ratio` is at most 500.
  - `stop_lookback` is gone from the code, with no alias.
- **Replica check:** the engine's coarse run of C on 2023-01-01..2026-11-10 matches `.cache/km3/candidate_trades.csv` by the rule in phase 4. Do this before reading any profit.
- **Report:** a report scores A, B and C with the rubric at 2% risk, using the per-config segment labels of phase 4. It lists the three stop-loss-offset trials as informational, and updates the trial count to 224.
- **Quality gates:** `uv run pytest tests/ -q` (Docker running; the 4 known Windows tz failures are expected), `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet` and `uv run pyright` on the touched packages all pass.

## Constraints

- `CLAUDE.md` rules: KISS; at most two hops; repositories in core; no docstrings; delete dead code; never deprecate and keep.
- **Prod data:** never `--drop`; never overwrite a prod bar; check `df -h` before any VPS dump; live trading stays disarmed. Phase 1 checks the prod safeguards doc before and after.
- **Local target:** the repo `.env` stays the all-local file. Never copy `remote-db.env` over it and never run `just tunnel` during this plan. Phase 1 task 1.1 defines the target guard, and every phase repeats it before a write or a run.
- **Secrets:** `../pocketquant-config/` files are read behind a privacy hook. When the hook asks, stop and get the user's approval. Never write a credential into this repo.
- **Archives:** dumps live under `.cache/dumps/` (gitignored) and are deleted after use.
- **Release:** a `develop` to `master` release needs the owner's explicit yes.
- **Pre-registration:** the phase-4 runs are fixed in phase 4. Nothing else runs, and no neighbour of C is tried. The start date, kill thresholds, minimum stop and match rule do not move after a number is seen.

## Non-goals

- A monthly loss brake, other strategies, the Exness account terms.
- Changing live paper or Exness order handling.
- Spending the 2022-05..2022-12 holdout. The owner keeps it for a later strategy.

## Owner decisions (2026-11-12)

1. **Minimum stop:** a closer swing stop is widened to `min_stop_atr` x ATR(14) on the top interval, and the trade is kept. The value is 0.5, chosen by the pre-registered rule.
2. **X:** it applies to both the entry (long = level + X, short = level - X) and the stop loss (long = swing - X, short = swing + X).
3. **Default:** `stoploss_lookback` defaults to 2, Elder's two bars of the trading timeframe.
4. **Rubric G2:** in-sample t >= 3.0 is the binding test. The Deflated Sharpe Ratio is reported but does not decide. Update `docs/governance/strategy-assessment-rubric.md` to match.
5. **Holdout:** keep the 2022 holdout untouched.
6. **Paper:** open a paper subscription for C only if C survives the phase-4 engine run.
7. **Where:** backtests run locally against a local Mongo copy, several in parallel.
8. **Stop-loss offset trials (red team):** ship `stoploss_buffer_atr` and run C with 0.1, 0.2 and 0.3 as informational trials 222-224. They cannot change C's verdict, which is scored at 0.0.
9. **G2 sample for C (red team):** C's in-sample t is computed over its whole selection window, 2023-01-01..2026-11-10. C's t on the phase-4 window is reported next to it.

## Red Team Review

### Session — 2026-11-12
**Findings:** 15 (15 accepted, 0 rejected). They come from 27 raw findings by three reviewers (Assumption Destroyer, Failure Mode Analyst, Security Adversary), adjudicated with kongming counsel.
**Severity breakdown:** 2 Critical, 7 High, 6 Medium.
**Reports:** `plans/reports/red-team-261112-1724-backtest-1m-fills-plan.md` (findings and evidence) and `plans/reports/kongming-261112-1724-red-team-adjudication.md` (adjudication and fixes).

| # | Finding | Severity | Disposition | Applied To |
|---|---|---|---|---|
| 1 | Phase 1 rollback with `--drop` would drop all prod `bars` | Critical | Accept | Phase 1 (route has no overwrite, rollback = exact `deleteMany`) |
| 2 | Golden check could not run on `01a1c41f`; phase 2 needed phase 3 | Critical | Accept | Plan, phases 1-3 (`01a1c980`, B0, G-a, G-b, new order) |
| 3 | Simulation-clock rule left open | High | Accept | Plan, phase 2 (one formula, stored-time meanings, tests) |
| 4 | Backfill: per-bar round trips, swallowed errors, tautological check | High | Accept | Phase 1 (local backfill, `fetched == inserted`, log scan) |
| 5 | A 1m gap skips fills and exits | High | Accept | Phase 2 (stand-in bucket), phases 1 and 4 (E0/E1 threshold) |
| 6 | Prod-pointed `.env`, port 27017 and dumps | High | Accept | Plan constraints, phase 1 target guard, phases 2-4 |
| 7 | Exness rate overcommit; armed state unchecked | High | Accept | Phase 1 (`--rate-fraction 0.05`, safeguards check) |
| 8 | 1m switch affects every prod backtest | High | Accept (disclosure and measurement; no scoping flag) | Phases 4 and 5 |
| 9 | "Out-of-sample" is selection data for C | High | Accept (labels and fixed start; kill thresholds kept) | Phase 4 |
| 10 | Merged cursors can idle past the cursor timeout | Medium | Accept (fix: `batch_size(1000)` in `stream`) | Phase 2 |
| 11 | Subscription rename contingency unsafe | Medium | Accept (simplified: stop and ask the owner if count is not 0) | Phases 3 and 5 |
| 12 | Validation gaps; equivalence test had no baseline | Medium | Accept | Phase 3 |
| 13 | Replica exact match ignores the warm-up difference | Medium | Accept | Phase 4 |
| 14 | Wrong health route; Exness-broker subscriptions omitted | Medium | Accept | Phase 5 |
| 15 | `stoploss_buffer_atr` had no caller | Medium | Accept (owner decision 8) | Plan, phase 4 |

Also from kongming, beyond the reviewers:
- The G2 sample for C was undefined and decides C's verdict (owner decision 9).
- A run whose log contains `skipped:strategy_error` or `paper.stop_fill_failed` is void.
- Check each run's snapshot `fill_interval` before reading any number.
- Compute every rubric number from the trade list, not from the stored Sharpe or drawdown.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01-backfill-1m-gold-bars.md, phase-02-backtest-replays-1m-fills.md, phase-03-triple-screen-stop-and-target-parameters.md, phase-04-rerun-and-rubric-score.md, phase-05-ship.md.
- Decision deltas checked: 12. They are: the backfill route; the rollback; the golden run id and B0/G-a/G-b; the phase order; the clock rule; the stand-in bucket; `batch_size`; the validation bounds; the segment labels and fixed start; the replica match rule; the trial count of 224 with the three offset trials; the `/health` route and the subscription contingency.
- Reconciled stale references: 10 (one more: the B0 export gained `exit_reason` for the phase-4 class count). They are: `01a1c41f` as the golden run; "or the first full 1m day"; "only delays fills"; `/api/v1/health`; "divide its value by ratio"; "Validate each as >= 0"; "out-of-sample segment / in-sample year"; "remote-db mode"; "trial count adds none".
- Unresolved contradictions: 0.

## Unresolved questions

- Is the Exness M1 history a rolling window? Phase 1 task 1.6 shows the first served bar. If it is after 2024-05-01, phase 1 stops and asks the owner.

## Validation Log

### Session 1 — 2026-11-12
**Trigger:** `/ak-plan validate` after the red-team rewrite.
**Questions asked:** 3

#### Verification Results
- Tier: Full (5 phases). The red-team pass already verified the original claims, so this pass checked only the claims added by the rewrite.
- Claims checked: 21
- Verified: 18 | Failed: 3 | Unverified: 1
- Failures:
  1. Phase 1 task 1.8 named `.cache/bt.py` as the runner template. It calls the HTTP API (`.cache/bt.py:18`). The direct-service runner is `.cache/ts_direct.py`.
  2. Phase 5 curled `localhost:41921/health` on the VPS host. That port listens inside the api container only (`deploy/vps/11-verify.sh:16-17,101`).
  3. Phase 1 said the `backtest_runs` `_id` is a UUID. It is a string (`backtest_repository.py:21`).
- Unverified: where the `EXNESS_*` keys live in `../pocketquant-config/`. A privacy hook blocks the read; phase 1 task 1.4 asks the user.

#### Questions & Answers
1. **[Assumptions]** Fix the 3 claims that do not match the code (runner template `.cache/ts_direct.py`, health check inside the api container, `_id` as a string)?
   - Options: Fix all 3 (Recommended) | Leave as is
   - **Answer:** Fix all 3
   - **Rationale:** an executor following the wrong instruction would fail a Verify step.
2. **[Risks]** Approve the 1m data-quality stop rule: stop when `(E0 + E1) / buckets > 1%` or the longest E0 run is over 96 buckets?
   - Options: Approve 1% / 96 (Recommended) | Looser 3% / 288 | Stricter 0.5% / 32
   - **Answer:** Approve 1% / 96
   - **Rationale:** it is pre-registered, so it cannot move after the audit numbers are seen.
3. **[Risks]** Run the 1-year 1m backtest on prod after the release to measure trader impact?
   - Options: Run outside trading hours (Recommended) | Run right after the release | Skip
   - **Answer:** Run right after the release
   - **Rationale:** it measures the real cost on the VPS early, and accepts the risk of slowing the trader during market hours.

#### Confirmed Decisions
- Runner template: `.cache/ts_direct.py`.
- Health check: `deploy/vps/11-verify.sh`, or `docker exec <api container> curl` for the raw JSON. Lease limit 30 s (`LEASE_TTL_S`, `app/roles.py:39`).
- Gap stop rule: 1% / 96, owner-confirmed.
- Prod load check: right after the release, window 2025-11-09..2026-11-08. Stop the check if `lease_renewed_age_s` reaches 30 s.

#### Impact on Phases
- Phase 1: task 1.8 runner template and `_id` type; task 1.7 notes the owner-confirmed thresholds.
- Phase 4: the runner reference names `.cache/ts_direct.py`.
- Phase 5: the health check runs inside the api container; task 5.4 step 5 runs right after the release with a 30 s lease stop.

### Whole-Plan Consistency Sweep
- Files reread: plan.md and phase-01 to phase-05.
- Decision deltas checked: 4.
- Reconciled stale references: 5 (`bt.py` in phases 1 and 4, the host-side curl in two places in phase 5, the UUID `_id`).
- Unresolved contradictions: 0.
