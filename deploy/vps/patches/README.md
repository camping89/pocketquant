# Deploy Patches

One-time idempotent migration scripts run during `deploy/vps/deploy.sh`.

## Convention

- Name: `one_time_<descriptive-snake-case>.py` (Python) or `one_time_<...>.sh` (shell)
- Must be **idempotent** — safe to re-run on already-migrated data (no-op after first success)
- Invoked from `deploy/vps/deploy.sh` after app container becomes healthy
- Removed from this folder only after all environments have run them at least once

## Pattern

```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env exec -T app \
  python -m deploy.vps.patches.<script_name> || true
```

Note: requires `COPY deploy/vps/patches/ deploy/vps/patches/` in `deploy/Dockerfile` if the migration runs inside the container, OR mount the folder via compose. Default: run via mount, not bake into image.
