# Bug backlog — context for separate brainstorm sessions

**Date scouted:** 2026-05-29
**Source:** scout-first pass during brainstorm session `/brainstorm braisntorm cho bug tiếp theo`
**Status:** Both bugs YAGNI-confirmed by scout — bring this doc into each session as anchor context

---

## Bug A — `Bar.tick_count` semantic inconsistency across data sources

### Symptom + doc reference
Documented in `docs/archive/migration-doubts-and-notes.md` (deferred 2026-05-07, still open 2026-05-25).

`bars` collection contains 3 different `tick_count` shapes:

| Source | `tick_count` written | Where (file:line) |
|---|---|---|
| TV historical fetch | `0` (default, never set) | `tradingview_client.py:138-150` |
| Live tick aggregation | `N` = ticks ingested per bar | `bar_builder.py:82` (`+= 1` per quote tick) |
| Binance backfill (one-off, 2026-05-07) | `N` = trades from kline index 8 | `scripts/backfill_1m_from_binance.py` |
| Binance live | `int(kline[8])` (same as backfill semantic) | `binance_mappers.py:90` |

### Discontinuity
Data shifts semantic around 2026-04-30 — that's when source mix changed in the bars collection.

### Scout findings — what production actually reads `tick_count`

| Reader | What it does | Real impact today |
|---|---|---|
| `Bar.is_complete` property (entities.py:56-57: `tick_count > 0`) | Dead code? Grep finds NO production caller. Only `BarBuilder.is_complete(current_time)` (different method, time-based) is used in `bar_app_service.py:103`. | None. Property is theoretical bug only. |
| `bar_app_service.py:144,161` — emits `BarCompletedEvent.tick_count` | Forwards to event bus — `OnBarCompleted` strategy callbacks see it | Currently unused by any strategy code (verify with `grep`) |
| `bar_app_service.py:257` — sets `tick_count: 0` in Redis when seeding from cascade | Initializes in-progress bar | Internal accounting |
| `stream_bars/route.py:52` — returns `tick_count` in SSE payload | Frontend SSE consumer | **UNKNOWN** — depends on `pocketquant-web` reading it. CHECK NEEDED. |
| `quote_dto.py:90` — `QuoteTick.tick_count` field | API DTO | Returned to frontend |
| `bar_repository.py:18,137` — persists to Mongo | Storage | Storage only |

**The actual blast radius is ≤2 SSE consumers in `pocketquant-web`.** Backend code does not branch on tick_count.

### Brainstorm session anchor — minimal questions to answer

1. Does `pocketquant-web` render `tick_count` to users? (grep the SPA repo)
2. If yes — is the value shown as "N ticks this bar" (display label) or used in conditional logic (e.g. "stale bar" badge)?
3. How many docs in prod `bars` have `tick_count == 0` post-2026-04-30? (`db.bars.countDocuments({tick_count: 0, datetime: {$gte: ISODate("2026-04-30")}})`)
4. Pick semantic:
   - Option A: `tick_count` = "trade/tick events" (unify on Binance kline[8] semantic). Backfill TV-historical rows with `null` or recompute from somewhere.
   - Option B: split into `tick_count` (in-flight ticks; cleared on bar close) + `trade_count` (frozen at bar close from provider). Migrate writers, leave readers on whichever they want.
   - Option C: deprecate `tick_count`, replace with `is_in_progress` boolean. Push completeness signal to its own field.
5. Migration: online ($set on read?), one-off script (mongo aggregation), or both?

### Out of scope for that brainstorm
- Other audit fields (`updated_at`, `source`) — those work fine.
- Backfill script archaeology — file already shipped; don't re-litigate.

