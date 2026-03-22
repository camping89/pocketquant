# PocketQuant Documentation Index

**Last Updated:** 2026-03-22 | **Codebase:** 13,641 LOC (278 files, 4-package monorepo) | **Architecture:** DDD + CQRS + Clean Architecture + Dishka DI | **Structure:** packages/{core, backtest, trading, api} | **Test Coverage:** 78%+

Welcome to PocketQuant documentation. Start below based on your role. **Latest (2026-03-22):** Complete 4-package monorepo restructuring. Dishka DI integration complete. All domain entities with MongoDB persistence (to_mongo/from_mongo). Port: 41920.

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

### [README.md](../README.md) (Root project README)
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

### [codebase-summary.md](./codebase-summary.md) (717 LOC)
**Codebase reference for developers**

Detailed module breakdown, layer responsibilities, data pipelines, patterns, and testing strategy.

**Use when:** Understanding project structure, finding modules, implementing new features

**Contains:**
- Architecture overview (DDD + CQRS + Clean Architecture + Dishka DI in 4-package monorepo)
- Three-tier domain structure: top-level (bar, order, position, symbol, sync_status, backtest), concepts (quote, risk, strategy), shared
- Package breakdown:
  - **pocketquant-core** (97 files, 5,609 LOC): domain, common, infrastructure, persistence
  - **pocketquant-backtest** (40 files): BacktestAppService, GridOptimizationAppService, repositories
  - **pocketquant-trading** (65 files): OrderAppService, PositionAppService, OKXBroker
  - **pocketquant-api** (86 files, ~2,738 LOC): Dishka DI, 27 CQRS handlers, 26 API endpoints, FastAPI composition root
- CQRS flow and data pipelines
- Key architectural patterns (value objects, broker abstraction, domain purity)
- MongoDB persistence: `to_mongo()`/`from_mongo()` methods on all entities
- Testing strategy and configuration

**Key Stats:**
- Total: 13,641 LOC (278 Python files across 4 packages)
- Core domain: 2,364 LOC (Bar, OrderAggregate, PositionAggregate, Symbol, SyncStatus entities)
- Common/DI: 993 LOC (Mediator, EventBus, Dishka providers, middleware)
- Infrastructure: 2,883 LOC (Brokers, TradingView, OKX WebSocket, APScheduler)
- Persistence: 1,214 LOC (MongoDB, Redis, 7 repositories)
- Collections: bars, orders, positions, symbols, backtest_results, sync_status, optimization_results

---

### [system-architecture.md](./system-architecture.md) (761 LOC)
**Architecture & design documentation**

Clean architecture layers, CQRS patterns, data pipelines, DI container, deployment considerations.

**Use when:** Understanding how things work, designing new features, troubleshooting

**Contains:**
- High-level architecture diagram (Features → Application → Domain, Infrastructure)
- Clean architecture layer breakdown (Domain, Application, Features, Infrastructure, Common)
- Dependency Injection container (Dishka) with 6 providers
- CQRS request/response flow (commands and queries)
- Handler 5-step pattern (Fetch → Validate → Persist → Invalidate → Publish)
- Data pipelines: historical sync, real-time quotes, strategy execution, backtesting
- Broker abstraction (IBroker → PaperBroker/OKXBroker with exponential backoff)
- Middleware stack (Correlation ID, Rate Limit, Idempotency)
- Event Bus pattern (FIFO, bounded history at 100 events)
- Resource lifecycle (startup sequence, graceful shutdown)
- Integration points (TradingView, OKX, MongoDB, Redis)

**Key Diagrams:**
- 7-layer architecture overview
- Startup sequence (11 steps)
- Data flow pipeline

---

### [code-standards.md](./code-standards.md) (763 LOC)
**Development guidelines & best practices**

Architecture patterns, code organization, testing, quality standards, performance.

**Use when:** Writing code, code review, testing, debugging

**Contains:**
- Clean architecture rules (Mandatory dependency direction: Features → Application → Domain, Infrastructure ← Domain)
- 12 architecture patterns: vertical slice, application layer, DI (Dishka), repository, service, provider, event handlers, CQRS, extract-method, schema consolidation, strategy impl, domain patterns
- Code organization (file naming, module size <200 LOC, imports)
- Commenting, type hints, error handling, logging
- Testing standards (fixtures, mocking, 80% coverage)
- Code quality tools (ruff, pyright, pytest)
- Performance (blocking I/O, bulk ops, caching, concurrency)
- Configuration & secrets (.env)
- UUID7 (time-ordered IDs)
- Deprecated patterns (DO NOT list)

