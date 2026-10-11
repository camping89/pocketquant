---
phase: 5
title: "Lean coding standard and metric ratchet"
status: pending
priority: P1
effort: 2d
dependencies: [4]
---

# Phase 05: Lean coding standard and metric ratchet

## Context Links
- Advice §2.4, §3 and §9 (success metrics).
- The current `docs/code-standards.md` is 799 lines. Stale claims: "Service Extract-Method Pattern" (§9), the 200-LOC module size rule ("Module Size") and the 20+ suffix roles ("Class Naming by Layer"). The comment section heading is `## Comment Policy — Explain WHY, Not WHAT` (:428).
- `CLAUDE.md` lines 3 ("7 contracts") and 12 (the "Service methods take Pydantic command/query models" rule).
- CI: `.github/workflows/cicd.yml` job `tests`, step `Check import contracts (layered architecture)` (:31-32).
- Metric baseline: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json` (794 / 661 / 315 = 0.4766 / 63). The metric script already supports `--out` and `--ratchet` (Phase 02 T2.2).

<!-- Updated: Validation Session 1 - ratchet freeze replaces the threshold stop-and-ask; standard is AS-IS -->
## Goal
A standard that matches the code as it exists at the end of Phase 04 (D5). The metric is measured after the lean refactor and frozen as a CI ceiling (the ratchet): CI fails if a later change makes the tiny share or the delegation count worse. The ≤30% tiny share and ≤20 delegations stay in the standard as an aspiration only, never as a gate. Exness, the add-a-provider touchpoint list and the `EXNESS_*` secrets rule are written in Phase 09, once they exist.

## Files to Create or Modify
- Rewrite: `docs/code-standards.md`
- Modify: `CLAUDE.md`, `.github/workflows/cicd.yml`, `pyproject.toml` (`[tool.code-metrics]`)
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json`

## Tasks

### T5.1 Branch
- **Goal:** Isolate the work.
- **Target files and symbols:** git
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c docs/lean-standard`
- **Success criteria:** On the branch.
- **Verify:** `git branch --show-current` prints `docs/lean-standard`.

<!-- Updated: Validation Session 1 - §8 AS-IS without router or provider checklist; §13 ratchet; §14 unchanged content -->
<!-- Updated: Validation Session 3 - source headings named instead of section numbers -->
### T5.2 Rewrite `docs/code-standards.md`
- **Goal:** Rules of thumb instead of mandates, written AS-IS in Vietnamese prose with English technical terms, as `CLAUDE.md` requires.
- **Target files and symbols:** `docs/code-standards.md`
- **Steps:**
  1. Read the current file in full.
  2. Write the new file with exactly these H2 sections, in order. The current file has 17 H2 headings, so the numbers below refer to the new file only. Content carried over from the current file comes from these headings: new section 10 from the H3 `### Async Suspension Points — "Await Is Preemption"` (currently line 583, under `## Performance Considerations`, including its `**1. Publish-before-subscribe**` rule), trimmed of history; new section 11 from `## Comment Policy — Explain WHY, Not WHAT` (currently line 428), verbatim; new section 14 from `## Configuration & Secrets` (currently line 733).
     1. `## Nguyên tắc`: KISS, DRY and balance (no god-functions and no micro-helpers).
     2. `## Khi nào extract helper`: extract only when the name adds meaning or the code is reused. A flow should be readable in one file where possible and in 3 at most.
     3. `## Kích thước file và hàm`: about 400 LOC per file is soft guidance, not a split trigger. Functions stay ≲ 60 lines.
     4. `## Đặt tên`: the suffix table is trimmed to `Repository`, `Service`, `Event`, `Error` and `Provider` (Dishka). Existing `AppService`, `CommandService` and `QueryService` names stay, but they are not distinct roles. Include the existing file-naming rules.
     5. `## Routes và services`: `FromDishka[...]` with `DishkaRoute`, never `Depends()` for services. Pydantic models only for real request bodies; scalars are passed directly.
     6. `## Dependency Injection`: 3 provider modules (`infrastructure`, `adapters`, `services`), `Settings` via `from_context`, `STRICT_VALIDATION`, and one provider per type.
     7. `## Repositories`: all in `core.infra.persistence.repositories`. UUIDv7 primary keys only (keep the existing code example).
     8. `## Sync policy pattern`: describe only what exists now. `SyncPolicy` fields (including `data_provider`, `quote_provider`, `poll_time_cap_s`, `calendars`), the `SyncPolicies` registry built in `app/di/adapters.py`, lookup strictly by exchange suffix through `policy_for` (no fallback; an unknown suffix logs once and is skipped), `MarketCalendar` sessions, the `sync_runner.py` jobs and `bar_integrity.py`. Do not write an add-a-provider checklist here; Phase 09 adds it.
     9. `## Composite symbol`: keep the existing content and add `split_composite` as the single split helper.
     10. `## Async: await là preemption point`: keep the existing section, trimmed.
     11. Keep the existing heading `## Comment Policy — Explain WHY, Not WHAT` and its content verbatim. `CLAUDE.md` links this heading.
     12. `## Testing`: characterization tests before a refactor, the snapshot baselines with the `BASELINE_UPDATE=1` regeneration rule, and testcontainers.
     13. `## Quality gate`: `just test`, ruff, pyright, 3 import-linter contracts, and the metric ratchet (`scripts/code_metrics.py --ratchet` against `[tool.code-metrics]` in `pyproject.toml`, with the metric definition from `scripts/code_metrics.py`). State that the ceiling only moves down, that raising it is a user decision, and that ≤30% tiny share and ≤20 delegations are an aspiration, not a gate.
     14. `## Configuration & Secrets`: keep the existing content.
  3. Do not include any of these strings: `Current Status`, `Last Updated`, `Version:`, `200 LOC`, `Extract-Method`, `Exness`, `EXNESS_`.
