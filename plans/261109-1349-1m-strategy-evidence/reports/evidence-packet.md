# Evidence packet: 1m strategy-evidence plan

This packet is the fixed input for every planning candidate. Do not reopen the decisions in it.

## Task

Write the full implementation plan for the confirmed scope below, as `plan.md` plus `phase-NN-<name>.md` files for the plan directory `plans/261109-1349-1m-strategy-evidence/`. The plan is written under the `--advice` handover contract (section "Handover contract" below): a weaker executor model (Sonnet-class) will run it end to end.

## Sources (read them; cite paths in the plan)

- Accepted advice: `plans/reports/advise-261109-1309-next-plan.md` (verdict, do/don't, checklist, success metrics, handoff brief, unverified items).
- Interview record: `plans/reports/advise-261109-1309-next-plan-state.md` (scout findings, Q1-Q6 owner answers).
- Project rules: `CLAUDE.md`, every file in `docs/governance/` (no-look-ahead rules, documentation rules), `docs/code-standards.md`, `docs/deployment.md`, `README.md`.
- Format exemplar (same owner, same handover contract, already executed successfully): `plans/261101-0843-stf-to-mtf-foundation/plan.md`, `phase-14-triple-screen.md`, `phase-15-release-d2.md`, `phase-16-backtests-and-paper-start.md`, `phase-17-observe-compare-delete.md`. Phase 16 holds the backtest run recipe, the PRODPY recipe, the coverage check (Task 16.1), the run-table format and the 1800 s cost ask.
- Deleted hitnrun2 code: `git show f3bb9e64^:src/pocketquant/core/domain/strategy/services/hitnrun2_strategy_service.py` (and its old tests at `f3bb9e64^`; find them with `git show --stat f3bb9e64`).
- Current strategy contract and its only consumer: `src/pocketquant/core/domain/strategy/services/__init__.py` (`check_strategy_inputs`, `STRATEGY_REGISTRY`), `src/pocketquant/core/domain/strategy/services/triple_screen_strategy_service.py`, `src/pocketquant/core/domain/strategy/value_objects.py` (`StrategyConfig`, `contract_spec`), tests `tests/core_test/unit/domain/strategy/test_triple_screen.py`, `tests/backtest_test/engine/test_triple_screen_backtest.py`.
- Costs: `scripts/seed_exness_symbols.py` (gold `commission_per_contract=0.035`, `spread=0.08`), `broker_factory.py` (spec read for paper).
- Backtest route: `src/pocketquant/app/routes/backtest.py`; backtest execution under `src/pocketquant/engine/backtest/`.
- Handoff of undone items (context only, out of scope): `plans/handoffs/exness-only-runtime-undone-items-20261031-1302.md`.

## Confirmed owner decisions (interview 2026-11-09, asked in Vietnamese, record in English)

| # | Decision |
|---|---|
| D1 | The next plan produces 1m strategy evidence: backtest and forward paper test with a 1m entry screen. |
| D2 | Both tracks. Track A: Triple Screen with a 1m entry screen, no code change, sets `1m,5m,15m` and `1m,15m,1h`. Track B: a dedicated 1m strategy. |
| D3 | Track B revives hitnrun2 (240-bar breakout, 480-bar SL extreme, 60-bar TP extreme, max loss 1%, min profit 2%) rewritten to the current multi-interval contract, with a cost filter that skips entries whose exit distance cannot cover the round-trip cost. |
| D4 | The backtest gate decides, per set: net `profit_factor >= 1.2` and `total_trades >= 100` over 12 months. Only passing sets go to paper. Paper runs 2 weeks per passing set, with no profit threshold, only to reconcile with the backtest. |
| D5 | The plan ends at the paper reconciliation and a written pass/fail verdict per set. Go-live and the two split-runtime bugs are out of scope. |

## Confirmed assumptions (owner accepted every one with the preview)

- A1: Track A runs 4 backtests: each set with `entry_type=stop, exit_mode=strategy` and with `entry_type=market, exit_mode=sl_tp`.
- A2: Costs come from the symbol's seeded spec (0.035 per oz per side, spread 0.08); no explicit cost is sent; runs go one at a time on prod; owner ask when one run exceeds 1800 s.
- A3: hitnrun2 runs as one interval, `intervals=["1m"]`.
- A4: The cost filter reads the cost from the symbol spec (`config.contract_spec`), never a hard-coded 0.15.
- A5: Paper reconciliation columns: trades per trading day, average commission per trade, exit-reason mix, zero `strategy_on_bar_error` / stale-bar events. Per-subscription trades are read by `trades.run_id` because the paper account is pooled.
- A6: The three existing Triple Screen paper subscriptions keep running and are not touched.

## Advice the plan should carry (from the accepted advice report)

- Run Track A first; start Track B coding only after Track A numbers exist (the advice orders it so; the owner chose "both", so Track B is not optional).
- Fact from the old code: `tp = max(60-bar extreme, close * (1 + min_profit_pct))`, `min_profit_pct = 0.02`, so the TP distance is at least about 80 USD/oz; a literal "TP distance < 0.15" filter never fires. Recommended filter: one parameter `min_cost_multiple` (suggested default 3) compared against the smaller of TP distance and SL distance, round-trip cost = `commission_per_contract * 2 + spread` from `config.contract_spec`. Backtest hitnrun2 with the default `min_profit_pct` and one lower value.
- Unverified: whether `StrategyConfig.contract_spec` is populated from the symbol's spec in both the backtest and trader paths. The plan must verify this first in Track B and stop-and-ask if fixing it needs an engine change.
- Unverified: 1m run time (estimate 20-25 min); 1m coverage for the 12-month window (rerun the Task 16.1 coverage check with 1m).
- Optional suggestions from the advice (archive the two completed plans; second shifted 12-month window for a passing set; reusable verdict snippet) are NOT owner-confirmed scope. Include only the reusable verdict snippet if it is the simplest way to produce the verdict lines; do not add the others.

## Done means

- A backtest table with `profit_factor` and `total_trades` for every run, one `verdict: pass|fail` line per set.
- hitnrun2 on master with `intervals=["1m"]`, a `min_cost_multiple` filter reading `config.contract_spec`, unit and backtest-path tests passing, CI green.
- One paper subscription per passing set, run at least 14 days, with a reconciliation record (the four A5 columns) against its backtest.
- The plan `status: completed` and moved to `plans/archive/`.

## Out of scope

Go-live Phases 11 and 12; `EXNESS_LIVE_TRADING`; the api `BROKER_DISABLED` check and the SPA strip flag; sweep harness, DSR, PBO; any change to Triple Screen logic; the three existing paper subscriptions.

## Constraints

- Live stays disarmed. `develop:master` push is an explicit owner ask every time. Committing and pushing `develop` is allowed without asking.
- Backtests run one at a time on prod, outside 00:00Z and 03:00Z windows, owner ask above 1800 s.
- No look-ahead (`docs/governance/no-look-ahead-rules.md`).
- Costs come from `ContractSpec`, never a literal 0.15.
- Code rules from `CLAUDE.md`: no docstrings, UUIDv7 keys, repositories only in core, fastapi only in app, short code, a flow in one file, no new class/flag/param without a real caller, log levels by frequency.
- English in plans, code, commits. No fake or synthetic data. Prod is read-only except the planned subscription creates and backtest runs. Creds live in `../pocketquant-config/`; never copy secrets into the repo; delete any copied SSH key at the end of each session.

## Handover contract (`--advice`, must be materialized in every phase file)

Every phase decomposes into ordered tasks. Each task states: Goal; Target files and symbols (exact paths); Steps (concrete, nothing left to infer); Success criteria (observable); Verify (an exact command and an exact expected result: exit code, substring, file existence or value, or literally `no verification needed`). Verification is a comparison, never a judgment. Every phase file ends with this block verbatim:

```markdown
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
```

## plan.md frontmatter

```yaml
---
title: "..."
description: "..."
status: pending
priority: P2
effort: "..."
branch: develop
tags: [...]
blockedBy: []
blocks: []
created: 2026-11-09
---
```

## Session

Working directory `D:\w\_me\algotrading\pocketquant`, branch `develop`, timezone Asia/Bangkok, date 2026-11-09. Plan text in English.
