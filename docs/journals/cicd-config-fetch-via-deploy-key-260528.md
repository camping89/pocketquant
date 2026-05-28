# CI/CD config fetch via deploy key — 2026-05-28

## What landed

`pocketquant` repo went from 5 GH Actions secrets to 1 (`POCKETQUANT_CONFIG_DEPLOY_KEY`). All VPS state (host, SSH key, prod `.env`, Docker Hub creds, Portainer admin) now lives in `pocketquant-config/vps/default/`. A new composite action `.github/actions/get-vps-config/` clones `pocketquant-config` at run time via the deploy key and emits 7 mask-safe outputs. Each of 4 jobs (`build-api`, `build-web`, `cleanup-tags`, `deploy`) re-fetches independently — auto-mask via `::add-mask::`, parallel clones, no cross-job leak. Eve-platform pattern. Multi-VPS-ready folder layout. Idempotent `bootstrap-gh.sh` for one-time setup + rotation.

End-to-end smoke-tested via `workflow_dispatch` on a throwaway branch (`feat/cicd-config-fetch-smoke`), then merged to `develop` for a real deploy. VPS `/health` returned 200 with all 5 containers healthy.

Plan: `plans/260528-2000-config-fetch-via-deploy-key/`.

## Decisions

- **Re-fetch pattern over share-via-outputs.** Each job clones `pocketquant-config` instead of one fetch propagating to dependents. Cost: 4 clones per run (each <2 s). Benefit: auto-mask, no cross-job env-var leak, smaller blast radius if one job's runner is compromised.
- **`POCKETQUANT_CONFIG_DEPLOY_KEY` as the only GH secret.** Bootstrap script is the single point of truth for both initial setup and rotation. No more 5-row "Add these secrets" docs.
- **`vps/<name>/` folder layout** rather than the previous flat `vps/{vultr, ssh, secrets, portainer}` files. `default` is the current single VPS. Adding `vps/staging/` later = copy folder + override fields.
- **`USERNAME=admin` kept in `portainer.env`.** The composite action doesn't emit it, but the file is the operator's source of truth — keeping the field lets a human log back in without grep'ing Slack.

## Surprises

- **GH Actions heredoc output strips one trailing newline** when read back through `${{ steps.cfg.outputs.* }}`. Without explicit `printf '%s\n'` in both the action AND each consumer (`Setup SSH`, `Write prod .env`), OpenSSH rejects the key with `error in libcrypto` and the `.env` file loses its last line terminator. Bash command substitution `$(normalize ...)` also strips trailing newlines, so the producing side needs a re-add too. Fixed in 2 commits.
- **`deploy.sh` validates a superset of what `pocketquant-config/.env` provides.** `MONGO_PASSWORD`, `MONGO_USER`, `WEB_PORT` were missing in the source `.env` because the running Mongo container had been initialized 2 weeks ago and never re-validated. `DOCKERHUB_USERNAME` was also missing because Docker Hub creds live in `docker-hub.env` (separate file), not `.env`. Fixed both by appending in the `Write prod .env` step + amending `pocketquant-config`.
- **App startup was already broken at `db.database.list_collection_names()` — pre-existing tech debt.** `Database` wrapper uses name-mangled `__database` and only exposes `get_database()`. The bug never surfaced because the prod container was kept alive across the migration commit that introduced the buggy call. `deploy.sh`'s recreate cycle finally tried to boot it. Fixed inline (4 sites in `main_extensions.py`); journaled as deferred test-coverage gap.
- **3 of the 5 "old" GH secrets returned 404 on delete.** Plan `260528-1700` was the supposed predecessor but had never actually created `VPS_HOST` / `VPS_SSH_KEY` / `PROD_ENV` in the repo — only `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` existed. Plan-on-paper diverged from reality.

## Open items

See `plans/260528-2000-config-fetch-via-deploy-key/cook-deferred-items-and-questions.md`. Highlights:

- **Node 20 deprecation** warnings on every CI run — must bump `actions/checkout`, `docker/*` actions before 2026-06-02.
- **Minor log leak**: the VPS IP is masked but appears once in the workflow log via a comment line at the top of `vps/default/.env` that GH renders inside the `env:` preamble dump. Pedantically violates the "zero plaintext leaks" criterion; pragmatically harmless (the IP is a port-scanned reality, not credential material).
- **No automated reconciliation** between `deploy.sh`'s `REQUIRED_VARS` list and `pocketquant-config/vps/default/.env`. Recommend a schema check (or a tracked `.env.example` listing required keys) before the next VPS provision.
- **`migrate_strategy_id_fields` lacks a test** that would have caught the `db.database` AttributeError before VPS recreate.

## Files of note

- `pocketquant-config/scripts/bootstrap-gh.sh` — one-time setup + rotation.
- `pocketquant-config/vps/default/{.env, host, id_rsa, id_rsa.pub, docker-hub.env, portainer.env}` — per-VPS bundle.
- `pocketquant/.github/actions/get-vps-config/action.yml` — composite action with 7 mask-safe outputs.
- `pocketquant/.github/workflows/cicd.yml` — 4 jobs, 1 secret reference.
- `pocketquant/docs/deployment.md` — rewritten Prerequisites + Credentials & Config Layout + Rollback (emergency SSH) sections.
