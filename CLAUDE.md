# CLAUDE.md — PocketQuant

5-package monorepo: 4 Python (`uv` workspace, `pocketquant.*` namespace) + 1 Node SPA (`pocketquant-web`, excluded from the workspace). Pattern: DDD + CQRS + Clean Architecture + Dishka DI.

## Layout

Dependency graph: `core ◁ execution ◁ {backtest, trading} ◁ {app, bff}`, `web → bff`. `app` and `bff` are independent siblings with no cross-imports (verified by import-linter). `backtest` and `trading` are independent siblings — neither imports the other.

## Rules that change decisions

- **All repositories in core** (`core.persistence.repositories`) — zero repos in backtest/trading.
- **Routes** use `FromDishka[Mediator]` + `DishkaRoute`, never `Depends()`.
- **Primary keys: UUIDv7 only** — never hash / natural key / ObjectId.
- **Async: every `await` is a preemption point** — wire deps before consumers (publish-before-subscribe), no `await` inside atomic blocks.

## Reference docs (discover detail here)

- Architecture, layers, DI providers, request flows, "Where does X live" → `docs/system-architecture.md`
- Naming table, comment policy, async-suspension patterns, schema, testing, perf → `docs/code-standards.md`
- Dependency + relationship visuals → `docs/architecture-visual-map.md`, `docs/system-relationship-map.md`
- Run / test / canonical routes → `README.md`

## Writing docs & prose

- Markdown only. Bullets/tables over paragraphs; add a Mermaid v11 or ASCII diagram when a concept has 2+ interacting parts.
- **Prose tiếng Việt.** Giữ nguyên tiếng Anh: tên trong code (`StrategyAppService`, `bar_repository.py`), thuật ngữ kỹ thuật (`dependency injection`, `CQRS handler`, `uv workspace`), định danh ngoài (`PEP 420`, `OKX`, `MongoDB`). Không trộn nửa Việt nửa Anh — thuật ngữ thì để nguyên cả cụm.
- **AS-IS only** — docs mô tả hệ thống hiện tại, không phải lịch sử. Không changelog, không banner (`Last Updated`, `Version`, `Status`), không change-narrative ("Previously…", "now / no longer", dated migration). Git giữ lịch sử.
- Comments & filenames explain WHY, no plan/phase/finding refs. Full policy → `docs/code-standards.md` → "Comment Policy".
