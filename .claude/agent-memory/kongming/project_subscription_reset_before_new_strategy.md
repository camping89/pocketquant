---
name: subscription-reset-before-new-strategy
description: 2026-10-31 user plans a subscription "reset" before writing a new strategy; MTF (multi-timeframe) question raised and judged not blocking
metadata:
  type: project
---

On 2026-10-31 the user planned to reset subscriptions before writing a new strategy and asked whether multi-timeframe support must be decided first.

**Why:** Subscriptions are strictly single-interval (unique triple strategy_code/symbol/interval, trader routes bars by symbol AND interval). No MTF path exists for live or backtest. Kongming advised: reset level and MTF are independent decisions; keep schema unchanged (YAGNI); if MTF is later wanted, prefer in-strategy aggregation from the 1m stream or a `context_intervals` list on the subscription, not repo pulls inside strategies.

**How to apply:** If the new strategy work resurfaces, check whether MTF became a real requirement before proposing schema changes. DELETE /subscriptions/{id} only removes the doc; orders/positions/trades keyed by subscription_id stay in Mongo, and an Exness venue position stays open on unload.
