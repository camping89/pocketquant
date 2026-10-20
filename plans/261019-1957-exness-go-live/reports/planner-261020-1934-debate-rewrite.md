# Planner: go-live plan rewritten from the debate synthesis

Date 2026-10-20 (Asia/Bangkok). Inputs: `kongming-261020-1924-debate-synthesis.md` (structure and §5), the evidence packet, candidates 1-3, the tunnel research, and the user decisions of 2026-10-20 19:35. Plan files only; no code, no commit.

## Result
- `plan.md` is a short index: conventions (entry gate, `NOT_YET`, [ASK]/[USER], no restart while live state matters), ops recipe, phases, dependencies, AC1-AC11, gates, deep-backfill note, rollback ladder (with 1b and the flat-account rule), out-of-scope flags and unresolved questions.
- Twelve phase files, in run order: 01 admin auth, 02 broker per subscription, 03 access-point re-resolve, 04 integrity unexpected bars, 05 safeguards and sizing, 06 SPA, 07 tunnel service, 08 deploy A, 09 deploy B, 10 arm (deploy C), 11 take one strategy live, 12 observation and go-live. Renames used `git mv` where the file was tracked; `phase-04-integrity-unexpected-bars.md` and `phase-10-arm-live-all-paper.md` are new.
- Each phase has an entry gate, numbered tasks with Goal / Target files and symbols / Steps / Success criteria / Verify, the gate legend, `NOT_YET` exits for waits, and the literal Failure Protocol block. Prod phases inline the SSH and admin-call patterns and a heredoc-indentation rule.
- `ak plan validate` reports the directory valid (exit 0).

## How the user decisions changed the synthesis
- No E2 gate anywhere. Phase 08 states the next E2 row; phases 10-12 state the latest row; deleting a paper subscription in Phase 11 makes E2's `running 2` read 1 (stated in the [ASK]).
- No Saturday window: deploys A and B run when code is done; each `master` push is an [ASK].
- Phase 10 arms only: flag on, pause right after, every subscription paper, `exness.broker_connected` count 0. The stop-distance and margin checks moved to Phase 11 (per candidate, at choice time); Phase 08 still records the stop distances early.
- Phase 11 is one strategy per run, driven by a state record in `reports/round-trip.md`: choose [ASK], pause and baseline, delete paper [ASK], create `exness` [ASK], zero-money proof (`orders` with `status: "rejected"` for the new subscription and no `order_quantity_below_broker_minimum`/`zero_position_size` line; `NOT_YET` until it appears), Resume [ASK], first natural trade (`NOT_YET` until a `trades` row exists), per-trade checks, `[USER] sl seen`, asymmetric AC6 with a balance-deal guard, D4 [ASK]. A restart guard re-pauses on every run.
- Phase 12 counts five clean rows from the latest `resumed_at`; the first row on or after 2026-11-02 adds an XAUUSD reopen check. DST is recorded, not a go-live gate.
- The deferred SSE check is record-only in Phase 10 (it was an arm gate in the synthesis); it gates nothing because arming is wanted as soon as possible.

## Deep backfill while armed (checked)
- Verified: `scripts/backfill/provider_bars.py:76-78` exits 3 while `EXNESS_LIVE_TRADING` is true. The flag is read only there, in `BrokerFactory` and in `ExnessClient.call`.
- Not blocked: in-app sync and `POST /market-data/integrity/repair` (they resync through `SyncService`, `integrity_jobs.py:116-130`). Paper subscriptions preload no history.
- Blocked: history beyond the 5000-bar request cap (new symbols, longer backtests, old holes). Phase 10 Task 10.3 lists the stored bar counts and asks whether to backfill before arming. Afterwards, a backfill needs the flag off, which needs a flat account and no `exness` subscription.

## Facts found while rewriting
- The adapter's `below_min_lot` log carries no subscription id; the plan uses the strategy service's `order_quantity_below_broker_minimum strategy_id=<id>` line and the durable `orders` rows instead. The pause rejection log gains `subscription_id` and `symbol` in Phase 05.
- Positions use `is_closed`, not `closed_at: null`; the plan uses `is_closed`.
- hitnrun2 citations: `max_loss_pct` at `:38`, the SL clamp at `:103` (the synthesis said `:37,:102`).
- On 2026-10-20 `pocketquant-config` showed `M vps/default/.env` with an empty diff [I: line endings or file mode]; Phase 08 shows `git status --short` in its config [ASK].
- The existing adapter test already pins "EXNESS_DAILY_LOSS_CAP not set" (`test_exness_broker_adapter.py:205`); Phase 05 keeps it and adds the `max_lots=None` case.

## Unresolved questions
- Deep backfill before arming: does the user want any history loaded first? Phase 10 asks with the bar counts; no answer is needed before cooking.
- The `camping89` recipe for `gh workflow run` (and whether `gh run` reads need it) is untested; Phase 08 probes it, and Phase 10 falls back to a UI dispatch by the user.
- The runner's handling of a `Status: BLOCKED` worker is inferred; the first `NOT_YET` exit (likely Phase 11's proof wait) shows it.
- The SPA local check needs the local `.env` from `pocketquant-config/local/all-local.env`; no `.env` exists in the worktree today, so Phase 06 creates and removes it.

Status: DONE
Summary: The plan is rewritten in place as twelve handover-ready phases with entry gates, `NOT_YET` exits and the Failure Protocol in every file, following the synthesis as adjusted by the 19:35 user decisions. `ak plan validate` passes.
Concerns: Phase 11 is long (about 300 lines) because it holds the whole one-strategy state machine; the dispatch auth and the BLOCKED-to-stop mapping are untested.
