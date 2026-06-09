---
phase: 1
title: "Bff package scaffold"
status: completed
priority: P2
effort: "4h"
dependencies: []
---

# Phase 1: Bff package scaffold

## Overview

Tạo package mới `pocketquant-bff` trong uv workspace: thư mục, `pyproject.toml`, namespace `pocketquant.bff.*`, dependency subset, build target. Chưa di chuyển logic — chỉ dựng khung + 1 entrypoint FastAPI rỗng chạy được `uv sync`. Việc move routes/DI sang Phase 4.

## Requirements

- Functional:
  - `packages/pocketquant-bff/` tồn tại, là workspace member, `uv sync` thành công.
  - Namespace package `pocketquant/bff/` (PEP 420 — no `__init__.py` ở `pocketquant/` level, đồng nhất các package khác).
  - Dist name `pocketquant-bff`, entry point `pocketquant-bff = "pocketquant.bff.main:run"`.
  - `pyproject.toml` deps: `pocketquant-core`, `pocketquant-infrastructure`, `pocketquant-backtest`, `pocketquant-trading`, `fastapi`, `uvicorn`, `dishka`. **KHÔNG** cần `pocketquant-execution` trực tiếp nếu bff không gọi engine — nhưng `trading`/`backtest` kéo `execution` theo transitively; bff chỉ import handlers/routes, không import engine app-service. Xác nhận lại khi Phase 4 chia DI.
- Non-functional:
  - Theo đúng layout `pocketquant-app/pyproject.toml` (cùng `[build-system] hatchling`, `[tool.hatch.build.targets.wheel] packages = ["src/pocketquant"]`).

## Architecture

### Layer position

`pocketquant.bff` và `pocketquant.app` đều là **top layer độc lập**, cùng đứng trên `{backtest, trading}`. import-linter contract (Phase 6) thêm `pocketquant.bff` vào cùng tầng `pocketquant.app` trong layers contract. Cả 2 KHÔNG import lẫn nhau.

```
core ◁ infrastructure ◁ execution ◁ {backtest, trading} ◁ {app, bff}
```

### Naming

- Package dir: `packages/pocketquant-bff/`
- Module: `packages/pocketquant-bff/src/pocketquant/bff/`
- Entry: `pocketquant.bff.main:run` (mirror `pocketquant.app.main:run`)

## Related Code Files

- Create: `packages/pocketquant-bff/pyproject.toml`
- Create: `packages/pocketquant-bff/src/pocketquant/bff/main.py` (FastAPI rỗng + `/health` placeholder, `run()` CLI)
- Create: `packages/pocketquant-bff/README.md` (1 đoạn role)
- Modify: root `pyproject.toml` — thêm `pocketquant-bff` vào `[tool.uv.sources]` (workspace=true). `members = ["packages/*"]` đã tự bắt; chỉ cần source mapping nếu package khác depend (chưa).
- Read context: `packages/pocketquant-app/pyproject.toml` (template).

## Implementation Steps

1. Tạo `packages/pocketquant-bff/pyproject.toml` copy cấu trúc từ `pocketquant-app/pyproject.toml`: đổi `name = "pocketquant-bff"`, `version = "0.1.0"`, description "FE gateway — stateless FastAPI serving pocketquant-web + DB read/write", `[project.scripts] pocketquant-bff = "pocketquant.bff.main:run"`.
2. Tạo `src/pocketquant/bff/main.py`: `create_app()` trả FastAPI tối thiểu với 1 route `GET /health` trả `{"status":"ok"}`; `app = create_app()`; `run()` gọi `uvicorn.run("pocketquant.bff.main:app", host="0.0.0.0", port=<bff_port>)`. (Routes/middleware/DI thật move ở Phase 4.)
3. KHÔNG tạo `__init__.py` tại `src/pocketquant/` (namespace package).
4. `uv sync` — verify workspace nhận package mới, lock cập nhật.
5. `uv run pocketquant-bff` — verify server start + `/health` trả 200. (Tạm port khác app, vd 41921; chốt port chính thức ở Phase 6 deploy.)
6. `just lint` + `just types` trên package mới.

## Success Criteria

- [ ] `packages/pocketquant-bff/` là workspace member; `uv sync` xanh.
- [ ] `uv run pocketquant-bff` start, `GET /health` → 200.
- [ ] Namespace package đúng (no stray `__init__.py`).
- [ ] lint + types clean trên file mới.

## Risk Assessment

- **uv.lock churn**: thêm package đổi lock. Mitigation: commit lock mới; verify `uv sync --frozen` xanh ở CI sau.
- **Port collision local**: bff + app cùng máy dev. Mitigation: bff port khác (41921), Vite proxy đổi ở Phase 5.
- **Dep subset đoán sai**: chưa chắc bff cần gì tới khi Phase 4 chia DI. Mitigation: Phase 1 để deps rộng (core+infra+backtest+trading), siết lại ở Phase 4 nếu engine không bị import.
