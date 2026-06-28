---
phase: 5
title: "Verify"
status: pending
priority: P1
dependencies: [1, 2, 3, 4]
---

# Phase 5: Verify

## Overview

Quality gate cuối: chạy full test suite BE+FE, import-linter, OpenAPI snapshot, và smoke-test end-to-end engulfing (backtest ra trade + chart vẽ pattern). Xác nhận TS↔Python detector khớp qua golden fixture.

## Requirements

- Functional: backtest engulfing chạy ra nhiều trade với SL/TP đúng; chart toggle vẽ đúng strong/weak.
- Non-functional: mọi gate xanh, không weaken test.

## Architecture

Verify theo thứ tự rẻ → đắt: lint → unit → integration → import-linter → OpenAPI → FE build+test → smoke E2E. (KHÔNG có mypy trong project — bỏ type-check BE; FE type-check qua `tsc -b` trong `npm run build`.)

**Lệnh canonical (verified `.github/workflows/cicd.yml`):** `uv run pytest tests/ -q`, `uv run lint-imports`, `uv run ruff check`. `just test-pkg`/`just lint`/`just types` KHÔNG tồn tại (README stale).

## Related Code Files

- Reference (không sửa trừ khi fix regression): toàn bộ file Phase 1-4.

## Implementation Steps

0. **Gate (red-team Finding 1):** xác nhận 260628-1514 **commit/merge** (HEAD có rename, plan `status: completed`, `git status` sạch) — KHÔNG phải dirty-tree. Nếu chưa → DỪNG, kết quả "nhiều trade" không đáng tin.
1. `uv run ruff check` — lint xanh.
2. `diff tests/core_test/unit/domain/strategy/patterns/engulfing_golden_fixture.json web/src/lib/indicators/__fixtures__/engulfing_golden_fixture.json` — 2 bản fixture giống hệt (chống drift TS↔Python).
3. `uv run pytest tests/core_test -q` — detector + EngulfingStrategy unit + golden fixture.
4. `uv run pytest tests/backtest_test -q` — integration engulfing ra ≥2 trade.
5. `uv run pytest tests/ -q` — full suite (strategy registry + `tests/baseline/test_openapi_snapshot.py`).
6. `uv run lint-imports` — xác nhận 7 contracts (`engulfing.py` chỉ import core; detector zero deps ngoài).
7. OpenAPI snapshot: snapshot là **schema-only** (verified — `/backtest/strategies` trả `list[str]` titled, không có enum strategy-code; `hitnrun2` không xuất hiện trong snapshot). `engulfing` là runtime value → **không đổi snapshot, không cần regenerate**. Nếu snapshot vỡ → đó là schema regression BẤT NGỜ (từ 260628-1514?) → điều tra, KHÔNG regenerate vô tội vạ.
8. `cd web && npm run lint && npm run build && npm run test` — vitest engulfing.test.ts khớp fixture copy.
9. Smoke E2E: sync 1 symbol có dữ liệu; enqueue backtest engulfing qua API; poll request → status completed, trades > 1; mở chart bật toggle Engulfing → markers strong/weak hiện cùng backtest markers.

## Success Criteria

- [ ] `uv run ruff check` + `uv run pytest tests/ -q` xanh.
- [ ] `uv run lint-imports` 7 contracts pass.
- [ ] Backtest engulfing: `total_trades > 1`, SL/TP mỗi trade khớp công thức.
- [ ] TS golden-fixture test khớp Python (vitest, máy enforce).
- [ ] `npm run lint && npm run build && npm run test` xanh.
- [ ] Smoke E2E: chart vẽ engulfing markers + backtest markers đồng thời, không override.
- [ ] OpenAPI snapshot không đổi (schema-only, engulfing là runtime value).
- [ ] 2 bản fixture (canonical + copy) byte-identical.

<!-- Updated: Validation Session 1 + Red Team Session 1 - gate commit-check; fixture diff; OpenAPI schema-only khẳng định -->
> **Lệnh:** bỏ `just types` (no mypy); `uv run ruff check` / `uv run pytest tests/ -q` / `uv run lint-imports`; `npm run test` (vitest). Gate 260628-1514 = commit/merge, không grep.

## Risk Assessment

- **Risk (red-team Finding 1):** backtest cap 1 trade nếu 260628-1514 chưa COMMIT (dirty-tree false-pass). Mitigation: step 0 gate kiểm tra commit + plan completed.
- **Risk:** OpenAPI snapshot vỡ. Mitigation: snapshot schema-only (verified `openapi_app_snapshot.json` — không enum strategy-code); engulfing không đổi schema. Nếu vỡ = regression bất ngờ, điều tra không regenerate.
- **Risk:** fixture copy drift khỏi canonical. Mitigation: step 2 `diff` trong verify.
- **Risk:** smoke E2E cần dữ liệu đã sync. Mitigation: sync symbol trước; dùng symbol/interval có sẵn.
