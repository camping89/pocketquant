"""Helpers for main.py: middleware, routes, health, and startup utilities.

The app process is the single backend entrypoint — it runs the full trading
runtime (scheduler, WS feed, reconcile loop, backtest worker) AND serves all
HTTP feature routes plus the SPA.
"""

import asyncio
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from dishka import AsyncContainer
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pocketquant.app.market_data.app_services.quote_app_service import QuoteAppService
from pocketquant.app.market_data.app_services.ws_subscription_manager import WsSubscriptionManager
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.core.common.exceptions import register_exception_handlers
from pocketquant.core.common.health import HealthCoordinator
from pocketquant.core.common.idempotency import IdempotencyMiddleware
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.rate_limit import RateLimitMiddleware
from pocketquant.core.common.tracing import CorrelationIDMiddleware, RequestLoggingMiddleware
from pocketquant.core.config import Settings
from pocketquant.core.domain.market_data.interfaces import IRealtimeQuoteProvider
from pocketquant.core.infra.persistence.health_checks import check_database, check_redis
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.core.infra.persistence.repositories.optimization_repository import (
    OptimizationRepository,
)
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.core.infra.scheduling.scheduler import JobScheduler
from pocketquant.engine.app_services.strategy_reconcile_service import (
    StrategyReconcileService,
)

logger = get_logger(__name__)

# All repository types that need MongoDB indexes on startup
_REPO_TYPES: list[type] = [
    OrderRepository,
    PositionRepository,
    BacktestRepository,
    BacktestRequestRepository,
    BacktestOrderRepository,
    BacktestTradeRepository,
    BarRepository,
    SyncStatusRepository,
    SymbolRepository,
    OptimizationRepository,
    JobHistoryRepository,
    SubscriptionRepository,
    TrackedSymbolRepository,
]


async def ensure_all_indexes(container: AsyncContainer) -> None:
    """Ensure MongoDB indexes for all repository collections."""
    repos = [await container.get(rt) for rt in _REPO_TYPES]
    await asyncio.gather(*(repo.ensure_indexes() for repo in repos))
    logger.info("database_indexes_ensured")


# Reverse migration (for rollback):
#     db.subscriptions.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.subscriptions.renameCollection("strategy_subscriptions")
#     db.orders.updateMany({}, {$rename: {subscription_id: "strategy_id"}})
#     db.positions.updateMany({}, {$rename: {subscription_id: "strategy_id"}})
#     db.backtest_runs.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_orders.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_trades.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#     db.backtest_optimization_runs.updateMany({}, {$rename: {strategy_code: "strategy_id"}})
#
# Field rename matrix:
#     strategy_subscriptions → subscriptions:    strategy_id → strategy_code
#     orders:                                    strategy_id → subscription_id
#     positions:                                 strategy_id → subscription_id
#     backtest_runs:                             strategy_id → strategy_code
#     backtest_orders:                           strategy_id → strategy_code
#     backtest_trades:                           strategy_id → strategy_code
#     backtest_optimization_runs:                strategy_id → strategy_code


_LEGACY_INDEX_NAMES: dict[str, list[str]] = {
    "subscriptions": ["ix_strategy_subscriptions_strategy_id"],
    "orders": ["ix_orders_strategy_id"],
    "positions": ["ix_positions_strategy_id"],
    "backtest_runs": [
        "ix_backtests_strategy_id",
        "ix_backtests_strategy_started",
        "ix_backtests_strategy_sharpe",
        "ix_backtests_strategy_sortino",
        "ix_backtests_strategy_winrate",
    ],
    "backtest_orders": ["ix_btorders_strategy_status"],
    "backtest_trades": ["ix_bttrades_strategy_direction"],
    "backtest_optimization_runs": ["ix_optimizations_strategy_id"],
}

_FIELD_RENAME_MATRIX: list[tuple[str, str]] = [
    ("subscriptions", "strategy_code"),
    ("orders", "subscription_id"),
    ("positions", "subscription_id"),
    ("backtest_runs", "strategy_code"),
    ("backtest_orders", "strategy_code"),
    ("backtest_trades", "strategy_code"),
    ("backtest_optimization_runs", "strategy_code"),
]


