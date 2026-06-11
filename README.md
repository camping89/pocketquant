# PocketQuant

PocketQuant is an algorithmic trading monorepo with:

- historical market-data sync from Binance public REST/WS (no auth required)
- live quote ingestion via Binance @aggTrade and bar aggregation
- backtesting and optimization APIs
- strategy orchestration and broker abstractions
- a React/Vite chart UI for inspecting synced data and backtest overlays

## Repo Layout

One Python package (`pocketquant`) with subpackage boundaries enforced by import-linter. The frontend is a separate npm app.

```text
src/pocketquant/
├── core/       # Domain, concepts, common utilities, config, ports + DTOs, persisted entities, AND concrete adapters: Database, Cache, repositories, PaperBroker, OKXBroker, binance, scheduler, http client
├── engine/     # Shared strategy/order/position/risk engine + strategy/orders-positions feature services
├── backtest/   # Backtest engine, optimization, backtest-run orchestration
└── app/        # FastAPI single backend: all API routes, SPA serving, scheduler, WS feed, strategy lifecycle, reconcile loop, backtest worker
web/            # React 19 + Vite chart UI
```

Dependency direction (import-linter contracts):

```text
core ◁ engine ◁ backtest ◁ app
web → app (HTTP only)
```

Note: the backend is a single process (`pocketquant.app.main`) listening on `:41921`. One DI container wires the full runtime and every API route.

## Prerequisites

- Python 3.14+
- `uv`
- Docker + Docker Compose
- Node.js 22+ and npm
- `just` is optional but recommended

## Backend Quick Start

```bash
cp ../pocketquant-config/local/all-local.env .env
just install
just up
just be      # backend (full runtime + API + SPA) on :41921
```

Backend URLs:

- API docs: `http://localhost:41921/api/v1/docs`
- OpenAPI JSON: `http://localhost:41921/api/v1/openapi.json`
- Health check: `http://localhost:41921/health`

If services fail to start, verify that `.env` is internally consistent:

- `MONGODB_URL` must point to the same host/port exposed by `MONGO_PORT`
- `REDIS_URL` must point to the same host/port exposed by `REDIS_PORT`

## Frontend Quick Start

Run the API first, then start the Vite app in a second terminal:

```bash
cd web
npm ci
npm run dev
```

Frontend URL:

- Vite dev UI: `http://localhost:5173` by default

Vite proxies `/api/*` to `http://localhost:41921` (the backend), so the browser app talks to the API automatically. If port `5173` is already in use, Vite will choose the next free port.

## Serve The Built UI Through Docker

Build the frontend:

```bash
cd web
npm run build
```

Run the full Docker stack:

```bash
just up  # starts mongo + redis (local infra; backend runs via `just be`)
```

Open: `http://localhost/`

In production the web container's nginx serves `web/dist` and proxies `/api/*` to the app container. Refreshing a client-side route returns `index.html` (SPA fallback).

## Market Data

**Crypto market data:** Binance public REST/WS (@aggTrade). No authentication required.

## Sync Smoke Test

The UI only becomes useful after at least one symbol/interval has been synced.

```bash
curl -X POST http://localhost:41921/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","exchange":"BINANCE","interval":"1d","n_bars":200}'

curl "http://localhost:41921/api/v1/market-data/sync-status/BTCUSDT%3ABINANCE?interval=1d"

curl "http://localhost:41921/api/v1/market-data/ohlcv/BTCUSDT%3ABINANCE/1d?limit=20"
```

What to expect:

- the sync response returns `status: "completed"`
- sync status shows `bar_count > 0`
- OHLCV returns non-empty `data`

## UI Smoke Test

After syncing `BINANCE:BTCUSDT`:

1. Open `http://localhost:5173`
2. Confirm the chart loads candles instead of the error overlay
3. Open the symbol picker and verify synced symbols are listed
4. Verify interval buttons appear for synced intervals only
5. Switch intervals and confirm the chart reloads
6. Toggle indicators and confirm overlays redraw
7. Pick the `hitnrun2` strategy and confirm a backtest request runs
8. Confirm backtest markers / position overlays appear on the chart

If the UI is empty:

- check browser devtools for failed `/api/*` calls
- confirm the backend is still running
- confirm sync status exists for the selected symbol and interval

Current backtest strategy IDs exposed by the API:

- `hitnrun2` — 1m breakdown/breakup with capped technical SL/TP (entry 4h window, SL 8h technical with 1% account cap, TP 1h technical with 2% account minimum)

## Test Commands

Backend:

```bash
just test
just test-pkg core
just lint
just types
```

Frontend:

```bash
cd web
npm run lint
npm run build
```

Manual API testing:

- Bruno collection: [`tests/http`](./tests/http)
- Curl walkthrough: [`tests/manual/api-test.http`](./tests/manual/api-test.http)

## Shutdown

Stop the Vite and API servers with `Ctrl+C`, then stop local infrastructure:

```bash
just down
```

## Docs

- [Docs Index](./docs/README.md)
- [System Architecture](./docs/system-architecture.md)
- [Deployment](./docs/deployment.md)

## License

MIT
