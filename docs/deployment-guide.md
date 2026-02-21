# Production Deployment Guide

**Last Updated:** 2026-02-21 | **Version:** 1.0 | **Min Python:** 3.14+ | **Architecture:** DDD + CQRS + Clean Architecture

## Prerequisites

Same as development requirements:
- Python 3.14+
- Docker & Docker Compose
- [just](https://github.com/casey/just)
- [uv](https://docs.astral.sh/uv/)

## Ubuntu/Debian

```bash
# Python
sudo apt install python3.14

# Docker
sudo apt install docker.io docker-compose-v2
sudo usermod -aG docker $USER  # Add user to docker group (logout/login required)

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# just
sudo apt install just  # Or: cargo install just
```

## Deploy

```bash
# Clone and configure
git clone <repo> && cd pocketquant
cp .env.example .env
# Edit .env: set MONGODB_URL, REDIS_URL, API_PORT, etc.

# Install dependencies
just install

# Start infrastructure (MongoDB 27018 + Redis 6379)
just up

# Run app (separate terminal)
uvicorn src.main:app --host 0.0.0.0 --port 8765
```

## Running as Service (systemd)

Create `/etc/systemd/system/pocketquant.service`:

```ini
[Unit]
Description=PocketQuant Trading Platform
After=network.target docker.service

[Service]
Type=simple
User=pocketquant
WorkingDirectory=/opt/pocketquant
ExecStart=/opt/pocketquant/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pocketquant
sudo systemctl start pocketquant
```

## Environment Variables

See `.env.example` for all options. Key production settings:

| Variable | Production Value | Purpose |
|----------|------------------|---------|
| `ENVIRONMENT` | `production` | Enables production mode |
| `LOG_FORMAT` | `json` | Structured JSON logs for log aggregators |
| `LOG_LEVEL` | `info` | Reduce noise (use `debug` for troubleshooting) |
| `MONGODB_URL` | Your MongoDB URL | Database connection |
| `REDIS_URL` | Your Redis URL | Cache connection |
| `OKX_API_KEY` | Your API key | OKX live trading |
| `OKX_API_SECRET` | Your secret key | OKX live trading |
| `OKX_PASSPHRASE` | Your passphrase | OKX live trading |
| `TRADINGVIEW_USERNAME` | Optional | TradingView auth |
| `TRADINGVIEW_PASSWORD` | Optional | TradingView auth |

## OKX Setup

For live trading via OKX:

1. Create OKX account at https://www.okx.com/
2. Generate API credentials:
   - Log in → Account → API
   - Create new key with trading permissions
   - Save: API Key, Secret Key, Passphrase
3. Add to `.env`:
   ```env
   OKX_API_KEY=your_api_key
   OKX_SECRET_KEY=your_secret_key
   OKX_PASSPHRASE=your_passphrase
   ```
4. Set broker in strategy config (see below)

## Strategy Configuration

Create strategy YAML file (e.g., `strategies/ma_crossover.yaml`):

```yaml
name: ma_crossover
description: Simple MA crossover strategy
symbol: BTCUSDT
exchange: OKX
broker: okx  # or 'paper' for simulation
parameters:
  fast_period: 10
  slow_period: 20
  quantity: 0.1
risk:
  max_position_size: 1.0
  stop_loss_percent: 2.0
  take_profit_percent: 5.0
```

Load strategy via API:

```bash
curl -X POST http://localhost:8765/api/v1/strategies/load \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ma_crossover",
    "config_path": "strategies/ma_crossover.yaml"
  }'
```

Start strategy:

```bash
curl -X POST http://localhost:8765/api/v1/strategies/start \
  -H "Content-Type: application/json" \
  -d '{"strategy_name": "ma_crossover"}'
```

## Database Initialization

Initialize MongoDB collections on first startup:

```bash
# Collections auto-created on first write
# Optional: Pre-create with indexes for performance

# Market data indexes
db.ohlcv.createIndex({ "symbol": 1, "exchange": 1, "interval": 1, "timestamp": 1 }, { unique: true })
db.symbols.createIndex({ "code": 1, "exchange": 1 }, { unique: true })

# Trading indexes
db.orders.createIndex({ "order_id": 1 }, { unique: true })
db.positions.createIndex({ "symbol": 1, "exchange": 1 }, { unique: true })

# Backtesting indexes
db.backtest_results.createIndex({ "run_id": 1 }, { unique: true })
db.optimization_results.createIndex({ "optimization_id": 1 }, { unique: true })
```

## Troubleshooting

**OKX Connection Issues:**
- Check API credentials in .env
- Verify API key has trading permissions
- Check IP whitelist (OKX security)
- Watch logs: `docker logs pocketquant-app`

**Strategy Not Starting:**
- Check strategy YAML syntax
- Verify symbol/exchange exists
- Check broker configuration
- Review logs for errors

**MongoDB Connection Failed:**
- Verify MONGODB_URL is correct
- Check MongoDB is running: `docker ps`
- Try connecting manually: `mongosh $MONGODB_URL`

**Strategy Not Trading:**
- Verify market data is flowing (check quotes endpoint)
- Check risk limits aren't blocking orders
- Review strategy logs for signals
- Try backtest first to validate logic

## Health Checks

```bash
# API health
curl http://localhost:$API_PORT/health

# Container status
docker compose -f docker/compose.yml ps
```
