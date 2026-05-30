# TODO: Centralize & Standardize Entity IDs on UUIDv7

**Goal (as requested):** every persisted entity uses UUIDv7 for `_id` — eliminate the hash-PK and ObjectId outliers so the ID strategy is consistent and centralized.

**Status:** DECIDED (scope), NOT STARTED (no coding yet — doc only).

### Owner Decisions (locked)

1. **Motivation:** consistency only (no specific bug). Uniformity is the goal in itself.
2. **Target:** `_id` is **100% UUIDv7** for every collection. No representation drift, no natural keys, no hash keys.
3. **Re-key all collections WE own to uuid7** (A subscriptions hash, B tracked_symbols composite, C1 job_history ObjectId). Data migration is **required and accepted**.
4. **One allowed exception: `apscheduler_jobs`** — library-owned `_id`. **Do NOT patch/fork APScheduler.** Left as the library writes it.

## Current State (verified in code)

`generate_id()` / `generate_id_str()` in `core/common/uuid.py` already wrap Python 3.14 `uuid7()`. 11 of 13 collections already key on uuid7 — only the representation differs (UUID-field-stringified vs `id: str`). That part is **already consistent in value**; the real inconsistencies are 3 deliberate exceptions:

| # | Collection | Current `_id` | Why it exists today |
|---|---|---|---|
| A | `subscriptions` | `sha256(strategy_code\|symbol\|interval)[:16]` | Idempotent re-subscribe (same triple → same PK → insert fails / no dup). Stable cache key + URL. |
| B | `tracked_symbols` | composite `symbol` string (`BTCUSDT:BINANCE`) | Symbol IS the identity; natural unique key. |
| C | `job_history` / `apscheduler_jobs` | Mongo ObjectId / APScheduler job-name | Not domain entities — created by insert default / 3rd-party lib. |

## Scope (per locked decisions)

Two workstreams, both in scope. WS1 is prerequisite cleanup; WS2 is the re-keying + migration.

### Workstream 1 — Representation consistency (LOW RISK)
Make every domain entity hold `id: UUID` and stringify only at the Mongo boundary. Today it's mixed:
- `UUID` field + `str()` on write: `Bar`, `Symbol`, `SyncStatus` ✅ already this form
- `id: str` holding uuid7 string: `OrderAggregate`, `PositionAggregate`, `BacktestResult`, `OptimizationResult`, backtest orders/trades → convert to `id: UUID`

Pure internal-type cleanup, no data migration, no behavior change.

### Workstream 2 — Re-key natural/hash PKs to uuid7 (HIGH RISK, migration required)
Per decision #3, every outlier is re-keyed. Disposition:

| # | Collection | Action | Idempotency / uniqueness preserved via |
|---|---|---|---|
| A | `subscriptions` | hash `_id` → uuid7 | **NEW unique compound index** `(strategy_code, symbol, interval)` — must be added in the SAME change or dedup is lost |
| B | `tracked_symbols` | composite-symbol `_id` → uuid7 | keep existing unique index on `symbol` |
| C1 | `job_history` | ObjectId → uuid7 | n/a (append-only log) |
| C2 | `apscheduler_jobs` | **EXEMPT — leave as-is** | library-owned; do NOT patch APScheduler |

For A, the migration must also rewrite the logical FK `subscription_id` in `orders`, `positions`, and `backtest_runs` to the new uuid7 values, in lockstep, or those references orphan.

## Risk Assessment

| Risk | Severity | Detail |
|---|---|---|
| Lose subscription idempotency | **HIGH** | Hash PK is the dedup mechanism. uuid7 PK means two identical `(strategy_code,symbol,interval)` subscriptions can both insert unless a unique compound index replaces it. Must add index in the same change. |
| Break prod subscription IDs | **HIGH** | `subscription.py:54-57` docstring explicitly forbids changing the recipe — existing prod IDs (in URLs, `orders.subscription_id`, `positions.subscription_id`, `backtest_runs.subscription_id`) depend on it. Changing PK orphans all FK references unless migrated. |
| FK fan-out | **HIGH** | `subscription_id` is a logical FK in `orders`, `positions`, `backtest_runs`. Re-keying subscriptions requires rewriting those references in lockstep. |
| APScheduler store not ours | **N/A — exempt** | `apscheduler_jobs._id` is library-owned; left as-is by decision, not patched. |
| Migration on prod data | **MEDIUM** | Live VPS Mongo holds real subscriptions/orders/positions. Needs backup + tested migration script (see `docs/deployment.md` mongodump procedure). |

