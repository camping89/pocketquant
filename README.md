# PocketQuant

Algorithmic trading platform. It syncs market data from Binance (no auth) and Exness (signed requests), ingests live quotes and builds bars, runs single backtests, drives strategies and brokers, and serves a React chart UI.

## Prerequisites

`uv`, Docker, Node and `just`. Versions: `requires-python` in `pyproject.toml`, the Node image in `web/Dockerfile`. Every `just` recipe is in `justfile`.

## Run

```bash
cp ../pocketquant-config/local/all-local.env .env
just install
just up                      # local Mongo and Redis
just be                      # backend
just fe                      # vite dev UI, proxies /api to the backend
```

- API docs: `http://localhost:41921/api/v1/docs`.
- In `.env`, the ports in `MONGODB_URL` and `REDIS_URL` must match `MONGO_PORT` and `REDIS_PORT`. Compose publishes those ports.
- Every local profile sets `APP_ROLES=api`. The process serves routes and backtests, takes no lease, and runs no scheduled job or quote feed.

### Against the prod VPS DB

`remote-db.env` points the app at prod Mongo and prod Redis through `just tunnel`. It keeps `APP_ROLES=api`, so prod's own worker and trader keep writing bars and live quotes. The local chart reads them from prod.

```bash
just tunnel                  # own terminal: forwards prod Mongo and Redis to localhost
cp .env .env.local.bak && cp ../pocketquant-config/local/remote-db.env .env
just be                      # no `just up`
just fe
cp .env.local.bak .env       # restore when done
```

- Every write route still writes to prod Mongo. That covers backtests, sync and repair routes, tracked symbols and subscriptions. Deleting a tracked symbol here deletes its prod data.
- Never add `worker` or `trader` to `APP_ROLES` here. Their leases live in prod Mongo, so this process would take over from prod when prod's lease lapses.
- Never run `pytest` on this `.env`. The prod guard in `tests/conftest.py` matches the VPS IP only, so it does not see the tunnel URL.

Two variants:

- **Local Redis:** `remote-db-local-redis.env` uses prod Mongo through the tunnel and keeps this process's Redis writes, such as cached OHLCV reads, local. The prod Mongo warnings above still apply. The chart shows no in-progress bar, because nothing writes live keys to local Redis. Start Redis before the backend:
  ```bash
  cp ../pocketquant-config/local/remote-db-local-redis.env .env
  just redis                 # local Redis only, not `just up`
  just be
  ```
- **Bar-building on a local DB:** use `all-local.env` and set `APP_ROLES=api,worker` in `.env`. The worker runs the scheduled sync and cascade jobs against your own Mongo. Add `trader` for the quote feed and strategies.
  ```bash
  cp ../pocketquant-config/local/all-local.env .env    # then edit APP_ROLES
  just up && just be
  ```

### Docker (built UI)

No local recipe serves the built UI. The `web` image (`web/Dockerfile`, nginx) runs only in the prod stack, `deploy/compose.prod.yml`. Locally, use `just fe`.

## Smoke Test

The UI needs at least one synced symbol and interval.

```bash
curl -X POST :41921/api/v1/market-data/sync -H 'Content-Type: application/json' \
  -d '{"symbol":"BTCUSDT:BINANCE","interval":"1d","n_bars":200,"source":"rest_backfill"}'
curl ':41921/api/v1/market-data/sync-status/BTCUSDT%3ABINANCE?interval=1d'   # bar_count > 0
curl ':41921/api/v1/market-data/ohlcv/BTCUSDT%3ABINANCE/1d?limit=20'        # non-empty data
```

Then open `http://localhost:5173`, load `BTCUSDT:BINANCE`, run a backtest, and check that markers and overlays render.

## Tests & Gates

Integration tests use testcontainers, so Docker must be running.

```bash
just test                    # pytest
just test-tz                 # pytest under three host timezones
uv run ruff check src        # lint (also every touched file)
uv run pyright src           # types (also every touched file)
uv run lint-imports          # import-linter contracts in pyproject.toml
uv run python scripts/code_metrics.py --ratchet   # code metric ratchet, ceiling in pyproject.toml
```

Manual API: Bruno [`tests/http`](./tests/http) and curl [`tests/manual/api-test.http`](./tests/manual/api-test.http).

Shutdown: `Ctrl+C` the servers, then `just down`. `just reset` also drops the volumes.

## Docs

[Governance](./docs/governance/) · [Architecture](./docs/system-architecture.md) · [Code standards](./docs/code-standards.md) · [Deployment](./docs/deployment.md)

## License

MIT
