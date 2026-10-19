# PocketQuant Docs

Docs describe the code as it is (AS-IS): no changelog, no version banner, no history. Git keeps the history. Docs are short, plain English only; the rule is in the project `CLAUDE.md`. When a doc and the code disagree, the code wins: fix the doc.

## Reading Order

| # | Doc | Read it for |
|---|---|---|
| 0 | [Root README](../README.md) | Install, run locally, smoke test, test gates. Read first. |
| 1 | [Project Overview](./project-overview-pdr.md) | Vision, goals, functional and non-functional requirements. |
| 2 | [System Architecture](./system-architecture.md) | Design decisions, layers, startup, control plane, backtest, market data, streaming, brokers, persistence. |
| 3 | [Codebase Summary](./codebase-summary.md) | Where things live. |
| 4 | [Code Standards](./code-standards.md) | How to write code here: naming, routes, DI, async rules, comments, tests, quality gate. |
| 5 | [Deployment](./deployment.md) | CI/CD, prod config, rollback, operator runbooks. |

## Topic Docs

| Doc | Read it for |
|---|---|
| [Engine scale-out limitation](./engine-scale-out-limitation.md) | Why one entry settles with one TP and a full close; what blocks scale-out and partial close. |
| [Swing pivot and key level](./swing-pivot-key-level.md) | How the take-profit key level is found, and why the chart's pattern view differs from the strategy's signals. |
| [Backtest rubric methodology](./backtest-rubric/methodology.md) | The offline scorecard for finished runs. Tool: `scripts/rubric/`. |

## Records (not authority)

- `journals/`: dated session notes. They age; do not treat them as current behavior.
- `todo/`: open research and roadmap notes.

## Checking Facts

- Routes: the OpenAPI page at `http://localhost:41921/api/v1/docs`.
- Env vars: `src/pocketquant/core/config.py`.
- Import contracts and the metric ceiling: `pyproject.toml`.
