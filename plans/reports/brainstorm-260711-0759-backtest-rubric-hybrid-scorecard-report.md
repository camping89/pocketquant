# Brainstorm — Backtest Rubric (hybrid empirical + static-definition + reconciliation)

> Metadata: mode=default (no flags). Scope chốt qua 6 câu AskUserQuestion. Nguồn: scout codebase + prod DB survey (read-only) + deep research (Lopez de Prado, quant metrics). Term tiếng Anh giữ nguyên; prose tiếng Việt.

## Problem statement

Cần một cách **có hệ thống (rubric)** để đánh giá mọi backtest run trong DB theo chuẩn quant analyst — thay vì đọc rời rạc từng `metrics` blob. Hai yêu cầu cốt lõi của user:
1. Rubric xây từ **best-practice quant** (deep research), mang methodology về, build module, chạy cho tất cả run.
2. **Không chỉ dùng DB result** (kết quả) — dùng luôn **strategy definition** (thiết kế) để phân tích. Đối chiếu design-intent vs realized outcome.

## Scout findings (facts, không suy đoán)

**DB (`backtest_runs`, prod VPS, read-only survey):**
- **8 run total → 6 finished, 2 failed.** Tất cả 1 symbol `BTCUSDT:BINANCE`, 1 interval `1m`, cost model (slippage 0.5, commission 3.0).
- 3 strategy: `engulfing` ×3, `hitnrun2` ×4, `engulfing_pullback30_touch` ×1.
- **Duplicate**: `hitnrun2` `019f1780-546f` và `019f1780-6b52` metrics identical → double-persist race artifact. Rubric phải dedup.
- `config_snapshot.parameters = {}` mọi run → params thật nằm trong code `_DEFAULTS`, không phải DB.
- `equity_curve` lưu (trade-keyed realized, ~3.4k–4.5k điểm/run). Per-bar returns curve KHÔNG lưu.
- Trade doc giàu: `entry_price, exit_price, sl_price, tp_price, quantity, pnl, commission, duration_seconds, direction` per-trade → **planned R:R tính trực tiếp từ DB** (không cần đọc _DEFAULTS).
- Run doc có field top-level `verdict` sẵn → chỗ persist tự nhiên.

**Finding chẩn đoán:** `hitnrun2` profit_factor **2.11** nhưng total_return **−3.1%** → gross-edge dương, cost nuốt sạch. Khác hẳn `engulfing` (pf 0.93, vô hướng thật). Rubric phải tách **gross-edge vs net-after-cost**.

**Codebase:**
- `PerformanceCalculatorDomainService` (`core/domain/trading/`) — có total_return, cagr, sharpe, sortino, max_dd, win_rate, profit_factor, avg_win/loss, avg_duration, commission. Thiếu Calmar/MAR/Ulcer/tail/expectancy/PSR/cost-to-edge.
- Strategy service structured rõ (`engulfing_pullback30_touch_strategy_service.py`): params + validation, SL/TP geometry, direction bias → **AST audit khả thi**.
- Layering import-linter khoá core◁engine◁app → module analysis KHÔNG được nhét vào `src/`. Chốt: `scripts/rubric/`.

## Deep research — methodology mang về (fetch nguồn gốc, có công thức)

Fan-out 8 search + fetch source `quantstats` (de-facto standard Python) để lấy **công thức chính xác**, không paraphrase.

### Empirical metrics (công thức từ quantstats/stats.py)

