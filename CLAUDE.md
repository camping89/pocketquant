# CLAUDE.md — PocketQuant

One Python package `src/pocketquant/` (subpackages: core, engine, backtest, app) + one Vite SPA (`web/`). Architecture, layers, run/test commands live in `README.md` + `docs/` — this file holds only the gotchas an agent gets wrong without being told, plus the docs index.

## Rules that change decisions

- **All repositories in core** (`core.infra.persistence.repositories`) — zero repos in backtest/app.
- **Routes** use `FromDishka[…CommandService/…QueryService]` + `DishkaRoute`, never `Depends()`. Service methods take Pydantic command/query models, return DTOs.
- **fastapi only in app** — core/engine never import it (import-linter enforced, 8 contracts).
- **Single uvicorn worker only** — scheduler/WS feed/broker are in-process singletons; `--workers N` duplicates the reconcile loop + live broker connection.
- **Primary keys: UUIDv7 only** — never hash / natural key / ObjectId.
- **Every `await` is a preemption point** — wire deps before consumers (publish-before-subscribe), no `await` inside atomic blocks.

## Reference docs (discover detail here)

- Architecture, layers, DI providers, request flows, "Where does X live", real-time streaming, strategy lifecycle → `docs/system-architecture.md`
- **Naming convention (suffix theo layer)**, comment policy, route/service/repo conventions, async-suspension patterns, schema, testing, perf → `docs/code-standards.md` (Section "Class Naming by Layer" + "Naming Principles & Exemptions")
- Run / test / canonical routes / remote-DB dev modes → `README.md`

## Writing docs & prose

- Markdown only. Bullets/tables over paragraphs; add a Mermaid v11 or ASCII diagram when a concept has 2+ interacting parts.
- **Prose tiếng Việt.** Giữ nguyên tiếng Anh: tên trong code (`StrategyAppService`, `bar_repository.py`), thuật ngữ kỹ thuật (`dependency injection`, `command service`, `import-linter`), định danh ngoài (`PEP 420`, `Binance`, `MongoDB`). Không trộn nửa Việt nửa Anh.
- **AS-IS only** — mô tả hệ thống hiện tại: không changelog, không banner (`Last Updated`, `Version`), không change-narrative ("Previously…", "now / no longer"). Git giữ lịch sử.
- **Code is the cleanest comment.** Default to no comment. Write one ONLY for: logic genuinely hard to follow in one spot, or a cheat/hack/workaround (+ external-system quirk, magic-number rationale, `# type: ignore` reason). Never restate code, never name-echo a symbol, no banners. Full policy → `docs/code-standards.md` → "Comment Policy".
