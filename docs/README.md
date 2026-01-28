# PocketQuant Documentation Index

**Last Updated:** 2026-01-21

Welcome to PocketQuant documentation. Start below based on your role.

## Quick Navigation

### For New Developers
1. Read [README.md](../README.md) for quick start (5 min)
2. Read [codebase-summary.md](./codebase-summary.md) for module overview (10 min)
3. Read [code-standards.md](./code-standards.md) for patterns (15 min)
4. Read [system-architecture.md](./system-architecture.md) for deep dive (20 min)

**Total onboarding: ~50 minutes**

### For Code Reviewers
- Reference: [code-standards.md](./code-standards.md) - Patterns & quality checklist
- Verify: Code follows documented patterns
- Check: Test coverage ≥80%

### For Feature Developers
- Architecture: [system-architecture.md](./system-architecture.md) - Integration points
- Patterns: [code-standards.md](./code-standards.md) - How to write code
- Examples: [codebase-summary.md](./codebase-summary.md) - Similar modules

### For Project/Product Managers
- Status: [project-overview-pdr.md](./project-overview-pdr.md) - Requirements & implementation
- Roadmap: [TODO.md](../TODO.md) - Priorities & next steps

---

## Document Guide

### [README.md](../README.md) (199 LOC)
**User-facing entry point**

Quick start guide, API examples, setup instructions, development commands.

**Use when:** Getting started, need quick reference

**Contains:**
- Feature overview
- Quick start (30 seconds)
- API examples (curl)
- Architecture diagram
- Development setup
- Documentation index

---

### [codebase-summary.md](./codebase-summary.md) (250 LOC)
**Codebase reference**

High-level module breakdown, codebase statistics, entry points, configuration.

**Use when:** Understanding project structure, finding modules

**Contains:**
- Architecture overview (Vertical Slice)
- Core infrastructure (964 LOC breakdown)
  - Database: PyMongo async, MongoDB, connection pooling
  - Cache: redis-py, JSON serialization
  - Logging: structlog, JSON format
  - Jobs: APScheduler, job definitions
- Market data feature (2,714 LOC breakdown)
  - API: 472 LOC, routes
  - Services: 848 LOC, business logic
  - Repositories: 428 LOC, data access
  - Models: 289 LOC, Pydantic definitions
  - Providers: 572 LOC, TradingView integrations
  - Jobs: 118 LOC, scheduled sync
- Startup sequence (11 steps)
- Key decisions explained
- Configuration variables
- Entry points (dev/prod)
- TODOs & limitations

**Key Stats:**
- Total: ~3,600 LOC (33 Python files)
- Largest module: 472 LOC (routes.py)
- All others: <400 LOC (except justified exceptions)

---

### [system-architecture.md](./system-architecture.md) (482 LOC)
**Architecture & design documentation**

Infrastructure patterns, data pipelines, concurrency model, deployment considerations.

**Use when:** Understanding how things work, designing new features, troubleshooting

**Contains:**
- High-level architecture diagram
- Infrastructure singletons explained
  - Database lifecycle, API, connection pooling
  - Cache design, serialization, TTL strategy
  - Logging pipeline, output formats
  - Job scheduler configuration
- Three data pipelines
  1. Historical sync: REST → MongoDB
  2. Real-time quotes: WebSocket → Aggregator → MongoDB + Redis
  3. Background jobs: APScheduler → per-symbol sync
- Concurrency model (event loop, thread pool, locks)
- Resource lifecycle (startup → shutdown)
- Integration points (TradingView, MongoDB, Redis)
- Error handling (transient, permanent, silent)
- Production considerations (monitoring, scaling, security)
- Performance characteristics (latency, throughput, memory)

**Key Diagrams:**
- 7-layer architecture overview
- Startup sequence (11 steps)
- Data flow pipeline

---

### [code-standards.md](./code-standards.md) (549 LOC)
**Development guidelines & best practices**

Architecture patterns, code organization, testing, quality standards, performance.

**Use when:** Writing code, code review, testing, debugging

**Contains:**
- 5 architecture patterns (with examples)
  1. Vertical Slice Architecture
  2. Singleton Infrastructure (class methods)
  3. Repository Pattern (stateless)
  4. Service Pattern (per-request vs singleton)
  5. Provider Pattern (external APIs)
- Code organization
  - File naming (kebab-case)
  - Module size (<200 LOC target)
  - Import organization
- Commenting standards (DO/DO NOT)
  - DO: WHY, constraints, gotchas, algorithms
  - DO NOT: Obvious code, variable restating
- Type hints (mypy compliance)
- Error handling (try-except, propagation)
- Logging with structlog (context variables)
- Testing standards (fixtures, mocking, 80% coverage)
- Code quality tools (ruff, mypy, pytest)
- Performance tips (blocking I/O, bulk ops, caching, concurrency)
- Configuration & secrets (.env usage)
- Quality checklist (pre-commit validation)
- Deprecated patterns (5 anti-patterns)

**File Size Targets:**
```
quote_aggregator.py:     368 LOC  ✅ (algorithm exception)
routes.py:               472 LOC  ⚠️  (split candidate)
quote_service.py:        236 LOC  ✅
data_sync_service.py:    244 LOC  ✅
```

---

### [project-overview-pdr.md](./project-overview-pdr.md) (380 LOC)
**Project vision, requirements, and status**

