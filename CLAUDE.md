# CLAUDE.md — PocketQuant

One Python package `src/pocketquant/` (subpackages: core, engine, app) + one Vite SPA (`web/`). Architecture, layers, run/test commands live in `README.md` + `docs/` — this file holds only the gotchas an agent gets wrong without being told, plus the docs index.

## Credentials & VPS access

- Claude Code may freely read and use all creds in `../pocketquant-config/` (SSH key, prod `.env`, Mongo/Redis passwords) and SSH into the VPS. The VPS is disposable and temporary — no approval needed.
- One hard rule: **all creds live in `pocketquant-config`, never in this repo.** No secrets in code, tests, docs, or committed env files here.

## Rules that change decisions

- **All repositories in core** (`core.infra.persistence.repositories`) — zero repos in engine/app.
- **Routes** use `FromDishka[…CommandService/…QueryService]` + `DishkaRoute`, never `Depends()`. Service methods take scalars; a Pydantic model only for a real request body or a validated multi-field query. They return DTOs. A route may inject a repository or `Cache` directly when the handler adds no logic (no service needed).
- **fastapi only in app** — core/engine never import it (import-linter enforced, 8 contracts).
- **Single uvicorn worker only** — scheduler/WS feed/broker are in-process singletons; `--workers N` duplicates the reconcile loop + live broker connection.
- **Primary keys: UUIDv7 only** — never hash / natural key / ObjectId.
- **Every `await` is a preemption point** — wire deps before consumers (publish-before-subscribe), no `await` inside atomic blocks.
- **Log level = frequency + audience, not importance** (`LOG_LEVEL=INFO` in prod → INFO+ prints). DEBUG = hot-path / per-iteration (per-bar, per-tick, per-cascade, HTTP bodies); INFO = one-shot lifecycle (startup/shutdown/connect, index creation) + per-trade business events (order/position fills) — must be low-frequency AND bounded; WARNING = recoverable/degraded; ERROR = failed op (+ `exc_info` for exceptions). **Never log unbounded payloads above DEBUG** (HTTP request/response bodies, full market-data arrays, `model_dump()` of large models) — DEBUG + truncate only. A per-bar/per-tick/per-request event at INFO scales with market activity → floods prod.
- **Language: short, plain English only.** Docs, code comments, commit messages, log event names and plan text are English. No Vietnamese, no translated mirrors. Docs are AS-IS: one idea per sentence, no history, no praise. A doc over 800 lines is cut or split in the same change that pushes it over.
- **Code stays short enough for a human to own for the next three years.** KISS, minimal abstraction, no over-engineering: a person must be able to review and control AI-written code without cognitive overload. Limits a reviewer can count:
  - A flow reads in one file, three at most (plus leaf calls such as repositories and clients).
  - At most two hops from a route or job to the I/O call (route → service → adapter).
  - A new class, port, helper, parameter, flag or config key needs a second real caller today, not a possible one.
  - Delete dead code in the same change; never deprecate and keep.
  - Prefer one 40-line function a reader can follow over five 8-line ones.
  - When a change needs more code than the code it replaces, stop and ask.

## Reference docs (discover detail here)

- Design decisions, layers, DI providers, startup, strategy control plane, streaming, brokers → `docs/system-architecture.md`
- Where things live → `docs/codebase-summary.md`
- **Naming convention (suffix by layer)**, comment policy, route/service/repo conventions, async-suspension patterns, testing, quality gate + code metric ratchet → `docs/code-standards.md` (Section "Class Naming by Layer" + "Naming Principles & Exemptions")
- Run / test / canonical routes / remote-DB dev modes → `README.md`
