# PocketQuant

Algorithmic trading platform: Binance market-data sync (REST/WS, no auth), live quote ingestion + bar aggregation, single-run backtesting, strategy/broker orchestration, and a React chart UI.

One Python package (`pocketquant`) with import-linter-enforced subpackage boundaries + a separate Vite SPA.

## Architecture

```text
src/pocketquant/
├── core/       # domain, ports/DTOs, entities + ALL concrete adapters (DB, cache, repos, brokers, binance, scheduler, http)
├── engine/     # strategy/order/position/risk engine + feature services
├── backtest/   # backtest engine + single-run orchestration (sandbox, replay, collector)
└── app/        # FastAPI backend: routes, SPA serving, scheduler, WS feed, reconcile loop, backtest tasks
web/            # React 19 + Vite chart UI
```

Dependency contracts (import-linter): `core ◁ engine ◁ backtest ◁ app`, `web → app` (HTTP only).

Backend is a **single process** (`pocketquant.app.main`, `:41921`) — one DI container wires the entire runtime and every route.

> **Single worker only.** Scheduler, WS feed, and broker are in-process singletons. `--workers N` duplicates the reconcile loop and live broker connection.

## Prerequisites

Python 3.14+ · `uv` · Docker Compose · Node 22+ · `just` (optional). Cross-platform; `just` auto-selects the venv Python per-OS.

## Run

```bash
cp ../pocketquant-config/local/all-local.env .env
just install                 # uv sync
just up                      # mongo + redis
just be                      # backend + API + SPA → :41921
just fe                      # vite dev UI → :5173 (proxies /api → :41921)
```

- API docs: `:41921/api/v1/docs` · OpenAPI: `/api/v1/openapi.json` · Health: `/health`
- `.env` sanity: `MONGODB_URL`/`REDIS_URL` hosts+ports must match `MONGO_PORT`/`REDIS_PORT`.
- Fast route iteration: `ENABLE_JOBS=false just be` skips the trading runtime so `--reload` stays light.

### Against the prod VPS DB

`remote-db.env` ships with `ENABLE_JOBS=false` (scheduler + reconcile off; API/SPA/backtest only).

```bash
cp .env .env.local.bak && cp ../pocketquant-config/local/remote-db.env .env
just be                      # no `just up` — DB/Redis are remote
cp .env.local.bak .env       # restore when done
```

> **Backtests persist to prod** (`backtest_runs`, `backtest_orders`, `backtest_trades`). Never run `pytest` on this `.env` — `conftest.py` refuses when `MONGODB_URL`/`REDIS_URL` point at the prod host.

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
  -d '{"symbol":"BTCUSDT","exchange":"BINANCE","interval":"1d","n_bars":200}'
curl ':41921/api/v1/market-data/sync-status/BTCUSDT%3ABINANCE?interval=1d'   # → bar_count > 0
curl ':41921/api/v1/market-data/ohlcv/BTCUSDT%3ABINANCE/1d?limit=20'        # → non-empty data
```

Then open `:5173`, load `BINANCE:BTCUSDT`, run a backtest strategy, confirm markers/overlays render.

Strategies exposed by the API:

- `hitnrun2` — 1m breakdown/breakup, capped technical SL/TP (entry 4h, SL 8h @ 1% account cap, TP 1h @ 2% account min)
- `engulfing` — full-candle engulfing (body+range over prior) with rejection-wick filter; SL at pattern extreme, TP = max(RR, key level)

## Tests & Gates

```bash
just test                    # pytest
uv run ruff check .          # lint
uv run pyright               # types
uv run lint-imports          # 7 import-linter contracts
```

Manual API: Bruno [`tests/http`](./tests/http) · curl [`tests/manual/api-test.http`](./tests/manual/api-test.http).

Shutdown: `Ctrl+C` the servers, then `just down` (`just reset` also drops volumes).

## Docs

[Index](./docs/README.md) · [Architecture](./docs/system-architecture.md) · [Deployment](./docs/deployment.md)

## License

MIT
