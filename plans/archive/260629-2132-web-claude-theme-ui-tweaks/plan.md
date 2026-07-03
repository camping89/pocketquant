---
title: "Web Claude theme + 4 UI tweaks"
description: "Claude AI dark/light theme + 4 UI fixes: indicator price-line removal, strategies indicator reuse, backtest datetime, live clock"
status: done
priority: P2
branch: "develop"
tags: [web, theme, ui]
blockedBy: []
blocks: []
created: "2026-06-29T14:49:39.398Z"
createdBy: "ck:plan"
source: skill
---

# Web Claude theme + 4 UI tweaks

## Overview

5 task UI cho `web/` SPA (+ 1 thay đổi contract backend ở backtest API):

1. **Claude AI theme** dark + light — CSS variable tokens + theme context, default dark, toggle cạnh `TimezoneSwitcher`, persist localStorage. Chart đọc màu qua `getComputedStyle`. Candle giữ 2 hue đối lập hòa palette Claude (up teal/sage, down clay/terracotta).
2. **Bỏ price line** ngang nét đứt cho indicators (`priceLineVisible:false`).
3. **Strategies page** thêm indicator toggles + render đầy đủ, tái dùng module charts, persist localStorage riêng.
4. **Backtest datetime** — `date`→`datetime` cả backend lẫn FE, default 1 năm trước→nay, `datetime-local`.
5. **Live clock** realtime cạnh timezone dropdown.

Brainstorm report: [`../reports/web-ui-claude-theme-and-4-tweaks-brainstorm-report.md`](../reports/web-ui-claude-theme-and-4-tweaks-brainstorm-report.md)

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Theme foundation](./phase-01-theme-foundation.md) | Done |
| 2 | [Chart theme & indicator price-line](./phase-02-chart-theme-indicator-price-line.md) | Done |
| 3 | [Strategies indicator reuse](./phase-03-strategies-indicator-reuse.md) | Done |
| 4 | [Backtest datetime BE+FE](./phase-04-backtest-datetime-be-fe.md) | Done |
| 5 | [Live clock](./phase-05-live-clock.md) | Done |

## Dependencies

```text
Phase 1 (theme foundation) ─┬─▶ Phase 2 (chart theme) ──▶ Phase 3 (strategies indicator)
                            └─▶ Phase 5 (live clock)
Phase 4 (backtest datetime) — độc lập
```

- Phase 2 `blockedBy` [1] — chart đọc CSS token do Phase 1 định nghĩa.
- Phase 3 `blockedBy` [2] — cùng sửa `strategy-chart.tsx`; tránh xung đột.
- Phase 5 `blockedBy` [1] — cùng sửa `__root.tsx` (toggle + clock đặt cạnh nhau).
- Phase 4 độc lập — backend + `backtest-form.tsx`.

## Acceptance criteria (tổng)

- [x] Toggle theme đổi tức thì cả UI chrome lẫn chart (bg/grid/candle), persist qua reload, default dark.
- [x] EMA/SMA/BB không còn đường ngang nét đứt; đường line giữ nguyên.
- [x] Strategies page có cùng bộ indicator toggles + render giống charts, dùng chung module (zero copy logic), persist riêng.
- [x] Backtest form default end=now / start=now−1y, chọn được phút; backtest chạy đúng range tới phút.
- [x] Clock chạy realtime, đổi UTC/Local theo dropdown.
- [x] `npm run lint` + `npm run build` (web) pass; backend test + ruff pass.

> **Recipe note (impl):** justfile chỉ có `test` (không có `types`/`test-pkg`/`baseline` như plan giả định). Lệnh thực tế dùng: lint/type = `python3 -m ruff check src/pocketquant/backtest tests/backtest_test` (clean); test = `env -u MONGODB_URL -u REDIS_URL uv run python -m pytest tests/backtest_test tests/baseline -q` (69 passed); baseline regenerate = thêm `BASELINE_UPDATE=1`. Phải unset MONGODB_URL/REDIS_URL vì env session trỏ prod (conftest guard chặn).

## Out of scope

- Theme cho từng component riêng lẻ ngoài token (chỉ token-driven).
- Thêm indicator mới (chỉ tái dùng bộ hiện có).
- `--status-*` job-history tokens light-aware (giữ dark-only).

## Validation Log

### Session 1 (2026-06-29)

**Verification Pass — Full tier (5 phases, 4 roles):**
- Claims checked: 9 | Verified: 7 | Failed: 1 | Unverified: 1
- ✅ `find_datetimes` tồn tại (`bar_repository.py:219`); `build_metrics` caller duy nhất = `result_collector.py:419`; baseline recipe = `just baseline` / `BASELINE_UPDATE=1`; `index.css` 4 literal dark-bg rgba (327/372/432/537); `resolve_date_range`/`build_backtest_config` không có caller.
- ❌ **FAILED**: Phase 4 thiếu `result_collector.py` — dùng `config.start_date` ở dòng 82 (`datetime.combine`), 425, 436. → Đã thêm vào Phase 4.
- ⚠️ Resolved: 5 test fixtures dùng `start_date=date(...)` → liệt kê để đổi `datetime(...)`.

**Decisions confirmed:**
1. `result_collector.py` → thêm vào Phase 4; dòng 82 bỏ `datetime.combine`, dùng thẳng `config.start_date` (giữ giờ/phút intraday).
2. Backtest `datetime-local` theo **tz dropdown**, FE convert→UTC khi submit (không phải UTC thuần). Suffix tz cạnh label.
3. Strategies indicator: **render đầy đủ** RSI/MACD panes (không cắt scope).
4. Candle/theme palette: **chốt hex trong Phase 1** (FINAL), không tinh chỉnh tự do khi implement.

**Phase propagation:** P1 (palette + inventory), P2 (candle từ token), P3 (RSI/MACD chốt), P4 (result_collector + TZ convert + baseline recipe + fixtures), P5 (no-op confirm).

### Whole-Plan Consistency Sweep (Session 1)

- "quy ước UTC" cũ trong plan.md out-of-scope + Phase 4 → đã thay bằng "theo tz dropdown, convert→UTC". Không còn mâu thuẫn.
- Palette hex: 1 nguồn = Phase 1 FINAL block; Phase 2 tham chiếu token `--up-color`/`--down-color`, không lặp hex. OK.
- `result_collector.py` xuất hiện nhất quán ở Related Files + Steps + Success Criteria Phase 4. OK.
- Baseline recipe nhất quán (`just baseline`) ở Related Files + Steps + Success Criteria. OK.
- **Zero unresolved contradiction.**