async def _rename_collection_if_needed(db, old: str, new: str) -> bool:
    """Rename ``old`` collection to ``new`` if migration is pending. Idempotent.

    Returns True if a rename happened, False if already migrated.
    Raises RuntimeError if both collections exist (manual intervention required).
    """
    existing = await db.database.list_collection_names()
    old_exists = old in existing
    new_exists = new in existing

    if old_exists and new_exists:
        raise RuntimeError(
            f"Both '{old}' and '{new}' collections exist — "
            "manual cleanup required before migration can proceed."
        )
    if old_exists and not new_exists:
        await db.database[old].rename(new)
        logger.info("mongo_migration.collection_renamed", old=old, new=new)
        return True
    logger.info("mongo_migration.skipped", collection=old, reason="already_migrated")
    return False


async def _rename_field_if_needed(db, collection: str, old_field: str, new_field: str) -> int:
    """`$rename` ``old_field`` → ``new_field`` on docs that still have the legacy key.

    Returns the count of modified docs (0 if migration already ran on this collection).
    """
    coll = db.database[collection]
    pending = await coll.count_documents({old_field: {"$exists": True}})
    if pending == 0:
        logger.info(
            "mongo_migration.skipped",
            collection=collection,
            field=old_field,
            reason="already_migrated",
        )
        return 0
    result = await coll.update_many(
        {old_field: {"$exists": True}},
        {"$rename": {old_field: new_field}},
    )
    logger.info(
        "mongo_migration.renamed",
        collection=collection,
        old_field=old_field,
        new_field=new_field,
        modified_count=result.modified_count,
    )
    return result.modified_count


async def _drop_legacy_indexes(db, collection: str, index_names: list[str]) -> None:
    """Drop legacy named indexes; tolerate IndexNotFound for idempotency."""
    coll = db.database[collection]
    for name in index_names:
        try:
            await coll.drop_index(name)
            logger.info("mongo_migration.dropped_index", collection=collection, index=name)
        except Exception as exc:
            # IndexNotFound (code 27) is benign — already dropped on a prior run.
            msg = str(exc)
            code = getattr(exc, "code", None)
            if code == 27 or "IndexNotFound" in msg or "index not found" in msg.lower():
                continue
            logger.warning(
                "mongo_migration.drop_index_failed",
                collection=collection,
                index=name,
                error=msg,
            )


async def migrate_strategy_id_fields(container: AsyncContainer) -> None:
    """Idempotent boot migration: rename ``strategy_id`` → ``strategy_code`` / ``subscription_id``.

    Runs BEFORE ``rehydrate_strategies_from_subscriptions`` so the rehydrate
    reads the new field name. Safe to call repeatedly — each step checks
    pending state before doing work.

    Steps:
      1. Rename collection ``strategy_subscriptions`` → ``subscriptions``.
      2. Per-collection ``$rename`` of the legacy ``strategy_id`` field.
      3. Drop legacy named indexes. ``ensure_all_indexes`` re-creates the new ones.
    """
    database = await container.get(Database)

    total_renamed = 0
    try:
        await _rename_collection_if_needed(
            database, old="strategy_subscriptions", new="subscriptions"
        )
        for collection, new_field in _FIELD_RENAME_MATRIX:
            renamed = await _rename_field_if_needed(
                database, collection, old_field="strategy_id", new_field=new_field
            )
            total_renamed += renamed
        for collection, names in _LEGACY_INDEX_NAMES.items():
            await _drop_legacy_indexes(database, collection, names)
    except Exception:
        logger.exception("mongo_migration.failed")
        raise

    logger.info("mongo_migration.completed", total_renamed=total_renamed)


async def migrate_subscription_desired_state(container: AsyncContainer) -> None:
    """Backfill control-plane state on pre-existing subscription docs. Idempotent.

    Old subscriptions lost their RAM run-state on restart; the declarative model
    treats ``desired_state="running"`` as auto-resume, so legacy docs are set to
    ``running`` (reconcile starts them) with ``actual_state="stopped"`` so the
    transition is observable in logs/FE. Only docs LACKING ``desired_state`` are
    touched — a human's later ``stop`` is never re-flipped on redeploy.

    Runs AFTER ``migrate_strategy_id_fields`` (field rename must precede) and
    BEFORE ``rehydrate_strategies_from_subscriptions`` so rehydrate/reconcile read
    the final field shape.

    Mass-start note: this flips EVERY legacy sub to running on first deploy. Pre-
    deploy, count the affected docs on a DB copy:
        db.subscriptions.countDocuments({desired_state: {$exists: false}})
    Rollback (stop everything):
        db.subscriptions.updateMany({}, {$set: {desired_state: "stopped"}})
    """
    database = await container.get(Database)
    coll = database.database["subscriptions"]
    result = await coll.update_many(
        {"desired_state": {"$exists": False}},
        {"$set": {"desired_state": "running", "actual_state": "stopped"}},
    )
    if result.modified_count:
        logger.info(
            "subscription_state_migration.completed",
            modified_count=result.modified_count,
        )


