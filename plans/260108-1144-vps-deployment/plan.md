---
title: "VPS Deployment to Vultr Singapore"
description: "Deploy PocketQuant to Vultr 4GB Singapore instance with Docker, nginx, SSL"
status: pending
priority: P1
effort: 6h
branch: main
tags: [deployment, vultr, docker, nginx, ssl, production]
created: 2026-01-08
---

# PocketQuant VPS Deployment Plan

## Overview

Deploy PocketQuant algo trading platform to Vultr 4GB Singapore VPS with production-grade Docker setup.

**Target Architecture:**
```
Internet → Cloudflare → nginx:443 → app:8000
                           ├── mongodb:27018 (internal)
                           └── redis:6379 (internal)
```

**Server Specs:**
- Provider: Vultr
- Plan: 4GB RAM / 2 vCPU / 80GB NVMe
- Region: Singapore (sgp)
- OS: Ubuntu 24.04 LTS

---

## Phase 1: Vultr Instance Provisioning (30 min)

### 1.1 Create Vultr Instance

**Via Vultr Dashboard:**
1. Go to vultr.com → Products → Compute → Deploy Server
2. Select:
   - Type: Cloud Compute (Regular Performance)
   - Location: Singapore
   - Image: Ubuntu 24.04 LTS x64
   - Plan: 4GB RAM ($24/mo)
   - Enable IPv6
   - Add SSH key (required before deployment)

**Via Vultr CLI (alternative):**
```bash
# Install vultr-cli
brew install vultr/vultr-cli/vultr-cli

# Configure API key
export VULTR_API_KEY="your-api-key"

# List regions
vultr-cli regions list | grep -i singapore
# Output: sgp   Singapore

# List plans
vultr-cli plans list | grep "4096 MB"

# Deploy
vultr-cli instance create \
  --region sgp \
  --plan vc2-2c-4gb \
  --os 2284 \  # Ubuntu 24.04 x64
  --ssh-keys "your-ssh-key-id" \
  --label "pocketquant-prod"
```

### 1.2 Initial Access

```bash
# Get server IP
export VPS_IP="<your-server-ip>"

# First SSH connection
ssh root@$VPS_IP

# Set hostname
hostnamectl set-hostname pocketquant-prod
```

---

## Phase 2: Server Hardening (45 min)

### 2.1 Create Non-Root User

```bash
# Create deploy user
adduser deploy
usermod -aG sudo deploy

# Copy SSH keys to deploy user
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 2.2 SSH Hardening

```bash
# Edit SSH config
nano /etc/ssh/sshd_config
```

**Apply settings:**
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

```bash
# Restart SSH
systemctl restart sshd

# Test from local machine BEFORE disconnecting
ssh deploy@$VPS_IP
```

### 2.3 UFW Firewall

```bash
# Install UFW
apt update && apt install -y ufw

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow essential ports
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'

# Enable firewall
ufw enable
ufw status verbose
```

### 2.4 Fail2ban for SSH Protection

```bash
# Install fail2ban
apt install -y fail2ban

# Create local config
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400
EOF

# Enable and start
systemctl enable fail2ban
systemctl start fail2ban

# Check status
fail2ban-client status sshd
```

### 2.5 System Updates & Automatic Security Updates

```bash
# Update system
apt update && apt upgrade -y

# Install unattended-upgrades
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# Verify
cat /etc/apt/apt.conf.d/20auto-upgrades
```

---

## Phase 3: Docker Installation (20 min)

### 3.1 Install Docker Engine

```bash
# Remove old versions
apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null

# Install prerequisites
apt install -y ca-certificates curl gnupg

# Add Docker GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify
docker --version
docker compose version

# Add deploy user to docker group
usermod -aG docker deploy
```

### 3.2 Configure Docker Daemon

```bash
cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {"base":"172.17.0.0/16","size":24}
  ]
}
EOF

