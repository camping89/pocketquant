# Phase 0 — Docs Convention + CLAUDE.md Link

**Priority:** P1 (nguồn chuẩn — làm trước để code mới tuân theo) · **Risk:** none · **Status:** completed

## Context
- Nguồn: `plans/reports/brainstorm-260705-0944-service-naming-convention.md`
- Target: `docs/code-standards.md` (đã có bảng "Class Naming by Layer" ~dòng 355) + `CLAUDE.md`

## Overview
Ghi convention final vào `docs/code-standards.md`, link rõ từ `CLAUDE.md` để agent/dev tương lai tuân theo TRƯỚC khi rename code. Không đụng code.

## Related files
- Modify: `docs/code-standards.md` — cập nhật bảng "Class Naming by Layer"
- Modify: `CLAUDE.md` — mục "Reference docs" thêm dòng trỏ tới naming section

## Implementation steps
1. Cập nhật bảng "Class Naming by Layer" trong `docs/code-standards.md`:
   - App Services → `*AppService` (giữ)
   - **Domain Services → `*DomainService`** (thay "no suffix"); file `*_domain_service.py`
   - **Domain Strategy → `*StrategyService`, interface `IStrategyService`**; file `*_strategy_service.py`
   - **Infra port → `I{Concept}Port`** (thay `I{Concept}`); file `*_port.py`, 1 port/file
   - **Infra impl → `{Source}[{Type}]Adapter`** (thay source-prefixed no-suffix); file `*_adapter.py`
   - **Helper → `*Helper`**; file `*_helper.py`
2. Thêm 3 nguyên tắc: (a) tên tự mã hóa layer; (b) không stack 2 doer-suffix `-er/-or` (trừ danh từ nghiệp vụ như `Broker`); (c) exempt list.
3. Cập nhật section "File Naming" ví dụ cho khớp suffix mới.
4. `CLAUDE.md` → mục "Reference docs (discover detail here)": đảm bảo dòng code-standards.md nêu rõ "Naming convention (suffix theo layer)" trỏ tới section.
5. AS-IS prose, tiếng Việt, giữ identifier tiếng Anh (theo `CLAUDE.md` writing rules). Không changelog/banner.

## Delegate
`docs-manager` agent (đọc report + code-standards.md hiện tại, cập nhật).

## Todo
- [x] Cập nhật bảng "Class Naming by Layer" trong code-standards.md
- [x] Thêm nguyên tắc + exempt list
- [x] Cập nhật ví dụ "File Naming"
- [x] Link/nhấn mạnh naming section trong CLAUDE.md
- [x] Đọc lại: AS-IS, tiếng Việt, không banner

## Success criteria
- Bảng naming trong code-standards.md khớp 100% convention final.
- CLAUDE.md trỏ tới naming section.
- Không đụng file code.
