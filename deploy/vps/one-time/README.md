# One-Time Scripts

Scripts that run **once per environment**, not on every deploy.

## Contents

- `00-server-setup.sh` — fresh-VPS provisioning (Docker, deploy user, firewall, fail2ban, SSH hardening). Run once as root on a new VPS. See [deployment.md → VPS Migration (new VPS)](../../../docs/deployment.md).
- `one_time_<name>.py` / `one_time_<name>.sh` — idempotent data/schema migrations, invoked from `deploy/vps/10-deploy.sh` after the app container becomes healthy.

## Migration script convention

- Name: `one_time_<descriptive-snake-case>.py` (Python) or `one_time_<...>.sh` (shell)
- Must be **idempotent** — safe to re-run on already-migrated data (no-op after first success)
- Invoked from `deploy/vps/10-deploy.sh` after app container becomes healthy
- Removed from this folder only after all environments have run them at least once

## Migration pattern

```bash
docker compose -f deploy/compose.prod.yml --env-file deploy/.env exec -T app \
  python -m deploy.vps.one-time.<script_name> || true
```

Note: requires `COPY deploy/vps/one-time/ deploy/vps/one-time/` in `deploy/Dockerfile` if the migration runs inside the container, OR mount the folder via compose. Default: run via mount, not bake into image.
