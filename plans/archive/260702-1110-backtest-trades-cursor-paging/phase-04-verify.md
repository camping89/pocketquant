# Phase 04 — Verify: tests, lint/types/build, openapi snapshot, review, smoke

## Backend

- `just test-pkg core` + backtest tests green (calculator, repo paged/keyset/markers/count, stats service, cursor roundtrip).
- `just lint`, `just types` clean. import-linter contracts pass.
- **OpenAPI + route snapshots**: routes changed (trades signature) + added (trade-markers, stats). Regenerate via `just baseline` (or `BASELINE_UPDATE=1 .venv/bin/python -m pytest tests/baseline/`), then review the diff before committing:
  - `tests/baseline/openapi_app_snapshot.json`
  - `tests/baseline/route_inventory_app_snapshot.json`

## Frontend

- Remove/adjust `web/src/components/backtest/stats-utils.test.ts` — the compute fns move to BE. Keep only tests for logic that remains client-side (if any). Do NOT leave tests importing deleted symbols.
- `npm run lint`, `npm run build` clean.

## Code review (MANDATORY)

- Spawn `code-reviewer` subagent with: scout summary, acceptance criteria, blast radius (trades tab, chart, stats, run-history rail, orders/overview/risk tabs, poll-until-finished). Checks:
  - a) every acceptance criterion met
  - b) no regression in touchpoints (overview/risk/orders tabs, verdict PATCH, history rail, run polling)
  - c) public contracts: `/{run_id}/trades` response shape CHANGED intentionally (was `{trades:[...]}`, now paged) — call out; confirm no other consumer of old shape (grep FE + Bruno/http tests).
  - d) follows existing patterns (DishkaRoute, FromDishka, service-owns-DTO, react-query).
  - e) no new lint/type/build errors anywhere.

## Manual smoke (prod run in issue)

- Run `019f141c-a437-70a9-8d2a-d748b773d9e7` (per re-smoke memory: use optimize-not-run discipline against prod DB; restore .env after).
- Verify: trades tab no longer lags; scroll loads more; sort/filter hit server; click trade → box + scroll; markers present; histograms/streaks/PF/drawdown correct; Open Positions tab populated.

## Finalize

- `/ck:project-management` sync-back across phases + plan status.
- `docs-manager`: update `docs/system-architecture.md` (new stats app-service, paged trades endpoint, request-flow) + `docs/code-standards.md` if a cursor/pagination convention is now established.
- Ask user to commit via `git-manager`.
- `/ck:journal` entry.

## Exit criteria

- All gates green; no unresolved regression; user-approved.
