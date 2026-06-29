---
title: "Engulfing strategy: pattern visualization + backtest entry/SL/TP"
description: >-
  New `engulfing` strategy: strict-body engulfing with directional
  close-location quality filter. Two consumers off one definition — chart
  toggle shows ALL patterns (strong/weak colored), Python strategy enters only
  strong patterns with SL below pattern + buffer and single TP = max(RR 1:1,
  swing key-level). Baseline 1-TP (no scale-out). Locked TS↔Python via shared
  golden fixture.
status: completed
priority: P2
branch: develop
tags:
  - strategy-engine
  - backtest
  - frontend
  - candlestick-pattern
blockedBy: [260628-1514-backtest-onfill-sharpe-fix-hook-rename]
blocks: []
created: "2026-06-28T09:08:04.573Z"
createdBy: "ck:plan"
source: skill
---

# Engulfing strategy: pattern visualization + backtest entry/SL/TP

## Overview

Thêm strategy `engulfing` với **một định nghĩa pattern, hai consumer**:

- **Chart (TS)** — nút toggle "Engulfing" vẽ **tất cả** body-engulfing, tô màu **strong/weak** theo quality filter (show-all-patterns-first).
- **Strategy (Python)** — `EngulfingStrategy(IStrategy)` chỉ entry pattern **strong**, SL dưới pattern extreme + buffer, **một** TP = `max(RR 1:1, swing key-level)`.

Nguồn thiết kế: `plans/2026-06-28-engulfing-strategy/brainstorm-report.md` (design approved).

**Baseline 1-TP** — engine KHÔNG hỗ trợ scale-out/multi-TP/partial close (4 tầng giới hạn, xem Phase 4). Scale-out → roadmap.

## ⚠ Cross-plan dependency (HARD BLOCK)

`blockedBy: [260628-1514-backtest-onfill-sharpe-fix-hook-rename]` — plan đó (status pending, P1) ảnh hưởng engulfing 2 cách:

1. **Rename hooks** — `on_bar→on_bar_completed`, `on_fill→on_order_filled`. Engulfing viết theo **tên MỚI** ngay từ đầu để không thành thêm bề mặt rename.
2. **Fill-hook bug** — hiện `on_fill` có 0 call-site → `_open_direction` kẹt → **backtest cap 1 trade**. Engulfing dùng cùng pattern reset `_open_direction` trong `on_order_filled`. Nếu implement TRƯỚC khi plan kia land, backtest engulfing cũng cap 1 trade (không phải lỗi engulfing — bug engine).

→ Implement engulfing **SAU** khi 260628-1514 land. FE+BE chung nhịp (user chọn). Hook contract dùng: `on_bar_completed(bar) -> Signal | None`, `on_order_filled(order: FilledOrder, fill_price) -> None` (param type là `FilledOrder` Protocol, KHÔNG phải `OrderAggregate`).

> ⚠ **"Land" = COMMITTED/MERGED, không phải dirty-tree.** Red-team phát hiện: code của 260628-1514 (rename hook + `OrderFilledEvent` handler) đang có trong working tree NHƯNG **chưa commit** (HEAD vẫn `on_bar`/`on_fill`), plan đó `status: pending`. Gate bằng `grep` tên hook sẽ **false-pass** vì grep match working tree. → Gate phải kiểm tra `git log` cho thấy 260628-1514 đã commit + plan đó `status: completed` + verify phase xanh. Không bắt đầu Phase 2 trên dirty tree.

## Definition (locked TS + Python)

**Strict body engulfing**, 2 chiều:

```
Bullish (→ LONG):  prev đỏ; curr xanh; open <= prev_close AND close >= prev_open
Bearish (→ SHORT): prev xanh; curr đỏ; open >= prev_close AND close <= prev_open
```

**Quality filter — close-location CÓ HƯỚNG** (chống weak/fake rejection):

```
LONG:  (high - close) / (high - low) <= max_rejection_wick_pct
SHORT: (close - low)  / (high - low) <= max_rejection_wick_pct
range 0 (high==low) → fail; default 0.30; =1.0 để tắt
```

## Entry / SL / TP (Python)

