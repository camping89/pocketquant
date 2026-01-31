# Phase 03: Backtest API & Grid Optimizer

## Context Links

- Parent: [plan.md](./plan.md)
- Depends on: [phase-02-backtest-metrics-persistence.md](./phase-02-backtest-metrics-persistence.md)
- Research: [researcher-02-backtest-patterns.md](./research/researcher-02-backtest-patterns.md)

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Critical |
| Status | pending |
| Estimate | 3h |

REST API endpoints for backtest execution and grid search optimizer for parameter sweeps.

## Key Insights

1. **CQRS pattern** - Commands for run/optimize, queries for results
2. **Parallel grid search** - Use `asyncio.gather` with semaphore for concurrency control
3. **Coarse-to-fine** - Start wide, narrow down winning region
4. **Combinatorial explosion** - 5 params x 10 values = 100k combos; limit to reasonable grid

## Requirements

### Functional
- POST `/backtest/run` - Execute single backtest
- POST `/backtest/optimize` - Run grid optimization
- GET `/backtest/{id}` - Get backtest result
- GET `/backtest/{id}/equity` - Get equity curve data
- GET `/optimization/{id}` - Get optimization results
- Grid optimizer: parameter ranges, target metric, max workers

### Non-Functional
- API response <100ms for submission (async execution)
- Grid optimizer uses N concurrent workers (configurable, default 4)
- Results queryable within 1 second

## Architecture

```
POST /backtest/run
    │
    ├─ RunBacktestCommand
    │   └─ Mediator.send()
    │       └─ RunBacktestHandler
    │           ├─ Create BacktestRunner
    │           ├─ Execute run
    │           └─ Return run_id
    │
    └─ Response: {run_id, status: "running"}

POST /backtest/optimize
    │
    ├─ RunOptimizationCommand
    │   └─ Mediator.send()
    │       └─ RunOptimizationHandler
    │           ├─ Generate parameter grid
    │           ├─ Semaphore(max_workers)
    │           ├─ asyncio.gather(*backtest_tasks)
    │           ├─ Rank by target_metric
    │           └─ Persist OptimizationRun
    │
    └─ Response: {optimization_id, status: "running", total_combinations: N}
```

### Grid Optimizer Flow

```python
async def optimize(config: OptimizationConfig) -> OptimizationRun:
    # Generate all parameter combinations
    param_names = list(config.parameter_grid.keys())
    param_values = list(config.parameter_grid.values())
    combinations = list(itertools.product(*param_values))

    # Limit concurrency
    semaphore = asyncio.Semaphore(config.max_workers)

    async def run_with_semaphore(params: dict) -> BacktestRun:
        async with semaphore:
            return await runner.run(config.with_params(params))

    # Run all in parallel (semaphore limits concurrency)
    tasks = [
        run_with_semaphore(dict(zip(param_names, combo)))
        for combo in combinations
    ]
    results = await asyncio.gather(*tasks)

    # Rank by target metric
    ranked = sorted(results, key=lambda r: getattr(r.metrics, config.target_metric), reverse=True)

    return OptimizationRun(
        results=ranked,
        best_params=ranked[0].config.params,
        best_metrics=ranked[0].metrics
    )
```

## Related Code Files

### Create
| File | Purpose | LOC |
|------|---------|-----|
| `src/features/backtesting/api/backtest-routes.py` | FastAPI routes | ~80 |
| `src/features/backtesting/commands/run-backtest-command.py` | CQRS command | ~30 |
| `src/features/backtesting/commands/run-optimization-command.py` | CQRS command | ~40 |
| `src/features/backtesting/handlers/run-backtest-handler.py` | Command handler | ~60 |
| `src/features/backtesting/handlers/run-optimization-handler.py` | Command handler | ~80 |
| `src/features/backtesting/queries/get-backtest-query.py` | CQRS query | ~20 |
| `src/features/backtesting/handlers/get-backtest-handler.py` | Query handler | ~40 |
| `src/features/backtesting/optimizer/grid-optimizer.py` | Parameter sweep | ~100 |
| `src/features/backtesting/models/optimization-config.py` | Config dataclass | ~40 |
| `src/features/backtesting/models/optimization-result.py` | Result dataclass | ~50 |

### Modify
| File | Change |
|------|--------|
| `src/main.py` | Register backtest routes |
| `src/common/mediator/dependencies.py` | Register handlers |

## Implementation Steps

1. **Create OptimizationConfig model**
   ```python
   @dataclass
   class OptimizationConfig(BacktestConfig):
       parameter_grid: dict[str, list[Any]]  # {"ma_fast": [5,10,20], "ma_slow": [50,100]}
       target_metric: str = "sharpe_ratio"   # metric to maximize
       max_workers: int = 4                   # concurrent backtests
   ```

2. **Create GridOptimizer**
   - `generate_combinations(grid)` - itertools.product
   - `optimize(config)` - parallel execution with semaphore
   - `rank_results(results, metric)` - sort by target

3. **Create CQRS commands and handlers**
   - RunBacktestCommand → RunBacktestHandler
   - RunOptimizationCommand → RunOptimizationHandler
   - GetBacktestQuery → GetBacktestHandler
   - GetOptimizationQuery → GetOptimizationHandler

4. **Create API routes**
   ```python
   @router.post("/run")
   async def run_backtest(request: RunBacktestRequest, mediator: Mediator = Depends()):
       cmd = RunBacktestCommand(...)
       result = await mediator.send(cmd)
       return {"run_id": result.id, "status": result.status}

   @router.post("/optimize")
   async def run_optimization(request: OptimizationRequest, mediator: Mediator = Depends()):
       cmd = RunOptimizationCommand(...)
       result = await mediator.send(cmd)
       return {"optimization_id": result.id, "total_combinations": result.total}

   @router.get("/{run_id}")
   async def get_backtest(run_id: str, mediator: Mediator = Depends()):
       query = GetBacktestQuery(run_id=run_id)
       return await mediator.send(query)
   ```

5. **Register routes and handlers**
   - Add router to main.py
   - Register handlers with Mediator

6. **Add MongoDB collection for optimization runs**
   - Collection: `optimization_runs`
   - Index on strategy_id

## Todo List

- [ ] Create `src/features/backtesting/models/optimization-config.py`
- [ ] Create `src/features/backtesting/models/optimization-result.py`
- [ ] Create `src/features/backtesting/optimizer/grid-optimizer.py`
- [ ] Create CQRS commands (run-backtest, run-optimization)
- [ ] Create CQRS handlers
- [ ] Create `src/features/backtesting/api/backtest-routes.py`
- [ ] Register routes in main.py
- [ ] Integration test: POST /backtest/run returns run_id
- [ ] Integration test: Grid optimizer runs N combinations

## Success Criteria

- [ ] POST /backtest/run returns run_id within 100ms
- [ ] GET /backtest/{id} returns full result with metrics
- [ ] Grid optimizer runs 9 combinations (3x3) in parallel
- [ ] Best params identified by target metric
- [ ] Optimization results persist to MongoDB

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Combinatorial explosion (100k+ combos) | Medium | High | Validate max combinations (e.g., 1000) in handler |
| Memory exhaustion from parallel runs | Medium | High | Semaphore limits concurrency; stream results |
| Long-running optimization blocks server | Low | Medium | Return ID immediately, poll for status |

## Security Considerations

- Input validation on parameter ranges
- Rate limit on optimization endpoint
- Max combinations cap (prevent DoS)

## Next Steps

After this phase:
- Backtest feature complete
- Phase 04: Begin OKX WebSocket implementation