async def migrate_tracked_symbols_uuid_ids(container: AsyncContainer) -> None:
    """Idempotent boot migration: re-key ``tracked_symbols._id`` from composite symbol to uuid7.

    Mongo forbids in-place ``_id`` updates, so each legacy doc (``_id`` is the
    composite symbol string, not parseable as UUID) is deleted and re-inserted
    with a fresh uuid7 ``_id``, all other fields preserved. Delete-before-insert
    is forced by the unique ``symbol`` index — inserting the copy first would
    collide with the legacy doc. Crash between the two ops loses at most one
    doc, which ``seed_tracked_symbols`` re-derives for auto-seeded symbols.

    The unique index is ensured FIRST so the dedup guarantee holds the moment
    ``_id`` stops being the natural key. Docs whose ``_id`` already parses as a
    UUID are untouched — re-runs are no-ops.
    """
    from pocketquant.core.common.uuid import UUID, generate_id_str

    database = await container.get(Database)
    coll = database.database["tracked_symbols"]

    try:
        await coll.create_index([("symbol", 1)], unique=True, name="ix_tracked_symbols_symbol")
    except Exception as exc:
        # A same-name index with a non-unique spec exists from an old deploy —
        # replace it. IndexOptionsConflict (85): same keys, different name;
        # IndexKeySpecsConflict (86): same name, different options.
        if getattr(exc, "code", None) not in (85, 86):
            raise
        await coll.drop_index("ix_tracked_symbols_symbol")
        await coll.create_index([("symbol", 1)], unique=True, name="ix_tracked_symbols_symbol")

    rekeyed = 0
    # Collection is small (admin-curated symbol list) — full scan is fine.
    legacy_docs = await coll.find({}).to_list(length=None)
    for doc in legacy_docs:
        try:
            UUID(str(doc["_id"]))
            continue  # already migrated
        except ValueError:
            pass
        # Log the full doc before deleting — if the process dies between the
        # two ops, an admin-added symbol (not re-derivable by the seeder) can
        # be restored from this line.
        logger.info("tracked_symbols_uuid_migration.rekeying", doc=doc)
        await coll.delete_one({"_id": doc["_id"]})
        await coll.insert_one({**doc, "_id": generate_id_str()})
        rekeyed += 1

    if rekeyed:
        logger.info("tracked_symbols_uuid_migration.completed", rekeyed=rekeyed)


async def migrate_job_history_uuid_ids(container: AsyncContainer) -> None:
    """Idempotent boot migration: re-key legacy ``job_history._id`` ObjectIds to uuid7.

    The write path already generates uuid7 ids; only docs from before that
    change still carry a Mongo ObjectId. The collection is an append-only log
    with no FK consumers, so each legacy doc is copied with a fresh uuid7
    ``_id`` (Mongo forbids in-place ``_id`` updates) and the original deleted.
    Filter ``{"_id": {"$type": "objectId"}}`` matches nothing after the first
    run — re-runs are no-ops. Cursor iteration keeps memory flat on large
    collections; inserted copies have string ids so the cursor never revisits.

    Two orderings per doc, dictated by the unique partial index
    ``idx_skip_idempotency`` on (job_id, scheduled_run_time):
      - Listener-path docs (``scheduled_run_time`` is a date) sit inside that
        index, so the copy would collide while the legacy doc holds the slot —
        delete first, insert after. The full doc is logged before the delete
        so a crash between the two ops is recoverable from the log line.
      - Wrapper-path docs (no ``scheduled_run_time``) insert the copy first,
        tagged ``_migrated_from: <old id>``, then delete — a crash leaves both
        docs behind, and the tag lets the next run skip the re-insert instead
        of duplicating the record.
    """
    from pocketquant.core.common.uuid import generate_id_str

    database = await container.get(Database)
    coll = database.database["job_history"]

    rekeyed = 0
    async for doc in coll.find({"_id": {"$type": "objectId"}}):
        old_id = doc["_id"]
        payload = {k: v for k, v in doc.items() if k != "_id"}

        existing_copy = await coll.find_one({"_migrated_from": str(old_id)}, {"_id": 1})
        if existing_copy is not None:
            # Crash-resume: copy already on disk from a prior run — just
            # finish the delete half.
            await coll.delete_one({"_id": old_id})
        elif isinstance(doc.get("scheduled_run_time"), datetime):
            logger.info("job_history_uuid_migration.rekeying", doc=doc)
            await coll.delete_one({"_id": old_id})
            await coll.insert_one({**payload, "_id": generate_id_str()})
        else:
            await coll.insert_one(
                {**payload, "_id": generate_id_str(), "_migrated_from": str(old_id)}
            )
            await coll.delete_one({"_id": old_id})
        rekeyed += 1
        if rekeyed % 500 == 0:
            logger.info("job_history_uuid_migration.progress", rekeyed=rekeyed)

    if rekeyed:
        logger.info("job_history_uuid_migration.completed", rekeyed=rekeyed)


