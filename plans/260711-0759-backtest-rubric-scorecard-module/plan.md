---
title: "Backtest rubric scorecard module"
description: "Offline quant-analyst rubric for all backtest runs: empirical metrics + Monte-Carlo robustness + MAE/MFE reconciliation + static AST audit, scored on 3 axes → A–F. scripts/rubric/, uv run. Persist to new top-level scorecard field."
status: completed
priority: P2
branch: "develop"
tags: [backtest, analytics, rubric, quant, scripts]
blockedBy: []
blocks: []
created: "2026-07-11T03:52:35.396Z"
createdBy: "ck:plan"
source: skill
---

# Backtest rubric scorecard module

## Overview

Một module phân tích **offline** (`scripts/rubric/`, chạy qua `uv run`) chấm điểm mọi backtest run theo chuẩn quant analyst. Không đụng trading path — đọc DB read-only, chỉ ghi khi `--persist`. Rubric 3 trục (**Performance · Robustness · Design-integrity**) → điểm 0–4/metric → grade **A–F**/trục + tổng. Trả lời 2 câu hỏi của user: (1) đánh giá run theo best-practice quant; (2) dùng cả **strategy definition** (static AST audit) chứ không chỉ DB result.

Brainstorm (self-contained, có công thức + nguồn): [`../reports/brainstorm-260711-0759-backtest-rubric-hybrid-scorecard-report.md`](../reports/brainstorm-260711-0759-backtest-rubric-hybrid-scorecard-report.md)
Deferred roadmap (DSR/PBO/CSCV): [`../../docs/todo/deflated-sharpe-pbo-cscv-roadmap.md`](../../docs/todo/deflated-sharpe-pbo-cscv-roadmap.md)

## Decisions (chốt qua brainstorm + scout, KHÔNG đảo lại nếu không có evidence mới)

- **Module ở `scripts/rubric/`** — analysis tooling, KHÔNG nhét vào `src/` (import-linter khoá core◁engine◁app). Chạy `uv run python scripts/rubric/run_rubric.py`.
- **Persist vào field top-level MỚI `scorecard`** (object) trên `backtest_runs` doc — KHÔNG dùng `verdict` (scout: `verdict` là scalar `str | None`, có PATCH route + FE consumer đọc `r.verdict`; ghi nested vào đó phá `from_mongo` + API `list_runs` + FE). Entity `from_mongo` chỉ đọc field đã biết → key top-level mới bị bỏ qua an toàn.
- **`--dry-run` mặc định; `--persist` opt-in**, idempotent upsert keyed theo `rubric_version`.
- **DRY reuse** `PerformanceCalculatorDomainService` (`core/domain/trading/`) cho metric đã có (Sharpe/Sortino/maxDD/profit_factor/…); chỉ viết mới phần thiếu.
- **PSR dùng `math.erf`** cho normal CDF Φ — KHÔNG thêm scipy (chưa có trong venv). `Φ(x)=0.5·(1+erf(x/√2))`.
- **Params thật từ AST** (`config_snapshot.parameters = {}` mọi run) — parse `_DEFAULTS` + geometry từ strategy service file, resolve qua `STRATEGY_REGISTRY[code].__module__`.
- **Dedup**: `hitnrun2` `019f1780-546f`/`6b52` metrics identical (double-persist race) → gộp, đánh dấu, không đếm 2 lần.
- **MCPT signal-permutation HOÃN** (cần replay engine, đắt) → round này chỉ **bootstrap trade-order** (rẻ, numpy) + PSR.
- **Threshold ngành** (Calmar>1/>3, Ulcer<5/>10, MAR>1, SQN 2–3/>3, PSR>0.95, cost-to-edge>1, MFE-capture>75%, MAE-to-stop 0.6–0.85) + **crypto-1m caveat** in trong output header.
- **`rubric_version` versioned** trong scoring — đổi threshold/weight ⇒ bump version, persist theo version.
- **[Validation S1] Returns basis** = **per-trade returns (bps notional)** cho return-distribution metrics (tail_ratio, gain_to_pain, PSR, SQN, expectancy). Ulcer/Calmar/Recovery/maxDD **buộc dùng `equity_curve`** (drawdown-based — cấu trúc, không phải lựa chọn). Ghi rõ basis trong docstring mỗi metric.
- **[Validation S1] Bootstrap** = **sequencing-only** (permutation thứ tự trade, giữ nguyên tập PnL) — đo sequencing risk. KHÔNG resample-with-replacement round này.
- **[Validation S1] Overall grade** = **weakest-axis dominates** (overall ≈ min 3 trục) — robustness F kéo tụt overall dù performance cao. KHÔNG weighted-average (che dấu điểm F).
- **[Validation S1] Reference doc** = thêm **`docs/backtest-rubric/methodology.md`** (threshold table + công thức + diễn giải, tiếng Anh theo rule docs/) — reference lâu dài, versioned cùng `RUBRIC_VERSION`.
- **[Validation S2] Output dir** = **`docs/backtest-rubric/`** (gom methodology + 4 generated artifact một chỗ dưới docs/). `--out` default trỏ đây; artifact commit như snapshot (docs/ được commit).
- **[Validation S2] Test location** = **`tests/scripts/rubric/`** (cây tests/ chuẩn, vào default `just test` + coverage). KHÔNG co-located.
- **[Validation S2] DB target** = **prod read-only, connection LAZY**: `MONGODB_URL` từ env (như recompute script), chỉ ghi khi `--persist`. Connection PHẢI lazy (trong function, không module-level) — để `import` module không vướng conftest prod-guard (`207.148.79.60`) khi unit test chạy dưới `tests/`.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Foundation & data access](./phase-01-foundation-data-access.md) | Completed |
| 2 | [Empirical metrics & reconciliation](./phase-02-empirical-metrics-reconciliation.md) | Completed |
| 3 | [Robustness (PSR + bootstrap)](./phase-03-robustness-psr-bootstrap.md) | Completed |
| 4 | [Trade-path MAE/MFE](./phase-04-trade-path-mae-mfe.md) | Completed |
| 5 | [Static AST audit](./phase-05-static-ast-audit.md) | Completed |
| 6 | [Scoring engine](./phase-06-scoring-engine.md) | Completed |
| 7 | [Renderers (md/json/html)](./phase-07-renderers-md-json-html.md) | Completed |
| 8 | [CLI orchestration & persist](./phase-08-cli-orchestration-persist.md) | Completed |