| Metric | Công thức | Threshold (ngành) |
|---|---|---|
| **Calmar** | `CAGR / |maxDD|` | >1 ok, >3 excellent |
| **MAR** | return / maxDD (full history) | >1 institutional, 0.5–1 retail |
| **Ulcer Index** | `sqrt(Σ drawdown² / (n−1))` | <5 tốt, >10 review |
| **Ulcer Perf Index** | `(comp_return − rf) / ulcer_index` | cao = return/pain tốt |
| **Tail ratio** | `|p95 / p5|` của returns | ~1 cân; <1 tail trái nặng |
| **Common Sense Ratio** | `profit_factor × tail_ratio` | >1 (bắt cả overtrading + tail) |
| **CPC Index** | `profit_factor × win_rate × win_loss_ratio` | >1 |
| **Gain-to-Pain** | `Σreturns / |Σ neg returns|` | >1 |
| **Recovery factor** | `|Σreturns| / |maxDD|` | cao = hồi phục nhanh |
| **Kelly criterion** | `((wl_ratio·win_p) − lose_p) / wl_ratio` | position-sizing sanity |
| **Risk of ruin** | `((1−wr)/(1+wr))^n` | ~0 an toàn |
| **SQN (Van Tharp)** | `(expectancy_R / σ_R) × √n` | <1.6 kém, 2–3 tốt, >3 xuất sắc |
| **Cost-to-edge** | gross edge / friction | >1 mới có cơ lời (master-report) |

### Trade-level MAE/MFE reconciliation (nâng cấp câu hỏi "dùng definition")

DB trade doc có `entry/exit/sl/tp/quantity` per-trade; kết hợp `bars` (path intrabar) → đo design-vs-realized **bằng số**:

| Diagnostic | Công thức | Threshold |
|---|---|---|
| **MFE capture rate** | actual exit profit ÷ MFE | >75% xuất sắc; 30–45% rò rỉ edge; <30% redesign |
| **MAE-to-Stop ratio** | avg MAE ÷ stop distance | <0.5 stop quá rộng; 0.6–0.85 calibrated; >0.85 quá chật |

→ Master-report kết luận định tính "SL 14 bps quá chật"; MAE distribution đo được chính xác winner có chạm gần SL không. Đây là reconciliation định lượng.

### Robustness KHÔNG cần sweep — Monte Carlo methods (bổ sung lớn từ research)

| Công cụ | Làm gì | Scale 1-run? |
|---|---|---|
| **Bootstrap trade-order** | resample thứ tự trade 1,000× → phân bố maxDD (real DD thường 3.1× backtest) | ✅ rẻ (không re-simulate) |
| **MCPT signal-permutation** | scramble signal 10k×, `p=(exceed+1)/(n+1)` → alpha thật hay market drift? | ⚠️ đắt (re-run engine) — phase sau |
| **PSR (Probabilistic Sharpe)** | `Φ((SR−SR*)√(n−1) / √(1−γ3·SR+((γ4−1)/4)·SR²))` | ✅ single-series |
| **DSR / PBO / CSCV** | deflate cho multiple-testing / P(overfit) | ❌ cần sweep families → `docs/todo/` |

**Brutal truth:** DSR/PBO/CSCV cần **parameter-sweep families** (nhiều trial cùng 1 strategy). DB có 6 run/3 strategy khác họ, params mặc định → áp DSR/PBO = **theatre thống kê**. Thay bằng **bootstrap + PSR** (academic-đúng, chạy trên 1 run). MCPT signal-perm để phase sau (cần replay engine). DSR/PBO roadmap đầy đủ → `docs/todo/`.

### Cơ sở thực nghiệm cho scoring

- **Wesley Gray**: median **73% Sharpe deterioration** backtest→live; strategy phức tạp sập nặng hơn (>30pp) → DoF-penalty có cơ sở.
- **Lopez de Prado**: sau 1,000 backtest độc lập, expected max Sharpe = **3.26 dù true Sharpe = 0** → lý do DSR tồn tại; và 7 failure modes (cross-validation leakage, backtest overfitting…).

## Approaches đã cân nhắc

**A — DB-only scorecard.** Chỉ metric mở rộng từ result. Đơn giản nhưng bỏ qua strategy definition → không trả lời câu hỏi #2. ❌

