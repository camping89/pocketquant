# Run And Test Guide

This is the current local workflow for running PocketQuant, validating market-data sync, and smoke-testing the UI.

## 1. Install Dependencies

Backend:

```bash
cp ../pocketquant-config/local/.env .env
just install
```

Frontend:

```bash
cd packages/pocketquant-web
npm ci
```

## 2. Start Local Infrastructure

```bash
just up
```

Expected result: MongoDB + Redis containers up and healthy (check via `docker ps`).

If they fail to start, compare `.env` with Docker ports:

- `MONGODB_URL` must match `MONGO_PORT`
- `REDIS_URL` must match `REDIS_PORT`

## 3. Run The API

```bash
just dev
```

Sanity checks:

```bash
curl http://localhost:41920/health
curl http://localhost:41920/api/v1/backtest/strategies
curl http://localhost:41920/api/v1/docs -I
```

Expected:

- `/health` reports `healthy`
- `/backtest/strategies` returns `["hitnrun2"]`
- `/api/v1/docs` responds `200`

## 4. Run The UI

In a second terminal:

```bash
cd packages/pocketquant-web
npm run dev
```

Open:

- `http://localhost:5173` by default

The Vite app proxies `/api/*` to the backend on `:41920`. If `5173` is already occupied, Vite will move to the next free port.

## 5. Sync Data For UI Testing

The UI depends on completed sync records. Run at least one sync first.

```bash
curl -X POST http://localhost:41920/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","exchange":"BINANCE","interval":"1d","n_bars":200}'
```

Verify the result:

```bash
curl "http://localhost:41920/api/v1/market-data/sync-status/BINANCE/BTCUSDT?interval=1d"
curl "http://localhost:41920/api/v1/market-data/ohlcv/BINANCE/BTCUSDT?interval=1d&limit=20"
curl "http://localhost:41920/api/v1/market-data/symbols?exchange=BINANCE"
```

What counts as a passing sync test:

- the sync response ends with `status: "completed"`
- symbol sync status has `bar_count > 0`
- OHLCV returns bars
- symbols list includes `BTCUSDT`

## 6. UI Smoke Test Checklist

After the sync passes:

1. Open `http://localhost:5173`
2. Confirm the default chart renders candles
3. Open the symbol selector and confirm synced symbols are listed
4. Confirm at least one interval button appears for the selected symbol
5. Switch intervals and confirm the chart reloads
6. Toggle indicators and confirm overlays update
7. Open the strategy selector and choose `hitnrun2`
8. Confirm a backtest request runs and markers/position overlays appear on the chart

If the UI is empty:

- check browser devtools for failed `/api/*` calls
- confirm the backend is still running
- confirm sync status exists for the selected symbol and interval

## 7. Built UI Smoke Test

To verify the production-style UI path served by FastAPI:

```bash
cd packages/pocketquant-web
npm run build
```

With the API still running, open:

- `http://localhost:41920/`

Passing result:

- the SPA loads from FastAPI
- API requests still succeed
- refreshing a client-side route still returns `index.html`

## 8. Automated Checks

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

## 9. Bruno And Manual API Assets

Bruno collection:

- `tests/http/environments/local.bru`
- `tests/http/market-data/*`
- `tests/http/backtest/*`

Curl walkthrough:

- `tests/manual/api-test.http`

## 10. Shutdown

Stop the Vite server with `Ctrl+C`.

Stop the API with `Ctrl+C`.

Stop local infrastructure when done:

```bash
just down
```