async def migrate_backtest_request_ids(container: AsyncContainer) -> None:
    """Idempotent boot migration: re-key legacy ``backtest_requests._id`` to uuid7.

    Legacy subscription-kind requests carried a deterministic ``bt:{sub_id}``
    ``_id`` — the old dedup mechanism. Dedup now lives in the partial unique
    index on (sub_id, status=pending), so that index is created FIRST: the
    guarantee must hold the moment ``_id`` stops encoding the subscription.

    Mongo forbids in-place ``_id`` updates, so each ``bt:``-prefixed doc is
    deleted and re-inserted with a fresh uuid7 ``_id``, all other fields
    preserved. Pending docs sit inside the unique index, so delete-before-
    insert is mandatory (the copy would collide while the legacy doc holds the
    slot). The full doc is logged before the delete — a crash between the two
    ops is recoverable from the log line, and the worst case is one lost
    queued request that the next run-all re-creates. Filter
    ``{"_id": {"$regex": "^bt:"}}`` matches nothing after the first run.
    """
    from pocketquant.core.common.uuid import generate_id_str
    from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
        ensure_pending_sub_unique_index,
    )

    database = await container.get(Database)
    coll = database.database["backtest_requests"]

    await ensure_pending_sub_unique_index(coll)

    rekeyed = 0
    legacy_docs = await coll.find({"_id": {"$regex": "^bt:"}}).to_list(length=None)
    for doc in legacy_docs:
        logger.info("backtest_request_uuid_migration.rekeying", doc=doc)
        payload = {k: v for k, v in doc.items() if k != "_id"}
        await coll.delete_one({"_id": doc["_id"]})
        await coll.insert_one({**payload, "_id": generate_id_str()})
        rekeyed += 1

    if rekeyed:
        logger.info("backtest_request_uuid_migration.completed", rekeyed=rekeyed)


async def migrate_backtest_run_cache_ids(container: AsyncContainer) -> None:
    """Idempotent boot migration: re-key legacy ``backtest_runs`` cache docs to uuid7.

    Legacy per-subscription cache docs carried ``_id == subscription_id``
    (16-hex) — the old slot mechanism. The slot guarantee (one cache doc per
    subscription) now lives in the unique sparse index on ``subscription_id``,
    so that index is ensured FIRST: the guarantee must hold the moment ``_id``
    stops encoding the subscription.

    Mongo forbids in-place ``_id`` updates, so each legacy doc is deleted and
    re-inserted with a fresh uuid7 ``_id``, all other fields preserved. The
    legacy doc occupies the unique-index slot, so delete-before-insert is
    mandatory (the copy would collide while the legacy doc holds the slot).
    Unlike admin-curated collections, only the doc id is logged before the
    delete: cache docs embed full equity curves (too large for a log line)
    and a crash between the two ops costs one cache entry that the next
    backtest run repopulates. Single-run docs never carry ``subscription_id``
    and are untouched; the filter matches nothing after the first run.
    """
    from pocketquant.core.common.uuid import generate_id_str
    from pocketquant.core.infra.persistence.repositories.backtest_repository import (
        ensure_subscription_cache_unique_index,
    )

    database = await container.get(Database)
    coll = database.database["backtest_runs"]

    await ensure_subscription_cache_unique_index(coll)

    rekeyed = 0
    legacy_docs = await coll.find(
        {"$expr": {"$eq": ["$_id", "$subscription_id"]}}
    ).to_list(length=None)
    for doc in legacy_docs:
        logger.info("backtest_run_cache_uuid_migration.rekeying", doc_id=doc["_id"])
        payload = {k: v for k, v in doc.items() if k != "_id"}
        await coll.delete_one({"_id": doc["_id"]})
        await coll.insert_one({**payload, "_id": generate_id_str()})
        rekeyed += 1

    if rekeyed:
        logger.info("backtest_run_cache_uuid_migration.completed", rekeyed=rekeyed)


