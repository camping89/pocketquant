# System Relationship Map

Whole-system **diagrams**: how the two repos, CI/CD, image registry, VPS runtime, external services, and clients connect. This is the zoomed-out visual companion to [System Architecture](./system-architecture.md) (which holds the prose: two-repo secret boundary, external-service table, local-dev modes, concern-map) and [Deployment](./deployment.md) (the ops runbook).

## 1. Repo Secret Boundary

```
┌─────────────────────────┐         ┌─────────────────────────────┐
│       pocketquant        │  reads  │     pocketquant-config       │
│  (code, no secrets)      │ ──────▶ │  (secrets: .env, ssh, creds) │
│  CI secret:              │ via     │  read-only deploy key        │
│  POCKETQUANT_CONFIG_     │ deploy  │                              │
│   DEPLOY_KEY ────────────┼─────────┤▶ grants clone access         │
└─────────────────────────┘  key    └─────────────────────────────┘
```

## 2. End-to-End Relationship (build → ship → run)

```
   Developer
      │ git push origin develop|master
      ▼
┌──────────────────────────────────────────────────────────────────────┐
│ GitHub Actions  (.github/workflows/cicd.yml)                           │
│                                                                        │
│   tests ─┐                                                             │
│          ├─▶ build-api ─┐                                              │
│          └─▶ build-web ─┤  (parallel docker build + push)             │
│                         ├─▶ cleanup-tags  (prune old SHA tags)        │
│                         └─▶ deploy  (needs both builds green)         │
│                              │                                         │
│        get-vps-config ───────┤ clones pocketquant-config via deploy key│
│        (composite action)    │  → ssh_key, host, env_content,         │
│                              │     docker-hub creds                    │
└──────────────┬───────────────┴─────────────────────────────┬─────────┘
               │ push images                                   │ rsync + ssh
               ▼                                               ▼
        ┌──────────────┐                          ┌────────────────────────┐
        │  Docker Hub  │   pull :latest/:sha       │      Vultr VPS         │
        │ pocketquant  │ ◀──────────────────────── │  /opt/pocketquant/     │
        │ pocketquant- │                           │  docker compose up     │
        │     web      │                           │  (compose.prod.yml)    │
        └──────────────┘                           └───────────┬────────────┘
                                                               │
                                                   5 containers on one bridge net
                                                               ▼
                          ┌──────────┬──────────┬──────────┬──────────┬───────────┐
                          │   web    │   app    │ mongodb  │  redis   │ portainer │
                          │  :80 →   │ :41920   │ :27017   │  :6379   │  :9000    │
                          │  /api/*  │ FastAPI  │  bars,   │ quote,   │  docker   │
                          │  proxy → │ (uvicorn)│ orders,  │ bar,     │  admin UI │
                          │   app    │          │ positions│ idempot, │           │
                          └────┬─────┘          │ ...      │ rate     │           │
                               │                └──────────┴──────────┴───────────┘
                               │ public entry (WEB_PORT)
                               ▼
                          ┌──────────┐
                          │  Trader  │  browser → SPA → /api/* → app
                          │ (client) │
                          └──────────┘
```

App reaches DBs by **service name** inside the compose network (`mongodb:27017`, `redis:6379`); a laptop reaches the same DBs by **VPS IP + published host port**. See [deployment.md](./deployment.md) for the runtime container table and port map.

## 3. Config Flow — single source of truth for prod env

```
pocketquant-config/vps/default/.env   (edit here, git push)
        │
        │ CI/CD `get-vps-config` reads at deploy time
        ▼
GitHub Actions writes deploy/.env  → rsync → VPS:/opt/pocketquant/deploy/.env
        │
        │ compose.prod.yml: app service `env_file: .env`
        ▼
pocketquant-app container env  (MONGODB_URL=mongodb:27017, etc.)
```

Any manual `.env` edit on the VPS is **overwritten every deploy**. To change prod config: edit in `pocketquant-config`, push there, then push any commit to `pocketquant` (or `gh workflow run cicd.yml`).

## 4. MongoDB Collection ERD (read this like an RDBMS schema)

MongoDB has **no enforced foreign keys** — relationships below are *logical* joins the application performs. Two join keys carry the whole model:

- **`subscription_id`** — deterministic hash of `(strategy_code, symbol, interval)`. Links live trading records back to their subscription.
- composite **`symbol`** string (`BTCUSDT:BINANCE`) — the shared natural key across market-data + trading collections.

