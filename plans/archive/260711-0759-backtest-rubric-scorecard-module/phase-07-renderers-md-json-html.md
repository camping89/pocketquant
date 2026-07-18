---
phase: 7
title: "Renderers (md/json/html)"
status: completed
priority: P2
dependencies: [6]
---

# Phase 7: Renderers (md/json/html)

## Overview

Xuất ScorecardResult ra 4 artifact: comparison table (md), per-run scorecard (md), JSON (machine-readable versioned), HTML self-contained (human-readable). Không đụng DB (persist ở Phase 8).

## Requirements

- Functional: 4 output format từ list[ScorecardResult]; mọi output có crypto-1m caveat + rubric_version header.
- Non-functional: HTML self-contained (inline CSS/JS, mở file:// được, không network asset); JSON stable schema versioned.

## Architecture

```
scripts/rubric/
  render_markdown.py   # render_comparison_table(results), render_scorecard(result)
  render_html.py       # render_html(results) -> self-contained string
  # JSON: dataclasses.asdict(result) + version wrapper (inline trong run_rubric hoặc helper nhỏ)
```

- **Comparison table (md)**: 1 hàng/run — strategy, symbol/interval, 3 axis grades, overall, xếp hạng theo overall. Header: rubric_version + caveat.
- **Per-run scorecard (md)**: 1 section/run — full metric breakdown (giá trị + band + điểm), reconciliation (planned vs realized R:R, gross-vs-net), MAE/MFE diagnostics, static audit (DoF, geometry, lookahead), diagnosis text (vd "cost-killed" / "no directional edge").
- **JSON**: `{rubric_version, generated_note, caveat, runs: [asdict(result)...]}`. Aliases (dedup) ghi kèm.
- **HTML**: editorial, self-contained. Bảng so sánh + accordion/section per-run + màu theo grade (A xanh→F đỏ). Inline CSS, không framework. Đọc offline.

## Related Code Files

- Create: `scripts/rubric/render_markdown.py`, `scripts/rubric/render_html.py`
- Uses: `ScorecardResult` (Phase 1/6)

## Implementation Steps

1. `render_markdown.render_comparison_table`: sort theo overall grade, cột axis + overall.
2. `render_markdown.render_scorecard`: per-run detail, breakdown table + diagnosis.
3. `render_html.render_html`: template string inline CSS; grade color coding; caveat banner; per-run collapsible.
4. JSON serialize: `dataclasses.asdict` + wrapper version/caveat/aliases.
5. Diagnosis text: rule đơn giản từ scores (gross>0 & net<0 → "cost-killed"; gross≈0 → "no edge"; PSR<0.5 → "unreliable").
6. Test: render 2-3 synthetic results → md valid, html mở được, json parse lại đúng schema.

## Success Criteria

- [ ] 4 format render từ cùng list results, nhất quán số liệu.
- [ ] HTML mở bằng browser (file://) hiển thị đủ, không cần network.
- [ ] Comparison table xếp hạng đúng theo overall; caveat + rubric_version ở header mọi format.
- [ ] Diagnosis text đúng: `hitnrun2`→"cost-killed", `engulfing`→"no directional edge".
- [ ] JSON re-parse thành dict hợp lệ, có aliases (dedup) + version.

## Risk Assessment

- **HTML escaping**: metric text/diagnosis chèn vào HTML phải escape (dù nội dung tự sinh, giữ an toàn + đúng). Dùng `html.escape`.
- **Output path**: ghi vào `--out` dir (Phase 8 truyền), default `docs/backtest-rubric/` [Validation S2]. Artifact commit như snapshot (docs/ được commit).
- **Over-engineering HTML**: giữ KISS — editorial tĩnh + collapsible, KHÔNG thêm chart lib. YAGNI.
