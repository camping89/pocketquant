# Comment Sweep & Policy Rule — Monorepo Refactor

**Date**: 2026-05-30 14:15  
**Severity**: Low (chore)  
**Component**: Codebase-wide (docs, web, backtest, core, trading, api, root tests)  
**Status**: Completed  

## What Happened

Executed 6-phase comment sweep across pocketquant monorepo via /ck:cook --auto from plan `plans/260530-comment-sweep-and-policy-rule/`. Codified a WHY-not-WHAT comment policy in `CLAUDE.md` + fuller guidance in `docs/code-standards.md`. Removed 58-158 comments per package; kept preservation candidates (async-suspension notes, race-condition ordering, exchange quirks, DI composition context, type-ignore rationale). Full suite: 3 fail/391 pass/12 skip (identical before and after).

**Commits:** 32eb2e1 (policy docs) → 374171e (web) → 987eb42 (backtest) → d0426c3 (core) → fbf3ad6 (trading) → c6f56d2 (api+root tests).

## The Brutal Truth

This should have been a 2-hour mechanical task. It became a 6-phase multi-agent job because the codebase is **thick with defensive comments** — mostly banner/name-echo/restatement that adds noise. The frustrating part: once we codified what to keep (WHY for race conditions, async suspension points, external API quirks), the agent handoffs worked cleanly, but I had to gate every phase myself because **I don't fully trust agent diffs without manual verification**. Core and trading packages needed high-touch review (async ordering, OKX exchange behavior) — removing a single line there could mask a subtle state machine invariant.

The positive surprise: ruff error count dropped 43 → 17 just by removing over-long comment lines. Invisible quality win.

## Technical Details

- **Baseline:** Phase 1 gated via `npm run test` + `jest` + full suite: 3 fail/391 pass/12 skip. Pre-existing failures in `tests/scripts/` (signature drift: `insert_many(source=...)` kwarg). Comment-unrelated.
- **Per-package verification:** Each phase diff filtered via git grep (`^-\s*//`, `^-\s*#`, `^-\s*"""`) to confirm deletion-only (no logic changes). Ruff reflow (E501 line-wrap) captured in same commit per plan.
- **Phase 4 (core):** 132 pass before+after. Preserved `async/await` suspension points (mediator ordering, hydration ordering, bar state machine). Agent flagged each; I spot-checked via file context.
- **Phase 5 (trading):** 31 pass before+after. Preserved OKX API quirks (websocket timing, order-state desync notes). High-care area.
- **Phase 6 (api+root tests):** 113 pass/12 skip. `main.py` left 100% untouched by design (DI/async composition root — too brittle to touch).
- **Mid-flight fix (phase 6):** Removing divider comments between imports exposed 3 unsorted import blocks (I001). Ran `uv run ruff check --fix --select I001` (imports-only, verified no logic change), manually wrapped 121-char comment to 2 lines, re-verified lint → baseline count.

## What We Tried

- Delegated phases 2-6 to fullstack-developer subagents with explicit keep-bar (remove: name-echo, banner, restatement; keep: WHY, race, ordering, await-suspension, external-quirk, type-ignore, contract-docstring).
- Gated each phase: diff grep verification + per-package test run + lint baseline before commit.
- Used `git stash` compare (branch vs stash) to prove regression-neutral (comment-removal is behavior-neutral; identical pass/skip counts = acceptance proof).

## Root Cause Analysis

The codebase carried ~15 years of accumulated comment patterns (banner blocks, redundant restatement, placeholder docstrings) without a documented policy. No agent was empowered to sweep before because "what's a safe comment to delete?" was unspecified. Once codified (WHY > WHAT), agents could move fast; controller just needed to verify (not trust).

The ruff-PATH gotcha: `just lint`/`just fmt` recipes call `ruff` directly without full path. In this env, global `ruff` doesn't exist. Recipe assumes it's in `PATH` or installed globally; uv venv doesn't auto-inject. Should be `uv run ruff` or explicit venv path in recipes.

## Lessons Learned

1. **Policy codification unblocks delegation.** Before: "is this comment OK to delete?" → agent hesitates. After: explicit keep-bar → agent moves, controller verifies. Split work clearly.
2. **Regression-neutral proof via test symmetry.** If comment-removal is behavior-neutral, identical per-package + full-suite pass/skip counts before+after each sweep = acceptance proof. Faster than code review.
3. **High-care zones need manual gate.** Core (async ordering), trading (exchange quirks), main.py (DI root) — don't trust agent diffs. Manual spot-check on the few flagged lines takes 5 min and saves a hidden state-machine bug.
4. **ruff PATH assumption is fragile.** Document: "ruff must be on global PATH or via `uv run ruff`". Or fix recipes to use full path.
5. **Divider-comment removal surfaces lint issues.** Removing blank-line separators between import groups can expose pre-existing I001 drift. Run lint after removal, not before.

## Next Steps

- [ ] Update `just` recipes to use `uv run ruff` instead of bare `ruff` (prevent future PATH errors).
- [ ] Add comment-policy section to team onboarding docs (link to `docs/code-standards.md`).
- [ ] Monitor backtest + core + trading for any async/state-machine regressions in next integration test run (policy applied; behavior should be unchanged, but high-care areas deserve a week of observation).

**Owner**: Closed; no follow-up required unless ruff-PATH recipes hit again.