## Honest Note on Cost (decision already made — recorded, not re-litigated)

Owner chose 100% uuid7, consistency-only, migration accepted. Recording the trade-off for whoever implements, not to reverse the call:

- The `subscriptions` hash PK was an **intentional idempotency design**, not sloppiness. Re-keying to uuid7 keeps the same guarantee via a unique compound index — so it's *more moving parts for an equal guarantee*, plus a one-time breaking migration of prod IDs (URLs, FKs). This is the expensive part of the work; budget for it.
- WS1 is cheap and risk-free — do it first regardless.
- `apscheduler_jobs` is the single accepted exception (library-owned `_id`, not patched).

Pair the change with a `docs/code-standards.md` rule so the consistency is enforced going forward, not just retrofitted once: *"Every persisted `_id` = UUIDv7 via `generate_id()`. No natural keys, no hash keys, no ObjectId. Uniqueness/idempotency constraints go on secondary unique indexes, never on `_id`."*

## Task Breakdown (for implementation — not yet started)

0. ~~Code standard~~ — DONE: uuid7-only `_id` rule written to `docs/code-standards.md` §12.6 (incl. library-owned exception).
1. **WS1 — representation:** convert `id: str` entities (`OrderAggregate`, `PositionAggregate`, `BacktestResult`, `OptimizationResult`, backtest orders/trades) to `id: UUID`; update `to_mongo`/`from_mongo`; `just types` + tests. No migration.
2. **WS2-B `tracked_symbols`:** add uuid7 `_id`, keep `symbol` unique index; migration re-keys docs.
3. **WS2-C1 `job_history`:** ObjectId → uuid7; migration re-keys docs.
4. **WS2-A `subscriptions` (highest risk, do last, isolated):**
   a. Add unique compound index `(strategy_code, symbol, interval)` FIRST (preserves dedup).
   b. Write migration: assign uuid7 to each subscription, build old→new id map.
   c. Rewrite `subscription_id` FK in `orders`, `positions`, `backtest_runs` via the map.
   d. Backup prod (mongodump per `docs/deployment.md`); dry-run; execute; `11-verify.sh`.
   e. Note: any external bookmarks/URLs using old subscription IDs break — accepted.
5. `apscheduler_jobs` — **no action** (exempt, library-owned).
6. Update `docs/system-relationship-map.md` §8 ERD + table + the `_id` prose to the final state (all-uuid7 except `apscheduler_jobs`).

## Files In Scope

- `packages/pocketquant-core/src/pocketquant/core/common/uuid.py` (already centralized — no change)
- `packages/pocketquant-core/src/pocketquant/core/domain/{bar,symbol,sync_status,order,position,tracked_symbol}/entities.py`
- `packages/pocketquant-trading/src/pocketquant/trading/domain/subscription.py` (A — high risk)
- `packages/pocketquant-backtest/src/pocketquant/backtest/domain/entities.py`
- Repositories with `create_index` (subscriptions, tracked_symbols) if PKs change
- `docs/code-standards.md`, `docs/system-relationship-map.md`

## Unresolved Questions

1. ~~Motivation~~ — RESOLVED: consistency only.
2. ~~Target representation~~ — RESOLVED: 100% uuid7, `id: UUID`.
3. ~~Breaking subscription IDs acceptable~~ — RESOLVED: yes, migration required and accepted.
4. ~~apscheduler_jobs exception~~ — RESOLVED: **exempt, do NOT patch the library.** It is the single allowed exception (third-party-owned `_id`). All collections we own are uuid7.

All questions resolved. Ready to implement in a separate session.

**Binding rule recorded:** `docs/code-standards.md` §12.6 "Primary Key Rule — UUIDv7 Only (MANDATORY)" — includes the one library-owned exception.
