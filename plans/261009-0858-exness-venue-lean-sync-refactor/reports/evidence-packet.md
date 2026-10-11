# Evidence packet — exness-venue-lean-sync-refactor (`ak:plan --ultra --advice`)

Immutable input shared identically by all five candidate planners. Do not edit.

## Task

Turn the confirmed advice into an executable, handover-ready implementation plan (`plan.md` + `phase-NN-*.md`) for PocketQuant:
add Exness as a third live venue behind the existing ports, after a balanced refactor of the market-data sync pipeline into a per-provider `SyncPolicy` + one shared runner, plus a rewritten coding standard. The plan will be executed by a weaker model (Sonnet/Flash class) via `/ak:cook --advice`, so it must be executable without inference.

## Sources (read these first, in order)

1. Advice report (confirmed recommendations, phases, checklist, success metrics, handoff brief): `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement.md`
2. Interview state (confirmed reframing R1-R8, G1-G3, D1-D7, non-goals, constraints, assumptions A-i..A-v, scout notes, Exness API facts): `D:/w/_me/algotrading/plans/reports/advise-261008-1148-exness-api-replacement-state.md`
3. Repository (git repo, branch `master`): `D:/w/_me/algotrading/pocketquant/`
   - `CLAUDE.md` (repo rules — binding), `README.md`, `justfile`, `pyproject.toml` (ruff, pyright, 7 import-linter contracts at lines ~74-140)
   - `docs/code-standards.md`, `docs/system-architecture.md`, `docs/deployment.md`
   - `src/pocketquant/{core,engine,backtest,app}/`, `tests/{core_test,engine_test,backtest_test,app_test,baseline}/`, `scripts/`
   - Prior plan for house style: `plans/260630-0031-backtest-mae-mfe-excursion/`
4. Exness API: `https://www.exness-api.com/` and its OpenAPI spec `/exness_api.yaml` (v1.0.2). Facts already gathered are in source 2; re-fetch only to settle an exact endpoint/field name.

Verify every file path, symbol, and command you put in the plan against the repo. Never invent paths.

## Confirmed scope (from the accepted advice — do not reopen)

- Keep Binance, OKX, PaperBroker and both strategies (`hitnrun2`, `engulfing`). Nothing deleted except the job modules / `sync_internals` / DI files / route files the refactor replaces.
- Exness REST + WS now (data provider, realtime quote provider, broker). MT5 = documented future provider only. No MCP. No deployment topology change.
- Order: Phase 0 read-only spike → refactor with Binance as the proving provider (characterization tests first) → Exness adapters as policy #2 → validation (spread param in PaperBroker, backtests, min-lot live round trip per strategy) → docs.
- Done means D1-D7 and success metrics exactly as in the advice report section 9 and the handoff brief.
- Refactor thresholds the user confirmed as "balanced": tiny-method share ≤30% (from 48%), pure-delegation methods ≤20 (from 63), any flow readable in ≤3 files, functions ≲60 lines, `app/di` ≤3 provider modules, market-data routes ≤2 files, import-linter = 3 contracts, `sync_internals/` gone.
- Assumptions confirmed: A-i instruments XAUUSD, EURUSD, BTCUSD CFD; A-ii bid candles stored; A-iii tick volume in `Bar.volume`; A-iv the thresholds above; A-v Exness policy = WS ticks live + REST native candles polled each minute, no cascade.

## Preconditions owned by the user (plan must gate on them, not perform them)

- User verifies the Developer Portal link from Exness Personal Area resolves to `exness-api.com`.
- User creates a scoped API key (one account, VPS IP allowlist) and stores it in `pocketquant-config` / env (`EXNESS_ACCOUNT_ID`, `EXNESS_API_KEY`, `EXNESS_PRIVATE_KEY` or path).
- User sets the live-test risk cap (minimum lot, SL always attached, daily loss cap).
The executor must never print, log, or commit key material.

## Repo constraints (binding)

- Single uvicorn worker; `core`/`engine`/`backtest` never import FastAPI; UUIDv7 primary keys; all repositories in `core.infra.persistence.repositories`; async publish-before-subscribe.
- Comment policy and docs rules in `CLAUDE.md` (docs prose in Vietnamese with English technical terms; AS-IS only, no changelog/banners; default no comments; no plan/phase refs in code, comments, test names or commit messages).
- Conventional commits, no AI references. Do not commit secrets.
- Quality gate per phase: `just test` (= `.venv/Scripts/python.exe -m pytest` on Windows), `uv run ruff check`, `uv run pyright`, `uv run lint-imports`. Confirm exact invocations from `justfile`/`pyproject.toml`.
- CFD lot/spread/contract-size logic lives only in the Exness adapter, never in `core/domain`.

## Handover contract (`--advice`) — every candidate MUST satisfy

The executor reads only `plan.md` and the phase files. Materialize everything into them.

- Keep the canonical phase frontmatter (`phase`, `title`, `status: pending`, `priority`, `effort`, `dependencies`) and sections Goal / Files to Create or Modify / Tasks / Verification, plus Context Links, Risks, Security where useful.
- Each phase = ordered tasks. Each task states: **Goal** (one observable outcome), **Target files and symbols** (exact paths, functions, endpoints, config keys), **Steps** (ordered, no inferred steps), **Success criteria** (observable), **Verify** (either `no verification needed` for a pure edit covered by the next task, or a mechanical pass condition: exact command + expected exit code / substring / file existence / value). "Confirm it works" is not allowed.
- Every phase file literally contains this block:

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

- Stop-and-ask conditions from the advice handoff brief must appear where they apply (live order above min lot or without SL; deleting Binance/OKX code; deployment topology change; Exness limits making policy A-v infeasible; unexplained test failure; portal link not resolving to exness-api.com).
- `plan.md` ≤ ~80 lines: frontmatter (`title`, `description`, `status: pending`, `priority`, `effort`, `branch: master`, `tags`, `blockedBy: []`, `blocks: []`, `created: 2026-10-09`), Overview, Goals, Phases table with human-readable link text, Dependencies, Success Criteria, user preconditions.

## Rubric the verifier will apply (1-20 each)

1. **Faithfulness** — matches the confirmed scope, D1-D7, thresholds, assumptions, non-goals, phase order; adds nothing unrequested; drops nothing requested.
2. **Grounding** — paths, symbols, commands, and current-state numbers verified against the repo/spec; no invented files.
3. **Executability by a weaker model** — tasks decomposed with no inferred steps; exact targets; every load-bearing step has a mechanical Verify; Failure Protocol present in every phase.
4. **Safety & risk control** — characterization tests before refactor; behaviour of Binance/OKX pinned; live-money steps gated (min lot, SL, user preconditions, no secrets printed); rollback per phase.
5. **Balance / KISS** — the plan's own design follows the lean standard (no new layers for their own sake, no god-functions), phase sizing sensible for one person over ~5-7 weeks.

Hard constraints (fail = reject candidate): missing Failure Protocol in any phase; any task without a Verify field; invented repo paths in target files; scope that deletes Binance/OKX/PaperBroker or builds MT5/MCP.

## Output format (candidates)

Write ONE file: `D:/w/_me/algotrading/pocketquant/plans/261009-0858-exness-venue-lean-sync-refactor/reports/planner-ultra-candidate-{N}.md`, containing every plan file concatenated, each preceded by a delimiter line on its own:

```
<!-- FILE: plan.md -->
...full plan.md content including frontmatter...
<!-- FILE: phase-01-<slug>.md -->
...
```

Phase file names: `phase-NN-<kebab-slug>.md`, NN two digits starting at 01. No other files written. Read-only everywhere else. Do not commit.
