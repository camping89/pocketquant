# PocketQuant

PocketQuant is an algorithmic trading monorepo with:

- historical market-data sync from Binance public REST/WS (no auth required)
- live quote ingestion via Binance @aggTrade and bar aggregation
- backtesting and optimization APIs
- strategy orchestration and broker abstractions
- a React/Vite chart UI for inspecting synced data and backtest overlays

## Monorepo Layout

Backend packages are managed with a `uv` workspace. The frontend is a separate npm app.

```text
packages/
├── pocketquant-core/       # Domain, common utilities, persistence, providers
├── pocketquant-backtest/   # Backtest handlers and persistence
├── pocketquant-trading/    # Strategy, order, position, broker workflows
├── pocketquant-api/        # FastAPI app, DI container, route composition
└── pocketquant-web/        # React 19 + Vite chart UI
```

Dependency direction:

```text
core ← {backtest, trading} ← api
web → api
```

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
just be
```

Backend URLs:

- API docs: `http://localhost:41920/api/v1/docs`
- OpenAPI JSON: `http://localhost:41920/api/v1/openapi.json`
- Health check: `http://localhost:41920/health`

If services fail to start, verify that `.env` is internally consistent:

- `MONGODB_URL` must point to the same host/port exposed by `MONGO_PORT`
- `REDIS_URL` must point to the same host/port exposed by `REDIS_PORT`

## Frontend Quick Start

Run the API first, then start the Vite app in a second terminal:

```bash
cd packages/pocketquant-web
npm ci
npm run dev
```

Frontend URL:

- Vite dev UI: `http://localhost:5173` by default

Vite proxies `/api/*` to `http://localhost:41920`, so the browser app talks to the local FastAPI server automatically. If port `5173` is already in use, Vite will choose the next free port.

## Serve The Built UI Through FastAPI

Build the frontend once:

```bash
cd packages/pocketquant-web
npm run build
```

Then start the API and open:

- `http://localhost:41920/`

FastAPI serves `packages/pocketquant-web/dist` when it exists.

## Market Data

**Crypto market data:** Binance public REST/WS (@aggTrade). No authentication required.

## Sync Smoke Test

The UI only becomes useful after at least one symbol/interval has been synced.

```bash
curl -X POST http://localhost:41920/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","exchange":"BINANCE","interval":"1d","n_bars":200}'

curl "http://localhost:41920/api/v1/market-data/sync-status/BINANCE/BTCUSDT?interval=1d"

curl "http://localhost:41920/api/v1/market-data/ohlcv/BINANCE/BTCUSDT?interval=1d&limit=20"
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
5. Toggle indicators and confirm overlays redraw
6. Pick a strategy and confirm a backtest request runs

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
cd packages/pocketquant-web
npm run lint
npm run build
```

Manual API testing:

- Bruno collection: [`tests/http`](./tests/http)
- Curl walkthrough: [`tests/manual/api-test.http`](./tests/manual/api-test.http)

## Docs

- [Run And Test Guide](./docs/run-and-test-guide.md)
- [Docs Index](./docs/README.md)
- [System Architecture](./docs/system-architecture.md)
- [Deployment](./docs/deployment.md)

## License

MIT