systemctl restart docker
```

---

## Phase 4: Production Docker Files (1 hour)

### 4.1 Create Dockerfile

**File: `Dockerfile`**
```dockerfile
# syntax=docker/dockerfile:1

# Build stage
FROM python:3.14-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --wheel-dir /wheels -e .

# Runtime stage
FROM python:3.14-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r pocketquant && useradd -r -g pocketquant pocketquant

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Copy application
COPY src/ ./src/
COPY scripts/ ./scripts/

# Set ownership
RUN chown -R pocketquant:pocketquant /app

# Switch to non-root user
USER pocketquant

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### 4.2 Create docker-compose.prod.yml

**File: `docker-compose.prod.yml`**
```yaml
version: "3.9"

services:
  nginx:
    image: nginx:1.25-alpine
    container_name: pocketquant-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/www:/var/www/certbot:ro
      - ./certbot/conf:/etc/letsencrypt:ro
    depends_on:
      app:
        condition: service_healthy
    networks:
      - frontend

  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: pocketquant-app
    restart: always
    expose:
      - "8000"
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
      - MONGODB_URL=mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27018/${MONGO_DB}?authSource=admin
      - MONGODB_DATABASE=${MONGO_DB}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - API_HOST=0.0.0.0
      - API_PORT=8000
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - frontend
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  mongodb:
    image: mongo:7.0
    container_name: pocketquant-mongodb
    restart: always
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_DB}
    volumes:
      - mongodb_data:/data/db
      - ./scripts/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
      - ./backups:/backups
    networks:
      - backend
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.2-alpine
    container_name: pocketquant-redis
    restart: always
    command: >
      redis-server
      --appendonly yes
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - backend
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # No external access

volumes:
  mongodb_data:
  redis_data:
```

### 4.3 Create nginx Configuration

**File: `nginx/nginx.conf`**
```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';
    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css application/json application/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    include /etc/nginx/conf.d/*.conf;
}
```

**File: `nginx/conf.d/pocketquant.conf`**
```nginx
upstream app {
    server app:8000;
    keepalive 32;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name YOUR_DOMAIN.com;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name YOUR_DOMAIN.com;

    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/YOUR_DOMAIN.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/YOUR_DOMAIN.com/chain.pem;

    # SSL configuration
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    # OCSP Stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout 5s;

    # API proxy
    location / {
        limit_req zone=api burst=20 nodelay;

        proxy_pass http://app;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://app;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

### 4.4 Create .env.prod Template

**File: `.env.prod.example`**
```bash
# Production Environment Configuration
# Copy to .env and update with real values

# MongoDB
MONGO_USER=pocketquant_prod
MONGO_PASSWORD=CHANGE_ME_STRONG_PASSWORD_32CHARS
MONGO_DB=pocketquant

# Redis
REDIS_PASSWORD=CHANGE_ME_ANOTHER_STRONG_PASSWORD

# TradingView (optional)
TRADINGVIEW_USERNAME=
TRADINGVIEW_PASSWORD=

# Domain
DOMAIN=YOUR_DOMAIN.com
```

---

## Phase 5: Domain & DNS Setup (20 min)

### 5.1 Cloudflare DNS Configuration

1. Log into Cloudflare Dashboard
2. Select your domain
3. Go to DNS → Records
4. Add records:

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A | api (or @) | YOUR_VPS_IP | Proxied (orange) | Auto |
| AAAA | api (or @) | YOUR_VPS_IPv6 | Proxied (orange) | Auto |

### 5.2 Cloudflare SSL Settings

1. Go to SSL/TLS → Overview
2. Set mode to **Full (strict)**
3. Go to SSL/TLS → Edge Certificates
4. Enable:
   - Always Use HTTPS
   - Automatic HTTPS Rewrites
   - TLS 1.3

---

## Phase 6: Let's Encrypt SSL (30 min)

### 6.1 Initial Certificate Request

```bash
# Create directories
mkdir -p certbot/www certbot/conf

# Create temporary nginx config for initial cert
cat > nginx/conf.d/pocketquant.conf << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
EOF

