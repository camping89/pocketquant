# Exness broker behind a default-off switch

2026-10-19 · Phase 07 of `plans/261009-0858-exness-venue-lean-sync-refactor` · commit `2528272` on develop

## What shipped
`ExnessBrokerAdapter` (`core/infra/brokers/exness/`) and the engine changes it needs: `IBrokerPort.normalize_quantity` and `fills_async`, `IStrategyService.on_order_rejected`, `OrderCancelledEvent` from async cancels, and async fill wiring for brokers that declare it. `BrokerFactory` refuses `exness` while `EXNESS_LIVE_TRADING` is false, and the client refuses order calls on its own. Develop CI run `39187699750` passed on all three timezones. Prod still has `exness_live_trading == False` and does not contain the broker package, because only master deploys.

## Decisions that differ from the plan text
- Exits skip the stop-loss rule and the daily loss cap. Blocking a close would keep the risk open, and the broker-side stop loss is already attached on open.
- A close must equal the held units, because `OrderAggregate.fill` raises on a quantity mismatch.
- The snapshot keeps positions the adapter mapped from its own fills, together with their repo rows. The first version did not mark those rows as matched, so a reconnect would have treated our own open position as closed while away. The go/no-go review caught it, and a regression test now pins it.
- The delegation ceiling went from 87 to 93 with coordinator approval. Four of the six new delegations are `IBrokerPort` members, so restructuring could not reach 87 without padding.

## Open before go-live
- An orphaned in-flight request, or a lost ACK or 429, keeps the snapshot gate closed until restart, because nothing schedules the reconcile.
- `_on_snapshot` replaces `_positions` after awaits, so a fill applied concurrently can be lost.
- A fill that arrives during an ACK call that then fails with TRANSPORT reaches an order the engine already rejected.
