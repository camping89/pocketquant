---
phase: 5
title: "Static AST audit"
status: completed
priority: P2
dependencies: [1]
---

# Phase 5: Static AST audit

## Overview

Phân tích **strategy definition** (không phải result): parse source strategy service qua AST → degrees-of-freedom, SL/TP geometry, entry-frequency class, lookahead-safety. Đây là nửa "dùng definition" của câu hỏi user, độc lập với DB.

## Requirements

- Functional: từ `strategy_code` → resolve source file qua `STRATEGY_REGISTRY[code].__module__`; parse `_DEFAULTS`, đếm tunable params (DoF), trích SL/TP formula shape, phát hiện lookahead risk.
- Non-functional: fallback "unknown" thay vì crash khi strategy shape lạ; chỉ 3 strategy hiện có nên chấp nhận brittleness có kiểm soát.

## Architecture

```
scripts/rubric/
  static_audit.py   # audit_strategy(strategy_code) -> StrategyAudit dict
```

Trích xuất:
- **degrees_of_freedom**: số key trong `_DEFAULTS` (tunable params). Gray-penalty: nhiều param = overfit risk cao. `engulfing_pullback30_touch` = 5 params.
- **sl_tp_geometry**: nhận diện pattern (SL = pattern extreme ± buffer; TP = max/min(1R, key_level)) — heuristic từ AST (tìm assignment tới `sl`/`tp`/`level`), fallback "custom".
- **entry_frequency_class**: heuristic — per-bar continuation (arm mỗi bar) vs rare setup. Đọc structure `on_bar_completed` (có deque/armed state → stateful setup).
- **lookahead_safety**: tìm dấu hiệu dùng bar chưa đóng / index tương lai. Strategy hiện dùng `prev_bar` + snapshot-before-append (an toàn) — audit confirm pattern đó, cờ nếu thấy truy cập forward index.
- **direction_bias**: đọc default `direction` param (long/short/both).

Cách resolve file:
```python
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
cls = STRATEGY_REGISTRY[strategy_code]
src_file = inspect.getsourcefile(cls)
tree = ast.parse(Path(src_file).read_text())
```

## Related Code Files

- Create: `scripts/rubric/static_audit.py`
- Reference (parse, not import-execute): `src/pocketquant/core/domain/strategy/services/*.py`, `STRATEGY_REGISTRY` in `services/__init__.py`

## Implementation Steps

1. Resolve file qua `STRATEGY_REGISTRY[code]` + `inspect.getsourcefile`.
2. `ast.parse` → walk: tìm `_DEFAULTS` dict (đếm keys = DoF), class `on_bar_completed` (entry-freq heuristic), assignment tới sl/tp/level (geometry).
3. Lookahead heuristic: cờ nếu thấy index `[i+k]` với k>0 trên bar array, hoặc dùng bar hiện tại trước khi đóng. Confirm safe pattern (prev_bar + snapshot).
4. Fallback: field không trích được → "unknown", không raise.
5. Unit test: chạy trên 3 strategy (`engulfing`, `hitnrun2`, `engulfing_pullback30_touch`) → DoF đúng, geometry nhận diện, không crash.

## Success Criteria

- [ ] `audit_strategy('engulfing_pullback30_touch')`: DoF=5, direction_bias='both', geometry nhận SL=pattern-extreme/TP=max(1R,key), lookahead='safe'.
- [ ] 3 strategy audit không crash; field lạ → 'unknown'.
- [ ] DoF khớp số param thật trong `_DEFAULTS` mỗi strategy.
- [ ] Lookahead audit confirm safe cho cả 3 (đều dùng prev_bar/snapshot pattern).

## Risk Assessment

- **AST brittle** khi strategy đổi cấu trúc → fallback 'unknown' + không raise; chỉ 3 strategy nên chi phí thấp. Ghi rõ đây là heuristic, không phải formal verification.
- **Geometry heuristic false-negative**: strategy phức tạp → 'custom'. Chấp nhận; DoF + direction luôn trích được (ít brittle nhất).
- **Import side-effect**: `STRATEGY_REGISTRY` import kéo core domain — chỉ để resolve class path, KHÔNG chạy strategy. Import an toàn (domain thuần, không I/O ở module load).
