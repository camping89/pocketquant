---
name: gate-commands
description: Verified full-gate command set for PocketQuant review (backend + frontend), including the local-DB pytest prefix that bypasses conftest prod-block
metadata:
  type: reference
---

Canonical gate commands (match CI `.github/workflows/cicd.yml`), all run green on 2026-06-28:

Backend (run from repo root `/Users/admin/workspace/_me/algo-trading/pocketquant`):
- `uv run ruff check`
- `uv run lint-imports` — expect **7 contracts kept** (layered arch, core-no-infra, core-no-inner, engine-no-upper, backtest-no-upper, fastapi-only-in-app, UUID7-only)
- pytest needs local DB override (conftest blocks prod URLs):
  `MONGODB_URL="mongodb://localhost:27017" REDIS_URL="redis://localhost:6379/1" uv run pytest tests/ -q`
- OpenAPI contract guard: `tests/baseline/test_openapi_snapshot.py` — adding a strategy to `STRATEGY_REGISTRY` does NOT change schema (`/backtest/strategies` returns `list[str]` at runtime).

Frontend (from `web/`):
- `npm run lint` (eslint) — repo has ~6 pre-existing `react-hooks/exhaustive-deps` warnings (chartRef / ref-in-cleanup in trading-chart.tsx, strategy-chart.tsx, monitor jobs route); 0 errors is the bar.
- `npm run build` (= `tsc -b && vite build`) — this is the FE typecheck; project has **no mypy** on the BE side.
- `npm run test` (vitest) — FE test runner added during engulfing work; `tsconfig.test.json` isolates test types.

Note: zsh parses a whole quoted-flag command as one word if you prefix `timeout 180 uv run ...` without it being a real binary; just run `uv run ...` directly.
