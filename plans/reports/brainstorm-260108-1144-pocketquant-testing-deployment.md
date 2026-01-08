# PocketQuant: Testing & Deployment Brainstorm

**Date:** 2026-01-08
**Status:** Agreed

## Problem Statement

PocketQuant has market data infrastructure ready (sync, quotes, aggregation) but needs:
1. Local validation before deployment
2. Production deployment to VPS
3. Core trading features (backtesting, strategies)

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| VPS Provider | Vultr Singapore | Low APAC latency, cost-effective |
| Instance Size | 4GB RAM ($24/mo) | Comfortable for MongoDB + Redis + App |
| Secrets Mgmt | Simple .env | Sufficient for single-server setup |
| SSL | Let's Encrypt + domain | Production-grade HTTPS |
| Deploy Method | Single docker-compose | All services in one file, simpler ops |
| Plan Structure | 3 separate plans | Clear separation of concerns |
| Execution Order | Test → Deploy → Features | Validate before investing in features |

## Plan Structure

### Plan A: Local Testing & Validation
**Priority:** 1 (First)
**Goal:** Ensure market data pipeline works end-to-end locally

**Scope:**
- Environment setup (venv, dependencies)
- Docker infra (MongoDB 7.0, Redis 7.2)
- Health check validation
- Historical data sync test (TradingView → MongoDB)
- Real-time quotes test (WebSocket)
- Data verification in MongoDB

**Success Criteria:**
- App starts without errors
- Can sync 5000 bars of AAPL daily data
- Real-time quotes flow and cache in Redis
- Data persists in MongoDB correctly

---

### Plan B: VPS Deployment (Vultr Singapore)
**Priority:** 2 (After local validation)
**Goal:** Production-ready deployment with SSL

**Scope:**
- Vultr 4GB instance provisioning
- Server hardening (SSH keys, UFW, fail2ban)
- Docker + Compose installation
- Production docker-compose with:
  - App container (Dockerfile)
  - MongoDB 7.0
  - Redis 7.2
  - Nginx reverse proxy
- Domain + Cloudflare DNS setup
- Let's Encrypt SSL (certbot)
- MongoDB backup strategy

**Success Criteria:**
- API accessible via HTTPS
- All endpoints functional remotely
- Data persists across restarts
- Automated SSL renewal configured

**Architecture:**
```
Internet → Cloudflare → Vultr (Singapore)
                           ├── nginx:443 (SSL termination)
                           │     └── proxy → app:8000
                           ├── app:8000 (FastAPI)
                           ├── mongodb:27017
                           └── redis:6379
```

---

### Plan C: Trading Engine Features
**Priority:** 3 (After deployment stable)
**Goal:** Core backtesting and strategy framework

**Scope (from TODO.md):**
1. Strategy Framework - Base class for trading strategies
2. Backtesting Engine - Run strategies against OHLCV, calculate metrics
3. Portfolio Tracker - Positions, P&L, holdings
4. Forward Testing - Paper trading with real-time quotes
5. Risk Management - Stop losses, position limits
6. Performance Reports - Trade logs, equity curves

**Dependencies:**
- Market data pipeline working (validated in Plan A/B)
- Sufficient historical data synced

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| TradingView rate limits | Medium | Cache aggressively, respect intervals |
| MongoDB data loss | High | Regular backups, volume persistence |
| WebSocket disconnects | Medium | Auto-reconnect logic (already implemented) |
| VPS downtime | Medium | Vultr has good uptime, consider monitoring |

## Next Steps

1. **Execute Plan A** - Test locally, validate all endpoints
2. **Create Plan A detailed implementation** - Step-by-step tasks
3. After Plan A success → Create Plan B implementation
4. After Plan B stable → Create Plan C implementation

## Files Created/Modified

- `TODO.md` - Feature roadmap
- This report

---

*Brainstorm concluded with user agreement on 3-plan structure.*
