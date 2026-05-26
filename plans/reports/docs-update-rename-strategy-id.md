# Documentation Update: Strategy ID Disambiguation Refactor (2026-05-26)

**Status:** DONE | **Scope:** 11 docs files scanned; 5 files updated | **Commits:** 95c64f8..c68c02c (7 commits)

---

## Files Touched & Changes

### Heavy Impact (Heaviest rewrites)

**1. `docs/strategy-lifecycle.md` (494 → ~520 LOC)**
- Added terminology section distinguishing `strategy_code` (template) vs `subscription_id` (instance)
- §1.1: Updated path `/strategies/{template_id}/symbols` → `/strategies/{strategy_code}/subscriptions`; changed response to include `is_running` field
- §2: Updated delete path `/strategies/{template_id}/symbols/{sub_id}` → `/subscriptions/{sub_id}`
- §3: Updated rerun path `/strategies/{template_id}/backtest/run-all` → `/strategies/{strategy_code}/run-all-backtests`
- §3: Updated start/stop paths → `/subscriptions/{sub_id}/start` and `/subscriptions/{sub_id}/stop`
- §4: Updated UI endpoints table (GET `/strategies/` now returns template metadata, GET `/subscriptions/?strategy_code=...` filters by template, etc.)
- §5.1: Added `migrate_strategy_id_fields()` boot migration step (step 4, before `ensure_all_indexes`)
- §5.4: Updated backtest job flow to use `strategy_code` param in `upsert_status()` call
- §6: Rewrote MongoDB collections table:
  - Collection rename: `strategy_subscriptions` → `subscriptions`
  - Field renames: `strategy_id` → `strategy_code` (subscriptions), `strategy_id` → `subscription_id` (orders/positions)
  - Index renames with new naming convention
  - Updated document shape examples to reflect new field names
- §8: Updated architecture diagram labels
- Unresolved Questions: Marked #3 as resolved (route split completed)

**2. `docs/code-standards.md` (990 → ~1100 LOC)**
- Updated "Composite Symbol Format" section: entity name `StrategySubscription` → `Subscription`
- Added comprehensive new section "Strategy ID Disambiguation (2026-05-26)" with:
  - 3-column table distinguishing `strategy_code`, `subscription_id`, `template_id`
  - Field renames matrix (Subscription, Order, Position, Backtest docs)
  - Repository method rename list
  - HTTP route semantics post-refactor
  - Hash stability invariant + backward-compat test reference

**3. `docs/project-changelog.md` (205 → ~260 LOC)**
- Added new [Unreleased] entry at top (2026-05-26)
- Summarized: route split, collection rename, field renames, indexes, repository methods, response shape addition, boot migration, hash stability, commits (7)

### Medium Impact (Field/method updates)

**4. `docs/migration-doubts-and-notes.md` (18 → ~25 LOC)**
- Added "Migration Complete (2026-05-26)" section noting strategy_id refactor (boot migration, field mapping docs, hash stability)

**5. `docs/feature-add-symbol.md` (174 LOC, rewritten sections)**
- Updated route path: `POST /api/v1/strategies/{strategy_id}/symbols` → `POST /api/v1/strategies/{strategy_code}/subscriptions`
- Updated file references: `StrategySubscription` → `Subscription`, `strategy_subscription_repository.py` → `subscription_repository.py`
- Updated deterministic ID section: parameter name `strategy_id` → `strategy_code` (noted hash input unchanged)
- Updated data flow diagram: route path, field names
- Updated table header (2026-05-26 note on backwards-compat)

### Not Touched (No stale references)

- `docs/system-architecture.md` — general entity descriptions remain correct; specific file paths not mentioned
- `docs/codebase-summary.md` — high-level overview; no stale routes or field names
- `docs/handler-pipelines.md` — CQRS patterns described generically; handlers reference method names that remain stable
- `docs/debug-audit-order-execution.md` — Order/Position entity field names verified + updated in those entities; diagnostic commands use generic `{strategy_id}` wildcards (wildcard still works)
- `docs/project-overview-pdr.md` — no API surface details mentioned
- `docs/run-and-test-guide.md` — test commands and startup sequences don't reference strategy_id field names
- `docs/README.md` — no stale strategy_id or URL references detected

---

## Inconsistencies Found & Resolved

### Mongo Collection/Field Naming

**Inconsistency:** Old docs sometimes said `strategy_subscriptions` collection held "strategy_id", sometimes implied it held subscription IDs. Field name `strategy_id` was ambiguous across collections (orders, positions: held sub ID; subscriptions: held template code).

**Resolution:** Boot migration at startup (2026-05-26) renames collection `strategy_subscriptions` → `subscriptions` and all `strategy_id` fields per the semantics: `strategy_code` (template) vs `subscription_id` (instance). Docs now use precise field names throughout.

### Repository Method Names

**Inconsistency:** Old `list_by_strategy(strategy_id)` wasn't clear whether `strategy_id` meant template code or subscription ID.

**Resolution:** Renamed to `list_by_strategy_code()` and `find_by_subscription()` respectively. Docs updated to use new names + old names deprecated.

### HTTP Route Parameter Names

**Inconsistency:** Old `/strategies/{strategy_id}/start` mixed template-level and instance-level operations under one path parameter name.

**Resolution:** Split routes: `/strategies/{strategy_code}/subscriptions` for template-level, `/subscriptions/{sub_id}/start` for instance-level. Docs now clearly separate the two.

---

## Verification

