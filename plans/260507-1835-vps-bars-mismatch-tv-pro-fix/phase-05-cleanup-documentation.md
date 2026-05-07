# Phase 05 — Cleanup + documentation

## Context links

- All prior phases (01-04)
- Docs root: `pocketquant/docs/`
- Documentation rules: `~/.claude/rules/documentation-management.md`

## Overview

- **Priority:** P2 — final cleanup
- **Status:** pending
- **Effort:** 2h
- **Description:** Sync docs to reflect Binance-only architecture (TradingView fully removed). No code changes. Conventional commit, no AI references.

## Key insights

- TV code deleted entirely in Phase 03 — docs must remove all "TV as backup / cold path" framing
- Audit + resync reports become permanent artifacts (success metric evidence) — link from changelog
- Deployment guide must drop all TV credential requirements and `MARKET_DATA_PROVIDER` references (none — single provider)
- `handler-pipelines.md` references `tradingview_client.py` for sync_1m → must update to `BinanceClient` / `IDataProvider`
- Major version bump in `pyproject.toml` due to breaking removal of `tradingview_*` Settings fields and TV creds env vars

## Requirements

### Functional
- Update 6 doc files (list below) to reflect: (a) Binance is the sole crypto data source, (b) `BarBuilder` delta-volume contract, (c) TV completely removed (no env flag, no cold path), (d) audit/resync runbook (2y window), (e) `IDataProvider` + `IRealtimeQuoteProvider` extension points
- Add changelog entry under `docs/project-changelog.md` with date + version bump (major)
- README quick-start: confirm no TV creds present anywhere
- Bump version in `pyproject.toml` (major increment)

### Non-functional
- Conventional commits: `docs:` prefix
- No emojis (per codebase convention)
- Concise: avoid duplicating phase plan content; link to plan directory
- Update `last_updated` headers in modified docs

## Architecture

```
phase-05 docs touch points:

system-architecture.md       ──► IDataProvider section + Binance-only path
codebase-summary.md          ──► binance/ folder added; tradingview/ removed
handler-pipelines.md         ──► sync_1m provider abstracted to IDataProvider
project-changelog.md         ──► entry: "Migrate to Binance, remove TradingView"
deployment-guide.md          ──► drop TV creds; add 2y resync runbook
README.md                    ──► quickstart: no TV mention
pyproject.toml               ──► major version bump
```

## Related code files

**Modify (docs only):**
- `pocketquant/docs/system-architecture.md`
- `pocketquant/docs/codebase-summary.md`
- `pocketquant/docs/handler-pipelines.md`
- `pocketquant/docs/project-changelog.md`
- `pocketquant/docs/deployment-guide.md`
- `pocketquant/README.md`

**Modify (version):**
- `packages/pocketquant-core/pyproject.toml` — bump major
- `packages/pocketquant-api/pyproject.toml` — bump major (if separate)

**Read for reference:**
- All Phase 01-04 plan files (canonical source of truth)
- `plans/reports/audit-260507-bar-quality.md` (pre-audit, link from changelog)
- `plans/reports/audit-260507-bar-quality-post.md` (post-audit, link from changelog)

## Implementation steps

1. **`system-architecture.md`** — Market Data section:
   - Diagram: Binance REST + WS (`@aggTrade`) as sole crypto path
   - Remove all TV references (no "cold backup", no "fallback")
   - Document `IDataProvider` + `IRealtimeQuoteProvider` extension points (for future OKX / stocks providers)
   - Note: `BarBuilder` requires per-tick **delta** volume contract
2. **`codebase-summary.md`** — under `pocketquant.core.infrastructure`:
   - Add `binance/` subfolder entry
   - **Remove** `tradingview/` subfolder entry
   - Update "Data Providers" section: list only `BinanceClient` (impl of `IDataProvider`)
   - Adjust LOC count estimate (down from TV removal, up from binance/)
   - Bump "Last Updated" header
3. **`handler-pipelines.md`** — sync_1m cron entry:
   - Replace `TradingViewClient.fetch_ohlcv` references with `IDataProvider.fetch_ohlcv` (current impl: `BinanceClient`)
   - Note rate-limit budget: Binance 1200 weight/min
