# SP2 — Rename `api` → `app`

> Brainstorm summary. Sub-project 2/3. Mechanical rename, độc lập (chèn trước/sau SP1 đều được).
> Liên quan: [SP1 control plane](./brainstorm-260609-1137-sp1-declarative-control-plane-report.md), [SP3 split](./brainstorm-260609-1137-sp3-split-app-and-bff-report.md).

## Problem statement

Package `pocketquant-api` thực chất là **composition root + runtime host** của cả monorepo (DI, migrations, scheduler, WS feed, strategy lifecycle), không phải "API/BFF". Tên `api` (và ý định đổi sang `bff`) đều sai bản chất. BFF = tầng FE-glue mỏng; thứ này *chạy cả hệ thống trading*. Đổi tên cho đúng: **`api` → `app`** (the application / runtime host).

> Lưu ý: "bff" chỉ đúng nếu **tách** tầng HTTP serve-FE ra thành package riêng — đó là SP3, không phải SP2. SP2 chỉ relabel package hiện tại cho đúng vai trò.

## Hiện trạng (verified)

- Module path: `pocketquant.api.*` — **250 occurrences** trên **106 file .py** (package internals + `tests/api_test/`).
- Dist name `pocketquant-api` + entry point: `pyproject.toml:32` → `pocketquant = "pocketquant.api.main:run"`.
- App khởi động từ đây: `api/main.py:38-87` (lifespan: DI, 5 migration/recovery step, scheduler, WS feed, strategy rehydrate).
- Không package backend nào import `pocketquant.api` (verified: core/infra/execution/backtest/trading đều sạch) → top layer thật, rename không vỡ layering.
- `web → api` là cạnh phụ thuộc duy nhất (HTTP, không import Python).

## Blast radius (verified)

| Vùng | Vị trí | Hành động |
|------|--------|-----------|
| Module dir | `packages/pocketquant-api/src/pocketquant/api/` → `.../app/` | Đổi tên thư mục |
| Package dir + dist | `packages/pocketquant-api/` → `packages/pocketquant-app/`; `name = "pocketquant-app"` | `pyproject.toml` của package |
| Import refs | 250 occ / 106 file: `pocketquant.api` → `pocketquant.app` | Sed/codemod toàn repo |
| Entry point | `pyproject.toml:32` `pocketquant.api.main:run` → `pocketquant.app.main:run` | Giữ tên command `pocketquant` (xem D1) |
| uv workspace sources | root `pyproject.toml` `[tool.uv.sources]` + mọi `dependencies = ["pocketquant-api"]` | Đổi `pocketquant-api` → `pocketquant-app` |
| import-linter | root `pyproject.toml [tool.importlinter]` — layer `pocketquant.api` (top) + forbidden_modules trong nhiều contract | Đổi mọi `pocketquant.api` → `pocketquant.app` |
| Docker | `deploy/Dockerfile:23` COPY path + `:64` CMD `pocketquant.api.main:app` | Đổi path + CMD module |
| CI | `.github/workflows/cicd.yml` — `tests/api_test/`, job `build-api` | Đổi test path + (tùy) tên job |
| Tests | `tests/api_test/` → `tests/app_test/` + imports bên trong | Đổi dir + refs |
| pyright | `pyrightconfig.json` refs `pocketquant-api` | Đổi |
| Docs/Plans | `README.md`, `docs/*` (system-architecture, code-standards, websocket-architecture, pdr...), `CLAUDE.md` | Đổi refs (xem D2 về plans lịch sử) |

## Expected output (acceptance)

1. Thư mục `packages/pocketquant-app/src/pocketquant/app/`, dist `pocketquant-app`.
2. Toàn bộ `from pocketquant.api...` → `from pocketquant.app...`; 0 ref `pocketquant.api` còn sót trong code/config sống.
3. `uv sync` thành công; `uv run pocketquant` chạy app như cũ.
4. import-linter pass với layer đổi tên.
5. Docker build + CMD chạy; CI xanh (`tests/app_test/`).
6. Docs/`CLAUDE.md` cập nhật tên + dependency graph.

## Quyết định cần chốt khi plan

| # | Câu hỏi | Khuyến nghị |
|---|---------|-------------|
| D1 | Tên command CLI `pocketquant` giữ hay đổi? | **Giữ** `pocketquant`, chỉ đổi import target `pocketquant.app.main:run`. Command là UX ngoài, không cần đổi. |
| D2 | `plans/` lịch sử có rewrite không? | **Không** rewrite plans cũ (là lịch sử, git giữ). Chỉ sửa code + config sống + `docs/` + `README` + `CLAUDE.md`. |
| D3 | `tests/api_test/` đổi tên dir? | Đổi → `tests/app_test/` cho nhất quán; cập nhật CI path. |
| D4 | `web` package có đổi tên không? | **Không trong SP2.** `web` giữ nguyên; chỉ là consumer HTTP. (Cân nhắc ở SP3 nếu muốn.) |
| D5 | Làm SP2 trước hay sau SP1? | Độc lập. Nếu làm SP2 trước: SP1 sau đó thao tác trên `pocketquant.app`. Rename trước cho "sạch tên" rồi mới đụng logic cũng hợp lý. |

## Strategy thực thi (gợi ý)

- Codemod 1 phát: `rg -l 'pocketquant\.api' | xargs sed -i 's/pocketquant\.api/pocketquant.app/g'` + đổi dir + dist name, rồi `uv sync` + chạy import-linter + test. Vì là top layer, rủi ro thấp.
- Cẩn thận chuỗi `api` ngắn xuất hiện trong context khác (vd `api_prefix`, `/api/v1` URL prefix, biến `api` trong `register_routes`). **Chỉ replace `pocketquant.api` / `pocketquant-api`**, KHÔNG replace chữ `api` trần.
- `api_prefix="/api/v1"` (URL FE) **giữ nguyên** — đó là HTTP path, không phải module name.

## Risks

| Risk | Mức | Mitigation |
|------|-----|-----------|
| Over-replace chữ `api` trần (URL prefix, var `api` trong include_router) | Trung | Chỉ match `pocketquant.api`/`pocketquant-api`; review diff `api_prefix`, `register_routes` |
| uv.lock / workspace lệch sau đổi dist name | Trung | `uv sync` lại, commit lock mới |
| Docker CMD `pocketquant.api.main:app` quên đổi → container chết | Trung | Verify Dockerfile:64; smoke run container |
| import-linter contract còn ref tên cũ → CI đỏ | Thấp | Đổi đủ mọi contract trong pyproject |
| Dạng URL `/api/v1` bị tưởng nhầm phải đổi | Thấp | Ghi rõ: URL prefix KHÔNG đổi |

## Success metrics

- `rg 'pocketquant\.api|pocketquant-api'` trên code/config sống = 0 hit (trừ plans lịch sử nếu D2=giữ).
- `uv run pocketquant` + Docker CMD chạy y hệt trước.
- CI xanh, import-linter pass.

## Next steps

- `/ck:plan` (default — mechanical rename, không đổi hành vi; test hiện có đủ làm regression net).
- Pass report này làm context.

## Unresolved questions

1. D1 (giữ command `pocketquant`?) và D4 (`web` có đổi tên?) — chốt khi plan.
2. Thứ tự với SP1: rename trước hay sau? (ảnh hưởng SP1 thao tác trên `api` hay `app`).
3. Tên job CI `build-api`/`build-app` có cần đổi không (chỉ là label) — minor.
