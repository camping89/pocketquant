---
title: "PaperBroker futures-accounting fix (divide-by-zero root cause)"
description: "Chuyển PaperBroker sang futures/margin accounting — xóa 2 bug (total_equity rớt 0 khi all-in; double-count realized_pnl khi close) là root cause của divide-by-zero ở Sharpe/Sortino. TDD: regression test pin hành vi đúng trước khi sửa core broker dùng chung forward-test."
status: done
priority: P1
branch: "develop"
tags: [paper-broker, accounting, backtest, metrics, bugfix, tdd]
blockedBy: []
blocks: []
created: "2026-06-28T13:50:00.491Z"
createdBy: "ck:plan"
source: skill
---

# PaperBroker futures-accounting fix (divide-by-zero root cause)

## Overview

Report `plans/reports/follow-up-tech-debt-260628-2009-performance-calculator-divide-by-zero-report.md` chẩn đoán divide-by-zero là cosmetic. Brainstorm `plans/reports/brainstorm-paper-broker-futures-accounting-260628-2013-divide-by-zero-root-cause-report.md` bác bỏ: đó là triệu chứng của **2 bug accounting thật trong `PaperBroker`**, cùng 1 root cause (trộn mô hình spot + futures). Fix bằng cách chuyển hẳn sang **futures/margin model**.

| Bug | Triệu chứng | Verify |
|---|---|---|
| **1** — `total_equity` rớt ~0 khi mở all-in | MTM curve có điểm `0` → Sharpe/Sortino bị ép `0.0` sai, drawdown giả -100% | `returns_curve` index 7/16/25 = 0.0 |
| **2** — double-count `realized_pnl` khi close | balance sai +5.5% | broker final = 11107.4, đúng = 10553.7 |

**Quyết định đã chốt (user):** Scope C (cả 2 bug) · model **C-futures** · giữ guard calculator · document accounting trong `docs/`. **Sau red-team:** (a) **tối giản** — giữ `available_balance = _balance` (KHÔNG đổi sang free-margin), cắt `_can_afford` rewrite + `_compute_free_margin` helper; (b) **thêm price propagation** — mark broker positions to market per-bar để MTM curve có nghĩa.

**Scout đã resolve:** OKX = SWAP/perp futures (`okx_broker.py:308-309`) → domain khớp futures; leverage **1× cố định** (không có field leverage trong config). **available_balance có 3 consumer** (red-team C1): `handler.py:38` (`<=0` gate), `handler.py:100` (`calculate_max_size`, không trong order path), và `strategy_app_service.py:361` → `PositionSizer.calculate_size` (sizing live/forward thật). → giữ `available_balance = _balance` để KHÔNG đổi sizing behavior.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Regression tests (tests-first)](./phase-01-regression-tests-tests-first.md) | Done |
| 2 | [Fix PaperBroker accounting](./phase-02-fix-paperbroker-accounting.md) | Done |
| 3 | [Guard calculator + engulfing asserts](./phase-03-guard-calculator-engulfing-asserts.md) | Done |
| 4 | [Docs accounting model](./phase-04-docs-accounting-model.md) | Done |
| 5 | [Verify](./phase-05-verify.md) | Done |

## Accounting model (futures, 1× leverage) — tối giản

```
total_equity      = _balance + Σ unrealized_pnl(open)   # unrealized track per-bar (price propagation)
available_balance = _balance                            # GIỮ NGUYÊN — không đổi sizing behavior
```

- **Open / add** (chiều cùng dấu): KHÔNG đụng `_balance`.
- **Close / reduce**: `_balance += Δrealized` (delta của lần reduce này, KHÔNG phải cumulative `position.realized_pnl`).
- `_balance` chỉ đổi khi có realized pnl → final = `initial + Σ realized` (đúng 1×).
- `available_balance = _balance` (formula giữ nguyên). KHÔNG đổi `_can_afford`, KHÔNG thêm `_compute_free_margin`/`margin_used` tracking.

**Behavior change được thừa nhận (red-team C1/C2):** formula `available_balance = _balance` không đổi, NHƯNG vì futures không trừ notional khỏi `_balance` ở open, **giá trị** `available_balance` khi đang có vị thế mở sẽ cao hơn so với spot buggy hiện tại. Hệ quả:
- Strategy round-trip 1 vị thế (engulfing, hitnrun2 — đóng trước khi mở mới): khi flat, `available_balance = _balance = full` → sizing **không đổi**.
- Pyramiding / multi-symbol (size entry chồng khi đang có vị thế mở): spot buggy hiện cho `available ~0` (chicken-egg sẵn có) → size~0; futures cho `available = full` → size bình thường. Đây là hành vi **đúng** cho futures (margin không tiêu cash), nhưng là behavior change so với code buggy. Không có strategy hiện tại pyramiding → tác động forward thực tế = 0; flag để maintainer biết.

