---
phase: 0
title: "Pre-Migration Prep"
status: pending
priority: P1
effort: 1h
---

# Phase 0: Pre-Migration Prep

## Overview

Validate architectural boundaries with import-linter before moving any files. Establish the dependency contracts that the split must honor.

## Steps

### 0.1 Add import-linter

```bash
uv add --dev import-linter
```

### 0.2 Create import-linter config

Add to `pyproject.toml`:

```toml
[tool.importlinter]
root_packages = ["src"]

[[tool.importlinter.contracts]]
name = "Domain layer independence"
type = "layers"
layers = [
    "src.features",
    "src.application",
    "src.infrastructure",
    "src.domain",
    "src.common",
]

[[tool.importlinter.contracts]]
name = "Backtest does not depend on Trading"
type = "forbidden"
source_modules = [
    "src.domain.backtest",
    "src.application.backtesting",
    "src.features.backtesting",
]
forbidden_modules = [
    "src.application.trading",
    "src.application.strategy",
    "src.features.trading",
    "src.features.strategy",
    "src.infrastructure.brokers.okx",
    "src.infrastructure.webhooks",
]

[[tool.importlinter.contracts]]
name = "Trading does not depend on Backtest"
type = "forbidden"
source_modules = [
    "src.application.trading",
    "src.application.strategy",
    "src.features.trading",
    "src.features.strategy",
    "src.infrastructure.brokers.okx",
]
forbidden_modules = [
    "src.domain.backtest",
    "src.application.backtesting",
    "src.features.backtesting",
]
```

### 0.3 Run import-linter, fix violations

```bash
lint-imports
```

If violations found: fix them BEFORE proceeding. This is the gate.

### 0.4 Create new branch

```bash
git checkout -b feat/monorepo-split
```

## Todo

- [ ] Install import-linter
- [ ] Add contracts to pyproject.toml
- [ ] Run lint-imports, all contracts pass
- [ ] Create feat/monorepo-split branch

## Success Criteria

- All import-linter contracts pass
- Zero violations = clean seams confirmed
