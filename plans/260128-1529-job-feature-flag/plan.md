---
title: "Job Feature Flag"
description: "Add config flag to enable/disable background jobs in API process"
status: pending
priority: P3
effort: 15m
branch: master
tags: [config, jobs, feature-flag]
created: 2026-01-28
---

# Job Feature Flag

## Goal
Cho phép bật/tắt background jobs trong API process thông qua config.

## Why
- Chuẩn bị cho việc tách API và Worker trong tương lai
- Cho phép chạy API-only hoặc API+Jobs tùy deployment

## Changes Required

| File | Change |
|------|--------|
| `src/config.py` | Thêm `enable_jobs: bool = True` |
| `.env.example` | Thêm `ENABLE_JOBS=true` |
| `src/main.py` | Wrap `register_sync_jobs()` với condition |

## Implementation

### Phase 1: Add Config Flag
→ [phase-01-add-config-flag.md](phase-01-add-config-flag.md)

**Status:** ⬜ Pending

## Success Criteria
- [ ] `ENABLE_JOBS=true` → Jobs chạy bình thường
- [ ] `ENABLE_JOBS=false` → API chạy, không có jobs
- [ ] Default `true` để backward compatible