```
LONG:  entry=close; pattern_low=min(low_curr,low_prev); SL=pattern_low*(1-sl_buffer_pct)
       risk=entry-SL; tp_rr=entry+risk; key=max(highs[-N:]); TP=max(tp_rr,key)
SHORT: mirror — pattern_high=max(high_curr,high_prev); SL=pattern_high*(1+sl_buffer_pct)
       risk=SL-entry; tp_rr=entry-risk; key=min(lows[-N:]); TP=min(tp_rr,key)
```

## Params (default, tune-được)

```python
_DEFAULTS = {
    "direction": "both",              # long | short | both
    "sl_buffer_pct": 0.001,           # 0.1%
    "key_level_lookback_bars": 20,
    "max_rejection_wick_pct": 0.30,   # 1.0 = tắt filter
}
```

## Phases

| Phase | Name | Status | Priority | Depends |
|-------|------|--------|----------|---------|
| 1 | [Engulfing detector + golden fixture](./phase-01-engulfing-detector-golden-fixture.md) | Done | P2 | — |
| 2 | [EngulfingStrategy + backtest](./phase-02-engulfingstrategy-backtest.md) | Done | P1 | 1 |
| 3 | [Frontend pattern visualization](./phase-03-frontend-pattern-visualization.md) | Done | P2 | 1 |
| 4 | [Docs (scale-out limit + swing pivot)](./phase-04-docs-scale-out-limit-swing-pivot.md) | Done | P3 | — |
| 5 | [Verify](./phase-05-verify.md) | Done | P1 | 1,2,3,4 |

Phase 1 (detector + golden fixture) là nền: cả Phase 2 (Python) và Phase 3 (TS) dùng chung fixture. Phase 4 (docs) độc lập. Phase 5 verify cuối.

## Acceptance criteria

- [x] `GET /backtest/strategies` liệt kê `engulfing` (registry chứa `engulfing`; test `test_engulfing_registered_in_strategy_registry`).
- [x] Detector golden fixture: TS test và Python test ra **cùng** tập pattern (bullish/bearish) + **cùng** `rejection_wick_pct` (fixture byte-identical, 9 case; Python `pytest.approx`, TS `toBeCloseTo(…,12)`).
- [x] `EngulfingStrategy` implement `on_bar_completed` + `on_order_filled` (hook MỚI); position cap 1; `_open_direction` set-after-fill, reset đúng.
- [x] Backtest engulfing ra **nhiều trade** (`total_trades > 1` qua full stack); SL/TP từng trade khớp công thức.
- [x] TP = `max(tp_rr, key_level)` (LONG) / `min` (SHORT) — luôn ≥ RR 1:1.
- [x] Quality filter loại pattern có wick ngược chiều > ngưỡng; `=1.0` tắt filter (test cả 2).
- [x] Toggle "Engulfing" vẽ markers, strong đậm / weak nhạt; **KHÔNG** override backtest markers (merge chung 1 array trước `setMarkers`).
- [x] 2 docs trong `docs/`: scale-out limitation + swing pivot education.
- [x] `uv run ruff check` + `uv run pytest tests/ -q` xanh (623 passed, 1 skipped); `uv run lint-imports` 7 contracts pass; OpenAPI snapshot không đổi.
- [x] `cd web && npm run lint && npm run build` xanh; `npm run test` (vitest) golden-fixture parity pass (9 case).

> **Tooling note (verified):** project KHÔNG có mypy — bỏ mọi `just types` cho BE; type-check FE qua `tsc -b` (trong `npm run build`). Lệnh canonical theo CI (`.github/workflows/cicd.yml`): `uv run pytest tests/ -q`, `uv run lint-imports`, `uv run ruff check`. `just test-pkg`/`just lint`/`just types` KHÔNG tồn tại trong justfile (README stale).

## Out of scope

- Scale-out / multi-TP / partial close (engine không hỗ trợ — Phase 4 doc + roadmap).
- Backend pattern-detection API (chọn client-side TS).
- Full-range engulfing, trend filter, recent-swing-pivot detect, round-number levels.

## Dependencies

- **blockedBy** `260628-1514-backtest-onfill-sharpe-fix-hook-rename` — hook rename + fill-hook fix. Engulfing chờ plan này land.
- Không plan nào khác chồng lấn.