**File Size Targets:**
```
quote_aggregator.py:     368 LOC  ✅ (algorithm exception)
routes.py:               472 LOC  ⚠️  (split candidate)
quote_app_service.py:        236 LOC  ✅
data_sync_service.py:    244 LOC  ✅
```

---

### [project-overview-pdr.md](./project-overview-pdr.md) (505 LOC)
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
| README.md | Quick start | All | 381 |
| codebase-summary.md | Reference | Developers | 717 |
| code-standards.md | Guidelines | Developers, Reviewers | 763 |
| system-architecture.md | Design | Architects, Developers | 761 |
| project-overview-pdr.md | Requirements | All | 505 |
| handler-pipelines.md | Handler details | Developers | 663 |
| deployment-guide.md | Production setup | DevOps | 204 |
| ddd-strategic-map.md | DDD structure | Architects | 142 |
| **Total** | | | **4,136** |

---

## Key Concepts Explained

### Vertical Slice Architecture (Operation-First)
Each feature (market_data, backtesting, strategy, trading, risk) is self-contained. **Operations are the primary organizational unit.** Each operation folder contains: command/query.py, handler.py, optional route.py. Shared code within a feature is in base/.

**Example Structure:**
```
features/backtesting/
├── base/          # Shared: engine, metrics, models, optimizer, repository
├── run/           # Operation: execute backtest
│   ├── command.py
│   ├── handler.py
│   └── route.py
├── optimize/      # Operation: optimize parameters
└── router.py
```

**Why:** Clear separation of use cases. Each operation is self-contained and testable. Easy to add/remove operations without cascading changes. Developers understand an entire feature by reading operations.

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
A: POST /backtest/run with strategy name and date range. GridOptimizationAppService handles parameter optimization. See deployment-guide.md.

**Q: How do I set up live trading with OKX?**
A: Add OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE to .env. See deployment-guide.md "OKX Setup".

**Q: How do I test code?**
A: See code-standards.md "Testing Standards". Run `pytest`. Target: 80% coverage, unit + integration.

**Q: Where is the production deployment guide?**
A: See [deployment-guide.md](./deployment-guide.md). Covers systemd, env vars, health checks.

**Q: How do I handle errors?**
A: See code-standards.md "Error Handling". Be specific with exceptions, log with context variables.

**Q: What's the Dishka DI structure?**
A: 6 providers (Core, Persistence, Infrastructure, MarketData, Trading, Handler) in `packages/pocketquant-api/src/pocketquant/api/di/`. Routes use `FromDishka[Mediator]`. See code-standards.md.

**Q: What's the EventBus max history?**
A: **100 events** (hardcoded in CoreProvider). See codebase-summary.md "EventBus".

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
| 2026-03-22 | Monorepo restructuring complete: 4-package uv workspace (core, backtest, trading, api). Dishka DI integration. All domain entities with MongoDB persistence. Port: 41920. Updated all docs. |
| 2026-03-15 | DDD aggregate cleanup: Deleted OHLCVAggregate, QuoteAggregate, SymbolAggregate. Renamed domain/ohlcv/→domain/bar/, OHLCVRepository→BarRepository, collection ohlcv→bars. Symbol flattened to entity. Schemas deleted. |
| 2026-02-21 | Accuracy refresh: Verified all LOC counts (13,641 across 277 files), fixed Motor→PyMongo references, corrected justfile commands (just up/down, not start/stop), fixed mypy→pyright. Updated all doc files with accurate metrics. |
| 2026-02-13 | Operation-first vertical slice restructure: All features reorganized with operations as primary unit. Updated architecture docs, code standards, feature structure. Each operation folder self-contained. |
| 2026-02-12 | Updated stats: 213 files, 14,393 LOC. Documented @event_handler decorator & auto-discovery, UUID7 migration, updated_at field rename |
| 2026-02-01 | AS-IS codebase documentation: 180 files, 12,420 LOC. Added detailed module breakdown, domain services, OKX reconnection handler, GridOptimizationAppService details |
| 2026-01-28 | Codebase growth: 4,200 → 12,377 LOC (65 → 180 files) |
| 2026-01-21 | Initial documentation suite (5 docs, 2,324 LOC) |

---

**Last Updated:** 2026-03-22 | **Codebase:** 13,641 LOC (278 files, 4-package monorepo) | **Architecture:** DDD + CQRS + Clean Architecture + Dishka DI | **Test Coverage:** 78%+ | **Next Review:** 2026-04-01
