# Phase 08 — End-to-end verification

**Priority:** Final gate before shipping.
**Status:** ⏳ pending, blocked by 4+6+7

## Scope

Verify the full stack: lint, types, unit tests, integration tests, manual smoke against a real running stack (Mongo + Redis + FastAPI + Vite).

## Steps

### Backend
```bash
just lint
just types
just test
just test-pkg core
just test-pkg trading
just test-pkg backtest
just test-pkg api
```

All must exit 0.

### Frontend
```bash
cd packages/pocketquant-web
npm run lint
npx tsc --noEmit
npm run build
```

All must exit 0.

### Migration verification on real dev DB

1. Snapshot current Mongo: `mongodump --uri "$MONGODB_URL" --out /tmp/predeploy-snapshot`
2. Deploy new code, boot the API.
3. Tail logs and confirm:
   - `mongo_migration.renamed` lines for each collection
   - `mongo_migration.completed` total > 0
4. Verify shape of one doc per collection (mongosh):
   - `db.strategy_subscriptions.findOne({})` — has `strategy_code`, no `strategy_id`
   - `db.orders.findOne({})` — has `subscription_id`, no `strategy_id`
   - `db.positions.findOne({})` — has `subscription_id`, no `strategy_id`
   - `db.backtests.findOne({})` — has `strategy_code`, no `strategy_id`
5. Verify indexes: `db.<col>.getIndexes()` shows new names, no legacy `*_strategy_id` indexes.

### Manual smoke flow

Using the Bruno collection at `tests/http` (or curl):

1. `GET /api/v1/strategies` — lists `["hitnrun2"]`.
2. `POST /api/v1/strategies/hitnrun2/subscriptions` body `{"symbol":"BTCUSDT:BINANCE","interval":"1m"}` → 201 with sub.id.
3. `POST /api/v1/subscriptions/{sub_id}/start` → 200, `{"subscription_id": "...", "status":"started"}`.
4. `GET /api/v1/subscriptions/{sub_id}` → 200, `is_running: true`.
5. `POST /api/v1/subscriptions/{sub_id}/stop` → 200.
6. `POST /api/v1/strategies/hitnrun2/run-all-backtests` → 200, `{"job_ids":[...]}`.
7. Poll `GET /api/v1/subscriptions/{sub_id}/backtest` until `status: completed`.
8. `DELETE /api/v1/subscriptions/{sub_id}` → 204.

### Manual UI smoke

Open `http://localhost:5173`:
1. Sidebar lists strategies (templates).
2. Add subscription dialog works.
3. Start button switches to "Stop" (uses `is_running` field).
4. Error states surface real backend messages (validates the original bug-fix).
5. Backtest run-all from the dashboard works.

## Acceptance criteria

- All commands above pass green
- All 8 smoke-flow steps succeed
- No new errors in browser DevTools console
- No `strategy_id` references remain in live code (`rg "strategy_id" -t py -t ts --no-heading | grep -v migrate | grep -v __pycache__ | grep -v node_modules` returns only comments / file names / test fixtures explicitly named)

## Rollback plan

If any verification fails:
1. Stop the API.
2. Restore Mongo snapshot from predeploy.
3. Redeploy the prior commit.
4. Open a tracking issue with the specific failure mode.
5. Iterate on the affected phase only — do not retry whole plan.

## Out of scope

- Performance benchmarking
- Load testing
- Production deploy (this plan covers dev verification only)
