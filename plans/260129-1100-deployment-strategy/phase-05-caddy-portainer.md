# Phase 05: Caddy + Portainer

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** [Phase 02](phase-02-compose-prod.md), [Phase 04](phase-04-server-setup.md)
- **Docs:** Caddy documentation

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 |
| Status | ⏳ Pending |
| Effort | 30m |

Setup Caddy reverse proxy để expose services + Portainer để quản lý containers.

## Key Insights

- Caddy auto HTTPS nếu có domain
- HTTP mode cho IP-only setup
- Portainer protected by basic auth hoặc riêng port
- All services qua single entry point

## Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    CADDY (:80)                          │
│                                                          │
│  /api/*       → app:8000        (FastAPI)               │
│  /portainer/* → portainer:9000  (Container UI)          │
│  /grafana/*   → grafana:3000    (Dashboards)            │
│  /mongo/*     → mongo-express:8081 (DB Admin)           │
│  /health      → app:8000/health (Direct health check)   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Related Code Files

### Files to Create
- `docker/Caddyfile`
- `docker/Caddyfile.domain` (template for HTTPS)

## Implementation Steps

### Step 1: Create Caddyfile (HTTP only - IP mode)

```
# docker/Caddyfile
# HTTP mode - for IP-only access
# Replace with Caddyfile.domain when you have a domain

:80 {
    # API - Main application
    handle /api/* {
        reverse_proxy app:8000
    }

    # Health check (direct access)
    handle /health {
        reverse_proxy app:8000
    }

    # OpenAPI docs
    handle /api/v1/docs* {
        reverse_proxy app:8000
    }
    handle /api/v1/redoc* {
        reverse_proxy app:8000
    }
    handle /api/v1/openapi.json {
        reverse_proxy app:8000
    }

    # Portainer - Container management
    handle /portainer/* {
        uri strip_prefix /portainer
        reverse_proxy portainer:9000
    }

    # Grafana - Monitoring dashboards
    handle /grafana/* {
        uri strip_prefix /grafana
        reverse_proxy grafana:3000
    }

    # Mongo Express - Database admin
    handle /mongo/* {
        uri strip_prefix /mongo
        reverse_proxy mongo-express:8081
    }

    # Default - redirect to API docs
    handle {
        redir /api/v1/docs permanent
    }

    # Logging
    log {
        output stdout
        format console
        level INFO
    }
}
```

### Step 2: Create Caddyfile.domain (HTTPS - for future)

```
# docker/Caddyfile.domain
# HTTPS mode - use when you have a domain
# Rename to Caddyfile and update DOMAIN variable

{$DOMAIN:api.example.com} {
    # Automatic HTTPS via Let's Encrypt

    # API - Main application
    handle /api/* {
        reverse_proxy app:8000
    }

    handle /health {
        reverse_proxy app:8000
    }

    # OpenAPI docs
    handle /api/v1/docs* {
        reverse_proxy app:8000
    }
    handle /api/v1/redoc* {
        reverse_proxy app:8000
    }
    handle /api/v1/openapi.json {
        reverse_proxy app:8000
    }

    # Portainer - protected
    handle /portainer/* {
        # Basic auth protection
        basicauth {
            admin $PORTAINER_HASH
        }
        uri strip_prefix /portainer
        reverse_proxy portainer:9000
    }

    # Grafana
    handle /grafana/* {
        uri strip_prefix /grafana
        reverse_proxy grafana:3000
    }

    # Mongo Express - protected
    handle /mongo/* {
        basicauth {
            admin $MONGO_EXPRESS_HASH
        }
        uri strip_prefix /mongo
        reverse_proxy mongo-express:8081
    }

    handle {
        redir /api/v1/docs permanent
    }

    log {
        output stdout
        format json
        level INFO
    }
}
```

### Step 3: Configure Portainer for subpath

Portainer cần biết nó đang chạy ở subpath `/portainer`:

```yaml
# In compose.prod.yml - add to portainer service
portainer:
  ...
  command: --base-url /portainer
```

### Step 4: Configure Grafana for subpath

```yaml
# In compose.prod.yml - grafana environment
environment:
  - GF_SERVER_ROOT_URL=%(protocol)s://%(domain)s/grafana/
  - GF_SERVER_SERVE_FROM_SUB_PATH=true
```

### Step 5: Test Configuration

```bash
# On server
cd /opt/pocketquant

# Start all services
docker compose -f docker/compose.prod.yml \
  --env-file docker/.env.prod \
  --profile monitoring \
  --profile admin \
  up -d

# Test endpoints
curl http://localhost/health
curl http://localhost/api/v1/docs
curl http://localhost/portainer/
curl http://localhost/grafana/
curl http://localhost/mongo/
```

## Endpoints Summary

| Path | Service | Auth |
|------|---------|------|
| `/api/*` | FastAPI | Rate limit (app) |
| `/health` | FastAPI | None |
| `/api/v1/docs` | Swagger UI | None |
| `/portainer/*` | Portainer | Built-in auth |
| `/grafana/*` | Grafana | Built-in auth |
| `/mongo/*` | Mongo Express | Basic auth |

## Todo List

- [ ] Create `docker/Caddyfile`
- [ ] Create `docker/Caddyfile.domain` (template)
- [ ] Update compose.prod.yml với subpath configs
- [ ] Test all endpoints locally
- [ ] Verify Portainer accessible
- [ ] Verify Grafana accessible

## Success Criteria

- [ ] All services accessible via Caddy
- [ ] `/health` returns 200
- [ ] Portainer shows all containers
- [ ] Grafana loads with Loki datasource
- [ ] No direct port exposure (except 80)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Misconfigured proxy | Medium | Test each route |
| Auth bypass | High | Use built-in auth |
| Path collision | Low | Distinct prefixes |

## Security Considerations

- Portainer has its own auth system
- Grafana requires login
- Mongo Express uses basic auth
- Only port 80 exposed externally
- Internal services not directly accessible

## Switching to HTTPS (Future)

```bash
# 1. Get a domain (e.g., duckdns.org - free)
# 2. Point domain to server IP
# 3. Update Caddyfile
cp docker/Caddyfile.domain docker/Caddyfile

# 4. Add domain to .env.prod
echo "DOMAIN=your-domain.duckdns.org" >> docker/.env.prod

# 5. Restart Caddy
docker compose -f docker/compose.prod.yml restart caddy

# Caddy will auto-obtain Let's Encrypt certificate
```

## Next Steps

After completion → [Phase 06: Monitoring](phase-06-monitoring.md)
