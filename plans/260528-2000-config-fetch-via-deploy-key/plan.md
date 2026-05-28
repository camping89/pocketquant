---
title: "Centralize CI/CD config via pocketquant-config deploy-key fetch"
description: "Move VPS host, SSH key, prod .env, Docker Hub creds, and Portainer access creds out of GH Actions secrets into pocketquant-config private repo. CI/CD fetches config at run time via one deploy key. Eve-platform pattern (approach A: re-fetch in each job)."
status: pending
priority: P2
branch: "develop"
tags: [cicd, secrets, infra]
blockedBy: []
blocks: []
supersedes: [260528-1700-cicd-deploy-into-github-actions]
created: "2026-05-28T13:01:26.920Z"
createdBy: "ck:plan"
source: skill
---

# Centralize CI/CD config via pocketquant-config deploy-key fetch

## Overview

Reduce GH Actions secrets from 5 → 1 (`POCKETQUANT_CONFIG_DEPLOY_KEY`). All VPS + Docker Hub + Portainer credentials live in `pocketquant-config/` (private repo). Each CI job fetches what it needs via a composite action (`get-vps-config`) using SSH deploy key auth. Approach A: re-fetch in every job → auto-mask via `::add-mask::`, parallel clones, no cross-job leak risk. Eve-platform pattern.

Source design: [brainstorm-config-fetch-via-deploy-key.md](./brainstorm-config-fetch-via-deploy-key.md).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Restructure pocketquant-config layout + bootstrap script](./phase-01-restructure-pocketquant-config-layout-bootstrap-script.md) | Pending |
| 2 | [Add get-vps-config composite action](./phase-02-add-get-vps-config-composite-action.md) | Pending |
| 3 | [Rewrite cicd.yml using composite action](./phase-03-rewrite-cicd-yml-using-composite-action.md) | Pending |
| 4 | [Bootstrap + smoke-test on throwaway branch](./phase-04-bootstrap-smoke-test-on-throwaway-branch.md) | Pending |
| 5 | [Cleanup old GH secrets + docs sweep](./phase-05-cleanup-old-gh-secrets-docs-sweep.md) | Pending |

## Key decisions (locked by brainstorm)

- Pattern: eve-platform `get-secrets` composite action over private config repo.
- Source: `camping89/pocketquant-config` (private, confirmed via gh api).
- Scope: ALL — VPS host, SSH key, prod `.env`, Docker Hub creds, Portainer access creds.
- SSH key storage: separate file `vps/default/id_rsa` (renamed from `vultr`).
- Folder name: `default` (single VPS, role=prod implicit; allows multi-VPS later).
- Auto-redeploy on config push: NO.
- Portainer service: keep running on VPS; only remove access creds from pocketquant docs.
- Cross-job mask: approach A (re-fetch in each job; auto `::add-mask::`; parallel clones).
- Bootstrap: `pocketquant-config/scripts/bootstrap-gh.sh` — idempotent (handles initial setup + rotation).

## Final GH Actions secrets state

- ADD: `POCKETQUANT_CONFIG_DEPLOY_KEY` (private half of ed25519 deploy key)
- REMOVE: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`

## Dependencies

Supersedes (informational, not blocking): [260528-1700-cicd-deploy-into-github-actions](../260528-1700-cicd-deploy-into-github-actions/plan.md). That plan landed the 3-GH-secrets approach; this plan migrates away from it.

External: requires `camping89/pocketquant-config` repo to accept new layout (Phase 1 modifies it).

## Out of scope

- Validate-on-push workflow in pocketquant-config (typo guard) — future.
- Auto-redeploy via `repository_dispatch` from pocketquant-config.
- Multi-env split (dev/stag/uat) — single VPS only.
- Renaming pocketquant-config default branch from `master` to `main`.
- Migration of pocketquant-config's `.env.local` (local-dev only, untouched).
