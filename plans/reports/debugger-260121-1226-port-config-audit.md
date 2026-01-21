# Port Configuration Audit Report

## Executive Summary

**Issue**: Port configuration (8765) scattered across multiple files and documentation, with inconsistencies in archived deployment plans using port 8000.

**Root Cause**: No centralized source of truth for port configuration. Documentation, scripts, and examples hardcode port values instead of referencing the canonical config.

**Impact**:
- Configuration drift risk when changing default port
- Inconsistent developer experience
- Maintenance overhead updating multiple locations
- Confusion from archived plans showing different port (8000 vs 8765)

**Recommended Solutions**:
1. Single source of truth: `src/config.py` (already exists)
2. Update all documentation to reference environment variable
3. Remove hardcoded ports from examples
4. Clarify archived plan discrepancies

---

## Technical Analysis

### 1. Port Definitions by Category

#### A. Canonical Configuration (Source of Truth)
**Location**: `src/config.py`
- **Line 22**: `api_port: int = 8765`
- **Line 21**: `api_host: str = "0.0.0.0"`
- Uses Pydantic Settings with `.env` file support
- Environment variable: `API_PORT`

**Location**: `.env.example`
- **Line 13**: `API_PORT=8765`
- **Line 12**: `API_HOST=0.0.0.0`

**Status**: ✅ Correct - Single source of truth pattern

---

#### B. Application Usage (Correct)
**Location**: `src/main.py`
- **Line 109**: `host=settings.api_host`
- **Line 110**: `port=settings.api_port`
- **Line 111**: `reload=settings.environment == "development"`

**Status**: ✅ Correct - Uses Settings object

---

#### C. Development Tools (Mixed)

**Location**: `justfile`
- **Line 28**: `start port="8765":` - Hardcoded default parameter
- **Line 30**: `{{uvicorn}} src.main:app --reload --host 0.0.0.0 --port {{port}}`
- Allows override: `just start 9000`

**Status**: ⚠️ Partially correct - Default hardcoded but overridable

**Location**: `.vscode/launch.json`
- **Line 8-9**: Uses uvicorn module without explicit port
- **Line 11**: Uses `.env` file via `envFile`

**Status**: ✅ Correct - Reads from `.env`

---

#### D. Documentation (Scattered Hardcoded References)

**Location**: `README.md`
- **Line 26**: `http://localhost:8765/api/v1/docs`
- **Line 68, 77, 80, 85, 91, 94**: Multiple curl examples with `localhost:8765`
- **Line 155**: `.venv/bin/uvicorn src.main:app --workers 4 --host 0.0.0.0 --port 8765`

**Location**: `.claude/CLAUDE.md`
- **Line 118**: `Base URL: /api/v1 (default port: 8765)`

**Location**: `docs/codebase-summary.md`
- **Line 237**: `uvicorn src.main:app --host 0.0.0.0 --port 8765 --workers 4`
- **Line 238-239**: URLs with `localhost:8765`

**Location**: `docs/project-overview-pdr.md`
- **Line 369**: `uvicorn src.main:app --workers 4 --host 0.0.0.0 --port 8765`

**Location**: `docs/system-architecture.md`
- **Line 431**: `uvicorn src.main:app --workers 4 --port 8765`

**Status**: ❌ Problematic - Hardcoded in 15+ locations

---

#### E. Infrastructure (Different Services)

**Location**: `docker/compose.yml`
- **Line 9**: MongoDB: `27018:27018`
- **Line 28**: Redis: `6379:6379`
- **Line 44**: Mongo Express: `8081:8081`
- **Note**: API port (8765) not in Docker config - runs on host

**Status**: ✅ Correct - Infrastructure services use different ports

---

#### F. Archived/Historical Plans (Inconsistent Port)

**Location**: `plans/260108-1144-vps-deployment/plan.md`
- **Line 304**: `EXPOSE 8000`
- **Line 308**: `http://localhost:8000/health`
- **Line 311**: `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`

**Location**: `plans/archived/260114-1831-docker-restructure/plan.md`
- References to port 8000 in archived deployment plans

**Status**: ⚠️ Historical - Old deployment plans used port 8000, now using 8765

---

### 2. Configuration Duplication Matrix

