# Brainstorm Summary — Move Package Tests to Root `tests/`

## Problem Statement

4 Python test suites currently live inside their packages
(`packages/pocketquant-{core,backtest,trading,api}/tests/`, 57 files total).
Goal: consolidate all pytest suites under root `tests/`, named per-package,
ending with `_test`, snake_case.

## Requirements (concrete)

- **Expected output:** `tests/{core,backtest,trading,api}_test/` directories, each
  containing the moved suite + its `conftest.py` + subdirs intact. Package
  `tests/` folders removed.
- **Acceptance criteria:** `uv run pytest tests/ --collect-only` reports the same
  test count pre/post; `just test` green; pyright clean; api relative imports
  (`from .app_factory import make_test_app`) still resolve.
- **Scope boundary (OUT):** no conftest consolidation (duplicates kept as-is); no
  CI full-suite expansion (CI stays api-only smoke); `tests/{http,manual,scripts}`
  untouched.
- **Non-negotiable constraints:** `<pkg>_test` naming, Python snake_case, preserve
  git history (`git mv`), no behavior change.
- **Touchpoints:** `pyproject.toml`, `pyrightconfig.json`, `justfile`,
  `.github/workflows/cicd.yml`, `docs/code-standards.md`, `docs/system-architecture.md`.

## Target Layout

```
tests/
├── conftest.py              # existing — workspace root → sys.path (unchanged)
├── core_test/               # ← packages/pocketquant-core/tests/
├── backtest_test/           # ← packages/pocketquant-backtest/tests/
├── trading_test/            # ← packages/pocketquant-trading/tests/
├── api_test/                # ← packages/pocketquant-api/tests/
│   └── integration/         #   __init__.py + app_factory.py preserved
├── scripts/  manual/  http/ # existing (untouched)
```

## Approaches Evaluated

| Approach | Verdict |
|----------|---------|
| `git mv` per package + collapse `testpaths` to `["tests"]` | **CHOSEN** — preserves history, minimal edits, importlib mode disambiguates |
| Symlink shim / keep both | Rejected — duplicate collection, confusing |
| Consolidate conftests same round | Deferred — user chose keep-as-is to limit blast radius |

## Decisions (user-confirmed)

1. Naming: `<pkg>_test` (core_test, backtest_test, trading_test, api_test).
2. Conftests: keep per-folder, no consolidation (duplication accepted).
3. CI: path-fix only → `pytest tests/api_test/` smoke; do NOT expand to full suite.

## Implementation Edits (6)

1. `git mv packages/pocketquant-<pkg>/tests tests/<pkg>_test` ×4.
2. `pyproject.toml` → `testpaths = ["tests"]`.
3. `pyrightconfig.json` → swap 4 `packages/*/tests` → `tests/*_test` in `include`
   and `executionEnvironments`.
4. `justfile` → `test-pkg pkg:` → `pytest tests/{{pkg}}_test/`.
5. `cicd.yml` → `uv run pytest tests/api_test/ -v`.
6. Docs: `code-standards.md:595`, `system-architecture.md:533` path refs.

## Risks & Mitigations

- **api relative imports** — dir stays a package (`__init__.py` travels). Verified
  by collect-only + full run.
- **4 duplicate `pytest_configure` prod-guards** — already idempotent under one
  suite today; unchanged.
- **Stale `__pycache__`** — clean before verify to avoid ghost collection.

## Incidental Improvement

`deploy/Dockerfile:26 COPY packages/ packages/` currently copies nested
`packages/*/tests/` into the image (`.dockerignore tests/` only matches root).
Post-move, all tests sit in root `tests/` → correctly excluded. Smaller image,
no action needed.

## Validation

```bash
find . -name __pycache__ -type d -path '*/tests/*' -prune -exec rm -rf {} +  # pre-clean
uv run pytest tests/ --collect-only   # count must match baseline
just test                              # full suite green
pyright                                # clean
```

## Out of Scope / Unresolved

- Conftest DRY consolidation — candidate for a follow-up round.
- CI coverage gap (core/backtest/trading not run in CI) — user deferred.
