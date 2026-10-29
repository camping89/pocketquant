# PocketQuant

Algorithmic trading platform: market-data sync from Binance (REST/WS, no auth) and Exness (signed REST/WS market data and quotes for CFDs), live quote ingestion + bar aggregation, single-run backtesting, strategy/broker orchestration, and a React chart UI.

One Python package (`pocketquant`) with import-linter-enforced subpackage boundaries + a separate Vite SPA.

## Architecture

```text
src/pocketquant/
├── core/       # domain, ports/DTOs, entities + ALL concrete adapters (DB, cache, repos, brokers, binance, exness, scheduler)
├── engine/     # framework-free orchestration, 5 feature areas: strategy/ execution/ market_data/ backtest/ live/
└── app/        # FastAPI backend: routes, scheduler, WS feed, reconcile loop, backtest tasks
web/            # React 19 + Vite chart UI
```

Dependency contracts (import-linter): `core ◁ engine ◁ app`, `web → app` (HTTP only). Backtest and live are two drivers on one shared engine.

Backend is a **single process** (`pocketquant.app.main`, `:41921`) — one DI container wires the entire runtime and every route.

> **Single worker only.** Scheduler, WS feed, and broker are in-process singletons. `--workers N` duplicates the reconcile loop and live broker connection.

## Prerequisites

Python 3.14+ · `uv` · Docker Compose · Node 22+ · `just` (optional). Cross-platform; `just` auto-selects the venv Python per-OS.

## Run

```bash
cp ../pocketquant-config/local/all-local.env .env
just install                 # uv sync
just up                      # mongo + redis
just be                      # backend + API → :41921
just fe                      # vite dev UI → :5173 (proxies /api → :41921)
```

- API docs: `:41921/api/v1/docs` · OpenAPI: `/api/v1/openapi.json` · Health: `/health`
- `.env` sanity: `MONGODB_URL`/`REDIS_URL` hosts+ports must match `MONGO_PORT`/`REDIS_PORT`.
- Fast route iteration: `ENABLE_JOBS=false just be` skips the trading runtime so `--reload` stays light.
- Market-data routing has no env knob: a composite symbol's suffix names the data provider
  that serves its bars (`BTCUSDT:BINANCE` → `binance`, `XAUUSD:EXNESS` → `exness`).
- `TZ` must be `UTC`. The app refuses to start on any other process zone, because bars, cron
  triggers and session calendars are UTC instants.

### Against the prod VPS DB

`remote-db.env` ships with `ENABLE_JOBS=false` — **scheduler + reconcile loop off**. The live WS feed still runs (it powers the realtime chart) but writes only ephemeral quote / in-progress-bar keys to Redis; the sole Mongo `bars` writer is the gated `sync_1m` + cascade cron, so **local never persists bars to prod Mongo**. Closed candles on the chart are read from prod Mongo, kept fresh by prod's own cron.

```bash
cp .env .env.local.bak && cp ../pocketquant-config/local/remote-db.env .env
just be                      # backend :41921 — no `just up`, DB/Redis are remote
just fe                      # vite :5173 — realtime chart streams from the local feed
cp .env.local.bak .env       # restore when done
```

> **Backtests persist to prod** (`backtest_runs`, `backtest_orders`, `backtest_trades`). Never run `pytest` on this `.env` — `conftest.py` refuses when `MONGODB_URL`/`REDIS_URL` point at the prod host.

The local feed writes the same `quote:latest` / `bar:current` keys prod writes, so it shares prod's ephemeral Redis state and opens a second Binance WS. Two variants avoid that:

- **Isolated live state** — use `remote-db-local-redis.env` (`MONGODB_URL` → prod for history + closed bars, `REDIS_URL` → local so the feed's in-progress bar/quote stay separate). Redis is a hard startup dependency, so bring it up **before** `just be` or the app crashes on boot:
  ```bash
  cp ../pocketquant-config/local/remote-db-local-redis.env .env
  just redis     # ONLY local Redis — not `just up` (that also starts an unused local mongo)
  just be
  ```
- **Test bar-building on a local DB** — run fully local with jobs on, so `sync_1m` + cascade write bars to your own Mongo:
  ```bash
  cp ../pocketquant-config/local/all-local.env .env   # then set ENABLE_JOBS=true
  just up && just be                                   # sync_1m + cascade → local Mongo
  ```

### Docker (built UI)

```bash
cd web && npm run build      # → web/dist
just up                      # nginx serves dist, proxies /api → app, SPA fallback → index.html
```

Open `http://localhost/`.

## Smoke Test

The UI needs at least one synced symbol/interval.

```bash
curl -X POST :41921/api/v1/market-data/sync -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT:BINANCE","interval":"1d","n_bars":200,"source":"rest_backfill"}'
curl ':41921/api/v1/market-data/sync-status/BTCUSDT%3ABINANCE?interval=1d'   # → bar_count > 0
curl ':41921/api/v1/market-data/ohlcv/BTCUSDT%3ABINANCE/1d?limit=20'        # → non-empty data
```

Then open `:5173`, load `BTCUSDT:BINANCE`, run a backtest, and check that markers and overlays render.

Strategies: `GET /api/v1/strategies`, registered in `STRATEGY_REGISTRY` (`src/pocketquant/core/domain/strategy/services/__init__.py`).

## Tests & Gates

```bash
just test                    # pytest
uv run ruff check src        # lint (also every touched file)
uv run pyright src           # types (also every touched file)
uv run lint-imports          # 8 import-linter contracts
uv run python scripts/code_metrics.py --ratchet   # code metric ratchet (ceiling in pyproject.toml)
```

Manual API: Bruno [`tests/http`](./tests/http) · curl [`tests/manual/api-test.http`](./tests/manual/api-test.http).

Shutdown: `Ctrl+C` the servers, then `just down` (`just reset` also drops volumes).

## Docs

[Index](./docs/README.md) · [Architecture](./docs/system-architecture.md) · [Code standards](./docs/code-standards.md) · [Deployment](./docs/deployment.md)

## License

MIT
