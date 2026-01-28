# Production Deployment Guide

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

# Start services
just start
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
ExecStart=/opt/pocketquant/.venv/bin/python -m src.main
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

## Health Checks

```bash
# API health
curl http://localhost:$API_PORT/health

# Container status
docker compose -f docker/compose.yml ps
```