# Collections referencing subscriptions._id and the field that carries it.
_SUBSCRIPTION_FK_FIELDS: list[tuple[str, str]] = [
    ("orders", "subscription_id"),
    ("positions", "subscription_id"),
    ("backtest_runs", "subscription_id"),
    ("backtest_requests", "sub_id"),
]


async def migrate_subscription_uuid_ids(container: AsyncContainer) -> None:
    """Idempotent boot migration: re-key ``subscriptions._id`` to uuid7 + rewrite FKs.

    Legacy docs carried a deterministic sha256 16-hex ``_id`` derived from the
    (strategy_code, symbol, interval) triple — the old dedup mechanism. Dedup
    now lives in the unique compound index on that triple, so the index is
    created FIRST: the guarantee must hold the moment ``_id`` stops encoding
    the triple.

    Unlike the other uuid re-keys, four collections reference this ``_id``
    (see ``_SUBSCRIPTION_FK_FIELDS``), so a crash mid-rewrite must not fork
    ids between the subscription doc and its references — and a subscription
    is user data, so the delete/insert gap must not lose it either. The map
    collection ``_id_migration_map`` makes every step resumable:

      1. Upsert ``{_id: old_id, new_id: uuid7, payload: <doc sans _id>}`` per
         legacy doc — re-runs keep the already-assigned new_id, and the stored
         payload survives a crash between the delete and insert below.
      2. Per map entry: delete the legacy doc, insert ``{payload, _id: new_id}``
         (delete-first is forced by the triple index — the copy shares the
         legacy doc's triple slot), then ``update_many`` each FK field
         ``old_id → new_id``. Every op filters on the old value or checks for
         the copy first, so a partially-completed run resumes cleanly.
      3. Verify no old_id remains in ``subscriptions._id`` or any FK field,
         then drop the map. Residue → log error, KEEP the map, continue boot —
         the next boot retries; the app never blocks on this.

    Runs BEFORE ``rehydrate_strategies_from_subscriptions`` — RAM is empty at
    that point, so no live instance key can hold a stale id.
    """
    from pocketquant.core.common.uuid import UUID, generate_id_str

    database = await container.get(Database)
    subs = database.database["subscriptions"]
    id_map = database.database["_id_migration_map"]

    await subs.create_index(
        [("strategy_code", 1), ("symbol", 1), ("interval", 1)],
        unique=True,
        name="ix_subscriptions_dedup_triple",
    )

    # Step 1 — persist the old→new map (with payload) before touching any doc.
    async for doc in subs.find({}):
        raw_id = str(doc["_id"])
        try:
            UUID(raw_id)
            continue  # already uuid-keyed
        except ValueError:
            pass
        payload = {k: v for k, v in doc.items() if k != "_id"}
        await id_map.update_one(
            {"_id": raw_id},
            {"$setOnInsert": {"new_id": generate_id_str()}, "$set": {"payload": payload}},
            upsert=True,
        )

    # Step 2 — rewrite from the map (covers entries from a crashed prior run
    # whose legacy doc may already be gone, hence map-driven).
    entries = await id_map.find({}).to_list(length=None)
    if not entries:
        return

    for entry in entries:
        old_id, new_id = entry["_id"], entry["new_id"]

        await subs.delete_one({"_id": old_id})
        if await subs.find_one({"_id": new_id}, {"_id": 1}) is None:
            payload = entry.get("payload")
            if payload is not None:
                await subs.insert_one({**payload, "_id": new_id})
            else:
                # Unreachable via step 1 (payload always stored before any
                # delete) — loud marker so data loss is never silent.
                logger.error(
                    "subscription_uuid_migration.payload_missing",
                    old_id=old_id,
                    new_id=new_id,
                )
        logger.info("subscription_uuid_migration.rekeying", old_id=old_id, new_id=new_id)

        for coll_name, field in _SUBSCRIPTION_FK_FIELDS:
            result = await database.database[coll_name].update_many(
                {field: old_id}, {"$set": {field: new_id}}
            )
            if result.modified_count:
                logger.info(
                    "subscription_uuid_migration.fk_rewritten",
                    collection=coll_name,
                    field=field,
                    old_id=old_id,
                    modified_count=result.modified_count,
                )

    # Step 3 — verify, then self-clean the map.
    residue = 0
    for entry in entries:
        old_id = entry["_id"]
        if await subs.count_documents({"_id": old_id}):
            residue += 1
            continue
        for coll_name, field in _SUBSCRIPTION_FK_FIELDS:
            if await database.database[coll_name].count_documents({field: old_id}):
                residue += 1
                break

    if residue:
        # Keep the map so the next boot retries with the same new_ids.
        logger.error("subscription_uuid_migration.residue", count=residue)
    else:
        await id_map.drop()
        logger.info("subscription_uuid_migration.completed", rekeyed=len(entries))