4. **`project-changelog.md`** — new top entry:
   ```
   ## 2026-05-07 — Binance migration + TradingView removal (BREAKING)
   - Switched crypto data path to Binance public REST + WS (`@aggTrade`)
   - Removed TradingView entirely: deleted `infrastructure/tradingview/`, dropped `tvdatafeed` dep, removed `TRADINGVIEW_USERNAME/PASSWORD` env vars
   - Fixed BarBuilder cumulative-volume aggregation bug (Bug #2) via delta-pass adapter
   - Re-synced last 2 years (all canonical tfs); flat_pct dropped from ~100% to <5%
   - BREAKING: `Settings.tradingview_username/password` fields removed
   - Audit reports: plans/reports/audit-260507-bar-quality{,-post}.md
   ```
5. **`deployment-guide.md`**:
   - Remove `TRADINGVIEW_USERNAME/PASSWORD` from env vars table
   - Remove any "TV credentials required" notes
   - Add runbook: "2-year re-sync procedure" (link to Phase 04, including multi-day execution option via `--symbols` filter)
   - Add note: stale `TRADINGVIEW_*` env vars in production are ignored (Pydantic `extra="ignore"`); operator may safely delete from `.env`
6. **`README.md`** — quickstart:
   - Remove TV creds from `.env` example
   - Add line: "Crypto market data: Binance public REST/WS (no auth required)"
7. **`pyproject.toml`** — major version bump (breaking change: TV Settings removed).
8. Final grep sweep: `grep -r "tradingview\|TRADINGVIEW\|tvdatafeed" pocketquant/docs/ pocketquant/README.md` returns 0 hits (or only historical changelog entries).
9. Lint Markdown (`markdownlint` if configured) — clean.
10. Commit:
    ```
    docs: sync architecture for Binance-only data provider; remove TradingView refs
    ```

## Todo list

- [ ] Update `system-architecture.md` (Binance-only, IDataProvider/IRealtimeQuoteProvider extension)
- [ ] Update `codebase-summary.md` (binance/ added, tradingview/ removed, last-updated)
- [ ] Update `handler-pipelines.md` (sync_1m provider abstraction)
- [ ] Add changelog entry (BREAKING) to `project-changelog.md`
- [ ] Update `deployment-guide.md` (drop TV creds, add 2y resync runbook)
- [ ] Update `README.md` quickstart
- [ ] Bump major version in `pyproject.toml`
- [ ] Final grep sweep: 0 active TV refs in docs
- [ ] Lint Markdown
- [ ] Conventional commit `docs: ...`

## Success criteria

- All 6 docs reflect post-migration / post-removal state
- Changelog entry present with BREAKING marker; links audit reports
- `grep -r "TRADINGVIEW_USERNAME" pocketquant/docs/ pocketquant/README.md` returns 0 hits
- `grep -r "TradingViewClient" pocketquant/docs/` returns 0 active refs (only changelog historical context)
- `grep -r "MARKET_DATA_PROVIDER" pocketquant/docs/` returns 0 hits
- Conventional commit landed with `docs:` prefix
- Major version bumped in `pyproject.toml`
- No file >200 lines (docs may exceed but stay readable)

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stale TV references survive in untouched docs | Medium | Low | Final grep sweep across all `docs/` for `tradingview\|TRADINGVIEW\|tvdatafeed` |
| Changelog version mismatch with code release | Low | Low | Pin date 2026-05-07; align with merge commit |
| Deployment guide drifts from actual `.env.example` | Low | Medium | Cross-reference `.env.example` updated in Phase 03 |
| Major version bump breaks downstream consumers' lockfiles | Medium | Medium | Document breaking change prominently in changelog top; consumers regenerate lockfiles |
| Operator misses runbook for stale `TRADINGVIEW_*` env in `.env` | Low | Low | Deployment guide explicit note: "safe to delete; ignored by Pydantic" |

## Security considerations

- Docs include no secrets.
- TV removal eliminates two env vars (creds) → reduced misconfig leak surface.

## Next steps

- Merge PR; deploy to production VPS.
- Run Phase 04 production scripts (audit + 2y resync) post-deploy.
- Monitor first 24h for `@aggTrade` event-rate impact on `BarAppService` (per Phase 01 risk).

## Unresolved questions

1. Should `pyproject.toml` major-version bump be 2.0.0 or current+1.0.0? **Recommendation:** Follow existing semver convention; if currently `1.x.y`, bump to `2.0.0`. Defer concrete number to release time.
2. Add deprecation note for any external consumers documenting TV removal upgrade path? **Answer:** No external consumers identified; defer until needed. Changelog BREAKING entry is sufficient.
