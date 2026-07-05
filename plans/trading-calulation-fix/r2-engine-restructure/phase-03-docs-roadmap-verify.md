# Phase 03 — Docs sync + roadmap R2 done + final gate sweep

**Context:** [plan](plan.md) · [roadmap R2](../roadmap.md) · STRUCTURE-ONLY.
**Priority:** medium · **Status:** done · **Depends:** P1, P2.

## Overview

Đồng bộ tài liệu về cấu trúc mới (3 tầng, 5 feature area engine, 8 contract), đánh dấu
R2 done trong roadmap, và chạy full-gate cuối cùng xác nhận không hồi quy.

## Docs cần sync (AS-IS, không changelog)

- **`docs/system-architecture.md`** — cây package (backtest giờ là `engine/backtest/`), sơ đồ tầng 4→3, "Where does X live" cho backtest/live/strategy/execution, danh sách import-linter contract (7→8).
- **`docs/code-standards.md`** — path ref `backtest/…` → `engine/backtest/…`; mục contract/layer nếu liệt kê số tầng; class-naming-by-layer nếu nhắc backtest package.
- **KHÔNG đụng** `docs/journals/*` — snapshot lịch sử theo ngày (git giữ lịch sử).
- **`README.md`** — chỉ sửa nếu có ref path module `pocketquant.backtest` / lệnh trỏ `backtest/` (grep xác nhận; canonical routes URL không đổi).

## Roadmap update

- `../roadmap.md` bảng Decomposition: hàng **R2** cột Track/Trạng thái → **✅ Done** (khớp format R1: `**R2** ✅`).
- Giải unresolved R2: *"intra-engine dùng layers hay independence?"* → **GIẢI: 2 contract tách (independence [backtest,live] + forbidden máy-chung→driver), tổng 8 contract."*
- `plan.md` frontmatter `status: pending` → `done`.

## Verify (full sweep)

1. `just test` — toàn bộ xanh, số pass = baseline trước R2.
2. `ruff check .` — clean.
3. `pyright` (hoặc lệnh type-check dự án) — 0 error.
4. `lint-imports` — **8 contracts kept**.
5. `grep -rn "pocketquant.backtest" src tests docs` = **0** (trừ journals lịch sử + roadmap/plan mô tả).
6. Smoke: `python -c "import pocketquant.app.main"` OK (DI wiring resolve path mới).

## Todo

- [x] Update `docs/system-architecture.md` (cây + tầng + contract 8 + where-X-lives)
- [x] Update `docs/code-standards.md` (path ref + số tầng)
- [x] Update `README.md` nếu có ref (grep-driven)
- [x] Roadmap: R2 → ✅ Done + giải unresolved R2
- [x] `plan.md` status → done
- [x] Full-gate sweep (test/ruff/pyright/lint-imports/import-smoke) xanh
- [x] `grep pocketquant.backtest` src/tests/docs = 0 (ngoài lịch sử)

## Success criteria

- 4 gate xanh; DI app import OK.
- Docs mô tả đúng cấu trúc AS-IS: 3 tầng, `engine/{strategy,execution,market_data,backtest,live}`, 8 contract.
- Roadmap phản ánh R2 done, unblock R3 + R8.

## Next

Roadmap: R2 done → mở R3 (logic: CommissionModel) ở session riêng.