async def recover_stale_backtests(container: AsyncContainer) -> None:
    """Mark any backtest docs stuck in 'running' as 'failed' on startup.

    Safe to call repeatedly — idempotent. Logs once if any docs were updated.
    """
    repo = await container.get(BacktestRepository)
    n = await repo.mark_stale_running_as_failed()
    if n:
        logger.info("stale_backtest_recovery", marked_failed=n)


async def recover_orphan_jobs(container: AsyncContainer) -> None:
    """Mark any job_history docs stuck at status='running' as 'failed' on startup.

    Orphan rows arise when a job's wrapper writes record_start() but the
    process is killed before record_finish() runs (e.g. mid-deploy
    CancelledError). Without this sweep, dashboards show forever-running jobs.
    Safe to call repeatedly — idempotent. Logs once if any docs were updated.

    Must run AFTER ensure_all_indexes (proves DB connectivity) and BEFORE
    start_background_jobs (so new runs aren't racing the reconcile sweep).
    """
    repo = await container.get(JobHistoryRepository)
    n = await repo.reconcile_orphan_running(max_age_seconds=600)
    if n:
        logger.info("orphan_jobs_recovered", marked_failed=n)


async def rehydrate_strategies_from_subscriptions(container: AsyncContainer) -> None:
    """Re-load one strategy instance per persisted subscription on startup.

    Strategy instances live in-process and disappear on every container
    restart, but their subscriptions are durable in MongoDB. Each subscription
    owns its own runtime instance keyed by ``sub.id`` so that subscribing the
    same template to multiple (symbol, interval) pairs results in independent
    instances. Subscriptions whose template no longer exists in the registry
    are skipped with a warning.
    """
    from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
    from pocketquant.core.domain.strategy.value_objects import StrategyConfig
    from pocketquant.engine.app_services.strategy_app_service import StrategyAppService

    sub_repo = await container.get(SubscriptionRepository)
    strategy_service = await container.get(StrategyAppService)

    subs = await sub_repo.list_all()
    if not subs:
        return

    loaded = 0
    for sub in subs:
        sub_id = str(sub.id)
        if strategy_service.get_strategy(sub_id) is not None:
            continue
        strategy_class = STRATEGY_REGISTRY.get(sub.strategy_code)
        if strategy_class is None:
            logger.warning(
                "rehydrate_skipped_unknown_template",
                sub_id=sub_id,
                strategy_code=sub.strategy_code,
            )
            continue
        await strategy_service.load_strategy(
            StrategyConfig(
                id=sub_id,
                name=sub.strategy_code,
                symbol=sub.symbol,
                interval=sub.interval.value,
            ),
            strategy_class=strategy_class,
        )
        loaded += 1

    if loaded:
        logger.info("strategies_rehydrated", count=loaded)