- **Success criteria:** The standard matches the code and contains no stale or future claims.
- **Verify:**
  - `grep -cE "Current Status|Last Updated|Version:|200 LOC|Extract-Method|Exness|EXNESS_" docs/code-standards.md` prints `0`.
  - `grep -c "^## " docs/code-standards.md` prints `14`.
  - `grep -c "SyncPolicies" docs/code-standards.md` is ≥ 1.
  - `grep -c "## Comment Policy" docs/code-standards.md` prints `1`.

### T5.3 `CLAUDE.md` rules aligned
- **Goal:** The binding rule file stops contradicting the standard.
- **Target files and symbols:** `CLAUDE.md`, lines 3 and 12
- **Steps:**
  1. Line 3: replace `(7 contracts)` with `(3 contracts)`.
  2. Line 12: replace the sentence "Service methods take Pydantic command/query models and return DTOs." with "Service methods take Pydantic models only for real request bodies; scalar parameters are passed directly."
- **Success criteria:** Both lines are updated and nothing else changes.
- **Verify:** `grep -c "3 contracts" CLAUDE.md` prints `1`. `grep -c "Pydantic command/query models" CLAUDE.md` prints `0`. `git diff --stat CLAUDE.md` shows `2 insertions(+), 2 deletions(-)`.

<!-- Updated: Validation Session 1 - measure after the refactor and freeze the ceiling (ratchet), replacing the threshold decision -->
### T5.4 Freeze the metric ratchet
- **Goal:** The values measured after the lean refactor become the CI ceiling, and CI fails on any regression.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json`, `pyproject.toml` `[tool.code-metrics]`, `.github/workflows/cicd.yml` job `tests`
- **Steps:**
  1. `uv run python scripts/code_metrics.py --out plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json`
  2. Append to `pyproject.toml`, copying the two numbers exactly from that JSON (`tiny_share` as written, 4 decimals; `delegations` as an integer):
     ```toml
     [tool.code-metrics]
     max_tiny_share = <tiny_share>
     max_delegations = <delegations>
     ```
  3. In `cicd.yml`, after the step `Check import contracts (layered architecture)`, insert:
     ```yaml
           - name: Code metrics ratchet
             run: uv run python scripts/code_metrics.py --ratchet
     ```
  4. Report the frozen values next to the baseline (0.4766 / 63) to the user as information. This is not a stop-and-ask; the user already chose the ratchet.
- **Success criteria:** The ceiling equals the measured values and the ratchet passes on the current code.
- **Verify:**
  - `uv run python -c "import json,tomllib;m=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-after-refactor.json'));c=tomllib.load(open('pyproject.toml','rb'))['tool']['code-metrics'];print(c['max_tiny_share']==m['tiny_share'] and c['max_delegations']==m['delegations'])"` prints `True`.
  - `uv run python scripts/code_metrics.py --ratchet; echo $?` ends with `0`.
  - `uv run python -c "import yaml;yaml.safe_load(open('.github/workflows/cicd.yml'))"` exits 0.

<!-- Updated: Validation Session 1 - gate includes the ratchet -->
### T5.5 Gate and ship
- **Goal:** Deployed with green CI, which now runs the ratchet.
- **Target files and symbols:** git
- **Steps:**
  1. Run the full gate: `just test`, `uv run ruff check`, `uv run pyright`, `uv run lint-imports` and `uv run python scripts/code_metrics.py --ratchet`.
  2. `git add docs/code-standards.md CLAUDE.md .github/workflows/cicd.yml pyproject.toml plans/261009-0858-exness-venue-lean-sync-refactor`
  3. `git commit -m "docs(standards): rewrite code standard as lean rules of thumb and freeze the code metric ratchet"`
  4. Ask the user for approval, then merge, push and watch CI as in Phase 01 T1.7 steps 4-6.
- **Success criteria:** Green.
- **Verify:** The gate passes with the same pass conditions as Phase 04 T4.6, `Contracts: 3 kept, 0 broken.` included, and the ratchet exits 0. `gh run watch` exits 0. `gh run view <databaseId> --log | grep -c "Code metrics ratchet"` ≥ 1, and the `=== Verdict:` line contains `, 0 failures)`.

## Verification
T5.2 (greps), T5.3, T5.4 (frozen ceiling equals the measurement) and T5.5 (CI runs the ratchet).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- Any later need to raise the ratchet ceiling is a user decision; never edit `[tool.code-metrics]` upward without it.
- A test failure stays unexplained.

## Risks
- **The ratchet blocks a legitimate change later** (likelihood M, impact M). Mitigation: the failing CI step names the metric; the fix is to restructure (for example inline thin wrappers), or ask the user to raise the ceiling. Never inline code only to move a number.
- **Docs drift into future claims** (M/L). Mitigation: T5.2 bans Exness and status strings; Phase 09 adds the Exness content once it exists.

## Rollback
`git revert` the merge commit. These are docs, CI and a `pyproject.toml` section only.

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
