# Security: Redis Public Exposure (No Auth)

**Severity:** High
**Status:** Resolved 2026-05-29 (requirepass; public port retained by decision)
**Discovered:** 2026-05-29

## Issue

Production Redis is published on a public IP with **no password**.

- Bind/published: `207.148.79.60:53679` (host-published port of the `redis` container in `deploy/compose.prod.yml`).
- `REDIS_URL=redis://207.148.79.60:53679/0` — no credentials.
- `redis-server` command in compose has **no `--requirepass`**.

Anyone who can reach that port can read every cached value and run
`FLUSHALL`, `CONFIG SET`, `KEYS *`, etc. For an algo-trading system this means
cache poisoning, data exfiltration, and trivial DoS of the cache layer.

Contrast: MongoDB on the same VPS *does* enforce auth
(`mongodb://pocketquant:<pass>@...`). Redis is the gap.

## Impact

- **Confidentiality:** all cached market data / session / computed state readable.
- **Integrity:** attacker writes arbitrary keys → app reads poisoned cache.
- **Availability:** `FLUSHALL` or memory pressure (`maxmemory 100mb` + `allkeys-lru`) trivially abused.
- **Lateral:** `CONFIG SET dir` / `SAVE` RCE-style attacks are possible on unauth Redis.

## Fix (recommended order)

### 1. Require a password (do this regardless of network controls)

`deploy/compose.prod.yml` → `redis` service `command`:

```yaml
command: redis-server --appendonly yes --maxmemory 100mb --maxmemory-policy allkeys-lru --requirepass ${REDIS_PASSWORD}
```

Add `REDIS_PASSWORD` to the prod env source and update the URL:

- `pocketquant-config/vps/default/.env` (prod, internal):
  ```
  REDIS_PASSWORD=<strong-random>
  REDIS_URL=redis://:<strong-random>@redis:6379/0
  ```

> Note the `:` before the password — Redis URLs use an empty username.
>
> **Prod-only by decision.** Local dev Redis (`compose.local.yml`,
> `pocketquant-config/local/all-local.env`, `pocketquant/.env`) stays no-auth on
> localhost — do NOT mirror `--requirepass` there.

### 2. Restrict network exposure (defense in depth)

Pick one:

- **Best:** stop publishing Redis to the host at all. Remove the `ports:` block
  from the `redis` service — the app container reaches it over the internal
  docker network (`redis:6379`) and never needs the public port. Only keep a
  published port if external tools (RedisInsight) genuinely need it.
- **If a published port is required:** bind to loopback only
  (`127.0.0.1:53679:6379`) and tunnel over SSH, **or** firewall the port (ufw /
  cloud security group) to your dev IP only.

### 3. Rotate

After enabling auth, treat the prior unauth window as compromised: rotate any
secrets/sessions that were cached, and `FLUSHALL` once under new auth to drop
any attacker-planted keys.

## Verification

```bash
# From an untrusted network — should now FAIL with NOAUTH:
redis-cli -h 207.148.79.60 -p 53679 ping
# (auth) -> should PONG:
redis-cli -h 207.148.79.60 -p 53679 -a "$REDIS_PASSWORD" ping
```

## Affected files (prod only)

- `deploy/compose.prod.yml` — `redis` service `command` + `healthcheck`.
- `deploy/vps/10-deploy.sh` — assert `REDIS_PASSWORD` non-empty before `up`.
- `deploy/vps/11-verify.sh` — Redis check passes `-a "$REDIS_PASSWORD"`.
- `pocketquant-config/vps/default/.env` — `REDIS_PASSWORD`, `REDIS_URL`.

Local dev (`compose.local.yml`, `pocketquant-config/local/all-local.env`, `pocketquant/.env`)
is intentionally left no-auth — not affected.

## Resolution (2026-05-29)

`requirepass` applied as the **sole** access control:

- `deploy/compose.prod.yml` redis `command` now ends with `--requirepass ${REDIS_PASSWORD}`;
  healthcheck authenticates with `-a ${REDIS_PASSWORD} --no-auth-warning`.
- `pocketquant-config/vps/default/.env` carries `REDIS_PASSWORD` (32-byte base64,
  `openssl rand -base64 32`) and `REDIS_URL=redis://:<pw>@redis:6379/0`.
- `deploy/vps/11-verify.sh` Redis check passes `-a "$REDIS_PASSWORD"`.
- Rotated post-deploy: `FLUSHALL` once under new auth to drop any keys planted
  during the prior unauth window.

**Network exposure decision:** loopback-only bind / SSH tunnel was **rejected** —
no static dev IP available for allowlisting, and an external tool needs the
published port. The public `0.0.0.0` publish on `207.148.79.60:53679` is
**retained**; the 32-byte random password is the only barrier.

**Residual risk (accepted):** online brute force (Redis does no AUTH
rate-limiting) and any future Redis auth-bypass CVE remain exploitable against
the open port. Mitigated only by password entropy. Revisit removing the `ports:`
block (option 2-best below) if the external-tool need ends.

**Secret visibility (inherent to `--requirepass` on the command line):** the
password appears in `docker inspect` output and the container process list, and
is therefore readable by anyone with docker-socket access. Portainer is
published (`${PORTAINER_PORT}`) with `/var/run/docker.sock` mounted, so a
Portainer compromise also exposes the Redis password. `--no-auth-warning` only
prevents the password from leaking into Redis/healthcheck *logs*, not the
process list. Acceptable given the same socket already grants full container
control; noted so the password is treated as compromised if the socket is.

## Open questions

- Does any external tool actually need the published Redis port? If not, option
  2-best (remove `ports:`) closes the exposure entirely with no tunneling.