**Cảnh báo delta (tránh tạo bug mới):** `PositionAggregate.reduce_quantity` cộng dồn vào `self.realized_pnl` (cumulative). Nếu `_balance += live.realized_pnl` thì partial-close lần 2 cộng lại cumulative → triple-count. Phải capture delta trong broker:
```python
before = live.realized_pnl
live.reduce_quantity(qty, fill_price)
self._balance += live.realized_pnl - before
```

## Price propagation (red-team C4 — mảnh thiếu để curve có nghĩa)

`get_balance:385` tính `unrealized` từ `position.current_price`, nhưng broker KHÔNG mark position to market per-bar — `_on_bar_completed:559` chỉ set `_current_prices` dict, còn `current_price` của `PositionAggregate` chỉ đổi trong open/add/reduce (`entities.py:99,124`). → giữa các fill `unrealized=0`, `total_equity` phẳng = `_balance`. Fix xóa điểm `0` (hết divide-by-zero) nhưng curve vẫn phẳng → Sharpe vẫn bị ép 0.

**Fix (validate-chốt: đặt ở `_on_bar_completed`, KHÔNG side-effect trong getter):** mark open positions to `event.close` ở cuối `_on_bar_completed` (sau SL/TP loop, `paper_broker.py:576`). `get_balance` thuần đọc.
```python
# cuối _on_bar_completed, sau _fire_synthetic_exit loop
async with self._lock:
    for pos in self._positions.values():
        if not pos.is_closed and pos.symbol == event.symbol:
            pos.update_price(event.close)
```
**Ordering (đã verify):** `_mtm_on_bar` (`backtest_app_service.py:90-94`) subscribe SAU broker `_on_bar_completed` (comment `:87-89`) → broker mark positions trước, `_mtm_on_bar` gọi `get_balance` đọc unrealized đã update → `total_equity` track giá per-bar. `get_balance` giữ thuần đọc (không mutate).

## Acceptance criteria (toàn plan)

- [x] No divide-by-zero ở `performance_calculator` (guard targeted, không gate `PYTHONWARNINGS=error` toàn suite — red-team C12)
- [x] Engulfing test: broker final balance = `initial + Σ realized` re-derive từ trade log của chính run đó (KHÔNG hard-pin `10553.7` — red-team C9); structural assert "no double-count" (mỗi reduce += đúng delta)
- [x] Sau price propagation: MTM curve track giá per-bar (không phẳng giữa fill); Sharpe/Sortino finite và non-zero khi có biến động thật (fixture high-volatility); `max_drawdown` phản ánh swing thật
- [x] Regression: long/short/partial-close + add-then-reduce round-trip — `_balance` + `total_equity` đúng số kỳ vọng; `available_balance == _balance` giữ nguyên
- [x] SL/TP synthetic-exit có balance assertion (red-team C5)
- [x] `available_balance` semantics + sizing behavior KHÔNG đổi (giữ `= _balance`); forward path không regress
- [x] `uv run pytest` (640 passed, 1 skipped) + `ruff` + `pyright` xanh; import-linter 7 contracts không vỡ
- [x] Docs `system-architecture.md` có sub-section futures vs spot accounting

## Implementation Delta (post-plan)

Red-team C3/C7 chốt giữ `_can_afford` nguyên. Code review sau implement nâng lại latent High: dưới futures, BUY cover một SHORT có cover-notional > balance bị `_can_afford` REJECT → kẹt vị thế (inert hôm nay vì engulfing/hitnrun2 đóng short qua SL/TP synthetic exit, bypass `_can_afford`). **User chốt thêm minimal guard now:** `_can_afford` trả `True` khi BUY reduce/cover SHORT đang mở (cover không tiêu margin). KHÔNG đổi sizing/round-trip hiện tại; thêm test `test_losing_short_cover_not_blocked_by_affordability` + docs note. Đây là delta có chủ đích so với plan scope gốc.

## Dependencies

Không có plan đang mở chặn/được chặn. Plan liên quan `260628-1514-backtest-onfill-sharpe-fix-hook-rename` đã `status: done` (đã sửa annualization 365; plan này sửa tầng accounting bên dưới, độc lập). Live `OKXBroker` không đụng (balance từ sàn).

## Red Team Review