## Dependencies

**Cross-plan (không blocking):** `260630-0031-backtest-mae-mfe-excursion` (P3, pending) cũng tính MAE/MFE nhưng **trong engine** (broker SL/TP path, forward-only, mutate `Trade` domain, run mới). Rubric tính MAE/MFE **offline từ `bars`** cho run cũ trong `scripts/`. Khác file ownership (`src/` vs `scripts/`), khác timing (live vs offline), không đụng nhau — KHÔNG block. Nếu plan engine chạy sau, rubric có thể đọc field mae/mfe DB thay vì tự tính (tối ưu tương lai, không phải giờ).

**Intra-plan:** P1 (foundation) block tất cả. P2–P5 độc lập nhau (đều chỉ phụ thuộc P1), làm song song được. P6 (scoring) blockedBy P2–P5 (cần metric để chấm). P7 (renderers) blockedBy P6. P8 (CLI) blockedBy P7.

## Acceptance criteria

- [x] `uv run python scripts/rubric/run_rubric.py --all-finished` → 4 artifact vào `docs/backtest-rubric/` (comparison `.md` + per-run scorecards `.md` + `.json` + `.html`) cho 6 finished run, **dedup còn 5 distinct**.
- [x] Mỗi run: 3 grade trục + tổng; mọi điểm truy về 1 metric + 1 threshold (không có điểm "mờ").
- [x] Reconciliation `engulfing_pullback30_touch` (`019f36d2`) khớp master-report: planned R:R mean ~1.71 (master ~1.57), realized R-multiple −0.039 (âm, master ~−0.05), win_rate 42.9% exact, mae_to_stop 0.90 (SL quá chật). `hitnrun2` gross +5.46 bps nhưng net −1.54 (cost-killed, cost_to_edge 0.78); `engulfing` gross ≈ 0 (no-edge) — rubric phân biệt được 2 bệnh.
- [x] `--persist` off mặc định; on → field `scorecard` upsert idempotent theo `rubric_version` (single `$set`), KHÔNG đụng `verdict`/`metrics`/`equity_curve`. `--dry-run` override `--persist`.
- [x] HTML self-contained (inline CSS/JS, mở file:// đọc được), có crypto-1m caveat header.
- [x] `docs/backtest-rubric/methodology.md` tồn tại, threshold table khớp `THRESHOLDS` code, header có `RUBRIC_VERSION`.
- [x] Overall grade = weakest-axis (min 3 trục); test robustness=F + performance=A → overall ≤ D.
- [x] `ruff` + `pyright` clean trên `scripts/rubric/`.
- [x] Unit test dưới `tests/scripts/rubric/` (69 test) cho metric math (PSR, Ulcer, Calmar, SQN, bootstrap sequencing-only) + AST audit 3 strategy + renderers + dedup; pure math (không cần DB — connection lazy). Chạy cần override `MONGODB_URL` local (conftest prod-guard chặn khi direnv nạp prod URL).

## Constraints (CLAUDE.md)

- Read-only DB mặc định; `MONGODB_URL` từ env, KHÔNG hardcode. Query qua `uv run` (venv có pymongo 4.16; skills venv KHÔNG có).
- **Connection LAZY** (trong function, không module-level) — import `scripts/rubric/*` không được connect Mongo, để unit test dưới `tests/scripts/rubric/` không vướng conftest prod-guard (`207.148.79.60`) khi direnv nạp prod URL. Test math = pure, không cần DB.
- Mỗi file logic <200 LOC → tách theo module boundary.
- KHÔNG thêm dependency mới (numpy đã có; PSR dùng `math.erf`).
- `scripts/` KHÔNG import ngược vào trading path để mutate; chỉ đọc `PerformanceCalculatorDomainService` như pure function.
- AS-IS: không changelog/banner trong code; comment chỉ cho chỗ khó hoặc quirk.

## Out of scope

DSR/PBO/CSCV (→ docs/todo) · MCPT signal-permutation (phase sau) · multi-symbol/multi-interval · walk-forward tự động · optimizer/sweep · refactor strategy engine · FE/dashboard integration.

## Validation Log

### Session 1 — 2026-07-11
**Trigger:** `/ck:plan validate` sau khi tạo plan (mode default, Full-tier verification 8 phase).
**Questions asked:** 4

#### Verification Results
- **Tier:** Full (8 phases, 4 roles)
- **Claims checked:** 6 | **Verified:** 6 | **Failed:** 0 | **Unverified:** 0
- Fact Checker: `STRATEGY_REGISTRY` + 3 keys (`services/__init__.py:11-15`) ✓; 6 `PerformanceCalculatorDomainService` methods reuse ✓; bars fields open/high/low/close/datetime (`bar_repository.py:92-135`) ✓.
- Contract Verifier: `EquityPoint.drawdown` (`value_objects.py:26`) ✓; `BacktestResult.from_mongo` dùng explicit `data.get()` per-field + docstring "ignores legacy keys" → field top-level mới `scorecard` KHÔNG phá `from_mongo`/API/FE ✓ (xác nhận quyết định persist an toàn).
- Scope Auditor: `scorecard` field độc lập `verdict`/`metrics`/`equity_curve` ✓.

#### Questions & Answers
1. **[Assumptions]** Returns basis cho PSR/tail/gain-to-pain? → **Per-trade returns (bps notional)** cho return-distribution metrics; Ulcer/Calmar/maxDD buộc equity_curve (drawdown-based). Ảnh hưởng: nhất quán master-report, tránh PSR lệch do equity_curve không đều nhịp.
2. **[Architecture]** Bootstrap kiểu nào? → **Sequencing-only** (permutation). Đo sequencing risk; KHÔNG resample-with-replacement (YAGNI round này).
3. **[Tradeoffs]** Overall grade? → **Weakest-axis dominates** (≈min). Robustness F kéo tụt overall dù performance cao — không che dấu điểm F.
4. **[Scope]** Docs reference? → **Có, `docs/rubric-methodology.md`** (English, versioned cùng RUBRIC_VERSION). *(→ S2 dời thành `docs/backtest-rubric/methodology.md`.)*

#### Confirmed Decisions
- Returns basis: per-trade bps (distribution metrics) + equity_curve (drawdown metrics).
- Bootstrap: sequencing-only permutation.
- Overall grade: weakest-axis dominates.
- Add `docs/rubric-methodology.md`.

#### Impact on Phases
- Phase 2: docstring mỗi metric ghi rõ returns basis (per-trade vs equity).
- Phase 3: bootstrap = sequencing-only (đã khớp; xác nhận KHÔNG resample-with-replacement).
- Phase 6: overall grade = weakest-axis (min-based), KHÔNG weighted-average; scoring reference → docs.
- Phase 6/7: thêm task tạo `docs/rubric-methodology.md`.

### Whole-Plan Consistency Sweep
- Files reread: plan.md, phase-01…phase-08 (grep-based delta scan).
- Decision deltas checked: 4 (returns basis, bootstrap type, overall grade, docs).
- Reconciled stale references: 2 — Phase 6 "weighted-sum … + tổng" → tách rõ 2 cấp (metric→axis weighted-sum, axis→overall min); Phase 3 "bootstrap resample" → "permutation (sequencing-only)".
- Unresolved contradictions: 0.

### Session 2 — 2026-07-11
**Trigger:** `/ck:plan validate` lần 2 trên active plan. Verify sâu testing + connection lifetime (facts Session 1 chưa kiểm).
**Questions asked:** 3

#### Verification Results (new facts)
- Fact Checker: `pyproject.toml` `testpaths=["tests"]` → `pytest` default chỉ quét `tests/`, không `scripts/`. Tiền lệ `scripts/backfill/test_binance_bars.py` co-located (excluded default, chạy explicit). `asyncio_mode=auto`, `--import-mode=importlib`.
- Scope Auditor: `tests/conftest.py` prod-guard refuse khi `MONGODB_URL`/`REDIS_URL` chứa `207.148.79.60` (line 28,53-57). direnv `.env` nạp prod URL vào env → module-level Mongo connect trong `scripts/rubric/` sẽ vướng guard lúc import test. → ràng buộc connection LAZY.
- `tests/scripts/` đã tồn tại (convention có sẵn).

#### Questions & Answers
1. **[Architecture]** Test location? → **`tests/scripts/rubric/`** (cây tests/ chuẩn, vào default `just test` + coverage). Override tiền lệ co-located của backfill.
2. **[Risks]** DB target? → **Prod read-only, connection LAZY** (client trong function, không module-level). Tránh conftest prod-guard khi import test.
3. **[Scope]** Output dir? → **`docs/backtest-rubric/`** (gom methodology + 4 artifact một chỗ dưới docs/; commit như snapshot). Dời `docs/rubric-methodology.md` → `docs/backtest-rubric/methodology.md`.

#### Confirmed Decisions
- Test → `tests/scripts/rubric/` (vào default `just test`; import pure, không DB).
- DB → prod read-only, connection lazy (import không connect).
- Output → `docs/backtest-rubric/` (methodology.md + 4 generated artifact, committed).

#### Impact on Phases
- Phase 1: connection LAZY (client trong function) + constraint note.
- Phase 2: test-location anchor `tests/scripts/rubric/`.
- Phase 6: docs path `docs/rubric-methodology.md` → `docs/backtest-rubric/methodology.md`.
- Phase 7/8: `--out` default `plans/reports/rubric/` → `docs/backtest-rubric/`.

### Whole-Plan Consistency Sweep (S2)
- Files reread: plan.md, phase-01,02,06,07,08 (path/test/connection deltas).
- Decision deltas checked: 3 (test location, DB lazy, output dir).
- Reconciled stale references: 4 — `plans/reports/rubric/` → `docs/backtest-rubric/` (plan.md AC, phase-07, phase-08); `docs/rubric-methodology.md` → `docs/backtest-rubric/methodology.md` (phase-06 ×4, plan.md). S1 log giữ nguyên lịch sử + con trỏ "→ S2".
- Unresolved contradictions: 0.
