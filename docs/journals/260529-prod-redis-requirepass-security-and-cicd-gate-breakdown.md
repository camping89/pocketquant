# Prod Redis `requirepass` security fix + CI gate exposed latent pydantic break — 2026-05-29

## What landed

Fixed critical security exposure: prod Redis (207.148.79.60:53679) was publicly reachable with NO authentication. Anyone could `FLUSHALL`, `CONFIG SET dir` (RCE), or exfiltrate cached data. Added `--requirepass ${REDIS_PASSWORD}` (32-byte base64, no `/` or `+` chars) to `deploy/compose.prod.yml` as sole access control. Kept public port (user decision — no static IP for allowlisting, no SSH tunnel).

Dependent changes shipped together:
- `compose.prod.yml` healthcheck: `redis-cli -a ${REDIS_PASSWORD} --no-auth-warning ping`
- `deploy/vps/11-verify.sh`: redis check now uses `-a "${REDIS_PASSWORD:-}"` (default prevents `set -u` abort)
- `deploy/vps/10-deploy.sh`: added fail-closed guard — refuse deploy if `REDIS_PASSWORD` empty (empty requirepass silently disables auth while healthcheck still PONGs, silently reopening the exposure)
- `pocketquant-config/vps/default/.env`: added `REDIS_PASSWORD` + `REDIS_URL=redis://:<pw>@redis:6379/0`
- `docs/security-redis-exposure.md`: status Resolved, residual-risk notes (online brute force, future auth-bypass CVE, password visible via docker inspect)

Plan: `plans/260529-secure-prod-redis-requirepass/`.

Second push confirmed: external `ping` → `NOAUTH Authentication required`, auth `ping` → `PONG`. FLUSHALL'd 8 cache-only keys (`bar:current:*`, `quote:latest:*`, `rate_limit:*`) — all app-repopulated, Mongo-backed.

## The brutal reality

**First push FAILED.** Deploy was blocked by `tests` job returning 27 failed + 17 errors, all `pydantic ValidationError: 11 validation errors for Settings`. Prod stayed unauth for ~40 minutes until fix landed. The problem: a 9bdbc48 commit (unrelated, riding under the 1-line Redis change) introduced a brand-new CI `tests` job that had NEVER run before. That job hits structlog's `add_app_context` processor, which calls `get_settings()` → bare `Settings()` at log initialization time. Locally, pytest passed because direnv supplies the `.env` vars; CI choked because it had none. **The security gate was broken by a latent break that CI's absence-of-tests had masked.**

## Technical details

- **Exposure:** Redis `INFO replication` responds without auth, leaking role/version/connected-slaves. Any actor on the network can write/delete/expire all keys.
- **Root of latent break:** `packages/pocketquant-api/tests/conftest.py` had no `pytest_configure` hook to seed env vars. The `add_app_context` processor depends on `settings.trace_enabled`, `settings.log_level`, etc. at log init (before any test runs). Without the vars, pydantic rejects the Settings object on construction.
- **Why it wasn't caught:** 27 failed tests across 4 test files, 11 missing fields in one call to Settings. The first error cascaded: `conftest.py` import → `main_extensions.py` imports `structlog.wrap_logger()` → processor chain evaluates → Settings() called → missing required fields → ValidationError → pytest collection failure → entire suite fails.
- **Fix:** seeded placeholder vars in `pytest_configure` using `os.environ.setdefault` (preserves real dev env, allows hermetic CI). Placed AFTER the existing production-URL guard (`assert not <prod-url> in settings...`) so the guard still fires on injected prod URLs. Verified in scrubbed shell (`env -i pytest`): 113 passed / 12 skipped / 0 failed, guard still rejects.

## Decisions

- **`requirepass` only, not ACL.** ACL is available in Redis 6+; we run Redis 7. Tradeoff: requirepass is simpler (1 password instead of per-user rules), weaker (no granular perms per key/command), but sufficient for a single-app private cache. Added residual-risk doc.
- **Fail-closed guard in deploy script.** Plan said "no edits to 10-deploy.sh"; added one anyway (empty password check). Justification: the guard protects the security control itself — if password var is unset, requirepass becomes a no-op, silently reopening the hole. Better to fail the deploy and alert the operator.
- **Prod-only scope.** Local/test Redis intentionally runs no-auth (DX, test isolation). Prod-only `.env` inclusion ensures no cross-env leakage.
- **Plain password string (not Redis ACL credentials):** Avoids dependency on Redis ACL feature maturity; password goes into `REDIS_URL` as `redis://:<pw>@host:port/db`.

## Lessons

1. **CI gate absence masks latent breaks.** A `tests` job that never runs is as good as no gate. We introduced it in 9bdbc48 (unrelated to Redis fix), but it had zero coverage until it actually ran in the deploy pipeline. Lesson: land CI jobs in a separate PR with a dry run first, or enable them on a branch before merging to main.

2. **Env-dependent initialization is fragile.** Pydantic models, structlog processors, anything that reads environment at import-time needs a test-harness fallback. Using `os.environ.setdefault` in `pytest_configure` is the pattern: seed placeholders, let real env override, keep it hermetic.

3. **Audit the handoff between security controls.** The requirepass + healthcheck + deploy guard are three separate points. If any breaks, the others still allow the container to reach "healthy" and the deploy to proceed. Documented the failure mode chain in `docs/security-redis-exposure.md`.

## Files of note

- `deploy/compose.prod.yml` — `redis` service command + healthcheck
- `deploy/vps/10-deploy.sh` — fail-closed REDIS_PASSWORD guard (new)
- `deploy/vps/11-verify.sh` — redis-cli check
- `pocketquant-config/vps/default/.env` — REDIS_PASSWORD + REDIS_URL (separate repo)
- `packages/pocketquant-api/tests/conftest.py` — pytest_configure with env seeding
- `docs/security-redis-exposure.md` — residual risks & mitigation

## Next steps

- Monitor auth failures in prod Redis logs (will appear as `NOAUTH` in client error paths). Establish baseline within 1 week.
- Regenerate REDIS_PASSWORD before 2026-06-05 (share via existing secure channel, not git).
- In next CI refresh: add linting/format jobs to the gate so failures are caught early (current gate is too shallow: only build-api, build-web, deploy).