## Params (CHỐT — validation 2026-06-28)

| Param | Giá trị chốt |
|---|---|
| `sl_buffer_pct` | `0.001` (0.1%) |
| `key_level_lookback_bars` | `20` |
| `max_rejection_wick_pct` | `0.30` **default ban đầu — tune bằng backtest, KHÔNG phải số chốt cứng** (1.0 = tắt filter) |
| `pattern_low`/`pattern_high` | `min`/`max` của **2 nến** (prev + curr) |

Tune sau qua `parameters` dict khi backtest. `max_rejection_wick_pct=0.30` chưa validate với data thật (red-team flag) → coi là điểm khởi đầu, không phải kết luận.

> **Quyết định scope (red-team + user):** GIỮ quality filter (đúng mối lo rejection của user, không cắt). GIỮ vitest cho parity nhưng **copy fixture vào `web/`** thay vì đọc cross-root `node:fs` (giải quyết gốc 2 High finding tsc/eslint).

## Validation Log

### Session — 2026-06-28

#### Verification Results
- **Tier:** Full (5 phases, 4 roles)
- **Claims checked:** 12
- **Verified:** 8 | **Failed:** 4 | **Unverified:** 0

**Verified:**
- import-linter = **7 contracts** (`grep -c '^\[\[tool.importlinter.contracts\]\]' pyproject.toml`).
- `patterns/` dir chưa tồn tại → tạo mới đúng.
- OpenAPI: `/backtest/strategies` trả `list[str]` runtime; thêm strategy không đổi schema (`tests/baseline/test_openapi_snapshot.py`).
- Cross-plan dep `260628-1514` chính xác; bidirectional `blockedBy`/`blocks` đã wire.
- ⚠ **Sửa bởi Red Team:** claim "hook vẫn `on_bar`/`on_fill` ở `interfaces.py:37,62`" SAI — working tree đã có `on_bar_completed:51`/`on_order_filled:76` (UNCOMMITTED), HEAD vẫn `on_bar:42`/`on_fill:67`. Đây là dirty-tree state, xem Red Team Finding 1.

**Failures (đã sửa qua interview):**
1. [Fact Checker] `just types` — **không có mypy** trong project (`grep mypy` rỗng) → bỏ; FE type-check qua `tsc -b`.
2. [Fact Checker] `just lint` / `just test-pkg` — **không tồn tại** trong justfile (chỉ `test`) → `uv run ruff check` / `uv run pytest tests/ -q`.
3. [Contract Verifier] FE golden-fixture test — `web/` **không có test runner** (không vitest/jest, 0 test file) → quyết định **thêm vitest** (test FE đầu tiên).
4. [Fact Checker] Lệnh canonical = CI `.github/workflows/cicd.yml:32,35` (`uv run lint-imports`, `uv run pytest tests/ -q`).

#### Decisions confirmed
| Topic | Quyết định | Áp dụng |
|---|---|---|
| TS fixture lock | **Thêm vitest** vào `web/`, parity máy enforce | Phase 3, 5 |
| Tooling commands | Sửa hết theo CI canonical (`uv run ...`), bỏ `just types` | Phase 1,2,5 + plan.md |
| Params | Chốt: `sl_buffer_pct=0.001`, `key_level_lookback_bars=20`, `max_rejection_wick_pct=0.30`, pattern extreme = min/max 2 nến | Phase 2 + plan.md |

### Whole-Plan Consistency Sweep
- **Files reread:** plan.md, phase-01..05.
- **Decision deltas checked:** 3 (vitest add, tooling rename, params chốt).
- **Reconciled stale references:** mọi `just types`/`just lint`/`just test-pkg` → `uv run ...`; Phase 3+5 thêm `npm run test`; Phase 1 ghi fixture là source cho vitest; open-questions section → Params CHỐT.
- **Unresolved contradictions:** 0.
- ⚠ Lưu ý còn lại (không phải contradiction): Phase 4 docs tham chiếu `paper_broker.py:636`/`:454` — số dòng có thể dịch sau khi 260628-1514 land; Phase 4 step 1 đã yêu cầu đọc lại trước khi ghi (mô tả invariant ưu tiên hơn số dòng cứng). *(Red Team Finding 1+3 sau đó đã loại bỏ line numbers khỏi Phase 4 — dùng symbol names.)*