### Session — 2026-06-28
**Findings:** 12 (10 accepted, 2 rejected/noted)
**Severity breakdown:** 4 Critical, 3 High, 5 Medium
**Reviewers:** Failure Mode Analyst (Flow Tracer), Assumption Destroyer (Scope Auditor), Scope & Complexity Critic (Contract Verifier)

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| C1 | `available_balance` có 3 consumer (sizing path missed), không phải 2/no-FE | Critical | Accept | plan.md, Ph2 |
| C2 | Free-margin → sizing chicken-and-egg (size=0 khi positioned) | Critical | Accept (giải bằng giữ `=_balance`) | plan.md, Ph2 |
| C3 | `_can_afford` rewrite = scope creep + trap close-short BUY | Critical | Accept (CẮT rewrite) | Ph2 |
| C4 | MTM curve vẫn phẳng — broker không mark position per-bar | Critical | Accept (thêm price propagation) | plan.md, Ph2 |
| C5 | SL/TP synthetic-exit không có balance assertion | High | Accept | Ph1, Ph5 |
| C7 | `handler.py:38` guard đảo nghĩa dưới free-margin | High | Reject (giữ `=_balance` → guard không đổi nghĩa; latent, no EXIT emitter) | — |
| C8 | `_can_afford` gọi 3 nơi không phải 1 | High | Accept (moot sau khi cắt, ghi chú) | Ph2 |
| C9 | Không hard-pin `10553.7` (sizing đổi → số đổi) | Medium | Accept | Ph5 |
| C10 | Characterization test chỉ assert upl=0 → phantom | Medium | Accept | Ph3 |
| C11 | Thiếu test add-then-reduce (long/short) | Medium | Accept | Ph1 |
| C12 | `PYTHONWARNINGS=error` gate quá rộng; cắt Ph4 diagram | Medium | Accept | Ph3, Ph4, Ph5 |
| — | Phase 1 red-first arithmetic chưa chứng minh per-test | Medium | Accept (precompute trong Ph1) | Ph1 |

**OKX parity (C6):** giữ `available_balance = _balance` (không claim free-margin parity) → docs Phase 4 KHÔNG khẳng định "khớp availBal"; chỉ mô tả PaperBroker model + ghi rõ OKX `availBal` định nghĩa riêng (unverified external — không claim parity).

### Whole-Plan Consistency Sweep (Red Team)
- Files reread: plan.md, phase-01..05
- Decision deltas checked: 3 (available_balance giữ `=_balance` không phải free-margin; cắt `_can_afford`/`_compute_free_margin`; thêm price propagation)
- Reconciled stale references: phase-01 (bỏ free-margin tests, thêm SL/TP + add-then-reduce + price-prop + available==balance), phase-02 (cắt `_can_afford` rewrite + helper, thêm price propagation, available=_balance), phase-03 (characterization futures open + post-mark, không gate toàn suite), phase-04 (bỏ diagram + OKX parity claim), phase-05 (re-derive không hard-pin, targeted gate, SL/TP balance). plan.md "Accounting model": sửa `available = total_equity − margin_used` → `= _balance`; gỡ `margin_used` khỏi formula chính.
- Behavior-change được thừa nhận tường minh (available_balance value khi positioned cao hơn spot buggy; tác động forward = 0 vì không strategy pyramiding).
- Unresolved contradictions: 0
- Lưu ý: bảng Bug (plan.md:24) giữ số chẩn đoán gốc `11107.4/10553.7` làm bằng chứng bug — Phase 5 KHÔNG hard-pin số này (re-derive); không mâu thuẫn (số là evidence chẩn đoán, không phải acceptance target).

## Validation Log

### Session 1 — 2026-06-28
**Verification Pass:** SKIPPED (guard) — `## Red Team Review` đã có verification evidence tận code (Flow Tracer/Scope Auditor/Contract Verifier verify file:line). Không còn `[UNVERIFIED]` tag.

**Questions asked:** 3 (genuine decision points)

| # | Decision point | Chốt | Propagated |
|---|---|---|---|
| 1 | Vị trí price propagation | **`_on_bar_completed`** (không side-effect trong getter); ordering verified `_mtm_on_bar` subscribe sau | plan.md, Ph1 test#7, Ph2 |
| 2 | Assert Sharpe≠0 risk | **Fixture high-volatility riêng** (`test_sharpe_nonzero_on_volatile_curve`), tách khỏi engulfing round-trip | Ph3 |
| 3 | `available_balance` pyramiding behavior change | **Chấp nhận + ghi docs** known semantics, không thêm guard (YAGNI) | Ph4 |

### Whole-Plan Consistency Sweep (Validate)
- Files reread: plan.md, phase-01..05
- Decision deltas checked: 3 (price prop location → `_on_bar_completed`; Sharpe≠0 → fixture riêng; pyramiding → docs note)
- Reconciled: plan.md price-prop section (getter→`_on_bar_completed` + ordering); Ph1 test#7 (BarCompletedEvent thay set_current_price); Ph2 (mark ở `_on_bar_completed`, get_balance thuần đọc, success criteria + risk); Ph3 (engulfing assert finite + fixture riêng cho ≠0); Ph4 (pyramiding semantics note).
- Stale check: "lazy trong get_balance"/"side-effect getter" đã gỡ khỏi mọi nơi; engulfing "Sharpe≠0" đã chuyển sang fixture riêng.
- Unresolved contradictions: 0