13 collections. Collection `_id` strategies + the per-collection reference table live in [system-architecture.md](./system-architecture.md) → "MongoDB Collections & Repository Access". Rendered PNG: [`visuals/collection-erd.png`](./visuals/collection-erd.png) (source: [`visuals/collection-erd.mmd`](./visuals/collection-erd.mmd)).

```mermaid
erDiagram
    SYMBOLS ||..o{ BARS : "symbol (ref data)"
    SYMBOLS ||..o{ SYNC_STATUS : "symbol"
    SYMBOLS ||..o{ TRACKED_SYMBOLS : "symbol"
    TRACKED_SYMBOLS ||..o{ BARS : "drives sync → writes"
    TRACKED_SYMBOLS ||..|| SYNC_STATUS : "sync progress per (symbol,interval)"

    SUBSCRIPTIONS ||--o{ ORDERS : "subscription_id"
    SUBSCRIPTIONS ||--o{ POSITIONS : "subscription_id"
    SUBSCRIPTIONS ||..o| BACKTEST_RUNS : "subscription_id (cached result)"
    SYMBOLS ||..o{ SUBSCRIPTIONS : "symbol"

    BACKTEST_RUNS ||--o{ BACKTEST_ORDERS : "run_id"
    BACKTEST_RUNS ||--o{ BACKTEST_TRADES : "run_id"

    SYMBOLS {
        uuid _id PK
        string symbol UK "BTCUSDT:BINANCE"
        string name
        string asset_type
        bool is_active
    }
    BARS {
        uuid _id PK
        string symbol FK "composite"
        enum interval
        datetime datetime "UK with symbol+interval"
        float open_high_low_close
        float volume
        string source
    }
    SYNC_STATUS {
        uuid _id PK
        string symbol "UK with interval"
        string interval
        string status
        int bar_count
        datetime last_bar_at
    }
    TRACKED_SYMBOLS {
        string symbol PK "composite = natural _id"
    }
    SUBSCRIPTIONS {
        string _id PK "hash(strategy_code|symbol|interval)"
        string strategy_code "→ in-code STRATEGY_REGISTRY"
        string symbol FK "composite"
        enum interval
        datetime created_at
    }
    ORDERS {
        string _id PK
        string subscription_id FK
        string symbol FK
        enum side
        enum order_type
        enum status
        float quantity
        float sl_price
        float tp_price
        string broker_order_id "→ OKX external"
    }
    POSITIONS {
        string _id PK
        string subscription_id FK
        string symbol FK
        enum side
        float entry_price
        float realized_pnl
        bool is_closed
    }
    BACKTEST_RUNS {
        string _id PK "run_id"
        string strategy_code
        string subscription_id "nullable, cache key"
        string status
        datetime started_at
    }
    BACKTEST_ORDERS {
        string _id PK "order_id"
        string run_id FK
        string strategy_code
        string symbol
        string status
    }
    BACKTEST_TRADES {
        string _id PK "trade_id"
        string run_id FK
        string strategy_code
        datetime entry_time
        float pnl
    }
    BACKTEST_OPTIMIZATION_RUNS {
        string _id PK
        string strategy_code
        datetime created_at
    }
    JOB_HISTORY {
        objectid _id PK
        string job_id
        string status
    }
    APSCHEDULER_JOBS {
        string _id PK "job name"
        datetime next_run_time "cross-process lock"
    }
```

### How to read the relationships

- **Live trading chain:** `subscriptions` is the hub. One subscription → many `orders` and many `positions` (both carry `subscription_id`). A subscription's *cached* latest backtest also lands in `backtest_runs` keyed by `subscription_id`.
- **Backtest chain (mirror of live):** one `backtest_runs` (`run_id`) → many `backtest_orders` + many `backtest_trades`. **Separate** collections from live `orders`/`positions` so backtests never touch production trading data.
- **Market-data chain:** `tracked_symbols` is the input list → cron sync jobs write `bars` and update `sync_status` per `(symbol, interval)`. `symbols` is the descriptive catalog all reference by composite string.
- **No physical joins:** everything resolved app-side by `subscription_id` or composite `symbol`. Orphan records are possible if a subscription is deleted (cleanup is explicit in repo methods like `delete_by_strategy_code`).
