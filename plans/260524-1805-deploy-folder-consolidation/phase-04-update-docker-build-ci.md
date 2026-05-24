---
phase: 4
title: "Update Docker build & CI"
status: completed
priority: P1
effort: "30m"
dependencies: [2]
---

# Phase 4: Update Docker build & CI

## Overview

CI must explicitly point at `deploy/Dockerfile` (no longer at root). Dockerfile content largely unchanged — build context stays repo root, so all `COPY packages/...` and `COPY scripts/...` lines remain valid. Add a CI smoke build step to fail-fast if path wiring breaks.

## Requirements

- Functional: `docker build -f deploy/Dockerfile .` succeeds locally and in CI. Both API and Web images publish to Docker Hub on push to `master`/`develop`.
- Non-functional: `.dockerignore` stays at root (universal convention); Docker reads it from the context regardless of Dockerfile location.

## Architecture

```yaml
# CI: pass --file explicitly, context unchanged
- uses: docker/build-push-action@v5
  with:
    context: .
    file: deploy/Dockerfile     # NEW
    push: true
    ...
```

```dockerfile
# Dockerfile body: unchanged (context is still repo root)
COPY pyproject.toml uv.lock README.md ./
COPY packages/... packages/...
COPY scripts/ scripts/          # kept (defensive — supports docker exec ... python -m scripts.x)
```

## Related Code Files

- Modify: `.github/workflows/ci.yml` (build-api job)
- Read-only: `deploy/Dockerfile` (no edit unless audit surfaces stale paths)
- Read-only: `.dockerignore` (verify contents reference no moved paths)
- Read-only: `packages/pocketquant-web/Dockerfile` (web image — out of scope, untouched)

## Implementation Steps

1. **`.github/workflows/ci.yml` — build-api job** (around line 32):
   ```yaml
   - uses: docker/build-push-action@v5
     with:
       context: .
       file: deploy/Dockerfile        # ADD THIS LINE
       push: true
       tags: ${{ steps.meta.outputs.tags }}
       labels: ${{ steps.meta.outputs.labels }}
       cache-from: type=gha
       cache-to: type=gha,mode=max
   ```
2. **build-web job — NO CHANGE** (web Dockerfile stays in package; `context: ./packages/pocketquant-web` already correct).
3. **Verify `deploy/Dockerfile` content** — read top-to-bottom; confirm:
   - All `COPY` lines are relative to repo root (context = `.`)
   - No `COPY ./docker/...` or similar broken refs (there were none to begin with)
   - Keep `COPY scripts/ scripts/` (default per unresolved Q1)
   - HEALTHCHECK + EXPOSE + CMD unchanged
4. **Verify `.dockerignore`** — read file; confirm no entries reference `docker/` as a folder we're now deleting, or `Dockerfile` at root (entries usually exclude things from context, not include).
5. **Add optional CI smoke build step** (low cost, high value):
   ```yaml
   - name: Smoke build verification
     run: docker build -f deploy/Dockerfile -t pocketquant:smoke .
   ```
   Place before `docker/build-push-action` (or as a separate workflow run on PRs). Skip if `build-push-action` already exercises the path.
6. **Local validation hand-off**: Phase 8 runs `docker build -f deploy/Dockerfile .` locally to confirm.

## Success Criteria

- [ ] `.github/workflows/ci.yml` has `file: deploy/Dockerfile` in build-api job
- [ ] Web build job unchanged
- [ ] `docker build -f deploy/Dockerfile .` runs to completion locally (or in Phase 8)
- [ ] `.dockerignore` content reviewed; no orphan refs to deleted `docker/` folder
- [ ] CI green on next push (verified in Phase 8 + post-merge)

## Risk Assessment

- **Risk:** Forgot `file:` line; CI silently looks for `./Dockerfile` at root and fails. **Mitigation:** explicit success criterion above; CI log will show clear `failed to read dockerfile` error.
- **Risk:** `COPY scripts/` ships data-ops Python that grows over time. **Mitigation:** acceptable for now; revisit if image size becomes an issue (unresolved Q1 in plan.md).
- **Risk:** `.dockerignore` excludes `deploy/` (unlikely but possible). **Mitigation:** explicit grep of `.dockerignore` for `deploy` substring during the review step.