**B — Hybrid (CHỌN).** Empirical scorecard + static AST audit + reconciliation design-vs-realized. Trả lời cả 2 câu hỏi. Insight cao nhất (khoảng cách design-vs-realized chính là chẩn đoán). Vẫn KISS thống kê (không giả vờ DSR/PBO). ✅

**C — Full Lopez de Prado (DSR+PBO+CSCV).** Không khả thi ở scale này; kết quả giả. Hoãn → doc todo. ❌

## Giải pháp chốt (Approach B)

### Rubric 3 trục
1. **Performance** (trades + equity_curve): total_return, CAGR, Calmar, MAR, Ulcer, Ulcer Perf Index, recovery factor, Sharpe/Sortino, Gain-to-Pain.
2. **Robustness** (trade PnL dist + Monte Carlo): PSR, **bootstrap maxDD distribution**, SQN, tail ratio, Common Sense Ratio, CPC, expectancy (R), skew/kurtosis, top-5-trade concentration, risk-of-ruin. (MCPT signal-perm → phase sau.)
3. **Design-integrity** (AST audit + reconciliation): degrees-of-freedom (Gray-penalty), **MAE/MFE capture + MAE-to-stop**, entry-frequency class, lookahead-safety, cost-to-edge, planned-vs-realized R:R gap, gross-vs-net edge split.

### Scoring (threshold-based, KISS)
- Threshold **ngành** (Calmar>1 ok/>3 excellent; Ulcer<5 tốt/>10 review; MAR>1 institutional; SQN 2–3 tốt/>3 xuất sắc; PSR>0.95 tin cậy; cost-to-edge>1; MFE-capture>75% / MAE-to-stop 0.6–0.85) — **note crypto-1m caveat** rõ ràng (threshold gốc cho equity/daily).
- Mỗi metric → 0–4 điểm → weighted-sum/trục → grade A–F/trục + tổng. Mọi điểm truy về 1 số + 1 ngưỡng. Không ML.

### Module (`scripts/rubric/`, chạy qua `uv run`, mỗi file <200 LOC)
```
scripts/rubric/
  __init__.py
  empirical_metrics.py    # Calmar/MAR/Ulcer/UPI/tail/CSR/CPC/gain-to-pain/recovery/SQN/Kelly/RoR (quantstats formulas, DRY reuse PerformanceCalculator)
  robustness.py           # PSR + bootstrap trade-order → maxDD distribution (numpy, no re-simulate)
  trade_path_analysis.py  # MAE/MFE per-trade from bars: capture rate, MAE-to-stop
  static_audit.py         # AST parse strategy services → DoF, SL/TP geometry, entry-class, lookahead-safety
  reconciliation.py       # planned R:R (từ per-trade sl/tp/entry) vs realized; gross-vs-net edge split
  scoring.py              # thresholds → điểm → grades (rubric_version versioned)
  render_markdown.py      # comparison table + per-run scorecard
  render_html.py          # self-contained HTML
  run_rubric.py           # CLI: --run-id/--all-finished, --dry-run(default), --persist, --out
```
(8 file logic <200 LOC; `trade_path_analysis` cần đọc `bars` collection cho path intrabar.)

### Outputs (tất cả)
- Comparison table (md) · Per-run scorecard (md) · JSON scorecards (versioned) · HTML self-contained.
- **Persist**: field `verdict.rubric` trong `backtest_runs`, keyed `rubric_version`, idempotent upsert, `--persist` opt-in (mặc định `--dry-run`).

### Xử lý thực tế
- Dedup hitnrun2 546f/6b52 (double-persist).
- Params từ AST `_DEFAULTS`, không từ DB `{}`.
- PSR/Sharpe trên trade-keyed returns (note caveat như code hiện có).
- Tách gross-edge vs net-after-cost để phân biệt "cost giết" (hitnrun2) vs "vô hướng" (engulfing).

