---
title: Broker per subscription and one venue adapter per process
date: 2026-10-21
summary: Subscriptions now carry paper or exness, and one Exness adapter serves the whole process; shipped to develop as 94b5a98.
---

# Broker per subscription and one venue adapter per process

## What happened
- `Subscription.broker` defaults to `paper`. A stored value other than `paper` or `exness` makes `from_mongo` raise.
- `POST /strategies/{code}/subscriptions` takes `broker`. An unknown value returns 422. `exness` returns 400 `BROKER_DISABLED` while `EXNESS_LIVE_TRADING` is false.
- Reconcile passes the subscription's broker into `StrategyConfig`.
- The broker pool keys paper by contract spec and venue brokers by type only. A venue broker is reused even after its last holder unloads.
- Removed `Settings.default_broker` and both `get_available_types` methods (the backtest stand-in had one too).

## Friction
- The literal dead-code grep matched orphan bytecode of deleted modules. Removing the bytecode caches made it pass.
- An edit script written with Python on Windows produced CRLF in the working copy; the files were converted back to LF before commit.

## Risks noted
- `StrategyAppService.stop()` disconnects only brokers held by a loaded strategy, so an unheld pooled Exness adapter is not disconnected at engine stop. Harm is shutdown-only.
- A bad stored broker fails more than reconcile: `list_all` raises, so startup bootstrap, the subscription list and delete by id fail too. This fails closed; the fix is a direct Mongo edit.
- Phase 05 must pass `Safeguards` to the shared adapter by reference, never as copied values, or Pause stops reaching it.

## Next steps
- Phase 03: re-resolve the access point.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