async def start_background_jobs(container: AsyncContainer) -> None:
    """Register background sync jobs with the scheduler.

    NOTE: the sync_jobs module-level container is wired at the top of lifespan()
    in main.py — before any `await` — to win the race against persisted
    MongoDBJobStore jobs that may dispatch during early Dishka resolves.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("background_jobs_disabled")
        return

    from pocketquant.engine.market_data.app_services.sync_jobs import register_sync_jobs

    await register_sync_jobs(
        container=container,
        job_scheduler=await container.get(JobScheduler),
    )
    logger.info("background_jobs_enabled")


async def start_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    """Start WS feed + subscription reconcile loop as background tasks.

    Stores task handles on app.state for lifespan cleanup:
      app.state.ws_task          — IRealtimeQuoteProvider.run_forever()
      app.state.subscription_task — WsSubscriptionManager.run()
    """
    quote_svc = await container.get(QuoteAppService)
    sub_mgr = await container.get(WsSubscriptionManager)

    await quote_svc.start()
    app.state.ws_task = quote_svc.ws_task  # task created inside start()

    app.state.subscription_task = asyncio.create_task(sub_mgr.run())
    logger.info("quote_feed.started")


async def stop_quote_feed(container: AsyncContainer, app: FastAPI) -> None:
    """Cancel WS + subscription tasks then disconnect the provider. 5s timeout each."""
    for attr in ("ws_task", "subscription_task"):
        task: asyncio.Task | None = getattr(app.state, attr, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

    provider = await container.get(IRealtimeQuoteProvider)
    await provider.disconnect()
    logger.info("quote_feed.stopped")


async def start_reconcile_loop(container: AsyncContainer, app: FastAPI) -> None:
    """Start the declarative control-plane reconcile loop as a background task.

    Gated on ``enable_jobs`` — same flag as background jobs, so the test/CLI
    profile (``enable_jobs=False``) never spins a live loop. Must start AFTER
    ``rehydrate_strategies_from_subscriptions`` so instances exist; otherwise the
    first tick logs N missing_instance warnings before catching up next tick.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("reconcile_loop_disabled")
        return

    svc = await container.get(StrategyReconcileService)
    app.state.reconcile_task = asyncio.create_task(svc.run())
    logger.info("reconcile_loop.started")