## Risks & mitigation
- **Mô tả ≠ validate OOS.** 1 symbol/1 interval/no-sweep → rubric chẩn đoán sức khỏe run, KHÔNG dự báo tương lai. Ghi rõ trong output header.
- **Persist mutate prod.** `--dry-run` default; `--persist` idempotent theo version.
- **AST brittle.** Fallback "unknown" thay vì crash; chỉ 3 strategy nên chi phí maintain thấp.
- **Threshold lệch cho crypto-1m.** Caveat minh bạch; không tự-hiệu-chuẩn từ n=6 (sẽ tự lừa dối).

## Acceptance criteria
- `uv run python scripts/rubric/run_rubric.py --all-finished` → 4 artifact (md table + md scorecards + json + html) cho 6 finished, dedup còn 5 distinct.
- Mỗi run: 3 grade trục + tổng; mọi điểm truy về threshold.
- Reconciliation `engulfing_pullback30_touch` khớp master-report (planned R:R ~1.57, realized âm) — sanity check.
- `docs/todo/` có doc full DSR/PBO/CSCV roadmap.
- `--persist` off default; on → idempotent `verdict.rubric`.

## Out of scope (round này)
DSR/PBO/CSCV implementation · multi-symbol · walk-forward tự động · optimizer/sweep · refactor strategy engine.

## Success metrics
- Chạy 1 lệnh ra 4 artifact cho toàn bộ run, human đọc HTML hiểu ngay run nào khỏe/bệnh ở trục nào.
- Rubric reproduce được chẩn đoán master-report (engulfing vô hướng; hitnrun2 cost-killed) — chứng minh rubric bắt đúng bệnh.

## Sources (deep research)
Metric formulas (authoritative):
- [quantstats/stats.py — Ran Aroussi (source code, exact formulas)](https://github.com/ranaroussi/quantstats/blob/main/quantstats/stats.py)
- [Trading Metrics that Actually Matter — Quant Fiction (CSR, CPC)](https://quantfiction.com/2018/08/20/trading-metrics-that-actually-matter/)
- [Advanced Trading Metrics: Sharpe, Sortino, Calmar, SQN, K-Ratio](https://tradingwyckoff.com/en/algorithmic-trading/advanced-trading-metrics/)

Trade-level MAE/MFE:
- [MAE/MFE analysis + capture/stop thresholds — Trader's Second Brain](https://traderssecondbrain.com/guides/mae-mfe-analysis)
- [SQN / R-multiple / expectancy — JournalPlus](https://journalplus.co/topics/performance-metrics/)

Robustness / overfitting:
- [Monte Carlo Permutation Tests for Strategy Significance — Susan Potter](https://www.susanpotter.net/quant/monte-carlo-permutation-tests-strategy-significance/)
- [Trading Strategy Robustness Testing 2026 (bootstrap, MC, jitter)](https://blog.pickmytrade.io/trading-strategy-robustness-testing-2026-guide/)
- [Avoid Complexity and Magical Backtests — Wesley Gray / Alpha Architect (73% Sharpe decay)](https://alphaarchitect.com/looking-at-alternatives-avoid-complexity-and-magical-backtests/)
- [7 Reasons Most ML Funds Fail — Lopez de Prado (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3031282)

Deferred (DSR/PBO/CSCV → docs/todo):
- [The Deflated Sharpe Ratio — Bailey & Lopez de Prado (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- [The Probability of Backtest Overfitting — davidhbailey.com (PDF)](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- [PBO / CSCV — CRAN pbo package](https://cran.r-project.org/web/packages/pbo/readme/README.html)

## Unresolved questions
- Verdict schema: `verdict.rubric` co-exist với các key `verdict` khác thế nào? (cần đọc consumer của `verdict` trước khi ghi — làm ở phase plan).
- HTML output: standalone hay reuse `docs/visuals/` style? (quyết định ở plan).
- PSR benchmark Sharpe: dùng SR*=0 hay SR* theo số run? (n=6 → dùng 0, ghi caveat).
