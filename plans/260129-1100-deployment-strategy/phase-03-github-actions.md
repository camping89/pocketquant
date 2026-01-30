# Phase 03: GitHub Actions Workflow

## Context

- **Parent:** [plan.md](plan.md)
- **Dependencies:** [Phase 01](phase-01-dockerfile.md), [Phase 02](phase-02-compose-prod.md)
- **Docs:** GitHub Actions docs

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 |
| Status | ⏳ Pending |
| Effort | 45m |

Create GitHub Actions workflow với generic secrets (provider-agnostic).

## Key Insights

- Generic secret names (DEPLOY_* instead of VULTR_*)
- Secrets chỉ chứa SSH credentials
- App config stored on server (.env.prod)
- Works with any VPS provider

## GitHub Secrets Required

```yaml
# Generic - works with any provider
DEPLOY_HOST       # VPS IP address (e.g., 123.45.67.89)
DEPLOY_USER       # SSH user (e.g., deploy)
DEPLOY_SSH_KEY    # Private SSH key (PEM format)

# Optional - app secrets (if not using server .env)
TRADINGVIEW_USERNAME
TRADINGVIEW_PASSWORD
```

## Related Code Files

### Files to Create
- `.github/workflows/deploy.yml`

### Files to Reference
- `Dockerfile`
- `docker/compose.prod.yml`

## Implementation Steps

### Step 1: Create deploy.yml

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches:
      - master
  workflow_dispatch:
    inputs:
      profile:
        description: 'Compose profiles to enable'
        required: false
        default: 'monitoring,admin'
        type: choice
        options:
          - ''
          - 'monitoring'
          - 'admin'
          - 'monitoring,admin'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    name: Build & Push Image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-,format=short

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    name: Deploy to Server
    needs: build
    runs-on: ubuntu-latest

    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            set -e

            echo "=== Deploying PocketQuant ==="
            cd /opt/pocketquant

            # Login to GHCR
            echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin

            # Pull latest image
            docker pull ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

            # Determine profiles
            PROFILES="${{ github.event.inputs.profile || 'monitoring,admin' }}"
            PROFILE_FLAGS=""
            if [ -n "$PROFILES" ]; then
              for p in $(echo $PROFILES | tr ',' ' '); do
                PROFILE_FLAGS="$PROFILE_FLAGS --profile $p"
              done
            fi

            # Restart app service only (preserves other services)
            docker compose -f docker/compose.prod.yml --env-file docker/.env.prod $PROFILE_FLAGS up -d app

            # Wait for startup
            echo "Waiting for app to start..."
            sleep 15

            # Health check
            echo "Running health check..."
            curl -f http://localhost:8000/health || exit 1

            echo "=== Deployment successful ==="

      - name: Verify deployment
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            echo "=== Container Status ==="
            docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep pocketquant

            echo ""
            echo "=== Health Check ==="
            curl -s http://localhost:8000/health | python3 -m json.tool || true

            echo ""
            echo "=== Recent App Logs ==="
            docker logs pocketquant-app --tail 10 2>&1 || true

  cleanup:
    name: Cleanup Old Images
    needs: deploy
    runs-on: ubuntu-latest

    steps:
      - name: Cleanup on server
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            echo "=== Cleaning up old images ==="
            # Remove dangling images
            docker image prune -f

            # Remove images older than 7 days
            docker image prune -af --filter "until=168h" || true

            echo "=== Disk usage ==="
            df -h /
```

### Step 2: Setup GitHub Secrets

1. Go to repository → Settings → Secrets and variables → Actions
2. Add secrets:

| Secret | Example Value |
|--------|---------------|
| `DEPLOY_HOST` | `123.45.67.89` |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

### Step 3: Enable GHCR Permissions

1. Repository → Settings → Actions → General
2. "Read and write permissions" under Workflow permissions
3. Check "Allow GitHub Actions to create and approve pull requests"

### Step 4: Test Workflow

```bash
# Option 1: Push to master
git checkout master
git merge feature/deployment
git push origin master

# Option 2: Manual trigger
# Go to Actions tab → Deploy to Production → Run workflow
```

## Todo List

- [ ] Create `.github/workflows/deploy.yml`
- [ ] Setup GitHub Secrets (DEPLOY_*)
- [ ] Enable GHCR permissions
- [ ] Test with a push to master
- [ ] Verify health check passes

## Success Criteria

- [ ] Workflow triggers on push to master
- [ ] Image builds and pushes successfully
- [ ] SSH deploy executes without errors
- [ ] Health check passes
- [ ] Total time < 5 minutes
- [ ] Old images cleaned up

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| SSH key exposure | Critical | GitHub secrets encrypted |
| Deploy fails mid-way | Medium | Only restart app, not full stack |
| Health check timeout | Medium | 15s wait + retry |

## Rollback Procedure

```bash
# SSH to server
ssh deploy@$DEPLOY_HOST

# List available images
docker images | grep pocketquant

# Rollback to previous SHA
export OLD_TAG="sha-abc1234"
docker tag ghcr.io/user/repo:$OLD_TAG ghcr.io/user/repo:latest
docker compose -f docker/compose.prod.yml --env-file docker/.env.prod up -d app

# Verify
curl http://localhost:8000/health
```

## Next Steps

After completion → [Phase 04: Server Setup](phase-04-server-setup.md)