async def stop_reconcile_loop(container: AsyncContainer, app: FastAPI) -> None:
    """Cancel the reconcile task. Must run BEFORE quote-feed stop + container.close
    so reconcile never issues start/stop against an engine that is shutting down."""
    task: asyncio.Task | None = getattr(app.state, "reconcile_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    logger.info("reconcile_loop.stopped")


async def start_backtest_worker(container: AsyncContainer, app: FastAPI) -> None:
    """Start the backtest-request queue worker as a background task.

    Gated on ``enable_jobs`` (same as scheduler/reconcile) so the test/CLI
    profile never drains the queue. The worker owns ALL backtest compute,
    replacing the removed APScheduler ``bt:*`` one-off jobs.
    """
    settings = await container.get(Settings)
    if not settings.enable_jobs:
        logger.info("backtest_worker_disabled")
        return

    worker = await container.get(BacktestRequestWorker)
    app.state.backtest_worker_task = asyncio.create_task(worker.run())
    logger.info("backtest_worker.started")


async def stop_backtest_worker(container: AsyncContainer, app: FastAPI) -> None:
    """Cancel the backtest-worker task. Must run BEFORE container.close so the
    worker never dispatches against an engine that is shutting down."""
    task: asyncio.Task | None = getattr(app.state, "backtest_worker_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    logger.info("backtest_worker.stopped")


async def register_health_checks(container: AsyncContainer, app: FastAPI) -> None:
    """Register health check functions with the coordinator."""
    hc = await container.get(HealthCoordinator)
    hc.register("database", partial(check_database, app.state.database))
    hc.register("redis", partial(check_redis, app.state.cache))


def handle_startup_failure(error: Exception) -> None:
    """Display a rich error panel and re-raise so lifespan finally block runs.

    Raises the original exception so FastAPI's lifespan context manager propagates
    it as a startup error (process exits), but the finally block in lifespan()
    executes first — cancelling WS/subscription tasks and closing the DI container.
    Using os._exit() would bypass that cleanup; sys.exit() / re-raise does not.
    """
    from rich.console import Console
    from rich.panel import Panel

    console = Console(stderr=True)
    console.print(
        Panel(
            f"[bold red]{type(error).__name__}[/]: {error}",
            title="Startup Failed",
            border_style="red",
        )
    )
    console.print("\n[dim]Your code:[/]")
    console.print("  -> [cyan]pocketquant.app.main[/] in lifespan")
    console.print("  -> [cyan]pocketquant.core.infra.persistence.mongodb[/] in connect")
    raise error


def configure_middleware(app: FastAPI, settings) -> None:
    """Attach all middleware layers and global exception handlers."""
    from fastapi.exceptions import RequestValidationError

    register_exception_handlers(app, validation_error_cls=RequestValidationError)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, capacity=200, refill_rate=20.0)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(CorrelationIDMiddleware)


async def _list_jobs_from_mongo(
    database: Database, history_repo: JobHistoryRepository
) -> list[dict[str, Any]]:
    """Read apscheduler_jobs + job_history directly from Mongo.

    apscheduler_jobs stores serialised APScheduler job docs. We read raw Mongo
    docs and project only the stable fields (id, next_run_time). The func_ref
    is stored inside the pickled payload — we skip deserialisation and expose
    only the last-run enrichment from job_history instead.
    """
    coll = database.database["apscheduler_jobs"]
    raw_jobs = await coll.find({}, {"_id": 1, "next_run_time": 1}).to_list(length=200)

    job_ids = [doc["_id"] for doc in raw_jobs]
    last_runs: dict[str, dict[str, Any]] = {}
    if job_ids:
        try:
            last_runs = await history_repo.get_latest_by_job_ids(job_ids)
        except Exception:
            logger.warning("system_jobs.last_runs_failed", exc_info=True)

    result = []
    for doc in raw_jobs:
        job_id = doc["_id"]
        # MongoDBJobStore stores next_run_time as a UTC float timestamp
        # (datetime_to_utc_timestamp), None when the job is paused.
        next_run = doc.get("next_run_time")
        entry: dict[str, Any] = {
            "id": job_id,
            "next_run": (
                datetime.fromtimestamp(next_run, tz=UTC).isoformat()
                if next_run is not None
                else None
            ),
            "last_run": last_runs.get(job_id),
        }
        result.append(entry)
    return result


def register_routes(app: FastAPI, settings) -> None:
    """Register health endpoint, all feature routers, and SPA serving."""
    from pocketquant.app.routes.backtest import backtest_router, run_all_backtests_router
    from pocketquant.app.routes.market_data import router as market_data_router
    from pocketquant.app.routes.market_data_quotes import router as quote_router
    from pocketquant.app.routes.strategy import strategy_router, subscription_router
    from pocketquant.app.routes.tracked_symbols import router as tracked_symbols_router
    from pocketquant.app.routes.trading_orders_positions import trading_router

    @app.get("/health")
    @inject
    async def health_check(
        health_coordinator: FromDishka[HealthCoordinator],
    ) -> dict:
        result = await health_coordinator.check_all()
        result["version"] = settings.app_version
        result["environment"] = settings.environment
        return result

    api = APIRouter(prefix=settings.api_prefix, route_class=DishkaRoute)

    @api.get("/system/jobs")
    async def list_jobs(
        database: FromDishka[Database],
        history_repo: FromDishka[JobHistoryRepository],
    ) -> list[dict]:
        # Read the APScheduler Mongo store directly — no scheduler API coupling,
        # and the route works identically when enable_jobs=false.
        return await _list_jobs_from_mongo(database, history_repo)

    from pocketquant.app.routes.system_jobs import router as system_jobs_router

    api.include_router(market_data_router)
    api.include_router(tracked_symbols_router, prefix="/market-data")
    api.include_router(quote_router)
    api.include_router(system_jobs_router)
    api.include_router(strategy_router)
    api.include_router(run_all_backtests_router)
    api.include_router(subscription_router)
    api.include_router(trading_router)
    api.include_router(backtest_router)

    app.include_router(api)

    # StaticFiles + SPA fallback — after API routes so /api/* is never intercepted
    # repo root = 4 levels up from src/pocketquant/app/main_extensions.py
    web_dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if web_dist.is_dir():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="static-assets")

        # include_in_schema=False: static-file serving, not API surface — keeps
        # OpenAPI/route snapshots independent of whether web/dist was built.
        @app.get("/{path:path}", include_in_schema=False)
        async def spa_fallback(path: str) -> FileResponse:
            """Serve index.html for all non-API routes (SPA fallback)."""
            file = web_dist / path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(web_dist / "index.html")

        logger.info("spa_mounted", path=str(web_dist))
    else:
        # Expected in prod (web ships in its own container); locally it means
        # `npm run build` hasn't produced web/dist yet.
        logger.info("spa_not_mounted", path=str(web_dist))