### Files relevant to that brainstorm
- `packages/pocketquant-core/src/pocketquant/core/domain/bar/entities.py:35-96`
- `packages/pocketquant-core/src/pocketquant/core/domain/bar/services/bar_builder.py:59,82,91,114`
- `packages/pocketquant-core/src/pocketquant/core/infrastructure/binance/binance_mappers.py:90`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/bar_app_service.py:103,144,161,257`
- `packages/pocketquant-api/src/pocketquant/api/market_data/handlers/ohlcv/stream_bars/route.py:32,52`
- `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/quote_dto.py:90`
- `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py:18,137`
- `docs/archive/migration-doubts-and-notes.md` (entry: tick_count)

---

## Bug B — Strategy YAML path resolution is CWD-relative

### Symptom + doc reference
Documented in `docs/archive/migration-doubts-and-notes.md`:
> Strategy YAML path resolution uses CWD-relative — may need project-root resolution for Docker/production.

### Scout findings — what actually loads strategies today

Two layers:

1. **YAML loader** (`packages/pocketquant-trading/src/pocketquant/trading/app_services/yaml_strategy_loader.py`):
   - `StrategyLoader.load(path: Path) -> StrategyConfig` (line 19-82)
   - `StrategyLoader.load_all(directory: Path) -> list[StrategyConfig]` (line 84-128) — only test fixtures use it
   - Takes whatever `Path` the caller hands in. No internal CWD coupling. The "CWD-relative" risk is in the *caller*.

2. **Callers of `StrategyLoader.load`**:
   - `handlers/strategy/load/route.py:21-30` — POST `/strategies/load` admin endpoint. `body.path` from request → `Path(body.path)` → loader. Caller-supplied path; risk lives in whoever calls this endpoint.
   - `handlers/strategy/load/handler.py:21` — same path, command-side.
   - **NO callsite in `main.py` lifespan.** Lifespan rehydrates from Mongo (`rehydrate_strategies_from_subscriptions`) using `STRATEGY_REGISTRY` for class lookup, not YAML.

### Brutal-honest blast radius
- Prod only breaks if:
  - Someone calls `POST /strategies/load` with relative path.
  - Container's CWD differs from where the YAML actually lives.
- Docker `WORKDIR /app` is fixed. If YAMLs ship inside the image at known paths, *absolute* paths from the API caller work fine. *Relative* paths only fail if the caller doesn't know where CWD is — usually self-inflicted.
- **No evidence of prod failure.** Doc says "may need" — speculative.

### Brainstorm session anchor — minimal questions to answer

1. Where do strategy YAMLs actually live in prod? Inside the API image (`/app/strategies/*.yaml`)? In `pocketquant-config/` (mounted via volume)? Or are there none right now (everything is in `STRATEGY_REGISTRY` code)?
2. Who is supposed to call `POST /strategies/load` in production? (devs? admin UI? bootstrap script?) — if no one, the bug doesn't exist; delete the endpoint.
3. If the endpoint stays, pick resolution policy:
   - Option A: require absolute path; reject relative with 400.
   - Option B: resolve relative to a fixed root (env var `POCKETQUANT_STRATEGIES_DIR` or constant `/app/strategies/`).
   - Option C: use `pocketquant-config/strategies/` mounted volume by convention.
4. If `load_all` ever gets a non-test use case → revisit then.

### Out of scope for that brainstorm
- Refactoring `STRATEGY_REGISTRY` (code-based template registry) — that's a separate concern.
- Subscriptions rehydration from Mongo — already works, don't touch.

### Files relevant to that brainstorm
- `packages/pocketquant-trading/src/pocketquant/trading/app_services/yaml_strategy_loader.py` (full file)
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/route.py:21-30`
- `packages/pocketquant-trading/src/pocketquant/trading/handlers/strategy/load/handler.py:21`
- `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` — `rehydrate_strategies_from_subscriptions` (line 267-312) for context on why lifespan no longer touches YAML
- `docs/archive/migration-doubts-and-notes.md` (entry: YAML path)
- `deploy/Dockerfile` (check WORKDIR + COPY of any strategies/ dir)

---

## Priority recommendation (brutal-honest)

**Neither is a "ship-blocker bug."** Both are documented future-state concerns.

| | Bug A (tick_count) | Bug B (YAML path) |
|---|---|---|
| Production impact today | None proven (UI dependency unknown) | None proven (endpoint may be unused) |
| Data already polluted | Yes (3 sources mixed since 2026-04-30) | No |
| Effort if real | Medium (data migration) | Small (caller-side fix) |
| Recommended trigger | First UI feature that branches on `tick_count` | First request that fails with relative path |

**Suggested order if you do brainstorm:**
1. Bug B first — smaller, faster, can be closed cleanly (or even "deleted endpoint" outcome).
2. Bug A second — gather UI consumer data before deciding semantic.

---

## Open questions (carry into separate brainstorm sessions)

1. Does `pocketquant-web` render or branch on `tick_count`? (Bug A)
2. How many post-2026-04-30 bars have `tick_count == 0`? (Bug A)
3. Who calls `POST /strategies/load` in production today? Anyone? (Bug B)
4. Are there YAML files shipped in the Docker image? (Bug B)