# Start nginx only
docker compose -f docker-compose.prod.yml up -d nginx

# Request certificate
docker run --rm \
  -v $(pwd)/certbot/www:/var/www/certbot \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email your@email.com \
  --agree-tos \
  --no-eff-email \
  -d YOUR_DOMAIN.com

# Update nginx config to full HTTPS version (from Phase 4.3)
# Then restart
docker compose -f docker-compose.prod.yml restart nginx
```

### 6.2 Certificate Auto-Renewal

**File: `scripts/renew-certs.sh`**
```bash
#!/bin/bash
set -e

cd /home/deploy/pocketquant

docker run --rm \
  -v $(pwd)/certbot/www:/var/www/certbot \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  certbot/certbot renew --quiet

docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

```bash
# Make executable
chmod +x scripts/renew-certs.sh

# Add cron job (as deploy user)
crontab -e
# Add line:
0 3 * * * /home/deploy/pocketquant/scripts/renew-certs.sh >> /var/log/certbot-renew.log 2>&1
```

---

## Phase 7: Deployment (30 min)

### 7.1 Prepare Server Directory

```bash
# As deploy user
sudo mkdir -p /home/deploy/pocketquant
sudo chown deploy:deploy /home/deploy/pocketquant
cd /home/deploy/pocketquant
```

### 7.2 Deploy Application

```bash
# Clone repository (or copy files)
git clone https://github.com/your-org/pocketquant.git .

# Or rsync from local
rsync -avz --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  ./ deploy@$VPS_IP:/home/deploy/pocketquant/

# Create .env from template
cp .env.prod.example .env
nano .env  # Update with real passwords

# Create nginx directories
mkdir -p nginx/conf.d certbot/www certbot/conf backups

# Build and start
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### 7.3 Validation Checklist

```bash
# Check containers
docker compose -f docker-compose.prod.yml ps

# Check health endpoint
curl https://YOUR_DOMAIN.com/health

# Check API docs
curl https://YOUR_DOMAIN.com/api/v1/docs

# Check MongoDB connection
docker compose -f docker-compose.prod.yml exec mongodb mongosh \
  -u $MONGO_USER -p $MONGO_PASSWORD --authenticationDatabase admin \
  --eval "db.stats()"

# Check Redis
docker compose -f docker-compose.prod.yml exec redis redis-cli \
  -a $REDIS_PASSWORD ping

# Check logs
docker compose -f docker-compose.prod.yml logs app --tail 50
```

---

## Phase 8: MongoDB Backup (30 min)

### 8.1 Create Backup Script

**File: `scripts/backup-mongodb.sh`**
```bash
#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/home/deploy/pocketquant/backups"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="pocketquant_${DATE}"

# Load environment
source /home/deploy/pocketquant/.env

echo "[$(date)] Starting MongoDB backup..."

# Create backup
docker exec pocketquant-mongodb mongodump \
  --username="$MONGO_USER" \
  --password="$MONGO_PASSWORD" \
  --authenticationDatabase=admin \
  --db="$MONGO_DB" \
  --archive="/backups/${BACKUP_NAME}.archive" \
  --gzip

# Verify backup
if [ -f "${BACKUP_DIR}/${BACKUP_NAME}.archive" ]; then
    SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.archive" | cut -f1)
    echo "[$(date)] Backup created: ${BACKUP_NAME}.archive (${SIZE})"
else
    echo "[$(date)] ERROR: Backup file not found!"
    exit 1
fi

# Delete old backups
find "$BACKUP_DIR" -name "pocketquant_*.archive" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Cleaned backups older than ${RETENTION_DAYS} days"

