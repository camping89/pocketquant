---
name: exit-reason-never-persisted-trades-route-reads-positions
description: 2026-11-06 exit_reason consults; e1db1f8d persists it only in the trades collection; closed positions rows have no reason and no join key to trades; UI design = switch the subscription trades route to TradeRepository
metadata:
  type: project
---

Until develop e1db1f8d (2026-11-06) no live/paper close persisted a reason. That commit added `exit_reason: str | None` to `TradeClosedEvent` and `Trade`; it lands in the `trades` collection (live via LiveTradeCollector, backtest via backtest_report_app_service). Old rows have no field (`from_mongo` reads None).

**Why:** `git log -S exit_reason` before that commit found the string only in a 2026-06-28 plans report. Prod evidence quoting `exit_reason: None / side: None` came from that report's mental model, not a schema.

**How to apply:**
- `GET /subscriptions/{id}/trades` served closed `positions` rows (StrategyQueryService.get_trades) as of e1db1f8d. Positions rows carry no reason and cannot be joined to `trades`: the paper broker opens its own PositionAggregate (own UUID) while PositionAppService opens a second one from OrderFilledEvent, so `TradeClosedEvent.position_id` != the positions row id (Exness uses the venue position id); `closed_at` is `utc_now()` at engine processing, `exit_time` is the fill time. Counsel 2026-11-06 (second consult): switch the route to a newest-first TradeRepository query and delete `find_closed_by_subscription`; do not add position_id to Trade. Trade-offs accepted: DTO id becomes the trade id (no FE consumer), partial closes become one row each, live rows exist only since collector commit e310892d (2026-07-06).
- `TradeRepository.list_by_subscription` sorts entry_time asc with limit 500 (feeds LiveMetricsQueryService oldest-first); a drawer needs a desc query or it shows the oldest N.
- Trader restart does NOT delete open paper positions: `load_open_positions` keeps every open row, standby `bootstrap_live_instances` loads brokers first, `take_over` restores paper brokers from those rows + `realized_net`. Only `unload_strategy` drops a paper position (reconcile orphan/edit paths). Pending stops are dropped at takeover and re-placed by the strategy.
- Exness venue vocabulary is still unverified: `sltp` comes from the API yaml enum and a fixture; what the venue reports for a close we requested is unknown until the first live close after deploy.
- Prod check 2026-11-06 ~15:50Z (before the trades-route deploy): 3 paper XAUUSD:EXNESS subs, `trades` count per run_id == closed `positions` count (12/12, 1/1, 53/53), so the switch keeps row counts; 0 of 66 trades had exit_reason (e1db1f8d not yet deployed); the positions-based route returned `quantity: 0.0` on every closed row (closed position quantity), the trades route returns the fill quantity instead. live_trading false, entries_paused true, 1 open paper position per sub, no pending orders. Local `master` ref is stale; compare against `origin/master`.
