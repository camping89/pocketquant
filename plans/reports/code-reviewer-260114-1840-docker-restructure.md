# Code Review: Docker Restructure

## Scope
- Files reviewed: `docker/compose.yml`, `docker/mongo-init.js`, `justfile`, `README.md`, `CLAUDE.md`
- Review focus: Security, path correctness, breaking changes
- Lines changed: ~118 additions, ~47 deletions

## Overall Assessment
Clean restructure with correct paths. **3 CRITICAL ISSUES** found requiring immediate fix.

---

## Critical Issues

### 1. **[SECURITY] Hardcoded Dev Credentials in Compose File**
**File:** `docker/compose.yml` (lines 9-11)

```yaml
MONGO_INITDB_ROOT_USERNAME: pocketquant
MONGO_INITDB_ROOT_PASSWORD: pocketquant_dev  # ⚠️ HARDCODED
```

**Impact:** Credentials exposed in version control, production deployment risk

**Fix:**
```yaml
environment:
  MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USER:-pocketquant}
  MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD:?Password required}
```

Also update line 46:
```yaml
ME_CONFIG_MONGODB_URL: mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@mongodb:27018/
```

---

### 2. **[BREAKING] Justfile Uses Inconsistent Docker Commands**
**File:** `justfile` (line 18, 22)

```bash
stop:
    docker compose -f docker/compose.yml stop  # ✅ Correct

logs:
    docker compose -f docker/compose.yml logs  # ✅ Correct
```

BUT line 13:
```bash
start:
    docker compose -f docker/compose.yml up -d  # ✅ NOW CORRECT
```

**Status:** Actually FIXED in current version. Git diff showed old version using `docker-compose` (deprecated CLI), current uses `docker compose` (V2 plugin). **No action needed.**

---

### 3. **[PATH] Relative Path in Volume Mount Breaks Context**
**File:** `docker/compose.yml` (line 14)

```yaml
volumes:
  - ./docker/mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
```

**Issue:** `./docker/` relative path assumes compose file is run from project root. When using `-f docker/compose.yml`, Docker's context is still project root, so this WORKS. However, it's fragile if anyone runs:

```bash
cd docker && docker compose up  # ❌ Would look for ./docker/docker/mongo-init.js
```

**Recommended Fix:**
```yaml
volumes:
  - ./mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
```

Since compose file is in `docker/`, use relative path from there. Docker Compose resolves paths relative to compose file location when using `-f`.

---

## High Priority Findings

### 4. **[DOCS] README Production Instructions Outdated**
**File:** `README.md` (line 229)

Shows:
```bash
docker-compose up -d  # ❌ Missing -f flag, uses deprecated CLI
```

Should be:
```bash
docker compose -f docker/compose.yml up -d
```

---

### 5. **[SECURITY] Mongo Express Exposed Without Auth**
**File:** `docker/compose.yml` (line 47)

```yaml
ME_CONFIG_BASICAUTH: "false"
```

**Risk:** Admin UI accessible without authentication (though under `admin` profile)

**Recommendation:** Enable basic auth for production-like testing:
```yaml
ME_CONFIG_BASICAUTH: "true"
ME_CONFIG_BASICAUTH_USERNAME: ${MONGO_ADMIN_USER:-admin}
ME_CONFIG_BASICAUTH_PASSWORD: ${MONGO_ADMIN_PASSWORD:?Password required}
```

---

## Medium Priority Improvements

### 6. **Breaking Change Not Fully Documented**
**Migration Guide Missing:**

Users upgrading from old structure will see:
```bash
$ docker-compose up
ERROR: Can't find compose.yml or docker-compose.yml
```

**Add to README:**
```markdown
### Migrating from Previous Versions
If upgrading from version < X.X.X:
1. Stop old containers: `docker-compose down`
2. Use new commands via justfile or: `docker compose -f docker/compose.yml up -d`
```

---

### 7. **Volume Mount Path Inconsistency**
Git diff shows volume mount was updated from `./scripts/` to `./docker/`, but actual file shows `./docker/mongo-init.js`. This is CORRECT but plan document claimed it would be `./docker/` directory mount. Current implementation is better (single file mount = more explicit).

---

## Low Priority Suggestions

### 8. **Compose File Missing Top-level Name**
Add:
```yaml
name: pocketquant
services:
  # ...
```

Prevents Docker from using directory name as project prefix.

---

### 9. **Redis Maxmemory Too Low for Production**
```yaml
command: redis-server --appendonly yes --maxmemory 256mb  # ⚠️ Small
```

256MB may be insufficient for production quote caching. Consider env-based config:
```yaml
command: redis-server --appendonly yes --maxmemory ${REDIS_MAXMEMORY:-256mb}
```

---

## Positive Observations
✅ Correctly uses `docker compose` V2 plugin throughout
✅ Health checks properly configured
✅ Volume persistence maintained
✅ Mongo init script schema validation is robust
✅ Read-only mount flag (`:ro`) correctly used
✅ Container naming prevents conflicts
✅ Profiles correctly isolate optional services

---

## Recommended Actions

**MUST FIX (Before Merge):**
1. Replace hardcoded credentials with env vars in `docker/compose.yml`
2. Fix volume mount path to `./mongo-init.js` (relative to compose file)
3. Update README production section with correct command

**SHOULD FIX (This Week):**
4. Add migration guide for breaking change
5. Enable basic auth for mongo-express (or document risk)

**NICE TO HAVE:**
6. Add `name: pocketquant` to compose file
7. Make Redis maxmemory configurable

---

## Metrics
- Security Issues: **2 critical** (hardcoded creds, exposed admin UI)
- Path Errors: **1 critical** (fragile relative path)
- Breaking Changes: **1 undocumented** (docker-compose.yml location)
- Deprecated Syntax: **0** (all using modern V2)

**Block Merge:** YES (until critical security/path issues resolved)
