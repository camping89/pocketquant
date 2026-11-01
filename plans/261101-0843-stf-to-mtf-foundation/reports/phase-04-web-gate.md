# Phase 04 report: web gate

The web type check is green, and CI now runs a `web` job (lint, `tsc -b`, vitest) that `build-web` needs. The first CI run failed because the generated route tree was untracked; tracking it fixed the run.

## Entry gate

`dirty=0 synced=yes`; Phase 03 report ends `Result: PASS`; `d1_deployed_at=` count `1`; `docker-ok`.

## Task 04.1: cover the interrupted status

Red output (`npx tsc -b 2>&1 | grep -c "error TS2741"` printed `2`):

```
src/components/monitor/job-status-palette.ts(3,7): error TS2741: Property 'interrupted' is missing in type '{ completed: string; running: string; missed: string; skipped_max_instances: string; failed: string; stuck: string; error: string; }' but required in type 'Record<JobRunStatus, string>'.
src/components/monitor/job-status-palette.ts(13,14): error TS2741: Property 'interrupted' is missing in type '{ completed: string; running: string; missed: string; skipped_max_instances: string; failed: string; stuck: string; error: string; }' but required in type 'Record<JobRunStatus, string>'.
```

After the fix: `tsc=0`; lint `0 errors, 6 warnings`; vitest `70 passed (70)`. Commit `d1183d65` `fix(web): cover the interrupted job status in the palette`.

## Task 04.2: CI web job

Verify printed `['npm ci', 'npm run lint', 'npm test', 'npx tsc -b'] ['tests', 'web']`. Commit `724f02a4` `ci: run the web lint, type check and tests`.

## Task 04.3: CLOSE

- GATES: `Contracts: 6 kept, 0 broken.`; ratchet exit 0; ruff `All checks passed!`; web `tsc=0`, lint `0 errors`, vitest `70 passed`.
- FULLSUITE on `724f02a4`: `4 failed, 1255 passed, 1 skipped, 50 warnings, 4 errors in 123.86s (0:02:03)`; unexpected count `0`.
- Verify attempt 1: run `41319626649` on `724f02a4` printed `failure failure`. The three `tests` jobs passed; `web` failed at "Type check" with `src/main.tsx(5,27): error TS2307: Cannot find module './routeTree.gen'` and TS2345/TS2353 on every `createFileRoute` path.
- Verify attempt 2: run `41320465008` on `c0c78fb6` printed `success success` (`web` job `success`).

## Deviation: route tree not tracked

- Cause (verified): `git check-ignore -v web/src/routeTree.gen.ts` printed `.gitignore:2:routeTree.gen.ts`. The file had never been tracked. Only the TanStack Router vite plugin (`web/vite.config.ts`) generates it, so a fresh CI checkout running `tsc -b` before any vite command has no route tree. Locally the file existed from earlier vite runs.
- Counsel: `kongming` advised tracking the generated file (the TanStack Router FAQ says to commit `routeTree.gen.ts`) over adding a CI generate step, which would need either an unlocked `@tanstack/router-cli` or a fifth `npx vite build` step.
- Applied: regenerated with `npx vite build` (exit 0), deleted the ignore rule and its comment from the root `.gitignore`, and committed the file. `git check-ignore` now returns `1`. Web GATES re-run: `tsc=0`, lint `0 errors, 6 warnings`, vitest `70 passed`. Task 04.2 Verify re-run unchanged and passing. The CI workflow was not changed.
- Files changed beyond the phase Files list: `.gitignore`, `web/src/routeTree.gen.ts` (new tracked file).
- Trade-off: this reverses the ignore rule added in `74de04b0`; route changes now show the regenerated tree in diffs. No doc mentions the route tree, so no doc update is owed.
- FULLSUITE was not re-run after `c0c78fb6`: that commit touches only `.gitignore` and one web file, and CI ran the full Python suite green under three time zones on it.
- Commit `c0c78fb6` `chore(web): track the generated route tree so a fresh checkout type-checks`.

## Commits

`d1183d65`, `724f02a4`, `c0c78fb6` (all on `origin/develop`).

Result: PASS
