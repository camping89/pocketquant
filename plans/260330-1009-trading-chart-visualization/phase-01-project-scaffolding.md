---
phase: 1
priority: P0
effort: S
status: complete
---

# Phase 1: Project Scaffolding

## Overview

Bootstrap `packages/pocketquant-web/` as a Vite + React + TypeScript SPA. No Python deps — pure Node.js package.

## Context

- [plan.md](plan.md)
- Existing monorepo uses `uv` workspace for Python; this is a separate Node.js package
- CORS already configured in FastAPI (`packages/pocketquant-api/src/pocketquant/api/main_extensions.py:115-121`)

## Requirements

- Vite 6 + React 19 + TypeScript 5.7+
- `lightweight-charts` v5.x
- `@tanstack/react-query` v5.x for data fetching
- ESLint + Prettier (minimal config)
- Dev proxy to FastAPI `http://localhost:41920`

## Architecture

```
packages/pocketquant-web/
├── src/
│   ├── api/                  # API client module
│   ├── components/
│   │   ├── chart/            # Chart components
│   │   ├── controls/         # UI controls
│   │   └── layout/           # App shell, header
│   ├── hooks/                # Custom hooks
│   ├── lib/                  # Indicator math, utilities
│   ├── types/                # Shared TypeScript types
│   ├── App.tsx               # Root component
│   ├── main.tsx              # Entry point
│   └── index.css             # Global styles (dark theme)
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── vite.config.ts
├── eslint.config.js
└── .gitignore
```

## Implementation Steps

1. Create directory `packages/pocketquant-web/`
2. Initialize with `npm create vite@latest . -- --template react-ts` (or manual setup)
3. Install deps:
   ```bash
   npm install lightweight-charts @tanstack/react-query
   npm install -D @types/react @types/react-dom eslint prettier
   ```
4. Configure `vite.config.ts`:
   ```typescript
   export default defineConfig({
     plugins: [react()],
     server: {
       port: 5173,
       proxy: {
         '/api': {
           target: 'http://localhost:41920',
           changeOrigin: true,
         },
       },
     },
   });
   ```
5. Set up dark theme base CSS (CSS variables for chart colors)
6. Create empty directory structure (`api/`, `components/chart/`, etc.)
7. Create `App.tsx` shell with QueryClientProvider
8. Verify `npm run dev` starts and renders

## Related Code Files

- **Create:** `packages/pocketquant-web/` (entire directory)
- **Read:** `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` (CORS config reference)

## Todo

- [x] Scaffold Vite project
- [x] Install dependencies
- [x] Configure dev proxy
- [x] Dark theme CSS variables
- [x] App shell with QueryClientProvider
- [x] Verify dev server runs

## Success Criteria

- `npm run dev` starts on port 5173
- Proxy routes `/api/*` to FastAPI at 41920
- TypeScript compiles without errors
- Empty app renders with dark background
