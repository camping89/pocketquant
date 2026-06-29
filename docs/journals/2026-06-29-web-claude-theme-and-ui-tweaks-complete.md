# Web Claude Theme & UI Tweaks — Complete

**Date**: 2026-06-29 22:46  
**Severity**: Low  
**Component**: web/app  
**Status**: Resolved

## What Happened

Hoàn tất 2 commit trên develop (86252ee + b6d16ee): minute-precision backtest range + Claude dark/light theme system + 4 UI tweaks cho web. Toàn bộ feature verified, zero regression, sẵn sàng merge qua master.

## Thay đổi chính

**Backend:** `BacktestConfig.start_date/end_date` đổi `date` → `datetime` (OpenAPI snapshot regen); backward-compat date-only string vẫn parse; `_load_bars` bỏ `datetime.combine`; end-inclusive tới phút.

**Web:**
- Theme system: CSS `:root[data-theme=dark|light]` tokens (palette Claude: clay accent + warm-gray/cream), fallback dark `:root`, `ThemeContext` + toggle app-nav, persist localStorage `pq.theme.mode`.
- Chart re-theme: `theme-colors.ts` getComputedStyle token; `useChart` re-apply layout/grid, zoom intact, candle re-color; bỏ indicator price-line.
- Strategies page: toggle reuse module (zero duplicate compute), merge engulf+trade markers 1 plugin, persist indicators.
- Backtest form: `datetime-local` tz-aware, convert UTC submit, tz label suffix, default end=now/start=1y ago.
- Live clock realtime app-nav.

## The Brutal Truth

Plan viết giả định recipe (`just types`, `just baseline`) nhưng justfile thực tế không có — phải dùng ruff/pytest/`BASELINE_UPDATE=1` thực tế. Tốn vài phút trace shell flow thế là ổn.

Prod-DB session chứa `MONGODB_URL`/`REDIS_URL` → conftest chặn test ngay. Phải `env -u` để clean, KHÔNG động .env — security guardrail tốt nhưng cần doc/wiki.

## Technical Details

**Code review findings:**
- M1: theme token fallback `:root` dark (phòng vỡ UI nếu thiếu data-theme attr) ✓
- L1/L2/L3: out-of-scope/intended, giữ nguyên

**Verification:**
- web: ruff 0 errors, build pass
- backend: ruff clean
- pytest: 69 passed, 0 skipped

**Commits:**
- `86252ee`: feat(backtest): minute precision — OpenAPI baseline updated
- `b6d16ee`: feat(web): Claude theme + tweaks

## Root Cause Analysis

Plan assumptions về recipe ≠ thực tế là vì plan viết top-down (abstraction), không verify justfile inventory. Prod-DB guard (conftest block) là architectural đúng nhưng undocumented — dev đã quen clean shell trước test.

## Lessons Learned

1. **Recipe assumptions**: verify `just` inventory trước khi write plan tương tác shell.
2. **Env leakage**: prod-DB URLs trong session = runtime guard bảo vệ tốt; cần wiki entry cho dev context setup.
3. **Code review efficiency**: M-level feedback (real issue) vs L-level (documentation/nit) = giữ review focus trên behavior + safety.
4. **Baseline snapshot**: BASELINE_UPDATE=1 + regen = solid pattern, document nó ở CONTRIBUTING.md nếu chưa có.

## Next Steps

Merge qua master (master ← develop thông qua PR/ff). Zero blocking issues, ready production deploy nếu needed.