## Red Team Review

### Session — 2026-06-28
**Findings:** 15 (13 accepted, 2 rejected) từ 3 reviewer (Failure Mode Analyst/Flow Tracer, Assumption Destroyer/Scope Auditor, Fact Checker + Scope Critic).
**Severity breakdown:** 1 Critical, 4 High, 8 Medium (+2 rejected).

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| 1 | Dependency 260628-1514 dirty-tree (code uncommitted, plan pending); grep-gate false-pass | Critical | Accept | plan.md, P2 step1, P5 step0 |
| 2 | `tsc -b`+`eslint .` vỡ trên `.test.ts` (include src, vite/client types, browser globals) | High | Accept | P3 (tsconfig.test + eslint override) |
| 3 | Phase 4 sai 3 line number (`value_objects:17`→:19, `paper_broker:636`→:642, `:454`→:426/:460) | High | Accept | P4 (bỏ line numbers, dùng symbol) |
| 4 | Phase 2 hook param `OrderAggregate` → thực `FilledOrder` Protocol | High | Accept | P2 |
| 5 | `rejection_wick_pct: None` → `approx(None)` crash + JSON null parity gap | High | Accept | P1 (luôn float, sentinel 1.0) |
| 6 | `_open_direction` set lạc quan → wedge khi entry reject/size=0 | Medium | Accept | P2 (set sau fill) |
| 7 | Chart shows MORE patterns than strategy acts on (warmup+cap) — oversold | Medium | Accept | P4 caveat |
| 8 | Key-level off-by-one (deque maxlen N+1, pre/post-append unspec) | Medium | Accept | P2 (pin: maxlen N, strictly-before) |
| 9 | Param validation incomplete (lookback/buffer unvalidated, swallowed by except) | Medium | Accept | P2 (validate all) |
| 10 | `use-indicators.ts` misdirection (engulfing markers ở trading-chart) | Medium | Accept | P3 |
| 11 | Marker cleanup `length===0` detach → flicker/leak | Medium | Accept | P3 (cleanup on unmount) |
| 12 | OpenAPI escape-hatch wording backwards | Medium | Accept | P5 (schema-only khẳng định) |
| 13 | Cross-root `node:fs` fixture fragile | High→gộp #2 | Accept | P1+P3 (copy vào web/) |
| R1 | Same-bar entry stop-out | High | **Reject** | SL=pattern_low×(1−buf) < entry-bar low → không trigger. Disproven `position_sizer.py`/SL formula. Vẫn thêm test phòng (P2 test c) |
| R2 | `sl_buffer_pct=0.001` neuters risk model | High | **Reject** | Reviewer nhầm buffer=SL distance. Thực `price_risk=entry−SL≈pattern depth` (`position_sizer.py:55-59`). Vẫn thêm position-size test (P2 test d) |

**Scope decisions (user, sau khi nghe giải thích):**
- GIỮ quality filter — đúng mối lo rejection ban đầu; `0.30` = default tune-được (không số chốt).
- GIỮ vitest cho parity NHƯNG copy fixture vào `web/` (không cross-root) — giải quyết gốc Finding 2/13.

### Whole-Plan Consistency Sweep (post-red-team)
- **Files reread:** plan.md, phase-01..05.
- **Decision deltas checked:** 13 accepted findings + 2 scope decisions.
- **Reconciled stale references:** hook param type `OrderAggregate`→`FilledOrder` (P2); gate grep→commit-check (P2,P5,plan.md); `rejection_wick_pct` None→float (P1); fixture cross-root→copy (P1,P3,P5); line numbers→symbol names (P4); `_open_direction` set-after-fill (P2); deque maxlen N+1→N (P2); Validation Log stale claim "hook vẫn on_bar/on_fill" đã đánh dấu sửa.
- **Unresolved contradictions:** 0.
- ⚠ Lưu ý: Finding 6 (set-after-fill) phụ thuộc entry-fill publish `OrderFilledEvent` — P2 step 2 verify; nếu không, fallback optimistic-set+rollback (ghi rõ). Không phải contradiction, là điều kiện cần verify lúc implement.
