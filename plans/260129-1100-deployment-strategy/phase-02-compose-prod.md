# Phase 02: Production Docker Compose (Full Stack)

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** [Phase 01](phase-01-dockerfile.md)
- **Docs:** [system-architecture.md](../../docs/system-architecture.md)

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 |
| Status | ⏳ Pending |
| Effort | 45m |

Create production Docker Compose với full self-hosted stack.

## Key Insights

- All services self-hosted (MongoDB, Redis, Loki, Grafana)
- Caddy as reverse proxy (Phase 05)
- Portainer for container management
- Resource limits cho VPS 2GB

## Services Stack

| Service | Image | RAM Limit | Purpose |
|---------|-------|-----------|---------|
| app | ghcr.io/*/pocketquant | 512MB | FastAPI application |
| mongodb | mongo:7.0 | 512MB | Database |
| redis | redis:7.2-alpine | 128MB | Cache |
| loki | grafana/loki:2.9.0 | 256MB | Log aggregation |
| promtail | grafana/promtail:2.9.0 | 64MB | Log shipping |
| grafana | grafana/grafana:10.2.0 | 256MB | Dashboards |
| portainer | portainer/portainer-ce | 128MB | Container UI |
| caddy | caddy:2-alpine | 64MB | Reverse proxy |
| **Total** | | **~1.9GB** | |

## Related Code Files

### Files to Create
- `docker/compose.prod.yml`
- `docker/.env.prod.example`

### Files to Reference
- `docker/compose.yml` - Dev compose reference
- `.env.example` - Env vars

## Implementation Steps

### Step 1: Create compose.prod.yml

```yaml
# docker/compose.prod.yml
name: pocketquant-prod

services:
  # ===========================================
  # APPLICATION
  # ===========================================
  app:
    image: ghcr.io/${GITHUB_USER}/pocketquant:${IMAGE_TAG:-latest}
    container_name: pocketquant-app
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
      - MONGODB_URL=mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/pocketquant?authSource=admin
      - REDIS_URL=redis://redis:6379/0
      - TRADINGVIEW_USERNAME=${TRADINGVIEW_USERNAME:-}
      - TRADINGVIEW_PASSWORD=${TRADINGVIEW_PASSWORD:-}
      - ENABLE_JOBS=true
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        tag: "{{.Name}}"
    labels:
      - "app=pocketquant"
    networks:
      - pocketquant-net

  # ===========================================
  # DATABASE
  # ===========================================
  mongodb:
    image: mongo:7.0
    container_name: pocketquant-mongodb
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
      MONGO_INITDB_DATABASE: pocketquant
    volumes:
      - mongodb_data:/data/db
      - ./mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    networks:
      - pocketquant-net

  mongo-express:
    image: mongo-express:1.0.2
    container_name: pocketquant-mongo-express
    restart: unless-stopped
    environment:
      ME_CONFIG_MONGODB_ADMINUSERNAME: ${MONGO_USER}
      ME_CONFIG_MONGODB_ADMINPASSWORD: ${MONGO_PASSWORD}
      ME_CONFIG_MONGODB_URL: mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/
      ME_CONFIG_BASICAUTH: "true"
      ME_CONFIG_BASICAUTH_USERNAME: ${MONGO_EXPRESS_USER:-admin}
      ME_CONFIG_BASICAUTH_PASSWORD: ${MONGO_EXPRESS_PASSWORD}
    depends_on:
      mongodb:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 128M
    networks:
      - pocketquant-net
    profiles:
      - admin

  # ===========================================
  # CACHE
  # ===========================================
  redis:
    image: redis:7.2-alpine
    container_name: pocketquant-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 100mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M
    networks:
      - pocketquant-net

  # ===========================================
  # LOGGING (Loki + Promtail)
  # ===========================================
  loki:
    image: grafana/loki:2.9.0
    container_name: pocketquant-loki
    restart: unless-stopped
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki_data:/loki
      - ./loki-config.yml:/etc/loki/local-config.yaml:ro
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M
    networks:
      - pocketquant-net
    profiles:
      - monitoring

  promtail:
    image: grafana/promtail:2.9.0
    container_name: pocketquant-promtail
    restart: unless-stopped
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./promtail-config.yml:/etc/promtail/config.yml:ro
    command: -config.file=/etc/promtail/config.yml
    depends_on:
      - loki
    deploy:
      resources:
        limits:
          memory: 64M
    networks:
      - pocketquant-net
    profiles:
      - monitoring

  # ===========================================
  # MONITORING (Grafana)
  # ===========================================
  grafana:
    image: grafana/grafana:10.2.0
    container_name: pocketquant-grafana
    restart: unless-stopped
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_USER:-admin}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_SERVER_ROOT_URL=${GRAFANA_ROOT_URL:-http://localhost:3000}
      - GF_SERVER_SERVE_FROM_SUB_PATH=true
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml:ro
    depends_on:
      - loki
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M
    networks:
      - pocketquant-net
    profiles:
      - monitoring

  # ===========================================
  # MANAGEMENT (Portainer)
  # ===========================================
  portainer:
    image: portainer/portainer-ce:latest
    container_name: pocketquant-portainer
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - portainer_data:/data
    deploy:
      resources:
        limits:
          memory: 128M
    networks:
      - pocketquant-net
    profiles:
      - admin

  # ===========================================
  # REVERSE PROXY (Caddy)
  # ===========================================
  caddy:
    image: caddy:2-alpine
    container_name: pocketquant-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    deploy:
      resources:
        limits:
          memory: 64M
    networks:
      - pocketquant-net

# ===========================================
# NETWORKS & VOLUMES
# ===========================================
networks:
  pocketquant-net:
    driver: bridge

volumes:
  mongodb_data:
  redis_data:
  loki_data:
  grafana_data:
  portainer_data:
  caddy_data:
  caddy_config:
```

### Step 2: Create .env.prod.example

```bash
# docker/.env.prod.example
# Copy to .env.prod and fill in values

# ===========================================
# DEPLOYMENT
# ===========================================
GITHUB_USER=your-github-username
IMAGE_TAG=latest

# ===========================================
# DATABASE
# ===========================================
MONGO_USER=pocketquant
MONGO_PASSWORD=change_this_strong_password

# ===========================================
# ADMIN UIs (optional)
# ===========================================
MONGO_EXPRESS_USER=admin
MONGO_EXPRESS_PASSWORD=change_this_password
GRAFANA_USER=admin
GRAFANA_PASSWORD=change_this_password
GRAFANA_ROOT_URL=http://your-ip/grafana

# ===========================================
# APP (optional)
# ===========================================
TRADINGVIEW_USERNAME=
TRADINGVIEW_PASSWORD=
```

### Step 3: Create supporting config files

```yaml
# docker/loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks

limits_config:
  retention_period: 168h  # 7 days

compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  retention_enabled: true
```

```yaml
# docker/promtail-config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
      - source_labels: ['__meta_docker_container_label_app']
        target_label: 'app'
    pipeline_stages:
      - json:
          expressions:
            level: level
            event: event
            logger: logger
      - labels:
          level:
          event:
```

```yaml
# docker/grafana-datasources.yml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
```

## Todo List

- [ ] Create `docker/compose.prod.yml`
- [ ] Create `docker/.env.prod.example`
- [ ] Create `docker/loki-config.yml`
- [ ] Create `docker/promtail-config.yml`
- [ ] Create `docker/grafana-datasources.yml`
- [ ] Test locally với `docker compose --profile monitoring --profile admin up`

## Success Criteria

- [ ] All services start successfully
- [ ] Health checks pass
- [ ] Memory limits enforced (total < 2GB)
- [ ] Logs flow to Loki → Grafana

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| OOM (out of memory) | High | Conservative memory limits |
| Data loss on volume | High | Separate volume per service |
| Service dependency | Medium | Health checks + depends_on |

## Security Considerations

- MongoDB requires auth
- Mongo Express protected by basic auth
- Grafana requires login
- Internal network isolation
- Only Caddy exposed to internet

## Next Steps

After completion → [Phase 03: GitHub Actions](phase-03-github-actions.md)
