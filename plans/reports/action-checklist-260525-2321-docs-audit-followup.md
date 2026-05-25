# Docs Audit — Action Checklist

**Source audit:** `D:\w\_me\algo-bot\plans\reports\brainstorm-260525-1930-docs-audit-toc.md`
**How to use:** Work top to bottom. Check `[x]` as you finish.

---

## P0 — Critical (done in session 260525-2327)

- [x] **1. Fix CLAUDE.md package count** — updated to "5-package monorepo (4 Python uv workspace + 1 Node frontend)"; added `pocketquant-web` row + noted uv exclude
- [x] **2. Refresh TODO.md** — replaced 4 stale items; added Status column, completed-recently section, and removed-do-not-reintroduce section
- [x] **3. Resolve plan 260511-1408 phantom dependency** — deleted plan dir (8 files) + brainstorm report via `git rm` (staged, awaiting commit)
- [x] **4. Write `pocketquant-config\README.md`** — wrote layout + operator-task table + conventions + cross-links
- [x] **6. Mark sandbox brainstorms as IMPLEMENTED** — added IMPLEMENTED banner to both files with verified locations
- [x] **7. Update `migration-doubts-and-notes.md`** — added "Last reviewed" date + clarified YAGNI defer status
- [x] **8. Delete historical YAML footnote from root README** — removed line 129 paragraph
- [x] **9. Close out cook-260525-0834 Phase 2** — status changed to DONE; lint marked OUT OF SCOPE (pre-existing baseline); manual smoke marked PASS (verified via VPS deploy)

### Item #14 — delete completed plans + reports (done)

- [x] Group A: `pocketquant/plans/260511-1408-backtest-analysis-panel/` + brainstorm report (9 files git-staged)
- [x] Group B: workspace `plans/260525-0829-move-symbol-selector-to-charts/` (3 files removed, irrecoverable)
- [x] Group C: `pocketquant/plans/260525-1006-deployment-gaps/` (2 files git-staged)
- [x] Group D: 6 workspace `plans/reports/*.md` historical reports (irrecoverable)

### Skipped (per user direction)

- ~~5. Add workspace-root README~~ — user said no
- ~~14. Add PLANS.md index~~ — user said no, prefer deletion of completed plans

---

## P1 — Pending (do this sprint)

- [ ] **10. Rewrite handler-pipelines.md API paths** — *2-3 h*
  - File: `D:\w\_me\algo-bot\pocketquant\docs\handler-pipelines.md`
  - Change: pre-composite-symbol paths `/{exchange}/{symbol}` → composite `/{symbol}`
  - Verify against actual FastAPI routers in `packages\pocketquant-api\`

- [ ] **11. Translate `feature-add-symbol.md` to English** — *1 h*
  - File: `D:\w\_me\algo-bot\pocketquant\docs\feature-add-symbol.md` (Vietnamese)
  - Action: create `feature-add-symbol-en.md` with English translation

- [ ] **12. Trim `codebase-summary.md` to ≤400 LOC** — *1-2 h*
  - File: `D:\w\_me\algo-bot\pocketquant\docs\codebase-summary.md` (currently 796 lines)
  - Move depth into `system-architecture.md`; keep as quick package-map

- [ ] **13. Trim `debug-audit-order-execution.md`** — *1-2 h*
  - File: `D:\w\_me\algo-bot\pocketquant\docs\debug-audit-order-execution.md` (currently 401 lines)
  - Reduce to 7-step golden path; move edge cases to appendix

- [ ] **15. Refocus `ddd-strategic-map.md`** — *1 h*
  - File: `D:\w\_me\algo-bot\pocketquant\docs\ddd-strategic-map.md`
  - Remove aggregate enumeration (overlaps system-architecture)
  - Keep only: bounded contexts, context relationships, ubiquitous language

---

## P2 — Next quarter (nice-to-have)

- [ ] **16. Testing Strategy guide** — 4-6 h
- [ ] **17. CONTRIBUTING.md** — 2 h
- [ ] **18. Troubleshooting / FAQ** — start 3 h
- [ ] **19. `docs\adr\` folder + 3-5 ADRs** — 4-6 h
- [ ] **20. API reference / OpenAPI spec export** — 1 day
- [ ] **21. Monitoring & Alerting runbook** — defer until prod observability matures

---

## Pending git commit

The following pocketquant changes are staged but not committed (commit them when ready):

```
M  pocketquant/CLAUDE.md
M  pocketquant/README.md
M  pocketquant/TODO.md
M  pocketquant/docs/migration-doubts-and-notes.md
D  pocketquant/plans/260511-1408-backtest-analysis-panel/ (8 files)
D  pocketquant/plans/260525-1006-deployment-gaps/ (2 files)
D  pocketquant/plans/reports/brainstorm-260511-1408-backtest-analysis-panel.md
```

Plus untracked:
```
?? pocketquant/docs/strategy-lifecycle.md  (pre-existing, unrelated)
?? pocketquant/plans/reports/action-checklist-260525-2321-docs-audit-followup.md  (this file)
```

Suggested commit message (split into 2 or keep as one):
```
docs: refresh CLAUDE.md, TODO.md, README.md + close stale plans

- CLAUDE.md: clarify 5-package layout (4 uv + 1 web)
- TODO.md: refresh checklist, add Status column, remove obsolete items
- README.md: drop historical YAML footnote
- migration-doubts: add last-reviewed date
- delete completed plan 260525-1006-deployment-gaps
- delete abandoned plan 260511-1408-backtest-analysis-panel
- delete related brainstorm report
```
