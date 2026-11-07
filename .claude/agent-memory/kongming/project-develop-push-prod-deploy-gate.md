---
name: develop-push-prod-deploy-gate
description: As of 2026-10-16 every develop push built, overwrote Docker Hub :latest and deployed to the prod VPS; fix recommended = master-only gates + per-ref concurrency in cicd.yml
metadata:
  type: project
---

On 2026-10-16 the operator asked to guarantee a `develop` push never deploys to the prod VPS. Audit found (verified): `deploy`, `build-*`, `cleanup-tags` all ran on develop; Docker Hub `latest` == develop `sha-20baa15`; no master image left on Hub; a develop push cancelled an in-flight master deploy on 2026-07-04 via the shared static `concurrency.group: deploy`. Recommended fix: `if: github.ref == 'refs/heads/master'` on the four non-test jobs and `group: ${{ github.workflow }}-${{ github.ref }}`; then push master once to re-point `latest`. Report: `D:/w/_me/algotrading/plans/reports/kongming-261016-0836-develop-push-no-vps-deploy.md`.

**Why:** single-operator project trading live money (OKX); no staging; develop had been the de-facto prod branch.

**How to apply:** before advising on any CI/deploy change, check whether this fix landed (`git show origin/develop:.github/workflows/cicd.yml`, look for the master-only `if` on `build-app`). If it did, treat master as the only prod branch; if not, every develop push is still a prod deploy and plans must be push-safe per commit. Related: [[plan-verify-git-stat-truncation]].
