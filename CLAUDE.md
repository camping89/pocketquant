# CLAUDE.md — PocketQuant

One Python package `src/pocketquant/` (subpackages: core, engine, backtest, app) + one Vite SPA (`web/`). Architecture, layers, run/test commands live in `README.md` + `docs/` — this file holds only the gotchas an agent gets wrong without being told, plus the docs index.

## Credentials & VPS access

- Claude Code may freely read and use all creds in `../pocketquant-config/` (SSH key, prod `.env`, Mongo/Redis passwords) and SSH into the VPS. The VPS is disposable and temporary — no approval needed.
- One hard rule: **all creds live in `pocketquant-config`, never in this repo.** No secrets in code, tests, docs, or committed env files here.

## Rules that change decisions

- **All repositories in core** (`core.infra.persistence.repositories`) — zero repos in backtest/app.
- **Routes** use `FromDishka[…CommandService/…QueryService]` + `DishkaRoute`, never `Depends()`. Service methods take Pydantic command/query models, return DTOs.
- **fastapi only in app** — core/engine never import it (import-linter enforced, 8 contracts).
- **Single uvicorn worker only** — scheduler/WS feed/broker are in-process singletons; `--workers N` duplicates the reconcile loop + live broker connection.
- **Primary keys: UUIDv7 only** — never hash / natural key / ObjectId.
- **Every `await` is a preemption point** — wire deps before consumers (publish-before-subscribe), no `await` inside atomic blocks.
- **Log level = frequency + audience, not importance** (`LOG_LEVEL=INFO` in prod → INFO+ prints). DEBUG = hot-path / per-iteration (per-bar, per-tick, per-cascade, HTTP bodies); INFO = one-shot lifecycle (startup/shutdown/connect, index creation) + per-trade business events (order/position fills) — must be low-frequency AND bounded; WARNING = recoverable/degraded; ERROR = failed op (+ `exc_info` for exceptions). **Never log unbounded payloads above DEBUG** (HTTP request/response bodies, full market-data arrays, `model_dump()` of large models) — DEBUG + truncate only. A per-bar/per-tick/per-request event at INFO scales with market activity → floods prod.

## Reference docs (discover detail here)

- Architecture, layers, DI providers, request flows, "Where does X live", real-time streaming, strategy lifecycle → `docs/system-architecture.md`
- **Naming convention (suffix theo layer)**, comment policy, route/service/repo conventions, async-suspension patterns, schema, testing, perf → `docs/code-standards.md` (Section "Class Naming by Layer" + "Naming Principles & Exemptions")
- Run / test / canonical routes / remote-DB dev modes → `README.md`
