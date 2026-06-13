# CLAUDE.md — PocketQuant

Single Python package `src/pocketquant/` (with subpackages: core, engine, backtest, app) + 1 Node SPA (`web/`). Pattern: DDD + Clean Architecture + Dishka DI. Dependency enforcement via import-linter contracts in `pyproject.toml` (7 contracts).

## Layout

Dependency graph: `core ◁ engine ◁ backtest ◁ app`, `web → app`. Backend là 1 process duy nhất (`pocketquant.app.main`, port `:41921`): toàn bộ API routes, SPA serving, scheduler, WS feed, reconcile loop, backtest worker chạy chung 1 DI container.

## Rules that change decisions

- **All repositories in core** (`core.infra.persistence.repositories`) — zero repos in backtest/app.
- **Routes** use `FromDishka[SomeCommandService/SomeQueryService]` + `DishkaRoute`, never `Depends()`. Service methods take Pydantic command/query models and return DTOs. Example: `StrategyCommandService`, `BacktestQueryService`.
- **fastapi only in app** — core/engine/backtest never import fastapi (import-linter enforced).
- **Single uvicorn worker only** — scheduler/WS feed/broker là in-process singletons; `--workers N` sẽ nhân bản reconcile loop + live broker connection.
- **Primary keys: UUIDv7 only** — never hash / natural key / ObjectId.
- **Async: every `await` is a preemption point** — wire deps before consumers (publish-before-subscribe), no `await` inside atomic blocks.

## Reference docs (discover detail here)

- Architecture, layers, DI providers, request flows, "Where does X live", real-time streaming, strategy lifecycle, ops context, visuals → `docs/system-architecture.md`
- Naming table, comment policy, route/service/repo conventions, async-suspension patterns, schema, testing, perf → `docs/code-standards.md`
- Run / test / canonical routes → `README.md`

## Writing docs & prose

- Markdown only. Bullets/tables over paragraphs; add a Mermaid v11 or ASCII diagram when a concept has 2+ interacting parts.
- **Prose tiếng Việt.** Giữ nguyên tiếng Anh: tên trong code (`StrategyAppService`, `bar_repository.py`), thuật ngữ kỹ thuật (`dependency injection`, `command service`, `import-linter`), định danh ngoài (`PEP 420`, `OKX`, `MongoDB`). Không trộn nửa Việt nửa Anh — thuật ngữ thì để nguyên cả cụm.
- **AS-IS only** — docs mô tả hệ thống hiện tại, không phải lịch sử. Không changelog, không banner (`Last Updated`, `Version`, `Status`), không change-narrative ("Previously…", "now / no longer", dated migration). Git giữ lịch sử.
- Comments & filenames explain WHY, no plan/phase/finding refs. Full policy → `docs/code-standards.md` → "Comment Policy".