Product goals, requirements (functional & non-functional), implementation status, roadmap preview.

**Use when:** Understanding project goals, requirements, what's complete

**Contains:**
- Project vision (5 strategic goals)
- Functional requirements (6 main features)
  - F1: Historical data sync
  - F2: Real-time quotes
  - F3: Multi-interval aggregation
  - F4: Data retrieval
  - F5: Symbol registry
  - F6: Background jobs
- Non-functional requirements (6 categories)
  - Performance, reliability, observability, security, maintainability, scalability
- Implementation status (per feature)
  - All core features 100% complete
  - Test coverage by component (avg 80%)
  - Module breakdown with LOC
- Success criteria (v1.0 checklist)
- Known limitations & TODOs (3 priority levels)
- Roadmap phases (Phase 2-5 preview)
- Development practices (branching, commits, code review)

**Status Summary:**
- v1.0: Core features complete ✅
- Documentation: 90% complete
- Test coverage: 80% average
- Code quality: 100% type coverage

---

---

## Cross-References

### Reading Paths by Role

**Backend Engineer:**
1. codebase-summary.md (structure)
2. code-standards.md (patterns)
3. system-architecture.md (design)

**Frontend Engineer (future):**
1. README.md (quick start)
2. system-architecture.md (API contracts)
3. code-standards.md (quality expectations)

**QA/Tester:**
1. project-overview-pdr.md (requirements)
2. code-standards.md (test expectations)

**Tech Lead:**
1. system-architecture.md (design)
2. code-standards.md (quality)
3. project-overview-pdr.md (scope)

**Product Manager:**
1. README.md (overview)
2. project-overview-pdr.md (requirements)

---

## Documentation Statistics

| Document | Purpose | Audience |
|----------|---------|----------|
| README.md | Quick start | All |
| codebase-summary.md | Reference | Developers |
| code-standards.md | Guidelines | Developers, Reviewers |
| system-architecture.md | Design | Architects, Developers |
| project-overview-pdr.md | Requirements | All |
| deployment-guide.md | Production setup | DevOps |

---

## Key Concepts Explained

### Vertical Slice Architecture
Each feature (e.g., market_data) contains all layers: API, services, repositories, models, providers, jobs.

**Why:** Clear separation, easy to add features without affecting others.

### Singleton Infrastructure
Database, Cache, JobScheduler are class-based singletons with class method APIs.

**Why:** Single expensive connection per resource type, initialized once, accessed everywhere.

### Repository Pattern
Stateless data access via class methods only.

**Why:** Easy to test, no complex lifecycle, functions as data mapper.

### Service Pattern
Per-request instantiation for stateless logic, singleton for persistent state.

**Why:** Per-request is simple and testable; singleton is needed for WebSocket state.

### Thread Pool Isolation
TradingView blocking I/O runs in ThreadPoolExecutor (max 4 workers).

**Why:** Blocking code doesn't block async event loop, prevents app hangs.

---

## Getting Help

### Common Questions

**Q: Where do I add a new feature?**
A: Create `/src/features/{feature}/` following market_data structure. See code-standards.md.

**Q: How do I add an endpoint?**
A: Add to `/src/features/{feature}/api/` routes. Follow patterns in system-architecture.md.

**Q: How do I test code?**
A: See code-standards.md section "Testing Standards". Run `pytest`.

**Q: Where is the production deployment guide?**
A: See [deployment-guide.md](./deployment-guide.md).

**Q: What's the testing strategy?**
A: See code-standards.md "Testing Standards". Target: 80% coverage, unit + integration.

**Q: How do I handle errors?**
A: See code-standards.md "Error Handling". Be specific with exceptions, log with context.

**Q: Should I use DI or singletons?**
A: Routes use FastAPI Depends(). Infrastructure uses class-method singletons. See system-architecture.md.

**Q: How do I cache data?**
A: Use `Cache.set/get/delete_pattern()`. See system-architecture.md "Cache" section.

### Troubleshooting

**App won't start:**
- Check MongoDB is running: `docker ps`
- Check Redis is running: `docker ps`
- See CLAUDE.md for setup commands

**Tests failing:**
- Check fixtures: conftest.py
- Check mocking: code-standards.md "Mocking Singletons"
- Run verbose: `pytest -v --tb=short`

**Type errors:**
- Run mypy: `mypy src/`
- See code-standards.md "Type Hints"

**Linting errors:**
- Run ruff: `ruff check . --fix`
- See code-standards.md "Linting"

---

## Keeping Documentation Updated

When you make code changes:

1. **Architecture changed:** Update system-architecture.md
2. **Patterns changed:** Update code-standards.md
3. **Module added:** Update codebase-summary.md
4. **Requirements change:** Update project-overview-pdr.md

**Pre-commit check:** See if any docs need updating based on code changes.

---

## Related Files

- **CLAUDE.md** - Global development guidelines (read first)
- **pyproject.toml** - Python project configuration
- **.env.example** - Configuration template
- **docker/compose.yml** - Infrastructure setup
- **tests/** - Test suite
- **src/** - Source code (follow patterns in docs)

---

## Version History

| Date | Updates |
|------|---------|
| 2026-01-21 | Initial documentation suite (5 docs, 2,324 LOC) |

---

**Last Updated:** 2026-01-21 | **Maintained By:** docs-manager | **Next Review:** 2026-02-21
