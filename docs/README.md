# PocketQuant Documentation Index

**Last Updated:** 2026-02-12 | **Codebase:** 14,393 LOC (213 files) | **Test Coverage:** 78%+

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

### [codebase-summary.md](./codebase-summary.md) (420+ LOC)
**Codebase reference for developers**

Detailed module breakdown, layer responsibilities, data pipelines, patterns, and testing strategy.

**Use when:** Understanding project structure, finding modules, implementing new features

**Contains:**
- Architecture overview (DDD + CQRS + Vertical Slice)
- Module breakdown by layer:
  - **src/common** (700 LOC) - Mediator, EventBus, middleware, singletons
  - **src/domain** (1,674 LOC) - Aggregates, value objects, domain events, services
  - **src/infrastructure** (3,127 LOC) - Brokers, persistence, providers, scheduling
  - **src/features** (6,561 LOC) - Feature slices (market_data, backtesting, strategy, trading, risk)
- CQRS flow and data pipelines
- Key architectural patterns (value objects, broker abstraction, domain purity)
- Testing strategy and configuration

**Key Stats:**
- Total: 14,393 LOC (213 files, 182 Python files in src/)
- src/common: 700+ LOC (28 files)
- src/domain: 1,674+ LOC (33 files)
- src/infrastructure: 3,127+ LOC (32 files)
- src/features: 6,561+ LOC (85 files)
- tests/: 843 LOC (17 files)
- docker/: 401 LOC (5 files)

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
- Type hints (pyright compliance)
- Error handling (try-except, propagation)
- Logging with structlog (context variables)
- Testing standards (fixtures, mocking, 80% coverage)
- Code quality tools (ruff, pyright, pytest)
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

### [project-overview-pdr.md](./project-overview-pdr.md) (450+ LOC)
**Project vision, requirements, and status**

Product goals, requirements (functional & non-functional), implementation status, roadmap preview.

**Use when:** Understanding project goals, requirements, what's complete

**Contains:**
- Project vision (5 strategic goals)
- Functional requirements (10 features: F1-F10)
  - F1-F6: Market data (sync, quotes, aggregation, retrieval, registry, jobs)
  - F7: Strategy Engine (load, execute, broker abstraction)
  - F8: Backtesting Engine (run, optimize, metrics)
  - F9: Order & Position Management (lifecycle, P&L tracking)
  - F10: Live Trading (OKX integration, WebSocket)
- Non-functional requirements (6 categories)
  - Performance, reliability, observability, security, maintainability, scalability
- Implementation status (per feature)
  - All 10 features 100% complete ✅
  - Test coverage by component (74-85%)
  - Module breakdown with LOC breakdown
- Success criteria (v1.0 checklist: all 12 items complete)
- Known limitations & TODOs
- Roadmap phases (Phase 2-5 preview: data sources, extended backtesting, advanced trading)
- Development practices (branching, commits, code review)

**Status Summary:**
- v1.0: Extended features complete ✅ (strategy, backtesting, trading, OKX)
- Documentation: 95% complete
- Test coverage: 78% average (strategic features well-tested)
- Code quality: 100% type coverage, DDD architecture

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

| Document | Purpose | Audience | LOC |
|----------|---------|----------|-----|
| README.md | Quick start | All | 177 |
| codebase-summary.md | Reference | Developers | 420+ |
| code-standards.md | Guidelines | Developers, Reviewers | 650+ |
| system-architecture.md | Design | Architects, Developers | 480+ |
| project-overview-pdr.md | Requirements | All | 473 |
| deployment-guide.md | Production setup | DevOps | 200 |
| **Total** | | | **2,400+** |

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
A: Create `/src/features/{feature}/` following vertical slice pattern. See code-standards.md.

**Q: How do I add a CQRS handler?**
A: Create command/query class, handler class (extends Handler base), register with Mediator. See code-standards.md "CQRS Handler Pattern".

**Q: How do I write a trading strategy?**
A: Implement IStrategy interface (on_bar method), return StrategySignal on trading conditions. See code-standards.md "Strategy Implementation Pattern".

**Q: How do I run a backtest?**
A: POST /backtest/run with strategy name and date range. GridOptimizer handles parameter optimization. See deployment-guide.md.

**Q: How do I set up live trading with OKX?**
A: Add OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE to .env. See deployment-guide.md "OKX Setup".

**Q: How do I test code?**
A: See code-standards.md "Testing Standards". Run `pytest`. Target: 80% coverage, unit + integration.

**Q: Where is the production deployment guide?**
A: See [deployment-guide.md](./deployment-guide.md). Covers systemd, env vars, health checks.

**Q: How do I handle errors?**
A: See code-standards.md "Error Handling". Be specific with exceptions, log with context variables.

**Q: Should I use DI or singletons?**
A: Routes use FastAPI Depends(). Infrastructure (DB/Cache) uses class-method singletons. See system-architecture.md.

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
- Run pyright: `pyright src/`
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
| 2026-02-12 | Updated stats: 213 files, 14,393 LOC. Documented @event_handler decorator & auto-discovery, UUID7 migration, updated_at field rename |
| 2026-02-01 | AS-IS codebase documentation: 180 files, 12,420 LOC. Added detailed module breakdown, domain services, OKX reconnection handler, GridOptimizer details |
| 2026-01-28 | Codebase growth: 4,200 → 12,377 LOC (65 → 180 files) |
| 2026-01-21 | Initial documentation suite (5 docs, 2,324 LOC) |

---

**Last Updated:** 2026-02-12 | **Codebase:** 14,393 LOC (213 files) | **Test Coverage:** 78%+ | **Next Review:** 2026-03-01
