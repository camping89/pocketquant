---
phase: 8
title: "Local validation"
status: completed
priority: P1
effort: "30m"
dependencies: [1, 2, 3, 4, 5, 6, 7]
---

# Phase 8: Local validation

## Overview

Final gate before commit/push. Re-greps for orphan refs, runs dev workflow end-to-end locally, smoke-builds the Docker image. Catches any miss from earlier phases.

## Requirements

- Functional: every `just` recipe touched by this refactor works. Docker image builds. No old-path references remain in active code/config/docs.
- Non-functional: validation produces a written checklist in plan-local reports/ for the PR description.

## Architecture

Pure validation. No code change. Output: `plans/260524-1805-deploy-folder-consolidation/reports/validation-checklist.md`.

## Related Code Files

- Read-only: everything touched in phases 1–7
- Create: `plans/260524-1805-deploy-folder-consolidation/reports/validation-checklist.md`

## Implementation Steps

1. **Final grep sweep** — must return zero matches across all listed paths:
   ```powershell
   # Run from project root
   $patterns = @(
     "docker/compose",
     "docker/\.env",
     "docker/scripts/",
     "docker/mongo-init",
     "scripts\.one_time_purge_legacy_strategies",
     "bash deploy\.sh",
     "bash verify\.sh"
   )
   $excludes = @("--glob=!.venv", "--glob=!node_modules", "--glob=!__pycache__",
                 "--glob=!htmlcov", "--glob=!.git", "--glob=!.pytest_cache",
                 "--glob=!.ruff_cache", "--glob=!.import_linter_cache",
                 "--glob=!docs/journals/*", "--glob=!plans/260507-*",
                 "--glob=!plans/260508-*", "--glob=!plans/260511-*",
                 "--glob=!plans/260523-*", "--glob=!plans/260524-1*")
   foreach ($p in $patterns) {
     Write-Host "=== $p ==="
     rg $p @excludes
   }
   ```
   Document any survivors in the checklist; only acceptable in: this plan's own files, the brainstorm report, the changelog entry (which references old paths in past tense).

2. **`just` recipes — local dev smoke test:**
   ```powershell
   just down              # clean slate
   just up                # mongo + redis start via deploy/compose.yml
   just check             # check_env.py reports OK
   ```
   Expected: all three commands exit 0. Containers visible in `docker ps`.

3. **Docker image local build:**
   ```powershell
   docker build -f deploy/Dockerfile -t pocketquant:smoke .
   ```
   Expected: build completes; final image listed via `docker images pocketquant:smoke`.

4. **Web image local build (regression check — must still work, no changes intended):**
   ```powershell
   docker build -f packages/pocketquant-web/Dockerfile -t pocketquant-web:smoke ./packages/pocketquant-web
   ```

5. **Local prod-stack simulation (REQUIRED — no staging VPS available):**
   Simulate the VPS deploy on localhost using the freshly-built images. Drop after confirm.
   ```powershell
   # Stop dev stack to free ports
   just down

   # Tag local builds to match what compose.prod.yml expects
   docker tag pocketquant:smoke ${env:DOCKERHUB_USERNAME}/pocketquant:latest
   docker tag pocketquant-web:smoke ${env:DOCKERHUB_USERNAME}/pocketquant-web:latest

   # Bring up prod stack via deploy/ paths (mirrors what deploy/deploy.sh does on VPS)
   docker compose -f deploy/compose.prod.yml --env-file deploy/.env up -d --remove-orphans

   # Wait for app health
   for ($i=0; $i -lt 30; $i++) {
     $h = docker inspect --format='{{.State.Health.Status}}' pocketquant-app 2>$null
     if ($h -eq "healthy") { break }
     Start-Sleep 2
   }

   # Hit the health endpoint
   docker exec pocketquant-app curl -sf http://localhost:41920/health

   # Run verify.sh against the local prod stack
   bash deploy/verify.sh
   # Inspect: deploy/reports/verify-<timestamp>.md should show all PASS

   # Teardown
   docker compose -f deploy/compose.prod.yml --env-file deploy/.env down -v
   ```
   **Pass criteria:** all containers healthy, /health returns 200, verify.sh report = HEALTHY (or DEGRADED with only disk/memory warnings on dev machine).

6. **`deploy/deploy.sh` dry-trace** (do NOT execute against real VPS):
   - `cat deploy/deploy.sh` end-to-end; manually verify every path resolves under `cd deploy/`.
   - Confirm no `docker/` substring remains.

7. **`deploy/verify.sh` dry-trace**: same treatment.

8. **CI hand-off**: this is local-only validation. Real CI run gates on push. Document in checklist: "CI green = required follow-up after merge."

9. **Write validation checklist** at `plans/260524-1805-deploy-folder-consolidation/reports/validation-checklist.md`:
   ```markdown
   # Validation Checklist — Deploy Folder Consolidation

   ## Final Grep Sweep
   - [x] / [ ] zero orphan refs (or list survivors with justification)

   ## just Recipes
   - [ ] just down → exit 0
   - [ ] just up → containers up
   - [ ] just check → OK

   ## Docker Builds
   - [ ] deploy/Dockerfile → image built
   - [ ] packages/pocketquant-web/Dockerfile → image built (regression)

   ## Local Prod-Stack Simulation
   - [ ] compose.prod.yml up → all 4 containers healthy
   - [ ] /health returns 200
   - [ ] verify.sh report = HEALTHY (or only disk/memory warnings)
   - [ ] compose down -v → clean teardown

   ## Script Traces
   - [ ] deploy/deploy.sh — no docker/ refs
   - [ ] deploy/verify.sh — no docker/ refs

   ## Post-Merge Follow-ups
   - [ ] CI green on first push
   - [ ] VPS migration runbook executed before next prod deploy
   ```

## Success Criteria

- [ ] Grep sweep clean (or all survivors justified)
- [ ] `just up && just check && just down` round-trip succeeds
- [ ] `docker build -f deploy/Dockerfile .` succeeds
- [ ] Web image build still succeeds
- [ ] **Local prod-stack simulation passes** (compose.prod.yml up → all healthy → verify.sh HEALTHY → clean teardown)
- [ ] Validation checklist written + committed
- [ ] Ready to commit + push + open PR

## Risk Assessment

- **Risk:** Validation passes locally but CI fails (path-case mismatch, missing newline, etc.). **Mitigation:** monitor first CI run post-push; document fix in checklist follow-ups.
- **Risk:** Local Docker daemon caches old image. **Mitigation:** use `--no-cache` if uncertain (`docker build --no-cache -f deploy/Dockerfile .`).
- **Risk:** Operator skips this phase and commits broken state. **Mitigation:** this phase is a HARD gate; PR description should reference the checklist.
- **Risk:** Local prod stack port conflict with dev stack. **Mitigation:** explicit `just down` before bringing up prod stack; teardown with `down -v` removes volumes so dev `just up` after starts clean.
- **Risk:** Local prod simulation hides VPS-specific failures (file permissions, ufw, SELinux). **Mitigation:** known limitation — runbook + first-deploy monitoring catches these post-push.