| Location | Type | Port Value | Source | Issue |
|----------|------|------------|--------|-------|
| `src/config.py:22` | Code | 8765 | Settings class | ✅ Source of truth |
| `.env.example:13` | Config | 8765 | Env template | ✅ Correct reference |
| `src/main.py:110` | Code | `settings.api_port` | From Settings | ✅ Correct usage |
| `justfile:28` | Script | "8765" | Default param | ⚠️ Hardcoded default |
| `README.md` (15+ refs) | Docs | 8765 | Hardcoded | ❌ Duplication |
| `.claude/CLAUDE.md:118` | Docs | 8765 | Hardcoded | ❌ Duplication |
| `docs/*.md` (6+ refs) | Docs | 8765 | Hardcoded | ❌ Duplication |
| `plans/**/*.md` (25+ refs) | Plans | 8765 | Hardcoded | ⚠️ Documentation |
| Archived plans | Plans | 8000 | Old value | ⚠️ Historical |

---

### 3. Environment Variable Usage Pattern

**Current Flow**:
```
.env file (API_PORT=8765)
    ↓
src/config.py (Pydantic Settings)
    ↓
src/main.py (uvicorn.run uses settings.api_port)
```

**Gaps**:
- `justfile` doesn't read from `.env`, uses hardcoded default
- All documentation shows hardcoded `8765` instead of `$API_PORT`
- curl examples in README don't mention port is configurable

---

### 4. Config File Locations

**Primary Config Files**:
1. `src/config.py` - Pydantic Settings class (lines 8-46)
2. `.env.example` - Environment variable template (line 13)
3. `.env` - User's local config (gitignored, not in repo)

**Config-Related Files**:
- `docker/compose.yml` - Infrastructure ports (27018, 6379, 8081)
- `.vscode/launch.json` - Debug config (uses envFile)
- `pyproject.toml` - No port config
- `justfile` - Development scripts with hardcoded default

**No Additional Config Files Found**:
- No `config.yaml`, `config.json`, or other config formats
- No separate dev/staging/prod config files
- No Docker env files with API_PORT

---

## Duplication Summary

### Critical Issues
1. **README.md**: 15+ hardcoded port references
2. **docs/*.md**: 6 files with hardcoded ports
3. **justfile**: Default parameter hardcoded

### Total Count by File Type
- **Documentation**: ~25 hardcoded references to port 8765
- **Plans/Reports**: ~40+ references (mix of 8765 and 8000)
- **Code**: 1 hardcoded default in justfile
- **Config**: 2 locations (source + example)

---

## Recommended Actions

### Immediate Fixes

1. **Update justfile**
   ```just
   # Read from env or use fallback
   default_port := env_var_or_default('API_PORT', '8765')
   start port=default_port:
       {{uvicorn}} src.main:app --reload --host 0.0.0.0 --port {{port}}
   ```

2. **Update README.md**
   - Add note at top: "Default port: 8765 (configurable via API_PORT in .env)"
   - First curl example: `curl http://localhost:${API_PORT:-8765}/health`
   - Later examples can keep hardcoded 8765 for simplicity with caveat

3. **Update .claude/CLAUDE.md**
   ```markdown
   Base URL: `/api/v1` (default port: 8765, set via API_PORT env var)
   ```

4. **Add to docs/system-architecture.md**
   Section on "Configuration Management" explaining:
   - Single source: `src/config.py`
   - Override via `.env` file
   - All settings available as env vars

### Long-term Improvements

1. **Documentation Strategy**
   - Add `docs/configuration.md` with all env vars
   - Reference config.py as source of truth
   - Document override mechanisms

2. **Validation Script**
   - Add to CI/CD: Check docs don't contradict config.py defaults
   - Lint script to find hardcoded ports in docs

3. **Docker Compose Enhancement**
   - Add optional API service to docker/compose.yml
   - Use `API_PORT` env var in compose file
   - Allow local dev entirely in Docker

---

## Unresolved Questions

1. **Why port 8000 in archived deployment plans?**
   - Was there a migration from 8000 to 8765?
   - Should archived plans be updated with a note?

2. **Should justfile read .env file?**
   - Just doesn't natively support .env files
   - Could source .env in shell or document override: `API_PORT=9000 just start`

3. **Production deployment port strategy?**
   - VPS deployment plans show port 8000
   - Nginx proxy would handle external port mapping
   - Internal port (8765) shouldn't matter if behind proxy

4. **Should documentation use variable syntax?**
   - Trade-off: `${API_PORT:-8765}` vs hardcoded `8765`
   - Hardcoded easier to copy-paste
   - Variable syntax more accurate but harder to read

5. **MongoDB port discrepancy?**
   - Config shows `27018` but standard MongoDB is `27017`
   - Intentional to avoid conflicts with local MongoDB instances?
   - Should be documented in docker/compose.yml comments