# List current backups
echo "[$(date)] Current backups:"
ls -lh "$BACKUP_DIR"/*.archive 2>/dev/null || echo "No backups found"

echo "[$(date)] Backup completed successfully"
```

### 8.2 Setup Cron Job

```bash
# Make executable
chmod +x scripts/backup-mongodb.sh

# Create log directory
mkdir -p /home/deploy/logs

# Add to crontab
crontab -e
# Add:
0 2 * * * /home/deploy/pocketquant/scripts/backup-mongodb.sh >> /home/deploy/logs/backup.log 2>&1
```

### 8.3 Restore Procedure

```bash
# Restore from backup
docker exec -i pocketquant-mongodb mongorestore \
  --username="$MONGO_USER" \
  --password="$MONGO_PASSWORD" \
  --authenticationDatabase=admin \
  --archive="/backups/pocketquant_YYYYMMDD_HHMMSS.archive" \
  --gzip \
  --drop
```

---

## Phase 9: Monitoring & Maintenance

### 9.1 Basic Health Monitoring

**File: `scripts/health-check.sh`**
```bash
#!/bin/bash

DOMAIN="YOUR_DOMAIN.com"
WEBHOOK_URL=""  # Optional: Slack/Discord webhook

check_service() {
    local response=$(curl -s -o /dev/null -w "%{http_code}" "https://${DOMAIN}/health")
    if [ "$response" != "200" ]; then
        echo "[$(date)] ALERT: Health check failed (HTTP $response)"
        # Optional: send webhook alert
        return 1
    fi
    echo "[$(date)] OK: Health check passed"
    return 0
}

check_service
```

```bash
# Add to crontab (every 5 minutes)
*/5 * * * * /home/deploy/pocketquant/scripts/health-check.sh >> /home/deploy/logs/health.log 2>&1
```

### 9.2 Log Rotation

**File: `/etc/logrotate.d/pocketquant`**
```
/home/deploy/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 deploy deploy
}
```

---

## Project Structure After Deployment

```
pocketquant/
├── Dockerfile                  # NEW
├── docker-compose.yml          # Development (existing)
├── docker-compose.prod.yml     # NEW - Production
├── .env                        # Production secrets (gitignored)
├── .env.prod.example           # NEW - Template
├── nginx/
│   ├── nginx.conf              # NEW
│   └── conf.d/
│       └── pocketquant.conf    # NEW
├── certbot/
│   ├── www/                    # ACME challenge
│   └── conf/                   # SSL certificates
├── backups/                    # MongoDB backups
├── scripts/
│   ├── mongo-init.js           # Existing
│   ├── backup-mongodb.sh       # NEW
│   ├── renew-certs.sh          # NEW
│   └── health-check.sh         # NEW
├── src/                        # Application code
└── ...
```

---

## Summary

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Vultr provisioning | 30 min |
| 2 | Server hardening | 45 min |
| 3 | Docker installation | 20 min |
| 4 | Docker files creation | 60 min |
| 5 | Domain/DNS setup | 20 min |
| 6 | SSL certificates | 30 min |
| 7 | Deployment | 30 min |
| 8 | MongoDB backup | 30 min |
| 9 | Monitoring | 15 min |
| **Total** | | **~6 hours** |

---

## Files to Create

1. `Dockerfile` - Multi-stage Python container
2. `docker-compose.prod.yml` - Production orchestration
3. `.env.prod.example` - Environment template
4. `nginx/nginx.conf` - Main nginx config
5. `nginx/conf.d/pocketquant.conf` - Site config
6. `scripts/backup-mongodb.sh` - Backup script
7. `scripts/renew-certs.sh` - SSL renewal
8. `scripts/health-check.sh` - Health monitoring

---

## Unresolved Questions

1. **Domain name** - What is the actual domain to use?
2. **Cloudflare proxy** - Use Cloudflare proxy (orange cloud) or DNS-only (gray)?
   - Recommendation: Use proxy for DDoS protection and caching
3. **TradingView credentials** - Will prod use authenticated TradingView access?
4. **Backup storage** - Consider offsite backup (S3, Backblaze B2) for disaster recovery?
5. **Monitoring** - Need alerting service (Uptime Robot, Betterstack)?
6. **API authentication** - Production API should have auth. Planned?