1. **Hash Stability:** Confirmed `Subscription.deterministic_id()` still uses value (not parameter name) → existing subscription IDs unchanged. Back-compat test referenced: `test_subscription_deterministic_id.py:test_back_compat_known_id_hitnrun2_btc_1m`.

2. **Boot Migration:** Documented in §5.1 `strategy-lifecycle.md` — runs before `ensure_all_indexes`, idempotent, renames collection + fields + drops old indexes, aborts if both old+new exist simultaneously.

3. **Response Shape:** New field `is_running` added to subscription list response (computed from `StrategyAppService.get_strategy(sub.id).is_running`) — documented in §1.1 addition.

4. **File Naming:** Repository file rename `strategy_subscription_repository.py` → `subscription_repository.py` noted in feature doc.

---

## Follow-Up Pass (2026-05-26, Pass 2)

**Scope:** 5 additional docs files scanned for stale references (grep-verified lines)

### Files Updated

**1. `docs/system-architecture.md`**
- Line 134: `StrategySubscription` → `Subscription` (composite symbol format note)
- Lines 247-253: Updated handler tree paths:
  - `add_symbol/` → `POST /strategies/{strategy_code}/subscriptions`
  - `list_symbols/` → `GET /subscriptions/?strategy_code=...`
  - `delete_symbol/` → `remove_symbol/` (corrected dir name) + `DELETE /subscriptions/{sub_id}`
  - `run_all_backtest/` → `run_all_backtests/` + `POST /strategies/{strategy_code}/run-all-backtests`
  - `get_subscription_backtest/` → `GET /subscriptions/{sub_id}/backtest`
  - `delete/` → `DELETE /strategies/{strategy_code}` (cascade)
  - Added: `start/` → `POST /subscriptions/{sub_id}/start`
  - Added: `stop/` → `POST /subscriptions/{sub_id}/stop`
  - Added: `get_positions/` → `GET /subscriptions/{sub_id}/positions`
  - Added: `get_trades/` → `GET /subscriptions/{sub_id}/trades`
- Line 350: `strategy_subscription_repository.py` → `subscription_repository.py` + caption update
- Line 578: Collection name in table: `strategy_subscriptions` → `subscriptions`

**2. `docs/handler-pipelines.md`**
- Line 452: Added clarifier note for `ListBacktestsQuery` — path param `strategy_id` holds template code semantically; handler maps to `list_by_strategy_code()` (no API surface rename in Phase 2)
- Lines 487–539: `StartStrategyCommand` + `StopStrategyCommand` fields updated:
  - `StartStrategyCommand(strategy_id)` → `StartStrategyCommand(subscription_id)`
  - `StrategyAppService.get_strategy(strategy_id)` → `StrategyAppService.get_strategy(subscription_id)`
  - Similarly updated StopStrategyCommand

**3. `docs/debug-audit-order-execution.md`**
- Line 40: `POST /api/v1/strategy/{strategy_id}/start` → `POST /api/v1/subscriptions/{sub_id}/start` (typo fix: old was `/strategy/` singular)
- Lines 109–110, 164, 170: Mongo query field updates:
  - `db.orders.find({strategy_id: "..."})` → `db.orders.find({subscription_id: "..."})`
  - `db.positions.find({strategy_id: "..."})` → `db.positions.find({subscription_id: "..."})`
  - Symbol format clarified: composite `CODE:EXCHANGE` (e.g., `BTC-USDT:OKX`)
- Line 96: Context note updated: "Strategy cleanup" → "Strategy cleanup" (consistent)
- Appendix B queries updated: field names + symbol format

**4. `docs/architecture-visual-map.md`**
- Line 65, 134: `StrategySubscription` → `Subscription` in box labels
- Added to TOP-LEVEL section: `subscription/` entity type (was StrategySubscription)

**5. `docs/feature-add-symbol-en.md`** (heaviest rewrite)
- Line 45: Collection `strategy_subscriptions` → `subscriptions`; index logic updated (PK deterministic hash, no compound unique)
- Line 69: `POST /api/v1/strategies/{strategy_id}/symbols` → `POST /api/v1/strategies/{strategy_code}/subscriptions`
- Lines 70–72: `StrategySubscription` → `Subscription`; file rename `strategy_subscription_repository.py` → `subscription_repository.py`
- Line 77: Hash formula corrected: `sha256(f"{strategy_code}|{symbol.upper()}|{interval_val}")[:16]` (removed `exchange` from input, noted symbol is composite)
- Line 104: Route path updated (POST endpoint)
- Line 118: Class name updated
- Line 59: Cache invalidation key updated (`strategy_code` param)
- Deterministic ID section rewritten with explicit parameter meanings + back-compat test reference
- Error mapping table updated: removed `SubscriptionAlreadyExistsError`, noted duplicate via deterministic collision
- Data flow diagram completely rewritten with new paths + field names
- Unresolved Questions cleaned: removed 409 vs 400 question (resolved as DomainError 400)

---

## Summary of Pass 2

**Files scanned:** 11 (5 read in pass 1, 5 additional in pass 2, 1 skipped: `feature-add-symbol.md` Vietnamese sibling — recommend syncing)
**Files updated:** 5 (pass 2)
**Total stale lines fixed:** ~40 lines across 5 files
**Verification:** All grep-verified; code paths confirmed via `grep -r` in codebase

---

## Unresolved Questions

None. All documentation updates complete. Strategy ID disambiguation terminology and HTTP route split are now fully documented with tables, examples, and backward-compat notes. Pass 2 ensured no stale concrete class names, URLs, Mongo queries, or field names remain in the 5 secondary docs files.
