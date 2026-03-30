# QA Test Report: pocketquant-web Package

**Date:** 2026-03-30 | **Package:** pocketquant-web | **Status:** BUILD SUCCESS, LINT FAILURES

---

## Executive Summary

TypeScript compilation and production build both **PASS**. Bundle sizes well within limits. However, **2 critical lint errors** detected in `trading-chart.tsx` related to React 19 ref usage that must be fixed before merging.

---

## 1. TypeScript Compilation

**Status:** ✓ PASS

```
Command: npx tsc -b
Result: No output, 0 exit code
```

- **All TS references resolved:** `tsconfig.json` references `tsconfig.app.json` and `tsconfig.node.json` ✓
- **Strict mode enabled:** `noUnusedLocals`, `noUnusedParameters`, `strict: true` ✓
- **JSX configured:** `jsx: "react-jsx"` with React 19 support ✓
- **No compilation errors detected**

---

## 2. Production Build

**Status:** ✓ PASS

```
Command: npm run build
Result: Built successfully in 154ms
```

### Build Summary

| Artifact | Size | Gzipped | Status |
|----------|------|---------|--------|
| index.html | 0.46 KB | 0.30 KB | ✓ |
| index-*.css | 2.79 KB | 0.92 KB | ✓ |
| index-*.js | 395.46 KB | 124.64 KB | ✓ |
| **Total dist/** | 408 KB | ~126 KB | ✓ |

**Assessment:** Total gzipped bundle (~126 KB) is **well under 500 KB limit**. Main JS chunk includes React 19, React DOM, TanStack Query, lightweight-charts, and all app code.

---

## 3. Lint Analysis

**Status:** ✗ FAILING (2 errors, 2 warnings)

```
Command: npm run lint
Result: Exit code 1
```

### Critical Errors

**File:** `src/components/chart/trading-chart.tsx`

#### Error 1 & 2: Cannot access refs during render (Lines 90)

```typescript
// Line 90 - PROBLEMATIC CODE
useRealtimeBar(exchange, symbol, interval, candleRef.current, volumeRef.current)
```

**Issue:** Calling hook outside of `useEffect` and passing ref `.current` values during render phase.

- `react-hooks/refs` — Cannot access `candleRef.current` during render
- `react-hooks/refs` — Cannot access `volumeRef.current` during render

**Root Cause:** `useRealtimeBar` is a custom hook that internally uses `useEffect`, but it's being called at component render time with refs that should only be accessed inside effects.

**Fix Required:**
1. Wrap the `useRealtimeBar` call in a `useEffect` block, OR
2. Restructure `useRealtimeBar` to accept refs via a ref, not by value, OR
3. Move ref initialization into a separate effect that manages both candle/volume setup and realtime polling

**Recommended Approach:** Wrap in useEffect:
```typescript
useEffect(() => {
  useRealtimeBar(exchange, symbol, interval, candleRef.current, volumeRef.current)
}, [exchange, symbol, interval])
```

#### Warning 1 & 2: Ref cleanup (Lines 82, 106)

```
react-hooks/exhaustive-deps — The ref value 'chartRef.current' will likely have changed
by the time this effect cleanup function runs.
```

**Issue:** Using `chartRef.current` in cleanup function without capturing it in effect scope.

**Fix Required:** Capture ref in effect closure:
```typescript
useEffect(() => {
  const chart = chartRef.current  // capture here
  if (!chart || !data) return

  // ... setup code ...

  return () => {
    if (chart) {  // use captured value, not chartRef.current
      // cleanup
    }
  }
}, [data])
```

---

## 4. Detailed Error Context

### trading-chart.tsx Issues

**Line 87 & 110:** Both useEffect calls have `eslint-disable-line react-hooks/exhaustive-deps` suppressions.

**Lines 75-86:** Cleanup function uses `chartRef.current` directly instead of capturing in closure.

**Lines 104-108:** Same pattern — uses `chartRef.current` in cleanup.

**Line 90:** Calling `useRealtimeBar` hook at component render level (not in effect) with ref values.

---

## 5. Dependencies Analysis

**Installed versions:**
- react: ^19.2.4
- react-dom: ^19.2.4
- @tanstack/react-query: ^5.95.2
- lightweight-charts: ^5.1.0
- typescript: ~5.9.3
- vite: ^8.0.1

**ESLint config:**
- @eslint/js: ^9.39.4
- typescript-eslint: ^8.57.0
- eslint-plugin-react-hooks: ^7.0.1 (enforces React hooks rules)
- eslint-plugin-react-refresh: ^0.5.2

All devDependencies present and compatible.

---

## 6. Build Output Verification

**dist/ structure:**
```
dist/
├── index.html (0.46 KB)
├── assets/
│   ├── index-ChVSHK6h.css (2.79 KB, 0.92 KB gzipped)
│   └── index-CL3S3zBR.js (395.46 KB, 124.64 KB gzipped)
└── favicon.svg
```

**Vite configuration verified:**
- Rolldown bundler working correctly
- Source maps available in dev
- API proxy configured to http://localhost:41920

---

## 7. Critical Issues

| Issue | Severity | File | Line | Action Required |
|-------|----------|------|------|-----------------|
| Cannot access refs during render | ERROR | trading-chart.tsx | 90 | BLOCKING — Wrap `useRealtimeBar` call in useEffect |
| Ref cleanup pattern | WARNING | trading-chart.tsx | 82, 106 | HIGH — Capture chartRef in closure, remove eslint-disable |

---

## 8. Test Summary

| Test | Result | Details |
|------|--------|---------|
| TypeScript compilation | ✓ PASS | 0 errors, all config refs valid |
| Production build | ✓ PASS | 154ms, all assets generated |
| Lint check | ✗ FAIL | 2 errors, 2 warnings in trading-chart.tsx |
| Bundle size | ✓ PASS | 124.64 KB gzipped (well under 500 KB limit) |
| Dependencies | ✓ OK | All required packages installed |

---

## 9. Recommendations

### Immediate Actions (BLOCKING)

1. **Fix Line 90 (useRealtimeBar call):**
   - Move outside render phase into useEffect
   - Dependencies: [exchange, symbol, interval, candleRef, volumeRef]

2. **Fix Lines 75-86 cleanup function:**
   - Capture `chartRef.current` as local const at start of effect
   - Use captured value in cleanup
   - Remove `eslint-disable-line react-hooks/exhaustive-deps`

3. **Fix Lines 104-108 cleanup function:**
   - Apply same pattern as above
   - Ensure proper ref capture

### Post-Fix Validation

- Re-run `npm run lint` — must achieve 0 errors
- Re-run `npm run build` — verify no regressions
- Test in browser dev mode — verify chart renders and real-time updates work

### Optional Improvements

- Consider extracting chart setup logic into custom hook to reduce component complexity
- Add unit tests for `use-realtime-bar.ts` hook behavior
- Consider memoizing indicator series operations to avoid unnecessary re-renders

---

## 10. Coverage Status

**Unit Tests:** None currently (acknowledged in task scope)
**Integration Tests:** None currently
**Manual Testing:** Not performed in this QA cycle

Recommend adding tests for:
- Chart initialization and cleanup
- Real-time bar polling and error handling
- Indicator series addition/removal
- Ref lifecycle management

---

## Unresolved Questions

None — lint errors are clear and actionable.

---

**Report Generated:** 2026-03-30 10:37 UTC
**QA Lead:** Tester Agent
**Next Steps:** Fix lint errors, revalidate build, proceed to code review
